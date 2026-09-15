# Terminal output freshness and million-line evidence

## Decision

The operator question is “when did this terminal last produce bytes?”, not “when did the task state last change?” LocalFlow now takes one filesystem metadata snapshot per full task projection and returns both `log_size` and UTC `log_updated_at`. This adds no per-task syscall to the existing three-second bounded task refresh, survives controller restarts, and advances only when the authoritative terminal log changes. A missing log returns `null`.

The terminal rail deliberately renders no activity time: every row keeps only the task name, tags, selection state, and a conditional unread-output marker. After a user selects a terminal with output, the right-side terminal header renders exactly one neutral age containing only an integer and `s`, `m`, `h`, or `d`, such as `24s`. An output-less terminal renders no time element or placeholder. The `time` element carries the ISO value, its title gives the exact time, and its accessible name explains the compact value. Silence is evidence for operator attention, not proof of a hang, so no danger color or automatic failure state is introduced.

## Mature approaches compared

| Method | Strength | Failure boundary | Decision |
| --- | --- | --- | --- |
| Task state/update timestamp | already available | changes for queue, stop, status and recovery events without terminal bytes | rejected |
| Browser first-observation timer | no server change | resets on reload and differs by browser; not historical truth | rejected |
| Database timestamp updated by controller | query-efficient | systemd supervisor owns continuous file writes, so controller callbacks can miss bytes | rejected for current ownership |
| Log `stat` size + mtime in one snapshot | same authority and syscall as current size, restart-safe | wall-clock calibration changes displayed relative age | adopted; exact timestamp remains visible |

For large history, loading the whole file into xterm was rejected because xterm's asynchronous write queue can be overwhelmed. DOM row virtualization was also rejected as the primary solution because it does not preserve ANSI terminal semantics and does not bound archive transfer. The adopted path keeps xterm.js with a 5000-line scrollback, loads at most a 4 MiB disk window, sends at most 64 KiB then waits for the xterm write callback ACK, and searches the full archive server-side in 1 MiB blocks with 15-second and 200-result caps.

## Primary research

- xterm.js Flowcontrol explains that `write` is asynchronous, fast producers can outpace its parser, and transport-level flow control is required: https://xtermjs.org/docs/guides/flowcontrol/
- xterm.js `Terminal.write` documents its completion callback and `scrollback` is a finite row setting: https://xtermjs.org/docs/api/terminal/classes/terminal/ and https://xtermjs.org/docs/api/terminal/interfaces/iterminaloptions/
- VS Code Terminal Basics distinguishes the visible viewport from bounded scrollback and provides explicit buffer navigation: https://code.visualstudio.com/docs/terminal/basics
- Find Skills searches for `terminal log performance` returned general performance and log-forensics packages. None supplied an xterm byte-window, ACK flow-control, fixed-browser or LocalFlow filesystem-authority contract, so no package was installed; the official renderer documentation and existing project-specific skills were stronger evidence.

## Failure reproduction and gates

The first public API test failed with `KeyError: 'log_updated_at'`, proving the requested fact was absent before implementation. `tests_v2/test_terminal.py` now checks a real live task's full detail and list timestamp. Its generated million-line fixture contains exactly 1,000,000 lines and reads the final 4 MiB only in 64 KiB blocks; traced Python peak allocation must stay below 2 MiB and the read must complete within the broad 3-second lab ceiling. The pre-existing independent search fixture has 1,048,576 ordinary lines plus boundary cases, proves a match crossing the 1 MiB block edge and a final-line hit, and caps traced allocation below 32 MiB.

The Edge journey proves that all rail rows contain zero activity-time elements, records the selected terminal header's sole semantic timestamp, selects another terminal, waits for real delayed output and the unread marker, then selects the live task and proves that the single header timestamp switched to that terminal. Restoring per-row timestamps, leaving the selected header stale, removing `log_updated_at`, replacing it with task time, loading from offset zero, increasing a chunk, or removing semantic time breaks an independent browser, API, memory, or source-contract oracle.

The 2026-09-14 browser receipt passed the complete Edge journey (9 tests) and the current Playwright Chromium/Firefox compatibility journey (2 tests). With no user tasks active Edge measured 59.504 MiB controller RSS, 1.54% of one CPU core, 7.929 MiB renderer heap, zero idle WebSockets, and a 20.5 ms Terminal-to-Tasks next-paint time. The fixed Chrome 84/Firefox 78 Docker stage did not run because the local Docker Desktop Linux-engine pipe was unavailable after three bounded pull attempts; this does not weaken the direct Edge oracle but keeps fixed-legacy-browser publication validation outstanding until Docker is restored and the runner is repeated.
