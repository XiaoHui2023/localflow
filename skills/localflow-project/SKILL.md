---
name: localflow-project
description: Navigate and change the LocalFlow Ubuntu task runner codebase while preserving its task, configuration, plugin, security, and release boundaries.
---

# LocalFlow project

Use this skill when analyzing or modifying the extracted LocalFlow project.

## Start here

1. Read `../../docs/architecture.md` for owners and data flow.
2. Read only the relevant contract: `requirements.md`, `configuration.md`, `plugins.md`, `security.md`, `stopping.md`, or `terminal.md`.
3. Search `../../src/localflow/` before editing. The task database and `TaskService` own lifecycle truth; plugins expand work but do not own scheduling.
4. Keep the browser, file configuration, and program API on the same validation and plugin contracts.
5. Before declaring a user requirement complete, update `../../docs/requirements.md` and `../../quality/traceability.json`, then verify every applicable surface directly. A stored/API field does not prove it is visible in the browser; a source example does not prove the starter, repository plugin copy, release archive, or running instance uses it.
6. Treat every accepted source, documentation, example, workflow, quality, or skill modification as unreleased until the complete quality gate passes, `main` is pushed, the rolling GitHub Release succeeds for that exact commit, and freshly downloaded Release assets pass checksum plus extracted-archive smoke verification. Do not report a change as delivered merely because local tests passed or Actions started.

## Invariants

- A task becomes terminal only after the executor confirms its process owner ended.
- Commands, paths, labels, mutex keys, plugin snapshots, explicit inputs and host-allocated values freeze in the enqueue transaction. The scheduler never edits task parameters after submission.
- Browser presentation never substitutes for server authorization.
- Do not publish or mutate external systems unless the user separately authorizes it.
- Search equivalent implementations, examples, starter files and packaging inputs together. Add a failure mutant that removes the required surface so an older receipt cannot silently remain valid.

For API work, use `localflow-api`. For plugin work, use `localflow-plugin-development`. For deployment or live-process work, use `localflow-operations`.
