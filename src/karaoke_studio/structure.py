from __future__ import annotations

from .models import LineState, LyricLine, MoraToken, RawAlignedLine, StructuralIssue
from .mora import normalize_romaji


def reconcile_to_yohane(line: LyricLine, raw: RawAlignedLine) -> StructuralIssue | None:
    """Map native timing subdivisions to source readings without inventing text.

    Yohane splits a romanized compound such as ``uo`` into ``u`` and ``o``.
    Match their contiguous character spans to the original mora, never to a
    nearby unrelated token. Returned labels are alignment data, not kana.
    """

    def failure(reason: str) -> StructuralIssue:
        line.state = LineState.STRUCTURAL_WARNING
        return StructuralIssue(
            code="yohane_unit_mapping",
            severity="error",
            line_id=line.id,
            message=reason,
            details={"kf": len(raw.k_values_cs), "cm": len(line.moras)},
        )

    existing = [normalize_romaji(mora.romaji).replace(" ", "") for mora in line.moras]
    returned = [normalize_romaji(label) for label in raw.labels]
    if len(returned) != len(raw.k_values_cs):
        return failure("native timing labels do not match the k sequence")
    if any(len(label.split()) != 1 for label in returned):
        return failure("native alignment contains an empty or compound label")
    if "".join(existing) != "".join(returned):
        return failure("native romanized transcript differs from the source readings")
    if existing == returned:
        line.state = LineState.ALIGNED
        return None

    spans: list[tuple[int, int, int]] = []
    cursor = 0
    for old_index, value in enumerate(existing):
        if value:
            spans.append((cursor, cursor + len(value), old_index))
            cursor += len(value)
    assigned: dict[int, list[int]] = {}
    old_for_raw: list[int] = []
    cursor = 0
    for raw_index, label in enumerate(returned):
        end = cursor + len(label)
        owner = next((old for start, stop, old in spans if start <= cursor and end <= stop), None)
        if owner is None:
            return failure("native unit crosses a source mora boundary")
        assigned.setdefault(owner, []).append(raw_index)
        old_for_raw.append(owner)
        cursor = end

    # Split only the source kana spelling over its native subdivisions. Empty
    # display pieces carry timing; no romanized label is rendered as text.
    kana_for_raw = [""] * len(returned)
    for old_index, raw_indices in assigned.items():
        kana = line.moras[old_index].kana
        total = len(existing[old_index])
        weight = previous = 0
        for raw_index in raw_indices:
            weight += len(returned[raw_index])
            boundary = round(len(kana) * weight / total)
            kana_for_raw[raw_index] = kana[previous:boundary]
            previous = boundary

    # A long mark or ruby punctuation has no romanized token. Keep it in its
    # own display group, attached to the preceding/next timed source unit.
    for old_index, value in enumerate(existing):
        if value:
            continue
        old = line.moras[old_index]
        previous = next(
            (
                index
                for index in range(old_index - 1, -1, -1)
                if index in assigned and line.moras[index].display_token_id == old.display_token_id
            ),
            None,
        )
        if previous is not None:
            kana_for_raw[assigned[previous][-1]] += old.kana
            continue
        following = next(
            (
                index
                for index in range(old_index + 1, len(existing))
                if index in assigned and line.moras[index].display_token_id == old.display_token_id
            ),
            None,
        )
        if following is None:
            return failure("source reading has no timed unit in its display group")
        target = assigned[following][0]
        # Multiple leading marks retain their source order.
        prefix = "".join(
            mora.kana
            for index, mora in enumerate(line.moras[:old_index])
            if not existing[index] and mora.display_token_id == old.display_token_id
        )
        if prefix and kana_for_raw[target].startswith(prefix):
            kana_for_raw[target] = prefix + old.kana + kana_for_raw[target][len(prefix) :]
        else:
            kana_for_raw[target] = old.kana + kana_for_raw[target]

    rebuilt = [
        MoraToken(
            id=f"{line.id}-native-m{index}",
            kana=kana_for_raw[index],
            romaji=label,
            group_id=line.moras[old_for_raw[index]].group_id,
            display_token_id=line.moras[old_for_raw[index]].display_token_id,
        )
        for index, label in enumerate(returned)
    ]
    for token in line.display_tokens:
        before = "".join(mora.kana for mora in line.moras if mora.display_token_id == token.id)
        after = "".join(mora.kana for mora in rebuilt if mora.display_token_id == token.id)
        if before != after:
            return failure("native mapping would change the source reading")
    groups = [
        group.model_copy(
            update={"mora_ids": [mora.id for mora in rebuilt if mora.group_id == group.id]}
        )
        for group in line.ruby_groups
    ]
    line.moras = rebuilt
    line.ruby_groups = groups
    line.yohane_input = " ".join(returned)
    line.state = LineState.ALIGNED
    line.warning_codes = [
        code
        for code in line.warning_codes
        if code not in {"yohane_kana_anchor", "yohane_display_fallback"}
    ]
    return None
