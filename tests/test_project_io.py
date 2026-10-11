from __future__ import annotations

import json
from pathlib import Path

import pytest

from karaoke_studio.migrations import migrate_payload
from karaoke_studio.project_io import ProjectReadError, create_project, load_project, save_project


def test_v0_payload_migrates_in_memory_without_rewriting_source() -> None:
    payload = {"project_id": "old", "title": "Old", "lines": []}

    migrated, applied = migrate_payload(payload)

    assert applied == [1]
    assert migrated["schema_version"] == 1
    assert "schema_version" not in payload


def test_future_schema_is_rejected() -> None:
    with pytest.raises(ValueError, match="newer than supported"):
        migrate_payload({"schema_version": 99})


def test_atomic_save_retains_backup_and_recovers_read_only(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project = create_project(project_dir, "First")
    project.title = "Second"
    save_project(project_dir, project)
    target = project_dir / "project.karaoke.json"
    backup = project_dir / "project.karaoke.json.bak"
    assert json.loads(backup.read_text(encoding="utf-8"))["title"] == "First"

    target.write_text("{broken", encoding="utf-8")
    recovered = load_project(project_dir, recover_read_only=True)

    assert recovered.title == "First"
    assert recovered.read_only is True
    with pytest.raises(PermissionError):
        save_project(project_dir, recovered)


def test_damaged_project_without_backup_reports_error(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "project.karaoke.json").write_text("not json", encoding="utf-8")

    with pytest.raises(ProjectReadError, match="no valid backup"):
        load_project(project_dir, recover_read_only=True)
