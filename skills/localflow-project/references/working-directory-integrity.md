# Working-directory integrity

## Contract

- Every runnable configuration explicitly supplies `working_directory`; plugins must not silently substitute the LocalFlow runtime root.
- Relative working directories are interpreted against the LocalFlow runtime root once, by the host, before plan display and enqueue. Plan, immutable task snapshot, lifecycle log, executor cwd, and child cwd must agree on the same absolute value.
- Plugins may create tasks but do not own relative-path policy. `TaskService` repeats normalization for direct task submissions so the public task API has the same snapshot rule.
- Never infer cwd from arbitrary command text. GNU Make `-f FILE` selects a makefile but does not change directory; `make -C DIR` explicitly changes directory before reading makefiles. The user chooses `working_directory` or writes `-C`.

## Natural reproduction (2026-09-04)

Frozen baseline commit `cef4941041b6b3161d59dd2e34b6125fd713186c` was exercised twice through `/api/v1/runs/plan`, `/api/v1/runs`, task detail, log, and filesystem side effects on hosted Ubuntu with real GNU Make. Run https://github.com/XiaoHui2023/localflow/actions/runs/33848596095 records the complete receipt.

- Verification config without `working_directory`, using `make -f /tmp/.../external-project/External.mk all`, planned and ran in the LocalFlow root. Make `CURDIR`, prerequisite read, `mkdir`, and output all proved the wrong root.
- The same config with explicit external `working_directory` read the external prerequisite and wrote only below the external project.
- A command-plugin config with relative `working_directory: project` preserved `project` in the plan and later failed because it was resolved from a backend-dependent controller cwd.

This is a configuration/snapshot ownership escape, not a GNU Make defect and not evidence that `-f` should imply a directory.

## Fix and regression corpus

1. Require `working_directory` for the verification plugin while leaving `${case}`, `${seed}`, and `${run}` entirely optional in arbitrary commands.
2. Normalize plugin drafts before plan/enqueue and normalize direct task drafts again in `TaskService`.
3. Upgrade an installed built-in plugin only when its normalized content digest matches a known shipped baseline. Preserve edited regular files and every symlink.
4. Short gates cover missing cwd rejection, relative plan/task equality, direct task submission, arbitrary commands with no Case/seed placeholders, user edits, and plugin symlinks.
5. Long gates use real Make and assert `CURDIR`, prerequisite content, positive target effects, negative LocalFlow-root effects, systemd ownership, and the extracted frozen executable.

The old implementation must fail the natural-reproduction Oracle. Printed `PWD` alone is insufficient because it does not prove prerequisite resolution or child side effects.

## Tool fallback record

The Windows host had no GNU Make, Docker Desktop's Linux backend named pipe was unavailable, and WSL exposed only `docker-desktop`. The bounded fallback was a disposable Git worktree/branch plus hosted Ubuntu Actions; the branch and worktree were removed after downloading the immutable receipt. GNU Make manual per-node pages timed out in the web reader, so the full official manual was used instead: https://www.gnu.org/software/make/manual/make.html.
