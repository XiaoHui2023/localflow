# Stopping progress and process ownership

Use this topic when a task is slow to exit, appears hung, leaves descendants, loses its result observer, or must be controlled by an AI client.

## Decision model

1. The task snapshot owns a replayable sequence of signal, terminal-input, or dedicated stop-command actions.
2. `timeout_seconds` is the ordinary grace period. Never infer a program-specific quit command or acceptable shutdown duration in the core.
3. If and only if the application emits trustworthy cleanup progress, the plugin may set `extend_timeout_on_output: true` and a finite `max_timeout_seconds`. New bytes reset the quiet window but never the hard deadline.
4. After the final graceful action, kill the complete systemd cgroup, not a remembered child PID. Keep `stopping` until both the unit is inactive and an exit result is available.
5. A result-channel exception is not an exit fact. Probe ownership; retry with bounded backoff while the process tree remains alive. Use `lost` only when neither a live owner nor a result exists.
6. Controller shutdown owns a global graceful budget. At expiry it cancels competing soft sequences, records `sigkill`, cleans every remaining cgroup, and waits for proof rather than abandoning ownership.

## AI terminal intervention

- Send line-oriented commands through UTF-8 input.
- Send arbitrary escape/control bytes through Base64 input; use named Ctrl+C/Ctrl+D for the common cases.
- Resize before driving a full-screen terminal program.
- Observe output by byte offset or the ACK-gated WebSocket; never infer acceptance from a successful write alone.
- Distinguish terminal Ctrl+C from task interrupt: the former is application input, the latter enters the persisted stop protocol.
- Treat HTTP 409 as an authoritative non-writable terminal, especially after completion.

## Required evidence

- A graceful task emits cleanup progress longer than its quiet window and exits naturally with code 0.
- A noisy non-terminating task reaches the hard bound, is SIGKILLed, and leaves an empty cgroup.
- A controller-wide shutdown cancels soft sequences, kills an uncooperative parent plus descendant, records `sigkill`, and proves the unit inactive.
- An injected wait-channel failure while the process remains live retries and reaches the true exit code.
- Signed HTTP tests cover arbitrary terminal bytes, Ctrl+C, resize, offset logs and terminal-state rejection; administrator browser tests separately cover WebSocket ACK.

## Sources and scope

- systemd `systemd.service` documents a graceful stop timeout followed by SIGKILL and repeated `EXTEND_TIMEOUT_USEC` notifications for legitimate long stops: https://github.com/systemd/systemd/blob/main/man/systemd.service.xml
- systemd transient units support `KillMode`, `SendSIGKILL`, and stop timeout properties: https://github.com/systemd/systemd/blob/main/docs/TRANSIENT-SETTINGS.md
- systemd warns that `KillMode=none` disables process lifecycle management and recommends `control-group` or `mixed`: https://github.com/systemd/systemd/blob/main/src/core/load-fragment.c

LocalFlow does not claim that terminal output is equivalent to `sd_notify`. It deliberately exposes output-based extension only as an opt-in plugin contract and adds a hard deadline because arbitrary task output is not authenticated progress.
