"""Independent desktop job worker; progress survives closing the app window."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .derived_ass import OverwideError
from .media_render import upload_copies, write_record
from .models import utc_now
from .project_io import load_project, save_project
from .service import _production_lock, align_project, produce_project
from .workspace_11月7日 import ProductionInput

STAGES = {
    "歌词解析": 0.05,
    "输入归档": 0.12,
    "音频准备": 0.22,
    "整曲对齐": 0.35,
    "模板导出": 0.7,
    "字幕展开及成片": 0.8,
    "压缩上传版": 0.9,
}


def run(request_file: Path) -> int:
    request = json.loads(request_file.read_text(encoding="utf-8"))
    state_file = Path(request["state_file"])
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state.update(
        pid=os.getpid(), status="running", message="准备制作", updated_at=utc_now().isoformat()
    )
    write_record(state_file, state)

    def event(stage: str, status: str):
        if status == "failed":
            return
        state.update(
            stage=stage,
            progress=STAGES.get(stage, state["progress"]),
            message=f"{stage}" + ("完成" if status == "completed" else "中"),
            updated_at=utc_now().isoformat(),
        )
        write_record(state_file, state)

    try:
        root = Path(request["project_dir"])
        action = request.get("action")
        if action in ("render", "align"):
            files = run_editor(root, action, request, event)
            state.update(
                status="completed",
                progress=1,
                stage="完成",
                files=files,
                message="导出完成" if action == "render" else "对齐完成",
                updated_at=utc_now().isoformat(),
            )
            write_record(state_file, state)
            return 0

        inputs = ProductionInput.model_validate(request["inputs"]).resolved()
        if inputs.license_accepted:
            project = load_project(root)
            project.model.license_accepted_at = utc_now()
            save_project(root, project)
        title_text = (
            inputs.title_text
            if inputs.title_text is not None
            else inputs.title + (f"/{inputs.artist}" if inputs.artist else "")
        )
        arguments = dict(
            video=inputs.video,
            lyrics=inputs.lyrics,
            title=inputs.title,
            audio=inputs.audio,
            trim_start=inputs.trim_start,
            trim_end=inputs.trim_end,
            theme=inputs.theme,
            colors={"sung": inputs.color} if inputs.color else {},
            title_text=title_text,
            off_vocal=inputs.off_vocal,
            translation=inputs.translation,
            outputs=inputs.outputs,
            blackout_bottom=inputs.blackout_bottom or None,
            video_bitrate_mbps=inputs.video_bitrate_mbps,
            countdown=inputs.countdown,
            katakana_ruby=inputs.katakana_ruby,
        )
        record = root / ".karaoke-work/production-request.json"
        if request.get("use_project_settings") and record.is_file():
            saved = json.loads(record.read_text(encoding="utf-8"))
            saved.pop("project_dir", None)
            for key in ("video", "audio", "lyrics", "off_vocal", "translation"):
                if saved.get(key) is not None:
                    saved[key] = Path(saved[key])
            arguments.update(saved)
        _, result, _ = produce_project(
            **arguments,
            project_dir=root,
            fresh=inputs.fresh,
            prepare_only=inputs.mode == "prepare",
            allow_download=inputs.allow_download,
            on_event=event,
        )
        files = (
            {name: str(item.path) for name, item in result.media.outputs.items()}
            if result.media
            else {}
        )
        state.update(
            status="completed",
            progress=1,
            stage="完成",
            message="对齐完成，可进入编辑" if inputs.mode == "prepare" else "制作完成",
            files=files,
            updated_at=utc_now().isoformat(),
        )
        write_record(state_file, state)
        return 0
    except Exception as exc:
        details = {}
        if isinstance(exc, OverwideError):
            details["overwide"] = [
                dict(index=line.index, text=line.text, width_px=line.width) for line in exc.lines
            ]
        message = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            message = "对齐模型运行失败，请检查模型和运行环境后重试"
        state.update(
            status="failed",
            message=message,
            error_type=type(exc).__name__,
            details=details,
            updated_at=utc_now().isoformat(),
        )
        write_record(state_file, state)
        return 1


def run_editor(root: Path, action: str, request: dict, event) -> dict:
    work = root / ".karaoke-work"
    work.mkdir(exist_ok=True)
    if action == "align":
        event("整曲对齐", "started")
        with _production_lock(work / "production.lock"):
            align_project(
                root,
                force=request.get("fresh", True),
                allow_download=request.get("allow_download", False),
            )
        return {}

    from .ass import export_ass
    from .editor_11月7日 import save_settings
    from .render_job import load_render_job, run_render_job, with_video_bitrate

    job_path = root / "render-job.json"
    if not job_path.is_file():
        save_settings(root, {})
    with _production_lock(work / "production.lock"):
        project = load_project(root)
        if project.alignment_stale:
            raise ValueError("歌词已修改，请重新对齐后导出")
        if not project.source.video_path:
            raise ValueError("这个项目需要视频素材才能导出 MP4")
        render = with_video_bitrate(load_render_job(job_path), request.get("video_bitrate_mbps"))
        source = root / "EditorSource-11月7日.ass"
        source.write_text(export_ass(project), encoding="utf-8")
        render = render.model_copy(
            update={"source_ass": source, "reuse_outputs": not request.get("fresh", True)}
        )
        event("字幕展开及成片", "started")
        result = run_render_job(render)
        files = (
            {name: str(item.path) for name, item in result.media.outputs.items()}
            if result.media
            else {}
        )
        if request.get("upload") and files:
            event("压缩上传版", "started")
            files = upload_copies(files)
        return files


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1])))
