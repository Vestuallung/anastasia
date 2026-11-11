"""Structured editor scene: no ASS serialization or ASS playback in the preview."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .ass import _display_units
from .config import section
from .derived_ass import (
    APPEARANCE,
    CANONICAL_H,
    CANONICAL_W,
    CHINESE_FONT,
    COUNTDOWN_RADIUS,
    COUNTDOWN_SPACING,
    KANA_FONT_RATIO,
    KANA_RISE_RATIO,
    MAIN_FONT,
    TITLE_FONT,
    Canvas,
    FontMeasurer,
    TranslationPlacement,
    _countdown_anchor,
    _katakana_ruby,
    _load_translation,
    _prepare_countdowns,
    assign_x_positions,
    compute_display_windows,
    compute_sentence_layout,
)
from .lyrics import build_line
from .media_render import parse_media_time, resolve_output_canvas, write_record
from .models import LineState, ReadingSource
from .mora import is_kana
from .project_io import load_project, save_project
from .themes import resolve_theme
from .timing import effective_boundaries

MEASURER = FontMeasurer()


class EditorPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    playback_speed: Literal[0.5, 0.75, 1, 1.25, 1.5, 2] = 0.75
    preserve_pitch: bool = True
    loop: Literal["line", "off"] = "line"
    lead_ms: int = Field(default=250, ge=0, le=2000)
    snap: bool = True
    snap_ms: Literal[1, 5, 10, 20, 50, 100] = 10
    key_step_ms: Literal[1, 5, 10, 20, 50, 100] = 10
    seek_large_ms: Literal[100, 250, 500, 1000] = 1000
    show_waveform: bool = True
    show_characters: bool = True
    show_readings: bool = True


def preferences(root: Path) -> EditorPreferences:
    path = root / ".karaoke-work/EditorPreferences-11月7日.json"
    for candidate in (path, path.with_suffix(".json.bak")):
        try:
            return EditorPreferences.model_validate_json(candidate.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            continue
    return EditorPreferences()


def save_preferences(root: Path, value: EditorPreferences) -> None:
    path = root / ".karaoke-work/EditorPreferences-11月7日.json"
    if path.is_file():
        try:
            previous = EditorPreferences.model_validate_json(path.read_text(encoding="utf-8"))
            write_record(path.with_suffix(".json.bak"), previous.model_dump())
        except (OSError, ValidationError):
            pass
    write_record(path, value.model_dump())


def merged_settings(root: Path, updates: dict) -> dict:
    current = deepcopy(settings(root))
    for key, value in updates.items():
        if key == "colors" and value == {}:
            current[key] = {}
        elif isinstance(value, dict) and isinstance(current.get(key), dict):
            current[key].update(value)
        else:
            current[key] = value
    return current


def preview_settings(root: Path, updates: dict) -> dict:
    from .render_job import RenderJob

    candidate = merged_settings(root, updates)
    if "source_ass" in candidate:
        candidate = RenderJob.model_validate(candidate).model_dump(mode="json")
    return scene(root, config=candidate)


def settings(root: Path) -> dict:
    path = root / "render-job.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    local = root / ".karaoke-work/editor-settings.json"
    if local.is_file():
        payload.update(json.loads(local.read_text(encoding="utf-8")))
    return payload


@lru_cache(maxsize=16)
def video_canvas(
    path: str, size: int, modified: int, mode: str, width: int | None, height: int | None
) -> Canvas:
    return resolve_output_canvas(
        Path(path), frame_mode=mode, target_width=width, target_height=height
    )


def scene(root: Path, project=None, *, config: dict | None = None) -> dict:
    project = project or load_project(root)
    config = settings(root) if config is None else config
    theme = resolve_theme(
        config.get("theme", section("production")["default_theme"]), config.get("colors", {})
    )
    layout = {**section("layout"), **config.get("layout", {})}
    media = config.get("media", {})
    canvas = Canvas()
    video = root / project.source.video_path if project.source.video_path else None
    if video and video.is_file() and project.raw_alignment:
        info = video.stat()
        frame = media.get("frame", {})
        canvas = video_canvas(
            str(video.resolve()),
            info.st_size,
            info.st_mtime_ns,
            frame.get("mode", "preserve"),
            frame.get("target_width"),
            frame.get("target_height"),
        )
    dialogues, line_bounds = [], {}
    for line in project.lines:
        bounds = effective_boundaries(project, line.id)
        line_bounds[line.id] = bounds
        if len(bounds) != len(line.moras) + 1 or not line.moras:
            continue
        tokens = []
        current = bounds[0] / 1000
        for display in line.display_tokens:
            indices = [
                i for i, mora in enumerate(line.moras) if mora.display_token_id == display.id
            ]
            explicit = any(
                g.source in (ReadingSource.RUBY, ReadingSource.USER, ReadingSource.AGENT)
                and display.id in g.display_token_ids
                for g in line.ruby_groups
            )
            if not indices:
                tokens.append(
                    dict(
                        type="main",
                        text=display.text,
                        start=current,
                        end=current,
                        dur_cs=0,
                        line=0,
                        mora_indices=[],
                    )
                )
                continue
            cursor = 0
            for unit, count in _display_units(display.text, len(indices)):
                selected = indices[cursor : cursor + count]
                begin = bounds[selected[0]] / 1000 if selected else current
                finish = bounds[selected[-1] + 1] / 1000 if selected else current
                tokens.append(
                    dict(
                        type="main",
                        text=unit,
                        start=begin,
                        end=finish,
                        dur_cs=(finish - begin) * 100,
                        line=0,
                        mora_indices=selected,
                    )
                )
                if selected and (not is_kana(unit) or explicit):
                    for i in selected:
                        tokens.append(
                            dict(
                                type="kana",
                                text=line.moras[i].kana,
                                start=bounds[i] / 1000,
                                end=bounds[i + 1] / 1000,
                                dur_cs=(bounds[i + 1] - bounds[i]) / 10,
                                line=0,
                                mora_index=i,
                            )
                        )
                current = finish
                cursor += count
        if config.get("katakana_ruby", True):
            tokens, _ = _katakana_ruby(tokens)
        dialogues.append(
            dict(
                i=line.source_index,
                line_id=line.id,
                start=bounds[0] / 1000,
                end=bounds[-1] / 1000,
                tokens=tokens,
                paragraph_start=bool(line.paragraph_before),
            )
        )
    duration = (project.audio.duration_ms or 0) / 1000
    if dialogues:
        compute_display_windows(dialogues, duration or max(d["end"] for d in dialogues))
    countdown_indices, _ = (
        _prepare_countdowns(dialogues, config.get("subtitle_offset", 0))
        if config.get("countdown", True)
        else (set(), 0)
    )
    offset = config.get("subtitle_offset", 0) * 1000
    result = []
    for index, d in enumerate(dialogues):
        drawing = compute_sentence_layout(MEASURER, d)
        assign_x_positions(
            drawing, "left" if index % 2 == 0 else "right", layout.get("margin_x", 110)
        )
        base_y = layout.get("top_y", 750) if index % 2 == 0 else layout.get("bottom_y", 950)
        split = len({char["line"] for char in drawing["main_chars"]}) > 1
        first_y = base_y - (55 if split else 0)
        countdown_position = None
        if index in countdown_indices:
            left, dot_y = _countdown_anchor(drawing, first_y)
            countdown_position = {
                "left": left, "y": dot_y, "radius": COUNTDOWN_RADIUS, "spacing": COUNTDOWN_SPACING,
            }
        mains = [t for t in d["tokens"] if t["type"] == "main"]
        glyphs = []
        for token, char in zip(mains, drawing["main_chars"], strict=True):
            y = first_y + char["line"] * 110
            kana = [
                {
                    **k,
                    "start_ms": k["start"] * 1000 + offset,
                    "end_ms": k["end"] * 1000 + offset,
                    "y": y - round(MAIN_FONT * KANA_RISE_RATIO),
                }
                for k in char["kana_tokens"]
            ]
            glyphs.append(
                dict(
                    text=char["text"],
                    left=char["main_left"],
                    right=char["main_right"],
                    y=y,
                    start_ms=token["start"] * 1000 + offset,
                    end_ms=token["end"] * 1000 + offset,
                    mora_indices=token["mora_indices"],
                    kana=kana,
                )
            )
        result.append(
            dict(
                id=d["line_id"],
                index=d["i"],
                start_ms=d["start"] * 1000 + offset,
                end_ms=d["end"] * 1000 + offset,
                display_start_ms=max(0, d["display_start"] * 1000 + offset),
                display_end_ms=d["display_end"] * 1000 + offset,
                glyphs=glyphs,
                width=drawing["total_width"],
                paragraph_start=d["paragraph_start"],
                countdown=index in countdown_indices,
                countdown_position=countdown_position,
            )
        )
    translations = {}
    translation_events = []
    translation = config.get("translation")
    if translation:
        path = Path(translation["file"])
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            try:
                entries = _load_translation(path)["lines"]
                translations = {
                    line.id: entries[i]["text"]
                    for i, line in enumerate(project.lines)
                    if i < len(entries)
                }
                placement = TranslationPlacement(
                    translation.get("position", "top_left"),
                    translation.get("alignment"),
                    translation.get("x"),
                    translation.get("y"),
                ).resolved()
                for i, line in enumerate(project.lines):
                    if i >= len(entries) or not entries[i].get("text"):
                        continue
                    bounds = line_bounds[line.id]
                    end_index = entries[i].get("end_index", i)
                    if not bounds or not i <= end_index < len(project.lines):
                        continue
                    end_bounds = line_bounds[project.lines[end_index].id]
                    if not end_bounds:
                        continue
                    translation_events.append(
                        dict(
                            line_id=line.id,
                            text=entries[i]["text"],
                            start_ms=bounds[0] + offset,
                            end_ms=end_bounds[-1] + offset,
                            alignment=placement[0],
                            x=placement[1],
                            y=placement[2],
                        )
                    )
                for i, event in enumerate(translation_events[:-1]):
                    event["end_ms"] = min(event["end_ms"], translation_events[i + 1]["start_ms"])
            except ValueError:
                pass

    def hexcolor(color):
        return "#" + "".join(f"{c:02X}" for c in color)

    return dict(
        lines=result,
        canvas=dict(width=canvas.width, height=canvas.height),
        theme=theme.name,
        typography=dict(
            width=CANONICAL_W,
            height=CANONICAL_H,
            main=MAIN_FONT,
            reading=round(MAIN_FONT * KANA_FONT_RATIO),
            title=TITLE_FONT,
            chinese=CHINESE_FONT,
            title_y=APPEARANCE["title_y"],
            outline=APPEARANCE["outline"],
            title_outline=APPEARANCE["title_outline"],
            chinese_outline=APPEARANCE["chinese_outline"],
            bold=APPEARANCE["bold"],
        ),
        title_text=config.get("title_text", ""),
        colors=dict(
            sung=hexcolor(theme.sung),
            unsung_fill=hexcolor(theme.unsung_fill),
            unsung_outline=hexcolor(theme.unsung_outline),
            sung_outline=hexcolor(theme.sung_outline),
            title_fill=hexcolor(theme.title_fill or theme.sung),
            title_outline=hexcolor(theme.title_outline),
        ),
        layout=layout,
        blackout=media.get("blackout", []),
        video_bitrate_mbps=media.get("video_bitrate_mbps"),
        countdown=config.get("countdown", True),
        katakana_ruby=config.get("katakana_ruby", True),
        translations=translations,
        translation_events=translation_events,
        subtitle_offset_ms=offset,
        video_offset_ms=parse_media_time(media.get("trim_start", 0)) * 1000,
        audio_offset_ms=0
        if project.audio.prepared_path
        else parse_media_time(media.get("trim_start", 0)) * 1000,
    )


def save_settings(root: Path, updates: dict) -> None:
    current = merged_settings(root, updates)
    from .render_job import RenderJob, load_render_job, sync_production_request

    project = load_project(root)
    if "source_ass" not in current:
        defaults = dict(
            source_ass=str(root / "EditorSource-11月7日.ass"),
            output_ass=str(root / "EditorOutput-11月7日.ass"),
            theme=section("production")["default_theme"],
            audio_end=(project.audio.duration_ms or 1000) / 1000,
            media=dict(
                video=str(root / project.source.video_path) if project.source.video_path else "",
                audio=str(root / (project.audio.prepared_path or project.source.audio_path or "")),
                trim_end=(project.audio.duration_ms or 1000) / 1000,
                output_dir=str(root),
            ),
        )
        media = {**defaults["media"], **current.get("media", {})}
        current = {**defaults, **current, "media": media}
    validated = RenderJob.model_validate(current)
    write_record(root / "render-job.json", validated.model_dump(mode="json"))
    local = root / ".karaoke-work/editor-settings.json"
    local.unlink(missing_ok=True)
    sync_production_request(load_render_job(root / "render-job.json"), root / "render-job.json")


def edit_text(root: Path, line_id: str, text: str, commit: bool = True) -> dict:
    project = load_project(root)
    old = next((line for line in project.lines if line.id == line_id), None)
    if old is None:
        raise ValueError("找不到歌词")
    if not text.strip() or "\n" in text or "\r" in text:
        raise ValueError("请编辑单句歌词")
    replacement = build_line(text, old.source_index, paragraph_before=old.paragraph_before)
    unchanged = [m.romaji for m in replacement.moras] == [m.romaji for m in old.moras]
    if not unchanged:
        if commit and project.raw_alignment:
            original_path = root / ".karaoke-work/editor-original-alignment.json"
            if not original_path.exists():
                write_record(original_path, project.raw_alignment.model_dump(mode="json"))
        project.alignment_stale = True
        # Draft text previews use the old phrase interval as a temporary layout.
        from .models import RawAlignedLine
        from .timing import quantized_k_values

        bounds = effective_boundaries(project, line_id)
        if project.raw_alignment and bounds and replacement.moras:
            temporary = [
                round(bounds[0] + (bounds[-1] - bounds[0]) * i / len(replacement.moras))
                for i in range(len(replacement.moras) + 1)
            ]
            for i, raw in enumerate(project.raw_alignment.lines):
                if raw.line_id == line_id:
                    project.raw_alignment.lines[i] = RawAlignedLine(
                        line_id=line_id,
                        start_ms=bounds[0],
                        end_ms=bounds[-1],
                        k_values_cs=quantized_k_values(temporary),
                        labels=[m.romaji for m in replacement.moras],
                    )
            project.timing_patches = [p for p in project.timing_patches if p.line_id != line_id]
    replacement.id = old.id
    replacement.state = old.state if unchanged else LineState.STALE
    project.lines[project.lines.index(old)] = replacement
    if commit:
        save_project(root, project)
        translation = settings(root).get("translation")
        if translation:
            source = Path(translation["file"])
            source = source if source.is_absolute() else root / source
            if source.is_file():
                payload = _load_translation(source)
                entries = payload.get("lines", [])
                if len(entries) == len(project.lines):
                    changed = False
                    for entry, line in zip(entries, project.lines, strict=True):
                        visible = "".join(token.text for token in line.display_tokens)
                        if entry.get("source_text") != visible:
                            entry.update(source_text=visible, annotated_source_text=line.original)
                            changed = True
                    if changed:
                        local = root / "EditorTranslation-11月7日.json"
                        write_record(local, payload)
                        save_settings(root, {"translation": {"file": str(local)}})
        request_path = root / ".karaoke-work/production-request.json"
        if request_path.is_file():
            original = (
                "\n".join("\n" * line.paragraph_before + line.original for line in project.lines)
                + "\n"
            )
            edited = root / "EditedLyrics-11月7日.txt"
            edited.write_text(original, encoding="utf-8")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["lyrics"] = str(edited)
            write_record(request_path, request)
            state_path = root / ".karaoke-work/production-state.json"
            if state_path.is_file():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state.setdefault("lyrics", {}).update(text=original, format=".txt")
                state["line_texts"] = [line.original for line in project.lines]
                write_record(state_path, state)
    return scene(root, project)
