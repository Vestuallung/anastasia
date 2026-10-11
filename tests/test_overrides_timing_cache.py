from __future__ import annotations

import pytest
from conftest import StubAnalyzer

from karaoke_studio.cache import alignment_cache_key
from karaoke_studio.lyrics import build_line
from karaoke_studio.models import (
    KaraokeProject,
    OverrideFile,
    ReadingOverride,
    ReadingSource,
)
from karaoke_studio.overrides import apply_overrides
from karaoke_studio.timing import (
    create_timing_patch,
    effective_boundaries,
    move_boundary,
    move_line,
    restore_raw_timing,
)


def _override(project: KaraokeProject, *, author: str, reading: str, romaji: str) -> OverrideFile:
    line = project.lines[0]
    group = line.ruby_groups[0]
    return OverrideFile(
        project_id=project.project_id,
        overrides=[
            ReadingOverride(
                line_id=line.id,
                expected_text=line.original,
                span=group.span,
                reading=reading,
                romaji=romaji,
                author=author,
                reason="explicit project reading",
            )
        ],
    )


@pytest.mark.parametrize(
    ("original", "automatic_source"),
    [("他人《ひと》", ReadingSource.RUBY), ("他人", ReadingSource.MECAB)],
)
def test_override_has_priority_over_ruby_or_mecab(
    original: str, automatic_source: ReadingSource
) -> None:
    analyzer = StubAnalyzer({"他人": [("他人", "タニン")]})
    line = build_line(original, 0, analyzer=analyzer)
    project = KaraokeProject(project_id="p", title="Priority", lines=[line])
    assert line.ruby_groups[0].source == automatic_source

    changed = apply_overrides(
        project, _override(project, author="agent", reading="ひと", romaji="hi to")
    )

    assert changed == 1
    assert line.ruby_groups[0].source == ReadingSource.AGENT
    assert line.yohane_input == "hi to"
    assert project.alignment_stale is True
    assert len(project.override_history) == 1
    assert project.override_history[0].before["source"] == automatic_source.value


def test_user_override_is_recorded_as_user_source() -> None:
    line = build_line("他人《ひと》", 0, analyzer=StubAnalyzer({}))
    project = KaraokeProject(project_id="p", title="Priority", lines=[line])

    apply_overrides(project, _override(project, author="user", reading="たにん", romaji="ta ni n"))

    assert line.ruby_groups[0].source == ReadingSource.USER
    assert project.override_history[-1].author == "user"


def test_timing_patch_is_overlay_and_restore_keeps_raw_immutable(
    aligned_project: KaraokeProject,
) -> None:
    raw = aligned_project.raw_alignment
    assert raw is not None
    original_k = list(raw.lines[0].k_values_cs)
    line_id = aligned_project.lines[0].id

    patch = create_timing_patch(
        aligned_project,
        line_id,
        [1100, 1250, 1400],
        kind="line_shift",
    )

    assert patch.before_ms == [1000, 1100, 1300]
    assert effective_boundaries(aligned_project, line_id) == [1100, 1250, 1400]
    assert raw.lines[0].k_values_cs == original_k

    restored = restore_raw_timing(aligned_project, line_id)

    assert restored.kind == "restore"
    assert effective_boundaries(aligned_project, line_id) == [1000, 1100, 1300]
    assert raw.lines[0].k_values_cs == original_k


def test_timing_edit_helpers_reject_negative_or_reversed_time() -> None:
    assert move_boundary([100, 200, 300], 1, 250) == [100, 250, 300]
    with pytest.raises(ValueError, match="before zero"):
        move_line([100, 200], -101)
    with pytest.raises(ValueError, match="negative duration"):
        move_boundary([100, 200, 300], 1, 301)


def test_cache_invalidation_tracks_reading_not_display_or_timing(
    aligned_project: KaraokeProject,
) -> None:
    original = alignment_cache_key(aligned_project)
    line = aligned_project.lines[0]
    create_timing_patch(
        aligned_project,
        line.id,
        [1050, 1150, 1350],
        kind="line_shift",
    )
    assert alignment_cache_key(aligned_project) == original

    line.display_tokens[0].text = "愛"
    assert alignment_cache_key(aligned_project) == original

    line.moras[0].romaji = "e"
    line.yohane_input = " ".join(mora.romaji for mora in line.moras)
    assert alignment_cache_key(aligned_project) != original
