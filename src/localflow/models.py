from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


CommandInput = str | list[str]


def normalize_command(value: CommandInput) -> list[str]:
    """Normalize the public command contract to the executor's argv contract.

    A string intentionally has Ubuntu shell semantics.  A list remains exact argv,
    which is useful when callers need to bypass shell parsing.
    """
    if isinstance(value, str):
        if not value.strip() or "\x00" in value:
            raise ValueError("command must be non-empty and contain no NUL")
        return ["/bin/sh", "-c", value]
    if not value or any(not isinstance(item, str) or not item or "\x00" in item for item in value):
        raise ValueError("command arguments must be non-empty strings and contain no NUL")
    return value


class TaskState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


TERMINAL_STATES = {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED, TaskState.LOST}


class TaskStatus(BaseModel):
    key: str
    label: str
    tone: str = "neutral"
    finished: bool = False


class StopAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["signal", "input", "exec"]
    signal: Literal["SIGINT", "SIGTERM"] | None = None
    data: str | None = Field(default=None, max_length=4096)
    command: list[str] | None = Field(default=None, min_length=1, max_length=64)
    timeout_seconds: float = Field(default=10, ge=0, le=86400)
    output_contains: str | None = Field(default=None, min_length=1, max_length=512)
    label: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def action_matches_type(self) -> StopAction:
        populated = sum(value is not None for value in (self.signal, self.data, self.command))
        if populated != 1:
            raise ValueError("stop action requires exactly one signal, data, or command")
        if self.type == "signal" and self.signal is None:
            raise ValueError("signal stop action requires signal")
        if self.type == "input" and self.data is None:
            raise ValueError("input stop action requires data")
        if self.type == "exec" and self.command is None:
            raise ValueError("exec stop action requires command")
        if self.data is not None and ("\x00" in self.data or len(self.data.encode()) > 4096):
            raise ValueError("stop input must be at most 4096 bytes and contain no NUL")
        if self.command and any(not item or "\x00" in item for item in self.command):
            raise ValueError("stop command arguments must be non-empty and contain no NUL")
        return self


class StopStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[StopAction] = Field(min_length=1, max_length=8)


COMMON_CONFIG_FIELDS = frozenset(
    {
        "plugin",
        "name",
        "working_directory",
        "command",
        "labels",
        "mutex_keys",
        "custom",
        "stop",
        "variables",
        "project",
    }
)


class CommonConfigFields(BaseModel):
    """Typed fields shared by file, browser and inline API configurations."""

    model_config = ConfigDict(extra="ignore")

    plugin: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    working_directory: str | None = Field(default=None, min_length=1)
    command: CommandInput | None = None
    labels: list[str] | None = Field(default=None, max_length=64)
    mutex_keys: list[str] | None = Field(default=None, max_length=32)
    custom: dict[str, Any] | None = None
    stop: StopStrategy | None = None
    variables: dict[str, Any] | None = None
    project: str | None = Field(default=None, min_length=1)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: CommandInput | None) -> CommandInput | None:
        if value is not None:
            normalize_command(value)
        return value

    @field_validator("labels", "mutex_keys")
    @classmethod
    def validate_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 128 for item in normalized):
            raise ValueError("items must be 1..128 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("items must be unique")
        return normalized


class TaskCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "smoke-case-a",
                    "working_directory": "/srv/project-a",
                    "command": "bash run.sh --case case_a",
                    "labels": ["smoke", "project-a"],
                    "mutex_keys": ["license:sim-a"],
                    "custom": {"report_path": "/srv/reports/case_a/index.html"},
                }
            ]
        },
    )
    name: str = Field(min_length=1, max_length=200)
    working_directory: str = Field(min_length=1)
    command: list[str]
    labels: list[str] = Field(default_factory=list, max_length=64)
    mutex_keys: list[str] = Field(default_factory=list, max_length=32)
    custom: dict[str, Any] = Field(default_factory=dict)
    template: str | None = None
    plugin_snapshot: dict[str, Any] = Field(default_factory=dict)
    stop: StopStrategy | None = None

    @field_validator("command", mode="before")
    @classmethod
    def non_empty_arguments(cls, value: CommandInput) -> list[str]:
        return normalize_command(value)

    @field_validator("labels", "mutex_keys")
    @classmethod
    def normalized_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 128 for item in normalized):
            raise ValueError("items must be 1..128 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("items must be unique")
        return normalized


class DeferredValue(BaseModel):
    """A host-owned value that is allocated before a task becomes visible."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["monotonic_unix"]
    namespace: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


class TaskDraft(TaskCreate):
    """Plugin plan output; the store resolves deferred values in the enqueue transaction."""

    deferred_values: dict[str, DeferredValue] = Field(default_factory=dict, max_length=32)

    @field_validator("deferred_values")
    @classmethod
    def valid_deferred_names(
        cls, value: dict[str, DeferredValue]
    ) -> dict[str, DeferredValue]:
        for name in value:
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", name) is None:
                raise ValueError("deferred value names must be valid variable names")
        return value


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
    status: TaskStatus


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


class RunCreate(BaseModel):
    """One-request plugin run using the same document contract as config files."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "configuration": {
                    "plugin": "verification",
                    "name": "smoke",
                    "case_directory": "cases",
                    "working_directory": ".",
                    "command": "python3 scripts/simulate.py --case ${case}",
                },
                "inputs": {"cases": ["smoke"], "case_runs": {"smoke": 2}},
            }
        },
    )
    configuration: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)
