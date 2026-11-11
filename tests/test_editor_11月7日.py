import json
import struct
import wave
from pathlib import Path

from conftest import StubAnalyzer
from fastapi.testclient import TestClient

from karaoke_studio.api import create_app
from karaoke_studio.editor_11月7日 import edit_text, scene
from karaoke_studio.lyrics import build_line
from karaoke_studio.models import RawAlignedLine
from karaoke_studio.project_io import load_project, save_project


def test_scene_directly_maps_kanji_to_all_moras(tmp_path, aligned_project):
    line = build_line("来《らい》", 0, analyzer=StubAnalyzer({}))
    aligned_project.lines = [line]
    aligned_project.raw_alignment.lines = [
        RawAlignedLine(
            line_id=line.id, start_ms=1000, end_ms=1300, k_values_cs=[10, 20], labels=["ra", "i"]
        )
    ]
    aligned_project.audio.duration_ms = 3000
    save_project(tmp_path, aligned_project)
    glyph = scene(tmp_path)["lines"][0]["glyphs"][0]
    assert glyph["text"] == "来" and glyph["mora_indices"] == [0, 1]
    assert glyph["start_ms"] == 1000 and glyph["end_ms"] == 1300
    assert [k["text"] for k in glyph["kana"]] == ["ら", "い"]
    client = TestClient(create_app(tmp_path))
    response = client.post(
        f"/api/lines/{line.id}/timing",
        json={"boundaries_ms": [1000, 1150, 1300], "kind": "boundary", "boundary_index": 1},
    )
    assert response.status_code == 200
    next_glyph = response.json()["editor"]["lines"][0]["glyphs"][0]
    assert next_glyph["kana"][0]["end_ms"] == 1150
    assert next_glyph["end_ms"] == 1300
    assert load_project(tmp_path).timing_patches[-1].after_ms == [1000, 1150, 1300]


def test_text_preview_is_transient_and_commit_saves_structured_data(tmp_path, aligned_project):
    aligned_project.alignment_stale = False
    aligned_project.audio.duration_ms = 3000
    save_project(tmp_path, aligned_project)
    line_id = aligned_project.lines[0].id
    preview = edit_text(tmp_path, line_id, "愛《あい》", False)
    assert preview["lines"][0]["glyphs"][0]["text"] == "愛"
    assert load_project(tmp_path).lines[0].original == "あい"
    edit_text(tmp_path, line_id, "愛《あい》", True)
    saved = load_project(tmp_path)
    assert saved.lines[0].original == "愛《あい》" and not saved.alignment_stale
    edit_text(tmp_path, line_id, "あいう", True)
    changed = load_project(tmp_path)
    assert changed.alignment_stale and len(changed.lines[0].moras) == 3
    assert len(changed.raw_alignment.lines[0].k_values_cs) == 3
    assert (tmp_path / ".karaoke-work/editor-original-alignment.json").is_file()


def test_scene_route_never_serializes_ass(tmp_path, aligned_project, monkeypatch):
    import karaoke_studio.api as api

    aligned_project.audio.duration_ms = 3000
    save_project(tmp_path, aligned_project)
    monkeypatch.setattr(
        api, "export_ass", lambda *_: (_ for _ in ()).throw(AssertionError("ASS preview requested"))
    )
    result = TestClient(create_app(tmp_path)).get("/api/project")
    assert result.status_code == 200 and result.json()["editor"]["lines"]


def test_waveform_range_retains_detail_and_last_sample(tmp_path):
    from karaoke_studio.audio import waveform_peaks

    audio = tmp_path / "range.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(1000)
        output.writeframes(struct.pack("<2001h", *([0] * 1000 + [8192] * 1000 + [32767])))
    assert waveform_peaks(audio, 30, start_ms=0, end_ms=1000) == [0] * 30
    latter = waveform_peaks(audio, 30, start_ms=1000, end_ms=2001)
    assert len(latter) <= 30 and latter[0] == 0.25 and latter[-1] == 1


def test_settings_preview_never_writes_or_starts_media_job(tmp_path, aligned_project, monkeypatch):
    import karaoke_studio.render_job as renderer

    save_project(tmp_path, aligned_project)
    monkeypatch.setattr(
        renderer,
        "run_render_job",
        lambda *_: (_ for _ in ()).throw(AssertionError("render started")),
    )
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/editor/settings/preview",
        json={
            "title_text": "Preview title",
            "theme": "hinatazaka46",
            "layout": {"top_y": 700},
            "media": {"blackout": [{"x": 0, "y": 950, "width": 1920, "height": 130, "start": 0}]},
        },
    )
    assert response.status_code == 200
    assert response.json()["title_text"] == "Preview title"
    assert response.json()["lines"][0]["glyphs"][0]["y"] == 700
    assert not (tmp_path / "render-job.json").exists()
    saved = client.post(
        "/api/editor/settings", json={"title_text": "Saved title", "theme": "hinatazaka46"}
    )
    assert saved.status_code == 200
    assert saved.json()["editor"]["theme"] == "hinatazaka46"
    assert json.loads((tmp_path / "render-job.json").read_text())["title_text"] == "Saved title"


def test_editor_preferences_persist_across_sessions_and_recover_backup(tmp_path, aligned_project):
    save_project(tmp_path, aligned_project)
    client = TestClient(create_app(tmp_path))
    prefs = client.get("/api/project").json()["editor_preferences"]
    prefs.update(playback_speed=1.25, snap_ms=50, show_readings=False, preserve_pitch=False)
    assert client.post("/api/editor/preferences", json=prefs).status_code == 200
    reopened = TestClient(create_app(tmp_path)).get("/api/project").json()
    assert reopened["editor_preferences"] == prefs
    assert not (tmp_path / "render-job.json").exists()
    assert client.post("/api/editor/preferences", json={**prefs, "snap_ms": 0}).status_code == 422
    assert client.post("/api/editor/preferences", json={**prefs, "snap_ms": 20}).status_code == 200
    path = tmp_path / ".karaoke-work/EditorPreferences-11月7日.json"
    path.write_text("interrupted settings")
    assert client.get("/api/project").json()["editor_preferences"] == prefs


def test_display_edit_keeps_translation_paired_without_changing_original(tmp_path, aligned_project):
    from karaoke_studio.editor_11月7日 import save_settings, settings

    save_project(tmp_path, aligned_project)
    original = tmp_path / "original-translation.json"
    original.write_text(
        json.dumps(
            {"schema_version": 1, "lines": [{"index": 0, "source_text": "あい", "text": "爱"}]}
        )
    )
    save_settings(tmp_path, {"translation": {"file": str(original)}})
    edit_text(tmp_path, aligned_project.lines[0].id, "愛《あい》", True)
    paired = Path(settings(tmp_path)["translation"]["file"])
    assert paired.name == "EditorTranslation-11月7日.json"
    assert json.loads(paired.read_text())["lines"][0]["source_text"] == "愛"
    assert json.loads(paired.read_text())["lines"][0]["text"] == "爱"
    assert json.loads(original.read_text())["lines"][0]["source_text"] == "あい"


def test_editor_export_uses_current_timings_and_fresh_render(
    tmp_path, aligned_project, monkeypatch
):
    from types import SimpleNamespace

    import karaoke_studio.render_job as renderer
    from karaoke_studio.ass import export_ass

    save_project(tmp_path, aligned_project)
    line = aligned_project.lines[0]
    before = load_project(tmp_path)
    # Use the same persisted patch route as the timeline.
    captured = []

    def render(job):
        captured.append(job)
        assert job.source_ass.read_text() == export_ass(load_project(tmp_path))
        assert job.reuse_outputs is False
        return SimpleNamespace(
            media=SimpleNamespace(
                outputs={
                    "on_vocal_karaoke": SimpleNamespace(path=tmp_path / "on_vocal_karaoke.mp4")
                }
            )
        )

    monkeypatch.setattr(renderer, "run_render_job", render)
    with TestClient(create_app(tmp_path)) as client:
        from karaoke_studio.timing import effective_boundaries

        bounds = [value + 100 for value in effective_boundaries(before, line.id)]
        assert (
            client.post(
                f"/api/lines/{line.id}/timing", json={"boundaries_ms": bounds, "kind": "line_shift"}
            ).status_code
            == 200
        )
        result = client.post("/api/jobs/render")
        assert result.status_code == 200
        job_id = result.json()["job_id"]
        assert "completed" in client.get(f"/api/jobs/{job_id}/events").text
        assert (
            client.get(f"/api/jobs/{job_id}/result")
            .json()["files"]["on_vocal_karaoke"]
            .endswith(".mp4")
        )
    assert len(captured) == 1
