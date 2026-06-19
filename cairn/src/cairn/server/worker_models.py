from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


TaskType = Literal["reason", "explore", "bootstrap"]
WorkerType = Literal["claudecode", "codex", "pi", "mock"]

WORKER_ENV_KEYS: dict[WorkerType, tuple[str, ...]] = {
    "claudecode": ("ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"),
    "codex": ("CODEX_MODEL", "CODEX_BASE_URL", "OPENAI_API_KEY"),
    "pi": ("PI_MODEL", "PI_BASE_URL", "PI_API_KEY", "PI_PROVIDER_API"),
    "mock": (),
}


class WorkerOut(BaseModel):
    id: str
    name: str
    type: WorkerType
    task_types: list[TaskType]
    max_running: int
    priority: int
    enabled: bool
    env: dict[str, str]
    created_at: str
    updated_at: str


class WorkerCreate(BaseModel):
    name: str = Field(min_length=1)
    type: WorkerType
    task_types: list[TaskType]
    max_running: int = Field(default=1, gt=0)
    priority: int = Field(default=0, ge=0)
    enabled: bool = True
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("task_types")
    @classmethod
    def validate_task_types(cls, value: list[TaskType]) -> list[TaskType]:
        if not value:
            raise ValueError("task_types must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("task_types must be unique")
        return value

    @field_validator("env")
    @classmethod
    def validate_env(cls, value: dict[str, str], info) -> dict[str, str]:
        # info.data may not have 'type' yet if Pydantic validates in field order;
        # we rely on the router to check env completeness after full validation.
        return value


class WorkerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    type: WorkerType | None = None
    task_types: list[TaskType] | None = None
    max_running: int | None = Field(default=None, gt=0)
    priority: int | None = Field(default=None, ge=0)
    enabled: bool | None = None
    env: dict[str, str] | None = None

    @field_validator("task_types")
    @classmethod
    def validate_task_types(cls, value: list[TaskType] | None) -> list[TaskType] | None:
        if value is not None:
            if not value:
                raise ValueError("task_types must not be empty")
            if len(set(value)) != len(value):
                raise ValueError("task_types must be unique")
        return value


class WorkerEnabledUpdate(BaseModel):
    enabled: bool


class TestConnectionRequest(BaseModel):
    type: WorkerType
    env: dict[str, str] = Field(default_factory=dict)


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
