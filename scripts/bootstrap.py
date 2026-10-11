#!/usr/bin/env python3
"""Install system tools, isolated runtimes and the configured alignment model."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def platform_name() -> str:
    return "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux"


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(3):
        try:
            print(f"Downloading {destination.name}", flush=True)
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
                shutil.copyfileobj(response, out)
            temporary.replace(destination)
            return
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2)


def portable_tool(url: str, folder: Path, executable: str, downloads: Path) -> Path:
    existing = list(folder.rglob(executable)) if folder.exists() else []
    if existing:
        return existing[0]
    archive = downloads / (folder.name + ".zip")
    if not archive.is_file() or not zipfile.is_zipfile(archive):
        download(url, archive)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(folder)
    return next(folder.rglob(executable))


def linux_commands(packages: list[str]) -> list[list[str]]:
    if shutil.which("apt-get"):
        commands = [["apt-get", "update"], ["apt-get", "install", "-y", *packages]]
    elif shutil.which("dnf"):
        commands = [["dnf", "install", "-y", *packages]]
    elif shutil.which("pacman"):
        commands = [["pacman", "-S", "--needed", "--noconfirm", *packages]]
    elif shutil.which("zypper"):
        commands = [["zypper", "--non-interactive", "install", *packages]]
    else:
        raise RuntimeError("Install Git and FFmpeg with your distribution's package manager.")
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    return [prefix + command for command in commands]


def save_environment(values: dict[str, str]) -> None:
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "environment.sh").write_text(
        "\n".join(f"export {key}={shlex.quote(value)}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    (runtime / "environment.ps1").write_text(
        "\n".join(
            f"$env:{key} = '{value.replace(chr(39), chr(39) * 2)}'" for key, value in values.items()
        )
        + "\n",
        encoding="utf-8-sig",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-only", action="store_true")
    parser.add_argument("--skip-model", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".runtime")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--platform", choices=["windows", "macos", "linux"])
    args = parser.parse_args()
    system = args.platform or platform_name()
    data = args.data_dir.expanduser().resolve()
    settings = tomllib.loads((ROOT / "installer.toml").read_text(encoding="utf-8"))
    os.environ["KARAOKE_HOME"] = str(ROOT)
    if args.config:
        os.environ["KARAOKE_CONFIG"] = str(args.config.resolve())
    from karaoke_studio.config import section, tool_path

    uv = os.environ.get("KARAOKE_UV") or shutil.which("uv") or "uv"
    values = {
        "KARAOKE_UV": uv,
        "UV_PROJECT_ENVIRONMENT": os.environ.get("UV_PROJECT_ENVIRONMENT", str(data / "main")),
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(data / "cache/uv")),
        "UV_PYTHON_INSTALL_DIR": os.environ.get("UV_PYTHON_INSTALL_DIR", str(data / "python")),
        "UV_TOOL_DIR": os.environ.get("UV_TOOL_DIR", str(data / "tools/envs")),
        "UV_TOOL_BIN_DIR": os.environ.get("UV_TOOL_BIN_DIR", str(data / "tools/bin")),
        "HF_HOME": str(data / "cache/huggingface"),
        "TORCH_HOME": str(data / "cache/torch"),
        "XDG_CACHE_HOME": str(data / "cache"),
        "TEMP": str(data / "temp"),
        "TMP": str(data / "temp"),
        "TMPDIR": str(data / "temp"),
        "PYTHONUTF8": "1",
    }
    if (
        not args.main_only
        or (
            data / "align" / ("Scripts/python.exe" if system == "windows" else "bin/python")
        ).is_file()
    ):
        values["KARAOKE_YOHANE_PYTHON"] = str(
            data / "align" / ("Scripts/python.exe" if system == "windows" else "bin/python")
        )
    if args.config:
        values["KARAOKE_CONFIG"] = str(args.config.resolve())
    os.environ.update(values)
    if system in {"windows", "linux"} and section("runtime")["device"] == "cpu":
        os.environ["KARAOKE_TORCH_INDEX_URL"] = settings["alignment"]["cpu_index_url"]

    def run(command: list[str]) -> None:
        print(shlex.join(map(str, command)), flush=True)
        if not args.plan:
            subprocess.run(command, cwd=ROOT, check=True)

    needed = ["ffmpeg", "ffprobe"] + ([] if args.main_only else ["git"])
    found = {}
    for name in needed:
        candidate = tool_path(name) if name in {"ffmpeg", "ffprobe"} else name
        found[name] = shutil.which(candidate) if system == platform_name() else None
    missing = [name for name in needed if not found[name]]
    if not args.plan and found["ffmpeg"]:
        filters = subprocess.check_output(
            [found["ffmpeg"], "-hide_banner", "-filters"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if " ass " not in filters and "ffmpeg" not in missing:
            missing.append("ffmpeg")
    if args.plan:
        print(
            json.dumps(
                {
                    "platform": system,
                    "data_directory": str(data),
                    "downloads": settings.get(system, {}),
                    "tools_to_install": missing,
                },
                indent=2,
            )
        )
    else:
        for folder in (data, data / "temp", data / "cache", data / "downloads"):
            folder.mkdir(parents=True, exist_ok=True)
    if missing and system == "windows":
        for name in ("git", "ffmpeg"):
            if name not in missing and not (name == "ffmpeg" and "ffprobe" in missing):
                continue
            if not args.plan:
                executable = portable_tool(
                    settings["windows"][name + "_archive"],
                    data / "tools" / name,
                    name + ".exe",
                    data / "downloads",
                )
                os.environ["PATH"] = str(executable.parent) + os.pathsep + os.environ["PATH"]
        if not args.plan:
            found = {name: found[name] or shutil.which(name) for name in needed}
    elif missing and system == "macos":
        brew = shutil.which("brew")
        if not brew:
            installer = data / "temp/homebrew-install.sh"
            if not args.plan:
                download(settings["macos"]["homebrew_installer"], installer)
            run(["/bin/bash", str(installer)])
            brew = next(
                (path for path in settings["macos"]["brew_candidates"] if Path(path).is_file()),
                "brew",
            )
        run([brew, "install", *settings["macos"]["packages"]])
        if not args.plan:
            os.environ["PATH"] = str(Path(brew).parent) + os.pathsep + os.environ["PATH"]
            found = {name: found[name] or shutil.which(name) for name in needed}
            prefix = subprocess.check_output(
                [brew, "--prefix", settings["macos"]["ffmpeg_formula"]], text=True
            ).strip()
            for name in ("ffmpeg", "ffprobe"):
                found[name] = str(Path(prefix) / "bin" / name)
    elif missing and system == "linux":
        commands = (
            [
                ["sudo", "apt-get", "update"],
                ["sudo", "apt-get", "install", "-y", *settings["linux"]["packages"]],
            ]
            if args.plan
            else linux_commands(settings["linux"]["packages"])
        )
        for command in commands:
            run(command)
        if not args.plan:
            found = {name: found[name] or shutil.which(name) for name in needed}
    if not args.plan:
        for name in needed:
            if not found[name]:
                raise RuntimeError(
                    f"Tool installation result: {name}. Configure its executable path."
                )
        values["KARAOKE_FFMPEG"] = found["ffmpeg"]
        values["KARAOKE_FFPROBE"] = found["ffprobe"]
        os.environ.update(values)
        filters = subprocess.check_output(
            [found["ffmpeg"], "-hide_banner", "-filters"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if " ass " not in filters:
            raise RuntimeError("Select an FFmpeg build with the ASS/libass filter.")
    command = [sys.executable, str(ROOT / "scripts/setup.py"), "--runtime-dir", str(data)]
    if args.main_only:
        command.append("--main-only")
    elif not args.skip_model:
        command.append("--with-model")
    if args.config:
        command += ["--config", str(args.config.resolve())]
    run(command)
    if not args.plan:
        save_environment(values)
        print(
            "Ready. Run karaoke-local.ps1 --help"
            if system == "windows"
            else "Ready. Run ./karaoke-local --help"
        )


if __name__ == "__main__":
    main()
