# Identity, Agent API, adaptive Shell, and Case row evidence

## Failure-first observations

- A default string task ignored `$SHELL=/bin/bash` and normalized to `/bin/sh -c`; `$SHELL=/bin/tcsh` behaved identically. New model tests failed on both argv shapes before the common normalizer changed.
- `server.session_cookie_domain` was silently discarded as an unknown settings field. A sibling-host login produced no Domain attribute; insecure and unrelated hosts were accepted. Parameterized unsafe-domain tests all failed before validation and request gates were added.
- The Case picker still rendered `.case-step.increase`, so the user's requested row-as-increment interaction was absent. The static interaction contract now forbids that control, and the browser journey targets the row for click and hold.
- Accepted task creation already returned IDs, but callers still had to construct monitor URLs. Tests now require `Location`, `Retry-After`, compatibility IDs, body hrefs, ordered batch resources, and stable idempotent responses.

## Implemented contracts

- String commands select `$SHELL`, then the effective user's passwd login Shell, then `/bin/sh`; `false`/`nologin` are not selected. Core invokes `-ic`, freezes that argv, and restores the absolute cwd after rc loading. Exact argv stays exact. Run inspection shows the selected Shell even when automatic.
- `web-admin-key` remains create-once. Host-only persistent cookies cover same-host restarts and port changes. Opt-in `session_cookie_domain` accepts plain multi-label DNS names only; cookie issue/refresh requires HTTPS and a matching host, and sets Secure. Two independent runtime roots with copied identical web keys authenticate through one standards-compliant sibling-domain cookie jar.
- The Case name row is the increase button. Pointer press adds one, repeats after 550 ms with bounded acceleration, and global release/cancel/blur cleanup remains authoritative. The conditional minus retains the same state machine; no plus is rendered. Ctrl/Cmd click and marquee retain group selection.
- Single task and batch creation preserve `task_id`/`task_ids`; each adds resource objects, and 202 headers identify the same status monitor. Archive Skills define an Agent sequence from schema/plan through ID, events/log offsets, terminal control, interrupt, and confirmed final state.

## Direct evidence

- Windows: `tests_v2/test_command_contract.py`, `test_security.py`, `test_tasks.py`, `test_terminal.py`, and `test_config.py`.
- Ubuntu Docker: `tests_target/test_shell_profile.py` passed both a real `.bashrc` alias and a real `.cshrc`/tcsh alias while each rc changed to the wrong directory; all relative output stayed in the configured external project.
- Browser: `frontend/e2e/localflow.spec.js` verifies no plus, one click, delayed repeat, release stability, decrement-to-zero, grouping, wheel no-op, and post-run reset. The receipt is regenerated from current sources before publication.

## Research basis

- RFC 6265 defines host-only versus Domain cookies, cross-subdomain scope, port sharing, persistence, Secure/HttpOnly behavior, public-suffix rejection, and the sibling-domain integrity caveat.
- RFC 9110 says a 202 representation ought to identify a status monitor; Location is the standard resource reference.
- GNU Bash documents `.bashrc` for interactive non-login shells and default alias expansion. zsh and fish official documentation confirm their interactive startup configuration; POSIX `pwd.h` defines `pw_shell`.

## Learning/tool disclosure

The external Skill registry search for reusable LocalFlow-specific operator patterns timed out twice at the bounded 60-second limit without output. This prevented importing a third-party Skill, but did not block implementation: official standards/component documentation, the existing user-root solution catalog, repository contracts, failure-first tests, and real browser/Linux fixtures were used instead. Recovery requires the Skill registry/network service to return a bounded search result; rerun the catalog search before adopting a new external package.
