from __future__ import annotations

from conftest import StubAnalyzer

from karaoke_studio.ass import export_ass
from karaoke_studio.lyrics import build_line
from karaoke_studio.models import KaraokeProject, RawAlignedLine, RawAlignment
from karaoke_studio.structure import reconcile_to_yohane
from karaoke_studio.validate import inspect_project


def test_n_followed_by_vowel_is_deterministically_separated_for_yohane() -> None:
    line = build_line("けんお", 0, analyzer=StubAnalyzer({"けんお": [("けんお", "ケンオ")]}))

    assert line.yohane_input == "ke n o"
    assert len(line.yohane_input.split()) == len(line.moras) == 3


def test_multiple_moras_can_share_one_kanji_display_group() -> None:
    line = build_line("失《うしな》う", 0, analyzer=StubAnalyzer({"う": [("う", "ウ")]}))
    explicit = line.ruby_groups[0]

    assert explicit.display == "失"
    assert len(explicit.mora_ids) == 3
    assert len({mora.display_token_id for mora in line.moras[:3]}) == 1


def test_transcript_mismatch_preserves_source_and_raw_timing() -> None:
    line = build_line("あい", 0, analyzer=StubAnalyzer({"あい": [("あい", "アイ")]}))
    raw = RawAlignedLine(
        line_id=line.id,
        start_ms=1000,
        end_ms=1400,
        k_values_cs=[10, 15, 15],
        labels=["a", "x", "i"],
    )
    original_k = list(raw.k_values_cs)
    before = line.model_dump()

    issue = reconcile_to_yohane(line, raw)

    assert issue is not None and issue.code == "yohane_unit_mapping"
    assert line.model_dump(exclude={"state"}) == {k: v for k, v in before.items() if k != "state"}
    assert raw.k_values_cs == original_k


def test_missing_native_labels_preserves_display_groups() -> None:
    line = build_line("𠮷野", 0, analyzer=StubAnalyzer({"𠮷野": [("𠮷野", "ヨシノ")]}))
    raw = RawAlignedLine(
        line_id=line.id,
        start_ms=200,
        end_ms=500,
        k_values_cs=[10, 10],
        labels=[],
    )

    issue = reconcile_to_yohane(line, raw)

    assert issue is not None and issue.code == "yohane_unit_mapping"
    assert len(line.moras) == 3
    assert len(raw.k_values_cs) == 2
    assert len(line.ruby_groups) == 1
    assert line.ruby_groups[0].display == "𠮷野"


def test_export_preserves_raw_k_even_when_line_end_has_tail() -> None:
    line = build_line("あい", 0, analyzer=StubAnalyzer({"あい": [("あい", "アイ")]}))
    raw = RawAlignedLine(
        line_id=line.id,
        start_ms=1000,
        end_ms=1600,
        k_values_cs=[10, 20],
    )
    project = KaraokeProject(
        project_id="raw-k",
        title="Raw",
        lines=[line],
        raw_alignment=RawAlignment(
            cache_key="cache",
            adapter_version="test",
            model_id="test",
            model_revision="test",
            audio_sha256="a",
            normalized_romaji_sha256="b",
            lines=[raw],
        ),
    )

    output = export_ass(project)

    assert r"{\k10}あ{\k20}い" in output
    assert ",0:00:01.00,0:00:01.60," in output
    assert raw.k_values_cs == [10, 20]
    assert not [issue for issue in inspect_project(project) if issue.severity == "error"]


def test_split_kana_units_preserve_explicit_readings_and_text() -> None:
    line = build_line("Wow《ウォウ》 Yeah《イェー》", 0, analyzer=StubAnalyzer({}))
    raw = RawAlignedLine(
        line_id=line.id,
        start_ms=0,
        end_ms=500,
        k_values_cs=[10, 10, 10, 10, 10],
        labels=["u", "o", "u", "i", "e"],
    )
    issue = reconcile_to_yohane(line, raw)
    assert issue is None
    assert "".join(mora.kana for mora in line.moras) == "ウォウイェー"
    assert "".join(token.text for token in line.display_tokens) == "Wow Yeah"
    for group in line.ruby_groups:
        reading = "".join(m.kana for m in line.moras if m.id in group.mora_ids)
        assert reading == group.reading
    assert raw.k_values_cs == [10, 10, 10, 10, 10]
