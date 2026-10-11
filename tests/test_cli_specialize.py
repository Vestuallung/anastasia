from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from karaoke_studio.cli import app


def test_specialize_writes_formal_job_without_alignment(tmp_path: Path) -> None:
    source_ass = tmp_path / "existing.ass"
    video = tmp_path / "video.mp4"
    output_dir = tmp_path / "out"
    source_ass.write_text("[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n", encoding="utf-8")
    video.write_bytes(b"placeholder")

    result = CliRunner().invoke(
        app,
        [
            "specialize",
            str(source_ass),
            str(video),
            "--trim-start",
            "0:30",
            "--trim-end",
            "5:52",
            "--theme",
            "hinatazaka46",
            "--title-text",
            "既存轨迹",
            "--pad-to-1080p",
            "--output-dir",
            str(output_dir),
            "--write-job-only",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads((output_dir / "specialize-job.json").read_text(encoding="utf-8"))
    assert payload["source_ass"] == str(source_ass)
    assert payload["audio_end"] == 322.0
    assert payload["theme"] == "hinatazaka46"
    assert payload["media"]["trim_start"] == "0:30"
    assert payload["media"]["trim_end"] == "5:52"
    assert payload["media"]["pad_to_1080p"] is True
