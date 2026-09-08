from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from configlib.resolver import resolve_variables as resolve_configlib_variables
from configlib.yaml_compose import apply_composition

REFERENCE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_.-]*)\}")


class VariableError(ValueError):
    pass


def resolve_config_tree(
    document: dict[str, Any],
    deferred: set[str] | None = None,
    external: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a merged configlib tree while preserving host-allocated values."""
    source = deepcopy(document)
    aliases = source.get("variables", {})
    if aliases is not None and not isinstance(aliases, dict):
        raise VariableError("variables must be an object")
    # The legacy ``variables`` table intentionally aliases its keys at the
    # document root, including when a target field has the same name.
    augmented = {**(external or {}), **source, **(aliases or {})}
    tokens = {
        name: f"__LOCALFLOW_DEFERRED_{name.upper()}_7F4C2E__"
        for name in (deferred or set())
    }
    augmented.update(tokens)
    try:
        resolved = apply_composition(resolve_configlib_variables(augmented))
    except KeyError as error:
        message = str(error).strip("'\"")
        name = message.rsplit(": ", 1)[-1]
        raise VariableError(f"unknown variable: {name}") from error
    except ValueError as error:
        raise VariableError(str(error)) from error

    def restore(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: restore(item) for key, item in value.items()}
        if isinstance(value, list):
            return [restore(item) for item in value]
        if not isinstance(value, str):
            return value
        for name, token in tokens.items():
            value = value.replace(token, "${" + name + "}")
        return value

    restored = restore(resolved)
    for name in tokens:
        if name not in source:
            restored.pop(name, None)
    for name in set(external or {}) | set(aliases or {}):
        if name not in source:
            restored.pop(name, None)
    return restored


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        result[path] = item
        if isinstance(item, dict):
            result.update(_flatten(item, path))
    return result


@dataclass(frozen=True)
class Resolution:
    value: Any
    sources: dict[str, str]


class VariableResolver:
    def __init__(
        self,
        layers: list[tuple[str, dict[str, Any]]],
        deferred: set[str] | None = None,
    ) -> None:
        self.values: dict[str, Any] = {}
        self.sources: dict[str, str] = {}
        for layer_name, layer in layers:
            for key, value in _flatten(layer).items():
                self.values[key] = value
                self.sources[key] = layer_name
        self._cache: dict[str, Any] = {}
        self.deferred = deferred or set()

    def variable(self, name: str, stack: tuple[str, ...] = ()) -> Any:
        if name in self._cache:
            return self._cache[name]
        if name in self.deferred:
            return "${" + name + "}"
        if name in stack:
            raise VariableError(f"variable cycle: {' -> '.join((*stack, name))}")
        if name not in self.values:
            raise VariableError(f"unknown variable: {name}")
        resolved = self.resolve(self.values[name], (*stack, name))
        self._cache[name] = resolved
        return resolved

    def resolve(self, value: Any, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(value, dict):
            return {key: self.resolve(item, stack) for key, item in value.items()}
        if isinstance(value, list):
            return [self.resolve(item, stack) for item in value]
        if not isinstance(value, str):
            return value
        match = REFERENCE.fullmatch(value)
        if match:
            return self.variable(match.group(1), stack)

        def replace(reference: re.Match[str]) -> str:
            resolved = self.variable(reference.group(1), stack)
            if isinstance(resolved, dict | list):
                raise VariableError(
                    f"structured variable cannot be embedded in text: {reference.group(1)}"
                )
            return str(resolved)

        return REFERENCE.sub(replace, value)

    def resolution(self, value: Any) -> Resolution:
        resolved = self.resolve(value)
        used = {match.group(1) for match in REFERENCE.finditer(str(value))}
        return Resolution(
            resolved, {name: self.sources[name] for name in used if name in self.sources}
        )
