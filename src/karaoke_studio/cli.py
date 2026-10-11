from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import typer

from .api import create_app
from .ass import export_ass
from .audio_match import AudioOpeningMatchError, match_audio_opening
from .config import section
from .derived_ass import DerivedAssError, OverwideError, fmt_ass_time
from .media_render import MediaRenderError, parse_media_time
from .models import utc_now
from .overrides import apply_overrides, load_overrides
from .project_io import create_project, load_project, save_project
from .render_job import RenderJobReport, load_render_job, run_render_job
from .service import (
    align_project,
    automate_project,
    import_project_assets,
    prepare_project,
    produce_project,
)
from .themes import THEMES
from .validate import doctor as run_doctor
from .validate import inspect_project

app = typer.Typer(no_args_is_help=True, help="Local-first Japanese karaoke studio")
export_app = typer.Typer(no_args_is_help=True)
app.add_typer(export_app, name="export")


def _job_ref(path: Path, base: Path) -> str:
    resolved = path.resolve()
    try:
        return os.fspath(resolved.relative_to(base.resolve()))
    except ValueError:
        return os.fspath(resolved)


def _render_report_payload(report: RenderJobReport) -> dict[str, object]:
    ass_report = report.ass
    payload: dict[str, object] = {
        "ok": True,
        "source_dialogues": ass_report.source_dialogues,
        "generated_events": ass_report.generated_events,
        "long_interludes": ass_report.long_interludes,
        "max_width_px": ass_report.max_width,
        "font_size_px": ass_report.font_size,
        "output_ass": str(ass_report.output),
    }
    if report.media is not None:
        payload["outputs"] = {
            name: {
                "path": str(result.path),
                "ffmpeg_exit_code": result.ffmpeg_exit_code,
                "reused": result.reused,
                "elapsed_seconds": result.elapsed_seconds,
            }
            for name, result in report.media.outputs.items()
        }
        if report.media.match is not None:
            payload["opening_match"] = {
                "offset_seconds": report.media.match.offset_seconds,
                "correlation": report.media.match.correlation,
                "second_best_correlation": report.media.match.second_best_correlation,
            }
    if report.translation is not None:
        payload["translation"] = {
            "lines": report.translation.lines,
            "max_width_px": report.translation.max_width,
            "combined_ass": str(report.translation.combined_output),
            "zh_only_ass": str(report.translation.zh_only_output),
        }
    payload["requested_outputs"] = list(report.requested_outputs)
    payload["timings"] = report.timings
    return payload


@app.command("render-job")
def render_job_command(
    job_file: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Expand one formal JSON job into its automatic ASS and media variants."""
    try:
        report = run_render_job(load_render_job(job_file))
    except OverwideError as exc:
        payload = {
            "ok": False,
            "code": "overwide",
            "message": str(exc),
            "lines": [
                {
                    "index": line.index,
                    "text": line.text,
                    "start": fmt_ass_time(line.start),
                    "end": fmt_ass_time(line.end),
                    "width_px": line.width,
                    "font_size_px": line.font_size,
                }
                for line in exc.lines
            ],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=True)
        raise typer.Exit(2) from exc
    except (
        AudioOpeningMatchError,
        DerivedAssError,
        MediaRenderError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        payload = {"ok": False, "code": "render_job_error", "message": str(exc)}
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(_render_report_payload(report), ensure_ascii=False, indent=2))


@app.command("specialize")
def specialize_command(
    source_ass: Path = typer.Argument(..., exists=True, dir_okay=False),
    video: Path = typer.Argument(..., exists=True, dir_okay=False),
    trim_end: str = typer.Option(..., "--trim-end", help="输出片段结束时间"),
    theme: str = typer.Option(
        section("production")["default_theme"], "--theme", help="主题：nogizaka46 等"
    ),
    trim_start: str = typer.Option("0", "--trim-start", help="输入视频起始时间"),
    title_text: str = typer.Option("", "--title-text", help="右上角标题；留空则不创建"),
    output_dir: Path | None = typer.Option(None, "--output-dir", file_okay=False),
    output_ass: Path | None = typer.Option(None, "--output-ass", dir_okay=False),
    job_file: Path | None = typer.Option(None, "--job-file", dir_okay=False),
    audio: Path | None = typer.Option(None, exists=True, dir_okay=False),
    off_vocal: Path | None = typer.Option(None, "--off-vocal", exists=True, dir_okay=False),
    match_reference_audio: Path | None = typer.Option(
        None, "--match-reference-audio", exists=True, dir_okay=False
    ),
    translation: Path | None = typer.Option(None, "--translation", exists=True, dir_okay=False),
    prefer_early_seconds: float | None = typer.Option(None, "--prefer-early-seconds", min=8.000001),
    pad_to_1080p: bool = typer.Option(False, "--pad-to-1080p"),
    only: list[str] = typer.Option(
        [],
        "--only",
        help=(
            "显式限制输出；可重复。默认按可用输入自动决定："
            "on_vocal_karaoke/off_vocal_karaoke/on_vocal_karaoke_zh/on_vocal_zh_only"
        ),
    ),
    write_job_only: bool = typer.Option(False, "--write-job-only"),
) -> None:
    """用已有 ASS 轨迹直接生成正式作业并渲染，不运行 Yohane。"""
    if theme not in THEMES:
        raise typer.BadParameter(
            f"未知主题 {theme!r}；可选：{', '.join(THEMES)}", param_hint="--theme"
        )
    valid_outputs = {
        "on_vocal_karaoke",
        "off_vocal_karaoke",
        "on_vocal_karaoke_zh",
        "on_vocal_zh_only",
    }
    invalid = sorted(set(only) - valid_outputs)
    if invalid:
        raise typer.BadParameter(f"未知输出：{', '.join(invalid)}", param_hint="--only")
    start = parse_media_time(trim_start)
    end = parse_media_time(trim_end)
    if end <= start:
        raise typer.BadParameter("--trim-end 必须晚于 --trim-start")

    destination = (output_dir or source_ass.parent).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    derived_ass = (output_ass or destination / f"{source_ass.stem}_formalized.ass").resolve()
    rendered_job = (job_file or destination / "specialize-job.json").resolve()
    media: dict[str, object] = {
        "video": _job_ref(video, rendered_job.parent),
        "trim_start": trim_start,
        "trim_end": trim_end,
        "output_dir": ".",
    }
    if audio is not None:
        media["audio"] = _job_ref(audio, rendered_job.parent)
    if off_vocal is not None:
        media["external_audio"] = _job_ref(off_vocal, rendered_job.parent)
    if match_reference_audio is not None:
        media["match_reference_audio"] = _job_ref(match_reference_audio, rendered_job.parent)
    if prefer_early_seconds is not None:
        media["prefer_early_seconds"] = prefer_early_seconds
    if pad_to_1080p:
        media["pad_to_1080p"] = True
    payload: dict[str, object] = {
        "schema_version": 2,
        "source_ass": _job_ref(source_ass, rendered_job.parent),
        "output_ass": _job_ref(derived_ass, rendered_job.parent),
        "theme": theme,
        "title_text": title_text,
        "audio_end": end - start,
        "media": media,
    }
    if translation is not None:
        payload["translation"] = {"file": _job_ref(translation, rendered_job.parent)}
    if only:
        payload["outputs"] = only
    rendered_job.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    typer.echo(f"job {rendered_job}")
    if write_job_only:
        return
    try:
        report = run_render_job(load_render_job(rendered_job))
    except OverwideError as exc:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "code": "overwide",
                    "message": str(exc),
                    "lines": [
                        {
                            "index": line.index,
                            "text": line.text,
                            "start": fmt_ass_time(line.start),
                            "end": fmt_ass_time(line.end),
                            "width_px": line.width,
                            "font_size_px": line.font_size,
                        }
                        for line in exc.lines
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(2) from exc
    except (
        AudioOpeningMatchError,
        DerivedAssError,
        MediaRenderError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        typer.echo(
            json.dumps(
                {"ok": False, "code": "specialize_error", "message": str(exc)},
                ensure_ascii=False,
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(_render_report_payload(report), ensure_ascii=False, indent=2))


@app.command("match-audio-opening")
def match_audio_opening_command(
    video: Path = typer.Argument(..., exists=True, dir_okay=False),
    external_audio: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Find where the external audio opening occurs in the video's audio stream."""
    try:
        match = match_audio_opening(video, external_audio)
    except AudioOpeningMatchError as exc:
        typer.echo(
            json.dumps(
                {"ok": False, "code": "opening_match_failed", "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "offset_seconds": match.offset_seconds,
                "correlation": match.correlation,
                "second_best_correlation": match.second_best_correlation,
                "sample_rate": match.sample_rate,
                "template_start_seconds": match.template_start_seconds,
                "template_duration_seconds": match.template_duration_seconds,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def new(directory: Path, title: str = typer.Option(..., "--title", "-t")) -> None:
    project = create_project(directory, title)
    typer.echo(f"created {directory / 'project.karaoke.json'} ({project.project_id})")


@app.command(name="import")
def import_command(
    project: Path,
    lyrics: Path = typer.Option(..., exists=True, dir_okay=False),
    audio: Path | None = typer.Option(None, exists=True, dir_okay=False),
    video: Path | None = typer.Option(None, dir_okay=False),
    legacy_parentheses: bool = typer.Option(False, help="Parse 漢字(かんじ) as legacy ruby"),
    preserve_ass_timing: bool = typer.Option(
        False, help="Adopt valid ASS k tags and skip alignment"
    ),
) -> None:
    result = import_project_assets(
        project,
        lyrics_path=lyrics,
        audio_path=audio,
        video_path=video,
        legacy_parentheses=legacy_parentheses,
        preserve_ass_timing=preserve_ass_timing,
    )
    typer.echo(f"imported {len(result.lines)} lyric lines")


@app.command()
def automate(
    video: Path,
    audio: Path,
    title: str,
    lyrics_file: Path | None = typer.Option(None, "--lyrics-file", exists=True, dir_okay=False),
) -> None:
    """Create a project beside VIDEO and run import, prepare, align and ASS export."""
    lyrics = lyrics_file.read_text(encoding="utf-8") if lyrics_file else sys.stdin.read()
    if not lyrics.strip():
        raise typer.BadParameter("lyrics must be provided through stdin or --lyrics-file")
    try:
        project_dir, output, cache_hit = automate_project(video, audio, title, lyrics)
    except (OSError, ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"created {project_dir}")
    typer.echo(f"aligned {'cache' if cache_hit else 'yohane'}")
    typer.echo(f"exported {output}")


@app.command("produce")
def produce(
    video: Path = typer.Argument(..., exists=True, dir_okay=False),
    title: str = typer.Argument(...),
    lyrics_file: Path = typer.Option(..., "--lyrics-file", exists=True, dir_okay=False),
    audio: Path | None = typer.Option(None, "--audio", exists=True, dir_okay=False),
    project: Path | None = typer.Option(None, "--project", file_okay=False),
    theme: str = typer.Option(section("production")["default_theme"], "--theme"),
    color: str | None = typer.Option(None, "--color", help="项目主色 #RRGGBB，不修改预设"),
    color_override: list[str] = typer.Option([], "--color-override", help="可重复：字段=#RRGGBB"),
    trim_start: str = typer.Option("0", "--trim-start"),
    trim_end: str | None = typer.Option(None, "--trim-end"),
    title_text: str = typer.Option("", "--title-text", help="右上角标注；默认留空"),
    off_vocal: Path | None = typer.Option(None, "--off-vocal", exists=True, dir_okay=False),
    translation: Path | None = typer.Option(None, "--translation", exists=True, dir_okay=False),
    only: list[str] = typer.Option([], "--only"),
    top_y: float = typer.Option(section("layout")["top_y"], "--top-y"),
    bottom_y: float = typer.Option(section("layout")["bottom_y"], "--bottom-y"),
    margin_x: float = typer.Option(section("layout")["margin_x"], "--margin-x"),
    canvas_width: int | None = typer.Option(None, "--canvas-width"),
    canvas_height: int | None = typer.Option(None, "--canvas-height"),
    force_render: bool = typer.Option(False, "--force-render", help="强制重新烧录，保留有效对齐"),
) -> None:
    """一条命令完成歌词对齐、模板展开与成片；同一项目自动复用有效阶段。"""
    colors = {"sung": color} if color is not None else {}
    try:
        for item in color_override:
            key, value = item.split("=", 1)
            colors[key] = value
        root, result, timing = produce_project(
            video,
            lyrics_file,
            title,
            project_dir=project,
            audio=audio,
            trim_start=trim_start,
            trim_end=trim_end,
            theme=theme,
            colors=colors,
            title_text=title_text,
            off_vocal=off_vocal,
            translation=translation,
            outputs=only or None,
            top_y=top_y,
            bottom_y=bottom_y,
            margin_x=margin_x,
            target_width=canvas_width,
            target_height=canvas_height,
            force_render=force_render,
        )
    except OverwideError as exc:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "code": "overwide",
                    "message": str(exc),
                    "lines": [
                        {
                            "index": line.index,
                            "text": line.text,
                            "start": fmt_ass_time(line.start),
                            "end": fmt_ass_time(line.end),
                            "width_px": line.width,
                            "font_size_px": line.font_size,
                        }
                        for line in exc.lines
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(2) from exc
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        typer.echo(
            json.dumps(
                {"ok": False, "code": "produce_error", "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    payload = _render_report_payload(result)
    payload.update(
        project=str(root), stages=timing["stages"], elapsed_seconds=timing["elapsed_seconds"]
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("resume")
def resume_production(
    project: Path = typer.Argument(..., exists=True, file_okay=False),
    color: str | None = typer.Option(None, "--color"),
    theme: str | None = typer.Option(None, "--theme"),
    off_vocal: Path | None = typer.Option(None, "--off-vocal", exists=True, dir_okay=False),
    translation: Path | None = typer.Option(None, "--translation", exists=True, dir_okay=False),
    no_off_vocal: bool = typer.Option(False, "--no-off-vocal"),
    no_translation: bool = typer.Option(False, "--no-translation"),
    force_render: bool = typer.Option(False, "--force-render"),
) -> None:
    """沿用该项目上次 produce 参数，重新读取原歌词，自动复用有效阶段。"""
    try:
        request_path = project / ".karaoke-work" / "production-request.json"
        if not request_path.is_file():
            raise ValueError("项目尚无 produce 记录；首次用 produce --project 指定此目录")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request["project_dir"] = str(project.resolve())
        if color is not None:
            request.setdefault("colors", {})["sung"] = color
        if theme is not None:
            request["theme"] = theme
            if color is None:
                request.setdefault("colors", {}).pop("sung", None)
        if off_vocal is not None:
            request["off_vocal"] = str(off_vocal.resolve())
        if translation is not None:
            request["translation"] = str(translation.resolve())
        if no_off_vocal:
            request["off_vocal"] = None
        if no_translation:
            request["translation"] = None
        for key in ("video", "lyrics", "audio", "project_dir", "off_vocal", "translation"):
            if request.get(key) is not None:
                request[key] = Path(request[key])
        root, result, timing = produce_project(**request, force_render=force_render)
    except OverwideError as exc:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "code": "overwide",
                    "message": str(exc),
                    "lines": [
                        {
                            "index": line.index,
                            "text": line.text,
                            "start": fmt_ass_time(line.start),
                            "end": fmt_ass_time(line.end),
                            "width_px": line.width,
                            "font_size_px": line.font_size,
                        }
                        for line in exc.lines
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(2) from exc
    except (OSError, ValueError, RuntimeError, TypeError, subprocess.SubprocessError) as exc:
        typer.echo(
            json.dumps(
                {"ok": False, "code": "resume_error", "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    payload = _render_report_payload(result)
    payload.update(
        project=str(root), stages=timing["stages"], elapsed_seconds=timing["elapsed_seconds"]
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def prepare(project: Path) -> None:
    result = prepare_project(project)
    typer.echo(f"prepared {result.audio.prepared_path} ({result.audio.duration_ms} ms)")


@app.command()
def align(
    project: Path,
    allow_download: bool = typer.Option(False, help="Allow Hugging Face model download"),
    accept_model_license: bool = typer.Option(
        False, help="Accept CC-BY-NC-SA-4.0 for the default model"
    ),
    yohane_python: Path | None = typer.Option(None, exists=True, dir_okay=False),
) -> None:
    data = load_project(project)
    if accept_model_license:
        data.model.license_accepted_at = utc_now()
        save_project(project, data)
        typer.echo("recorded model license acceptance: CC-BY-NC-SA-4.0")
    result, cache_hit = align_project(
        project,
        allow_download=allow_download,
        yohane_python=yohane_python,
    )
    typer.echo(f"aligned {len(result.lines)} lines ({'cache' if cache_hit else 'yohane'})")


@app.command()
def inspect(
    project: Path,
    json_output: bool = typer.Option(False, "--json", help="Machine-readable Agent report"),
) -> None:
    data = load_project(project, recover_read_only=True)
    issues = inspect_project(data)
    payload = {
        "project_id": data.project_id,
        "alignment_stale": data.alignment_stale,
        "line_count": len(data.lines),
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        typer.echo(f"{len(data.lines)} lines, {len(issues)} structural issues")
        for issue in issues:
            typer.echo(f"[{issue.severity}] {issue.code} {issue.line_id or '-'}: {issue.message}")


@app.command("apply-overrides")
def apply_override_command(project: Path, overrides: Path = typer.Option(..., exists=True)) -> None:
    data = load_project(project)
    count = apply_overrides(data, load_overrides(overrides))
    data.issues = inspect_project(data)
    save_project(project, data)
    typer.echo(f"applied {count} overrides; alignment marked stale")


@export_app.command("ass")
def export_ass_command(
    project: Path,
    output: Path = typer.Option(..., "--output", "-o", dir_okay=False),
) -> None:
    data = load_project(project)
    if data.alignment_stale:
        raise typer.BadParameter("reading alignment is stale; run karaoke align")
    output.write_text(export_ass(data), encoding="utf-8", newline="\n")
    typer.echo(f"exported {output}")


@app.command()
def validate(project: Path) -> None:
    data = load_project(project, recover_read_only=True)
    issues = inspect_project(data)
    for issue in issues:
        typer.echo(f"[{issue.severity}] {issue.code}: {issue.message}")
    if any(issue.severity == "error" for issue in issues):
        raise typer.Exit(1)
    typer.echo("project structure is valid")


@app.command()
def doctor(project: Path | None = None) -> None:
    checks = run_doctor(project)
    typer.echo(json.dumps(checks, ensure_ascii=False, indent=2))
    if any(isinstance(value, dict) and not value.get("ok", False) for value in checks.values()):
        raise typer.Exit(1)


@app.command()
def serve(
    project: Path,
    host: str = typer.Option("127.0.0.1", hidden=True),
    port: int = typer.Option(8765),
) -> None:
    if host != "127.0.0.1":
        raise typer.BadParameter("Karaoke Studio only listens on 127.0.0.1")
    import uvicorn

    typer.echo(f"Karaoke Studio: http://127.0.0.1:{port}/")
    uvicorn.run(create_app(project.resolve()), host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
