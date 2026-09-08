# Terminal state, concise task detail, and shell profile evidence

## Decisions

- Verification task detail hides the standalone seed and run-log rows while the immutable API snapshot and plugin result evaluation retain both values.
- Terminal lifecycle and attention are separate channels. Visible “运行中/历史” groups and status text carry state; name color only reinforces it. A dot exists only after the authoritative `log_size` of an unselected task grows beyond the page's first-observation baseline, and selection acknowledges it.
- A string command remains deterministic `/bin/sh -c` unless configuration explicitly supplies `shell`. An explicit bash/csh-like shell uses `-ic`, allowing its normal interactive rc file and aliases/functions. Exact argv rejects `shell`.
- The absolute working directory is bound into the normalized interactive command after root-relative resolution. This avoids a new internal environment variable and restores cwd after an rc-file `cd`.

## Natural failures and fixes

1. The first Edge reproduction required `data-terminal-state=running`; the old list had no state contract and every row rendered the same dot. It failed at `frontend/e2e/localflow.spec.js:564` before the new implementation.
2. The first background-growth test submitted a second task while `max_concurrency=1`; it remained queued behind the long live task and failed the running-state oracle. The test was corrected to select retained history while the already-running terminal emitted a delayed second line, so it exercises real background growth without assuming spare concurrency.
3. Windows full pytest cannot establish Linux shell/PTY semantics. A disposable systemd Docker host runs the Linux-only isolated-HOME `.bashrc` alias test and the complete systemd/permission suite.

## Direct proof

- `tests_v2/test_command_contract.py` covers default shell, explicit bash/csh command shape, exact argv, invalid combinations, empty and NUL rejection.
- `tests_target/test_shell_profile.py` creates a real `.bashrc` alias, deliberately changes to the LocalFlow root in rc, then proves the relative marker and recorded cwd exist only in the configured external project.
- `frontend/e2e/localflow.spec.js` proves active/history order and labels, no initial or selected-stream dot, one accessible marker after actual background log growth, acknowledgement on selection, retained API seed, and absent seed/run-log rows in verification task detail.
- The full browser receipt, Linux systemd receipt, static interaction contract, source hashes, screenshots, resource metrics and final release verification are generated only after the final source is fixed.

## Research

Official VS Code documentation treats terminal status as a conditional tab icon rather than a permanent decoration and keeps terminal names/statuses separately visible. W3C WCAG 2.2 requires information not be conveyed through color alone. GNU Bash documents that interactive non-login shells read `~/.bashrc`, while non-interactive shells do not expand aliases unless configured; this is why profile loading is explicit rather than silently changing every string command.

- https://code.visualstudio.com/docs/terminal/appearance
- https://code.visualstudio.com/docs/terminal/basics
- https://www.w3.org/WAI/WCAG22/Understanding/use-of-color
- https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files
- https://www.gnu.org/software/bash/manual/html_node/Aliases.html

The first combined web research request for VS Code, Carbon and WAI did not return within three bounded 30-second waits and was terminated. A narrower retry succeeded for official VS Code/W3C sources, and a separate official GNU Bash query succeeded. The timeout therefore did not reduce the implemented evidence or leave a research dependency unresolved.
