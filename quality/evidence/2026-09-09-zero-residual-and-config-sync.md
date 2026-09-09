# Zero-residual shutdown and direct config synchronization

## Failure evidence

- `SystemdExecutor` previously treated every non-zero `systemctl is-active` result as inactive. systemd can return non-success while a unit is still `deactivating`, so that boolean was not sufficient proof that the task cgroup had finished cleanup.
- `TaskService.shutdown_all` took its active snapshot without first joining already-dispatched `_start` coroutines. A late systemd ownership handoff could therefore race the snapshot.
- `config.invalid` events originally displayed a notice but did not carry a version or reload externally written invalid YAML into a clean Monaco editor.
- The first direct Playwright invocation lacked the project runner's base URL and failed before navigation. It is environment setup evidence, not a product failure; the formal browser runner was used for the valid receipt.
- The first repeated formal browser run found a harness false positive: `count()` matched a hidden login field and then waited for it as if login were required. The harness now checks `isVisible()`; the full matrix was rerun rather than accepting the partial result.

## Corrective design

- Stop scheduling and await all dispatched launchers before the shutdown snapshot. Then cancel queued work, run graceful stop strategies, escalate complete process groups/cgroups and wait for ownership proof.
- Read explicit `LoadState` and `ActiveState`. Treat `activating`, `active`, `reloading`, `deactivating`, maintenance and unknown non-terminal values conservatively as owned. Accept only loaded `inactive`/`failed`, or `not-found`, as no longer running.
- Include a content version on invalid configuration events and pass valid/invalid changes through the same targeted SSE reload. Preserve dirty drafts instead of replacing them.

## Verification

- Focused Python scheduler/watcher/systemd-state suite: 17 passed, 1 Linux-only symlink test skipped on Windows.
- Complete `tests_v2`: 152 passed, 5 platform-specific skips. Complete Ruff and traceability checks passed; frontend `npm audit` reported zero vulnerabilities.
- Disposable Ubuntu 24.04/systemd container target gate: 170 passed. The explicit post-run probes found no `localflow-task-*` user units and no LocalFlow supervisor or test `sleep 30` process. The inspected container was then removed.
- Browser gate: Edge full workflow 2 passed, current Chromium/Firefox 2 passed, and fixed Chrome 84 plus Firefox 78 both passed. The test directly writes valid and invalid YAML under the live test root, observes automatic editor/Problems refresh within 3 seconds, then writes a different disk version while the editor is dirty and proves the draft remains visible.
- Complete source, Ubuntu/systemd, frozen binary, publish and downloaded-asset results are recorded below when the same commit finishes the release chain.
