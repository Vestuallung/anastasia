from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .models import (
    KaraokeProject,
    LineState,
    MoraToken,
    OverrideFile,
    OverrideHistory,
    ReadingSource,
)
from .mora import mora_romaji, normalize_romaji, split_mora


def load_overrides(path: Path) -> OverrideFile:
    return OverrideFile.model_validate(json.loads(path.read_text(encoding="utf-8")))


def apply_overrides(project: KaraokeProject, override_file: OverrideFile) -> int:
    if override_file.project_id != project.project_id:
        raise ValueError("override file belongs to a different project")
    changed = 0
    for override in override_file.overrides:
        line = next((item for item in project.lines if item.id == override.line_id), None)
        if line is None:
            raise ValueError(f"unknown line id: {override.line_id}")
        if line.original != override.expected_text:
            raise ValueError(f"line text changed since override was authored: {line.id}")
        groups = [
            group
            for group in line.ruby_groups
            if group.span.start == override.span.start and group.span.end == override.span.end
        ]
        if len(groups) != 1:
            raise ValueError("override span must exactly match one ruby group")
        group = groups[0]
        token = next(token for token in line.display_tokens if token.id in group.display_token_ids)
        before = group.model_dump(mode="json")
        if override.display_only:
            removed = set(group.mora_ids)
            line.moras = [mora for mora in line.moras if mora.id not in removed]
            line.ruby_groups.remove(group)
            token.alignable = False
        else:
            if not override.reading:
                raise ValueError("reading is required unless display_only is true")
            kana_moras = split_mora(override.reading)
            supplied_romaji = (
                normalize_romaji(override.romaji).split()
                if override.romaji
                else [normalize_romaji(mora_romaji(mora)) for mora in kana_moras]
            )
            if len(supplied_romaji) != len(kana_moras):
                raise ValueError("explicit romaji must contain one space-delimited unit per mora")
            old_ids = set(group.mora_ids)
            kept = [mora for mora in line.moras if mora.id not in old_ids]
            replacements: list[MoraToken] = []
            for index, (kana, romaji) in enumerate(zip(kana_moras, supplied_romaji, strict=True)):
                replacements.append(
                    MoraToken(
                        id=f"{group.id}-override-{index}",
                        kana=kana,
                        romaji=romaji,
                        group_id=group.id,
                        display_token_id=token.id,
                    )
                )
            insertion = next(
                (index for index, mora in enumerate(line.moras) if mora.id in old_ids), len(kept)
            )
            line.moras = kept[:insertion] + replacements + kept[insertion:]
            group.reading = override.reading
            group.mora_ids = [mora.id for mora in replacements]
            group.source = (
                ReadingSource.AGENT if override.author.lower() == "agent" else ReadingSource.USER
            )
        line.yohane_input = " ".join(mora.romaji for mora in line.moras if mora.romaji)
        line.state = LineState.STALE
        project.alignment_stale = True
        project.override_history.append(
            OverrideHistory(
                id=str(uuid4()),
                line_id=line.id,
                span=override.span,
                before=before,
                after={
                    "display_only": override.display_only,
                    "reading": override.reading,
                    "romaji": override.romaji,
                },
                author=override.author,
                reason=override.reason,
            )
        )
        changed += 1
    return changed
