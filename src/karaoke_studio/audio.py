from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from .cache import sha256_file
from .config import tool_path
from .models import AudioRecord


def prepare_audio(
    source: Path, project_dir: Path, *, trim_start: float = 0, duration: float | None = None
) -> AudioRecord:
    ffmpeg = shutil.which(tool_path("ffmpeg"))
    ffprobe = shutil.which(tool_path("ffprobe"))
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required")
    destination = project_dir / ".karaoke-work" / "audio" / "prepared-16k-mono.wav"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="karaoke-audio-", dir=project_dir / ".karaoke-work"
    ) as temp:
        temporary = Path(temp) / "prepared.wav"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(trim_start),
                "-i",
                str(source),
                *(["-t", str(duration)] if duration is not None else []),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(temporary),
            ],
            check=True,
        )
        temporary.replace(destination)
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=duration",
            "-of",
            "json",
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    duration_value = metadata.get("format", {}).get("duration")
    if not duration_value:
        duration_value = next(
            (
                stream.get("duration")
                for stream in metadata.get("streams", [])
                if stream.get("duration")
            ),
            None,
        )
    if duration_value:
        duration = float(duration_value)
    else:
        with wave.open(str(destination), "rb") as handle:
            duration = handle.getnframes() / handle.getframerate()
    if duration <= 0:
        raise RuntimeError("prepared audio is empty")
    return AudioRecord(
        original_sha256=sha256_file(source),
        prepared_path=destination.relative_to(project_dir).as_posix(),
        prepared_sha256=sha256_file(destination),
        duration_ms=round(duration * 1000),
    )


def waveform_peaks(wav_path: Path, points: int = 1800) -> list[float]:
    with wave.open(str(wav_path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError("waveform generation expects 16-bit mono WAV")
        frames = handle.readframes(handle.getnframes())
    if not frames:
        return []
    samples = memoryview(frames).cast("h")
    window = max(1, len(samples) // points)
    return [
        round(max(abs(value) for value in samples[index : index + window]) / 32768, 4)
        for index in range(0, len(samples), window)
    ][:points]
