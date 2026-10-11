from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from .cache import alignment_cache_key, normalized_romaji
from .config import configured_path, section, yohane_python
from .models import KaraokeProject, RawAlignedLine, RawAlignment, utc_now


class AlignmentCancelled(RuntimeError):
    pass


def find_yohane_python(project_dir: Path) -> Path:
    candidate = yohane_python()
    if candidate.is_file():
        return candidate.resolve()
    raise RuntimeError(f"Yohane Python executable: {candidate}")


def run_yohane(
    project: KaraokeProject,
    project_dir: Path,
    *,
    allow_download: bool = False,
    python: Path | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> RawAlignment:
    if not project.audio.prepared_path or not project.audio.prepared_sha256:
        raise ValueError("prepare audio before alignment")
    if allow_download and not project.model.license_accepted_at:
        raise PermissionError("accept the model license before enabling download")
    interpreter = python or find_yohane_python(project_dir)
    audio = (project_dir / project.audio.prepared_path).resolve()
    src_root = Path(__file__).resolve().parents[1]
    request = {
        "audio_path": str(audio),
        "lyrics": normalized_romaji(project),
        "model_id": project.model.model_id,
        "model_revision": project.model.revision,
        "allow_download": allow_download,
        "cache_dir": str(configured_path(section("model")["cache_dir"]))
        if section("model")["cache_dir"]
        else None,
    }
    work_root = project_dir / ".karaoke-work"
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yohane-", dir=work_root) as temporary:
        request_path = Path(temporary) / "request.json"
        response_path = Path(temporary) / "response.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "YOHANE_DEVICE": section("runtime")["device"],
                "PYTORCH_ENABLE_MPS_FALLBACK": "1",
                "PYTHONPATH": str(src_root),
            }
        )
        if not allow_download:
            env["HF_HUB_OFFLINE"] = "1"
            env["PYTORCHF_HUB_OFFLINE"] = "1"
            env["PYTORHF_HUB_OFFLINE"] = "1"
        process = subprocess.Popen(
            [
                str(interpreter),
                "-m",
                "karaoke_studio.yohane_worker",
                str(request_path),
                str(response_path),
            ],
            env=env,
        )
        while process.poll() is None:
            if cancel_check and cancel_check():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise AlignmentCancelled("alignment cancelled")
            time.sleep(0.2)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, process.args)
        result = json.loads(response_path.read_text(encoding="utf-8"))
    if len(result["lines"]) != len(project.lines):
        raise RuntimeError(
            f"Yohane returned {len(result['lines'])} lines for {len(project.lines)} lyric lines"
        )
    romaji_hash = hashlib.sha256(normalized_romaji(project).encode()).hexdigest()
    alignment = RawAlignment(
        cache_key=alignment_cache_key(project),
        created_at=utc_now(),
        adapter_version=result["adapter_version"],
        model_id=project.model.model_id,
        model_revision=project.model.revision,
        audio_sha256=project.audio.prepared_sha256,
        normalized_romaji_sha256=romaji_hash,
        lines=[
            RawAlignedLine(line_id=line.id, **raw)
            for line, raw in zip(project.lines, result["lines"], strict=True)
        ],
    )
    project.model.resolved_snapshot = result["snapshot"]
    project.model.checksums = result["checksums"]
    return alignment
