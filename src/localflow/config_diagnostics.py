from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .models import COMMON_CONFIG_FIELDS, CommonConfigFields
from .plugins import PluginRegistry


class ConfigIssue(BaseModel):
    message: str
    severity: Literal["error", "warning"] = "error"
    line: int = Field(default=1, ge=1)
    column: int = Field(default=1, ge=1)
    end_line: int = Field(default=1, ge=1)
    end_column: int = Field(default=2, ge=1)


class ConfigDiagnosis(BaseModel):
    kind: Literal["generic", "fragment", "task"]
    valid: bool
    runnable: bool
    plugin: str | None = None
    common_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    issues: list[ConfigIssue] = Field(default_factory=list)


def syntax_error_diagnosis(error: Exception) -> ConfigDiagnosis:
    detail = getattr(error, "problem", None) or str(error)
    message = f"syntax or import error: {detail}"
    mark = getattr(error, "problem_mark", None)
    if mark is not None:
        line = int(mark.line) + 1
        column = int(mark.column) + 1
    elif getattr(error, "lineno", None) is not None:
        line = int(error.lineno)
        column = int(getattr(error, "colno", 1))
    else:
        match = re.search(r"line\s+(\d+).*?column\s+(\d+)", str(error), re.I | re.S)
        line = int(match.group(1)) if match else 1
        column = int(match.group(2)) if match else 1
    return ConfigDiagnosis(
        kind="generic",
        valid=False,
        runnable=False,
        errors=[message],
        issues=[
            ConfigIssue(
                message=message,
                line=line,
                column=column,
                end_line=line,
                end_column=column + 1,
            )
        ],
    )


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
        return ConfigDiagnosis(
            kind="generic",
            valid=False,
            runnable=False,
            errors=["plugin: field required for runnable configuration"],
        )

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
            valid=False,
            runnable=False,
            common_fields=present,
            errors=[*errors, "plugin: field required for runnable configuration"],
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
        validation_document = document
        try:
            validation_document = plugins.resolve_config_document(document)
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"variables: {error}")
        if validation_document is not document:
            try:
                CommonConfigFields.model_validate(validation_document)
            except ValidationError as error:
                for message in _validation_errors(error):
                    if message not in errors:
                        errors.append(message)
        required = set(getattr(loaded.instance, "required_common_fields", set()))
        for field in sorted(required):
            if field not in validation_document or validation_document[field] is None:
                errors.append(f"{field}: field required by plugin {plugin_name}")
        config_model = getattr(loaded.instance, "config_model", None)
        if config_model is None:
            warnings.append(f"plugin {plugin_name} does not declare a plugin-field schema")
        else:
            declared_plugin_fields = set(config_model.model_fields)
            plugin_values = {
                key: value
                for key, value in validation_document.items()
                if key in declared_plugin_fields
            }
            try:
                config_model.model_validate(plugin_values)
            except ValidationError as error:
                errors.extend(_validation_errors(error, "plugin."))
        validate_config = getattr(loaded.instance, "validate_config", None)
        if callable(validate_config):
            try:
                plugin_errors = validate_config(document)
                if not isinstance(plugin_errors, list) or any(
                    not isinstance(item, str) for item in plugin_errors
                ):
                    raise TypeError("validate_config must return a list of strings")
                errors.extend(plugin_errors)
            except (TypeError, ValueError) as error:
                errors.append(f"plugin: configuration validation failed: {error}")
    return ConfigDiagnosis(
        kind="task",
        valid=not errors,
        runnable=loaded is not None and not errors,
        plugin=plugin_name,
        common_fields=present,
        errors=errors,
        warnings=warnings,
    )
