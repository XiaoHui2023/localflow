from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


TERMINAL_STATES = {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED, TaskState.LOST}


class TaskCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "smoke-case-a",
                    "working_directory": "/srv/project-a",
                    "command": ["bash", "run.sh", "--case", "case_a"],
                    "labels": ["smoke", "project-a"],
                    "mutex_keys": ["license:sim-a"],
                    "custom": {"report_path": "/srv/reports/case_a/index.html"},
                }
            ]
        },
    )
    name: str = Field(min_length=1, max_length=200)
    working_directory: str = Field(min_length=1)
    command: list[str] = Field(min_length=1)
    labels: list[str] = Field(default_factory=list, max_length=64)
    mutex_keys: list[str] = Field(default_factory=list, max_length=32)
    custom: dict[str, Any] = Field(default_factory=dict)
    template: str | None = None
    plugin_snapshot: dict[str, Any] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def non_empty_arguments(cls, value: list[str]) -> list[str]:
        if any(not argument or "\x00" in argument for argument in value):
            raise ValueError("command arguments must be non-empty and contain no NUL")
        return value

    @field_validator("labels", "mutex_keys")
    @classmethod
    def normalized_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 128 for item in normalized):
            raise ValueError("items must be 1..128 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("items must be unique")
        return normalized


class TaskRecord(TaskCreate):
    id: str
    state: TaskState
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    pid: int | None = None
    executor_ref: str | None = None
    interrupt_stage: str | None = None
    blocked_by: list[str] = Field(default_factory=list)
    blocked_keys: list[str] = Field(default_factory=list)
    log_size: int = 0
    started_monotonic: float | None = None
    elapsed_seconds: float | None = None


class EventRecord(BaseModel):
    id: int
    task_id: str | None
    kind: str
    at: datetime
    data: dict[str, Any]


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str
    values: dict[str, Any] = Field(default_factory=dict)
    common: dict[str, Any] = Field(default_factory=dict)
