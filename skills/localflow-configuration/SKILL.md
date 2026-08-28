---
name: localflow-configuration
description: Create, diagnose, compose, move, or run LocalFlow YAML, TOML, and JSON configuration files without bypassing plugin validation.
---

# LocalFlow configuration

Read `../../docs/configuration.md`. Inspect the single matching example under `../../config/` or `../../examples/` instead of inventing a second schema.

Production packages contain only `command/hello-world.yaml` and `verification/demo.yaml`. `config.yaml` is a startup-only file beside the executable; it is not part of the dynamic configuration API or Run page. Resolve relative paths against the LocalFlow root and use the inspection endpoint before running path-sensitive configurations.

## Classification

- No common task field: generic data.
- Any common task field: validate the complete common contract.
- `plugin` present: also validate plugin existence and plugin-specific fields.
- Invalid or partial task configuration remains visible but cannot run.

Use the supported configlib include syntax for shared values. The selected plugin comes from the merged configuration, not separate UI or client state. Prefer a string `command`; it has Ubuntu `/bin/sh -lc` semantics. Use a string list only when exact argv without shell parsing is required.

When changing a file through the API, preserve its version token. When editing directly, use an atomic save so the watcher never consumes a half-written document.

The Run page manages both `config/` and trusted `plugins/`. It supports directories, rename/move, copy/cut/paste and external edits. A root, directory or file may be a symbolic link: edit follows the target, while move/copy/delete preserves link identity. Never replace a symlink with a regular file. Lexical API paths remain under `config/` or `plugins/`; an external target is authorized only by an owner-created link.
