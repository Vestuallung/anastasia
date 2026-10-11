from __future__ import annotations

import math
import os
import struct
import wave
from pathlib import Path

import pytest

from karaoke_studio.models import utc_now
from karaoke_studio.project_io import create_project, save_project
from karaoke_studio.service import align_project, import_project_assets, prepare_project


def _write_generated_vowel(path: Path, seconds: float = 5.0) -> None:
    sample_rate = 16_000
    frame_count = round(seconds * sample_rate)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for index in range(frame_count):
            time = index / sample_rate
            envelope = min(1.0, time * 5, (seconds - time) * 5)
            sample = envelope * (
                0.55 * math.sin(2 * math.pi * 220 * time)
                + 0.25 * math.sin(2 * math.pi * 440 * time)
                + 0.12 * math.sin(2 * math.pi * 660 * time)
            )
            output.writeframesraw(struct.pack("<h", round(18_000 * sample)))


@pytest.mark.model
@pytest.mark.skipif(
    os.environ.get("KARAOKE_MODEL_INTEGRATION") != "1",
    reason="requires the separately licensed model and dedicated Yohane runtime",
)
def test_fixed_model_aligns_generated_media(tmp_path: Path) -> None:
    project_dir = tmp_path / "generated-model-project"
    lyrics = tmp_path / "lyrics.txt"
    audio = tmp_path / "generated-vowel.wav"
    lyrics.write_text("あ《あ》\n", encoding="utf-8")
    _write_generated_vowel(audio)

    create_project(project_dir, "generated model integration")
    project = import_project_assets(project_dir, lyrics_path=lyrics, audio_path=audio)
    project.model.license_accepted_at = utc_now()
    save_project(project_dir, project)
    prepare_project(project_dir)
    aligned, cache_hit = align_project(project_dir, allow_download=True)

    assert not cache_hit
    assert aligned.raw_alignment is not None
    assert aligned.raw_alignment.model_revision == aligned.model.revision
    assert aligned.raw_alignment.adapter_version.endswith(
        "@git:5d10abefb5b63c902c162cdda0640274418ae8d7"
    )
    assert aligned.model.resolved_snapshot
    assert aligned.model.checksums
