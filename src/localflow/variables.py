from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

REFERENCE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_.-]*)\}")


class VariableError(ValueError):
    pass


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
            if isinstance(resolved, (dict, list)):
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
