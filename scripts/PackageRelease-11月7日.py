"""Stage the portable source and prebuilt UI, then create the release ZIP."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    ".gitignore",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "config.toml",
    "installer.toml",
    "install.sh",
    "install.ps1",
    "karaoke-local",
    "karaoke-local.ps1",
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "README.zh_CN.md",
    "README.en.md",
    "README.ja.md",
    "Start-Studio-11月7日.command",
    "Start-Studio-11月7日.cmd",
    "Start-Studio-11月7日.sh",
}
TREES = {".github", "docs", "examples", "patches", "schemas", "scripts", "src", "tests", "web"}
SKIP = {
    ".DS_Store",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    "test-results",
    "playwright-report",
    "JASSUB-LICENSE.txt",
}
MEDIA = {".mp4", ".mkv", ".m4a", ".wav", ".mp3", ".pt", ".safetensors", ".onnx"}


def included(path: Path) -> bool:
    return (
        not any(part in SKIP for part in path.parts)
        and path.suffix not in (MEDIA | {".pyc", ".tsbuildinfo"})
        and path.name
        not in {
            "vite.config.js",
            "vite.config.d.ts",
            "playwright.config.js",
            "playwright.config.d.ts",
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--archive-only", action="store_true", help="Write the ZIP without staging a directory."
    )
    args = parser.parse_args()
    destination = args.directory.resolve()
    archive = destination.with_suffix(".zip")
    if (destination.exists() and not args.archive_only) or archive.exists():
        parser.error("choose a new output directory")
    if not (ROOT / "src/karaoke_studio/static/index.html").is_file():
        parser.error("build the web interface first")
    app = "KaraokeStudio-11月7日.app"
    paths = [ROOT / name for name in sorted(FILES)]
    for tree in sorted(TREES | {app}):
        paths.extend(path for path in (ROOT / tree).rglob("*") if path.is_file())
    paths.extend(
        ROOT / "desktop" / name
        for name in (
            "BuildDesktop-11月7日.sh",
            "DesktopHost-11月7日.swift",
        )
    )
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as output:
        for source in paths:
            relative = source.relative_to(ROOT)
            if not included(relative):
                continue
            if not args.archive_only:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            output.write(source, destination.name + "/" + relative.as_posix())
    if not args.archive_only:
        print(destination)
    print(archive)


if __name__ == "__main__":
    main()
