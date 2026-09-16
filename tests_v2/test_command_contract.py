import shlex

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
    multiline = ["/bin/bash", "-ic", "cd /srv/project && printf first\nprintf second"]
    assert command_for_log(multiline, "/srv/project") == "printf first\nprintf second"


def test_task_source_files_are_frozen_before_the_exact_user_command(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    environment = project / "environment setup.sh"
    environment.write_text("export PROJECT_MODE=fast\n", encoding="utf-8")
    task = TaskCreate(
        name="sourced",
        working_directory=str(project),
        shell="/bin/bash",
        source=["environment setup.sh"],
        command="printf '%s' \"$PROJECT_MODE\"",
    )
    frozen = freeze_command_working_directory(
        task.command, str(project), task.source
    )
    assert frozen[:2] == ["/bin/bash", "-ic"]
    assert f"source {shlex.quote(str(environment))}\n" in frozen[2]
    assert "localflow_source_status=$?\n" in frozen[2]
    assert f"cd {shlex.quote(str(project))}\n" in frozen[2]
    assert frozen[2].endswith("printf '%s' \"$PROJECT_MODE\"")
    assert command_for_log(frozen, str(project)) == "printf '%s' \"$PROJECT_MODE\""
    assert "source" not in task.model_dump()


def test_tcsh_sources_on_separate_parse_lines_before_user_command(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    environment = project / "environment.csh"
    environment.write_text("setenv PROJECT_MODE fast\n", encoding="utf-8")
    task = TaskCreate(
        name="tcsh-source",
        working_directory=str(project),
        shell="/bin/tcsh",
        source=["environment.csh"],
        command="printf '%s' \"$PROJECT_MODE\"",
    )
    frozen = freeze_command_working_directory(task.command, str(project), task.source)
    body = frozen[2]
    assert f"source {shlex.quote(str(environment))}\n" in body
    assert "if ( $status != 0 ) exit $status\n" in body
    assert "# localflow:user-command\nprintf" in body
    assert command_for_log(frozen, str(project)) == "printf '%s' \"$PROJECT_MODE\""


def test_source_files_preserve_order_and_quote_paths(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    first = project / "first setup.csh"
    second = project / "second setup.csh"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    task = TaskCreate(
        name="source-list",
        working_directory=str(project),
        shell="/bin/tcsh",
        source=[first.name, second.name],
        command="printf ready",
    )
    frozen = freeze_command_working_directory(task.command, str(project), task.source)

    first_command = f"source {shlex.quote(str(first.resolve()))}"
    second_command = f"source {shlex.quote(str(second.resolve()))}"
    assert first_command in frozen[2]
    assert second_command in frozen[2]
    assert frozen[2].index(first_command) < frozen[2].index(second_command)


def test_source_paths_use_safe_wrapper_for_posix_sh(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    task = TaskCreate(
        name="source-sh",
        working_directory=str(project),
        shell="/bin/sh",
        source=["./environment.sh"],
        command="printf done",
    )

    frozen = freeze_command_working_directory(task.command, str(project), task.source)

    expected = shlex.quote(str((project / "environment.sh").resolve()))
    assert f"localflow_source {expected}" in frozen[2]
    assert '. "$@"' in frozen[2]


def test_source_requires_a_shell_command_and_valid_paths() -> None:
    with pytest.raises(ValidationError, match="source is only valid with a string command"):
        CommonConfigFields(source=["environment.csh"], command=["make", "all"])
    with pytest.raises(ValidationError, match="source is only valid with a string command"):
        TaskCreate(
            name="exact",
            working_directory=".",
            source=["environment.csh"],
            command=["make", "all"],
        )
    with pytest.raises(ValidationError, match="source must contain"):
        TaskCreate(name="empty", working_directory=".", source=[], command="true")


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
