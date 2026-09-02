import pytest
from pydantic import ValidationError

from localflow.models import CommonConfigFields, TaskCreate


def test_command_string_uses_ubuntu_shell_and_list_remains_exact_argv() -> None:
    common = CommonConfigFields(command="printf 'hello world\\n' > result.txt")
    assert isinstance(common.command, str)
    shell = TaskCreate(name="shell", working_directory=".", command=common.command)
    exact = TaskCreate(name="exact", working_directory=".", command=["printf", "%s", "ok"])
    assert shell.command == ["/bin/sh", "-c", "printf 'hello world\\n' > result.txt"]
    assert exact.command == ["printf", "%s", "ok"]


@pytest.mark.parametrize("command", ["", "   ", "bad\0command", [], ["ok", ""]])
def test_command_rejects_empty_or_nul_values(command) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(name="bad", working_directory=".", command=command)
