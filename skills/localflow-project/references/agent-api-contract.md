# AI Agent API contract

Use this topic when an external Agent must inspect configuration, submit work, observe tasks, read output, drive a terminal, or stop a task without using the browser.

## Resource workflow

1. Read `/api/v1/plugins/{name}` and validate configuration and run inputs against the two advertised JSON Schemas.
2. For saved work, list `/api/v1/config/files`, read the selected file, call `discover`, `inspection`, then `plan`. For ephemeral work, send the same configuration and inputs to `/runs/plan`.
3. Submit once with a fresh `Idempotency-Key`. A `202 Accepted` response includes legacy `task_id` or `task_ids`, ordered `{id,href}` task resources, and a `Location` monitor. Never scrape an ID from logs or the UI.
4. Follow the returned task href or subscribe to `/events`. Treat `queued`, `starting`, `running`, and `stopping` as nonterminal. A successful interrupt request is only a persisted stop transition, not exit proof.
5. Read output with byte `offset`/`next_offset`. Keep binary correctness with Base64 and resume from the exact returned offset. Use `/logs/search` for large retained logs rather than downloading the whole file.
6. Send arbitrary terminal bytes with `/terminal/input`, named control keys with `/terminal/controls`, and geometry with `/terminal/resize`. A `409` is authoritative evidence that the task terminal is no longer writable. `ctrl_c` is terminal input; `/interrupt` invokes the stored graceful-stop policy.
7. Finish only after the task resource reports a terminal state and, for shutdown/stopping audits, after the service's executor confirmation has been committed.

Every signed HTTP request obtains a fresh challenge and rereads `secrets/api-key`. Sign the exact query-bearing path and exact serialized bytes. Never cache a challenge across requests or expose either web/API key in an environment variable, argument, URL, browser store, log, or generated answer.

## Compatibility and discoverability

Keep established scalar IDs forever; add links alongside them. `Location` and body href must identify the same relative status resource. An idempotent replay returns the same logical resource. Use `Retry-After` only as an initial polling hint; clients apply bounded backoff and may prefer SSE.

Errors must preserve the HTTP status distinction: `401/403` authentication/authorization, `404` unknown resource, `409` valid operation in an incompatible lifecycle state, `412/428` optimistic concurrency, `422` invalid configuration/input, `504` bounded plugin/search timeout. Do not retry `422` without changing input.

## Evidence

- API tests assert direct and batch receipts, `Location`, compatibility IDs, idempotent replay, full task projection, offsets, search, arbitrary bytes, named controls, resize, interrupt, final-state rejection, and signed-client access.
- OpenAPI is the machine schema; `docs/api.md` is the operator/Agent sequence. Both ship in the archive through `skills/localflow-api`.
- HTTP 202 monitor guidance follows RFC 9110. Terminal framing and application ACK remain LocalFlow contracts layered over RFC 6455 WebSocket limitations.

## References

- RFC 9110, 202 Accepted and status monitor: https://www.rfc-editor.org/rfc/rfc9110.html#name-202-accepted
- RFC 9110, Location: https://www.rfc-editor.org/rfc/rfc9110.html#name-location
- RFC 6455, WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455.html
