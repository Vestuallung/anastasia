from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import tool_path

FFMPEG = Path(tool_path("ffmpeg"))


class AudioOpeningMatchError(ValueError):
    pass


@dataclass(frozen=True)
class AudioOpeningMatch:
    offset_seconds: float
    correlation: float
    second_best_correlation: float
    sample_rate: int
    template_start_seconds: float
    template_duration_seconds: float


def decode_mono(path: Path, *, sample_rate: int, duration: float | None = None) -> np.ndarray:
    if not path.is_file():
        raise AudioOpeningMatchError(f"音频输入不存在: {path}")
    command = [str(FFMPEG), "-v", "error", "-i", str(path), "-map", "0:a:0"]
    if duration is not None:
        command.extend(["-t", f"{duration:.3f}"])
    command.extend(["-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"])
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AudioOpeningMatchError(f"无法解码音频流: {path}: {message}")
    samples = np.frombuffer(completed.stdout, dtype="<f4").astype(np.float64)
    if not samples.size:
        raise AudioOpeningMatchError(f"输入没有可解码音频样本: {path}")
    return samples


def _first_active_sample(samples: np.ndarray, sample_rate: int) -> int:
    window = max(1, sample_rate // 4)
    usable = samples[: len(samples) // window * window]
    if not usable.size:
        return 0
    rms = np.sqrt(np.mean(usable.reshape(-1, window) ** 2, axis=1))
    peak = float(np.max(rms))
    if peak <= 1e-7:
        raise AudioOpeningMatchError("外部音轨开头探测区间为静音")
    active = np.flatnonzero(rms >= max(peak * 0.12, 1e-5))
    return int(active[0] * window) if active.size else 0


def match_pcm_opening(
    reference: np.ndarray,
    external_opening: np.ndarray,
    *,
    sample_rate: int,
    template_seconds: float = 8.0,
    minimum_correlation: float = 0.60,
    minimum_margin: float = 0.03,
) -> AudioOpeningMatch:
    start = _first_active_sample(external_opening, sample_rate)
    template_length = int(round(template_seconds * sample_rate))
    template = external_opening[start : start + template_length].astype(np.float64, copy=True)
    if len(template) < template_length:
        raise AudioOpeningMatchError("外部音轨开头不足以构造匹配片段")
    if len(reference) < len(template):
        raise AudioOpeningMatchError("MV 音轨短于匹配片段")
    template -= np.mean(template)
    template_energy = float(np.dot(template, template))
    if template_energy <= 1e-10:
        raise AudioOpeningMatchError("外部音轨匹配片段缺少有效波形")

    full_length = len(reference) + len(template) - 1
    fft_length = 1 << (full_length - 1).bit_length()
    dots = np.fft.irfft(
        np.fft.rfft(reference, fft_length) * np.fft.rfft(template[::-1], fft_length),
        fft_length,
    )[len(template) - 1 : len(reference)]
    prefix = np.concatenate(([0.0], np.cumsum(reference)))
    prefix_sq = np.concatenate(([0.0], np.cumsum(reference * reference)))
    count = len(template)
    sums = prefix[count:] - prefix[:-count]
    energies = prefix_sq[count:] - prefix_sq[:-count] - sums * sums / count
    denominator = np.sqrt(np.maximum(energies, 1e-12) * template_energy)
    correlations = dots / denominator

    best_index = int(np.argmax(correlations))
    best = float(correlations[best_index])
    exclusion = max(sample_rate * 2, len(template) // 2)
    candidates = correlations.copy()
    candidates[max(0, best_index - exclusion) : best_index + exclusion + 1] = -np.inf
    second = float(np.max(candidates)) if np.isfinite(candidates).any() else -1.0
    if best < minimum_correlation:
        raise AudioOpeningMatchError(
            f"共同开头匹配置信度不足: best={best:.4f}, threshold={minimum_correlation:.4f}"
        )
    if best - second < minimum_margin:
        raise AudioOpeningMatchError(
            f"共同开头匹配峰不唯一: best={best:.4f}, second={second:.4f}, "
            f"margin={best - second:.4f}"
        )
    return AudioOpeningMatch(
        offset_seconds=(best_index - start) / sample_rate,
        correlation=best,
        second_best_correlation=second,
        sample_rate=sample_rate,
        template_start_seconds=start / sample_rate,
        template_duration_seconds=len(template) / sample_rate,
    )


def match_audio_opening(
    video: Path,
    external_audio: Path,
    *,
    sample_rate: int = 8000,
    probe_seconds: float = 20.0,
    template_seconds: float = 8.0,
    prefer_early_seconds: float | None = None,
    minimum_correlation: float = 0.60,
    minimum_margin: float = 0.03,
) -> AudioOpeningMatch:
    reference = decode_mono(video, sample_rate=sample_rate)
    if prefer_early_seconds is not None:
        if prefer_early_seconds <= template_seconds:
            raise AudioOpeningMatchError("开头优先搜索窗口必须长于匹配模板")
        reference = reference[: int(round(prefer_early_seconds * sample_rate))]
    opening = decode_mono(external_audio, sample_rate=sample_rate, duration=probe_seconds)
    return match_pcm_opening(
        reference,
        opening,
        sample_rate=sample_rate,
        template_seconds=template_seconds,
        minimum_correlation=minimum_correlation,
        minimum_margin=minimum_margin,
    )
