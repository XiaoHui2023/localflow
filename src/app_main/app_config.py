from __future__ import annotations

import ipaddress
from pathlib import Path

from configlib import ConfigLoader
from pydantic import ConfigDict, Field, field_validator

from plugin_loader import default_plugin_paths


class AppConfig(ConfigLoader):
    """localflow 主配置：服务监听、插件路径与访问白名单。"""

    model_config = ConfigDict(extra="forbid")

    port: int = Field(
        default=0,
        ge=0,
        le=65535,
        description="监听端口；0 表示由系统分配空闲端口",
    )
    bind_host: str = Field(
        default="0.0.0.0",
        description="监听地址；0.0.0.0 表示所有网卡",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="插件根目录列表，路径相对配置文件所在目录",
    )
    whitelist: list[str] = Field(
        default_factory=list,
        description="客户端 IP 白名单；非空时仅列表内地址可连入",
    )

    @field_validator("whitelist")
    @classmethod
    def _validate_whitelist(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in values:
            text = raw.strip()
            if not text:
                raise ValueError("whitelist 项不能为空字符串")
            ipaddress.ip_address(text)
            normalized.append(text)
        return normalized

    def allows_client(self, client_ip: str) -> bool:
        if not self.whitelist:
            return True
        return client_ip in self.whitelist

    def plugin_paths(self) -> list[Path]:
        """展开插件目录；未配置 sources 时使用仓库默认 plugins/。"""
        if self._file_path is None:
            raise RuntimeError("须通过 from_file() 加载配置后再解析插件路径")

        if not self.sources:
            return default_plugin_paths()

        base = self._file_path.parent.resolve()
        resolved: list[Path] = []
        for raw in self.sources:
            path = Path(raw)
            if not path.is_absolute():
                path = (base / path).resolve()
            else:
                path = path.resolve()
            resolved.append(path)
        return resolved
