# Resource workspace and controller stability evidence

## Contract

- `command` is string-first for human-authored configuration and still accepts exact argv lists.
- The Run page owns one virtualized `config/` + `plugins/` explorer with direct create, folder, copy, cut, paste, rename and delete actions.
- Filesystem links remain links. Content edits follow their targets; identity operations act on the directory entry. A lexical two-root boundary prevents request paths from manufacturing outside access.
- A bounded one-second reconciliation complements native file notifications so external edits through links reach the current editor.
- Plugin reconciliation reports changed paths; clean editors refresh only when their file changed, while dirty editor content is preserved with a conflict notice.
- Terminal output uses a 64 KiB application-level ACK window tied to the xterm write callback.
- The controller survives accidental terminal signals. Only SIGUSR1 starts fleet shutdown; it exits after all task process trees are confirmed gone.
- The frozen release smoke sends INT, TERM and HUP to the complete foreground process group and verifies the private controller PID plus HTTP after every signal; it then sends SIGUSR1 to that same PID used by `stop-localflow.sh`.
- Verification Case rows use one compact full-width column with 70 ms hover/focus transitions; focus alone never changes a run count.

## Oracles and failure samples

`tests_v2/test_command_contract.py`, `tests_v2/test_workspace.py`, and `tests_v2/test_watcher.py` cover empty/NUL commands, stale versions, invalid Python, unsupported extensions, self-descendant operations, import breakage, link flattening/deletion, link cycles, and external-target changes. The browser gate performs the real explorer keyboard and disk-to-editor journeys and counts terminal ACK frames. `tools/run_frozen_smoke.py` sends all protected signals to the final binary, starts an intentionally uncooperative live process group, requests explicit shutdown, and rejects a remaining `/proc/<pid>` or controller PID file.

The release workflow repeats these checks on Ubuntu, runs the systemd/PTY target suite, executes the final static binary on legacy CPU models, and opens that same binary with current Chrome/Firefox plus fixed Chrome 84/Firefox 78 before publishing.

The first hosted run stopped at the systemd container readiness gate. A new local container proved all 106 tests still passed, isolating the difference to the hosted runner's cgroup namespace/readiness state. The workflow now shares the host cgroup namespace explicitly, accepts both systemd `running` and `degraded` as readiness states, prints failed units on timeout, and still requires the functional PTY/cgroup tests to pass before packaging.

The second hosted run passed source, systemd, static build and legacy CPU gates, then exposed that current Uvicorn uses `capture_signals()` rather than the legacy `install_signal_handlers()` hook. After disabling both ownership paths, a rebuilt onefile exposed the separate PyInstaller parent/controller PID model under SIGHUP. The final oracle follows the real controller PID instead of equating it with the unpacking parent. Both the standalone staticx executable and a fresh archive extraction passed the complete task, process-group signal, uncooperative child cleanup and PID-file smoke.

## Final local and target results

- Windows source suite: 95 passed, 4 skipped; Ruff, dependency audit and `git diff --check` passed.
- Ubuntu 24.04 systemd target: 106 passed, including owner permission, PTY and symlink behavior.
- Browser matrix: Edge full journey 2/2, current Chromium/Firefox 2/2, fixed Chrome 84 and Firefox 78 boot/login/editor journeys passed with zero captured console/resource errors.
- Warm idle evidence: controller RSS 62.285 MiB, controller CPU 0.757% of one core, renderer heap 11.409 MiB, renderer idle CPU 0.621%, 1,110 DOM nodes, 309 listeners, 7 background requests, zero hidden WebSockets and one observed xterm ACK frame.
- Case browser oracle: exactly one x origin, every row at least 95% of list width, transition duration at most 100 ms, focus-visible state without count mutation; click, wheel, marquee and group editing remained green.

## Research disclosure

Official React Arborist, VS Code file-watcher, xterm.js flow-control/security, Python process, Linux inotify, and systemd documentation were reachable during this iteration. No learning/download step failed, so no capability was silently replaced by an unverified assumption. Source links and adopted boundaries are recorded in `docs/research.md`.
