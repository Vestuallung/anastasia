from __future__ import annotations

from collections.abc import Callable

from .models import SCHEMA_VERSION

Migration = Callable[[dict[str, object]], dict[str, object]]


def _v0_to_v1(payload: dict[str, object]) -> dict[str, object]:
    migrated = dict(payload)
    migrated["schema_version"] = 1
    migrated.setdefault("core_version", "0.1.0")
    migrated.setdefault("alignment_stale", bool(migrated.get("raw_alignment") is None))
    return migrated


MIGRATIONS: dict[int, Migration] = {0: _v0_to_v1}


def migrate_payload(payload: dict[str, object]) -> tuple[dict[str, object], list[int]]:
    version = int(payload.get("schema_version", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"project schema {version} is newer than supported schema {SCHEMA_VERSION}"
        )
    migrated = dict(payload)
    applied: list[int] = []
    while version < SCHEMA_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"no migration path from schema {version}")
        migrated = migration(migrated)
        version += 1
        applied.append(version)
    return migrated, applied
