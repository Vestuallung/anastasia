from __future__ import annotations

import re
import unicodedata

from pykakasi import kakasi

SMALL_KANA = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")
KANA_RE = re.compile(r"[ぁ-ゖァ-ヺーゝゞヽヾ]")
_KAKASI = kakasi()


def is_kana(value: str) -> bool:
    return bool(value) and all(KANA_RE.fullmatch(char) for char in value)


def split_mora(reading: str) -> list[str]:
    """Split Japanese reading into display moras without discarding っ, ん or ー."""
    normalized = unicodedata.normalize("NFKC", reading).replace(" ", "")
    result: list[str] = []
    for char in normalized:
        if char in SMALL_KANA and result and result[-1] not in {"っ", "ッ", "ん", "ン", "ー"}:
            result[-1] += char
        else:
            result.append(char)
    return result


def reading_to_romaji(reading: str) -> str:
    pieces = _KAKASI.convert(reading)
    return "".join(str(piece.get("hepburn", "")) for piece in pieces).strip().lower()


def mora_romaji(mora: str) -> str:
    return reading_to_romaji(mora)


def normalize_romaji(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower().replace("’", "'")
    value = re.sub(r"[^a-z0-9' ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def romaji_mora_count(value: str) -> int:
    """Count explicitly separated alignment units.

    Karaoke Studio emits one space-delimited unit per display mora. A synthetic
    `n+vowel` break therefore changes tokenization without changing display.
    """
    return len([token for token in normalize_romaji(value).split(" ") if token])
