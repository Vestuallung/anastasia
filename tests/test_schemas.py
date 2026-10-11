from __future__ import annotations

import json
from pathlib import Path

from karaoke_studio.models import KaraokeProject, OverrideFile
from karaoke_studio.render_job import RenderJob

ROOT = Path(__file__).resolve().parents[1]


def test_committed_project_schema_matches_pydantic_model() -> None:
    committed = json.loads((ROOT / "schemas" / "project.karaoke.schema.json").read_text())

    assert committed == KaraokeProject.model_json_schema()
    assert committed["properties"]["schema_version"]["const"] == 1
    assert committed["additionalProperties"] is False


def test_committed_override_schema_matches_pydantic_model() -> None:
    committed = json.loads((ROOT / "schemas" / "overrides.karaoke.schema.json").read_text())

    assert committed == OverrideFile.model_json_schema()
    assert committed["properties"]["schema_version"]["const"] == 1
    assert committed["additionalProperties"] is False


def test_committed_render_job_schema_matches_pydantic_model() -> None:
    committed = json.loads((ROOT / "schemas" / "render-job.schema.json").read_text())

    assert committed == RenderJob.model_json_schema()
    assert committed["additionalProperties"] is False
