---
name: localflow-operations
description: Operate, diagnose, restart, or deploy LocalFlow on Ubuntu while protecting active tasks, credentials, logs, retention, and system resources.
---

# LocalFlow operations

Read `../../docs/operations.md`. For task exit incidents also read `../../docs/stopping.md`; for terminal behavior read `../../docs/terminal.md`.

## Safe operating boundary

- Resolve the actual root, service account, configuration, backend, PID, and active task count before restart or migration.
- Do not stop the controller merely to refresh static files while user tasks are active. The Ubuntu executor owns tasks through systemd/cgroups so controller restart must not kill them.
- Treat `stopping` as active. Confirm the complete task process owner is inactive before calling the task cancelled or the machine clean.
- Keep secrets owner-readable only and never print their contents.
- Retention deletes terminal task metadata and output together. Capacity protection may remove oldest terminal output early, but must record that it is unavailable.
- Measure controller CPU/RSS separately from user tasks and verify file, process, socket, and WebSocket cleanup after long-running checks.

Use a staged candidate directory for upgrades and retain the previous runnable version until the new health check passes.
