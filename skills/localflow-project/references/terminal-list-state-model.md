# Terminal list state model

## Operator questions

The list answers three independent questions: “Which terminals are still live?”, “When did each terminal last produce bytes?”, and “Which background terminal produced output I have not viewed?” Lifecycle, activity freshness, and attention are different channels and must not share one always-visible dot.

## Selected pattern

| Channel | Source of truth | Presentation | Acknowledgement |
| --- | --- | --- | --- |
| Lifecycle | Task `state` and plugin status label | Visible `运行中`/`历史` groups; rows contain only name and tags | Changes only with task lifecycle |
| Output activity | `log_updated_at` from the same filesystem metadata snapshot as `log_size` | Only a neutral compact age (`刚刚`, `24 秒`, `5 分钟`, or `—`) in each row; exact time and meaning stay in semantic `time` metadata | Changes only when the log file is written |
| New output | Increase in authoritative `log_size` after this page observed the task | One accent dot labelled `有新终端输出`, only on an unselected row | Selecting the terminal records the current size and removes the dot |

Active terminals sort before retained history; each group sorts newest first. Names and tags stay neutral, selection uses an inset accent edge, and the rail expands to a bounded 248–320px on wide screens. “只读历史” is omitted because the history group and absence of input controls already express the state.

## Rejected alternatives

- A state-colored dot on every row: ambiguous, visually noisy, and color-only.
- A completion dot or permanently state-colored name: duplicates the group and collides with “new output after completion.”
- Repeating `运行中` or `只读历史` in every row/header: consumes the narrow identity surface without adding a decision.
- Mark every non-empty historical log unread on first load: creates a wall of false notifications.
- Infer “quiet for a long time” from task `updated_at` or polling time: neither is the last-output timestamp. Use the log file metadata already read for authoritative size, and do not label silence as a hang.
- Persist unread unread state in local storage: cannot reconcile log truncation, retention, another browser or another administrator without a server cursor.

Persistent unread still requires a per-user server acknowledgement cursor. Output age needs only the server-owned log timestamp; it must not be persisted or guessed by CSS.

## Test oracle

Edge opens a live terminal and sees a semantic output-activity time but no dot merely because it is running. It selects a retained history terminal; when the live task's real log size grows, both the authoritative timestamp and background unread marker advance. Selecting the live row clears the marker. The same journey proves “运行中” precedes “历史,” per-row lifecycle prose and “只读历史” are absent, names/tags remain visible, terminal bytes contain no connection/replay notices, and wide/mobile layouts do not overflow.

## Primary references

Checked 2026-09-08:

- VS Code Terminal Basics and Appearance: terminal tabs use a title plus optional status icon; status icons appear only when status changes, not as universal decoration. https://code.visualstudio.com/docs/terminal/basics and https://code.visualstudio.com/docs/terminal/appearance
- WCAG 2.2 Understanding 1.4.1 and G14: color cannot be the only means of conveying state; provide text or another cue. https://www.w3.org/WAI/WCAG22/Understanding/use-of-color and https://www.w3.org/WAI/WCAG22/Techniques/general/G14.html
