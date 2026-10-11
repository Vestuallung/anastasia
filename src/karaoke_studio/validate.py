from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import tool_path
from .models import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    KaraokeProject,
    StructuralIssue,
)
from .project_io import load_project
from .timing import effective_boundaries
from .yohane_adapter import find_yohane_python


def inspect_project(project: KaraokeProject) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    ids: set[str] = set()
    for line in project.lines:
        if line.id in ids:
            issues.append(
                StructuralIssue(
                    code="duplicate_line_id",
                    severity="error",
                    line_id=line.id,
                    message="stable line ID is duplicated",
                )
            )
        ids.add(line.id)
        if line.display_text != "".join(token.text for token in line.display_tokens):
            issues.append(
                StructuralIssue(
                    code="display_roundtrip",
                    severity="error",
                    line_id=line.id,
                    message="display token sequence does not round-trip",
                )
            )
        input_count = len(line.yohane_input.split())
        if input_count != len(line.moras):
            issues.append(
                StructuralIssue(
                    code="cm_romaji_count",
                    severity="error",
                    line_id=line.id,
                    message="display mora count differs from yohane romaji unit count",
                    details={"cm": len(line.moras), "romaji": input_count},
                )
            )
    if project.raw_alignment:
        raw_by_id = {line.line_id: line for line in project.raw_alignment.lines}
        for line in project.lines:
            raw = raw_by_id.get(line.id)
            if not raw:
                issues.append(
                    StructuralIssue(
                        code="missing_raw_line",
                        severity="error",
                        line_id=line.id,
                        message="raw alignment has no matching line",
                    )
                )
                continue
            if len(raw.k_values_cs) != len(line.moras):
                issues.append(
                    StructuralIssue(
                        code="kf_cm_count",
                        severity="warning",
                        line_id=line.id,
                        message="raw Yohane k count differs from display mora count",
                        details={"kf": len(raw.k_values_cs), "cm": len(line.moras)},
                    )
                )
            boundaries = effective_boundaries(project, line.id)
            if boundaries != sorted(boundaries):
                issues.append(
                    StructuralIssue(
                        code="timing_order",
                        severity="error",
                        line_id=line.id,
                        message="effective timing is not ordered",
                    )
                )
    return issues


def doctor(project_dir: Path | None = None) -> dict[str, object]:
    ffmpeg = shutil.which(tool_path("ffmpeg"))
    ffprobe = shutil.which(tool_path("ffprobe"))
    checks: dict[str, object] = {
        "python": {"ok": sys.version_info >= (3, 12), "version": sys.version.split()[0]},
        "ffmpeg": {"ok": bool(ffmpeg), "path": ffmpeg},
        "ffprobe": {"ok": bool(ffprobe), "path": ffprobe},
    }
    try:
        probe = (
            "import fugashi; print(fugashi.__version__ "
            "if hasattr(fugashi, '__version__') else 'installed')"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        checks["mecab_unidic"] = {"ok": True, "detail": result.stdout.strip()}
    except (subprocess.SubprocessError, OSError):
        checks["mecab_unidic"] = {"ok": False}
    font_dir = Path(__file__).resolve().parent / "assets" / "fonts"
    checks["preview_font"] = {
        "ok": any(font_dir.glob("*.otf")) or any(font_dir.glob("*.ttf")),
        "path": str(font_dir),
    }
    project = load_project(project_dir, recover_read_only=True) if project_dir else None
    model_id = project.model.model_id if project else DEFAULT_MODEL_ID
    revision = project.model.revision if project else DEFAULT_MODEL_REVISION
    try:
        yohane_python = find_yohane_python(project_dir or Path.cwd())
        probe = (
            "from huggingface_hub import snapshot_download; import yohane; "
            "print(snapshot_download(repo_id=__import__('sys').argv[1], "
            "revision=__import__('sys').argv[2], local_files_only=True))"
        )
        env = os.environ.copy()
        env["HF_HUB_OFFLINE"] = "1"
        result = subprocess.run(
            [str(yohane_python), "-c", probe, model_id, revision],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=True,
        )
        checks["yohane"] = {"ok": True, "python": str(yohane_python)}
        checks["model"] = {
            "ok": True,
            "id": model_id,
            "revision": revision,
            "snapshot": result.stdout.strip().splitlines()[-1],
            "license_accepted": bool(project and project.model.license_accepted_at),
        }
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        checks["yohane"] = {"ok": False, "detail": str(exc)}
        checks["model"] = {
            "ok": False,
            "id": model_id,
            "revision": revision,
            "license_accepted": bool(project and project.model.license_accepted_at),
        }
    return checks
