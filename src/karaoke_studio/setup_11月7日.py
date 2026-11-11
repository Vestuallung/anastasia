"""Portable application settings and persistent setup tasks."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import config_path, configured_path, load_config, section, tool_path, yohane_python


def now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _toml(settings: dict) -> str:
    sections: list[str] = []

    def scalar(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, list):
            return "[" + ", ".join(scalar(item) for item in value) + "]"
        raise ValueError("unsupported configuration value")

    def emit(table, parts):
        values = [
            f"{json.dumps(key)} = {scalar(value)}"
            for key, value in table.items()
            if not isinstance(value, dict)
        ]
        if values:
            header = "[" + ".".join(json.dumps(item) for item in parts) + "]" if parts else ""
            sections.append("\n".join(([header] if header else []) + values))
        for key, value in table.items():
            if isinstance(value, dict):
                emit(value, [*parts, key])

    emit(settings, [])
    return "\n\n".join(sections) + "\n"


class SettingsEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    alignment_python: str = ""
    device: Literal["cpu", "cuda", "mps"] = "cpu"
    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    model_cache: str = ""
    japanese_font: str = Field(min_length=1)
    japanese_font_path: str = Field(min_length=1)
    chinese_font: str = Field(min_length=1)
    chinese_font_path: str = Field(min_length=1)
    groups: dict[str, dict[str, str]]
    default_theme: str

    @model_validator(mode="after")
    def validate_groups(self):
        if self.default_theme not in self.groups:
            raise ValueError("默认团体必须在团体列表中")
        for key, value in self.groups.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
                raise ValueError("团体代号使用英文字母、数字、短横线或下划线")
            if not value.get("label") or not re.fullmatch(
                r"#[0-9A-Fa-f]{6}", value.get("sung", "")
            ):
                raise ValueError("请填写团体名和六位色号")
        return self


def editable_settings() -> dict:
    settings = load_config()
    return dict(
        ffmpeg=settings["tools"]["ffmpeg"],
        ffprobe=settings["tools"]["ffprobe"],
        alignment_python=settings["runtime"]["yohane_python"],
        device=settings["runtime"]["device"],
        model_id=settings["model"]["id"],
        model_revision=settings["model"]["revision"],
        model_cache=settings["model"]["cache_dir"],
        japanese_font=settings["fonts"]["japanese_family"],
        japanese_font_path=settings["fonts"]["japanese_path"],
        chinese_font=settings["fonts"]["chinese_family"],
        chinese_font_path=settings["fonts"]["chinese_path"],
        groups=settings["groups"],
        default_theme=settings["production"]["default_theme"],
    )


def save_application_settings(edit: SettingsEdit, fallback: Path) -> Path:
    settings = copy.deepcopy(load_config())
    settings["tools"].update(ffmpeg=edit.ffmpeg.strip(), ffprobe=edit.ffprobe.strip())
    settings["runtime"].update(yohane_python=edit.alignment_python.strip(), device=edit.device)
    model = settings["model"]
    changed_model = model["id"] != edit.model_id.strip()
    model.update(
        id=edit.model_id.strip(),
        revision=edit.model_revision.strip(),
        cache_dir=edit.model_cache.strip(),
        url="https://huggingface.co/" + edit.model_id.strip(),
    )
    if changed_model:
        model["license"] = "See model page"
    settings["fonts"].update(
        japanese_family=edit.japanese_font.strip(),
        japanese_path=edit.japanese_font_path.strip(),
        chinese_family=edit.chinese_font.strip(),
        chinese_path=edit.chinese_font_path.strip(),
    )
    settings["groups"] = edit.groups
    settings["production"]["default_theme"] = edit.default_theme
    target = config_path() or fallback
    target.parent.mkdir(parents=True, exist_ok=True)
    content = _toml(settings)
    tomllib.loads(content)
    if target.is_file():
        shutil.copy2(target, target.with_suffix(".toml.bak"))
    temp = target.with_name(target.name + "." + uuid4().hex + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(target)
    os.environ["KARAOKE_CONFIG"] = str(target)
    load_config.cache_clear()
    return target


def _tool_status(name: str) -> dict:
    executable = tool_path(name)
    try:
        command = (
            [executable, "-hide_banner", "-filters"]
            if name == "ffmpeg"
            else [executable, "-version"]
        )
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8
        )
        output = result.stdout + result.stderr
        ass = " ass " in output if name == "ffmpeg" else True
        ready = result.returncode == 0 and ass
        return dict(
            ready=ready,
            path=executable,
            message="就绪"
            if ready
            else "请选择包含 ASS 滤镜的 FFmpeg"
            if not ass
            else output[:200],
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(ready=False, path=executable, message=str(exc))


def environment_status() -> dict:
    python = yohane_python()
    model = section("model")
    request = dict(repo_id=model["id"], revision=model["revision"], local_files_only=True)
    if model["cache_dir"]:
        request["cache_dir"] = str(configured_path(model["cache_dir"]))
    script = """import importlib.util,json,sys
names=['yohane','torch','torchaudio','transformers','huggingface_hub']
missing=[name for name in names if importlib.util.find_spec(name) is None]
result={'runtime_ready': not missing, 'missing': missing, 'model_ready':False}
if not missing:
 try:
  from huggingface_hub import snapshot_download
  result['model_path']=snapshot_download(**json.loads(sys.argv[1]))
  result['model_ready']=True
 except Exception as exc:
  result['model_message']=str(exc)[:250]
print(json.dumps(result))
"""
    alignment = dict(runtime_ready=False, model_ready=False, python=str(python), missing=[])
    try:
        result = subprocess.run(
            [str(python), "-c", script, json.dumps(request)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode == 0:
            alignment.update(json.loads(result.stdout.strip().splitlines()[-1]))
        else:
            alignment["message"] = result.stderr[-500:]
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        alignment["message"] = str(exc)
    return dict(
        tools={name: _tool_status(name) for name in ["ffmpeg", "ffprobe"]},
        alignment=alignment,
        model_url=model["url"],
        model_license=model["license"],
        fonts={
            kind: dict(
                ready=configured_path(section("fonts")[kind + "_path"]).is_file(),
                family=section("fonts")[kind + "_family"],
            )
            for kind in ["japanese", "chinese"]
        },
    )


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["environment", "model"]
    license_accepted: bool = False


class SetupTasks:
    def __init__(self, home: Path, workspace: Path):
        self.home = home.resolve()
        self.directory = workspace / ".studio" / "setup"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.processes: dict[str, subprocess.Popen] = {}
        self.lock = threading.Lock()

    def _path(self, task_id):
        if not re.fullmatch(r"[0-9a-f]{32}", task_id):
            raise ValueError("unknown setup task")
        return self.directory / ("Setup-" + task_id + ".json")

    def get(self, task_id: str) -> dict:
        path = self._path(task_id)
        if not path.is_file():
            raise ValueError("unknown setup task")
        value = json.loads(path.read_text(encoding="utf-8"))
        process = self.processes.get(task_id)
        pid_file = path.with_suffix(".pid.json")
        if value.get("pid") is None and pid_file.is_file():
            value["pid"] = json.loads(pid_file.read_text(encoding="utf-8"))["pid"]
        if (
            process is not None
            and process.poll() is not None
            and value["status"] in {"queued", "running"}
        ):
            value.update(
                status="interrupted", message="配置任务已中断，可重新开始", finished_at=now()
            )
            atomic_json(path, value)
        elif process is None and value["status"] in {"queued", "running"}:
            if self._verified_pid(task_id, value) is None:
                value.update(
                    status="interrupted", message="配置任务已中断，可重新开始", finished_at=now()
                )
                atomic_json(path, value)
        return value

    def _verified_pid(self, task_id: str, value: dict) -> int | None:
        process = self.processes.get(task_id)
        if process:
            return process.pid if process.poll() is None else None
        pid = value.get("pid")
        if not pid:
            return None
        try:
            command = (
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine",
                ]
                if os.name == "nt"
                else ["ps", "-p", str(pid), "-o", "command="]
            )
            line = subprocess.check_output(command, text=True, encoding="utf-8", timeout=3)
            if "karaoke_studio.setup_worker_11月7日" in line and str(self._path(task_id)) in line:
                return int(pid)
        except (OSError, subprocess.SubprocessError):
            pass
        return None

    def list(self) -> list[dict]:
        return sorted(
            [
                self.get(p.stem.removeprefix("Setup-"))
                for p in self.directory.glob("Setup-*.json")
                if not p.name.endswith(".pid.json")
            ],
            key=lambda v: v["created_at"],
            reverse=True,
        )

    def start(self, request: SetupRequest) -> dict:
        if request.action == "model" and not request.license_accepted:
            raise ValueError("请先确认模型页面的使用许可")
        with self.lock:
            if any(task["status"] in {"queued", "running"} for task in self.list()):
                raise ValueError("已有配置任务正在运行")
            task_id = uuid4().hex
            path = self._path(task_id)
            value = dict(
                id=task_id,
                action=request.action,
                status="queued",
                created_at=now(),
                home=str(self.home),
                config=str(config_path()) if config_path() else None,
                message="正在准备配置",
                pid=None,
            )
            atomic_json(path, value)
            command = [sys.executable, "-m", "karaoke_studio.setup_worker_11月7日", str(path)]
            options = dict(
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.home,
            )
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                options["start_new_session"] = True
            try:
                process = subprocess.Popen(command, **options)
            except OSError as exc:
                value.update(status="failed", message=str(exc), finished_at=now())
                atomic_json(path, value)
                return value
            self.processes[task_id] = process
            # The worker owns further state writes; keep the PID in a separate sidecar.
            atomic_json(path.with_suffix(".pid.json"), dict(pid=process.pid))
            return value

    def cancel(self, task_id):
        value = self.get(task_id)
        if value["status"] not in {"queued", "running"}:
            return value
        pid = self._verified_pid(task_id, value)
        if pid:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(pid, signal.SIGTERM)
        else:
            raise ValueError("请等待配置任务结束后重新开始")
        value.update(status="cancelled", message="已停止配置", finished_at=now())
        atomic_json(self._path(task_id), value)
        return value


def application_settings_router(home: Path, workspace: Path) -> APIRouter:
    router = APIRouter(prefix="/api/application")
    tasks = SetupTasks(home, workspace)

    @router.get("/settings")
    def settings():
        return dict(settings=editable_settings(), config=str(config_path() or home / "config.toml"))

    @router.post("/settings")
    def save(edit: SettingsEdit):
        if any(task["status"] in {"queued", "running"} for task in tasks.list()):
            raise HTTPException(409, "请等待配置任务结束后再保存")
        path = save_application_settings(edit, home / "config.toml")
        return dict(settings=editable_settings(), config=str(path), restart_required=True)

    @router.get("/status")
    def status():
        return environment_status()

    @router.get("/tasks")
    def list_tasks():
        return tasks.list()

    @router.post("/setup")
    def setup(request: SetupRequest):
        try:
            return tasks.start(request)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/tasks/{task_id}/cancel")
    def cancel(task_id: str):
        try:
            return tasks.cancel(task_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return router
