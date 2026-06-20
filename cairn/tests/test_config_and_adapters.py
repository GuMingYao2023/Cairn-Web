from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from cairn.dispatcher.config import DispatchConfig, WorkerConfig, load_runtime_dispatch_config, validate_prompt_resources
from cairn.dispatcher.workers.adapters.codex import CodexDriver
from cairn.dispatcher.workers.adapters.pi import PiDriver
from cairn.server import db

from conftest import make_config


def _write_config(path, config: DispatchConfig) -> None:
    path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")


def _insert_mock_worker(name: str, *, enabled: bool = True, task_types: list[str] | None = None, env: dict[str, str] | None = None) -> None:
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO workers (id, name, type, task_types, max_running, priority, enabled, env, created_at, updated_at)
               VALUES (?, ?, 'mock', ?, 1, 0, ?, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')""",
            (
                f"worker-{name}",
                name,
                json.dumps(task_types or ["reason"]),
                int(enabled),
                json.dumps(env or {}),
            ),
        )


def test_runtime_dispatch_config_uses_yaml_workers_when_db_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_db_path", None)
    db.configure(tmp_path / "cairn.db")
    config_path = tmp_path / "dispatch.json"
    _write_config(config_path, make_config())

    config = load_runtime_dispatch_config(config_path)

    assert [worker.name for worker in config.workers] == ["test-worker"]


def test_runtime_dispatch_config_merges_db_and_config_workers(tmp_path, monkeypatch) -> None:
    """DB enabled workers override same-name config workers; config-only workers are kept."""
    monkeypatch.setattr(db, "_db_path", None)
    db.configure(tmp_path / "cairn.db")
    config_path = tmp_path / "dispatch.json"
    _write_config(config_path, make_config())
    _insert_mock_worker("enabled", enabled=True)
    _insert_mock_worker("disabled", enabled=False)

    config = load_runtime_dispatch_config(config_path)

    # "enabled" from DB + "test-worker" from config (not in DB)
    names = {worker.name for worker in config.workers}
    assert "enabled" in names
    assert "test-worker" in names
    assert "disabled" not in names


def test_runtime_dispatch_config_falls_back_to_config_when_db_workers_disabled(tmp_path, monkeypatch) -> None:
    """When all DB workers are disabled, config workers are still loaded."""
    monkeypatch.setattr(db, "_db_path", None)
    db.configure(tmp_path / "cairn.db")
    config_path = tmp_path / "dispatch.json"
    _write_config(config_path, make_config())
    _insert_mock_worker("disabled", enabled=False)

    config = load_runtime_dispatch_config(config_path)

    # Falls back to config workers since DB has no enabled workers
    assert [worker.name for worker in config.workers] == ["test-worker"]


def test_runtime_dispatch_config_validates_db_workers(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_db_path", None)
    db.configure(tmp_path / "cairn.db")
    config_path = tmp_path / "dispatch.json"
    _write_config(config_path, make_config())
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO workers (id, name, type, task_types, max_running, priority, enabled, env, created_at, updated_at)
               VALUES ('worker-bad', 'bad', 'claudecode', '[\"reason\"]', 1, 0, 1, '{}', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"""
        )

    with pytest.raises(ValidationError, match="missing env keys"):
        load_runtime_dispatch_config(config_path)
def test_dispatch_config_merges_common_env_with_worker_override() -> None:
    payload = make_config().model_dump()
    payload["common_env"] = {"SHARED": "common", "OVERRIDE": "common"}
    payload["workers"][0]["env"] = {"OVERRIDE": "worker"}

    config = DispatchConfig.model_validate(payload)

    assert config.workers[0].env["SHARED"] == "common"
    assert config.workers[0].env["OVERRIDE"] == "worker"


def test_dispatch_config_defaults_worker_healthcheck_and_rejects_unknown_mode() -> None:
    payload = make_config().model_dump()
    payload["runtime"].pop("worker_healthcheck")

    assert DispatchConfig.model_validate(payload).runtime.worker_healthcheck == "startup_only"

    payload["runtime"]["worker_healthcheck"] = "sometimes"
    with pytest.raises(ValidationError):
        DispatchConfig.model_validate(payload)


def test_dispatch_config_rejects_duplicate_workers_and_excess_project_parallelism() -> None:
    payload = make_config().model_dump()
    payload["workers"].append(dict(payload["workers"][0]))
    with pytest.raises(ValidationError, match="worker names must be unique"):
        DispatchConfig.model_validate(payload)

    payload = make_config().model_dump()
    payload["runtime"]["max_project_workers"] = 3
    with pytest.raises(ValidationError, match="max_project_workers cannot exceed max_workers"):
        DispatchConfig.model_validate(payload)


def test_pi_worker_rejects_invalid_context_window() -> None:
    with pytest.raises(ValidationError, match="PI_MODEL_CONTEXT_WINDOW must be greater than 0"):
        WorkerConfig.model_validate(
            {
                "name": "pi",
                "type": "pi",
                "task_types": ["explore"],
                "max_running": 1,
                "priority": 0,
                "env": {
                    "PI_MODEL": "model",
                    "PI_BASE_URL": "http://api",
                    "PI_API_KEY": "secret",
                    "PI_PROVIDER_API": "openai-completions",
                    "PI_MODEL_CONTEXT_WINDOW": "0",
                },
            }
        )


def test_mock_worker_rejects_unknown_phase_configuration() -> None:
    with pytest.raises(ValidationError, match="unsupported mock env keys"):
        WorkerConfig.model_validate(
            {
                "name": "mock",
                "type": "mock",
                "task_types": ["explore"],
                "max_running": 1,
                "priority": 0,
                "env": {"MOCK_UNKNOWN": "{}"},
            }
        )


def test_bundled_prompt_groups_have_required_placeholders() -> None:
    validate_prompt_resources("default")
    validate_prompt_resources("mock")


def test_pi_driver_models_json_and_execute_argv_include_context_window_and_tools() -> None:
    worker = WorkerConfig.model_validate(
        {
            "name": "pi-worker",
            "type": "pi",
            "task_types": ["explore"],
            "max_running": 1,
            "priority": 0,
            "env": {
                "PI_MODEL": "model",
                "PI_BASE_URL": "http://api",
                "PI_API_KEY": "secret",
                "PI_PROVIDER_API": "openai-completions",
                "PI_MODEL_CONTEXT_WINDOW": "131072",
            },
        }
    )

    result = PiDriver().build_execute(worker, "prompt", None)
    models = json.loads(result.argv[5])

    assert models["providers"]["cairn"]["models"][0]["contextWindow"] == 131072
    assert "--tools" in result.argv
    assert result.argv[-2:] == ["-p", "prompt"]


def test_codex_driver_execute_argv_passes_model_endpoint_and_prompt() -> None:
    worker = WorkerConfig.model_validate(
        {
            "name": "codex",
            "type": "codex",
            "task_types": ["reason"],
            "max_running": 1,
            "priority": 0,
            "env": {
                "CODEX_MODEL": "gpt-test",
                "CODEX_BASE_URL": "http://api/v1",
                "OPENAI_API_KEY": "secret",
            },
        }
    )

    argv = CodexDriver().build_execute(worker, "prompt", None).argv

    assert "--model" in argv
    assert "gpt-test" in argv
    assert 'model_providers.cairn.base_url="http://api/v1"' in argv
    assert argv[-2:] == ["--", "prompt"]
