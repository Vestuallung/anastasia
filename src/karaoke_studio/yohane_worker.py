"""Stdlib-only worker executed by the dedicated Yohane interpreter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .config import section

os.environ.setdefault("YOHANE_DEVICE", "cpu")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

K_TAG = re.compile(r"\{\\k(?P<k>\d+)[^}]*}(?P<label>[^{}]*)")

YOHANE_REVISION = section("yohane")["revision"]


def checksum_tree(root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        checksums[str(path.relative_to(root))] = digest.hexdigest()
    return checksums


def main() -> None:
    request_path = Path(sys.argv[1])
    response_path = Path(sys.argv[2])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request["allow_download"]:
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("PYTORCHF_HUB_OFFLINE", None)
    else:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["PYTORCHF_HUB_OFFLINE"] = "1"
        os.environ["PYTORHF_HUB_OFFLINE"] = "1"
    from huggingface_hub import snapshot_download
    from yohane.pipeline import Yohane

    snapshot = Path(
        snapshot_download(
            repo_id=request["model_id"],
            revision=request["model_revision"],
            cache_dir=request.get("cache_dir"),
            local_files_only=not request["allow_download"],
        )
    )
    aligner = Yohane(separator=None, forced_aligner=str(snapshot))
    aligner.load_song(Path(request["audio_path"]))
    aligner.load_lyrics(request["lyrics"])
    aligner.force_align()
    subtitles = aligner.make_subs()
    lines = []
    for event in subtitles.events:
        if getattr(event, "type", None) != "Dialogue":
            continue
        pairs = [
            (int(match.group("k")), match.group("label")) for match in K_TAG.finditer(event.text)
        ]
        lines.append(
            {
                "start_ms": int(event.start),
                "end_ms": int(event.end),
                "k_values_cs": [pair[0] for pair in pairs],
                "labels": [pair[1] for pair in pairs],
            }
        )
    response_path.write_text(
        json.dumps(
            {
                "adapter_version": (
                    f"{version('yohane')}@git:{YOHANE_REVISION}"
                    if _package_exists("yohane")
                    else f"unknown@git:{YOHANE_REVISION}"
                ),
                "snapshot": str(snapshot),
                "checksums": checksum_tree(snapshot),
                "lines": lines,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _package_exists(name: str) -> bool:
    try:
        version(name)
    except PackageNotFoundError:
        return False
    return True


if __name__ == "__main__":
    main()
