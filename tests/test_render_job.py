from __future__ import annotations

import json
from pathlib import Path

import pytest

import karaoke_studio.render_job as render_job_module
from karaoke_studio.derived_ass import Canvas, DerivedAssReport, TranslationAssReport
from karaoke_studio.media_render import (
    MediaRenderError,
    MediaRenderReport,
    RenderedFile,
    parse_media_time,
)
from karaoke_studio.render_job import (
    MediaSettings,
    RenderJob,
    TranslationSettings,
    load_render_job,
    run_render_job,
)


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("15", 15), ("01:23", 83), ("2:38:00", 9480), (4.5, 4.5)],
)
def test_parse_media_time(value: str | float, seconds: float) -> None:
    assert parse_media_time(value) == seconds


def test_parse_media_time_rejects_negative() -> None:
    with pytest.raises(MediaRenderError):
        parse_media_time("-1")


def test_render_job_resolves_all_relative_media_paths(tmp_path: Path) -> None:
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {
                "source_ass": "source.ass",
                "output_ass": "derived.ass",
                "theme": "keyakizaka46",
                "title_text": "曲/欅坂46",
                "audio_end": 100,
                "media": {
                    "mode": "matched_external",
                    "video": "video.mp4",
                    "external_audio": "off.mp3",
                    "match_reference_audio": "original.m4a",
                    "trim_start": "1:23",
                    "trim_end": "5:00",
                    "on_vocal_output": "on.mp4",
                    "off_vocal_output": "off.mp4",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    job = load_render_job(path)

    assert job.source_ass == tmp_path / "source.ass"
    assert job.output_ass == tmp_path / "derived.ass"
    assert job.media is not None
    assert job.media.video == tmp_path / "video.mp4"
    assert job.media.external_audio == tmp_path / "off.mp3"
    assert job.media.match_reference_audio == tmp_path / "original.m4a"
    assert job.media.on_vocal_output == tmp_path / "on.mp4"
    assert job.media.off_vocal_output == tmp_path / "off.mp4"


@pytest.mark.parametrize(
    ("with_off", "with_translation", "expected"),
    [
        (False, False, ("on_vocal_karaoke",)),
        (True, False, ("on_vocal_karaoke", "off_vocal_karaoke")),
        (
            False,
            True,
            ("on_vocal_karaoke", "on_vocal_karaoke_zh", "on_vocal_zh_only"),
        ),
        (
            True,
            True,
            (
                "on_vocal_karaoke",
                "off_vocal_karaoke",
                "on_vocal_karaoke_zh",
                "on_vocal_zh_only",
            ),
        ),
    ],
)
def test_default_output_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_off: bool,
    with_translation: bool,
    expected: tuple[str, ...],
) -> None:
    source = tmp_path / "source.ass"
    source.write_text("stub", encoding="utf-8")
    output_ass = tmp_path / "derived.ass"
    media = MediaSettings(
        video=tmp_path / "video.mp4",
        external_audio=tmp_path / "off.mp3" if with_off else None,
        mode="matched_external" if with_off else "on_vocal",
        trim_end=10,
        output_dir=tmp_path,
    )
    translation = TranslationSettings(file=tmp_path / "zh.json") if with_translation else None
    job = RenderJob(
        source_ass=source,
        output_ass=output_ass,
        theme="nogizaka46",
        audio_end=10,
        media=media,
        translation=translation,
    )
    monkeypatch.setattr(render_job_module, "_canvas", lambda _: Canvas())
    monkeypatch.setattr(
        render_job_module,
        "generate_derived_ass",
        lambda *args, **kwargs: DerivedAssReport(1, 1, 0, 100, 80, output_ass),
    )
    monkeypatch.setattr(
        render_job_module,
        "generate_translation_variants",
        lambda *args, **kwargs: TranslationAssReport(
            1, 100, tmp_path / "derived_zh.ass", tmp_path / "derived_zh_only.ass"
        ),
    )

    def fake_render_outputs(**kwargs: object) -> MediaRenderReport:
        paths = kwargs["output_paths"]
        assert isinstance(paths, dict)
        return MediaRenderReport({name: RenderedFile(path, 0) for name, path in paths.items()})

    monkeypatch.setattr(render_job_module, "render_outputs", fake_render_outputs)

    report = run_render_job(job)

    assert report.requested_outputs == expected
    assert report.media is not None
    assert tuple(report.media.outputs) == expected


def test_explicit_output_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_ass = tmp_path / "derived.ass"
    job = RenderJob(
        source_ass=tmp_path / "source.ass",
        output_ass=output_ass,
        theme="hinatazaka46",
        audio_end=10,
        translation=TranslationSettings(file=tmp_path / "zh.json"),
        media=MediaSettings(video=tmp_path / "video.mp4", trim_end=10),
        outputs=["on_vocal_zh_only"],
    )
    monkeypatch.setattr(render_job_module, "_canvas", lambda _: Canvas())
    monkeypatch.setattr(
        render_job_module,
        "generate_derived_ass",
        lambda *args, **kwargs: DerivedAssReport(1, 1, 0, 100, 80, output_ass),
    )
    monkeypatch.setattr(
        render_job_module,
        "generate_translation_variants",
        lambda *args, **kwargs: TranslationAssReport(
            1, 100, tmp_path / "derived_zh.ass", tmp_path / "derived_zh_only.ass"
        ),
    )
    monkeypatch.setattr(
        render_job_module,
        "render_outputs",
        lambda **kwargs: MediaRenderReport(
            {name: RenderedFile(path, 0) for name, path in kwargs["output_paths"].items()}
        ),
    )

    report = run_render_job(job)

    assert report.requested_outputs == ("on_vocal_zh_only",)
    assert report.media is not None
    assert tuple(report.media.outputs) == ("on_vocal_zh_only",)
