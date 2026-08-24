from __future__ import annotations

import ipaddress
import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ServerSettings(BaseModel):
    bind: str = "127.0.0.1"
    port: int = Field(default=0, ge=0, le=65535)
    anonymous_access: Literal["disabled", "summary", "readonly"] = "summary"
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    trusted_proxies: list[str] = Field(default_factory=list)


class ExecutionSettings(BaseModel):
    backend: Literal["systemd", "subprocess"] = "systemd"
    max_concurrency: int = Field(default=4, ge=1, le=256)
    sigint_grace_seconds: float = Field(default=20, ge=0, le=3600)
    sigterm_grace_seconds: float = Field(default=10, ge=0, le=3600)


class TimeSettings(BaseModel):
    display_timezone: str = "UTC"
    privileged_helper: list[str] = Field(default_factory=list)


class RetentionSettings(BaseModel):
    task_days: int = Field(default=90, ge=1, le=36500)
    log_days: int = Field(default=30, ge=1, le=36500)
    event_days: int = Field(default=30, ge=1, le=36500)
    cleanup_interval_seconds: int = Field(default=3600, ge=10, le=86400)


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)
    time: TimeSettings = Field(default_factory=TimeSettings)


def initialize_root(root: Path) -> None:
    for relative, mode in (
        ("config", 0o750),
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
    config = root / "config" / "server.yaml"
    if not config.exists():
        config.write_text(
            "server:\n"
            "  bind: 127.0.0.1\n"
            "  port: 0\n"
            "  anonymous_access: summary\n"
            "execution:\n"
            "  backend: systemd\n"
            "  max_concurrency: 4\n"
            "retention:\n"
            "  task_days: 90\n"
            "  log_days: 30\n"
            "  event_days: 30\n"
            "time:\n"
            "  display_timezone: UTC\n"
            "  privileged_helper:\n"
            "    - /usr/bin/sudo\n"
            "    - -n\n"
            "    - /usr/libexec/localflow-set-time.py\n",
            encoding="utf-8",
        )
    variables = root / "config" / "variables.yaml"
    if not variables.exists():
        variables.write_text("global: {}\nprojects: {}\n", encoding="utf-8")
    templates = root / "config" / "templates"
    templates.mkdir(exist_ok=True)
    command_example = templates / "hello.yaml"
    if not command_example.exists():
        command_example.write_text(
            "name: '${task_name}'\n"
            "working_directory: '${runtime_root}'\n"
            "command: [bash, -lc, 'printf \\\"%s\\\\n\\\" \\\"${message}\\\"']\n"
            "labels: [example, '${project}']\n"
            "mutex_keys: []\n"
            "custom:\n  project: '${project}'\n"
            "variables:\n"
            "  task_name: hello\n"
            "  project: demo\n",
            encoding="utf-8",
        )
    for name in ("verification.py", "declarative.py"):
        example = root / "plugins" / name
        if not example.exists():
            source = files("localflow.builtin_plugins").joinpath(f"{name}.example")
            example.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            if os.name != "nt":
                os.chmod(example, 0o640)


def load_settings(root: Path) -> Settings:
    path = root / "config" / "server.yaml"
    if not path.exists():
        return Settings()
    return Settings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def validate_deployment(settings: Settings) -> None:
    try:
        loopback = ipaddress.ip_address(settings.server.bind).is_loopback
    except ValueError:
        loopback = settings.server.bind == "localhost"
    if loopback:
        return
    missing = []
    for value, label in (
        (settings.server.tls_certfile, "tls_certfile"),
        (settings.server.tls_keyfile, "tls_keyfile"),
    ):
        if not value or not Path(value).is_absolute() or not Path(value).is_file():
            missing.append(label)
    if not settings.server.trusted_proxies:
        missing.append("trusted_proxies")
    else:
        try:
            for network in settings.server.trusted_proxies:
                ipaddress.ip_network(network, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid trusted proxy network: {exc}") from None
    if missing:
        raise ValueError(
            "non-loopback binding requires existing absolute TLS files and trusted proxy ranges: "
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
