import pytest

from localflow.variables import VariableError, VariableResolver


def test_layers_types_and_nested_resolution() -> None:
    resolver = VariableResolver(
        [
            ("global", {"root": "/srv", "count": 1}),
            ("project", {"root": "/work", "project": {"name": "chip-a"}}),
            ("template", {"runs": "${count}"}),
            ("run", {"count": 3, "case": "smoke"}),
        ]
    )
    resolved = resolver.resolve(
        {
            "directory": "${root}/${project.name}",
            "command": ["run", "${case}"],
            "runs": "${runs}",
        }
    )
    assert resolved == {
        "directory": "/work/chip-a",
        "command": ["run", "smoke"],
        "runs": 3,
    }


def test_unknown_cycle_and_structured_embedding_are_rejected() -> None:
    with pytest.raises(VariableError, match="unknown variable"):
        VariableResolver([]).resolve("${missing}")
    with pytest.raises(VariableError, match="variable cycle"):
        VariableResolver([("global", {"a": "${b}", "b": "${a}"})]).resolve("${a}")
    with pytest.raises(VariableError, match="structured variable"):
        VariableResolver([("global", {"items": [1, 2]})]).resolve("x-${items}")
