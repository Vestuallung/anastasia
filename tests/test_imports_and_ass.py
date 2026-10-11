from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import StubAnalyzer

from karaoke_studio.ass import export_ass, render_karaoke_text
from karaoke_studio.lyrics import ImportedLine, build_line, import_lyrics
from karaoke_studio.models import KaraokeProject
from karaoke_studio.project_io import create_project
from karaoke_studio.service import _adopt_ass_timing, import_project_assets


def test_txt_blank_lines_become_paragraph_boundaries(tmp_path: Path) -> None:
    source = tmp_path / "song.txt"
    source.write_text("最初\n\n\n次\n", encoding="utf-8")

    source_format, lines = import_lyrics(source)

    assert source_format == "txt"
    assert [(line.text, line.paragraph_before) for line in lines] == [("最初", 0), ("次", 2)]


def test_lrc_times_are_reference_markers_not_alignment(tmp_path: Path) -> None:
    source = tmp_path / "song.lrc"
    source.write_text("[00:01.25]最初\n[01:02.345]次\n", encoding="utf-8")

    source_format, lines = import_lyrics(source)

    assert source_format == "lrc"
    assert [(line.text, line.reference_time_ms) for line in lines] == [
        ("最初", 1250),
        ("次", 62345),
    ]
    assert all(line.ass_start_ms is None and not line.ass_k_values_cs for line in lines)


def test_ass_import_extracts_visible_text_times_and_k_values(tmp_path: Path) -> None:
    source = tmp_path / "song.ass"
    source.write_text(
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        r"Dialogue: 0,0:00:01.20,0:00:01.50,K1,,0,0,0,,{\k10}あ{\k20}い"
        "\n",
        encoding="utf-8",
    )

    source_format, lines = import_lyrics(source)

    assert source_format == "ass"
    assert lines == [
        ImportedLine(
            text="あい",
            ass_start_ms=1200,
            ass_end_ms=1500,
            ass_k_values_cs=(10, 20),
        )
    ]


def test_ass_preserve_mode_adopts_valid_timing_without_yohane() -> None:
    line = build_line("あい", 0, analyzer=StubAnalyzer({"あい": [("あい", "アイ")]}))
    project = KaraokeProject(project_id="p", title="Preserved", lines=[line])
    imported = [
        ImportedLine(text="あい", ass_start_ms=1200, ass_end_ms=1500, ass_k_values_cs=(10, 20))
    ]

    _adopt_ass_timing(project, imported)

    assert project.alignment_source == "preserved_ass"
    assert project.alignment_stale is False
    assert project.raw_alignment is not None
    assert project.raw_alignment.adapter_version == "ass-import"
    assert project.raw_alignment.lines[0].k_values_cs == [10, 20]


def test_ass_default_import_does_not_preserve_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    create_project(project_dir, "Default realign")
    source = tmp_path / "song.ass"
    source.write_text(
        r"Dialogue: 0,0:00:01.20,0:00:01.50,K1,,0,0,0,,{\k10}あ{\k20}い"
        "\n",
        encoding="utf-8",
    )
    built = build_line("あい", 0, analyzer=StubAnalyzer({"あい": [("あい", "アイ")]}))
    monkeypatch.setattr("karaoke_studio.service.build_lines", lambda *_args, **_kwargs: [built])

    project = import_project_assets(project_dir, lyrics_path=source, preserve_ass_timing=False)

    assert project.source.preserve_ass_timing is False
    assert project.raw_alignment is None
    assert project.alignment_source is None
    assert project.alignment_stale is True


def test_import_records_video_without_media_validation(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    create_project(project_dir, "Video source")
    lyrics = tmp_path / "lyrics.txt"
    audio = tmp_path / "audio.mp4"
    video = tmp_path / "video.mp4"
    lyrics.write_text("あ《あ》\n", encoding="utf-8")
    audio.write_bytes(b"audio placeholder")
    video.write_bytes(b"video placeholder")

    project = import_project_assets(
        project_dir,
        lyrics_path=lyrics,
        audio_path=audio,
        video_path=video,
    )

    assert project.source.audio_path == "source/audio.mp4"
    assert project.source.video_path == "source/video.mp4"
    assert (project_dir / project.source.video_path).read_bytes() == b"video placeholder"


def test_ass_uses_legacy_furigana_markers_and_k0_for_display_only(
    aligned_project: KaraokeProject,
) -> None:
    analyzer = StubAnalyzer({"あ": [("あ", "ア")], "い": [("い", "イ")]})
    line = build_line("　あ、  い！", 0, analyzer=analyzer)
    aligned_project.lines = [line]
    assert aligned_project.raw_alignment is not None
    aligned_project.raw_alignment.lines[0].line_id = line.id

    rendered = render_karaoke_text(line, [10, 20])
    visible = re.sub(r"\{\\k\d+}", "", rendered)

    assert visible == line.original
    assert rendered.startswith(r"{\k0}　{\k10}あ{\k0}、{\k0} {\k0} ")
    assert rendered.endswith(r"{\k20}い{\k0}！")
    assert export_ass(aligned_project).count(r"{\k0}") == 5


def test_ass_emits_character_furigana_without_word_joiners(aligned_project: KaraokeProject) -> None:
    line = build_line("車窓《しゃそう》", 0, analyzer=StubAnalyzer({}))
    aligned_project.lines = [line]
    assert aligned_project.raw_alignment is not None
    aligned_project.raw_alignment.lines[0].line_id = line.id
    aligned_project.raw_alignment.lines[0].k_values_cs = [10, 20, 30]

    rendered = render_karaoke_text(line, [10, 20, 30])
    exported = export_ass(aligned_project)

    assert rendered == r"{\k10}車|<しゃ{\k20}窓|<そ{\k30}#|<う"
    assert "\u2060" not in exported
    assert "Style: K1-furigana" in exported
    assert "template furi all" in exported
    assert all(
        line.split(",", 5)[3] == "K1"
        for line in exported.splitlines()
        if line.startswith("Dialogue:")
    )


def test_mixed_script_ruby_keeps_numeral_inside_the_reading_group() -> None:
    line = build_line(
        "2度目《にどめ》のキスから気《き》",
        0,
        analyzer=StubAnalyzer({"のキスから": [("のキスから", "ノキスカラ")]}),
    )

    assert [token.text for token in line.display_tokens] == ["2度目", "のキスから", "気"]
    assert line.ruby_groups[0].display == "2度目"
    assert render_karaoke_text(line, [10, 20, 30, 40, 50, 60, 70, 80, 90]) == (
        r"{\k10}2|<に{\k20}度|<ど{\k30}目|<め"
        r"{\k40}の{\k50}キ{\k60}ス{\k70}か{\k80}ら{\k90}気|<き"
    )


def test_numeric_fraction_ruby_binds_to_the_complete_fraction() -> None:
    line = build_line("22/7《ななぶんのにじゅうに》", 0, analyzer=StubAnalyzer({}))

    assert [token.text for token in line.display_tokens] == ["22/7"]
    assert [group.display for group in line.ruby_groups] == ["22/7"]
    assert [group.reading for group in line.ruby_groups] == ["ななぶんのにじゅうに"]


def test_single_unicode_symbol_ruby_does_not_leak_annotation_markers() -> None:
    line = build_line(
        "π《パイ》でなんかじゃ",
        0,
        analyzer=StubAnalyzer(
            {"でなんかじゃ": [("で", "デ"), ("なんか", "ナンカ"), ("じゃ", "ジャ")]}
        ),
    )

    assert line.display_text == "πでなんかじゃ"
    assert line.ruby_groups[0].display == "π"
    assert line.ruby_groups[0].reading == "パイ"
    assert [token.text for token in line.display_tokens] == ["π", "で", "なんか", "じゃ"]
