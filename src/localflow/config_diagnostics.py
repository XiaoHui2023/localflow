from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .models import COMMON_CONFIG_FIELDS, CommonConfigFields
from .plugins import PluginRegistry


class ConfigDiagnosis(BaseModel):
    kind: Literal["generic", "fragment", "task"]
    valid: bool
    runnable: bool
    plugin: str | None = None
    common_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _validation_errors(error: ValidationError, prefix: str = "") -> list[str]:
    messages: list[str] = []
    for item in error.errors(include_url=False, include_context=False):
        location = ".".join(str(part) for part in item["loc"])
        label = f"{prefix}{location}" if location else prefix.rstrip(".")
        messages.append(f"{label}: {item['msg']}" if label else item["msg"])
    return messages


def diagnose_config(document: Any, plugins: PluginRegistry) -> ConfigDiagnosis:
    if not isinstance(document, dict):
        return ConfigDiagnosis(
            kind="generic",
            valid=False,
            runnable=False,
            errors=["configuration root must be an object"],
        )

    present = sorted(COMMON_CONFIG_FIELDS.intersection(document))
    if not present:
        return ConfigDiagnosis(kind="generic", valid=True, runnable=False)

    errors: list[str] = []
    warnings: list[str] = []
    try:
        CommonConfigFields.model_validate(document)
    except ValidationError as error:
        errors.extend(_validation_errors(error))

    plugin_name = document.get("plugin")
    if "plugin" not in document:
        return ConfigDiagnosis(
            kind="fragment",
            valid=not errors,
            runnable=False,
            common_fields=present,
            errors=errors,
        )

    if not isinstance(plugin_name, str) or not plugin_name:
        return ConfigDiagnosis(
            kind="task",
            valid=False,
            runnable=False,
            common_fields=present,
            errors=errors or ["plugin: must be a non-empty string"],
        )

    loaded = plugins.plugins.get(plugin_name)
    if loaded is None:
        errors.append(f"plugin: plugin is not loaded: {plugin_name}")
    else:
        required = set(getattr(loaded.instance, "required_common_fields", set()))
        for field in sorted(required - set(document)):
            errors.append(f"{field}: field required by plugin {plugin_name}")
        config_model = getattr(loaded.instance, "config_model", None)
        if config_model is None:
            warnings.append(f"plugin {plugin_name} does not declare a plugin-field schema")
        else:
            plugin_values = {
                key: value for key, value in document.items() if key not in COMMON_CONFIG_FIELDS
            }
            try:
                config_model.model_validate(plugin_values)
            except ValidationError as error:
                errors.extend(_validation_errors(error, "plugin."))

    return ConfigDiagnosis(
        kind="task",
        valid=not errors,
        runnable=loaded is not None and not errors,
        plugin=plugin_name,
        common_fields=present,
        errors=errors,
        warnings=warnings,
    )
