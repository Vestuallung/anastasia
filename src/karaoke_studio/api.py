from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from .ass import export_ass
from .audio import waveform_peaks
from .config import configured_path, section
from .editor_11月7日 import EditorPreferences, preferences, preview_settings, save_preferences
from .models import JobEvent, OverrideFile, ReadingOverride, Span, utc_now
from .overrides import apply_overrides
from .project_io import load_project, resolve_project_path, save_project
from .service import align_project, import_project_assets, prepare_project
from .setup_11月7日 import application_settings_router
from .themes import ThemeName
from .timing import create_timing_patch, effective_boundaries, restore_raw_timing
from .validate import inspect_project
from .yohane_adapter import AlignmentCancelled

LOOPBACK_ORIGIN = re.compile(r"^https?://(?:127\.0\.0\.1|localhost)(?::\d+)?$")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadingEdit(ApiModel):
    expected_text: str
    span_start: int
    span_end: int
    reading: str | None = None
    romaji: str | None = None
    display_only: bool = False
    reason: str = "manual reading edit"


class TimingEdit(ApiModel):
    boundaries_ms: list[int]
    kind: Literal["line_shift", "boundary", "line_start", "line_end"]
    boundary_index: int | None = None
    reason: str = "manual timeline edit"


class TextEdit(ApiModel):
    text: str
    commit: bool = True


class EditorSettings(ApiModel):
    title_text: str | None = None
    colors: dict[str, str] | None = None
    countdown: bool | None = None
    katakana_ruby: bool | None = None
    theme: ThemeName | None = None
    layout: dict | None = None
    media: dict | None = None


@dataclass
class Job:
    id: str
    events: list[JobEvent] = field(default_factory=list)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False
    result: dict = field(default_factory=dict)

    def emit(self, stage: str, progress: float, message: str, status: str) -> None:
        self.events.append(
            JobEvent(stage=stage, progress=progress, message=message, status=status)  # type: ignore[arg-type]
        )


def _project_payload(project_dir: Path) -> dict[str, object]:
    project = load_project(project_dir, recover_read_only=True)
    payload = project.model_dump(mode="json")
    payload["effective_boundaries"] = {
        line.id: effective_boundaries(project, line.id) for line in project.lines
    }
    from .editor_11月7日 import scene

    payload["editor"] = scene(project_dir, project)
    payload["editor_preferences"] = preferences(project_dir).model_dump()
    return payload


def create_app(project_dir: Path, *, token: str | None = None, workspace=None) -> FastAPI:
    project_dir = project_dir.resolve()
    session_token = token
    app = FastAPI(title="Karaoke Studio", docs_url=None, redoc_url=None)
    app.include_router(
        application_settings_router(Path(os.environ.get("KARAOKE_HOME", Path.cwd())), project_dir)
    )
    app.state.session_token = session_token
    app.state.project_dir = project_dir
    app.state.jobs: dict[str, Job] = {}

    @app.middleware("http")
    async def local_security(request: Request, call_next):  # type: ignore[no-untyped-def]
        origin = request.headers.get("origin")
        if origin and not LOOPBACK_ORIGIN.match(origin):
            return PlainTextResponse("origin denied", status_code=403)
        if session_token and request.url.path.startswith("/api/"):
            supplied = request.headers.get("x-karaoke-token") or request.query_params.get("token")
            if not secrets.compare_digest(supplied or "", session_token):
                return PlainTextResponse("invalid session token", status_code=401)
        response = await call_next(request)
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    @app.get("/api/project")
    async def get_project() -> dict[str, object]:
        return _project_payload(project_dir)

    @app.get("/api/workspace")
    async def project_workspace() -> dict:
        return {"mode": "project", "path": str(project_dir)}

    @app.post("/api/editor/settings")
    async def editor_settings(edit: EditorSettings) -> dict:
        from .editor_11月7日 import save_settings

        try:
            save_settings(project_dir, edit.model_dump(exclude_none=True))
            return _project_payload(project_dir)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/editor/settings/preview")
    async def editor_settings_preview(edit: EditorSettings) -> dict:
        try:
            return preview_settings(project_dir, edit.model_dump(exclude_none=True))
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/editor/preferences")
    async def editor_preferences(edit: EditorPreferences) -> dict:
        save_preferences(project_dir, edit)
        return _project_payload(project_dir)

    @app.post("/api/lines/{line_id}/text")
    async def editor_text(line_id: str, edit: TextEdit) -> dict:
        from .editor_11月7日 import edit_text

        try:
            preview = edit_text(project_dir, line_id, edit.text, edit.commit)
            return _project_payload(project_dir) if edit.commit else preview
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/editor/open-folder")
    async def open_folder() -> dict:
        import subprocess
        import sys

        if sys.platform == "darwin":
            subprocess.Popen(["open", str(project_dir)])
        elif os.name == "nt":
            os.startfile(str(project_dir))
        else:
            subprocess.Popen(["xdg-open", str(project_dir)])
        return {"path": str(project_dir)}

    @app.post("/api/jobs/render")
    async def start_render(
        fresh: bool = True,
        upload: bool = False,
        video_bitrate_mbps: float | None = Query(default=None, ge=0, le=1000),
    ) -> dict:
        from .editor_11月7日 import save_settings
        from .media_render import upload_copies, write_record
        from .render_job import load_render_job, run_render_job, with_video_bitrate

        project = load_project(project_dir)
        if project.alignment_stale:
            raise HTTPException(409, "歌词已修改，请重新对齐后导出")
        if video_bitrate_mbps is not None and 0 < video_bitrate_mbps < 0.1:
            raise HTTPException(422, "视频码率至少为 0.1 Mbps")
        if workspace is not None:
            return start_workspace_job("render", fresh, upload=upload, video_bitrate_mbps=video_bitrate_mbps)
        try:
            save_settings(project_dir, {})
            job_path = project_dir / "render-job.json"
            render = with_video_bitrate(load_render_job(job_path), video_bitrate_mbps)
            source = project_dir / "EditorSource-11月7日.ass"
            source.write_text(export_ass(project), encoding="utf-8")
            render = render.model_copy(update={"source_ass": source, "reuse_outputs": not fresh})
            write_record(project_dir / "EditorRender-11月7日.json", render.model_dump(mode="json"))
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc
        job = Job(id=str(uuid4()))
        app.state.jobs[job.id] = job

        async def work():
            try:
                job.emit("render", 0, "正在导出成片", "running")
                result = await asyncio.to_thread(run_render_job, render)
                job.result = (
                    {name: str(item.path) for name, item in result.media.outputs.items()}
                    if result.media
                    else {}
                )
                if upload and job.result:
                    job.emit("upload", 0.9, "正在压缩上传版", "running")
                    job.result = await asyncio.to_thread(upload_copies, job.result)
                job.emit("complete", 1, "导出完成", "completed")
            except Exception as exc:
                job.emit("failed", 1, str(exc), "failed")
            finally:
                job.done.set()

        asyncio.create_task(work())
        return {"job_id": job.id}

    def start_workspace_job(
        kind: str, fresh: bool, allow_download: bool = False, upload: bool = False,
        video_bitrate_mbps: float | None = None,
    ) -> dict:
        try:
            state = workspace.start_editor(project_dir, kind, fresh, allow_download, upload, video_bitrate_mbps)
            return {"job_id": state["id"]}
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    def saved_job(job_id: str) -> dict:
        try:
            state = workspace.editor_job(project_dir, job_id)
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "任务不存在") from exc
        if state is None:
            raise HTTPException(404, "任务不存在")
        return state

    @app.get("/api/editor/job")
    async def latest_job() -> dict:
        return {"job": workspace.editor_job(project_dir) if workspace is not None else None}

    @app.get("/api/jobs/{job_id}/files/{name}")
    async def result_file(job_id: str, name: str) -> FileResponse:
        files = (await job_result(job_id))["files"]
        path = Path(files[name]) if name in files else None
        if path is None or not path.is_file():
            raise HTTPException(404, "找不到成片")
        return FileResponse(path, filename=path.name)

    @app.get("/api/jobs/{job_id}/result")
    async def job_result(job_id: str) -> dict:
        if workspace is not None:
            return {"files": saved_job(job_id)["files"]}
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在")
        return {"files": job.result}

    @app.get("/api/preview.ass")
    async def preview_ass() -> PlainTextResponse:
        return PlainTextResponse(
            export_ass(load_project(project_dir)), media_type="text/plain; charset=utf-8"
        )

    @app.get("/api/export.ass")
    async def download_ass() -> PlainTextResponse:
        project = load_project(project_dir)
        if project.alignment_stale:
            raise HTTPException(409, "reading alignment is stale")
        response = PlainTextResponse(export_ass(project), media_type="text/plain; charset=utf-8")
        response.headers["Content-Disposition"] = 'attachment; filename="karaoke-output.ass"'
        return response

    async def store_upload(upload: UploadFile, suffix: str) -> Path:
        work = project_dir / ".karaoke-work" / "uploads"
        work.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="import-", suffix=suffix, dir=work)
        target = Path(name)
        try:
            with open(descriptor, "wb", closefd=True) as handle:
                while chunk := await upload.read(1024 * 1024):
                    handle.write(chunk)
            return target
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @app.post("/api/import")
    async def import_assets(
        lyrics: UploadFile = File(...),
        audio: UploadFile | None = File(None),
        video: UploadFile | None = File(None),
        legacy_parentheses: bool = Form(False),
        preserve_ass_timing: bool = Form(False),
    ) -> dict[str, object]:
        lyrics_suffix = Path(lyrics.filename or "lyrics.txt").suffix.lower()
        if lyrics_suffix not in {".txt", ".lrc", ".ass"}:
            raise HTTPException(422, "lyrics must be TXT, LRC or ASS")
        lyrics_temp = await store_upload(lyrics, lyrics_suffix)
        audio_temp: Path | None = None
        video_temp: Path | None = None
        try:
            if audio:
                audio_suffix = Path(audio.filename or "audio.bin").suffix.lower() or ".bin"
                audio_temp = await store_upload(audio, audio_suffix)
            if video:
                video_suffix = Path(video.filename or "video.bin").suffix.lower() or ".bin"
                video_temp = await store_upload(video, video_suffix)
            await asyncio.to_thread(
                import_project_assets,
                project_dir,
                lyrics_path=lyrics_temp,
                audio_path=audio_temp or video_temp,
                video_path=video_temp,
                legacy_parentheses=legacy_parentheses,
                preserve_ass_timing=preserve_ass_timing,
            )
            return _project_payload(project_dir)
        finally:
            lyrics_temp.unlink(missing_ok=True)
            if audio_temp:
                audio_temp.unlink(missing_ok=True)
            if video_temp:
                video_temp.unlink(missing_ok=True)

    @app.post("/api/prepare")
    async def prepare_imported_audio() -> dict[str, object]:
        try:
            await asyncio.to_thread(prepare_project, project_dir)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return _project_payload(project_dir)

    @app.post("/api/model/accept-license")
    async def accept_model_license(accepted: bool = Form(...)) -> dict[str, object]:
        if not accepted:
            raise HTTPException(422, "model license acceptance must be explicit")
        project = load_project(project_dir)
        project.model.license_accepted_at = utc_now()
        save_project(project_dir, project)
        return {
            "model_id": project.model.model_id,
            "revision": project.model.revision,
            "license": project.model.license,
            "accepted_at": project.model.license_accepted_at.isoformat(),
        }

    @app.get("/api/audio")
    async def audio_file() -> FileResponse:
        project = load_project(project_dir)
        relative = project.audio.prepared_path or project.source.audio_path
        if not relative:
            raise HTTPException(404, "project has no audio")
        target = resolve_project_path(project_dir, relative)
        return FileResponse(target)

    @app.get("/api/video")
    async def video_file() -> FileResponse:
        project = load_project(project_dir)
        if not project.source.video_path:
            raise HTTPException(404, "project has no preview video")
        target = resolve_project_path(project_dir, project.source.video_path)
        return FileResponse(target)

    @app.get("/api/waveform")
    async def waveform(
        points: int = 1600, start_ms: int = 0, end_ms: int | None = None
    ) -> dict[str, object]:
        project = load_project(project_dir)
        if not project.audio.prepared_path:
            return {"peaks": [], "duration_ms": project.audio.duration_ms or 0}
        target = resolve_project_path(project_dir, project.audio.prepared_path)
        return {
            "peaks": await asyncio.to_thread(
                waveform_peaks, target, min(max(points, 100), 5000), start_ms, end_ms
            ),
            "duration_ms": project.audio.duration_ms or 0,
            "start_ms": max(0, start_ms),
            "end_ms": min(end_ms, project.audio.duration_ms or end_ms)
            if end_ms is not None
            else project.audio.duration_ms,
        }

    @app.get("/api/appearance")
    async def appearance_config() -> dict:
        fonts = section("fonts")
        return {
            "japanese_family": fonts["japanese_family"],
            "chinese_family": fonts["chinese_family"],
            "device": section("runtime")["device"],
            "model_url": section("model")["url"],
        }

    @app.get("/font/japanese")
    async def configured_japanese_font() -> FileResponse:
        return FileResponse(configured_path(section("fonts")["japanese_path"]))

    @app.get("/font/chinese")
    async def configured_chinese_font() -> FileResponse:
        return FileResponse(configured_path(section("fonts")["chinese_path"]))

    @app.get("/api/font")
    async def preview_font() -> FileResponse:
        target = Path(__file__).resolve().parent / "assets" / "fonts" / "NotoSansJP-Variable.ttf"
        return FileResponse(target, media_type="font/ttf")

    @app.get("/font/NotoSansJP.ttf")
    async def public_preview_font() -> FileResponse:
        target = Path(__file__).resolve().parent / "assets" / "fonts" / "NotoSansJP-Variable.ttf"
        return FileResponse(target, media_type="font/ttf")

    @app.get("/font/NotoSansCJKjp-Regular.otf")
    async def public_libass_font() -> FileResponse:
        target = Path(__file__).resolve().parent / "assets" / "fonts" / "NotoSansCJKjp-Regular.otf"
        return FileResponse(target, media_type="font/otf")

    @app.post("/api/lines/{line_id}/reading")
    async def edit_reading(line_id: str, edit: ReadingEdit) -> dict[str, object]:
        project = load_project(project_dir)
        overrides = OverrideFile(
            project_id=project.project_id,
            overrides=[
                ReadingOverride(
                    line_id=line_id,
                    expected_text=edit.expected_text,
                    span=Span(start=edit.span_start, end=edit.span_end),
                    reading=edit.reading,
                    romaji=edit.romaji,
                    display_only=edit.display_only,
                    author="user",
                    reason=edit.reason,
                )
            ],
        )
        try:
            apply_overrides(project, overrides)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        project.issues = inspect_project(project)
        save_project(project_dir, project)
        return _project_payload(project_dir)

    @app.post("/api/lines/{line_id}/timing")
    async def edit_timing(line_id: str, edit: TimingEdit) -> dict[str, object]:
        project = load_project(project_dir)
        try:
            create_timing_patch(
                project,
                line_id,
                edit.boundaries_ms,
                kind=edit.kind,
                boundary_index=edit.boundary_index,
                reason=edit.reason,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        save_project(project_dir, project)
        return _project_payload(project_dir)

    @app.post("/api/lines/{line_id}/restore-timing")
    async def restore_timing(line_id: str) -> dict[str, object]:
        project = load_project(project_dir)
        try:
            restore_raw_timing(project, line_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        save_project(project_dir, project)
        return _project_payload(project_dir)

    async def run_alignment(job: Job, allow_download: bool) -> None:
        try:
            job.emit("prepare", 0.05, "checking audio and cache", "running")
            if job.cancelled:
                job.emit("cancel", 1, "cancelled before alignment", "cancelled")
                return
            job.emit("align", 0.15, "running full-song Yohane alignment", "running")
            project, cache_hit = await asyncio.to_thread(
                align_project,
                project_dir,
                allow_download=allow_download,
                cancel_check=lambda: job.cancelled,
                force=True,
            )
            if job.cancelled:
                job.emit("cancel", 1, "alignment cancelled", "cancelled")
                return
            source = "cached result" if cache_hit else "Yohane result"
            job.emit("complete", 1, f"loaded {source} for {len(project.lines)} lines", "completed")
        except AlignmentCancelled:
            job.emit("cancel", 1, "alignment cancelled", "cancelled")
        except Exception as exc:  # surfaced through the local job log
            job.emit("failed", 1, str(exc), "failed")
        finally:
            job.done.set()

    @app.post("/api/jobs/align")
    async def start_alignment(allow_download: bool = False) -> dict[str, str]:
        if workspace is not None:
            return start_workspace_job("align", True, allow_download)
        job = Job(id=str(uuid4()))
        job.emit("queued", 0, "alignment queued", "queued")
        app.state.jobs[job.id] = job
        asyncio.create_task(run_alignment(job, allow_download))
        return {"job_id": job.id}

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, bool]:
        if workspace is not None:
            saved_job(job_id)
            await asyncio.to_thread(workspace.cancel, job_id)
            return {"cancel_requested": True}
        job = app.state.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "unknown job")
        job.cancelled = True
        return {"cancel_requested": True}

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str) -> StreamingResponse:
        if workspace is not None:
            saved_job(job_id)

            async def persisted_stream():
                previous = None
                while True:
                    value = await asyncio.to_thread(saved_job, job_id)
                    if value != previous:
                        yield f"data: {json.dumps(value, ensure_ascii=False)}\n\n"
                        previous = value
                    if value["status"] not in ("queued", "running"):
                        break
                    await asyncio.sleep(0.4)

            return StreamingResponse(persisted_stream(), media_type="text/event-stream")
        job = app.state.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "unknown job")

        async def stream():  # type: ignore[no-untyped-def]
            cursor = 0
            while True:
                while cursor < len(job.events):
                    event = job.events[cursor]
                    cursor += 1
                    yield f"data: {event.model_dump_json()}\n\n"
                if job.done.is_set():
                    break
                await asyncio.sleep(0.15)

        return StreamingResponse(stream(), media_type="text/event-stream")

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{path:path}")
        async def spa(path: str) -> FileResponse:
            requested = static_dir / path
            target = requested if path and requested.is_file() else static_dir / "index.html"
            return FileResponse(target)

    else:

        @app.get("/")
        async def missing_frontend() -> HTMLResponse:
            return HTMLResponse(
                "<h1>Karaoke Studio API</h1>"
                "<p>Build the React app with npm --prefix web run build.</p>"
            )

    return app
