from __future__ import annotations

from conftest import StubAnalyzer

from karaoke_studio.lyrics import build_line
from karaoke_studio.models import ReadingSource


def test_complete_ruby_bypasses_mecab() -> None:
    analyzer = StubAnalyzer({})

    line = build_line("他人《ひと》歌《うた》", 0, analyzer=analyzer)

    assert analyzer.calls == []
    assert line.display_text == "他人歌"
    assert [group.reading for group in line.ruby_groups] == ["ひと", "うた"]
    assert {group.source for group in line.ruby_groups} == {ReadingSource.RUBY}
    assert line.yohane_input.split() == ["hi", "to", "u", "ta"]


def test_partial_ruby_only_analyzes_unannotated_span() -> None:
    analyzer = StubAnalyzer({"と未来": [("と", "ト"), ("未来", "ミライ")]})

    line = build_line("他人《ひと》と未来", 3, analyzer=analyzer)

    assert analyzer.calls == ["と未来"]
    assert line.display_text == "他人と未来"
    assert [group.source for group in line.ruby_groups] == [
        ReadingSource.RUBY,
        ReadingSource.MECAB,
        ReadingSource.MECAB,
    ]


def test_unannotated_line_uses_local_analyzer_for_entire_line() -> None:
    analyzer = StubAnalyzer({"他人と未来": [("他人", "タニン"), ("と", "ト"), ("未来", "ミライ")]})

    line = build_line("他人と未来", 1, analyzer=analyzer)

    assert analyzer.calls == ["他人と未来"]
    assert all(group.source == ReadingSource.MECAB for group in line.ruby_groups)
    assert line.display_text == line.original


def test_parentheses_are_sung_text_unless_legacy_import_is_explicit() -> None:
    ordinary = StubAnalyzer({"他人": [("他人", "タニン")], "ひと": [("ひと", "ヒト")]})
    legacy = StubAnalyzer({})

    ordinary_line = build_line("他人(ひと)", 0, analyzer=ordinary)
    legacy_line = build_line("他人(ひと)", 0, analyzer=legacy, legacy_parentheses=True)

    assert ordinary.calls == ["他人", "ひと"]
    assert ordinary_line.display_text == "他人(ひと)"
    assert [token.text for token in ordinary_line.display_tokens if not token.alignable] == [
        "(",
        ")",
    ]
    assert legacy.calls == []
    assert legacy_line.display_text == "他人"
    assert legacy_line.ruby_groups[0].reading == "ひと"
    assert legacy_line.ruby_groups[0].source == ReadingSource.RUBY


def test_punctuation_and_unicode_spaces_round_trip_exactly() -> None:
    original = "　あ、  い！？…（う）　"
    analyzer = StubAnalyzer(
        {
            "あ": [("あ", "ア")],
            "い": [("い", "イ")],
            "う": [("う", "ウ")],
        }
    )

    line = build_line(original, 0, analyzer=analyzer)

    assert line.display_text == original
    assert "".join(token.text for token in line.display_tokens) == original
    assert all(
        not token.alignable
        for token in line.display_tokens
        if token.text.strip() in {"", "、", "！", "？", "…", "（", "）"}
    )


def test_english_ruby_accepts_apostrophes_hyphens_and_spaces() -> None:
    analyzer = StubAnalyzer({})
    original = "Nobody's Fault《ノーバディーズ・フォルト》 Brand-new day《ブランド・ニュー・デイ》"

    line = build_line(original, 0, analyzer=analyzer)

    assert analyzer.calls == []
    assert line.display_text == "Nobody's Fault Brand-new day"
    assert [group.display for group in line.ruby_groups] == ["Nobody's Fault", "Brand-new day"]
