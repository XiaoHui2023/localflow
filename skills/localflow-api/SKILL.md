---
name: localflow-api
description: Use and integrate LocalFlow's signed HTTP API for task queries, configuration lifecycle, plugin discovery, batch runs, logs, terminal input, and interruption.
---

# LocalFlow API

Read `../../docs/api.md` before generating a client and `../../docs/security.md` before handling credentials.

## Client rules

- Use the documented `/api/v1` paths; the UI is not an API contract.
- For every signed request: obtain a fresh challenge, reread the configured key file, sign the exact method, query-bearing path, body digest, nonce, and key generation, then discard transient signing material.
- Never place the key in a URL, browser storage, checked-in configuration, logs, examples, or answers.
- Use idempotency keys for retryable task or batch creation. Treat `422` as an input problem, not a retry signal.
- Prefer `POST /api/v1/runs` when one request must carry a plugin configuration plus run inputs and expand into one or more tasks.
- Fetch `/api/v1/plugins/{name}` for separate configuration and input JSON Schemas. Use `/runs/plan` or the saved configuration `/plan` endpoint to inspect exact task drafts without side effects; `deferred_values` are allocated only by the atomic submit transaction.
- Saved-configuration runs and inline runs return the same batch response and support atomic idempotency. Reusing one key with a changed body returns the original response, so generate one key per logical request.
- A 202 response carries compatibility IDs plus ordered `{id,href}` task resources. Follow the `Location` monitor instead of constructing or scraping a URL; an idempotent replay identifies the same logical resource.
- Read logs by byte offset and send task input/control through the documented task endpoints. Use arbitrary bytes for program input, named controls for Ctrl+C/Ctrl+D/Enter/Escape/Tab, resize before driving a full-screen program, and use server-side search for retained large logs. HTTP 409 means the terminal is no longer writable.
- Treat terminal Ctrl+C and task interrupt as different actions. An interrupt response of `stopping` is not proof that the process has exited; continue the returned task resource or events stream until a terminal state.

For the complete Agent state machine, compatibility/error contract, and evidence map, read `../localflow-project/references/agent-api-contract.md`.

Use placeholders such as `/srv/localflow`, `/srv/project`, and `KEY_FILE`; never copy machine-specific paths, ports, cookies, or secrets into reusable examples.
