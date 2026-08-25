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
- Read logs by byte offset and send task input/control through the documented task endpoints. An interrupt response of `stopping` is not proof that the process has exited.

Use placeholders such as `/srv/localflow`, `/srv/project`, and `KEY_FILE`; never copy machine-specific paths, ports, cookies, or secrets into reusable examples.
