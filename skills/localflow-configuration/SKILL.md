---
name: localflow-configuration
description: Create, diagnose, compose, move, or run LocalFlow YAML, TOML, and JSON configuration files without bypassing plugin validation.
---

# LocalFlow configuration

Read `../../docs/configuration.md`. Inspect the single matching example under `../../config/` or `../../examples/` instead of inventing a second schema.

Production packages contain only `command/hello-world.yaml` and `verification/demo.yaml`. `config.yaml` is a startup-only file beside the executable; it is not part of the dynamic configuration API or the Tasks-page run workbench. Resolve relative paths against the LocalFlow root and use the inspection endpoint before running path-sensitive configurations.

## Classification

- No common task field: generic data.
- Any common task field: validate the complete common contract.
- `plugin` present: also validate plugin existence and plugin-specific fields.
- Invalid or partial task configuration remains visible but cannot run.

Use the supported configlib include syntax for shared values. The selected plugin comes from the merged configuration, not separate UI or client state. Prefer a string `command`; it has Ubuntu non-login `/bin/sh -c` semantics. Use a string list only when exact argv without shell parsing is required.

Verification commands are arbitrary user commands. `${case}`, `${seed}` and `${run}` are optional variables: use any subset or none, and never require placeholders or append guessed flags. A Make example may use `make all CASE=${case} SEED=${seed}`, while another valid command is simply `make all`. The task output records the final expanded command before process output.

## Progressive working-directory disclosure

Treat `working_directory` as execution state, not helper text. Resolve a relative value against the LocalFlow root once, freeze the absolute result in the task, and pass that same value through the subprocess `cwd`, systemd `WorkingDirectory`, and PTY supervisor `chdir` boundaries. String commands use a non-login shell so profile scripts cannot silently change the inherited directory.

Disclose path evidence progressively: the run inspection shows the resolved directory before submission; the task log records the frozen directory and final command before process output; deeper diagnosis inspects the task snapshot, systemd unit and filesystem only when the visible values disagree with effects. Prove behavior with relative `mkdir`/file side effects in an external project and assert both that the target appears there and that no same-name artifact appears in the LocalFlow root. A printed `pwd`, successful `make`, or configured field alone is not proof.

When changing a file through the API, preserve its version token. When editing directly, use an atomic save so the watcher never consumes a half-written document.

The collapsible run panel inside the Tasks page manages both `config/` and trusted `plugins/`. It supports directories, rename/move, copy/cut/paste and external edits. A root, directory or file may be a symbolic link: edit follows the target, while move/copy/delete preserves link identity. Never replace a symlink with a regular file. Lexical API paths remain under `config/` or `plugins/`; an external target is authorized only by an owner-created link.
