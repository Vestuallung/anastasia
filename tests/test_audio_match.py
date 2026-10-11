from __future__ import annotations

import numpy as np
import pytest

import karaoke_studio.audio_match as audio_match
from karaoke_studio.audio_match import AudioOpeningMatchError, match_pcm_opening


def test_matches_external_opening_once_inside_reference() -> None:
    rng = np.random.default_rng(7)
    sample_rate = 1000
    opening = rng.normal(0, 0.2, 6000)
    reference = rng.normal(0, 0.01, 18000)
    reference[4250:10250] += opening

    match = match_pcm_opening(
        reference,
        opening,
        sample_rate=sample_rate,
        template_seconds=4,
    )

    assert match.offset_seconds == pytest.approx(4.25, abs=0.001)
    assert match.correlation > 0.99


def test_rejects_non_unique_opening_match() -> None:
    rng = np.random.default_rng(8)
    sample_rate = 1000
    opening = rng.normal(0, 0.2, 5000)
    reference = rng.normal(0, 0.01, 18000)
    reference[2000:7000] += opening
    reference[11000:16000] += opening

    with pytest.raises(AudioOpeningMatchError, match="不唯一"):
        match_pcm_opening(
            reference,
            opening,
            sample_rate=sample_rate,
            template_seconds=4,
        )


def test_prefer_early_limits_reference_search(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(9)
    sample_rate = 1000
    opening = rng.normal(0, 0.2, 5000)
    reference = rng.normal(0, 0.01, 18000)
    reference[2000:7000] += opening
    reference[11000:16000] += opening

    def fake_decode(path, *, sample_rate: int, duration=None):
        return reference if str(path) == "reference" else opening

    monkeypatch.setattr(audio_match, "decode_mono", fake_decode)
    match = audio_match.match_audio_opening(
        "reference",
        "external",
        sample_rate=sample_rate,
        template_seconds=4,
        prefer_early_seconds=8,
    )

    assert match.offset_seconds == pytest.approx(2.0, abs=0.001)
