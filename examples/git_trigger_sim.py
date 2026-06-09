from __future__ import annotations

import importlib
from pathlib import Path

from plugins.git_update import GitRepoUpdatePayload, GitUpdateAutomation

_repo = Path(__file__).resolve().parents[1]
_sim = importlib.import_module("examples.sim_run_script")

git_trigger_sim = GitUpdateAutomation(
    name="git_trigger_sim",
    repo_path=_repo,
    interval=60.0,
)

git_trigger_sim.register_script(_sim.sim_run)


@git_trigger_sim.register
async def on_git_update(payload: GitRepoUpdatePayload) -> None:
    commit = payload.update.commit
    print(
        "git 更新，触发仿真:",
        f"{payload.previous_hash[:7]} -> {commit.short_hash}",
        commit.subject,
    )
    _sim.sim_run.variables.set("phase", "由 git 触发")
