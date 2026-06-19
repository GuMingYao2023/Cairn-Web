from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from cairn.server.db import get_conn
from cairn.server.services import next_worker_id, utcnow
from cairn.server.worker_models import (
    WORKER_ENV_KEYS,
    WorkerCreate,
    WorkerOut,
    WorkerUpdate,
    TestConnectionRequest,
    TestConnectionResponse,
)
from cairn.server.worker_test_connection import test_worker_connection

router = APIRouter(tags=["workers"])


def _worker_from_row(row: dict) -> WorkerOut:
    return WorkerOut(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        task_types=json.loads(row["task_types"]),
        max_running=row["max_running"],
        priority=row["priority"],
        env=json.loads(row["env"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/workers", response_model=list[WorkerOut])
def list_workers():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workers ORDER BY created_at").fetchall()
        return [_worker_from_row(r) for r in rows]


@router.post("/workers", response_model=WorkerOut, status_code=201)
def create_worker(body: WorkerCreate):
    _validate_env_completeness(body.type, body.env)

    with get_conn() as conn:
        wid = next_worker_id(conn)
        now = utcnow()
        try:
            conn.execute(
                """INSERT INTO workers (id, name, type, task_types, max_running, priority, env, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    wid,
                    body.name.strip(),
                    body.type,
                    json.dumps(body.task_types),
                    body.max_running,
                    body.priority,
                    json.dumps(body.env),
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"Worker '{body.name}' already exists")
        row = conn.execute("SELECT * FROM workers WHERE id = ?", (wid,)).fetchone()
        return _worker_from_row(row)


@router.put("/workers/{worker_id}", response_model=WorkerOut)
def update_worker(worker_id: str, body: WorkerUpdate):
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, "Worker not found")

        updates: dict[str, str | int | list[str]] = {}
        if body.name is not None:
            updates["name"] = body.name.strip()
        if body.type is not None:
            updates["type"] = body.type
        if body.task_types is not None:
            updates["task_types"] = json.dumps(body.task_types)
        if body.max_running is not None:
            updates["max_running"] = body.max_running
        if body.priority is not None:
            updates["priority"] = body.priority
        if body.env is not None:
            updates["env"] = json.dumps(body.env)

        if not updates:
            raise HTTPException(400, "No fields to update")

        # Validate env completeness if type changed or env changed
        effective_type = body.type if body.type is not None else existing["type"]
        effective_env = body.env if body.env is not None else json.loads(existing["env"])
        _validate_env_completeness(effective_type, effective_env)

        updates["updated_at"] = utcnow()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [worker_id]

        try:
            conn.execute(f"UPDATE workers SET {set_clause} WHERE id = ?", values)
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"Worker name '{updates.get('name', '')}' already exists")

        row = conn.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
        return _worker_from_row(row)


@router.delete("/workers/{worker_id}", status_code=204)
def delete_worker(worker_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Worker not found")
        conn.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
    return Response(status_code=204)


@router.post("/workers/test-connection", response_model=TestConnectionResponse)
def test_connection(body: TestConnectionRequest):
    if body.type == "mock":
        return TestConnectionResponse(success=True, message="Mock worker is always available")
    _validate_env_completeness(body.type, body.env)
    success, message = test_worker_connection(body.type, body.env)
    return TestConnectionResponse(success=success, message=message)


def _validate_env_completeness(worker_type: str, env: dict[str, str]) -> None:
    """Check that all required env keys are present for the given worker type."""
    required = WORKER_ENV_KEYS.get(worker_type, ())  # type: ignore[arg-type]
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise HTTPException(400, f"Missing required env keys: {', '.join(missing)}")
