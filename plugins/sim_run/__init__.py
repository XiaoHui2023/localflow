from __future__ import annotations

from pathlib import Path

from .command import format_command
from .log_result import SimResultStatus, evaluate_log_result, resolve_log_path
from .script import SimRunScript

_DEFAULT_WORK_DIR = Path(__file__).resolve().parents[2]

sim_run = SimRunScript(
    name="仿真运行",
    project="chip_a",
    module="tb_top",
    case="sanity_smoke",
    seed="42",
    work_dir=str(_DEFAULT_WORK_DIR),
    command="echo sim {project} {module} {case} SEED={seed}",
    pass_regex=r"PASS|passed|UVM_ERROR\s*:\s*0",
    fail_regex=r"FAIL|UVM_ERROR\s*:\s*[1-9]",
    log_path="sim.log",
    result_status="—",
    formatted_command="",
    exit_code="—",
    duration="—",
    phase="待运行",
    log_tail="",
    error_message="",
    error_traceback="",
)

__all__ = [
    "SimResultStatus",
    "SimRunScript",
    "evaluate_log_result",
    "format_command",
    "resolve_log_path",
    "sim_run",
]
