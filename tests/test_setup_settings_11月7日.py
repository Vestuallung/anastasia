from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from karaoke_studio.config import load_config
from karaoke_studio.setup_11月7日 import (
    SettingsEdit,
    SetupRequest,
    SetupTasks,
    _toml,
    application_settings_router,
    atomic_json,
    editable_settings,
    save_application_settings,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("KARAOKE_HOME", str(tmp_path))
    monkeypatch.delenv("KARAOKE_CONFIG", raising=False)
    load_config.cache_clear()
    yield
    load_config.cache_clear()


def test_settings_roundtrip_unicode_and_custom_group(tmp_path):
    initial = editable_settings()
    initial["model_id"] = "example/custom-model"
    initial["model_revision"] = "main"
    initial["model_cache"] = "模型目录"
    initial["groups"]["emerald"] = {"label": "≠ME", "sung": "#00B379"}
    initial["default_theme"] = "emerald"
    initial["chinese_font_path"] = 'fonts/a "quoted" file.otf'
    target = save_application_settings(SettingsEdit(**initial), tmp_path / "Settings-11月7日.toml")
    assert target.is_file()
    current = editable_settings()
    assert current["default_theme"] == "emerald"
    assert current["model_cache"] == "模型目录"
    assert current["chinese_font_path"] == initial["chinese_font_path"]
    assert load_config()["model"]["url"] == "https://huggingface.co/example/custom-model"
    assert load_config()["encoder"]["video_codec"] == "libx264"
    save_application_settings(SettingsEdit(**current), target)
    assert target.with_suffix(".toml.bak").is_file()


def test_settings_reject_invalid_group_without_writing(tmp_path):
    value = editable_settings()
    value["groups"]["test"] = {"label": "Test", "sung": "#ZZZZZZ"}
    with pytest.raises(ValueError, match="六位色号"):
        SettingsEdit(**value)
    assert not list(tmp_path.glob("*.toml"))


def test_setup_task_state_survives_restart(tmp_path):
    tasks = SetupTasks(tmp_path, tmp_path)
    task_id = "a" * 32
    path = tasks._path(task_id)
    atomic_json(
        path, {"id": task_id, "status": "completed", "created_at": "2026-11-07", "message": "done"}
    )
    atomic_json(path.with_suffix(".pid.json"), {"pid": 99999999})
    restored = SetupTasks(tmp_path, tmp_path)
    assert len(restored.list()) == 1
    assert restored.list()[0]["status"] == "completed"


def test_dead_setup_worker_becomes_interrupted(tmp_path):
    tasks = SetupTasks(tmp_path, tmp_path)
    task_id = "b" * 32
    atomic_json(
        tasks._path(task_id),
        {"id": task_id, "status": "running", "pid": 99999999, "created_at": "2026-11-07"},
    )
    assert tasks.get(task_id)["status"] == "interrupted"


def test_model_download_requires_explicit_acceptance(tmp_path):
    tasks = SetupTasks(tmp_path, tmp_path)
    with pytest.raises(ValueError, match="模型页面"):
        tasks.start(SetupRequest(action="model"))
    assert tasks.list() == []


def test_setup_spawn_failure_is_persisted(tmp_path, monkeypatch):
    import karaoke_studio.setup_11月7日 as setup

    def fail(*args, **kwargs):
        raise OSError("test launch failed")

    monkeypatch.setattr(setup.subprocess, "Popen", fail)
    tasks = SetupTasks(tmp_path, tmp_path)
    task = tasks.start(SetupRequest(action="environment"))
    assert task["status"] == "failed"
    assert tasks.get(task["id"])["message"] == "test launch failed"


def test_settings_api_saves_and_reports_status(tmp_path, monkeypatch):
    import karaoke_studio.setup_11月7日 as setup

    monkeypatch.setattr(setup, "environment_status", lambda: {"alignment": {"model_ready": False}})
    app = FastAPI()
    app.include_router(application_settings_router(tmp_path, tmp_path))
    client = TestClient(app)
    value = client.get("/api/application/settings").json()["settings"]
    value["device"] = "cpu"
    result = client.post("/api/application/settings", json=value)
    assert result.status_code == 200
    assert result.json()["restart_required"]
    assert client.get("/api/application/status").json()["alignment"]["model_ready"] is False
    assert client.post("/api/application/setup", json={"action": "model"}).status_code == 409


def test_toml_serialization_preserves_special_characters():
    import tomllib

    value = {
        "groups": {"custom.key": {"label": "乃木坂46\n中文", "sung": "#00B379"}},
        "flags": {"yes": True, "list": ["a", "b"], "float": 0.5},
    }
    assert tomllib.loads(_toml(value)) == value
