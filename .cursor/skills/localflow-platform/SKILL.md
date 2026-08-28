---
name: localflow-platform
description: Implement, review, test, or document the LocalFlow Ubuntu offline task scheduling platform. Use for task lifecycle, systemd execution, queue mutex keys, config file synchronization, HMAC auth, plugin templates, terminal UI, and release quality work in this repository.
---

# LocalFlow Platform

## Required reading

Read the relevant project sources before changing behavior:

- Product behavior: `../../../docs/requirements.md`
- Ownership and lifecycle: `../../../docs/architecture.md`
- HTTP and realtime behavior: `../../../docs/api.md`
- Config and variables: `../../../docs/configuration.md`
- Plugin model: `../../../docs/plugins.md`
- Access control: `../../../docs/security.md`
- Ubuntu behavior: `../../../docs/operations.md`
- Quality and claims: `../../../docs/quality-metrics.md`
- Research choices: `../../../docs/research.md`

## Invariants

- Keep task processes outside the web server lifecycle.
- Route all lifecycle state changes through one task service.
- Store an immutable resolved snapshot when a task is queued.
- Create the bounded task log at queue acceptance. A start failure must still own a start time, log path, lifecycle context, concrete exception and final state.
- Keep display labels separate from mutex keys.
- Treat loopback binding and random ports as exposure reduction, never authentication.
- Enforce read-only projections on the server for HTTP, SSE, and WebSocket.
- Never place long-lived API keys in browser storage or task environments.
- Preserve source config formatting and reject stale web writes.
- Treat run acceptance as a transaction: immediate pending state, duplicate-submit lock, 202 confirmation, then bind QA to the returned task identity rather than a non-unique name.
- Render tooltips through one portal layer and prove clipping, viewport collision, pixel topness, hover, focus and Escape behavior with the shared browser oracle.
- Make SIGINT the first interrupt stage and test escalation with real processes.
- Protect the controller with caught no-op SIGINT/SIGTERM/SIGHUP handlers so exec'd tasks regain default dispositions; reserve SIGUSR1 and the packaged `stop-localflow.sh` for explicit, verified fleet shutdown.
- Treat `config/` and `plugins/` as a versioned resource workspace. Preserve symlink identity for copy/move/delete, follow links only for read/write, and reconcile external targets on a bounded timer because native watchers do not consistently follow them.
- Bound terminal output with one application-level ACK per xterm write; browser WebSocket APIs do not provide sufficient receive-side backpressure by themselves.
- Do not claim Ubuntu production readiness without target systemd evidence.

## Work sequence

1. Map every change to requirement IDs and quality metrics.
2. Update design sources first when behavior or ownership changes.
3. Implement the smallest responsibility owner; do not introduce a second lifecycle writer.
4. Add a passing case and a fault case that proves the oracle detects failure.
5. Run focused tests, then mirror every command in the Release workflow's source-quality step locally, including Ruff, pytest, the traceability checker, frontend build, and npm audit. A partial local gate is not release evidence.
6. Store evidence under `quality/evidence/` and update `quality/traceability.json`.
7. Report platform limits and any autonomous-learning failure explicitly.

## Test routes

- Pure application logic: local Python test environment.
- Browser behavior: built frontend plus browser end-to-end tests.
- Linux process and filesystem behavior: Linux container.
- systemd, PTY signal, owner permissions, restart recovery, and time helper: real Ubuntu systemd target.

No mock-only result can satisfy a target-platform metric.

## Ubuntu deployment route

1. Build `frontend/dist` without CDN dependencies and place the repository or release tree at `/opt/localflow`.
2. Create `/opt/localflow/venv`, install the project, and verify `/opt/localflow/venv/bin/localflow`.
3. Create the dedicated `localflow` system user and enable linger so its user systemd manager survives logouts.
4. Validate and install `deploy/localflow.sudoers`; install the fixed time helper, tmpfiles configuration, and main service unit with the modes in `README.md`.
5. Run tmpfiles, initialize `/var/lib/localflow` as the service user, build or edit the startup-only `/var/lib/localflow/config.yaml`, then enable the service.
6. Read the actual endpoint with `localflow status`; read the one-time administrator code only as the service user.
7. Run all `tests_target` under the `localflow` user manager and run `tests_target/deployed_probe.py` before claiming the deployment stable.
8. Run `tools/run_browser_quality.py` against system Edge; preserve explicit `blocked` status if neither that route nor the target route is available, and link exact evidence instead of widening the claim.
