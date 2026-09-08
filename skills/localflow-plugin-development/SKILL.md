---
name: localflow-plugin-development
description: Develop and validate trusted Python plugins for LocalFlow, including schemas, run controls, discovery hooks, task expansion, statuses, stopping, and API examples.
---

# LocalFlow plugin development

Read `../../docs/plugins.md` and `../../plugins/README.md`. Start from the closest existing plugin in `../../plugins/`; do not fork the host UI for one plugin.

## Contract

- Register one plugin with the provided decorator.
- Declare a configuration model, a strict input model matching the finite `run_fields` schema, status definitions, and one API example that expands successfully. Use `extra="forbid"` only for a genuinely closed configuration vocabulary; use `extra="allow"` when site/simulator fields or command-interpolation values are an intentional extension surface. The host schema must preserve that declared extra policy.
- Discovery returns data; it does not render components. The host owns controls, accessibility, layout, and responsive behavior.
- Optional `inspect(values, context)` returns read-only values and diagnostics; the host owns the compact component and tooltip. Keep inspection bounded, side-effect free and valid for both web and API callers.
- Keep editor syntax/import diagnosis separate from plugin diagnosis. Saving an ordinary configuration file never requires the plugin schema to pass. The plugin run surface owns resolved-value review and runnable errors.
- Inspection must show every consequential resolved value, including command, working directory, case/simulation paths, labels, mutex keys, configured output/log paths and operator-facing custom text. Check only inputs that must already exist. Do not reject or warn merely because an output or log file is expected to be created by the forthcoming run. Repeated operator text is a list of independent copy targets: preview every item, freeze resolved values into each task, and preserve them when result evaluation replaces calculated fields.
- Expansion returns independent `TaskCreate` records. When a value must be unique across requests or restarts, return `TaskDraft` with a host-owned `DeferredValue`; never edit a queued task or allocate a global sequence inside the plugin. Use mutex keys for scheduling, not display tags alone.
- Prefer string commands in examples and configuration; LocalFlow gives them Ubuntu shell semantics. Accept exact argv lists for callers that must bypass the shell. Stable commands belong in configuration and normally do not appear in `run_fields`.
- Result evaluation must use final authoritative output, include only files that exist, and return plugin-defined status keys. Keep internal calculation inputs under underscore-prefixed custom keys.
- A stop strategy is bounded and replayable. It may send signals, terminal input, or a fixed command, but terminal state still waits for executor confirmation.

Run the plugin tests and at least one real finite or interruptible example before handing it off.

## Composing verification configuration

For AI-authored verification configuration, fetch `/api/v1/plugins/verification` and start from `api.example`; validate configuration and inputs against their separate JSON Schemas instead of inventing field names. Keep stable command, directory, labels, mutex and log templates in configuration. Put selected cases, per-case counts and an optional seed in run inputs. `${case}`, `${seed}` and `${run}` may be combined anywhere in command and log templates. Call the plan endpoint before submission, then submit once with an idempotency key. The public error status is exactly `ERROR`; counts remain parser evidence and never enter the label or calculated detail.
