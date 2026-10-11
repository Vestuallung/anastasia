#!/usr/bin/env python3
"""Download the configured model into the Hugging Face cache."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("KARAOKE_HOME", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    if args.config:
        os.environ["KARAOKE_CONFIG"] = str(args.config.resolve())
    from karaoke_studio.config import configured_path, section, yohane_python

    model = section("model")
    cache = args.cache_dir or (configured_path(model["cache_dir"]) if model["cache_dir"] else None)
    request = {
        "repo_id": model["id"],
        "revision": args.revision or model["revision"],
        "cache_dir": str(cache) if cache else None,
    }
    print(
        json.dumps({**request, "url": model["url"], "license": model["license"]}, indent=2),
        flush=True,
    )
    if args.print_config:
        return
    worker = """import json,sys
from huggingface_hub import snapshot_download
request=json.loads(sys.argv[1])
print(snapshot_download(**request))
"""
    env = os.environ.copy()
    for key in (
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "PYTORCHF_HUB_OFFLINE",
        "PYTORHF_HUB_OFFLINE",
    ):
        env.pop(key, None)
    subprocess.run([str(yohane_python()), "-c", worker, json.dumps(request)], env=env, check=True)


if __name__ == "__main__":
    main()
