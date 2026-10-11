from __future__ import annotations

from dataclasses import dataclass, replace

from .config import section

RGB = tuple[int, int, int]
ThemeName = str


@dataclass(frozen=True)
class KaraokeTheme:
    name: str
    label: str
    light: RGB
    mid: RGB
    sung: RGB
    unsung_outline: RGB
    unsung_fill: RGB = (255, 255, 255)
    sung_outline: RGB = (255, 255, 255)
    title_fill: RGB | None = None
    title_outline: RGB = (255, 255, 255)


def parse_color(value: str) -> RGB:
    if len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"Expected #RRGGBB color: {value}")
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))


def _load_themes() -> dict[str, KaraokeTheme]:
    result = {}
    for name, item in section("groups").items():
        colors = {key: parse_color(value) for key, value in item.items() if key != "label"}
        sung = colors["sung"]
        defaults = {"light": sung, "mid": sung, "unsung_outline": (0, 0, 0)}
        result[name] = KaraokeTheme(name=name, label=item["label"], **(defaults | colors))
    return result


THEMES = _load_themes()


def get_theme(name: str) -> KaraokeTheme:
    try:
        return THEMES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown theme: {name}. Available themes: {', '.join(THEMES)}") from exc


def resolve_theme(name: str, colors: dict[str, str] | None = None) -> KaraokeTheme:
    allowed = {
        "sung",
        "unsung_fill",
        "unsung_outline",
        "sung_outline",
        "title_fill",
        "title_outline",
    }
    values = {}
    for key, value in (colors or {}).items():
        if key not in allowed:
            raise ValueError(f"Unknown color field: {key}")
        values[key] = parse_color(value)
    return replace(get_theme(name), **values)
