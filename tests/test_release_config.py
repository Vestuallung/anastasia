from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_python(args: list[str], config: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["KARAOKE_HOME"] = str(ROOT)
    if config:
        env["KARAOKE_CONFIG"] = str(config)
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env, text=True, capture_output=True, check=True
    )


def test_custom_group_and_appearance_reach_render_job(tmp_path: Path) -> None:
    config = tmp_path / "custom.toml"
    config.write_text(
        '[production]\ndefault_theme="example"\n[groups.example]\nlabel="Example"\nsung="#00B379"\n[appearance]\nmain_size=72\n',
        encoding="utf-8",
    )
    source = tmp_path / "source.ass"
    source.write_text(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,K1,,0,0,0,karaoke,{\\k100}あ\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.ass"
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps({"source_ass": str(source), "output_ass": str(output), "audio_end": 2})
    )
    result = run_python(
        ["-m", "karaoke_studio.launcher", "--config", str(config), "render-job", str(job)]
    )
    assert json.loads(result.stdout)["font_size_px"] == 72
    text = output.read_text(encoding="utf-8")
    assert "Example" in text and "&H0079B300&" in text
    assert "Noto Sans CJK JP" in text
    assert r"\fs72.00" in text


def test_model_download_plan_uses_configured_revision(tmp_path: Path) -> None:
    config = tmp_path / "model.toml"
    config.write_text(
        '[model]\nid="example/model"\nrevision="abc123"\nurl="https://example.org/model"\ncache_dir="cache"\n',
        encoding="utf-8",
    )
    result = run_python(
        [str(ROOT / "scripts/download_model.py"), "--config", str(config), "--print-config"]
    )
    data = json.loads(result.stdout)
    assert data["repo_id"] == "example/model"
    assert data["revision"] == "abc123"
    assert Path(data["cache_dir"]) == tmp_path / "cache"


def test_encoder_and_font_defaults_are_portable() -> None:
    result = run_python(
        [
            "-c",
            "import json; from karaoke_studio.media_render import _encode; "
            "from karaoke_studio.derived_ass import FONT_PATH; from pathlib import Path; "
            'print(json.dumps({"encode": _encode(), "font_exists": Path(FONT_PATH).is_file()}))',
        ]
    )
    data = json.loads(result.stdout)
    assert data["font_exists"]
    assert "libx264" in data["encode"]


def test_setup_plan_contains_pinned_patch_and_model_script() -> None:
    result = run_python([str(ROOT / "scripts/setup.py"), "--dry-run", "--with-model"])
    assert "5d10abefb5b63c902c162cdda0640274418ae8d7" in result.stdout
    assert "yohane-runtime.patch" in result.stdout
    assert "download_model.py" in result.stdout


def test_download_script_dispatches_the_configured_snapshot(tmp_path: Path) -> None:
    config = tmp_path / "model.toml"
    config.write_text('[model]\nid="example/model"\nrevision="fixed-revision"\n', encoding="utf-8")
    recorder = tmp_path / "request.json"
    stub = tmp_path / "huggingface_hub.py"
    stub.write_text(
        "import json\nfrom pathlib import Path\ndef snapshot_download(**kwargs):\n    Path("
        + repr(str(recorder))
        + ").write_text(json.dumps(kwargs))\n    return 'snapshot-ready'\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(ROOT / "src")])
    env["KARAOKE_YOHANE_PYTHON"] = sys.executable
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/download_model.py"),
            "--config",
            str(config),
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    assert json.loads(recorder.read_text()) == {
        "repo_id": "example/model",
        "revision": "fixed-revision",
        "cache_dir": str(tmp_path / "cache"),
    }


def test_custom_config_keeps_runtime_under_application_home(tmp_path: Path) -> None:
    interpreter = (
        tmp_path / ".runtime/align" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    config = tmp_path / "overlays/custom.toml"
    config.parent.mkdir()
    config.write_text("[appearance]\nmain_size=72\n")
    env = os.environ.copy()
    env.pop("KARAOKE_YOHANE_PYTHON", None)
    env.update(
        {
            "KARAOKE_HOME": str(tmp_path),
            "KARAOKE_CONFIG": str(config),
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    result = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "from karaoke_studio.config import yohane_python; print(yohane_python())",
        ],
        env=env,
        text=True,
    )
    assert Path(result.strip()) == interpreter


def test_default_config_matches_source_template() -> None:
    import tomllib

    with (ROOT / "config.toml").open("rb") as handle:
        editable = tomllib.load(handle)
    with (ROOT / "src/karaoke_studio/config/defaults.toml").open("rb") as handle:
        bundled = tomllib.load(handle)
    assert editable == bundled


def test_production_lock_is_released_between_processes(tmp_path: Path) -> None:
    from karaoke_studio.service import _production_lock

    lock = tmp_path / "production.lock"
    code = (
        "from pathlib import Path\n"
        "from karaoke_studio.service import _production_lock\n"
        f"with _production_lock(Path({str(lock)!r})):\n    pass\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    with _production_lock(lock):
        busy = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        assert busy.returncode != 0
        assert "该项目已有制作任务运行" in busy.stderr
    released = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True)
    assert released.returncode == 0
