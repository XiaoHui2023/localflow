# Plugin-owned Case discovery and concise CLI paths

This change removes the host-owned starter `cases/` tree. The verification plugin now owns both supported Case sources: `case_names` produces configuration-derived candidates and `case_directory` dynamically discovers one external directory level. The two sources are mutually exclusive, and the fresh-root test proves LocalFlow core does not create `cases/`.

The canonical public path options are `--workspace` and `--data`. The previous `--config-root` and `--state-dir` spellings remain hidden compatibility aliases. Tests prove canonical and legacy resolution, identical dual spelling, explicit rejection of conflicting paths, default resolution, and canonical-only help output.

Windows evidence is produced by `tests_v2/test_cli.py`, `tests_v2/test_initialize.py`, `tests_v2/test_plugins.py`, `tests_v2/test_config.py`, `tests_v2/test_tasks.py`, and `tests_v2/test_instance_paths.py`. Linux frozen/release evidence is intentionally not claimed until publication is separately authorized and the hosted producer/consumer gate succeeds.

The full `tests_v2` suite, the Edge 9-test journey, and the installed Chromium/Firefox compatibility journeys passed on 2026-09-12. The fixed Chrome 84/Firefox 78 container stage was attempted three times by the browser-quality runner but could not connect to `npipe:////./pipe/dockerDesktopLinuxEngine`; Docker Desktop was then started hidden and the engine still did not become ready. No fixed-legacy-browser claim is made from this workstation run. The hosted producer owns that final-binary claim and now also rejects any release bundle that recreates a host-level `cases/` directory.
