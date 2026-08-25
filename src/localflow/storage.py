from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    TERMINAL_STATES,
    EventRecord,
    StopStrategy,
    TaskCreate,
    TaskRecord,
    TaskState,
    TaskStatus,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, state TEXT NOT NULL, name TEXT NOT NULL, working_directory TEXT NOT NULL,
 command_json TEXT NOT NULL, labels_json TEXT NOT NULL, mutex_keys_json TEXT NOT NULL,
 custom_json TEXT NOT NULL, template TEXT, plugin_snapshot_json TEXT NOT NULL,
 stop_json TEXT,
 created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT, exit_code INTEGER, pid INTEGER,
 executor_ref TEXT, interrupt_stage TEXT, blocked_by_json TEXT NOT NULL DEFAULT '[]',
 blocked_keys_json TEXT NOT NULL DEFAULT '[]',
 log_size INTEGER NOT NULL DEFAULT 0, started_monotonic REAL, elapsed_seconds REAL
 ,status_key TEXT NOT NULL DEFAULT '', status_label TEXT NOT NULL DEFAULT '',
 status_tone TEXT NOT NULL DEFAULT 'neutral', status_finished INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tasks_state_created ON tasks(state, created_at, id);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, kind TEXT NOT NULL,
 at TEXT NOT NULL, data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_task ON events(task_id, id);
CREATE TABLE IF NOT EXISTS acknowledgements (
 task_id TEXT NOT NULL, viewer TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY(task_id, viewer)
);
CREATE TABLE IF NOT EXISTS idempotency (
 actor TEXT NOT NULL, route TEXT NOT NULL, key TEXT NOT NULL, response_json TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(actor, route, key)
);
CREATE TABLE IF NOT EXISTS nonces (
 nonce TEXT PRIMARY KEY, generation INTEGER NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS batches (
 id TEXT PRIMARY KEY, template TEXT NOT NULL, values_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batch_tasks (
 batch_id TEXT NOT NULL REFERENCES batches(id), task_id TEXT NOT NULL REFERENCES tasks(id),
 sequence INTEGER NOT NULL, PRIMARY KEY(batch_id, task_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(
        self,
        path: Path,
        database_max_bytes: int = 512 * 1024 * 1024,
        wal_max_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        page_size = int(self._db.execute("PRAGMA page_size").fetchone()[0])
        self._db.execute(f"PRAGMA max_page_count={max(database_max_bytes // page_size, 1)}")
        self._db.execute(f"PRAGMA journal_size_limit={max(wal_max_bytes, 0)}")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(SCHEMA)
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(tasks)")}
        migrations = {
            "started_monotonic": "REAL",
            "elapsed_seconds": "REAL",
            "blocked_keys_json": "TEXT NOT NULL DEFAULT '[]'",
            "status_key": "TEXT NOT NULL DEFAULT ''",
            "status_label": "TEXT NOT NULL DEFAULT ''",
            "status_tone": "TEXT NOT NULL DEFAULT 'neutral'",
            "status_finished": "INTEGER NOT NULL DEFAULT 0",
            "stop_json": "TEXT",
        }
        for column, declaration in migrations.items():
            if column not in columns:
                self._db.execute(f"ALTER TABLE tasks ADD COLUMN {column} {declaration}")

    def close(self) -> None:
        self._db.close()

    def create_task(self, task_id: str, draft: TaskCreate) -> TaskRecord:
        task_status = self._display_status(draft.plugin_snapshot, TaskState.QUEUED)
        values = (
            task_id,
            TaskState.QUEUED,
            draft.name,
            draft.working_directory,
            json.dumps(draft.command),
            json.dumps(draft.labels),
            json.dumps(draft.mutex_keys),
            json.dumps(draft.custom),
            draft.template,
            json.dumps(draft.plugin_snapshot),
            draft.stop.model_dump_json() if draft.stop else None,
            _now(),
            task_status.key,
            task_status.label,
            task_status.tone,
            int(task_status.finished),
        )
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    """INSERT INTO tasks(id,state,name,working_directory,command_json,labels_json,
                    mutex_keys_json,custom_json,template,plugin_snapshot_json,stop_json,created_at,
                    status_key,status_label,status_tone,status_finished)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    values,
                )
                self._add_event_locked(task_id, "task.queued", {"state": "queued"})
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return self.get_task(task_id)

    def create_batch(
        self,
        batch_id: str,
        template: str,
        request_values: dict[str, Any],
        tasks: list[tuple[str, TaskCreate]],
    ) -> list[TaskRecord]:
        created_at = _now()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    "INSERT INTO batches(id,template,values_json,created_at) VALUES(?,?,?,?)",
                    (batch_id, template, json.dumps(request_values), created_at),
                )
                for sequence, (task_id, draft) in enumerate(tasks):
                    task_status = self._display_status(draft.plugin_snapshot, TaskState.QUEUED)
                    self._db.execute(
                        """INSERT INTO tasks(id,state,name,working_directory,command_json,labels_json,
                        mutex_keys_json,custom_json,template,plugin_snapshot_json,stop_json,created_at,
                        status_key,status_label,status_tone,status_finished)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            task_id,
                            TaskState.QUEUED,
                            draft.name,
                            draft.working_directory,
                            json.dumps(draft.command),
                            json.dumps(draft.labels),
                            json.dumps(draft.mutex_keys),
                            json.dumps(draft.custom),
                            draft.template,
                            json.dumps(draft.plugin_snapshot),
                            draft.stop.model_dump_json() if draft.stop else None,
                            created_at,
                            task_status.key,
                            task_status.label,
                            task_status.tone,
                            int(task_status.finished),
                        ),
                    )
                    self._db.execute(
                        "INSERT INTO batch_tasks(batch_id,task_id,sequence) VALUES(?,?,?)",
                        (batch_id, task_id, sequence),
                    )
                    self._add_event_locked(
                        task_id,
                        "task.queued",
                        {"state": "queued", "batch_id": batch_id, "sequence": sequence},
                    )
                self._add_event_locked(
                    None, "batch.created", {"batch_id": batch_id, "count": len(tasks)}
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return [self.get_task(task_id) for task_id, _ in tasks]

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        batch = self._db.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if batch is None:
            raise KeyError(batch_id)
        task_rows = self._db.execute(
            "SELECT task_id FROM batch_tasks WHERE batch_id=? ORDER BY sequence", (batch_id,)
        )
        return {
            "id": batch["id"],
            "template": batch["template"],
            "values": json.loads(batch["values_json"]),
            "created_at": batch["created_at"],
            "task_ids": [row["task_id"] for row in task_rows],
        }

    def get_task(self, task_id: str) -> TaskRecord:
        row = self._db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._task(row)

    def list_tasks(
        self,
        *,
        states: Iterable[str] = (),
        labels: Iterable[str] = (),
        name: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        started_from: str | None = None,
        started_to: str | None = None,
        ended_from: str | None = None,
        ended_to: str | None = None,
        limit: int = 100,
        before: tuple[str, str] | None = None,
        ascending: bool = False,
    ) -> list[TaskRecord]:
        clauses: list[str] = []
        values: list[Any] = []
        state_values = list(states)
        if state_values:
            clauses.append(f"state IN ({','.join('?' for _ in state_values)})")
            values.extend(state_values)
        if name:
            clauses.append("name LIKE ? ESCAPE '\\'")
            escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            values.append(f"%{escaped}%")
        for label in labels:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(tasks.labels_json) WHERE json_each.value = ?)"
            )
            values.append(label)
        for column, operator, value in (
            ("created_at", ">=", created_from),
            ("created_at", "<=", created_to),
            ("started_at", ">=", started_from),
            ("started_at", "<=", started_to),
            ("ended_at", ">=", ended_from),
            ("ended_at", "<=", ended_to),
        ):
            if value is not None:
                clauses.append(f"{column} {operator} ?")
                values.append(value)
        if before:
            clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
            values.extend([before[0], before[0], before[1]])
        sql = "SELECT * FROM tasks" + ((" WHERE " + " AND ".join(clauses)) if clauses else "")
        direction = "ASC" if ascending else "DESC"
        sql += f" ORDER BY created_at {direction}, id {direction} LIMIT ?"
        values.append(min(max(limit, 1), 500))
        return [self._task(row) for row in self._db.execute(sql, values)]

    def transition(
        self,
        task_id: str,
        expected: Iterable[TaskState],
        state: TaskState,
        *,
        status_override: TaskStatus | None = None,
        **fields: Any,
    ) -> bool:
        expected_values = [item.value for item in expected]
        if not expected_values:
            return False
        row = self._db.execute(
            "SELECT plugin_snapshot_json,exit_code,interrupt_stage FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return False
        exit_code = fields.get("exit_code", row["exit_code"])
        interrupt_stage = fields.get("interrupt_stage", row["interrupt_stage"])
        task_status = status_override or self._display_status(
            json.loads(row["plugin_snapshot_json"]), state, exit_code, interrupt_stage
        )
        assignments = [
            "state=?",
            "status_key=?",
            "status_label=?",
            "status_tone=?",
            "status_finished=?",
        ]
        values: list[Any] = [
            state.value,
            task_status.key,
            task_status.label,
            task_status.tone,
            int(task_status.finished),
        ]
        allowed = {
            "started_at",
            "ended_at",
            "exit_code",
            "pid",
            "executor_ref",
            "interrupt_stage",
            "blocked_by_json",
            "log_size",
            "started_monotonic",
            "elapsed_seconds",
            "custom_json",
        }
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"unsupported task field: {key}")
            assignments.append(f"{key}=?")
            values.append(value)
        values.extend([task_id, *expected_values])
        placeholders = ",".join("?" for _ in expected_values)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                result = self._db.execute(
                    f"UPDATE tasks SET {','.join(assignments)} WHERE id=? AND state IN ({placeholders})",
                    values,
                )
                if result.rowcount:
                    self._add_event_locked(
                        task_id, f"task.{state.value}", {"state": state.value, **fields}
                    )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return bool(result.rowcount)

    def append_event(self, task_id: str | None, kind: str, data: dict[str, Any]) -> int:
        with self._lock:
            return self._add_event_locked(task_id, kind, data)

    def materialize_runtime(
        self, task_id: str, command: list[str], custom: dict[str, Any]
    ) -> bool:
        """Freeze values that intentionally become known only when a task starts."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                result = self._db.execute(
                    """UPDATE tasks SET command_json=?,custom_json=?
                       WHERE id=? AND state=?""",
                    (
                        json.dumps(command),
                        json.dumps(custom, ensure_ascii=False),
                        task_id,
                        TaskState.STARTING.value,
                    ),
                )
                if result.rowcount:
                    self._add_event_locked(task_id, "task.runtime_materialized", {})
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return bool(result.rowcount)

    def _add_event_locked(self, task_id: str | None, kind: str, data: dict[str, Any]) -> int:
        result = self._db.execute(
            "INSERT INTO events(task_id,kind,at,data_json) VALUES(?,?,?,?)",
            (task_id, kind, _now(), json.dumps(data, default=str)),
        )
        return int(result.lastrowid)

    def events_after(self, after: int, limit: int = 500) -> list[EventRecord]:
        rows = self._db.execute(
            "SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (after, limit)
        )
        return [
            EventRecord(
                id=row["id"],
                task_id=row["task_id"],
                kind=row["kind"],
                at=row["at"],
                data=json.loads(row["data_json"]),
            )
            for row in rows
        ]

    def latest_event(self, kind: str) -> EventRecord | None:
        row = self._db.execute(
            "SELECT * FROM events WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)
        ).fetchone()
        if row is None:
            return None
        return EventRecord(
            id=row["id"],
            task_id=row["task_id"],
            kind=row["kind"],
            at=row["at"],
            data=json.loads(row["data_json"]),
        )

    def acknowledge(self, task_id: str, viewer: str) -> None:
        self.get_task(task_id)
        self._db.execute(
            "INSERT OR REPLACE INTO acknowledgements(task_id,viewer,at) VALUES(?,?,?)",
            (task_id, viewer, _now()),
        )

    def is_acknowledged(self, task_id: str, viewer: str) -> bool:
        return (
            self._db.execute(
                "SELECT 1 FROM acknowledgements WHERE task_id=? AND viewer=?", (task_id, viewer)
            ).fetchone()
            is not None
        )

    def idempotency_get(self, actor: str, route: str, key: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT response_json FROM idempotency WHERE actor=? AND route=? AND key=?",
            (actor, route, key),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def idempotency_put(self, actor: str, route: str, key: str, response: dict[str, Any]) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO idempotency(actor,route,key,response_json,created_at) VALUES(?,?,?,?,?)",
            (actor, route, key, json.dumps(response), _now()),
        )

    def set_blocked_by(self, task_id: str, blockers: list[str], keys: list[str]) -> None:
        encoded = json.dumps(sorted(set(blockers)))
        encoded_keys = json.dumps(sorted(set(keys)))
        with self._lock:
            row = self._db.execute(
                """SELECT blocked_by_json,blocked_keys_json FROM tasks
                WHERE id=? AND state='queued'""",
                (task_id,),
            ).fetchone()
            if row is None or (row[0] == encoded and row[1] == encoded_keys):
                return
            self._db.execute(
                """UPDATE tasks SET blocked_by_json=?,blocked_keys_json=?
                WHERE id=? AND state='queued'""",
                (encoded, encoded_keys, task_id),
            )
            self._add_event_locked(
                task_id, "task.blocked", {"blocked_by": blockers, "blocked_keys": keys}
            )

    def snapshot_stop(self, task_id: str, strategy: StopStrategy) -> None:
        """Persist the effective default before its first action is sent."""
        with self._lock:
            self._db.execute(
                "UPDATE tasks SET stop_json=? WHERE id=? AND stop_json IS NULL",
                (strategy.model_dump_json(), task_id),
            )

    def terminal_task_ids_before(self, ended_before: str) -> list[str]:
        rows = self._db.execute(
            """SELECT id FROM tasks WHERE ended_at IS NOT NULL AND ended_at < ?
            AND state IN ('succeeded','failed','cancelled','lost')""",
            (ended_before,),
        )
        return [str(row[0]) for row in rows]

    def terminal_task_ids_oldest(self) -> list[str]:
        rows = self._db.execute(
            """SELECT id FROM tasks WHERE ended_at IS NOT NULL
            AND state IN ('succeeded','failed','cancelled','lost')
            ORDER BY ended_at ASC, id ASC"""
        )
        return [str(row[0]) for row in rows]

    def set_log_size(self, task_id: str, size: int) -> None:
        with self._lock:
            self._db.execute("UPDATE tasks SET log_size=? WHERE id=?", (max(size, 0), task_id))

    def purge_retention(
        self, *, tasks_before: str, events_before: str, idempotency_before: str
    ) -> list[str]:
        task_ids = self.terminal_task_ids_before(tasks_before)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if task_ids:
                    marks = ",".join("?" for _ in task_ids)
                    self._db.execute(
                        f"DELETE FROM acknowledgements WHERE task_id IN ({marks})", task_ids
                    )
                    self._db.execute(
                        f"DELETE FROM batch_tasks WHERE task_id IN ({marks})", task_ids
                    )
                    self._db.execute(f"DELETE FROM events WHERE task_id IN ({marks})", task_ids)
                    self._db.execute(f"DELETE FROM tasks WHERE id IN ({marks})", task_ids)
                    self._db.execute(
                        "DELETE FROM batches WHERE id NOT IN (SELECT DISTINCT batch_id FROM batch_tasks)"
                    )
                self._db.execute("DELETE FROM events WHERE at < ?", (events_before,))
                self._db.execute(
                    "DELETE FROM idempotency WHERE created_at < ?", (idempotency_before,)
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return task_ids

    @staticmethod
    def _display_status(
        snapshot: dict[str, Any],
        state: TaskState,
        exit_code: int | None = None,
        interrupt_stage: str | None = None,
    ) -> TaskStatus:
        core = {
            "queued": {"label": "等待", "tone": "neutral", "finished": False},
            "starting": {"label": "启动中", "tone": "info", "finished": False},
            "running": {"label": "运行中", "tone": "info", "finished": False},
            "stopping": {"label": "退出中", "tone": "warning", "finished": False},
            "succeeded": {"label": "完成", "tone": "success", "finished": True},
            "failed": {"label": "失败", "tone": "danger", "finished": True},
            "cancelled": {"label": "已中断", "tone": "warning", "finished": True},
            "lost": {"label": "状态丢失", "tone": "danger", "finished": True},
        }
        statuses = snapshot.get("statuses", {}) if isinstance(snapshot, dict) else {}
        lifecycle = snapshot.get("lifecycle_statuses", {}) if isinstance(snapshot, dict) else {}
        if state in {
            TaskState.QUEUED,
            TaskState.STARTING,
            TaskState.RUNNING,
            TaskState.STOPPING,
            TaskState.LOST,
        }:
            key = lifecycle.get(state.value, state.value)
        elif state == TaskState.CANCELLED or interrupt_stage:
            key = snapshot.get("interrupt_status", "cancelled")
        else:
            rules = snapshot.get("result_statuses", {}) if isinstance(snapshot, dict) else {}
            key = rules.get(str(exit_code), rules.get("default", state.value))
        definition = statuses.get(key, core.get(key, core[state.value]))
        if not isinstance(definition, dict):
            definition = core[state.value]
            key = state.value
        return TaskStatus(
            key=str(key),
            label=str(definition.get("label", key)),
            tone=str(definition.get("tone", "neutral")),
            finished=bool(definition.get("finished", state in TERMINAL_STATES)),
        )

    @staticmethod
    def _task(row: sqlite3.Row) -> TaskRecord:
        state = TaskState(row["state"])
        snapshot = json.loads(row["plugin_snapshot_json"])
        status = (
            TaskStatus(
                key=row["status_key"],
                label=row["status_label"],
                tone=row["status_tone"],
                finished=bool(row["status_finished"]),
            )
            if row["status_key"]
            else Store._display_status(snapshot, state, row["exit_code"], row["interrupt_stage"])
        )
        return TaskRecord(
            id=row["id"],
            state=state,
            name=row["name"],
            working_directory=row["working_directory"],
            command=json.loads(row["command_json"]),
            labels=json.loads(row["labels_json"]),
            mutex_keys=json.loads(row["mutex_keys_json"]),
            custom=json.loads(row["custom_json"]),
            template=row["template"],
            plugin_snapshot=snapshot,
            stop=(StopStrategy.model_validate_json(row["stop_json"]) if row["stop_json"] else None),
            created_at=row["created_at"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            exit_code=row["exit_code"],
            pid=row["pid"],
            executor_ref=row["executor_ref"],
            interrupt_stage=row["interrupt_stage"],
            blocked_by=json.loads(row["blocked_by_json"]),
            blocked_keys=json.loads(row["blocked_keys_json"]),
            log_size=row["log_size"],
            started_monotonic=row["started_monotonic"],
            elapsed_seconds=row["elapsed_seconds"],
            status=status,
        )
