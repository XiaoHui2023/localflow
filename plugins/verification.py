from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from localflow.models import DeferredValue, TaskDraft
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
    # Verification configurations often carry simulator-specific values that
    # are consumed by command interpolation or a site-local plugin extension.
    model_config = ConfigDict(extra="allow")

    case_directory: str | None = None
    case_root: str | None = None
    case_names: list[str] = Field(default_factory=list)
    compile_logs: list[str] = Field(default_factory=list)
    run_logs: list[str] = Field(default_factory=list)
    custom_texts: list[str] = Field(default_factory=list)

    @field_validator("case_names")
    @classmethod
    def normalize_case_names(cls, values):
        names = [value.strip() for value in values]
        if any(not value for value in names):
            raise ValueError("case_names cannot contain empty names")
        return list(dict.fromkeys(names))

    @model_validator(mode="after")
    def require_case_source(self):
        if not self.case_directory and not self.case_root and not self.case_names:
            raise ValueError("case_directory or case_names is required")
        if self.case_names and (self.case_directory or self.case_root):
            raise ValueError("case_names and case_directory are alternative sources")
        return self


class VerificationInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[str] = Field(default_factory=list)
    runs: int = Field(default=1, ge=1)
    case_runs: dict[str, int] = Field(default_factory=dict)
    seed: int | str | None = None

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
    def validate_case_runs(self):
        unknown = set(self.case_runs).difference(self.cases)
        if unknown:
            raise ValueError(f"case_runs names must also appear in cases: {sorted(unknown)}")
        return self


@plugin("verification", version="5")
class Verification:
    config_model = VerificationConfig
    input_model = VerificationInputs
    required_common_fields = {"working_directory", "command"}
    deferred_variables = {"case", "seed"}
    title = "验证仿真"
    description = "选择 Case、次数和随机种子"
    instructions = "配置 Case 目录和仿真命令。使用时选择一个或多个 Case；每个 Case 的每次运行都会成为独立任务。"
    example = {
        "plugin": "verification",
        "case_names": ["case-a", "case-b", "smoke"],
        "working_directory": ".",
        "command": "make all CASE=${case} SEED=${seed}",
        "mutex_keys": ["simulator:demo"],
        "custom_texts": ["Case: ${case}", "Seed: ${seed}"],
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
        "finished": {"label": "运行结束", "tone": "neutral", "finished": True},
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

    def _available_cases(self, values, context):
        configured = values.get("case_names", [])
        if configured:
            if values.get("case_directory") or values.get("case_root"):
                raise ValueError("case_names and case_directory are alternative sources")
            return sorted(dict.fromkeys(str(item).strip() for item in configured))
        root = self._path(values.get("case_directory", values.get("case_root", "")), context)
        return self._case_names(root) if root.is_dir() else []

    @staticmethod
    def _path(value, context):
        path = Path(value)
        return path if path.is_absolute() else Path(context["root"]) / path

    def discover(self, values, context):
        return self._available_cases(values, context)

    def inspect(self, values, context):
        configured_cases = self._available_cases(values, context)
        if values.get("case_names"):
            items = [
                {
                    "name": "case_names",
                    "label": "Case",
                    "value": configured_cases,
                    "kind": "tokens",
                    "severity": "info",
                    "message": f"插件提供 {len(configured_cases)} 个 Case",
                }
            ]
        else:
            items = []
        case_root = self._path(
            values.get("case_directory", values.get("case_root", "")), context
        ).resolve()
        if not values.get("case_names"):
            if case_root.is_dir():
                count = len(configured_cases)
                severity = "ok"
                message = f"已发现 {count} 个 Case" if count else "目录存在，但没有可用 Case"
                if count == 0:
                    severity = "warning"
            else:
                severity = "error"
                message = "找不到 Case 目录"
            items.append(
                {
                    "name": "case_directory",
                    "label": "Case 目录",
                    "value": str(case_root),
                    "kind": "path",
                    "check": "availability",
                    "severity": severity,
                    "message": message,
                }
            )
        selected_case = "${case}"
        preview_values = {
            "case": selected_case,
            "seed": "${seed}",
        }

        def preview(value):
            result = str(value)
            for key, replacement in preview_values.items():
                result = result.replace("${" + key + "}", str(replacement))
            return result

        working = self._path(values["working_directory"], context).resolve()
        for name, label in (("compile_logs", "编译日志"), ("run_logs", "运行日志")):
            configured = values.get(name, [])
            if not configured:
                continue
            resolved = []
            for raw in configured:
                path = Path(preview(raw))
                resolved.append(str(path if path.is_absolute() else (working / path).resolve()))
            items.append(
                {
                    "name": name,
                    "label": label,
                    "value": resolved,
                    "kind": "code-list",
                    "severity": "info",
                    "message": "仅展示解析结果；运行前不检查文件是否存在",
                }
            )
        labels = [preview(value) for value in values.get("labels", [])]
        items.append(
            {
                "name": "labels",
                "label": "标签",
                "value": labels,
                "kind": "tokens",
                "severity": "info",
                "message": None,
            }
        )
        for index, value in enumerate(values.get("custom_texts", [])):
            items.append(
                {
                    "name": f"custom_text_{index}",
                    "label": "自定义文本",
                    "value": str(value),
                    "kind": "text",
                    "severity": "info",
                    "message": None,
                }
            )
        return items

    def evaluate_result(self, task, _context):
        compile_logs = [Path(value) for value in task.custom.get("_compile_logs", [])]
        run_logs = [Path(value) for value in task.custom.get("_run_logs", [])]
        runtime = {"seed": task.custom["seed"]} if "seed" in task.custom else {}
        if task.custom.get("自定义文本"):
            runtime["自定义文本"] = task.custom["自定义文本"]
        if not run_logs:
            existing_compile = [path for path in compile_logs if path.is_file()]
            details = {
                **runtime,
                **(
                    {"编译日志": [str(path) for path in existing_compile]}
                    if existing_compile
                    else {}
                ),
            }
            return {"status": "finished", "custom": details}
        existing_run = [path for path in run_logs if path.is_file()]
        if not existing_run:
            if not compile_logs:
                return {"status": "finished", "custom": runtime}
            existing_compile = [path for path in compile_logs if path.is_file()]
            return {
                "status": "compile_error",
                "custom": {**runtime, "编译日志": [str(path) for path in existing_compile]},
            }
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace") for path in existing_run
        )
        status, _count = evaluate_vcs_text(text)
        return {
            "status": status,
            "custom": {**runtime, "运行日志": [str(path) for path in existing_run]},
        }

    def expand(self, values, context):
        command_template = values["command"]
        if not values.get("working_directory"):
            raise ValueError("working_directory is required")
        working_directory = self._path(values["working_directory"], context).resolve()
        available = set(self._available_cases(values, context))
        if not values.get("cases"):
            raise ValueError("at least one case is required")
        tasks = []
        for case_name in values["cases"]:
            if case_name not in available:
                raise ValueError(f"case not found: {case_name}")
            case_runs = values.get("case_runs", {})
            default_runs = values.get("runs", 1)
            for index in range(int(case_runs.get(case_name, default_runs))):
                configured = values.get("seed")
                automatic_seed = configured in {None, ""}
                seed = "${seed}" if automatic_seed else int(configured) + index
                dynamic = VariableResolver(
                    [
                        (
                            "root",
                            {
                                "case": case_name,
                                "seed": seed,
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
                queue_identity = json.dumps(
                    [case_name, sorted(labels)], ensure_ascii=False, separators=(",", ":")
                )
                mutex_keys.append(
                    "verification:" + hashlib.sha256(queue_identity.encode()).hexdigest()[:24]
                )
                if isinstance(command_template, str):
                    command_source = command_template.replace("${case}", shlex.quote(case_name))
                    command = dynamic.resolve(command_source)
                else:
                    command = [str(item) for item in dynamic.resolve(command_template)]
                tasks.append(
                    TaskDraft(
                        name=case_name,
                        working_directory=str(working_directory),
                        shell=values.get("shell"),
                        command=command,
                        labels=labels,
                        mutex_keys=list(dict.fromkeys(mutex_keys)),
                        custom={
                            "_case": case_name,
                            "_run": index + 1,
                            **({} if automatic_seed else {"seed": seed}),
                            "_compile_logs": [
                                str(
                                    path
                                    if path.is_absolute()
                                    else (working_directory / path).resolve()
                                )
                                for path in (
                                    Path(str(value))
                                    for value in dynamic.resolve(values.get("compile_logs", []))
                                )
                            ],
                            "_run_logs": [
                                str(
                                    path
                                    if path.is_absolute()
                                    else (working_directory / path).resolve()
                                )
                                for path in (
                                    Path(str(value))
                                    for value in dynamic.resolve(values.get("run_logs", []))
                                )
                            ],
                            "自定义文本": [
                                str(value)
                                for value in dynamic.resolve(values.get("custom_texts", []))
                            ],
                        },
                        deferred_values={
                            "seed": DeferredValue(
                                source="monotonic_unix", namespace="verification.seed"
                            )
                        }
                        if automatic_seed
                        else {},
                    )
                )
        return tasks
