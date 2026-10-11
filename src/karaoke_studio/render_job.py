from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import section
from .derived_ass import (
    Canvas,
    DerivedAssError,
    DerivedAssReport,
    KaraokePlacement,
    TranslationAssReport,
    TranslationPlacement,
    generate_derived_ass,
    generate_translation_variants,
    parse_source_play_res,
)
from .media_render import MediaRenderReport, parse_media_time, render_outputs, resolve_output_canvas
from .themes import resolve_theme

OutputName = Literal[
    "on_vocal_karaoke",
    "off_vocal_karaoke",
    "on_vocal_karaoke_zh",
    "on_vocal_zh_only",
]


class FrameSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["preserve", "pad"] = "preserve"
    target_width: int | None = Field(default=None, gt=0)
    target_height: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target(self) -> FrameSettings:
        if self.mode == "pad" and (self.target_width is None or self.target_height is None):
            raise ValueError("pad 模式必须提供 target_width 和 target_height")
        return self


class MediaSettings(BaseModel):
    """Media inputs. Old mode/audio/output fields remain accepted for job-file compatibility."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["on_vocal", "matched_external"] = "on_vocal"
    video: Path
    audio: Path | None = None
    external_audio: Path | None = None
    match_reference_audio: Path | None = None
    trim_start: str | float = 0
    trim_end: str | float
    output_dir: Path | None = None
    on_vocal_output: Path | None = None
    off_vocal_output: Path | None = None
    frame: FrameSettings = Field(default_factory=FrameSettings)
    pad_to_1080p: bool = False
    prefer_early_seconds: float | None = Field(default=None, gt=8)
    minimum_correlation: float = Field(default=0.60, ge=-1, le=1)
    minimum_margin: float = Field(default=0.03, ge=0, le=2)

    @model_validator(mode="after")
    def normalize_legacy(self) -> MediaSettings:
        if self.mode == "matched_external" and self.external_audio is None:
            raise ValueError("matched_external 必须提供 external_audio")
        if self.pad_to_1080p:
            self.frame = FrameSettings(mode="pad", target_width=1920, target_height=1080)
        return self


class LayoutSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canvas_mode: Literal["auto", "video", "source_ass", "fixed"] = "auto"
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    margin_x: float = Field(default_factory=lambda: section("layout")["margin_x"], ge=0)
    top_y: float = Field(default_factory=lambda: section("layout")["top_y"], ge=0)
    bottom_y: float = Field(default_factory=lambda: section("layout")["bottom_y"], ge=0)

    @model_validator(mode="after")
    def validate_fixed(self) -> LayoutSettings:
        if self.canvas_mode == "fixed" and (self.width is None or self.height is None):
            raise ValueError("fixed 画布必须提供 width 和 height")
        return self


class TranslationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: Path
    combined_ass: Path | None = None
    zh_only_ass: Path | None = None
    position: Literal["bottom_left", "bottom_center", "bottom_right", "custom"] = "bottom_left"
    alignment: int | None = None
    x: float | None = None
    y: float | None = None


class RenderJob(BaseModel):
    """Formal downstream job. Relative paths resolve from the JSON directory."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = Field(default=2, ge=1, le=2)
    source_ass: Path
    output_ass: Path
    theme: str = Field(default_factory=lambda: section("production")["default_theme"])
    colors: dict[str, str] = Field(default_factory=dict)
    reuse_outputs: bool = True
    title_text: str = ""
    audio_end: float = Field(gt=0)
    subtitle_offset: float = 0.0
    translation: TranslationSettings | None = None
    media: MediaSettings | None = None
    outputs: list[OutputName] | None = None
    layout: LayoutSettings = Field(default_factory=LayoutSettings)

    @model_validator(mode="after")
    def unique_outputs(self) -> RenderJob:
        resolve_theme(self.theme, self.colors)
        if self.outputs is not None and len(set(self.outputs)) != len(self.outputs):
            raise ValueError("outputs 不得包含重复项")
        return self


def _absolute(base: Path, value: Path | None) -> Path | None:
    return None if value is None else value if value.is_absolute() else (base / value).resolve()


def load_render_job(path: Path) -> RenderJob:
    job = RenderJob.model_validate(json.loads(path.read_text(encoding="utf-8")))
    base = path.resolve().parent
    updates: dict[str, object] = {
        "source_ass": _absolute(base, job.source_ass),
        "output_ass": _absolute(base, job.output_ass),
    }
    if job.translation is not None:
        updates["translation"] = job.translation.model_copy(
            update={
                "file": _absolute(base, job.translation.file),
                "combined_ass": _absolute(base, job.translation.combined_ass),
                "zh_only_ass": _absolute(base, job.translation.zh_only_ass),
            }
        )
    if job.media is not None:
        updates["media"] = job.media.model_copy(
            update={
                field: _absolute(base, getattr(job.media, field))
                for field in (
                    "video",
                    "audio",
                    "external_audio",
                    "match_reference_audio",
                    "output_dir",
                    "on_vocal_output",
                    "off_vocal_output",
                )
            }
        )
    return job.model_copy(update=updates)


@dataclass(frozen=True)
class RenderJobReport:
    ass: DerivedAssReport
    translation: TranslationAssReport | None
    media: MediaRenderReport | None
    requested_outputs: tuple[OutputName, ...]
    timings: dict[str, float] = field(default_factory=dict)


def _canvas(job: RenderJob) -> Canvas:
    mode = job.layout.canvas_mode
    if job.media is not None:
        media_canvas = resolve_output_canvas(
            job.media.video,
            frame_mode=job.media.frame.mode,
            target_width=job.media.frame.target_width,
            target_height=job.media.frame.target_height,
        )
        if mode in ("auto", "video"):
            return media_canvas
        requested = (
            parse_source_play_res(job.source_ass)
            if mode == "source_ass"
            else Canvas(job.layout.width or 0, job.layout.height or 0)
        )
        if requested != media_canvas:
            raise DerivedAssError(
                f"ASS 画布 {requested.width}x{requested.height} 与实际视频输出 "
                f"{media_canvas.width}x{media_canvas.height} 不一致"
            )
        return requested
    if mode == "video":
        raise DerivedAssError("canvas_mode=video 需要 media.video")
    if mode == "fixed":
        return Canvas(job.layout.width or 0, job.layout.height or 0)
    return parse_source_play_res(job.source_ass)


def _available_outputs(job: RenderJob) -> set[OutputName]:
    if job.media is None:
        return set()
    available: set[OutputName] = {"on_vocal_karaoke"}
    if job.media.external_audio is not None:
        available.add("off_vocal_karaoke")
    if job.translation is not None:
        available.update(("on_vocal_karaoke_zh", "on_vocal_zh_only"))
    return available


def run_render_job(job: RenderJob) -> RenderJobReport:
    timings: dict[str, float] = {}
    available = _available_outputs(job)
    requested = (
        tuple(job.outputs)
        if job.outputs is not None
        else tuple(
            name
            for name in (
                "on_vocal_karaoke",
                "off_vocal_karaoke",
                "on_vocal_karaoke_zh",
                "on_vocal_zh_only",
            )
            if name in available
        )
    )
    unavailable = set(requested) - available
    if unavailable:
        raise DerivedAssError("请求的输出缺少对应输入: " + ", ".join(sorted(unavailable)))
    canvas = _canvas(job)
    theme = resolve_theme(job.theme, job.colors)
    begun = time.perf_counter()
    ass_report = generate_derived_ass(
        job.source_ass,
        job.output_ass,
        title_text=job.title_text,
        audio_end=job.audio_end,
        theme=theme,
        canvas=canvas,
        placement=KaraokePlacement(
            job.layout.margin_x,
            job.layout.top_y,
            job.layout.bottom_y,
        ),
        subtitle_offset=job.subtitle_offset,
    )
    timings["subtitle_expansion_seconds"] = round(time.perf_counter() - begun, 3)
    begun = time.perf_counter()
    translation_report = None
    combined_ass = job.output_ass.with_name(f"{job.output_ass.stem}_zh.ass")
    zh_only_ass = job.output_ass.with_name(f"{job.output_ass.stem}_zh_only.ass")
    needs_translation_ass = job.translation is not None and (
        job.outputs is None
        or bool({"on_vocal_karaoke_zh", "on_vocal_zh_only"}.intersection(requested))
    )
    if needs_translation_ass and job.translation is not None:
        combined_ass = job.translation.combined_ass or combined_ass
        zh_only_ass = job.translation.zh_only_ass or zh_only_ass
        translation_report = generate_translation_variants(
            job.source_ass,
            job.output_ass,
            job.translation.file,
            combined_output=combined_ass,
            zh_only_output=zh_only_ass,
            theme=theme,
            canvas=canvas,
            placement=TranslationPlacement(
                job.translation.position,
                job.translation.alignment,
                job.translation.x,
                job.translation.y,
            ),
            subtitle_offset=job.subtitle_offset,
        )
    timings["translation_seconds"] = round(time.perf_counter() - begun, 3)
    begun = time.perf_counter()
    media_report = None
    if job.media is not None and requested:
        output_dir = job.media.output_dir or job.output_ass.parent
        default_paths: dict[OutputName, Path] = {
            "on_vocal_karaoke": output_dir / "on_vocal_karaoke.mp4",
            "off_vocal_karaoke": output_dir / "off_vocal_karaoke.mp4",
            "on_vocal_karaoke_zh": output_dir / "on_vocal_karaoke_zh.mp4",
            "on_vocal_zh_only": output_dir / "on_vocal_zh_only.mp4",
        }
        if job.media.on_vocal_output is not None:
            default_paths["on_vocal_karaoke"] = job.media.on_vocal_output
        if job.media.off_vocal_output is not None:
            default_paths["off_vocal_karaoke"] = job.media.off_vocal_output
        ass_paths: dict[OutputName, Path] = {
            "on_vocal_karaoke": job.output_ass,
            "off_vocal_karaoke": job.output_ass,
            "on_vocal_karaoke_zh": combined_ass,
            "on_vocal_zh_only": zh_only_ass,
        }
        media_report = render_outputs(
            video=job.media.video,
            on_vocal_audio=job.media.audio,
            off_vocal_audio=job.media.external_audio,
            match_reference_audio=job.media.match_reference_audio,
            trim_start=parse_media_time(job.media.trim_start),
            trim_end=parse_media_time(job.media.trim_end),
            ass_by_output={name: ass_paths[name] for name in requested},
            output_paths={name: default_paths[name] for name in requested},
            frame_mode=job.media.frame.mode,
            target_width=job.media.frame.target_width,
            target_height=job.media.frame.target_height,
            prefer_early_seconds=job.media.prefer_early_seconds,
            minimum_correlation=job.media.minimum_correlation,
            minimum_margin=job.media.minimum_margin,
            reuse_outputs=job.reuse_outputs,
        )
    timings["media_seconds"] = round(time.perf_counter() - begun, 3)
    return RenderJobReport(ass_report, translation_report, media_report, requested, timings)
