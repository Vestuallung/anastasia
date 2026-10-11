from __future__ import annotations

import json
from pathlib import Path

import pytest

from karaoke_studio.derived_ass import (
    Canvas,
    DerivedAssError,
    generate_derived_ass,
    generate_translation_variants,
)
from karaoke_studio.themes import THEMES


def _source(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[Script Info]",
                "PlayResX: 1920",
                "PlayResY: 1080",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                r"Dialogue: 0,0:00:01.00,0:00:03.00,K1,,0,0,0,karaoke,{\k100}日|<ひ{\k100}常|<び",
                r"Dialogue: 0,0:00:04.00,0:00:05.00,K1,,0,0,0,karaoke,{\k100}空",
            ]
        ),
        encoding="utf-8",
    )


def test_translation_inherits_source_times_and_generates_two_variants(tmp_path: Path) -> None:
    source, karaoke = tmp_path / "source.ass", tmp_path / "karaoke.ass"
    _source(source)
    generate_derived_ass(
        source,
        karaoke,
        title_text="",
        audio_end=8,
        theme=THEMES["hinatazaka46"],
    )
    sidecar = tmp_path / "zh.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "language": "zh-Hans",
                "lines": [
                    {"index": 0, "source_text": "日常", "text": "日常生活"},
                    {"index": 1, "source_text": "空", "text": ""},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    combined, only = tmp_path / "combined.ass", tmp_path / "only.ass"

    report = generate_translation_variants(
        source,
        karaoke,
        sidecar,
        combined_output=combined,
        zh_only_output=only,
        theme=THEMES["hinatazaka46"],
        canvas=Canvas(),
    )

    assert report.lines == 1
    for output in (combined, only):
        text = output.read_text(encoding="utf-8")
        assert "Dialogue: 10,0:00:01.00,0:00:03.00,ChineseGlow" in text
        assert "Dialogue: 11,0:00:01.00,0:00:03.00,ChineseText" in text
        assert "\\fad(160,160)" in text
        assert "日常生活" in text
        assert "0:00:04.00,0:00:05.00,Chinese" not in text
    assert "Style: Outline" in combined.read_text(encoding="utf-8")
    assert "Style: Outline" not in only.read_text(encoding="utf-8")


def test_translation_rejects_source_text_mismatch(tmp_path: Path) -> None:
    source, karaoke = tmp_path / "source.ass", tmp_path / "karaoke.ass"
    _source(source)
    generate_derived_ass(
        source,
        karaoke,
        title_text="",
        audio_end=8,
        theme=THEMES["nogizaka46"],
    )
    sidecar = tmp_path / "zh.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "language": "zh-Hans",
                "lines": [
                    {"index": 0, "source_text": "错误", "text": "x"},
                    {"index": 1, "source_text": "空", "text": "y"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(DerivedAssError, match="source_text 不匹配"):
        generate_translation_variants(
            source,
            karaoke,
            sidecar,
            combined_output=tmp_path / "combined.ass",
            zh_only_output=tmp_path / "only.ass",
            theme=THEMES["nogizaka46"],
            canvas=Canvas(),
        )
