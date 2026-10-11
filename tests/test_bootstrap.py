from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("system", ["windows", "macos", "linux"])
def test_install_plan_covers_platform_and_runtime(system: str, tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/bootstrap.py"),
            "--plan",
            "--platform",
            system,
            "--data-dir",
            str(tmp_path / "data"),
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    assert f'"platform": "{system}"' in result.stdout
    assert "--runtime-dir" in result.stdout
    assert "--with-model" in result.stdout
    assert not (tmp_path / "data").exists()


def test_main_only_plan_keeps_model_optional(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/bootstrap.py"),
            "--plan",
            "--platform",
            "windows",
            "--main-only",
            "--data-dir",
            str(tmp_path / "data"),
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    assert "--main-only" in result.stdout
    assert "--with-model" not in result.stdout
    assert '"git"' not in result.stdout.split('"tools_to_install"')[1]


def test_portable_tool_extracts_and_reuses_archive(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "scripts/bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    with zipfile.ZipFile(downloads / "ffmpeg.zip", "w") as archive:
        archive.writestr("build/bin/ffmpeg.exe", b"portable-tool")
        archive.writestr("build/bin/library.dll", b"library")
    output = module.portable_tool(
        "https://example.invalid/archive", tmp_path / "ffmpeg", "ffmpeg.exe", downloads
    )
    assert output.read_bytes() == b"portable-tool"
    assert (output.parent / "library.dll").is_file()
    assert (
        module.portable_tool(
            "https://example.invalid/archive", tmp_path / "ffmpeg", "ffmpeg.exe", downloads
        )
        == output
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell entry")
def test_shell_entry_preserves_arguments_and_data_directory(tmp_path: Path) -> None:
    binary = tmp_path / "bin"
    binary.mkdir()
    uv = binary / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nprintf "%s\\n" "$UV_CACHE_DIR"\n')
    uv.chmod(0o755)
    env = os.environ.copy()
    for key in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_TOOL_DIR", "UV_TOOL_BIN_DIR"):
        env.pop(key, None)
    env["PATH"] = str(binary) + os.pathsep + env["PATH"]
    data = tmp_path / "data with spaces"
    result = subprocess.run(
        ["sh", str(ROOT / "install.sh"), "--main-only", "--data-dir", str(data)],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "--main-only" in result.stdout
    assert str(data / "cache/uv") in result.stdout


def test_readme_languages_have_matching_entry_points() -> None:
    assert (ROOT / "README.md").read_bytes() == (ROOT / "README.zh_CN.md").read_bytes()
    for language in ("zh_CN", "en", "ja"):
        text = (ROOT / f"README.{language}.md").read_text(encoding="utf-8")
        for entry in (
            "install.ps1",
            "sh install.sh",
            "macOS",
            "Linux",
            "Windows",
            "installer.toml",
        ):
            assert entry in text


def test_macos_uses_libass_build_outside_path(monkeypatch, tmp_path: Path) -> None:
    import karaoke_studio.config as config

    monkeypatch.setattr(config, "tool_path", lambda name: name)
    spec = importlib.util.spec_from_file_location("bootstrap_macos", ROOT / "scripts/bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "platform_name", lambda: "macos")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/tools/" + name)
    calls = []
    saved = {}
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kw: calls.append(command))

    def output(command, **kwargs):
        if "--prefix" in command:
            return str(tmp_path / "ffmpeg-full") + "\n"
        return "no subtitles" if command[0] == "/tools/ffmpeg" else " ... ass subtitle renderer"

    monkeypatch.setattr(module.subprocess, "check_output", output)
    monkeypatch.setattr(module, "save_environment", saved.update)
    monkeypatch.setattr(
        module.sys, "argv", ["bootstrap", "--main-only", "--data-dir", str(tmp_path / "data")]
    )
    monkeypatch.delenv("KARAOKE_FFMPEG", raising=False)
    monkeypatch.delenv("KARAOKE_FFPROBE", raising=False)
    module.main()
    assert any("ffmpeg-full" in command for command in calls)
    assert saved["KARAOKE_FFMPEG"] == str(tmp_path / "ffmpeg-full/bin/ffmpeg")
    assert saved["KARAOKE_FFPROBE"] == str(tmp_path / "ffmpeg-full/bin/ffprobe")
