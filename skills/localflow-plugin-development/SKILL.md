---
name: localflow-plugin-development
description: Develop and validate trusted Python plugins for LocalFlow, including schemas, run controls, discovery hooks, task expansion, statuses, stopping, and API examples.
---

# LocalFlow plugin development

Read `../../docs/plugins.md` and `../../plugins/README.md`. Start from the closest existing plugin in `../../plugins/`; do not fork the host UI for one plugin.

## Contract

- Register one plugin with the provided decorator.
- Declare a strict configuration model, a finite `run_fields` schema, status definitions, and one API example that expands successfully.
- Discovery returns data; it does not render components. The host owns controls, accessibility, layout, and responsive behavior.
- Optional `inspect(values, context)` returns read-only values and diagnostics; the host owns the compact component and tooltip. Keep inspection bounded, side-effect free and valid for both web and API callers.
- Expansion returns independent `TaskCreate` records. Use mutex keys for scheduling, not display tags alone.
- Prefer string commands in examples and configuration; LocalFlow gives them Ubuntu shell semantics. Accept exact argv lists for callers that must bypass the shell. Stable commands belong in configuration and normally do not appear in `run_fields`.
- Result evaluation must use final authoritative output, include only files that exist, and return plugin-defined status keys. Keep internal calculation inputs under underscore-prefixed custom keys.
- A stop strategy is bounded and replayable. It may send signals, terminal input, or a fixed command, but terminal state still waits for executor confirmation.

Run the plugin tests and at least one real finite or interruptible example before handing it off.

## Composing verification configuration

For AI-authored verification configuration, fetch the plugin description and start from `api.example.configuration`; validate the result against `api.configuration_schema` instead of inventing field names. Keep stable command, directory, labels, mutex and log templates in configuration. Put selected cases, per-case counts and an optional seed in run inputs. `${case}`, `${seed}` and `${run}` may be combined anywhere in command and log templates. Reject unknown fields, then run diagnosis and one finite example. The public error status is exactly `ERROR`; counts remain parser evidence and never enter the label or calculated detail.
