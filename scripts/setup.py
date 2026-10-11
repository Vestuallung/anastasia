#!/usr/bin/env python3
"""Create the application and alignment environments from configuration."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("KARAOKE_HOME", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--main-only", action="store_true")
    parser.add_argument("--with-model", action="store_true")
    parser.add_argument("--build-web", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.config:
        os.environ["KARAOKE_CONFIG"] = str(args.config.resolve())
    from karaoke_studio.config import section

    uv = shutil.which("uv") or "uv"

    def run(command: list[str]) -> None:
        print(" ".join(map(str, command)), flush=True)
        if not args.dry_run:
            if os.name == "nt" and command[0] == "npm":
                command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", *command]
            subprocess.run(command, cwd=ROOT, check=True)

    run([uv, "sync", "--python", "3.12", "--all-extras"])
    if not args.main_only:
        runtime = ROOT / ".runtime"
        checkout = runtime / "yohane"
        settings = section("yohane")
        patch = ROOT / "patches/yohane-runtime.patch"
        if not args.dry_run:
            runtime.mkdir(exist_ok=True)
        if not (checkout / ".git").exists():
            run(["git", "init", str(checkout)])
            run(["git", "-C", str(checkout), "remote", "add", "origin", settings["repository"]])
            run(
                [
                    "git",
                    "-C",
                    str(checkout),
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    settings["revision"],
                ]
            )
            run(["git", "-C", str(checkout), "checkout", "--detach", "FETCH_HEAD"])
        if args.dry_run:
            run(["git", "-C", str(checkout), "apply", str(patch)])
        else:
            current = subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
            ).strip()
            if current != settings["revision"]:
                run(
                    [
                        "git",
                        "-C",
                        str(checkout),
                        "fetch",
                        "--depth",
                        "1",
                        "origin",
                        settings["revision"],
                    ]
                )
                run(["git", "-C", str(checkout), "checkout", settings["revision"]])
            applied = subprocess.run(
                ["git", "-C", str(checkout), "apply", "--reverse", "--check", str(patch)],
                capture_output=True,
            )
            if applied.returncode:
                run(["git", "-C", str(checkout), "apply", str(patch)])
        align = runtime / "align"
        python = align / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([uv, "venv", "--allow-existing", "--python", "3.12", str(align)])
        run([uv, "pip", "install", "--python", str(python), *settings["packages"]])
        run([uv, "pip", "install", "--python", str(python), "--no-deps", "-e", str(checkout)])
    if args.build_web:
        run(["npm", "--prefix", "web", "ci"])
        run(["npm", "--prefix", "web", "run", "build"])
    if args.with_model:
        command = [sys.executable, str(ROOT / "scripts/download_model.py")]
        if args.config:
            command += ["--config", str(args.config)]
        run(command)
    print("Environment configuration complete" if not args.dry_run else "Setup plan complete")


if __name__ == "__main__":
    main()
