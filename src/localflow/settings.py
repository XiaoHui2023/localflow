from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ServerSettings(BaseModel):
    bind: str = "0.0.0.0"
    port: int = Field(default=0, ge=0, le=65535)
    anonymous_access: Literal["disabled", "summary", "readonly"] = "summary"
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    trusted_proxies: list[str] = Field(default_factory=list)


class ExecutionSettings(BaseModel):
    backend: Literal["auto", "systemd", "subprocess"] = "auto"
    max_concurrency: int = Field(default=4, ge=1, le=256)
    sigint_grace_seconds: float = Field(default=20, ge=0, le=3600)
    sigterm_grace_seconds: float = Field(default=10, ge=0, le=3600)


class TimeSettings(BaseModel):
    display_timezone: str = "UTC"
    privileged_helper: list[str] = Field(default_factory=list)


class RetentionSettings(BaseModel):
    task_days: int = Field(default=3, ge=1, le=36500)
    log_days: int | None = Field(default=None, ge=1, le=36500, exclude=True)
    event_days: int | None = Field(default=None, ge=1, le=36500, exclude=True)
    cleanup_interval_seconds: int = Field(default=3600, ge=10, le=86400)

    @model_validator(mode="after")
    def normalize_legacy_durations(self) -> RetentionSettings:
        legacy = [value for value in (self.log_days, self.event_days) if value is not None]
        if legacy and any(value != self.task_days for value in legacy):
            raise ValueError("retention uses one task_days duration for task data and terminal output")
        return self


class LoggingSettings(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    service_file_mb: int = Field(default=10, ge=1, le=1024)
    service_files: int = Field(default=5, ge=1, le=100)
    task_file_mb: int = Field(default=100, ge=1, le=102400)
    task_total_mb: int = Field(default=4096, ge=1, le=1048576)
    keep_free_mb: int = Field(default=512, ge=0, le=1048576)
    database_mb: int = Field(default=512, ge=16, le=1048576)
    wal_mb: int = Field(default=16, ge=1, le=1024)


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    time: TimeSettings = Field(default_factory=TimeSettings)

    @model_validator(mode="after")
    def validate_log_budget(self) -> Settings:
        active_budget = self.execution.max_concurrency * self.logging.task_file_mb
        if self.logging.task_total_mb < active_budget:
            raise ValueError(
                "logging.task_total_mb must cover execution.max_concurrency * "
                "logging.task_file_mb"
            )
        return self


_KNOWN_BUNDLED_PLUGIN_DIGESTS = {
    "verification.py": {
        # The two v2 copies shipped by cef4941: the tracked starter root and
        # the package resource. They differed slightly but had the same contract.
        "feefbb2dc3de11ab4eb9779b363a0d273d0ccad50ded0ee327d87dd3a90010aa",
        "130aa8f639de371deac43dfb1aae6c0518b57bf6f7fbbdc1a7881cfddce8d239",
        "7fe5ffde7af4efd2c8157c33a127a24763f899d9243dfca8ab7837d9d8f58dc8",
        "49b5e857c257efb1de3af37e4674c80fa35ce268b06906f7cc92ad0b4b4a2ffd",
        "995bbe2050d0c5c16cc0c336e9927b7d077d8ded09a06ccb01429494f23f2975",
        "f7b013dfea1c62f2d37577c4f5425aa91e99c83eb320a40da7a9ab4f120f9b6d",
        "3d88a1c66203733a44934b74651b918142a1718b592d23844365cb359e860856",
        "e521bd377614f9b9a330829726b65b2cf37f5f0a59b033a094a536179319139a",
        "354cdb8005c131eb8c3d8db4677784be32e6850d27fb0e1d96748f8303956005",
        "4fc099555f0f03457ffd670cdf10f36c0b714b20fe13795fcfa3c02fa02464e9",
    },
    "command.py": {
        "e73ad6a653f86af6bc3c9e55d0588cfda18f74b870978c226ad3dc0d39fc79a9",
        "0a80e82a3178b4271127b818ee551221398df3c2d63f04aaca7a30203c101ee6",
        "b0708115a37c6f00b766cac504e1199ea619eb2221146de5f15d9885721b9d43",
    },
}


def _normalized_text_digest(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _install_or_upgrade_builtin_plugin(destination: Path, source_text: str) -> None:
    if destination.is_symlink():
        return
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if _normalized_text_digest(existing) == _normalized_text_digest(source_text):
            return
        if _normalized_text_digest(existing) not in _KNOWN_BUNDLED_PLUGIN_DIGESTS[destination.name]:
            return
    temporary = destination.with_name(f".{destination.name}.localflow-update")
    temporary.write_text(source_text, encoding="utf-8")
    if os.name != "nt":
        os.chmod(temporary, 0o640)
    os.replace(temporary, destination)


def initialize_root(root: Path) -> None:
    for relative, mode in (
        ("config", 0o750),
        ("config/command", 0o750),
        ("config/verification", 0o750),
        ("scripts", 0o750),
        ("plugins", 0o750),
        ("runtime/instances", 0o750),
        ("logs", 0o750),
        ("secrets", 0o700),
        ("exports", 0o750),
    ):
        path = root / relative
        created = not path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt" and (created or relative != "secrets"):
            os.chmod(path, mode)
    config = root / "config.yaml"
    previous_config = root / "localflow.yaml"
    legacy_config = root / "config" / "server.yaml"
    if previous_config.is_file() and not config.exists():
        previous_config.replace(config)
    elif legacy_config.is_file() and not config.exists():
        legacy_config.replace(config)
    if not config.exists():
        config.write_text(
            "# LocalFlow reads this file only when it starts. Restart after editing.\n"
            "server:\n"
            "  # 0 asks Ubuntu for an available port; use 1-65535 for a fixed port.\n"
            "  port: 0\n"
            "execution:\n"
            "  # auto uses systemd when its user manager is available, otherwise subprocess.\n"
            "  backend: auto\n"
            "retention:\n"
            "  # One duration covers task details and terminal output.\n"
            "  task_days: 3\n",
            encoding="utf-8",
        )
    starter = files("localflow.starter_root")
    for relative in (
        "config/command/hello-world.yaml",
        "config/verification/demo.yaml",
        "Makefile",
        "scripts/simulate.py",
        "cases/case-a/README.txt",
        "cases/case-b/README.txt",
        "cases/smoke.case",
    ):
        destination = root / relative
        if not destination.exists():
            source = starter.joinpath(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            if os.name != "nt" and relative.startswith("scripts/"):
                os.chmod(destination, 0o750)
    for name in ("verification.py", "command.py"):
        example = root / "plugins" / name
        source = files("localflow.builtin_plugins").joinpath(f"{name}.example")
        _install_or_upgrade_builtin_plugin(example, source.read_text(encoding="utf-8"))
    plugin_readme = root / "plugins" / "README.md"
    if not plugin_readme.exists():
        source = files("localflow.builtin_plugins").joinpath("README.md.example")
        plugin_readme.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        if os.name != "nt":
            os.chmod(plugin_readme, 0o640)


def load_settings(root: Path) -> Settings:
    path = root / "config.yaml"
    if not path.exists():
        return Settings()
    return Settings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def validate_deployment(settings: Settings) -> None:
    missing = []
    tls_values = (
        (settings.server.tls_certfile, "tls_certfile"),
        (settings.server.tls_keyfile, "tls_keyfile"),
    )
    if any(value for value, _label in tls_values):
        for value, label in tls_values:
            if not value or not Path(value).is_absolute() or not Path(value).is_file():
                missing.append(label)
    if settings.server.trusted_proxies:
        try:
            for network in settings.server.trusted_proxies:
                ipaddress.ip_network(network, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid trusted proxy network: {exc}") from None
    if missing:
        raise ValueError(
            "configured TLS requires existing absolute certificate and key files: "
            + ", ".join(missing)
        )


def parse_config(path: Path, content: str):
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(content)
    if suffix == ".json":
        return json.loads(content)
    if suffix == ".toml":
        import tomllib

        return tomllib.loads(content)
    raise ValueError("supported formats are YAML, TOML, and JSON")
