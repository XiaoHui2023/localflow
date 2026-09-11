# Scheduler capacity and performance

## Decision boundary

“Every task is independent” means task IDs, snapshots, logs, PTYs, state transitions, signals and production cgroups do not alias. It cannot mean unlimited jobs receive unlimited CPU, RAM and I/O from finite hardware. Never implement unbounded launch as a substitute for capacity planning: Linux PSI explicitly treats CPU, memory and I/O contention as a source of latency, throughput loss and OOM risk.

Default `execution.max_concurrency` to `auto`. Resolve the effective value from the process CPU affinity, cgroup v2 `cpu.max` quota and host logical CPU count, taking the smallest applicable positive value. This uses every CPU actually granted to the LocalFlow service without mistaking host CPUs outside a container/service allocation for usable capacity. Allow an explicit `1..4096` override for measured I/O-heavy workloads or task-internal parallelism. Return both configured and effective values from the status API.

Do not apply implicit CPU, memory or I/O limits to task units. An independent systemd unit/cgroup is the lifecycle and attribution boundary; site policy can add resource control only through an explicit future contract. CPU-heavy tasks normally use one task slot per available CPU. If each job invokes `make -jN`, MPI or another threaded solver, operators must account for that nested parallelism when overriding the task count.

## Large-queue scheduler

Never use an API presentation cap as the scheduler truth cap. Active task enumeration must cover at least the full configured concurrency, and shutdown enumeration must cover the full supported active population. Queue selection uses a bounded advancing cursor:

1. Build held mutex ownership from all active tasks.
2. Scan at most `max(500, capacity * 4)`, capped at 10,000, oldest queued tasks per tick.
3. Mark overlapping mutex tasks blocked and continue scanning instead of treating the prefix as the queue.
4. Persist the last actually inspected `(created_at, id)`, not the last fetched row; otherwise filling capacity skips unexamined tasks.
5. Wrap to the beginning after reaching the end so a newly unblocked old task eventually runs.

Shutdown must drain interruptible records page by page. Raising a storage limit is not enough: a controller may have more queued records than one page even though its running population is bounded. Recovery must enumerate the full supported persisted active population rather than the new configured concurrency, because an operator may lower capacity between controller runs.

Do not couple terminal-task retention capacity to concurrent execution capacity. A total retained-log budget governs deletion of terminal task logs; active logs may temporarily exceed it and remain protected by the per-task file cap. Treating `concurrency * per-task cap` as a configuration validity rule creates an artificial server-throughput ceiling.

Dates passed back into SQLite cursors must use ISO text, not a Python datetime adapter whose space separator changes lexical ordering against stored `T` timestamps.

## Performance audit matrix

| Owner | Measure | Failure boundary |
| --- | --- | --- |
| Scheduler/SQLite | enqueue and two bounded scans through >500 blocked tasks; later independent task starts | starvation, scan >3 s or enqueue fixture >15 s on CI |
| Controller | process-tree RSS, CPU over an idle six-second window, background requests | versioned `quality/resource-budgets.json` |
| Browser | JS heap, task duration, DOM/listener counts, sockets; terminal→tasks next paint | versioned browser receipt, no hidden terminal socket |
| Initial web load | gzip size of the built legacy entry; deferred-editor fetch timing | <=0.3 MiB entry, Monaco absent before edit and present after edit |
| Terminal/log | in-memory xterm window and server search chunk/result cap | never load an entire 1 GB log |
| Production executor | one transient unit/cgroup per task, complete group stop and recovery | systemd target tests and frozen smoke |
| User workload | CPU, memory and I/O pressure | observe with cgroup accounting/PSI; do not misattribute to controller |

Every performance claim must name its owner and workload. A fast idle controller does not prove high-throughput scheduling; a scheduler unit test does not prove target-server solver throughput. Preserve separate evidence and disclose the boundary.

Treat mature heavyweight components as route/surface-scoped resources. Monaco remains the correct editor, but importing its editor API, language contributions and workers from the application bootstrap made every task-list visitor pay the cost. Keep them in one lazy `MonacoEditors` module loaded by editing/conflict surfaces. The quality gate must independently gzip the final `index-legacy-*` asset and verify browser Resource Timing before and after editor activation; a Vite size warning alone is discovery, not closure.

## Sources checked 2026-09-11

- Linux cgroup v2 resource distribution and limits: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
- Linux Pressure Stall Information: https://docs.kernel.org/accounting/psi.html
- Python CPU affinity API: https://docs.python.org/3/library/os.html#os.sched_getaffinity
- systemd resource control: https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html

Find Skills searches for batch scheduler resource-aware concurrency and systemd cgroup isolation found generic scheduler/systemd candidates. None included LocalFlow's SQLite state transitions, mutex cursor, frozen binary cleanup and fixed-browser evidence, so no external Skill or dependency was installed; the official kernel/systemd/Python contracts and project-specific gates are stronger for this scope.
