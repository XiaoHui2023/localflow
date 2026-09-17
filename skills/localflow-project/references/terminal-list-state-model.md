# Terminal list state model

## Operator questions

The list answers two questions: “Which terminals are still live?” and “Which background terminal produced output I have not viewed?” The selected terminal header answers “When did this terminal last produce bytes?” Lifecycle, activity freshness, and attention are different channels and must not share one always-visible dot.

## Selected pattern

| Channel | Source of truth | Presentation | Acknowledgement |
| --- | --- | --- | --- |
| Lifecycle | Task `state` and plugin status label | Visible `运行中`/`历史` groups; rows contain only name and tags | Changes only with task lifecycle |
| Output activity | `log_updated_at` from the filesystem metadata snapshot carried by task and WebSocket output/caught-up frames | For a selected, caught-up terminal with output, one neutral semantic time beside the name; hide during replay and below 5s, then show `24s`, `5m 12s`, `3h 8m`, or `2d 4h`; no output renders nothing, and rail rows never contain it | Recomputed every second while selected and active; authoritative origin changes only when the log is written |
| New output | Increase in authoritative `log_size` after this page observed the task | One accent dot labelled `有新终端输出`, only on an unselected row | Selecting the terminal records the current size and removes the dot |

## Selection and search compatibility

Terminal selection is tail-first. Key the xterm owner by task identity and derive its initial byte-window state synchronously from the selected task snapshot; an effect that begins at zero then updates to `log_size - 4 MiB` creates a real first WebSocket replay and visibly crawls through the archive. Keep the emulator visually hidden during its bounded ACK replay, call `scrollToBottom()` on `caught_up`, and reveal only in the following animation frame. This preserves immediate latest-output orientation without inventing connection text. Earlier data remains available only through the explicit prior-range control or an archive-search offset result.

Archive search owns a separate historical-navigation mode. Do not label a native-button result list as a `listbox` unless its option-selection and roving-focus contract is actually implemented. Use a bounded scrollable region with a visible result count and a complete row for every item: line number and byte offset as metadata, then an at-least-two-line code preview. Closing Find, Escape, or the result panel clears both results and errors and restores terminal keyboard focus. Clicking a hit closes the panel, loads a bounded byte window with leading context, uses xterm Search addon to reveal the hit, and freezes even a live terminal's WebSocket `end` at the selected window. A hit window is capped at 256 KiB, not the normal 4 MiB page: raw bytes can wrap into more visual rows than xterm's bounded scrollback and silently evict the match. Manual previous/next navigation returns to 4 MiB pages. The usual catch-up `scrollToBottom()` applies only in tail-follow mode; historical windows start at their hit/context, and a distinct `最新输出` action returns to live tail-follow.

Keep Ctrl/Cmd+C as the primary xterm selection-copy gesture. The pointer fallback is a mature context-menu primitive opened exactly where the user right-clicks: one solid-surface Copy item operates on `term.getSelection()`, supports keyboard/Escape/focus/collision behavior, and is disabled without a selection. Do not reveal a detached toolbar button after selection; it moves the action away from the user's pointer and does not match ordinary web text-copy expectations. Search overlays need a solid theme-color `background` declaration before any `color-mix()` enhancement; unsupported modern CSS must never make text controls transparent.

Active terminals sort before retained history; each group sorts newest first. Rail rows contain only neutral names and tags plus conditional unread attention, selection uses an inset accent edge, and the rail expands to a bounded 248–320px on wide screens. “只读历史” is omitted because the history group and absence of input controls already express the state.

Preserve xterm's selection-first copy convention. When Ctrl/Cmd+C arrives with a selection, copy `term.getSelection()` and consume the key; only an interactive terminal with no selection may forward Ctrl+C to the task. Retained history has no input channel, so copying can never become a late control action. Do not add a permanent copy button for every terminal line.

## Rejected alternatives

- A state-colored dot on every row: ambiguous, visually noisy, and color-only.
- A completion dot or permanently state-colored name: duplicates the group and collides with “new output after completion.”
- Repeating `运行中` or `只读历史` in every row/header: consumes the narrow identity surface without adding a decision.
- Mark every non-empty historical log unread on first load: creates a wall of false notifications.
- Infer “quiet for a long time” from task `updated_at` or polling time: neither is the last-output timestamp. Use the log file metadata already read for authoritative size, and do not label silence as a hang.
- Persist unread unread state in local storage: cannot reconcile log truncation, retention, another browser or another administrator without a server cursor.

Persistent unread still requires a per-user server acknowledgement cursor. Output age needs only the server-owned log timestamp; it must not be persisted or guessed by CSS. Browser receive/render time is not the same fact: buffered replay may visibly change long after the producer wrote it. Hide activity age until the protocol sends `caught_up`, then use the timestamp on that frame and subsequent live output frames.

## Selected-header timer contract

Keep task identity and output age in one non-wrapping flex row. The age is supporting metadata, so the name owns remaining width and ellipsizes before the timer; do not turn the pair into a two-row grid. Mount one one-second interval only while the terminal page is mounted, clean it up symmetrically, and compute from `Date.now() - log_updated_at` rather than incrementing a counter that can drift. A short 5-second suppression window avoids flashing `0s`–`4s` immediately after every write. Preserve seconds through the minute range because `5m` is too coarse for watching a recently quiet process; bound longer values to two adjacent units.

## Test oracle

Edge opens a live terminal with output, resets its real log mtime, sees no age inside 5 seconds, then observes the single semantic age appear and advance without another server write. It rewinds the same real mtime by 127 seconds and requires `2m Ns`, a header no taller than 52px, vertically aligned name/time centers, and time to the right of the name; no rail row may contain a time. An output-less selection and every retained-history selection render no activity element or placeholder: a completed task cannot still be described by an ever-growing stall timer. It copies a selected live output token with Ctrl+C without stopping the task, repeats selection/copy in retained history, then verifies history still has no input controls. It selects retained history; when the live task's real log size grows, the background unread marker advances without adding a row timestamp. Selecting the live row clears the marker and refreshes the single header timestamp. The same journey proves “运行中” precedes “历史,” per-row lifecycle prose and “只读历史” are absent, names/tags remain visible, terminal bytes contain no connection/replay notices, and wide/mobile layouts do not overflow.

## Primary references

Checked 2026-09-08:

- VS Code Terminal Basics and Appearance: terminal tabs use a title plus optional status icon; status icons appear only when status changes, not as universal decoration. https://code.visualstudio.com/docs/terminal/basics and https://code.visualstudio.com/docs/terminal/appearance
- WCAG 2.2 Understanding 1.4.1 and G14: color cannot be the only means of conveying state; provide text or another cue. https://www.w3.org/WAI/WCAG22/Understanding/use-of-color and https://www.w3.org/WAI/WCAG22/Techniques/general/G14.html
