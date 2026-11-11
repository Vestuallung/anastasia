from __future__ import annotations

from pathlib import Path

import pytest

import karaoke_studio.media_render as media_render
from karaoke_studio.media_render import MediaRenderError, resolve_output_canvas


def test_manual_video_bitrate_uses_hardware_or_software_without_crf(monkeypatch):
    canvas = media_render.Canvas(3840, 2160)
    for available, expected_codec in [(True, "h264_videotoolbox"), (False, "libx264")]:
        monkeypatch.setattr(
            media_render, "_videotoolbox_available", lambda *args, available=available: available
        )
        options = media_render._encode(10.5, canvas)
        assert options[options.index("-c:v") + 1] == expected_codec
        assert options[options.index("-b:v") + 1] == "10500000"
        assert "-crf" not in options
    assert "-crf" in media_render._encode()


def test_upload_retries_at_lower_bitrate_and_keeps_source(tmp_path, monkeypatch):
    source, output = tmp_path / "source.mp4", tmp_path / "upload.mp4"
    source.write_bytes(b"s" * 1_500_000)
    monkeypatch.setattr(media_render.sys, "platform", "linux")
    monkeypatch.setattr(
        media_render,
        "_probe",
        lambda _: {
            "format": {"duration": "3"},
            "streams": [{"codec_type": "audio", "bit_rate": "320000"}],
        },
    )
    bitrates = []

    def encode(command, scratch):
        bitrates.append(int(command[command.index("-b:v") + 1]))
        assert command[command.index("-c:a") + 1] == "copy"
        scratch.write_bytes(b"v" * (1_100_000 if len(bitrates) == 1 else 900_000))

    monkeypatch.setattr(media_render, "_run_ffmpeg", encode)
    assert media_render.compress_upload(source, output, max_mb=1).path == output
    assert len(bitrates) == 2 and bitrates[1] < bitrates[0]
    assert output.stat().st_size == 900_000
    assert source.stat().st_size == 1_500_000


def test_upload_copies_an_export_already_under_the_limit(tmp_path):
    source, output = tmp_path / "source.mp4", tmp_path / "upload.mp4"
    source.write_bytes(b"already small")
    media_render.compress_upload(source, output, max_mb=1)
    assert output.read_bytes() == source.read_bytes()


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
