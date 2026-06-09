from __future__ import annotations

import time
from pathlib import Path
from typing import ClassVar

from automation import (
    Script,
    badge,
    code,
    col,
    detail,
    div,
    labeled,
    row,
    spacer,
    summary,
    text,
    var_ref,
)
from automation.script.subprocess_cmd import run_shell_command

from .command import format_command
from .log_result import evaluate_log_result, read_log_tail, resolve_log_path


class SimRunScript(Script):
    """在工作目录执行仿真命令，并按日志正则判定 PASS / FAIL / ERROR。"""

    RUNTIME_VARIABLE_KEYS: ClassVar[frozenset[str]] = Script.RUNTIME_VARIABLE_KEYS | frozenset(
        {
            "result_status",
            "formatted_command",
        },
    )

    def build_view_template(self):
        return div(
            summary(
                row(
                    badge(var_ref("project"), tone="primary"),
                    text(" / "),
                    badge(var_ref("module"), tone="muted"),
                    spacer(size="sm"),
                    text("seed ", muted=True),
                    text(var_ref("seed"), bold=True),
                    spacer(size="sm"),
                    badge(var_ref("phase"), tone="warning"),
                ),
                row(
                    text(var_ref("case"), muted=True),
                    spacer(size="sm"),
                    text(var_ref("result_status"), bold=True),
                ),
            ),
            detail(
                col(
                    labeled("项目", var_ref("project")),
                    labeled("模块", var_ref("module")),
                    labeled("Case", var_ref("case")),
                    labeled("种子", var_ref("seed")),
                    labeled("工作目录", var_ref("work_dir")),
                    labeled("仿真日志", var_ref("log_path")),
                    labeled("命令", var_ref("formatted_command")),
                    labeled("终端日志", var_ref("terminal_log_path")),
                    gap="md",
                ),
            ),
        )

    def run(self) -> None:
        self.variables.set("phase", "准备")
        self.variables.set("result_status", "—")
        self.variables.set("formatted_command", "")

        work_dir = Path(str(self.variables.get("work_dir", "."))).expanduser().resolve()
        if not work_dir.is_dir():
            raise ValueError(f"工作目录不存在: {work_dir}")

        command_template = str(self.variables.get("command", "")).strip()
        if not command_template:
            raise ValueError("command 不能为空")

        formatted = format_command(command_template, self.variables.snapshot())
        self.variables.set("formatted_command", formatted)

        self.variables.set("phase", "执行中")
        print(f"工作目录: {work_dir}")
        print(f"$ {formatted}")

        started = time.perf_counter()
        completed = run_shell_command(self, formatted, cwd=work_dir)
        elapsed = time.perf_counter() - started
        self.variables.set("exit_code", str(completed.returncode))
        self.variables.set("duration", f"{elapsed:.2f}s")

        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
        if completed.stderr:
            print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n")

        log_path = resolve_log_path(str(self.variables.get("log_path", "")), work_dir)
        self.variables.set("phase", "判定结果")
        status, message = evaluate_log_result(
            log_path,
            pass_regex=str(self.variables.get("pass_regex", "")),
            fail_regex=str(self.variables.get("fail_regex", "")),
        )
        self.variables.set("result_status", status)
        self.variables.set("log_tail", read_log_tail(log_path))

        print(f"仿真日志: {log_path}")
        print(f"结果: {status}")
        if message:
            print(message)

        self.variables.set("phase", "完成")
        if status == "PASS":
            return
        raise RuntimeError(message or f"仿真结果: {status}")

    def build_result_template(self):
        return div(
            summary(
                row(
                    badge(var_ref("project"), tone="primary"),
                    text(" — "),
                    text(var_ref("case")),
                    spacer(size="sm"),
                    badge(var_ref("result_status"), tone="success"),
                ),
            ),
            detail(
                col(
                    labeled("结果", var_ref("result_status")),
                    labeled("退出码", var_ref("exit_code")),
                    labeled("耗时", var_ref("duration")),
                    labeled("工作目录", var_ref("work_dir")),
                    labeled("仿真日志", var_ref("log_path")),
                    labeled("命令", var_ref("formatted_command")),
                    labeled("错误", var_ref("error_message")),
                    code(var_ref("log_tail")),
                    labeled("终端输出文件", var_ref("terminal_log_path")),
                    gap="md",
                ),
            ),
        )
