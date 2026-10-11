from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .audio import prepare_audio
from .cache import alignment_cache_key, load_cached_alignment, save_cached_alignment
from .config import section
from .lyrics import ImportedLine, build_lines, import_lyrics
from .models import KaraokeProject, RawAlignedLine, RawAlignment, utc_now
from .project_io import create_project, load_project, save_project
from .structure import reconcile_to_yohane
from .validate import inspect_project
from .yohane_adapter import run_yohane


@contextmanager
def _production_lock(path: Path):
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            if path.stat().st_size == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError(f"该项目已有制作任务运行: {path.parent.parent}") from exc
        else:
            import fcntl

            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(f"该项目已有制作任务运行: {path.parent.parent}") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _copy_source(source: Path, project_dir: Path, kind: str) -> Path:
    destination_dir = project_dir / "source"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{kind}{source.suffix.lower()}"
    shutil.copy2(source, destination)
    return destination


def import_project_assets(
    project_dir: Path,
    *,
    lyrics_path: Path,
    audio_path: Path | None = None,
    video_path: Path | None = None,
    legacy_parentheses: bool = False,
    preserve_ass_timing: bool = False,
) -> KaraokeProject:
    project_dir = project_dir.resolve()
    project = load_project(project_dir)
    lyrics_copy = _copy_source(lyrics_path, project_dir, "lyrics")
    source_format, imported = import_lyrics(lyrics_copy)
    lines = build_lines(imported, legacy_parentheses=legacy_parentheses)
    project.lines = lines
    project.source.lyrics_path = str(lyrics_copy.relative_to(project_dir))
    project.source.lyrics_format = source_format
    project.source.legacy_parentheses_ruby = legacy_parentheses
    project.source.preserve_ass_timing = preserve_ass_timing
    project.source.imported_at = utc_now()
    project.raw_alignment = None
    project.alignment_source = None
    project.alignment_stale = True
    project.timing_patches = []
    if audio_path:
        audio_copy = _copy_source(audio_path, project_dir, "audio")
        project.source.audio_path = str(audio_copy.relative_to(project_dir))
    if video_path:
        video_copy = _copy_source(video_path, project_dir, "video")
        project.source.video_path = str(video_copy.relative_to(project_dir))
    if source_format == "ass" and preserve_ass_timing:
        _adopt_ass_timing(project, imported)
    project.issues = inspect_project(project)
    save_project(project_dir, project)
    return project


def normalize_title(title: str) -> str:
    normalized = title.strip()
    if normalized.startswith("《") and normalized.endswith("》"):
        normalized = normalized[1:-1].strip()
    if not normalized or Path(normalized).name != normalized:
        raise ValueError("title must be a non-empty folder name")
    return normalized


def produce_project(
    video: Path,
    lyrics: Path,
    title: str,
    *,
    project_dir: Path | None = None,
    audio: Path | None = None,
    trim_start: str = "0",
    trim_end: str | None = None,
    theme: str = section("production")["default_theme"],
    colors: dict[str, str] | None = None,
    title_text: str = "",
    off_vocal: Path | None = None,
    translation: Path | None = None,
    outputs: list[str] | None = None,
    top_y: float = section("layout")["top_y"],
    bottom_y: float = section("layout")["bottom_y"],
    margin_x: float = section("layout")["margin_x"],
    target_width: int | None = None,
    target_height: int | None = None,
    force_render: bool = False,
) -> tuple[Path, object, dict]:
    """Resumable full production. Media stay read-only; timing is clip-relative."""
    from .ass import export_ass
    from .media_render import _probe, file_identity, parse_media_time, write_record
    from .render_job import RenderJob, _available_outputs, _canvas, run_render_job

    title = normalize_title(title)
    video, lyrics = video.resolve(strict=True), lyrics.resolve(strict=True)
    audio = (audio or video).resolve(strict=True)
    off_vocal = off_vocal.resolve(strict=True) if off_vocal is not None else None
    translation = translation.resolve(strict=True) if translation is not None else None
    now = datetime.now()
    date = f"{now.month}月{now.day}日"
    root = (project_dir or video.parent / f"{title}-{date}").resolve()
    try:
        initial_state = json.loads(
            (root / ".karaoke-work" / "production-state.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        initial_state = {}
    artifact_date = initial_state.get("created_date", date)
    start = parse_media_time(trim_start)
    video_meta = _probe(video)
    audio_meta = video_meta if audio == video else _probe(audio)
    if not any(s.get("codec_type") == "video" for s in video_meta.get("streams", [])):
        raise ValueError(f"输入缺少视频流: {video}")
    if not any(s.get("codec_type") == "audio" for s in audio_meta.get("streams", [])):
        raise ValueError(f"输入缺少音频流: {audio}")
    video_duration = float(video_meta.get("format", {}).get("duration", 0))
    end = parse_media_time(trim_end) if trim_end is not None else video_duration
    if not 0 <= start < end or (video_duration > 0 and end > video_duration + 0.05):
        raise ValueError(f"裁剪区间无效: {start}–{end}; 视频长度 {video_duration}")
    text = lyrics.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("歌词为空")
    frame = (
        {"mode": "preserve"}
        if target_width is None and target_height is None
        else {
            "mode": "pad",
            "target_width": target_width,
            "target_height": target_height,
        }
    )
    # Validate all declarative options before importing or starting the model.
    job = RenderJob.model_validate(
        {
            "source_ass": root / f"字幕模板-{artifact_date}.ass",
            "output_ass": root / f"卡拉OK-{artifact_date}.ass",
            "theme": theme,
            "colors": colors or {},
            "title_text": title_text,
            "audio_end": end - start,
            "reuse_outputs": not force_render,
            "outputs": outputs,
            "translation": {"file": translation} if translation is not None else None,
            "layout": {"top_y": top_y, "bottom_y": bottom_y, "margin_x": margin_x},
            "media": {
                "video": video,
                "audio": audio,
                "external_audio": off_vocal,
                "match_reference_audio": audio,
                "trim_start": start,
                "trim_end": end,
                "output_dir": root,
                "frame": frame,
            },
        }
    )
    _canvas(job)
    unavailable = set(outputs or []) - _available_outputs(job)
    if unavailable:
        raise ValueError("请求的输出缺少对应输入: " + ", ".join(sorted(unavailable)))
    root.mkdir(parents=True, exist_ok=True)
    work = root / ".karaoke-work"
    work.mkdir(exist_ok=True)
    with _production_lock(work / "production.lock"):
        state_path = work / "production-state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("created_date", artifact_date)
        report = {
            "started_at": utc_now().isoformat(),
            "entry": "karaoke produce",
            "project": str(root),
            "job": job.model_dump(mode="json"),
            "stages": [],
            "ok": False,
        }
        report_path = root / f"制作记录-{date}.json"
        journal = root / f"制作过程-{date}.jsonl"
        total_start = time.perf_counter()

        def event(stage: str, status: str, **details: object) -> None:
            item = {"at": utc_now().isoformat(), "stage": stage, "status": status, **details}
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(json.dumps(item, ensure_ascii=False), file=sys.stderr, flush=True)

        def stage(name: str, action: Callable, reuse: bool = False):
            begun = time.perf_counter()
            event(name, "reused" if reuse else "started")
            try:
                result = None if reuse else action()
            except Exception as exc:
                item = {
                    "name": name,
                    "reused": False,
                    "status": "failed",
                    "elapsed_seconds": round(time.perf_counter() - begun, 3),
                    "error": str(exc),
                }
                report["stages"].append(item)
                event(name, "failed", error=str(exc), elapsed_seconds=item["elapsed_seconds"])
                raise
            item = {
                "name": name,
                "reused": reuse,
                "elapsed_seconds": round(time.perf_counter() - begun, 3),
            }
            report["stages"].append(item)
            event(name, "completed", **item)
            return result

        def code_stamp(names: list[str]) -> list[dict]:
            return [file_identity(Path(__file__).with_name(name + ".py")) for name in names]

        try:
            if not (root / "project.karaoke.json").exists():
                create_project(root, title)
            project = load_project(root)
            request = {
                "video": str(video),
                "lyrics": str(lyrics),
                "title": title,
                "project_dir": str(root),
                "audio": str(audio),
                "trim_start": str(start),
                "trim_end": str(end),
                "theme": theme,
                "colors": colors or {},
                "title_text": title_text,
                "off_vocal": str(off_vocal) if off_vocal else None,
                "translation": str(translation) if translation else None,
                "outputs": outputs,
                "top_y": top_y,
                "bottom_y": bottom_y,
                "margin_x": margin_x,
                "target_width": target_width,
                "target_height": target_height,
            }
            write_record(work / "production-request.json", request)
            lyric_key = {
                "text": text,
                "format": lyrics.suffix.lower(),
                "code": code_stamp(["lyrics", "structure", "mora"]),
            }
            project_lines = [line.original for line in project.lines]
            can_reuse_lyrics = (
                state.get("lyrics") == lyric_key and state.get("line_texts") == project_lines
            )

            def import_text():
                source_format, imported = import_lyrics(lyrics)
                project.lines = build_lines(imported)
                project.source.lyrics_format = source_format
                project.source.imported_at = utc_now()
                project.raw_alignment = None
                project.alignment_stale = True
                project.timing_patches = []

            stage("歌词解析", import_text, can_reuse_lyrics)

            # The existing editor requires project-relative sources. Only copy
            # changed inputs, inside a dedicated derived-data directory.
            def retain_inputs():
                retained = state.setdefault("retained_inputs", {})
                destination_dir = work / "inputs"
                destination_dir.mkdir(exist_ok=True)
                for kind, source in (("lyrics", lyrics), ("audio", audio), ("video", video)):
                    destination = destination_dir / f"{kind}{source.suffix.lower()}"
                    identity = file_identity(source)
                    previous = retained.get(kind, {})
                    if (
                        not (
                            destination.is_file()
                            and previous.get("source") == identity
                            and previous.get("copy") == file_identity(destination)
                        )
                        and destination.resolve() != source
                    ):
                        # APFS copy-on-write avoids copying a multi-GB
                        # concert merely to render a short excerpt.
                        cloned = False
                        if sys.platform == "darwin":
                            copied = subprocess.run(
                                ["/bin/cp", "-c", "-p", str(source), str(destination)],
                                capture_output=True,
                                check=False,
                            )
                            cloned = copied.returncode == 0
                        if not cloned:
                            shutil.copy2(source, destination)
                    retained[kind] = {"source": identity, "copy": file_identity(destination)}
                    setattr(project.source, kind + "_path", str(destination.relative_to(root)))

            stage("输入归档", retain_inputs)
            project.title = title
            save_project(root, project)
            state["lyrics"], state["line_texts"] = (
                lyric_key,
                [line.original for line in project.lines],
            )
            write_record(state_path, state)
            preparation = {
                "audio": file_identity(audio),
                "start": start,
                "end": end,
                "code": code_stamp(["audio"]),
            }
            prepared = root / project.audio.prepared_path if project.audio.prepared_path else None
            reuse_audio = (
                state.get("preparation") == preparation
                and prepared is not None
                and prepared.is_file()
                and state.get("prepared_file") == file_identity(prepared)
            )

            def prepare():
                project.audio = prepare_audio(audio, root, trim_start=start, duration=end - start)
                project.alignment_stale = True
                save_project(root, project)

            stage("音频准备", prepare, reuse_audio)
            state["preparation"] = preparation
            state["prepared_file"] = file_identity(root / project.audio.prepared_path)
            write_record(state_path, state)
            alignment_code = code_stamp(["service", "yohane_adapter", "structure", "cache"])
            alignment_inputs = {
                "model": project.model.model_id,
                "revision": project.model.revision,
                "readings": [line.yohane_input for line in project.lines],
            }
            reuse_alignment = (
                can_reuse_lyrics
                and reuse_audio
                and not project.alignment_stale
                and project.raw_alignment is not None
                and state.get("alignment_code") == alignment_code
                and state.get("alignment_inputs") == alignment_inputs
            )
            stage("整曲对齐", lambda: align_project(root), reuse_alignment)
            project = load_project(root)
            issues = [
                issue for issue in project.issues if issue.severity == "error"
            ] + inspect_project(project)
            if project.alignment_stale or issues:
                raise ValueError(
                    "对齐结构门禁失败: "
                    + json.dumps(
                        [issue.model_dump(mode="json") for issue in issues], ensure_ascii=False
                    )
                )
            state["alignment_code"] = alignment_code
            state["alignment_inputs"] = {
                "model": project.model.model_id,
                "revision": project.model.revision,
                "readings": [line.yohane_input for line in project.lines],
            }
            write_record(state_path, state)
            stage(
                "模板导出", lambda: job.source_ass.write_text(export_ass(project), encoding="utf-8")
            )
            job_path = root / "render-job.json"
            write_record(job_path, job.model_dump(mode="json"))
            result = stage("字幕展开及成片", lambda: run_render_job(job))
            report["ok"] = True
            report["timings"] = result.timings
            report["outputs"] = (
                {
                    name: {
                        "path": str(item.path),
                        "reused": item.reused,
                        "ffmpeg_exit_code": item.ffmpeg_exit_code,
                        "elapsed_seconds": item.elapsed_seconds,
                    }
                    for name, item in result.media.outputs.items()
                }
                if result.media
                else {}
            )
            return root, result, report
        except Exception as exc:
            report["error"] = str(exc)
            event("任务", "failed", error=str(exc))
            raise
        finally:
            report["elapsed_seconds"] = round(time.perf_counter() - total_start, 3)
            report["finished_at"] = utc_now().isoformat()
            write_record(report_path, report)


def automate_project(
    video_path: Path,
    audio_path: Path,
    title: str,
    lyrics_text: str,
) -> tuple[Path, Path, bool]:
    """Create a project beside the supplied media and run the local pipeline."""
    title = normalize_title(title)
    video_path = video_path.resolve()
    audio_path = audio_path.resolve()
    project_dir = video_path.parent / title
    create_project(project_dir, title)
    lyrics_path = project_dir / "lyrics.txt"
    lyrics_path.write_text(lyrics_text.rstrip() + "\n", encoding="utf-8")
    import_project_assets(
        project_dir,
        lyrics_path=lyrics_path,
        audio_path=audio_path,
        video_path=video_path,
    )
    prepare_project(project_dir)
    project, cache_hit = align_project(project_dir)
    issues = inspect_project(project)
    if project.alignment_stale or any(issue.severity == "error" for issue in issues):
        messages = "; ".join(issue.code for issue in issues)
        raise RuntimeError(f"alignment did not produce an exportable project: {messages}")
    output = project_dir / f"{title}.ass"
    from .ass import export_ass

    output.write_text(export_ass(project), encoding="utf-8", newline="\n")
    return project_dir, output, cache_hit


def _adopt_ass_timing(project: KaraokeProject, imported: list[ImportedLine]) -> None:
    if len(imported) != len(project.lines):
        raise ValueError("ASS line count changed during import")
    raw_lines: list[RawAlignedLine] = []
    for line, source in zip(project.lines, imported, strict=True):
        values = list(source.ass_k_values_cs)
        if source.ass_start_ms is None or source.ass_end_ms is None or not values:
            raise ValueError("ASS preserve mode requires line times and karaoke tags on every line")
        if len(values) != len(line.moras):
            raise ValueError(
                f"ASS line {line.source_index + 1} has {len(values)} k tags "
                f"for {len(line.moras)} moras"
            )
        raw_lines.append(
            RawAlignedLine(
                line_id=line.id,
                start_ms=source.ass_start_ms,
                end_ms=source.ass_end_ms,
                k_values_cs=values,
            )
        )
    project.raw_alignment = RawAlignment(
        cache_key="preserved-ass",
        adapter_version="ass-import",
        model_id="none",
        model_revision="none",
        audio_sha256="not-required",
        normalized_romaji_sha256="not-used",
        lines=raw_lines,
    )
    project.alignment_source = "preserved_ass"
    project.alignment_stale = False


def prepare_project(project_dir: Path) -> KaraokeProject:
    project = load_project(project_dir)
    if not project.source.audio_path:
        raise ValueError("project has no imported audio")
    source = project_dir / project.source.audio_path
    project.audio = prepare_audio(source, project_dir)
    if (
        project.raw_alignment
        and project.raw_alignment.audio_sha256 != project.audio.prepared_sha256
    ):
        project.alignment_stale = True
    save_project(project_dir, project)
    return project


def align_project(
    project_dir: Path,
    *,
    allow_download: bool = False,
    yohane_python: Path | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[KaraokeProject, bool]:
    project = load_project(project_dir)
    key = alignment_cache_key(project)
    alignment = load_cached_alignment(project_dir, key)
    cache_hit = alignment is not None
    if alignment is None:
        alignment = run_yohane(
            project,
            project_dir,
            allow_download=allow_download,
            python=yohane_python,
            cancel_check=cancel_check,
        )
        save_cached_alignment(project_dir, alignment)
    project.raw_alignment = alignment
    project.alignment_source = "yohane"
    project.alignment_stale = False
    project.timing_patches = []
    structural = []
    for line, raw in zip(project.lines, alignment.lines, strict=True):
        issue = reconcile_to_yohane(line, raw)
        if issue:
            structural.append(issue)
    project.issues = structural + inspect_project(project)
    save_project(project_dir, project)
    return project, cache_hit
