# Optional verification-log evidence

## Decision

`compile_logs` and `run_logs` describe optional domain evidence, not mandatory task inputs. Empty lists remain valid configuration and are absent from run inspection. Result evaluation distinguishes an unconfigured evidence source from a configured path whose expected file was not produced.

## Result matrix

| Compile configuration | Run configuration | Evidence | Result |
| --- | --- | --- | --- |
| absent | absent | none | neutral `finished` / “运行结束” |
| absent | configured but missing | none | neutral `finished`; never a compile status |
| configured | absent | existing compile files may be shown | neutral `finished`; no verification pass/fail |
| configured | configured but no run file | existing compile files only | `compile_error` |
| any | configured with a run file | authoritative run text | final UVM summary, then anchored VCS fallback |

## Gates

`tests_v2/test_plugins.py` proves both fields are optional in the public schema, exit codes 0 and nonzero cannot manufacture success/failure without run-log evidence, a missing configured run log cannot manufacture a compile phase when compilation was not configured, and existing compile detail survives a compile-only task without changing the neutral result. `tests_v2/test_feedback_20260907.py` proves the inspection API omits both empty sections. The production plugin and frozen starter source carry the same version-5 implementation.
