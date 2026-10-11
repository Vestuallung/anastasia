from __future__ import annotations

from collections.abc import Iterable

import pytest

from karaoke_studio.lyrics import build_line
from karaoke_studio.models import KaraokeProject, RawAlignedLine, RawAlignment


class StubAnalyzer:
    """Deterministic MeCab stand-in that also records which spans were analyzed."""

    def __init__(self, readings: dict[str, list[tuple[str, str]]]) -> None:
        self.readings = readings
        self.calls: list[str] = []

    def words(self, text: str) -> list[tuple[str, str]]:
        self.calls.append(text)
        return self.readings[text]


@pytest.fixture
def aligned_project() -> KaraokeProject:
    analyzer = StubAnalyzer({"あい": [("あい", "アイ")]})
    line = build_line("あい", 0, analyzer=analyzer)
    project = KaraokeProject(project_id="project-test", title="Test", lines=[line])
    project.audio.prepared_sha256 = "a" * 64
    project.raw_alignment = RawAlignment(
        cache_key="raw-cache",
        adapter_version="test",
        model_id=project.model.model_id,
        model_revision=project.model.revision,
        audio_sha256=project.audio.prepared_sha256,
        normalized_romaji_sha256="b" * 64,
        lines=[
            RawAlignedLine(
                line_id=line.id,
                start_ms=1000,
                end_ms=1300,
                k_values_cs=[10, 20],
            )
        ],
    )
    return project


def reading_map(items: Iterable[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    pairs = list(items)
    return {"".join(surface for surface, _ in pairs): pairs}
