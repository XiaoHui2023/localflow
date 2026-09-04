# Release quality gates

Use this topic only when changing test infrastructure, publishing, or diagnosing a Release. Everyday source work should stay on focused local tests and the relevant feature contract.

## Environment ownership

- Windows development runs deterministic Python tests, static analysis, the frontend build, quality-trace mutants, and current locally installed browsers. These are fast feedback, not Linux evidence.
- The browser runner replaces `frontend/dist` while building. Run API/Python tests that mount that directory only after the browser runner finishes; those gates are not safe to parallelize across the build boundary.
- A fresh GitHub-hosted Ubuntu VM owns Linux-only acceptance. Inside it, a privileged systemd test container owns PID 1, user-manager, PTY and cgroup behavior; an Ubuntu 16.04 container owns the glibc 2.23 PyInstaller and StaticX lineage.
- The final StaticX artifact, not source Python, owns legacy CPU, current Ubuntu Chrome/Firefox, fixed Chrome 84/Firefox 78, frozen task, shutdown and extracted-bundle claims.
- A broken or stale local Docker Desktop is an environment incident. Do not repair it merely to reproduce checks already owned by a fresh hosted runner, and never convert its failure into product evidence.
- A partial local browser pass may be retained as fast feedback, but it is not a complete receipt. Only the hosted final-binary matrix may close fixed Chrome/Firefox claims when the local Docker owner is unavailable.

## Producer and consumer boundary

The build job must finish all source, systemd, browser, compatibility, frozen and archive checks before uploading artifacts. It then generates GitHub build-provenance attestations for the exact binary, archive and checksum file. The publish job may move the rolling version tag and replace assets only after that producer gate passes.

Publication is not acceptance. A separate fresh job must:

1. resolve the remote tag through lightweight or annotated tag objects and require the triggering full commit SHA;
2. read Release asset names, sizes and API SHA-256 digests and compare them with the build artifact;
3. download every public asset into a new directory with bounded retry;
4. verify `SHA256SUMS`, build provenance attestations and exact asset inventory;
5. reject absolute paths, traversal, duplicate roots, devices and links before archive extraction;
6. run the complete frozen smoke from the extracted bundle root;
7. retain a receipt containing tag SHA, `updated_at`, asset hashes and workflow run.

For a rolling Release, `published_at` is its original creation time and normally remains old. Determine freshness from the remote tag SHA, Release `updated_at`, asset timestamps/digests and the consumer receipt. Always fetch tags or query the remote directly; a stale local tag is not remote evidence.

## Failure interpretation

- A source test failure belongs to the feature owner.
- A hosted Linux target failure blocks the Linux claim even when Windows passes.
- A publish failure means no new delivery.
- A consumer failure means the upload cannot be called delivered, even if the publish job is green.
- Network and registry operations use bounded retries. After exhaustion, report the exact external failure and preserve the last verified layer; do not weaken a gate or reuse checkout `dist/` as downloaded evidence.
- Repository `tools/` is intentionally not a runtime package. Tests for a standalone tool load its absolute file path with `importlib.util`; do not rely on the Windows `pytest` launcher placing the checkout root on `sys.path`, and do not add `PYTHONPATH` in CI to hide that boundary.
- Process output can become readable before the task service commits its terminal state. Tests that exercise terminal history must use a bounded wait on the task API's authoritative final state before asserting that late writes are rejected; an output marker is not a lifecycle barrier.
- Python's `tarfile.data_filter` intentionally ignores directory modes. A consumer extractor for this release must retain its path/link/device/ownership protections, then restore only sanitized directory rwx bits (`mode & 0755`); otherwise the valid `secrets/` entry is silently widened from `0700` to the process umask default and the downloaded bundle cannot start. Assert both the archive entry and the freshly extracted filesystem mode.
- A consumer receipt is complete only after it records the downloaded bundle's frozen smoke result. Merely writing metadata before launch, or relying on the publish job's success, is not execution evidence.
