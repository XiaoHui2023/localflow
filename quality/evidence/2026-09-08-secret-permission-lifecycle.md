# 2026-09-08 secret permission lifecycle evidence

## Contract

- A newly created `secrets` directory uses mode `0700` on POSIX.
- A newly created web or API key uses mode `0600` on POSIX.
- Existing secret permissions are operator-owned state. Startup does not audit, repair, reject, or regenerate because those modes changed.
- Required API-key content rotation preserves the existing file mode. Recreating a missing key uses the secure initial mode.

## Direct oracle

`tests_target/test_secret_permissions.py` changes the directory and both key modes after initial creation, reconstructs the root and authentication manager, and compares both modes and bytes. It separately deletes one key to distinguish first creation from an ordinary restart, and verifies rotation changes only API-key content while retaining the operator-selected mode.

## Failure mutants

- Restore `AuthManager.check_permissions()` on startup.
- Apply `chmod` to an existing secrets directory during root initialization.
- Rewrite an existing key during startup.
- Reset the API key to `0600` during normal terminal-task rotation.
- Create a missing key without applying `0600`.

## Verification

- `python -m ruff check src/localflow tests_v2 tests_target tools/check_quality.py tools/run_browser_quality.py tools/run_linux_browser_quality.py tools/run_frozen_smoke.py`: passed.
- `python -m pytest -q`: passed on Windows after the current frontend build completed.
- `python tools/check_quality.py`: passed with 57 metrics covering 148 requirements.
- `npm --prefix frontend run build`: passed; `npm --prefix frontend audit`: 0 vulnerabilities.
- Python 3.12 Linux container: `pytest -q tests_target/test_secret_permissions.py tests_v2/test_security.py`: 22 passed.

The first full Windows run was intentionally discarded because it overlapped `vite build`, whose clean-build phase temporarily removes `frontend/dist/assets`. The project release contract now explicitly requires these two gates to run across a build boundary rather than concurrently; the serial rerun above is the authoritative result.
