import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from karaoke_studio.gui_worker_11月7日 import run
from karaoke_studio.project_io import save_project
from karaoke_studio.workspace_11月7日 import ProductionInput, Workspace, create_workspace_app


class FakeProcess:
    pid = 987654

    def __init__(self, *args, **kwargs):
        self.code = None

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        self.code = -15
        return self.code


def assets(root: Path):
    video, lyrics = root / "video.mp4", root / "lyrics.txt"
    video.write_bytes(b"untouched video")
    lyrics.write_text("あ\n")
    return dict(title="Song", artist="日向坂46", video=str(video), lyrics=str(lyrics))


def test_library_opens_existing_project_with_scoped_editor_api(tmp_path, aligned_project):
    project = tmp_path / "existing"
    save_project(project, aligned_project)
    app = create_workspace_app(tmp_path / "library")
    client = TestClient(app)
    assert client.get("/api/workspace").json()["projects"] == []
    opened = client.post("/api/workspace/open", json={"path": str(project)})
    assert opened.status_code == 200
    url = opened.json()["url"]
    assert client.get(url + "api/project").json()["project_id"] == aligned_project.project_id
    assert client.get(url + "api/workspace").json()["mode"] == "project"
    assert client.get("/font/NotoSansJP.ttf").headers["content-type"] == "font/ttf"
    reopened = TestClient(create_workspace_app(tmp_path / "library")).get("/api/workspace").json()
    assert reopened["projects"][0]["url"] == url


def test_prepare_job_preserves_export_choices_and_persists_completion(tmp_path, monkeypatch):
    import karaoke_studio.gui_worker_11月7日 as worker
    import karaoke_studio.workspace_11月7日 as module

    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    captured = {}

    def produce(video, lyrics, title, **options):
        captured.update(options)
        options["on_event"]("整曲对齐", "completed")
        return options["project_dir"], SimpleNamespace(media=None), {}

    monkeypatch.setattr(worker, "produce_project", produce)
    workspace = Workspace(tmp_path / "library")
    state = workspace.start(ProductionInput(**assets(tmp_path)))
    assert state["fresh"] is True
    assert run(Path(state["request_file"])) == 0
    result = workspace.job(state["id"])
    assert result["status"] == "completed" and result["files"] == {}
    assert captured["prepare_only"] is True and captured["outputs"] == ["on_vocal_karaoke"]
    assert captured["title_text"] == "Song/日向坂46"
    assert Workspace(tmp_path / "library").job(state["id"])["status"] == "completed"
    assert (tmp_path / "video.mp4").read_bytes() == b"untouched video"


def test_retry_defaults_to_fresh_and_supports_explicit_recovery(tmp_path, monkeypatch):
    import karaoke_studio.workspace_11月7日 as module

    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    app = create_workspace_app(tmp_path / "library")
    client = TestClient(app)
    started = client.post("/api/workspace/produce", json=assets(tmp_path)).json()
    path = app.state.workspace.job_file(started["id"])
    state = json.loads(path.read_text())
    state.update(status="failed", message="interrupted")
    path.write_text(json.dumps(state))
    retry = client.post(f"/api/workspace/jobs/{started['id']}/retry", json={})
    assert retry.status_code == 200 and retry.json()["fresh"] is True
    new_id = retry.json()["id"]
    state["id"] = new_id
    app.state.workspace.job_file(new_id).write_text(
        json.dumps({**retry.json(), "status": "failed"})
    )
    recovered = client.post(f"/api/workspace/jobs/{new_id}/retry", json={"fresh": False})
    assert recovered.status_code == 200 and recovered.json()["fresh"] is False
    assert recovered.json()["project_path"] == started["project_path"]


def test_job_failure_is_persisted_with_useful_error(tmp_path, monkeypatch):
    import karaoke_studio.gui_worker_11月7日 as worker
    import karaoke_studio.workspace_11月7日 as module

    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(
        worker,
        "produce_project",
        lambda *_args, **_kw: (_ for _ in ()).throw(ValueError("请选择正确的音轨")),
    )
    workspace = Workspace(tmp_path / "library")
    state = workspace.start(ProductionInput(**assets(tmp_path)))
    assert run(Path(state["request_file"])) == 1
    assert workspace.job(state["id"])["message"] == "请选择正确的音轨"
    assert workspace.job(state["id"])["status"] == "failed"


def test_bilingual_and_variant_validation(tmp_path):
    values = assets(tmp_path)
    with pytest.raises(ValueError, match="中日版"):
        ProductionInput(**values, outputs=["on_vocal_karaoke_zh"]).resolved()
    Path(values["lyrics"]).write_text("日文：あ\n中文：啊\n")
    assert ProductionInput(**values, outputs=["on_vocal_karaoke_zh"]).resolved().lyrics.is_file()
    with pytest.raises(ValueError, match="伴奏版"):
        ProductionInput(**values, outputs=["off_vocal_karaoke"]).resolved()
    with pytest.raises(ValueError, match="结束时间"):
        ProductionInput(**values, trim_start="1:00", trim_end="00:10")
