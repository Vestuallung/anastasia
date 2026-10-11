from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from fugashi import Tagger

from .models import (
    DisplayToken,
    LineState,
    LyricLine,
    MoraToken,
    ReadingSource,
    RubyGroup,
    Span,
)
from .mora import is_kana, mora_romaji, normalize_romaji, split_mora

_KANJI_BASE = r"(?:[0-9０-９]*[一-鿿㐀-䶿々〆ヵヶ][一-鿿㐀-䶿々〆ヵヶ0-9０-９]*)"
_NUMERIC_FRACTION_BASE = r"[0-9０-９]+/[0-9０-９]+"
_ENGLISH_WORD = r"[A-Za-zＡ-Ｚａ-ｚ0-9０-９]+(?:['’\-‐‑－][A-Za-zＡ-Ｚａ-ｚ0-9０-９]+)*"
_ENGLISH_BASE = rf"{_ENGLISH_WORD}(?:[ \t　]+{_ENGLISH_WORD})*"
# Explicit ruby may annotate a single non-whitespace symbol as well, e.g.
# `π《パイ》`. Keep this fallback single-character so it cannot swallow
# adjacent sung text when the symbol is followed by ruby.
_RUBY_BASE_CHAR = r"[^\s《》\r\n]"
RUBY_RE = re.compile(
    rf"(?P<base>{_NUMERIC_FRACTION_BASE}|{_KANJI_BASE}|[ぁ-ゖァ-ヺー]+|{_ENGLISH_BASE}|{_RUBY_BASE_CHAR})"
    r"《(?P<reading>[^《》\r\n]+)》"
)
LEGACY_RUBY_RE = re.compile(
    r"(?P<base>[一-鿿㐀-䶿々〆ヵヶ]+|[A-Za-zＡ-Ｚａ-ｚ0-9０-９]+)"
    r"\((?P<reading>[ぁ-ゖァ-ヺー]+)\)"
)
LRC_TIME_RE = re.compile(r"^\[(?P<m>\d{1,3}):(?P<s>\d{2})(?:[.:](?P<f>\d{1,3}))?]\s?(?P<text>.*)$")
ASS_DIALOGUE_RE = re.compile(r"^Dialogue\s*:\s*(?P<body>.*)$", re.IGNORECASE)
ASS_K_RE = re.compile(r"\{\\k(?P<k>\d+)[^}]*}")
ASS_TAG_RE = re.compile(r"\{[^}]*}")


@dataclass(frozen=True)
class AnnotatedSegment:
    display: str
    span: Span
    reading: str | None
    source: ReadingSource | None


@dataclass(frozen=True)
class ImportedLine:
    text: str
    paragraph_before: int = 0
    reference_time_ms: int | None = None
    ass_start_ms: int | None = None
    ass_end_ms: int | None = None
    ass_k_values_cs: tuple[int, ...] = ()


class ReadingUnavailable(ValueError):
    pass


def stable_line_id(source_index: int, original: str) -> str:
    digest = hashlib.sha256(f"{source_index}\0{original}".encode()).hexdigest()[:12]
    return f"line-{source_index:04d}-{digest}"


def _is_alignable(char: str) -> bool:
    if char == "ー" or char.isalnum():
        return True
    category = unicodedata.category(char)
    return "ぁ" <= char <= "ヺ" or "一" <= char <= "鿿" or category.startswith("L")


def _split_plain(segment: AnnotatedSegment) -> list[AnnotatedSegment]:
    if not segment.display:
        return []
    result: list[AnnotatedSegment] = []
    start = 0
    alignable = _is_alignable(segment.display[0])
    for index, char in enumerate(segment.display[1:], start=1):
        next_alignable = _is_alignable(char)
        if next_alignable != alignable or not alignable:
            text = segment.display[start:index]
            result.append(
                AnnotatedSegment(
                    display=text,
                    span=Span(start=segment.span.start + start, end=segment.span.start + index),
                    reading=None,
                    source=None if alignable else ReadingSource.DISPLAY_ONLY,
                )
            )
            start = index
            alignable = next_alignable
    result.append(
        AnnotatedSegment(
            display=segment.display[start:],
            span=Span(start=segment.span.start + start, end=segment.span.end),
            reading=None,
            source=None if alignable else ReadingSource.DISPLAY_ONLY,
        )
    )
    return result


def parse_ruby(text: str, *, legacy_parentheses: bool = False) -> list[AnnotatedSegment]:
    matcher = LEGACY_RUBY_RE if legacy_parentheses else RUBY_RE
    output: list[AnnotatedSegment] = []
    cursor = 0
    for match in matcher.finditer(text):
        if match.start() > cursor:
            output.extend(
                _split_plain(
                    AnnotatedSegment(
                        display=text[cursor : match.start()],
                        span=Span(start=cursor, end=match.start()),
                        reading=None,
                        source=None,
                    )
                )
            )
        output.append(
            AnnotatedSegment(
                display=match.group("base"),
                span=Span(start=match.start("base"), end=match.end()),
                reading=match.group("reading"),
                source=ReadingSource.RUBY,
            )
        )
        cursor = match.end()
    if cursor < len(text):
        output.extend(
            _split_plain(
                AnnotatedSegment(
                    display=text[cursor:],
                    span=Span(start=cursor, end=len(text)),
                    reading=None,
                    source=None,
                )
            )
        )
    return output


def _feature_reading(word: object) -> str | None:
    feature = getattr(word, "feature", None)
    for name in ("kana", "pron", "reading"):
        value = getattr(feature, name, None)
        if value and value != "*":
            return str(value)
    if isinstance(feature, (tuple, list)):
        for index in (6, 7, 9):
            if index < len(feature) and feature[index] not in (None, "*"):
                return str(feature[index])
    return None


class LocalReadingAnalyzer:
    """Primary and only automatic reading provider: MeCab with UniDic."""

    def __init__(self) -> None:
        self._tagger = Tagger()

    def words(self, text: str) -> list[tuple[str, str]]:
        words: list[tuple[str, str]] = []
        for word in self._tagger(text):
            surface = str(word.surface)
            reading = _feature_reading(word)
            if not reading and (is_kana(surface) or surface.isalnum()):
                reading = surface
            if not reading:
                raise ReadingUnavailable(
                    f"MeCab/UniDic did not provide a reading for {surface!r}; add explicit ruby"
                )
            words.append((surface, reading))
        return words


def build_line(
    original: str,
    source_index: int,
    *,
    legacy_parentheses: bool = False,
    analyzer: LocalReadingAnalyzer | None = None,
    reference_time_ms: int | None = None,
    paragraph_before: int = 0,
) -> LyricLine:
    analyzer = analyzer or LocalReadingAnalyzer()
    line_id = stable_line_id(source_index, original)
    display_tokens: list[DisplayToken] = []
    ruby_groups: list[RubyGroup] = []
    moras: list[MoraToken] = []
    yohane_groups: list[str] = []
    token_no = 0
    group_no = 0
    mora_no = 0

    def add_group(display: str, span: Span, reading: str, source: ReadingSource) -> None:
        nonlocal token_no, group_no, mora_no
        token_id = f"{line_id}-t{token_no}"
        group_id = f"{line_id}-g{group_no}"
        display_tokens.append(DisplayToken(id=token_id, text=display, span=span, alignable=True))
        group_moras = split_mora(reading)
        mora_ids: list[str] = []
        group_romaji: list[str] = []
        for kana in group_moras:
            mora_id = f"{line_id}-m{mora_no}"
            romaji = normalize_romaji(mora_romaji(kana))
            mora_ids.append(mora_id)
            moras.append(
                MoraToken(
                    id=mora_id,
                    kana=kana,
                    romaji=romaji,
                    group_id=group_id,
                    display_token_id=token_id,
                )
            )
            group_romaji.append(romaji)
            mora_no += 1
        ruby_groups.append(
            RubyGroup(
                id=group_id,
                span=span,
                display_token_ids=[token_id],
                display=display,
                reading=reading,
                mora_ids=mora_ids,
                source=source,
            )
        )
        yohane_groups.append(" ".join(part for part in group_romaji if part))
        token_no += 1
        group_no += 1

    for segment in parse_ruby(original, legacy_parentheses=legacy_parentheses):
        if segment.source == ReadingSource.DISPLAY_ONLY:
            token_id = f"{line_id}-t{token_no}"
            display_tokens.append(
                DisplayToken(id=token_id, text=segment.display, span=segment.span, alignable=False)
            )
            token_no += 1
            continue
        if segment.reading is not None:
            add_group(segment.display, segment.span, segment.reading, ReadingSource.RUBY)
            continue
        offset = segment.span.start
        for surface, reading in analyzer.words(segment.display):
            local = segment.display.find(surface, offset - segment.span.start)
            if local < 0:
                local = offset - segment.span.start
            word_span = Span(
                start=segment.span.start + local,
                end=segment.span.start + local + len(surface),
            )
            add_group(surface, word_span, reading, ReadingSource.MECAB)
            offset = word_span.end

    return LyricLine(
        id=line_id,
        source_index=source_index,
        paragraph_before=paragraph_before,
        original=original,
        display_tokens=display_tokens,
        ruby_groups=ruby_groups,
        moras=moras,
        yohane_input=" ".join(group for group in yohane_groups if group),
        state=LineState.READY,
        reference_time_ms=reference_time_ms,
    )


def parse_lrc_time(minutes: str, seconds: str, fraction: str | None) -> int:
    fraction = fraction or "0"
    millis = int((fraction + "000")[:3])
    return (int(minutes) * 60 + int(seconds)) * 1000 + millis


def ass_time_to_ms(value: str) -> int:
    hours, minutes, rest = value.strip().split(":")
    seconds, centiseconds = rest.split(".")
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(centiseconds) * 10


def _ass_visible_text(text: str) -> str:
    without_tags = ASS_TAG_RE.sub("", text)
    return without_tags.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")


def import_lyrics(path: Path) -> tuple[str, list[ImportedLine]]:
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8-sig")
    if suffix == ".txt":
        lines = []
        blank_count = 0
        for line in raw.splitlines():
            if not line.strip():
                blank_count += 1
                continue
            lines.append(ImportedLine(text=line, paragraph_before=blank_count))
            blank_count = 0
        return "txt", lines
    if suffix == ".lrc":
        lines: list[ImportedLine] = []
        for value in raw.splitlines():
            match = LRC_TIME_RE.match(value)
            if match and match.group("text").strip():
                lines.append(
                    ImportedLine(
                        text=match.group("text"),
                        reference_time_ms=parse_lrc_time(
                            match.group("m"), match.group("s"), match.group("f")
                        ),
                    )
                )
        return "lrc", lines
    if suffix == ".ass":
        lines = []
        for value in raw.splitlines():
            match = ASS_DIALOGUE_RE.match(value)
            if not match:
                continue
            fields = match.group("body").split(",", 9)
            if len(fields) != 10:
                continue
            text = fields[9]
            lines.append(
                ImportedLine(
                    text=_ass_visible_text(text),
                    ass_start_ms=ass_time_to_ms(fields[1]),
                    ass_end_ms=ass_time_to_ms(fields[2]),
                    ass_k_values_cs=tuple(int(item.group("k")) for item in ASS_K_RE.finditer(text)),
                )
            )
        return "ass", lines
    raise ValueError("lyrics must be TXT, LRC or ASS")


def build_lines(
    imported: list[ImportedLine], *, legacy_parentheses: bool = False
) -> list[LyricLine]:
    analyzer = LocalReadingAnalyzer()
    return [
        build_line(
            item.text,
            index,
            legacy_parentheses=legacy_parentheses,
            analyzer=analyzer,
            reference_time_ms=item.reference_time_ms,
            paragraph_before=item.paragraph_before,
        )
        for index, item in enumerate(imported)
    ]
