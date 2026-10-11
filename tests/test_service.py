from __future__ import annotations

import pytest

from karaoke_studio.service import normalize_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("日向坂 46-《イチャイチャ虫》", "日向坂 46-《イチャイチャ虫》"),
        ("  《イチャイチャ虫》  ", "イチャイチャ虫"),
        ("《イチャイチャ虫》", "イチャイチャ虫"),
        ("日向坂 46-《イチャイチャ虫》》", "日向坂 46-《イチャイチャ虫》》"),
    ],
)
def test_normalize_title_preserves_internal_or_unpaired_brackets(raw: str, expected: str) -> None:
    assert normalize_title(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "《》", "nested/title"])
def test_normalize_title_rejects_empty_or_path_titles(raw: str) -> None:
    with pytest.raises(ValueError, match="title must be a non-empty folder name"):
        normalize_title(raw)
