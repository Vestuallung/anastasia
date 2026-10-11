from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import CORE_VERSION, KaraokeProject, RawAlignment
from .mora import normalize_romaji


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_romaji(project: KaraokeProject) -> str:
    return "\n".join(normalize_romaji(line.yohane_input) for line in project.lines)


def alignment_cache_key(project: KaraokeProject) -> str:
    payload = {
        "audio_sha256": project.audio.prepared_sha256,
        "romaji": normalized_romaji(project),
        # The normalized Yohane text alone is insufficient: punctuation and
        # visible spacing can change the source line IDs while leaving the
        # alignment text unchanged. Keep the source lyric identity in the
        # cache key so a lyric edit can never reuse stale raw alignment.
        "lyrics": [
            {
                "id": line.id,
                "original": line.original,
                "yohane_input": line.yohane_input,
            }
            for line in project.lines
        ],
        "model_id": project.model.model_id,
        "model_revision": project.model.revision,
        "sample_rate": project.audio.sample_rate,
        "channels": project.audio.channels,
        "core_version": CORE_VERSION,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def cache_path(project_dir: Path, key: str) -> Path:
    return project_dir / ".karaoke-work" / "alignments" / f"{key}.json"


def load_cached_alignment(project_dir: Path, key: str) -> RawAlignment | None:
    target = cache_path(project_dir, key)
    if not target.exists():
        return None
    return RawAlignment.model_validate_json(target.read_text(encoding="utf-8"))


def save_cached_alignment(project_dir: Path, alignment: RawAlignment) -> Path:
    target = cache_path(project_dir, alignment.cache_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(alignment.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target
