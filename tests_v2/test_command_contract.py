import pytest
from pydantic import ValidationError

from localflow.models import (
    CommonConfigFields,
    TaskCreate,
    command_for_log,
    freeze_command_working_directory,
)


def test_command_string_uses_detected_login_shell_and_list_remains_exact_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHELL", "/bin/bash")
    common = CommonConfigFields(command="printf 'hello world\\n' > result.txt")
    assert isinstance(common.command, str)
    shell = TaskCreate(name="shell", working_directory=".", command=common.command)
    exact = TaskCreate(name="exact", working_directory=".", command=["printf", "%s", "ok"])
    assert freeze_command_working_directory(shell.command, "/srv/project") == [
        "/bin/bash",
        "-ic",
        "cd /srv/project && printf 'hello world\\n' > result.txt",
    ]
    assert exact.command == ["printf", "%s", "ok"]


def test_detected_csh_is_used_without_plugin_specific_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHELL", "/bin/tcsh")
    task = TaskCreate(name="csh-alias", working_directory="/srv/project", command="build-fast")
    assert freeze_command_working_directory(task.command, "/srv/project") == [
        "/bin/tcsh",
        "-ic",
        "cd /srv/project && build-fast",
    ]


def test_command_log_hides_shell_cwd_wrapper_but_preserves_exact_argv() -> None:
    wrapped = ["/bin/tcsh", "-ic", "cd '/srv/project name' && make all CASE=smoke"]
    assert command_for_log(wrapped, "/srv/project name") == "make all CASE=smoke"
    assert command_for_log(["printf", "%s", "ok"], "/srv/project") == "printf %s ok"


def test_explicit_interactive_shell_loads_profile_without_weakening_exact_argv() -> None:
    shell = TaskCreate(
        name="shell-profile",
        working_directory="/srv/project",
        shell="/bin/bash",
        command="project-build",
    )
    assert freeze_command_working_directory(shell.command, "/srv/project") == [
        "/bin/bash",
        "-ic",
        "cd /srv/project && project-build",
    ]
    assert shell.model_dump().get("shell") is None
    with pytest.raises(ValidationError, match="only valid with a string command"):
        TaskCreate(
            name="exact",
            working_directory=".",
            shell="/bin/csh",
            command=["make", "all"],
        )


@pytest.mark.parametrize("command", ["", "   ", "bad\0command", [], ["ok", ""]])
def test_command_rejects_empty_or_nul_values(command) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(name="bad", working_directory=".", command=command)


@pytest.mark.parametrize("shell", ["", "   ", "bad\0shell"])
def test_shell_rejects_empty_or_nul_values(shell: str) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(name="bad", working_directory=".", shell=shell, command="true")
