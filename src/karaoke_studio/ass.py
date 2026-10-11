from __future__ import annotations

import re

from .config import section
from .models import KaraokeProject, LyricLine
from .mora import is_kana, split_mora
from .timing import effective_boundaries, quantized_k_values

# `|<` / `#|<` is the furigana convention consumed by Aegisub Karaoke
# Templater. The accompanying styles and templates deliberately mirror the
# established local workflow, rather than emitting invisible placeholder text.
ASS_HEADER = """[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {canvas_width}
PlayResY: {canvas_height}

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: K1-furigana,{font_family},{ruby_size},&H00FFFFFF,&H00FF0000,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2.5,0,1,120,30,260,1
Style: K1,{font_family},{main_size},&H00FFFFFF,&H00FF0000,&H00000000,&H80000000,0,0,0,0,100,100,5,0,1,5,0,1,120,30,290,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Comment: 0,0:00:00.00,0:00:00.00,K1,,0,0,0,code once,remember("default_color", "&HFF0000&"); remember("furigana_offset", 26);
Comment: 0,0:00:00.00,0:00:00.00,K1,,0,0,0,template syl all,!retime("line",-100,-100)!{{\\pos($center,$middle) \\an5 \\shad0 \\1c&HFFFFFF& \\3c&H000000& \\bord7 \\blur0}}
Comment: 0,0:00:00.00,0:00:00.00,K1,,0,0,0,template furi all,!retime("line",-100,-100)!{{\\pos($center,!$middle+recall("furigana_offset")!) \\an5 \\shad0 \\1c&HFFFFFF& \\3c&H000000& \\bord3 \\blur0}}
"""


def ass_time(milliseconds: int) -> str:
    centiseconds = max(0, round(milliseconds / 10))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"


def escape_ass_text(text: str) -> str:
    return (
        text.replace("\\", r"\textbackslash")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _line_k_values(project: KaraokeProject, line: LyricLine) -> tuple[int, int, list[int]]:
    raw = None
    if project.raw_alignment:
        raw = next((item for item in project.raw_alignment.lines if item.line_id == line.id), None)
    patches = [patch for patch in project.timing_patches if patch.line_id == line.id]
    if raw and (not patches or patches[-1].kind == "restore"):
        return raw.start_ms, raw.end_ms, list(raw.k_values_cs)
    boundaries = effective_boundaries(project, line.id)
    if not boundaries:
        return 0, 10, [0] * len(line.moras)
    return boundaries[0], boundaries[-1], quantized_k_values(boundaries)


def _display_units(text: str, mora_count: int) -> list[tuple[str, int]]:
    """Project a saved word-level reading onto visible character units only."""
    kana_units = split_mora(text) if is_kana(text) else []
    if len(kana_units) == mora_count:
        return [(unit, 1) for unit in kana_units]
    words = list(re.finditer(r"\S+", text))
    if words and all(char.isascii() for char in text if not char.isspace()):
        total_weight = sum(len(match.group()) for match in words)
        units: list[tuple[str, int]] = []
        previous_end = 0
        previous_boundary = 0
        cumulative_weight = 0
        for match in words:
            if match.start() > previous_end:
                units.append((text[previous_end : match.start()], 0))
            cumulative_weight += len(match.group())
            boundary = round(mora_count * cumulative_weight / total_weight)
            units.append((match.group(), boundary - previous_boundary))
            previous_boundary = boundary
            previous_end = match.end()
        if previous_end < len(text):
            units.append((text[previous_end:], 0))
        return units
    characters = list(text)
    if not characters:
        return []
    base, remainder = divmod(mora_count, len(characters))
    return [
        (char, base + (index >= len(characters) - remainder))
        for index, char in enumerate(characters)
    ]


def _render_aligned_token(
    text: str, mora_indices: list[int], line: LyricLine, k_values: list[int]
) -> str:
    if not mora_indices:
        return r"{\k0}" + escape_ass_text(text)
    output: list[str] = []
    cursor = 0
    for unit, count in _display_units(text, len(mora_indices)):
        if count <= 0:
            output.append(r"{\k0}" + escape_ass_text(unit))
            continue
        needs_furigana = not is_kana(unit)
        for offset in range(count):
            mora_index = mora_indices[cursor]
            duration = k_values[mora_index] if mora_index < len(k_values) else 0
            kana = line.moras[mora_index].kana
            if needs_furigana:
                display = escape_ass_text(unit) if offset == 0 else "#"
                output.append(f"{{\\k{duration}}}{display}|<{escape_ass_text(kana)}")
            else:
                display = escape_ass_text(unit) if offset == 0 else "#|<"
                output.append(f"{{\\k{duration}}}{display}")
            cursor += 1
    while cursor < len(mora_indices):
        mora_index = mora_indices[cursor]
        duration = k_values[mora_index] if mora_index < len(k_values) else 0
        output.append(f"{{\\k{duration}}}#|<")
        cursor += 1
    return "".join(output)


def render_karaoke_text(line: LyricLine, k_values: list[int]) -> str:
    mora_by_token: dict[str, list[int]] = {}
    for index, mora in enumerate(line.moras):
        mora_by_token.setdefault(mora.display_token_id, []).append(index)
    output: list[str] = []
    token_index = 0
    while token_index < len(line.display_tokens):
        token = line.display_tokens[token_index]
        indices = mora_by_token.get(token.id, [])
        # Projects created before mixed-script ruby support may contain a
        # leading numeral as a zero-duration token followed by the ruby group.
        # Join it only for export: the cached reading and raw Yohane k values
        # stay untouched, while the visible result matches new imports.
        if (
            token.alignable
            and not indices
            and token.text.isalnum()
            and token_index + 1 < len(line.display_tokens)
        ):
            next_token = line.display_tokens[token_index + 1]
            next_indices = mora_by_token.get(next_token.id, [])
            if next_indices and token.span.end == next_token.span.start:
                output.append(
                    _render_aligned_token(
                        token.text + next_token.text, next_indices, line, k_values
                    )
                )
                token_index += 2
                continue
        if not token.alignable:
            output.append(r"{\k0}" + escape_ass_text(token.text))
        else:
            output.append(_render_aligned_token(token.text, indices, line, k_values))
        token_index += 1
    result = "".join(output)
    parts = re.split(r"\{\\k\d+\}", result)
    visible = "".join(
        part.split("|<", 1)[0] for part in parts if part and part.split("|<", 1)[0] != "#"
    )
    if visible != escape_ass_text(line.display_text):
        raise ValueError(f"ASS export changed the source display text: {line.id}")
    return result


def export_ass(project: KaraokeProject) -> str:
    events: list[str] = []
    for line in project.lines:
        start, end, k_values = _line_k_values(project, line)
        text = render_karaoke_text(line, k_values)
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},K1,,0,0,0,karaoke,{text}")
    return (
        ASS_HEADER.format(
            font_family=section("fonts")["japanese_family"],
            canvas_width=section("layout")["canvas_width"],
            canvas_height=section("layout")["canvas_height"],
            main_size=section("appearance")["main_size"],
            ruby_size=round(
                section("appearance")["main_size"] * section("appearance")["ruby_ratio"]
            ),
            title=project.title.replace("\n", " "),
        )
        + "\n".join(events)
        + "\n"
    )
