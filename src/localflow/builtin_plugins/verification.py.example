from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from localflow.models import TaskCreate
from localflow.plugins import plugin, run_field
from localflow.variables import VariableResolver

UVM_SUMMARY = re.compile(r"UVM_(INFO|WARNING|ERROR|FATAL)\s*:\s*(\d+)", re.IGNORECASE)
VCS_FATAL = re.compile(r"(?im)^\s*(?:Fatal(?:-|\s*:\s*)|Error-\[NOA\]|\*F,)")
VCS_ERROR = re.compile(r"(?im)^\s*(?:Error(?:-|\s*:\s*)|\*E,)")


def evaluate_vcs_text(text: str) -> tuple[str, int]:
    """Classify the final UVM summary, then fall back to anchored VCS diagnostics."""
    summary = text.rsplit("UVM Report Summary", 1)[-1]
    counts = {name.upper(): int(value) for name, value in UVM_SUMMARY.findall(summary)}
    if counts:
        if counts.get("FATAL", 0):
            return "fatal", counts["FATAL"]
        if counts.get("ERROR", 0):
            return "error", counts["ERROR"]
        return "passed", 0
    fatal = len(VCS_FATAL.findall(text))
    if fatal:
        return "fatal", fatal
    error = len(VCS_ERROR.findall(text))
    if error:
        return "error", error
    return "passed", 0


class VerificationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_directory: str | None = None
    case_root: str | None = None
    cases: list[str] = Field(default_factory=list)
    runs: int = Field(default=1, ge=1)
    runs_per_case: int | None = Field(default=None, ge=1)
    case_runs: dict[str, int] = Field(default_factory=dict)
    seed: int | str | None = None
    compile_logs: list[str] = Field(default_factory=list)
    run_logs: list[str] = Field(default_factory=list)

    @field_validator("seed")
    @classmethod
    def validate_seed(cls, value):
        if value in {None, ""}:
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("seed must be an integer or empty") from error

    @model_validator(mode="after")
    def require_case_directory(self):
        if not self.case_directory and not self.case_root:
            raise ValueError("case_directory is required")
        if any(value < 1 for value in self.case_runs.values()):
            raise ValueError("case_runs values must be at least 1")
        return self


@plugin("verification", version="2")
class Verification:
    config_model = VerificationConfig
    required_common_fields = {"command"}
    deferred_variables = {"case", "seed", "run"}
    title = "验证仿真"
    description = "选择 Case、次数和随机种子"
    instructions = "配置 Case 目录和仿真命令。使用时选择一个或多个 Case；每个 Case 的每次运行都会成为独立任务。"
    example = {
        "plugin": "verification",
        "case_directory": "${root}/cases",
        "cases": [],
        "runs": 1,
        "command": ["python3", "-u", "${scripts_dir}/simulate.py"],
        "mutex_keys": ["simulator:demo"],
    }
    api_inputs = {
        "cases": ["case-a"],
        "case_runs": {"case-a": 1},
        "seed": None,
    }
    statuses = {
        "waiting": {"label": "等待仿真", "tone": "neutral", "finished": False},
        "starting": {"label": "准备仿真", "tone": "info", "finished": False},
        "simulating": {"label": "仿真中", "tone": "info", "finished": False},
        "stopping": {"label": "退出中", "tone": "warning", "finished": False},
        "passed": {"label": "验证通过", "tone": "success", "finished": True},
        "compile_error": {"label": "编译错误", "tone": "danger", "finished": True},
        "error": {"label": "ERROR", "tone": "danger", "finished": True},
        "fatal": {"label": "FATAL", "tone": "danger", "finished": True},
        "mismatch": {"label": "比对不一致", "tone": "warning", "finished": True},
        "crashed": {"label": "仿真异常", "tone": "danger", "finished": True},
        "stopped": {"label": "已停止", "tone": "warning", "finished": True},
        "lost": {"label": "状态丢失", "tone": "danger", "finished": True},
    }
    lifecycle_statuses = {
        "queued": "waiting",
        "starting": "starting",
        "running": "simulating",
        "stopping": "stopping",
        "lost": "lost",
    }
    result_statuses = {0: "passed", 2: "mismatch", "default": "crashed"}
    interrupt_status = "stopped"
    run_fields = [
        run_field(
            "cases",
            "case-picker",
            multiple=True,
            required=True,
            label="Case",
            count_field="case_runs",
            default_count_field="runs",
        ),
        run_field("seed", "seed", label="随机种子"),
    ]

    @staticmethod
    def _case_names(root):
        return sorted(
            {
                path.name if path.is_dir() else path.stem
                for path in root.iterdir()
                if not path.name.startswith(".") and (path.is_dir() or path.is_file())
            }
        )

    def discover(self, values, _context):
        root = Path(values.get("case_directory", values.get("case_root", "")))
        return self._case_names(root)

    def evaluate_result(self, task, _context):
        compile_logs = [Path(value) for value in task.custom.get("_compile_logs", [])]
        run_logs = [Path(value) for value in task.custom.get("_run_logs", [])]
        runtime = {"seed": task.custom["seed"]} if "seed" in task.custom else {}
        if not compile_logs and not run_logs:
            return "passed" if task.exit_code in {None, 0} else "crashed"
        existing_run = [path for path in run_logs if path.is_file()]
        if not existing_run:
            existing_compile = [path for path in compile_logs if path.is_file()]
            return {
                "status": "compile_error",
                "custom": {**runtime, "编译日志": [str(path) for path in existing_compile]},
            }
        text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in existing_run)
        status, _count = evaluate_vcs_text(text)
        return {
            "status": status,
            "custom": {**runtime, "运行日志": [str(path) for path in existing_run]},
        }

    def expand(self, values, context):
        root_resolver = VariableResolver(
            [("root", {"root": context["root"], "scripts_dir": str(Path(context["root"]) / "scripts")})]
        )
        case_root = Path(
            root_resolver.resolve(values.get("case_directory", values.get("case_root", "")))
        ).resolve()
        available = set(self._case_names(case_root))
        if not values.get("cases"):
            raise ValueError("at least one case is required")
        tasks = []
        for case_name in values["cases"]:
            if case_name not in available:
                raise ValueError(f"case not found: {case_name}")
            case_runs = values.get("case_runs", {})
            default_runs = values.get("runs", values.get("runs_per_case", 1))
            for index in range(int(case_runs.get(case_name, default_runs))):
                configured = values.get("seed")
                automatic_seed = configured in {None, ""}
                seed = "${seed}" if automatic_seed else int(configured) + index
                dynamic = VariableResolver(
                    [
                        (
                            "root",
                            {
                                "root": context["root"],
                                "scripts_dir": str(Path(context["root"]) / "scripts"),
                                "case": case_name,
                                "seed": seed,
                                "run": index + 1,
                            },
                        )
                    ],
                    deferred={"seed"} if automatic_seed else None,
                )
                labels = [
                    str(item)
                    for item in dynamic.resolve(values.get("labels", ["verification", case_name]))
                ]
                mutex_keys = [str(item) for item in dynamic.resolve(values.get("mutex_keys", []))]
                mutex_keys.extend(f"tag:{label}" for label in labels)
                command = [str(item) for item in dynamic.resolve(values["command"])]
                if not any("${case}" in str(item) or item == case_name for item in values["command"]):
                    command.extend(["--case", case_name])
                if not any("${seed}" in str(item) or item == str(seed) for item in values["command"]):
                    command.extend(["--seed", str(seed)])
                tasks.append(
                    TaskCreate(
                        name=case_name,
                        working_directory=str(case_root),
                        command=command,
                        labels=labels,
                        mutex_keys=list(dict.fromkeys(mutex_keys)),
                        custom={
                            "_case": case_name,
                            "_run": index + 1,
                            **({"_runtime_seed": "unix"} if automatic_seed else {"seed": seed}),
                            "_compile_logs": dynamic.resolve(values.get("compile_logs", [])),
                            "_run_logs": dynamic.resolve(values.get("run_logs", [])),
                        },
                    )
                )
        return tasks
