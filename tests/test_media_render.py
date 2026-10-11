from __future__ import annotations

from pathlib import Path

import pytest

import karaoke_studio.media_render as media_render
from karaoke_studio.media_render import MediaRenderError, resolve_output_canvas


@pytest.mark.parametrize(
    ("width", "height", "sar", "expected"),
    [
        (1080, 1080, "1:1", (1080, 1080)),
        (1440, 1080, "1:1", (1440, 1080)),
        (1080, 1920, "1:1", (1080, 1920)),
        (720, 576, "16:15", (768, 576)),
    ],
)
def test_preserve_canvas_uses_display_aspect_ratio(
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    height: int,
    sar: str,
    expected: tuple[int, int],
) -> None:
    monkeypatch.setattr(
        media_render,
        "_probe",
        lambda _: {
            "streams": [
                {
                    "codec_type": "video",
                    "width": width,
                    "height": height,
                    "sample_aspect_ratio": sar,
                }
            ]
        },
    )

    canvas = resolve_output_canvas(Path("video.mp4"))

    assert (canvas.width, canvas.height) == expected


def test_pad_canvas_requires_explicit_even_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_render,
        "_probe",
        lambda _: {"streams": [{"codec_type": "video", "width": 1080, "height": 1080}]},
    )
    assert (
        resolve_output_canvas(
            Path("video.mp4"), frame_mode="pad", target_width=1440, target_height=1080
        ).width
        == 1440
    )
    with pytest.raises(MediaRenderError, match="偶数"):
        resolve_output_canvas(
            Path("video.mp4"), frame_mode="pad", target_width=1439, target_height=1080
        )
