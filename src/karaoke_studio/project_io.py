from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .migrations import migrate_payload
from .models import KaraokeProject, utc_now

PROJECT_FILENAME = "project.karaoke.json"
OVERRIDES_FILENAME = "overrides.karaoke.json"


class ProjectReadError(RuntimeError):
    def __init__(self, message: str, raw: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.raw = raw


def project_file(path: Path) -> Path:
    return path if path.name == PROJECT_FILENAME else path / PROJECT_FILENAME


def create_project(directory: Path, title: str) -> KaraokeProject:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = project_file(directory)
    if target.exists():
        raise FileExistsError(f"project already exists: {target}")
    project = KaraokeProject(project_id=str(uuid4()), title=title)
    save_project(target, project)
    return project


def load_project(path: Path, *, recover_read_only: bool = False) -> KaraokeProject:
    target = project_file(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        migrated, _ = migrate_payload(payload)
        return KaraokeProject.model_validate(migrated)
    except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        if not recover_read_only:
            raise ProjectReadError(f"cannot open project: {exc}") from exc
        backup = target.with_suffix(target.suffix + ".bak")
        if backup.exists():
            try:
                recovered = KaraokeProject.model_validate_json(backup.read_text(encoding="utf-8"))
                recovered.read_only = True
                return recovered
            except (OSError, ValidationError):
                pass
        raise ProjectReadError(f"project is damaged and no valid backup exists: {exc}") from exc


def save_project(path: Path, project: KaraokeProject) -> None:
    if project.read_only:
        raise PermissionError("damaged projects opened in read-only mode cannot be saved")
    target = project_file(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    project.updated_at = utc_now()
    data = project.model_dump_json(indent=2, exclude_none=True) + "\n"
    backup = target.with_suffix(target.suffix + ".bak")
    if target.exists():
        backup.write_bytes(target.read_bytes())
    fd, temporary = tempfile.mkstemp(prefix=".karaoke-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def relative_to_project(project_dir: Path, source: Path) -> str:
    resolved_root = project_dir.resolve()
    resolved_source = source.resolve()
    try:
        return str(resolved_source.relative_to(resolved_root))
    except ValueError as exc:
        raise ValueError("project files must be copied inside the project directory") from exc


def resolve_project_path(project_dir: Path, relative: str) -> Path:
    root = project_dir.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("path escapes project directory")
    return candidate
