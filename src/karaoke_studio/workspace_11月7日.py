"""Desktop library and persisted production jobs shared by native and browser hosts."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .api import create_app
from .config import configured_path, section
from .derived_ass import _load_translation
from .media_render import parse_media_time, write_record
from .models import utc_now
from .project_io import create_project, load_project
from .setup_11月7日 import application_settings_router


class ProductionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    artist: str = ""
    video: Path
    lyrics: Path
    audio: Path | None = None
    off_vocal: Path | None = None
    translation: Path | None = None
    trim_start: str = "0"
    trim_end: str | None = None
    theme: str = Field(default_factory=lambda: section("production")["default_theme"])
    color: str | None = None
    title_text: str | None = None
    outputs: list[Literal["on_vocal_karaoke", "on_vocal_karaoke_zh", "off_vocal_karaoke"]] = Field(
        default_factory=lambda: ["on_vocal_karaoke"]
    )
    mode: Literal["prepare", "produce"] = "prepare"
    fresh: bool = True
    countdown: bool = True
    katakana_ruby: bool = True
    blackout_bottom: float = Field(default=0, ge=0, le=0.5)
    video_bitrate_mbps: float | None = Field(default=None, ge=0.1, le=1000, allow_inf_nan=False)
    allow_download: bool = False
    license_accepted: bool = False

    @model_validator(mode="after")
    def valid_input(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("请输入歌曲名")
        if len(set(self.outputs)) != len(self.outputs) or not self.outputs:
            raise ValueError("请选择成片版本")
        start = parse_media_time(self.trim_start)
        if start < 0 or (self.trim_end is not None and parse_media_time(self.trim_end) <= start):
            raise ValueError("结束时间应晚于开始时间")
        if self.allow_download and not self.license_accepted:
            raise ValueError("请确认模型许可后启用下载")
        return self

    def resolved(self) -> ProductionInput:
        values = self.model_dump()
        for key in ("video", "lyrics", "audio", "off_vocal", "translation"):
            if values[key] is not None:
                candidate = Path(values[key]).expanduser().resolve(strict=True)
                if not candidate.is_file():
                    raise ValueError(f"请选择文件：{candidate}")
                values[key] = candidate
        result = ProductionInput.model_validate(values)
        text = result.lyrics.read_text(encoding="utf-8-sig")
        first = next((line for line in text.splitlines() if line.strip()), "")
        bilingual = first.startswith(("日文：", "日文:"))
        if bilingual:
            _load_translation(result.lyrics)
        if "on_vocal_karaoke_zh" in result.outputs and not (bilingual or result.translation):
            raise ValueError("中日版需要中日对照歌词或独立翻译文件")
        if "off_vocal_karaoke" in result.outputs and not result.off_vocal:
            raise ValueError("伴奏版需要独立伴奏音轨")
        return result


def worker_alive(state: dict) -> bool:
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if os.name == "nt":
            command = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
                ],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            ).stdout
        else:
            command = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            ).stdout
        return (
            "karaoke_studio.gui_worker_11月7日" in command
            and str(state.get("request_file", "")) in command
        )
    except (OSError, subprocess.SubprocessError):
        return False


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.storage = self.root / ".studio"
        self.storage.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.storage / "Projects-11月7日.json"
        self.processes: dict[str, subprocess.Popen] = {}
        try:
            self.registry = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.registry = {}

    def register(self, path: Path) -> dict:
        path = path.expanduser().resolve()
        project = load_project(path, recover_read_only=True)
        key = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        record = dict(
            key=key,
            title=project.title,
            path=str(path),
            updated_at=project.updated_at.isoformat(),
            line_count=len(project.lines),
        )
        self.registry[key] = record
        write_record(self.registry_file, self.registry)
        return {**record, "url": f"/p/{key}/"}

    def projects(self) -> list[dict]:
        result = []
        for record in list(self.registry.values()):
            try:
                project = load_project(Path(record["path"]), recover_read_only=True)
                result.append(
                    {
                        **record,
                        "title": project.title,
                        "line_count": len(project.lines),
                        "updated_at": project.updated_at.isoformat(),
                        "url": f"/p/{record['key']}/",
                    }
                )
            except (OSError, RuntimeError, ValueError):
                result.append({**record, "unavailable": True})
        return sorted(result, key=lambda value: value["updated_at"], reverse=True)

    def job_file(self, job_id: str) -> Path:
        if not job_id or any(c not in "0123456789abcdef-" for c in job_id):
            raise ValueError("找不到任务")
        return self.storage / "jobs" / f"Job-{job_id}.json"

    def job(self, job_id: str) -> dict:
        path = self.job_file(job_id)
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["status"] in ("running", "queued"):
            process = self.processes.get(job_id)
            live = process.poll() is None if process is not None else worker_alive(state)
            if not live:
                # The worker writes terminal state before exiting; refresh after poll.
                state = json.loads(path.read_text(encoding="utf-8"))
                if state["status"] in ("running", "queued"):
                    state.update(
                        status="interrupted",
                        message="任务已中断，可以继续或从头制作",
                        updated_at=utc_now().isoformat(),
                    )
                    write_record(path, state)
        try:
            editable = bool(load_project(Path(state["project_path"]), recover_read_only=True).lines)
        except (OSError, ValueError, RuntimeError):
            editable = False
        return {**state, "editable": editable}

    def jobs(self) -> list[dict]:
        result = []
        for path in (self.storage / "jobs").glob("Job-*.json"):
            try:
                result.append(self.job(path.stem.removeprefix("Job-")))
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda value: value["created_at"], reverse=True)

    def start(self, inputs: ProductionInput, *, project_dir: Path | None = None) -> dict:
        inputs = inputs.resolved()
        root = (
            project_dir
            or self.root
            / f"Production-{datetime.now().month}月{datetime.now().day}日-{uuid4().hex[:6]}"
        )
        root = root.resolve()
        return self._start_job(
            root,
            inputs.mode,
            inputs.fresh,
            {
                "inputs": inputs.model_dump(mode="json"),
                "use_project_settings": project_dir is not None,
            },
            inputs.title,
        )

    def start_editor(
        self, root: Path, mode: str, fresh: bool = True, allow_download: bool = False,
        upload: bool = False,
        video_bitrate_mbps: float | None = None,
    ) -> dict:
        if mode not in ("align", "render"):
            raise ValueError("未知的编辑任务")
        return self._start_job(root, mode, fresh, {
            "allow_download": allow_download, "upload": upload, "video_bitrate_mbps": video_bitrate_mbps,
        })

    def editor_job(self, root: Path, job_id: str | None = None) -> dict | None:
        for value in [self.job(job_id)] if job_id else self.jobs():
            if value["project_path"] == str(root) and value["mode"] in ("align", "render"):
                return value
        return None

    def _start_job(
        self, root: Path, mode: str, fresh: bool, request: dict, title: str | None = None
    ) -> dict:
        for existing in self.jobs():
            if existing["project_path"] == str(root) and existing["status"] in (
                "running",
                "queued",
            ):
                raise ValueError("此项目正在制作，可在任务列表查看")
        if title is not None and not (root / "project.karaoke.json").is_file():
            create_project(root, title)
        project = self.register(root)
        job_id = str(uuid4())
        request_file = self.storage / "jobs" / f"Request-{job_id}.json"
        state_file = self.job_file(job_id)
        now = utc_now().isoformat()
        state = dict(
            id=job_id,
            title=project["title"],
            project_key=project["key"],
            project_url=project["url"],
            project_path=str(root),
            mode=mode,
            fresh=fresh,
            upload=request.get("upload", False),
            video_bitrate_mbps=request.get("video_bitrate_mbps"),
            status="queued",
            stage="准备",
            progress=0,
            message="等待制作",
            created_at=now,
            updated_at=now,
            pid=None,
            request_file=str(request_file),
            files={},
        )
        write_record(
            request_file,
            dict(
                **request,
                action=mode,
                fresh=fresh,
                project_dir=str(root),
                state_file=str(state_file),
            ),
        )
        write_record(state_file, state)
        options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        try:
            self.processes[job_id] = subprocess.Popen(
                [sys.executable, "-m", "karaoke_studio.gui_worker_11月7日", str(request_file)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                **options,
            )
        except OSError as exc:
            state.update(status="failed", message=str(exc))
            write_record(state_file, state)
            raise
        return state

    def cancel(self, job_id: str) -> dict:
        state = self.job(job_id)
        if state["status"] not in ("running", "queued"):
            return state
        process = self.processes.get(job_id)
        pid = process.pid if process is not None and process.poll() is None else state.get("pid")
        if pid and ((process is not None and process.poll() is None) or worker_alive(state)):
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False
                )
            else:
                with suppress(ProcessLookupError):
                    os.killpg(pid, signal.SIGTERM)
            if process is not None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        os.killpg(pid, signal.SIGKILL)
                    process.wait(timeout=3)
        state.update(status="cancelled", message="已停止制作", updated_at=utc_now().isoformat())
        write_record(self.job_file(job_id), state)
        return state


class ProjectDispatcher:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.apps: dict[str, FastAPI] = {}

    async def __call__(self, scope, receive, send):
        key = scope.get("path_params", {}).get("project_key")
        record = self.workspace.registry.get(key)
        if record is None:
            await JSONResponse({"detail": "找不到项目"}, status_code=404)(scope, receive, send)
            return
        if key not in self.apps:
            self.apps[key] = create_app(Path(record["path"]), workspace=self.workspace)
        await self.apps[key](scope, receive, send)


class OpenProject(BaseModel):
    path: Path


class RetryJob(BaseModel):
    fresh: bool = True
    mode: Literal["prepare", "produce"] | None = None


def create_workspace_app(directory: Path) -> FastAPI:
    workspace = Workspace(directory)
    app = FastAPI(title="Karaoke Studio", docs_url=None, redoc_url=None)
    app.include_router(
        application_settings_router(
            Path(os.environ.get("KARAOKE_HOME", Path.cwd())), workspace.root
        )
    )
    app.state.workspace = workspace

    @app.get("/api/workspace")
    async def info():
        return dict(
            mode="workspace",
            path=str(workspace.root),
            groups=section("groups"),
            model={key: section("model")[key] for key in ("url", "license")},
            default_theme=section("production")["default_theme"],
            projects=workspace.projects(),
            jobs=workspace.jobs(),
        )

    @app.post("/api/workspace/open")
    async def open_existing(value: OpenProject):
        try:
            return workspace.register(value.path)
        except (ValueError, OSError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/workspace/assets")
    async def upload_asset(
        file: Annotated[UploadFile, File()],
        kind: Annotated[Literal["video", "audio", "lyrics"], Form()],
    ):
        target = (
            workspace.storage
            / "uploads"
            / f"{kind}-{uuid4().hex}{Path(file.filename or '').suffix.lower()}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
        return dict(path=str(target), name=file.filename)

    @app.post("/api/workspace/produce")
    async def start_production(value: ProductionInput):
        try:
            return workspace.start(value)
        except (ValueError, OSError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/workspace/lyrics-info")
    async def lyrics_info(value: OpenProject):
        try:
            text = value.path.expanduser().read_text(encoding="utf-8-sig")
            first = next((line for line in text.splitlines() if line.strip()), "")
            bilingual = first.startswith(("日文：", "日文:"))
            count = (
                len(_load_translation(value.path)["lines"])
                if bilingual
                else len([line for line in text.splitlines() if line.strip()])
            )
            return dict(bilingual=bilingual, line_count=count)
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/workspace/jobs")
    async def jobs():
        return workspace.jobs()

    @app.get("/api/workspace/jobs/{job_id}")
    async def job(job_id: str):
        try:
            return workspace.job(job_id)
        except (ValueError, OSError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/workspace/jobs/{job_id}/cancel")
    async def cancel(job_id: str):
        try:
            return workspace.cancel(job_id)
        except (ValueError, OSError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/workspace/jobs/{job_id}/retry")
    async def retry(job_id: str, value: RetryJob):
        try:
            previous = workspace.job(job_id)
            request = json.loads(Path(previous["request_file"]).read_text(encoding="utf-8"))
            if previous["mode"] in ("align", "render"):
                return workspace.start_editor(
                    Path(previous["project_path"]),
                    previous["mode"],
                    value.fresh,
                    request.get("allow_download", False),
                    request.get("upload", False),
                    request.get("video_bitrate_mbps"),
                )
            inputs = ProductionInput.model_validate(
                {
                    **request["inputs"],
                    "fresh": value.fresh,
                    **({"mode": value.mode} if value.mode else {}),
                }
            )
            return workspace.start(inputs, project_dir=Path(previous["project_path"]))
        except (ValueError, OSError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    app.mount("/p/{project_key}", ProjectDispatcher(workspace))
    static = Path(__file__).parent / "static"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/font/japanese")
    async def japanese_font():
        return FileResponse(configured_path(section("fonts")["japanese_path"]))

    @app.get("/font/chinese")
    async def chinese_font():
        return FileResponse(configured_path(section("fonts")["chinese_path"]))

    @app.get("/font/NotoSansJP.ttf")
    async def font():
        return FileResponse(
            Path(__file__).parent / "assets/fonts/NotoSansJP-Variable.ttf", media_type="font/ttf"
        )

    @app.get("/{path:path}")
    async def index(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "找不到此功能"}, status_code=404)
        return FileResponse(static / "index.html")

    return app
