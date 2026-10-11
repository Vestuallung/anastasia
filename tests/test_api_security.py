from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from karaoke_studio.api import create_app
from karaoke_studio.ass import export_ass
from karaoke_studio.project_io import create_project, load_project, save_project


def test_api_requires_session_token_and_loopback_origin(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    create_project(project_dir, "API security")
    client = TestClient(create_app(project_dir, token="test-token"))

    assert client.get("/api/project").status_code == 401
    assert client.get("/api/project", headers={"x-karaoke-token": "wrong"}).status_code == 401
    assert (
        client.get(
            "/api/project",
            headers={"x-karaoke-token": "test-token", "origin": "https://evil.example"},
        ).status_code
        == 403
    )

    response = client.get(
        "/api/project",
        headers={"x-karaoke-token": "test-token", "origin": "http://127.0.0.1:8765"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "API security"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-embedder-policy"] == "require-corp"


def test_local_web_app_does_not_require_a_visible_token(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    create_project(project_dir, "Tokenless local app")
    client = TestClient(create_app(project_dir))

    response = client.get(
        "/api/project",
        headers={"origin": "http://127.0.0.1:8765"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Tokenless local app"


def test_api_accepts_token_query_for_sse_compatible_clients(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    create_project(project_dir, "SSE token")
    client = TestClient(create_app(project_dir, token="event-token"))

    response = client.get(
        "/api/project?token=event-token",
        headers={"origin": "http://localhost:5173"},
    )

    assert response.status_code == 200


def test_api_import_and_explicit_model_license_acceptance(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    create_project(project_dir, "Browser import")
    client = TestClient(create_app(project_dir, token="workflow-token"))
    headers = {"x-karaoke-token": "workflow-token", "origin": "http://localhost:5173"}

    imported = client.post(
        "/api/import",
        headers=headers,
        files={
            "lyrics": ("lyrics.txt", "あい\n", "text/plain"),
            "video": ("preview.mp4", b"preview-video", "video/mp4"),
        },
        data={"legacy_parentheses": "false", "preserve_ass_timing": "false"},
    )

    assert imported.status_code == 200
    assert imported.json()["lines"][0]["original"] == "あい"
    assert imported.json()["source"]["video_path"] == "source/video.mp4"
    preview_video = client.get("/api/video", headers=headers)
    assert preview_video.status_code == 200
    assert preview_video.content == b"preview-video"
    rejected = client.post("/api/model/accept-license", headers=headers, data={"accepted": "false"})
    accepted = client.post("/api/model/accept-license", headers=headers, data={"accepted": "true"})
    assert rejected.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["license"] == "CC-BY-NC-SA-4.0"

    project = load_project(project_dir)
    project.alignment_stale = False
    save_project(project_dir, project)
    exported = client.get("/api/export.ass", headers=headers)
    assert exported.status_code == 200
    assert exported.text == export_ass(load_project(project_dir))

    font = client.get("/font/NotoSansCJKjp-Regular.otf")
    assert font.status_code == 200
    assert font.content.startswith(b"OTTO")
