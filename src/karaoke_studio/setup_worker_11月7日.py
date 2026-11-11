"""Run one setup task independently of the graphical application."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .setup_11月7日 import atomic_json, now


def main():
    path = Path(sys.argv[1])
    value = json.loads(path.read_text(encoding="utf-8"))
    home = Path(value["home"])
    value.update(
        status="running",
        pid=os.getpid(),
        message="正在配置环境" if value["action"] == "environment" else "正在下载模型",
    )
    atomic_json(path, value)
    try:
        if value["action"] == "environment":
            command = [sys.executable, str(home / "scripts/setup.py"), "--alignment-only"]
            runtime = os.environ.get("KARAOKE_RUNTIME")
            if not runtime and os.environ.get("KARAOKE_YOHANE_PYTHON"):
                runtime = str(Path(os.environ["KARAOKE_YOHANE_PYTHON"]).parents[1].parent)
            if runtime:
                command += ["--runtime-dir", runtime]
        else:
            command = [sys.executable, str(home / "scripts/download_model.py")]
        if value.get("config"):
            command += ["--config", value["config"]]
        process = subprocess.Popen(
            command,
            cwd=home,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        tail = []
        assert process.stdout is not None
        for line in process.stdout:
            tail.append(line.rstrip())
            tail = tail[-8:]
        result = process.wait()
        if result:
            raise RuntimeError("\n".join(tail)[-1500:] or f"配置程序退出：{result}")
        value.update(status="completed", message="配置完成", finished_at=now())
    except Exception as exc:
        value.update(status="failed", message=str(exc), finished_at=now())
    atomic_json(path, value)


if __name__ == "__main__":
    main()
