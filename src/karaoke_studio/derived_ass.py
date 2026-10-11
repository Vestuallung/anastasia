"""Deterministic template-ASS expansion and translation overlays."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import ImageFont

from .config import configured_path, section
from .themes import KaraokeTheme

FONTS = section("fonts")
APPEARANCE = section("appearance")
LAYOUT = section("layout")
FONT_PATH = str(configured_path(FONTS["japanese_path"]))
FONT_NAME = FONTS["japanese_family"]
ZH_FONT_PATH = str(configured_path(FONTS["chinese_path"]))
ZH_FONT_NAME = FONTS["chinese_family"]
CANONICAL_W, CANONICAL_H = LAYOUT["canvas_width"], LAYOUT["canvas_height"]
MAIN_FONT, USABLE_W = APPEARANCE["main_size"], APPEARANCE["width_limit"]
KANA_FONT_RATIO, KANA_RISE_RATIO = APPEARANCE["ruby_ratio"], APPEARANCE["ruby_rise_ratio"]
CHINESE_FONT = APPEARANCE["chinese_size"]
TITLE_FONT = APPEARANCE["title_size"]
BOLD = int(APPEARANCE["bold"])


class DerivedAssError(ValueError):
    pass


class UnsupportedKaraokeTagError(DerivedAssError):
    pass


@dataclass(frozen=True)
class Canvas:
    width: int = CANONICAL_W
    height: int = CANONICAL_H

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise DerivedAssError("ASS 画布尺寸必须为正整数")

    @property
    def scale(self) -> float:
        return min(self.width / CANONICAL_W, self.height / CANONICAL_H)

    def x(self, value: float) -> float:
        return (self.width - CANONICAL_W * self.scale) / 2 + value * self.scale

    def y(self, value: float) -> float:
        return (self.height - CANONICAL_H * self.scale) / 2 + value * self.scale

    def size(self, value: float) -> float:
        return max(value * self.scale, 0.1)


@dataclass(frozen=True)
class KaraokePlacement:
    margin_x: float = LAYOUT["margin_x"]
    top_y: float = LAYOUT["top_y"]
    bottom_y: float = LAYOUT["bottom_y"]


@dataclass(frozen=True)
class TranslationPlacement:
    preset: Literal["bottom_left", "bottom_center", "bottom_right", "custom"] = "bottom_left"
    alignment: int | None = None
    x: float | None = None
    y: float | None = None

    def resolved(self) -> tuple[int, float, float]:
        presets = {
            "bottom_left": (1, 110.0, 1010.0),
            "bottom_center": (2, 960.0, 1010.0),
            "bottom_right": (3, 1810.0, 1010.0),
        }
        if self.preset != "custom":
            return presets[self.preset]
        if self.alignment not in range(1, 10) or self.x is None or self.y is None:
            raise DerivedAssError("中文字幕 custom 点位需要 alignment(1..9)、x、y")
        return self.alignment, self.x, self.y


@dataclass(frozen=True)
class OverwideLine:
    index: int
    text: str
    start: float
    end: float
    width: int
    font_size: int = MAIN_FONT


class OverwideError(DerivedAssError):
    def __init__(self, lines: list[OverwideLine]):
        self.lines = lines
        super().__init__(f"超宽检查失败: 共{len(lines)}句")


@dataclass(frozen=True)
class DerivedAssReport:
    source_dialogues: int
    generated_events: int
    long_interludes: int
    max_width: int
    font_size: int
    output: Path
    play_res_x: int = CANONICAL_W
    play_res_y: int = CANONICAL_H


@dataclass(frozen=True)
class TranslationAssReport:
    lines: int
    max_width: int
    combined_output: Path
    zh_only_output: Path


def to_bgr_ass(rgb: tuple[int, int, int]) -> str:
    return f"&H00{rgb[2]:02X}{rgb[1]:02X}{rgb[0]:02X}&"


def parse_ass_time(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, centiseconds = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centiseconds) / 100


def fmt_ass_time(value: float) -> str:
    total, cs = divmod(int(round(max(value, 0) * 100)), 100)
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"


def parse_source_play_res(path: Path) -> Canvas:
    text = path.read_text(encoding="utf-8")
    x = re.search(r"(?mi)^PlayResX:\s*(\d+)\s*$", text)
    y = re.search(r"(?mi)^PlayResY:\s*(\d+)\s*$", text)
    return Canvas(int(x.group(1)), int(y.group(1))) if x and y else Canvas()


def tokenize_ass(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    forbidden = sorted(set(re.findall(r"\\(?:K|kf|ko)\d+", text)))
    if forbidden:
        raise UnsupportedKaraokeTagError(
            "源 ASS 只允许 \\kNN；发现不支持的标签: " + ", ".join(forbidden)
        )
    in_events = False
    columns: list[str] = []
    result: list[dict] = []
    for line in text.splitlines():
        if line.strip() == "[Events]":
            in_events = True
            continue
        if in_events and line.startswith("["):
            in_events = False
        if not in_events:
            continue
        if line.startswith("Format:"):
            columns = [part.strip() for part in line[7:].split(",")]
            continue
        if not line.startswith("Dialogue:"):
            continue
        if not columns:
            raise DerivedAssError("[Events] 中 Dialogue 出现在 Format 之前")
        parts = line[9:].lstrip().split(",", len(columns) - 1)
        if len(parts) != len(columns):
            raise DerivedAssError(f"无法按 Events Format 解析 Dialogue: {line}")
        record = dict(zip(columns, parts, strict=True))
        if record.get("Effect") != "karaoke":
            continue
        # Old secondary-voice style names are an internal compatibility alias.
        style = record.get("Style", "")
        if style.lower().startswith("k2"):
            record["Style"] = "K1-furigana" if "furigana" in style.lower() else "K1"
        raw = record["Text"]
        if not raw.strip():
            continue
        if not re.search(r"\{\\k\d+\}", raw):
            raise DerivedAssError(f"karaoke Dialogue 缺少 \\kNN: {raw}")
        start, end = parse_ass_time(record["Start"]), parse_ass_time(record["End"])
        if end <= start:
            raise DerivedAssError(
                f"Dialogue 结束时间必须晚于开始时间: {record['Start']} - {record['End']}"
            )
        result.append({"start": start, "end": end, "text_raw": raw})
    if not result:
        raise DerivedAssError("源 ASS 中没有可用的 Effect=karaoke Dialogue")
    return result


def tokenize_dialogue(start: float, text: str) -> list[dict]:
    tokens: list[dict] = []
    current, pending, last_main, line_no = start, None, None, 0
    for part in re.split(r"(\{\\k\d+\})", text):
        if not part:
            continue
        match = re.fullmatch(r"\{\\k(\d+)\}", part)
        if match:
            if pending is not None:
                raise DerivedAssError("存在连续且未绑定文本的 \\kNN")
            pending = int(match.group(1))
            continue
        while part.startswith(r"\N"):
            line_no += 1
            part = part[2:]
        break_after = part.endswith(r"\N")
        if break_after:
            part = part[:-2]
        if not part:
            line_no += int(break_after)
            continue
        if pending is None:
            raise DerivedAssError(f"文本片段没有对应的 \\kNN: {part!r}")
        main, kana = part.split("|", 1) if "|" in part else (part, "")
        kana = kana.removeprefix("<")
        end = current + pending * 0.01
        if main == "#":
            if last_main is None:
                raise DerivedAssError("假名续接符 # 出现在首个主字之前")
            tokens[last_main]["end"] = end
            tokens[last_main]["dur_cs"] += pending
            tokens.append(
                {
                    "type": "kana",
                    "text": kana,
                    "start": current,
                    "end": end,
                    "dur_cs": pending,
                    "line": line_no,
                }
            )
        else:
            last_main = len(tokens)
            tokens.append(
                {
                    "type": "main",
                    "text": main,
                    "start": current,
                    "end": end,
                    "dur_cs": pending,
                    "line": line_no,
                }
            )
            if kana:
                tokens.append(
                    {
                        "type": "kana",
                        "text": kana,
                        "start": current,
                        "end": end,
                        "dur_cs": pending,
                        "line": line_no,
                    }
                )
        current, pending = end, None
        line_no += int(break_after)
    if pending is not None:
        raise DerivedAssError("Dialogue 末尾存在没有文本的 \\kNN")
    return tokens


def rebuild_dialogues(raw: list[dict]) -> list[dict]:
    result: list[dict] = []
    for source in raw:
        tokens = tokenize_dialogue(source["start"], source["text_raw"])
        if not any(token["type"] == "main" and token["text"] for token in tokens):
            continue
        result.append(
            {"i": len(result), "start": source["start"], "end": source["end"], "tokens": tokens}
        )
    if not result:
        raise DerivedAssError("源 ASS 中只有空歌词行")
    return result


def visible_text(dialogue: dict) -> str:
    output: list[str] = []
    current_line = 0
    for token in (item for item in dialogue["tokens"] if item["type"] == "main"):
        output.extend("\n" for _ in range(max(0, token["line"] - current_line)))
        output.append(token["text"])
        current_line = token["line"]
    return "".join(output)


def compute_display_windows(dialogues: list[dict], audio_end: float) -> list[dict]:
    for index, line in enumerate(dialogues):
        line["display_start"] = line["start"] - 2 if index == 0 else dialogues[index - 1]["start"]
        if index == len(dialogues) - 1:
            line["display_end"], line["long_interlude"] = min(line["end"] + 3, audio_end), False
        elif dialogues[index + 1]["start"] - line["end"] >= 8:
            line["display_end"], line["long_interlude"] = line["end"] + 1, True
            dialogues[index + 1]["display_start_override"] = dialogues[index + 1]["start"] - 2
        else:
            line["display_end"], line["long_interlude"] = dialogues[index + 1]["start"], False
    for line in dialogues:
        if "display_start_override" in line:
            line["display_start"] = line.pop("display_start_override")
    return dialogues


class FontMeasurer:
    def __init__(self) -> None:
        self.cache: dict[tuple[str, int, str], int] = {}
        self.fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def width(self, path: str, size: int, text: str) -> int:
        key = (path, size, text)
        if key not in self.cache:
            if not text:
                self.cache[key] = 0
            else:
                font_key = (path, size)
                if font_key not in self.fonts:
                    self.fonts[font_key] = ImageFont.truetype(path, size)
                box = self.fonts[font_key].getbbox(text)
                self.cache[key] = box[2] - box[0]
        return self.cache[key]


def compute_sentence_layout(measurer: FontMeasurer, dialogue: dict) -> dict:
    kana_size = max(round(MAIN_FONT * KANA_FONT_RATIO), 28)
    chars: list[dict] = []
    for token in dialogue["tokens"]:
        if token["type"] == "main":
            chars.append(
                {"text": token["text"], "kana_text": "", "kana_tokens": [], "line": token["line"]}
            )
        elif chars:
            chars[-1]["kana_tokens"].append(dict(token))
            chars[-1]["kana_text"] += token["text"]
    for char in chars:
        char["char_w"] = measurer.width(FONT_PATH, MAIN_FONT, char["text"])
        char["kana_w"] = measurer.width(FONT_PATH, kana_size, char["kana_text"])
        char["slot_w"] = max(char["char_w"], char["kana_w"] + 6)
    widths = {
        line: sum(c["slot_w"] for c in chars if c["line"] == line)
        for line in {c["line"] for c in chars}
    }
    return {
        "kana_size": kana_size,
        "main_chars": chars,
        "total_width": max(widths.values(), default=0),
        "measurer": measurer,
    }


def assign_x_positions(layout: dict, side: str, margin: float) -> None:
    for line_no in sorted({char["line"] for char in layout["main_chars"]}):
        line = [char for char in layout["main_chars"] if char["line"] == line_no]
        width = sum(char["slot_w"] for char in line)
        x = margin if side == "left" else CANONICAL_W - margin - width
        for char in line:
            char["main_left"] = x + (char["slot_w"] - char["char_w"]) / 2
            char["main_right"] = char["main_left"] + char["char_w"]
            kana_x = char["main_left"] + (char["char_w"] - char["kana_w"]) / 2
            for kana in char["kana_tokens"]:
                kana_width = layout["measurer"].width(FONT_PATH, layout["kana_size"], kana["text"])
                kana["left"], kana["right"] = kana_x, kana_x + kana_width
                kana_x += kana_width
            x += char["slot_w"]


def _token_events(
    text: str,
    font_size: int,
    y: float,
    left: float,
    right: float,
    display_start: float,
    display_end: float,
    token_start: float,
    token_end: float,
    theme: KaraokeTheme,
    canvas: Canvas,
    time_offset: float,
) -> list[str]:
    # Complementary clips remove the unsung black border as the white border advances.
    fs = canvas.size(font_size)
    border = canvas.size(APPEARANCE["outline"])
    xc, py = canvas.x((left + right) / 2), canvas.y(y)
    xl, xr = canvas.x(left - 6), canvas.x(right + 6)
    sung = to_bgr_ass(theme.sung)
    prefix = f"\\an5\\pos({xc:.2f},{py:.2f})\\fs{fs:.2f}\\b{BOLD}\\bord{border:.2f}\\shad0"
    events = []

    def emit(start: float, end: float, tags: str, style: str) -> None:
        start, end = max(0, start + time_offset), max(0, end + time_offset)
        if end > start:
            events.append(
                f"Dialogue: 6,{fmt_ass_time(start)},{fmt_ass_time(end)},{style},,0,0,0,,{{{prefix}{tags}}}{text}"
            )

    white = f"\\1c{to_bgr_ass(theme.unsung_fill)}\\3c{to_bgr_ass(theme.unsung_outline)}"
    colored = f"\\1c{sung}\\3c{to_bgr_ass(theme.sung_outline)}"
    emit(display_start, min(token_start, display_end), white, "Outline")
    end = min(token_end, display_end)
    if end > token_start:
        duration = round((end - token_start) * 1000)
        emit(
            token_start,
            end,
            white
            + f"\\clip({xl:.2f},0,{canvas.width},{canvas.height})\\t(0,{duration},\\clip({xr:.2f},0,{canvas.width},{canvas.height}))",
            "Outline",
        )
        emit(
            token_start,
            end,
            colored
            + f"\\clip(0,0,{xl:.2f},{canvas.height})\\t(0,{duration},\\clip(0,0,{xr:.2f},{canvas.height}))",
            "Fill",
        )
    emit(max(token_end, display_start), display_end, colored, "Fill")
    return events


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def generate_derived_ass(
    source: Path,
    output: Path,
    *,
    title_text: str,
    audio_end: float,
    theme: KaraokeTheme,
    canvas: Canvas | None = None,
    placement: KaraokePlacement | None = None,
    subtitle_offset: float = 0.0,
) -> DerivedAssReport:
    if not source.is_file():
        raise DerivedAssError(f"源 ASS 不存在: {source}")
    if source.resolve() == output.resolve():
        raise DerivedAssError("派生 ASS 不得覆盖源 ASS")
    if audio_end <= 0:
        raise DerivedAssError("audio_end 必须大于 0")
    canvas, placement = canvas or parse_source_play_res(source), placement or KaraokePlacement()
    dialogues = rebuild_dialogues(tokenize_ass(source))
    if dialogues[-1]["end"] > audio_end + 0.01:
        raise DerivedAssError(
            f"最后一句结束时间 {fmt_ass_time(dialogues[-1]['end'])} 超过音频结束时间 {fmt_ass_time(audio_end)}"
        )
    compute_display_windows(dialogues, audio_end)
    measurer, layouts, overwide, max_width = FontMeasurer(), [], [], 0
    for dialogue in dialogues:
        layout = compute_sentence_layout(measurer, dialogue)
        layouts.append(layout)
        max_width = max(max_width, layout["total_width"])
        if layout["total_width"] > USABLE_W:
            overwide.append(
                OverwideLine(
                    dialogue["i"],
                    visible_text(dialogue),
                    dialogue["start"],
                    dialogue["end"],
                    layout["total_width"],
                )
            )
    if overwide:
        raise OverwideError(overwide)
    for index, layout in enumerate(layouts):
        assign_x_positions(layout, "left" if index % 2 == 0 else "right", placement.margin_x)
    events: list[str] = []
    for index, (dialogue, layout) in enumerate(zip(dialogues, layouts, strict=True)):
        base_y = placement.top_y if index % 2 == 0 else placement.bottom_y
        split = len({char["line"] for char in layout["main_chars"]}) > 1
        mains = [token for token in dialogue["tokens"] if token["type"] == "main"]
        kanas = [token for token in dialogue["tokens"] if token["type"] == "kana"]
        for token, char in zip(mains, layout["main_chars"], strict=True):
            y = base_y + char["line"] * 110 - (55 if split else 0)
            events.extend(
                _token_events(
                    char["text"],
                    MAIN_FONT,
                    y,
                    char["main_left"],
                    char["main_right"],
                    dialogue["display_start"],
                    dialogue["display_end"],
                    token["start"],
                    token["end"],
                    theme,
                    canvas,
                    subtitle_offset,
                )
            )
        positioned_kanas = [kana for char in layout["main_chars"] for kana in char["kana_tokens"]]
        for token, kana in zip(kanas, positioned_kanas, strict=True):
            y = (
                base_y
                + token["line"] * 110
                - (55 if split else 0)
                - round(MAIN_FONT * KANA_RISE_RATIO)
            )
            events.extend(
                _token_events(
                    token["text"],
                    layout["kana_size"],
                    y,
                    kana["left"],
                    kana["right"],
                    dialogue["display_start"],
                    dialogue["display_end"],
                    token["start"],
                    token["end"],
                    theme,
                    canvas,
                    subtitle_offset,
                )
            )
    sung, outline = to_bgr_ass(theme.title_fill or theme.sung), to_bgr_ass(theme.unsung_outline)
    if title_text.strip():
        events.append(
            f"Dialogue: 9,{fmt_ass_time(dialogues[0]['display_start'] + subtitle_offset)},{fmt_ass_time(dialogues[-1]['display_end'] + subtitle_offset)},Title,,0,0,0,,{{\\an9\\pos({canvas.x(CANONICAL_W - placement.margin_x):.2f},{canvas.y(APPEARANCE['title_y']):.2f})\\fs{canvas.size(TITLE_FONT):.2f}\\1c{sung}\\3c{to_bgr_ass(theme.title_outline)}\\bord{canvas.size(APPEARANCE['title_outline']):.2f}\\shad0}}{_escape_ass_text(title_text)}"
        )
    style_format = "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    lines = [
        "[Script Info]",
        f"; Derived karaoke theme: {theme.label}",
        "; Generated by Karaoke Studio; source ASS is unchanged",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        f"PlayResX: {canvas.width}",
        f"PlayResY: {canvas.height}",
        "",
        "[V4+ Styles]",
        style_format,
        f"Style: Outline,{FONT_NAME},{canvas.size(MAIN_FONT):.2f},&H00FFFFFF,&H00FFFFFF,{outline},&H80000000&,0,0,0,0,100,100,{canvas.size(1):.2f},0,1,{canvas.size(APPEARANCE['outline']):.2f},0,5,0,0,0,1",
        f"Style: Fill,{FONT_NAME},{canvas.size(MAIN_FONT):.2f},&H00FFFFFF&,&H00FFFFFF&,&H00FFFFFF&,&H00FFFFFF&,0,0,0,0,100,100,{canvas.size(1):.2f},0,1,0,0,5,0,0,0,1",
        f"Style: Title,{FONT_NAME},{canvas.size(TITLE_FONT):.2f},{sung},{sung},&H00FFFFFF&,&H00000000&,0,0,0,0,100,100,0,0,1,{canvas.size(APPEARANCE['title_outline']):.2f},0,9,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
    ]
    _atomic_write(output, "\n".join(lines) + "\n")
    return DerivedAssReport(
        len(dialogues),
        len(events),
        sum(bool(d["long_interlude"]) for d in dialogues),
        max_width,
        MAIN_FONT,
        output,
        canvas.width,
        canvas.height,
    )


def _translation_events(
    source: Path,
    sidecar: Path,
    *,
    theme: KaraokeTheme,
    canvas: Canvas,
    placement: TranslationPlacement,
    subtitle_offset: float,
) -> tuple[list[str], int, int]:
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DerivedAssError(f"无法读取中文字幕 sidecar: {sidecar}: {exc}") from exc
    if payload.get("schema_version") != 1 or payload.get("language") != "zh-Hans":
        raise DerivedAssError("中文字幕 sidecar 必须为 schema_version=1、language=zh-Hans")
    dialogues = rebuild_dialogues(tokenize_ass(source))
    lines = payload.get("lines")
    if not isinstance(lines, list) or len(lines) != len(dialogues):
        raise DerivedAssError(
            f"中文字幕条数必须等于日文 Dialogue 数: zh={len(lines) if isinstance(lines, list) else 'invalid'}, ja={len(dialogues)}"
        )
    measurer, accepted, overwide, max_width = FontMeasurer(), [], [], 0
    for index, (entry, dialogue) in enumerate(zip(lines, dialogues, strict=True)):
        if not isinstance(entry, dict) or entry.get("index") != index:
            raise DerivedAssError(f"中文字幕下标必须连续；期望 {index}")
        expected = visible_text(dialogue)
        if entry.get("source_text") != expected:
            raise DerivedAssError(
                f"中文字幕 source_text 不匹配，index={index}: expected={expected!r}, actual={entry.get('source_text')!r}"
            )
        translated = entry.get("text")
        if not isinstance(translated, str):
            raise DerivedAssError(f"中文字幕 text 必须为字符串，index={index}")
        end_index = entry.get("end_index", index)
        if not isinstance(end_index, int) or not index <= end_index < len(dialogues):
            raise DerivedAssError(f"中文字幕 end_index 无效，index={index}: {end_index!r}")
        if not translated:
            continue
        for visual in translated.splitlines() or [translated]:
            width = measurer.width(ZH_FONT_PATH, CHINESE_FONT, visual)
            max_width = max(max_width, width)
            if width > USABLE_W:
                overwide.append(
                    OverwideLine(
                        index, translated, dialogue["start"], dialogue["end"], width, CHINESE_FONT
                    )
                )
        accepted.append((dialogue, translated, dialogues[end_index]["end"]))
    if overwide:
        raise OverwideError(overwide)
    alignment, x, y = placement.resolved()
    glow, events = to_bgr_ass(theme.sung), []
    for dialogue, translated, end in accepted:
        fade = min(160, round((dialogue["end"] - dialogue["start"]) * 500))
        common = f"\\an{alignment}\\pos({canvas.x(x):.2f},{canvas.y(y):.2f})\\fs{canvas.size(CHINESE_FONT):.2f}\\fad({fade},{fade})"
        text = _escape_ass_text(translated)
        events.extend(
            [
                f"Dialogue: 10,{fmt_ass_time(dialogue['start'] + subtitle_offset)},{fmt_ass_time(end + subtitle_offset)},ChineseGlow,,0,0,0,,{{{common}\\1a&HFF&\\3c{glow}\\bord{canvas.size(APPEARANCE['chinese_glow']):.2f}\\blur{canvas.size(APPEARANCE['chinese_blur']):.2f}\\shad0}}{text}",
                f"Dialogue: 11,{fmt_ass_time(dialogue['start'] + subtitle_offset)},{fmt_ass_time(end + subtitle_offset)},ChineseText,,0,0,0,,{{{common}\\1c&H00FFFFFF&\\3c&H00000000&\\bord{canvas.size(APPEARANCE['chinese_outline']):.2f}\\shad0}}{text}",
            ]
        )
    return events, len(accepted), max_width


def generate_translation_variants(
    source: Path,
    karaoke_ass: Path,
    sidecar: Path,
    *,
    combined_output: Path,
    zh_only_output: Path,
    theme: KaraokeTheme,
    canvas: Canvas,
    placement: TranslationPlacement | None = None,
    subtitle_offset: float = 0.0,
) -> TranslationAssReport:
    protected = {source.resolve(), karaoke_ass.resolve(), sidecar.resolve()}
    if (
        combined_output.resolve() in protected
        or zh_only_output.resolve() in protected
        or combined_output.resolve() == zh_only_output.resolve()
    ):
        raise DerivedAssError("中文字幕派生 ASS 不得覆盖输入或彼此覆盖")
    events, count, max_width = _translation_events(
        source,
        sidecar,
        theme=theme,
        canvas=canvas,
        placement=placement or TranslationPlacement(),
        subtitle_offset=subtitle_offset,
    )
    glow = to_bgr_ass(theme.sung)
    style_format = "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    styles = [
        f"Style: ChineseGlow,{ZH_FONT_NAME},{canvas.size(CHINESE_FONT):.2f},&HFFFFFFFF&,&HFFFFFFFF&,{glow},&H00000000&,0,0,0,0,100,100,0,0,1,{canvas.size(APPEARANCE['chinese_glow']):.2f},0,1,0,0,0,1",
        f"Style: ChineseText,{ZH_FONT_NAME},{canvas.size(CHINESE_FONT):.2f},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,{canvas.size(APPEARANCE['chinese_outline']):.2f},0,1,0,0,0,1",
    ]
    karaoke = karaoke_ass.read_text(encoding="utf-8")
    marker = "\n[Events]\n"
    if marker not in karaoke:
        raise DerivedAssError(f"派生 ASS 缺少 [Events]: {karaoke_ass}")
    combined = (
        karaoke.replace(marker, "\n" + "\n".join(styles) + marker, 1).rstrip()
        + "\n"
        + "\n".join(events)
        + "\n"
    )
    zh_only = "\n".join(
        [
            "[Script Info]",
            "; Chinese translation derived by Karaoke Studio",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            f"PlayResX: {canvas.width}",
            f"PlayResY: {canvas.height}",
            "",
            "[V4+ Styles]",
            style_format,
            *styles,
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )
    _atomic_write(combined_output, combined)
    _atomic_write(zh_only_output, zh_only)
    return TranslationAssReport(count, max_width, combined_output, zh_only_output)
