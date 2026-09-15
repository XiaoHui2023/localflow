# Unlimited task admission

RQ-182 changes the default from CPU-derived task slots to no LocalFlow concurrency ceiling. Independent tasks are admitted without waiting for a slot; old generated `auto` values resolve to the same unlimited behavior, explicit integers remain available as operator-requested limits, and mutex keys remain authoritative serialization constraints.

The scheduler enumerates active mutex owners across storage pages and admits queued work in bounded pages. The page bounds one event-loop turn rather than the number of simultaneously running tasks. Status represents the default as `unlimited` rather than zero or a guessed large integer.

Verification is owned by `tests_v2/test_scheduler.py`, `tests_v2/test_retention_pagination.py`, and `tests_v2/test_security.py`. These tests distinguish default admission, legacy configuration compatibility, explicit integer limits, mutex blocking, queue-prefix fairness, cross-page shutdown/recovery, and the public status value. They do not claim that finite CPU, memory, or I/O can preserve workload performance under arbitrary load.
