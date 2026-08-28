from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import inspect
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    COMMON_CONFIG_FIELDS,
    CommonConfigFields,
    StopStrategy,
    TaskCreate,
    TaskRecord,
    TaskStatus,
)
from .variables import VariableResolver

_loading: list[tuple[str, str, type]] | None = None


class RunFieldSpec(BaseModel):
    """Stable, presentation-independent contract exposed by a plugin run field."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal[
        "string", "integer", "seed", "path", "string-list", "json", "case-picker"
    ]
    label: str | None = Field(default=None, min_length=1, max_length=80)
    required: bool = False
    multiple: bool = False
    count_field: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    default_count_field: str | None = Field(
        default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )

    @model_validator(mode="after")
    def validate_component_options(self) -> RunFieldSpec:
        if self.type == "case-picker":
            if not self.count_field:
                raise ValueError("case-picker requires count_field")
            if self.count_field == self.name or self.default_count_field == self.name:
                raise ValueError("case-picker count fields must differ from its selection field")
        elif self.count_field or self.default_count_field:
            raise ValueError("count fields are only valid for case-picker")
        return self


class InspectionItem(BaseModel):
    """One read-only value shown while preparing a configured run."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: str | None = Field(default=None, min_length=1, max_length=80)
    value: str
    kind: Literal["text", "path", "command"] = "text"
    severity: Literal["ok", "info", "warning", "error"] = "info"
    message: str | None = None


def run_field(name: str, component: str, **options: Any) -> dict[str, Any]:
    """Declare one run-time control without coupling a plugin to the web framework."""

    value = {"name": name, "type": component, **options}
    RunFieldSpec.model_validate(value)
    return value


def plugin(name: str, *, version: str = "1"):
    def decorate(cls: type) -> type:
        if _loading is None:
            raise RuntimeError("@plugin can only register while LocalFlow loads a plugin file")
        _loading.append((name, version, cls))
        return cls

    return decorate


class TemplatePlugin(Protocol):
    run_fields: list[dict[str, Any]]

    def discover(self, context: dict[str, Any]) -> list[str]: ...
    def expand(self, values: dict[str, Any], context: dict[str, Any]) -> list[TaskCreate]: ...


@dataclass(frozen=True)
class LoadedPlugin:
    name: str
    version: str
    digest: str
    generation: int
    instance: TemplatePlugin
    path: str


class PluginRegistry:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.generation = 0
        self.plugins: dict[str, LoadedPlugin] = {}
        self.diagnostics: dict[str, str] = {}

    def load(self) -> None:
        global _loading
        candidates: dict[str, LoadedPlugin] = {}
        diagnostics: dict[str, str] = {}
        generation = self.generation + 1
        for path in sorted(self.directory.glob("*.py")):
            registrations: list[tuple[str, str, type]] = []
            _loading = registrations
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                module_name = f"localflow_user_plugin_{generation}_{path.stem}_{digest[:8]}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"cannot load {path}")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                for name, version, cls in registrations:
                    if name in candidates:
                        raise ValueError(f"duplicate plugin name: {name}")
                    instance = cls()
                    if not hasattr(instance, "run_fields") and hasattr(instance, "fields"):
                        instance.run_fields = instance.fields
                    if not hasattr(instance, "run_fields") or not callable(getattr(instance, "expand", None)):
                        raise TypeError(f"plugin {name} must define run_fields and expand")
                    self._validate_metadata(name, instance)
                    loaded = LoadedPlugin(
                        name, version, digest, generation, instance, str(path)
                    )
                    candidates[name] = loaded
                    for alias in getattr(instance, "aliases", []):
                        if alias in candidates:
                            raise ValueError(f"duplicate plugin name: {alias}")
                        candidates[alias] = loaded
            except Exception as exc:
                diagnostics[str(path)] = f"{type(exc).__name__}: {exc}"
            finally:
                _loading = None
        if candidates or not self.plugins:
            self.plugins = candidates
            self.generation = generation
        self.diagnostics = diagnostics

    def describe(self) -> list[dict[str, Any]]:
        unique = {item.name: item for item in self.plugins.values()}
        descriptions = []
        for item in unique.values():
            config_model = getattr(item.instance, "config_model", None)
            example = getattr(item.instance, "example", {"plugin": item.name})
            api_inputs = getattr(item.instance, "api_inputs", {})
            descriptions.append({
                "name": item.name,
                "title": getattr(item.instance, "title", item.name),
                "description": getattr(item.instance, "description", ""),
                "version": item.version,
                "digest": item.digest,
                "generation": item.generation,
                "fields": item.instance.run_fields,
                "instructions": getattr(item.instance, "instructions", ""),
                "example": example,
                "api": {
                    "endpoint": "/api/v1/runs",
                    "configuration_schema": self._configuration_schema(
                        item.name, item.instance
                    ),
                    "plugin_fields_schema": config_model.model_json_schema()
                    if config_model is not None
                    else None,
                    "input_fields": item.instance.run_fields,
                    "example": {"configuration": example, "inputs": api_inputs},
                },
                "statuses": getattr(item.instance, "statuses", {}),
            })
        return descriptions

    @staticmethod
    def _configuration_schema(name: str, instance: TemplatePlugin) -> dict[str, Any]:
        common = CommonConfigFields.model_json_schema()
        properties = dict(common.get("properties", {}))
        properties["plugin"] = {"const": name, "type": "string", "title": "Plugin"}
        required = {"plugin", *getattr(instance, "required_common_fields", set())}
        definitions = dict(common.get("$defs", {}))
        config_model = getattr(instance, "config_model", None)
        if config_model is not None:
            plugin_schema = config_model.model_json_schema()
            properties.update(plugin_schema.get("properties", {}))
            required.update(plugin_schema.get("required", []))
            definitions.update(plugin_schema.get("$defs", {}))
        schema: dict[str, Any] = {
            "title": f"{name} configuration",
            "type": "object",
            "properties": properties,
            "required": sorted(required),
            "additionalProperties": config_model is None,
        }
        if definitions:
            schema["$defs"] = definitions
        return schema

    def example(self, name: str) -> dict[str, Any]:
        loaded = self.plugins[name]
        value = getattr(loaded.instance, "example", {"plugin": loaded.name})
        if not isinstance(value, dict):
            raise TypeError(f"plugin {name} example must be an object")
        return value

    @staticmethod
    def _validate_metadata(name: str, instance: TemplatePlugin) -> None:
        if not isinstance(instance.run_fields, list):
            raise TypeError(f"plugin {name} run_fields must be a list")
        fields = [RunFieldSpec.model_validate(item) for item in instance.run_fields]
        field_names = [item.name for item in fields]
        if len(field_names) != len(set(field_names)):
            raise ValueError(f"plugin {name} run_fields must have unique names")
        required = getattr(instance, "required_common_fields", set())
        if not isinstance(required, set) or any(not isinstance(item, str) for item in required):
            raise TypeError(f"plugin {name} required_common_fields must be a set of strings")
        config_model = getattr(instance, "config_model", None)
        if config_model is not None and (
            not isinstance(config_model, type) or not issubclass(config_model, BaseModel)
        ):
            raise TypeError(f"plugin {name} config_model must be a Pydantic model")
        if config_model is not None:
            collisions = set(config_model.model_fields).intersection(COMMON_CONFIG_FIELDS)
            if collisions:
                raise ValueError(
                    f"plugin {name} config fields overlap common fields: {sorted(collisions)}"
                )
        example = getattr(instance, "example", {"plugin": name})
        if not isinstance(example, dict) or example.get("plugin") != name:
            raise TypeError(f"plugin {name} example must be an object naming that plugin")
        api_inputs = getattr(instance, "api_inputs", {})
        if not isinstance(api_inputs, dict):
            raise TypeError(f"plugin {name} api_inputs must be an object")
        statuses = getattr(instance, "statuses", {})
        if not isinstance(statuses, dict):
            raise TypeError(f"plugin {name} statuses must be an object")
        for key, value in statuses.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise TypeError(f"plugin {name} has an invalid status definition")
            if not isinstance(value.get("label"), str):
                raise TypeError(f"plugin {name} status {key} must have a label")
        referenced = set(getattr(instance, "result_statuses", {}).values())
        referenced.update(getattr(instance, "lifecycle_statuses", {}).values())
        interrupted = getattr(instance, "interrupt_status", None)
        if interrupted:
            referenced.add(interrupted)
        missing = referenced - set(statuses)
        if missing:
            raise ValueError(f"plugin {name} references undefined statuses: {sorted(missing)}")

    def expand(
        self, name: str, values: dict[str, Any], context: dict[str, Any]
    ) -> list[TaskCreate]:
        loaded = self.plugins[name]
        drafts = loaded.instance.expand(values, context)
        configured_stop = getattr(loaded.instance, "stop", None)
        stop = StopStrategy.model_validate(configured_stop) if configured_stop else None
        snapshot = {
            "name": name,
            "version": loaded.version,
            "digest": loaded.digest,
            "generation": loaded.generation,
            "values": values,
            "statuses": getattr(loaded.instance, "statuses", {}),
            "lifecycle_statuses": getattr(loaded.instance, "lifecycle_statuses", {}),
            "result_statuses": {
                str(key): value
                for key, value in getattr(loaded.instance, "result_statuses", {}).items()
            },
            "interrupt_status": getattr(loaded.instance, "interrupt_status", "cancelled"),
        }
        return [
            draft.model_copy(update={"plugin_snapshot": snapshot, "template": name, "stop": stop})
            for draft in drafts
        ]

    def expand_config(
        self,
        document: dict[str, Any],
        overrides: dict[str, Any],
        context: dict[str, Any],
    ) -> list[TaskCreate]:
        name = document.get("plugin")
        if not isinstance(name, str) or not name:
            raise ValueError("task configuration must name a plugin")
        self._validate_inputs(name, overrides)
        configured_stop = document.get("stop")
        values = self._config_values(document, overrides, context)
        drafts = self.expand(name, values, context)
        if configured_stop is None:
            return drafts
        stop = StopStrategy.model_validate(configured_stop)
        return [draft.model_copy(update={"stop": stop}) for draft in drafts]

    @staticmethod
    def _allowed_inputs(instance: TemplatePlugin) -> set[str]:
        allowed: set[str] = set()
        for raw in instance.run_fields:
            field = RunFieldSpec.model_validate(raw)
            allowed.add(field.name)
            if field.count_field:
                allowed.add(field.count_field)
            if field.default_count_field:
                allowed.add(field.default_count_field)
        return allowed

    def _validate_inputs(self, name: str, overrides: dict[str, Any]) -> None:
        allowed_inputs = self._allowed_inputs(self.plugins[name].instance)
        unknown_inputs = set(overrides).difference(allowed_inputs)
        if unknown_inputs:
            raise ValueError(
                f"inputs are not declared by plugin {name}: {sorted(unknown_inputs)}"
            )

    def _config_values(
        self,
        document: dict[str, Any],
        overrides: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        root = Path(context["root"])
        variables = document.get("variables", {})
        if not isinstance(variables, dict):
            raise ValueError("variables must be an object")
        plugin_name = document.get("plugin")
        instance = self.plugins[plugin_name].instance
        deferred = set(getattr(instance, "deferred_variables", set()))
        resolver = VariableResolver(
            [
                ("root", {"root": str(root), "scripts_dir": str(root / "scripts"), "cases_dir": str(root / "cases")}),
                ("config", variables),
                ("run", overrides),
            ],
            deferred=deferred,
        )
        values = {key: value for key, value in document.items() if key not in {"plugin", "stop", "variables"}}
        values.update({key: value for key, value in overrides.items() if key not in {"plugin", "stop", "variables"}})
        return resolver.resolution(values).value

    async def discover(
        self,
        name: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
        timeout_seconds: float = 5,
    ) -> list[str]:
        loaded = self.plugins[name]
        method = getattr(loaded.instance, "discover", None)
        if not callable(method):
            return []
        parameters = inspect.signature(method).parameters
        args = (values, context or {}) if len(parameters) >= 2 else (values,)
        result = await asyncio.wait_for(asyncio.to_thread(method, *args), timeout=timeout_seconds)
        if not isinstance(result, list) or any(not isinstance(item, str) for item in result):
            raise TypeError("plugin discover must return a list of strings")
        return result

    async def discover_config(
        self,
        document: dict[str, Any],
        overrides: dict[str, Any],
        context: dict[str, Any],
        timeout_seconds: float = 5,
    ) -> list[str]:
        name = document.get("plugin")
        if not isinstance(name, str) or not name:
            raise ValueError("task configuration must name a plugin")
        self._validate_inputs(name, overrides)
        values = self._config_values(document, overrides, context)
        return await self.discover(name, values, context, timeout_seconds)

    @staticmethod
    def _common_inspection(values: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        root = Path(context["root"])
        directory_value = str(values.get("working_directory", "."))
        directory = Path(directory_value)
        if not directory.is_absolute():
            directory = root / directory
        directory = directory.resolve()
        directory_ok = directory.is_dir()
        items = [{
            "name": "working_directory",
            "label": "工作目录",
            "value": str(directory),
            "kind": "path",
            "severity": "ok" if directory_ok else "error",
            "message": None if directory_ok else "找不到工作目录",
        }]
        command = values.get("command")
        if isinstance(command, str) and command.strip():
            items.append({
                "name": "command",
                "label": "命令",
                "value": command,
                "kind": "command",
                "severity": "ok",
                "message": "由 /bin/sh -lc 执行",
            })
        elif isinstance(command, list) and command:
            executable = str(command[0])
            executable_path = Path(executable)
            found = (
                (directory / executable_path).is_file()
                if executable_path.parent != Path(".")
                else shutil.which(executable) is not None
            )
            items.append({
                "name": "command",
                "label": "命令",
                "value": shlex.join(str(part) for part in command),
                "kind": "command",
                "severity": "ok" if found else "error",
                "message": None if found else f"找不到命令入口：{executable}",
            })
        return items

    async def inspect_config(
        self,
        document: dict[str, Any],
        overrides: dict[str, Any],
        context: dict[str, Any],
        timeout_seconds: float = 5,
    ) -> list[dict[str, Any]]:
        name = document.get("plugin")
        if not isinstance(name, str) or not name:
            raise ValueError("task configuration must name a plugin")
        self._validate_inputs(name, overrides)
        values = self._config_values(document, overrides, context)
        raw = self._common_inspection(values, context)
        method = getattr(self.plugins[name].instance, "inspect", None)
        if callable(method):
            parameters = inspect.signature(method).parameters
            args = (values, context) if len(parameters) >= 2 else (values,)
            extra = await asyncio.wait_for(
                asyncio.to_thread(method, *args), timeout=timeout_seconds
            )
            if not isinstance(extra, list):
                raise TypeError("plugin inspect must return a list")
            raw.extend(extra)
        return [InspectionItem.model_validate(item).model_dump() for item in raw]

    def evaluate_result(
        self, task: TaskRecord, context: dict[str, Any]
    ) -> tuple[TaskStatus, dict[str, Any]] | None:
        snapshot = task.plugin_snapshot
        name = snapshot.get("name") if isinstance(snapshot, dict) else None
        loaded = self.plugins.get(name) if isinstance(name, str) else None
        method = getattr(loaded.instance, "evaluate_result", None) if loaded else None
        if not callable(method):
            return None
        if snapshot.get("digest") != loaded.digest:
            raise RuntimeError(f"plugin {name} changed after task submission")
        result = method(task, context)
        if isinstance(result, str):
            key, custom, label = result, task.custom, None
        elif isinstance(result, dict):
            key = result.get("status")
            custom = result.get("custom", task.custom)
            label = result.get("label")
        else:
            raise TypeError(f"plugin {name} evaluate_result must return a status key or object")
        definition = snapshot.get("statuses", {}).get(key)
        if not isinstance(key, str) or not isinstance(definition, dict):
            raise ValueError(f"plugin {name} returned unknown status: {key!r}")
        if not isinstance(custom, dict):
            raise TypeError(f"plugin {name} result custom data must be an object")
        return (
            TaskStatus(
                key=key,
                label=str(label or definition.get("label", key)),
                tone=str(definition.get("tone", "neutral")),
                finished=True,
            ),
            custom,
        )
