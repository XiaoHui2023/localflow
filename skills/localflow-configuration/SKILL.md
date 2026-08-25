---
name: localflow-configuration
description: Create, diagnose, compose, move, or run LocalFlow YAML, TOML, and JSON configuration files without bypassing plugin validation.
---

# LocalFlow configuration

Read `../../docs/configuration.md`. Inspect the single matching example under `../../config/` or `../../examples/` instead of inventing a second schema.

## Classification

- No common task field: generic data.
- Any common task field: validate the complete common contract.
- `plugin` present: also validate plugin existence and plugin-specific fields.
- Invalid or partial task configuration remains visible but cannot run.

Use the supported configlib include syntax for shared values. Keep the complete include graph inside the configuration root. The selected plugin comes from the merged configuration, not separate UI or client state.

When changing a file through the API, preserve its version token. When editing directly, use an atomic save so the watcher never consumes a half-written document.
