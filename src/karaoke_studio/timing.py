from __future__ import annotations

from uuid import uuid4

from .models import KaraokeProject, RawAlignedLine, TimingPatch


def raw_boundaries(line: RawAlignedLine) -> list[int]:
    boundaries = [line.start_ms]
    for duration in line.k_values_cs:
        boundaries.append(boundaries[-1] + duration * 10)
    return boundaries


def effective_boundaries(project: KaraokeProject, line_id: str) -> list[int]:
    if not project.raw_alignment:
        return []
    raw = next((line for line in project.raw_alignment.lines if line.line_id == line_id), None)
    if raw is None:
        return []
    boundaries = raw_boundaries(raw)
    for patch in project.timing_patches:
        if patch.line_id == line_id:
            boundaries = list(patch.after_ms)
    return boundaries


def create_timing_patch(
    project: KaraokeProject,
    line_id: str,
    boundaries: list[int],
    *,
    kind: str,
    boundary_index: int | None = None,
    author: str = "user",
    reason: str = "manual timeline edit",
) -> TimingPatch:
    before = effective_boundaries(project, line_id)
    if not before:
        raise ValueError("line has no raw alignment")
    if len(boundaries) != len(before):
        raise ValueError("timing edits cannot add or remove mora boundaries")
    patch = TimingPatch(
        id=str(uuid4()),
        line_id=line_id,
        kind=kind,
        boundary_index=boundary_index,
        before_ms=before,
        after_ms=boundaries,
        author=author,
        reason=reason,
    )
    project.timing_patches.append(patch)
    return patch


def restore_raw_timing(
    project: KaraokeProject, line_id: str, *, author: str = "user"
) -> TimingPatch:
    if not project.raw_alignment:
        raise ValueError("project has no raw alignment")
    raw = next((line for line in project.raw_alignment.lines if line.line_id == line_id), None)
    if raw is None:
        raise ValueError("line has no raw alignment")
    return create_timing_patch(
        project,
        line_id,
        raw_boundaries(raw),
        kind="restore",
        author=author,
        reason="restore immutable raw alignment",
    )


def move_line(boundaries: list[int], delta_ms: int) -> list[int]:
    moved = [value + delta_ms for value in boundaries]
    if moved and moved[0] < 0:
        raise ValueError("line cannot be moved before zero")
    return moved


def move_boundary(boundaries: list[int], index: int, target_ms: int) -> list[int]:
    if index <= 0 or index >= len(boundaries) - 1:
        raise ValueError("internal boundary index is out of range")
    if not boundaries[index - 1] <= target_ms <= boundaries[index + 1]:
        raise ValueError("boundary would make a negative duration")
    changed = list(boundaries)
    changed[index] = target_ms
    return changed


def quantized_k_values(boundaries: list[int]) -> list[int]:
    """Quantize to ASS centiseconds while preserving the quantized line end."""
    if len(boundaries) < 2:
        return []
    quantized = [round(value / 10) for value in boundaries]
    durations = [quantized[index + 1] - quantized[index] for index in range(len(quantized) - 1)]
    if any(value < 0 for value in durations):
        raise ValueError("timings are not ordered")
    return durations
