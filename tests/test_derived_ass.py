from __future__ import annotations

from pathlib import Path

import pytest

from karaoke_studio.derived_ass import (
    Canvas,
    OverwideError,
    UnsupportedKaraokeTagError,
    fmt_ass_time,
    generate_derived_ass,
    parse_ass_time,
)
from karaoke_studio.themes import THEMES


def write_source(path: Path, dialogues: list[tuple[str, str]]) -> None:
    events = [
        f"Dialogue: 0,{start},{fmt_ass_time(parse_ass_time(start) + 1)},K1,,0,0,0,karaoke,{text}"
        for start, text in dialogues
    ]
    path.write_text(
        "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                *events,
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_generates_theme_colors_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "source.ass"
    output = tmp_path / "derived.ass"
    write_source(source, [("0:00:01.00", r"{\k50}日|<ひ{\k50}常|<び")])
    before = source.read_bytes()

    report = generate_derived_ass(
        source,
        output,
        title_text="日常/乃木坂46",
        audio_end=12,
        theme=THEMES["nogizaka46"],
    )

    text = output.read_text(encoding="utf-8")
    assert source.read_bytes() == before
    assert report.font_size == 96
    assert report.source_dialogues == 1
    assert "&H00D84F8B&" in text
    assert "&H00000000&" in text
    assert "日常/乃木坂46" in text


@pytest.mark.parametrize("tag", [r"{\K50}", r"{\kf50}", r"{\ko50}"])
def test_rejects_every_non_k1_tag(tmp_path: Path, tag: str) -> None:
    source = tmp_path / "source.ass"
    write_source(source, [("0:00:01.00", f"{tag}日")])
    with pytest.raises(UnsupportedKaraokeTagError):
        generate_derived_ass(
            source,
            tmp_path / "out.ass",
            title_text="x/y",
            audio_end=12,
            theme=THEMES["nogizaka46"],
        )


def test_reports_all_overwide_lines_without_replacing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.ass"
    output = tmp_path / "derived.ass"
    output.write_text("previous output\n", encoding="utf-8")
    long_line = "".join(r"{\k1}漢" for _ in range(30))
    write_source(
        source,
        [("0:00:01.00", long_line), ("0:00:11.00", long_line + r"{\k1}字")],
    )

    with pytest.raises(OverwideError) as caught:
        generate_derived_ass(
            source,
            output,
            title_text="x/y",
            audio_end=20,
            theme=THEMES["hinatazaka46"],
        )

    assert [line.index for line in caught.value.lines] == [0, 1]
    assert all(line.width > 1700 for line in caught.value.lines)
    assert output.read_text(encoding="utf-8") == "previous output\n"


@pytest.mark.parametrize(
    ("canvas", "expected_font"),
    [
        (Canvas(1080, 1080), "\\fs54.00"),
        (Canvas(1440, 1080), "\\fs72.00"),
        (Canvas(1080, 1920), "\\fs54.00"),
    ],
)
def test_arbitrary_canvas_uses_uniform_scale(
    tmp_path: Path, canvas: Canvas, expected_font: str
) -> None:
    source = tmp_path / "source.ass"
    output = tmp_path / "derived.ass"
    write_source(source, [("0:00:01.00", r"{\k50}日|<ひ{\k50}常|<び")])

    report = generate_derived_ass(
        source,
        output,
        title_text="",
        audio_end=12,
        theme=THEMES["hinatazaka46"],
        canvas=canvas,
    )

    text = output.read_text(encoding="utf-8")
    assert report.play_res_x == canvas.width
    assert report.play_res_y == canvas.height
    assert f"PlayResX: {canvas.width}" in text
    assert f"PlayResY: {canvas.height}" in text
    assert expected_font in text


def test_empty_karaoke_dialogue_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source.ass"
    source.write_text(
        "\n".join(
            [
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                "Dialogue: 0,0:00:00.00,0:00:01.00,K1,,0,0,0,karaoke,",
                r"Dialogue: 0,0:00:01.00,0:00:02.00,K1,,0,0,0,karaoke,{\k100}日",
            ]
        ),
        encoding="utf-8",
    )

    report = generate_derived_ass(
        source,
        tmp_path / "out.ass",
        title_text="",
        audio_end=3,
        theme=THEMES["nogizaka46"],
    )

    assert report.source_dialogues == 1
