from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Literal

from .audio_match import AudioOpeningMatch, AudioOpeningMatchError, match_audio_opening
from .config import configured_path, section, tool_path
from .derived_ass import Canvas

FFMPEG = Path(tool_path("ffmpeg"))
FFPROBE = Path(tool_path("ffprobe"))


class MediaRenderError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedFile:
    path: Path
    ffmpeg_exit_code: int
    reused: bool = False
    elapsed_seconds: float = 0.0


def file_identity(path: Path) -> dict:
    """Cheap local invalidation, not a content hash or final-media inspection."""
    info = path.stat()
    return {"path": str(path.resolve()), "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def write_record(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


@dataclass(frozen=True)
class MediaRenderReport:
    outputs: dict[str, RenderedFile]
    match: AudioOpeningMatch | None = None


# Compatibility aliases for callers that imported the previous report names.
OnVocalRenderReport = MediaRenderReport
DualRenderReport = MediaRenderReport


def parse_media_time(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        result = float(value)
    else:
        try:
            parts = [float(part) for part in value.strip().split(":")]
        except ValueError as exc:
            raise MediaRenderError(f"无法解析时间: {value}") from exc
        if len(parts) == 1:
            result = parts[0]
        elif len(parts) == 2:
            result = parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            result = parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            raise MediaRenderError(f"无法解析时间: {value}")
    if not math.isfinite(result) or result < 0:
        raise MediaRenderError(f"时间不得为负数: {value}")
    return result


def _probe(path: Path) -> dict:
    completed = subprocess.run(
        [str(FFPROBE), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise MediaRenderError(f"ffprobe 失败: {path}: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _stream(path: Path, kind: str) -> dict:
    stream = next(
        (item for item in _probe(path).get("streams", []) if item.get("codec_type") == kind),
        None,
    )
    if stream is None:
        label = "视频" if kind == "video" else "音频"
        raise MediaRenderError(f"输入没有可用{label}流: {path}")
    return stream


def ensure_embedded_audio(video: Path) -> None:
    _stream(video, "audio")


def _even(value: float) -> int:
    rounded = max(2, int(round(value)))
    return rounded if rounded % 2 == 0 else rounded + 1


def resolve_output_canvas(
    video: Path,
    *,
    frame_mode: Literal["preserve", "pad"] = "preserve",
    target_width: int | None = None,
    target_height: int | None = None,
) -> Canvas:
    stream = _stream(video, "video")
    if frame_mode == "pad":
        if not target_width or not target_height:
            raise MediaRenderError("pad 模式必须提供 target_width 和 target_height")
        if target_width % 2 or target_height % 2:
            raise MediaRenderError("目标画布宽高必须为偶数")
        return Canvas(target_width, target_height)
    try:
        sar = Fraction((stream.get("sample_aspect_ratio") or "1:1").replace(":", "/"))
    except (ValueError, ZeroDivisionError):
        sar = Fraction(1, 1)
    width = int(stream["width"])
    height = int(stream["height"])
    return Canvas(_even(width * float(sar)), _even(height))


def _ass_filter(path: Path, fonts_directory: Path | None = None) -> str:
    escaped = str(path.resolve()).replace("\\", r"\\").replace(":", r"\:")
    escaped = escaped.replace("'", r"\'").replace(",", r"\,")
    fonts = str(
        (fonts_directory or configured_path(section("fonts")["japanese_path"]).parent).resolve()
    )
    fonts = fonts.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")
    return f"ass='{escaped}':fontsdir='{fonts}'"


def _video_filter(
    video: Path,
    ass: Path,
    *,
    frame_mode: Literal["preserve", "pad"],
    target_width: int | None,
    target_height: int | None,
    fonts_directory: Path | None = None,
) -> str:
    canvas = resolve_output_canvas(
        video,
        frame_mode=frame_mode,
        target_width=target_width,
        target_height=target_height,
    )
    if frame_mode == "pad":
        geometry = (
            f"scale={canvas.width}:{canvas.height}:force_original_aspect_ratio=decrease,"
            f"pad={canvas.width}:{canvas.height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        )
    else:
        geometry = f"scale={canvas.width}:{canvas.height},setsar=1"
    return f"setpts=PTS-STARTPTS,{geometry},{_ass_filter(ass, fonts_directory)}"


def _run_ffmpeg(command: list[str], output: Path) -> RenderedFile:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
    if temporary.exists():
        temporary.unlink()
    started = time.perf_counter()
    last_update = 0.0
    with tempfile.TemporaryFile(mode="w+") as errors:
        with subprocess.Popen(
            [*command, "-progress", "pipe:1", "-nostats", str(temporary)],
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                if line.startswith("out_time=") and time.monotonic() - last_update >= 5:
                    print(
                        f"[编码] {output.name}: {line.strip().split('=', 1)[1]}",
                        file=sys.stderr,
                        flush=True,
                    )
                    last_update = time.monotonic()
            returncode = process.wait()
        errors.seek(0)
        message = errors.read().strip()
    if returncode != 0:
        if temporary.exists():
            temporary.unlink()
        raise MediaRenderError(f"ffmpeg 烧录失败: {output}: {message}")
    if not temporary.is_file():
        raise MediaRenderError(f"ffmpeg 返回成功但没有生成文件: {output}")
    temporary.replace(output)
    return RenderedFile(output, returncode, elapsed_seconds=round(time.perf_counter() - started, 3))


def _base_command(video: Path, trim_start: float) -> list[str]:
    return [
        str(FFMPEG),
        "-y",
        "-v",
        "error",
        "-ss",
        f"{trim_start:.6f}",
        "-i",
        str(video),
    ]


def _encode() -> list[str]:
    encoder = section("encoder")
    return [
        "-c:v",
        encoder["video_codec"],
        "-preset",
        encoder["preset"],
        "-crf",
        str(encoder["crf"]),
        "-pix_fmt",
        encoder["pixel_format"],
        "-c:a",
        encoder["audio_codec"],
        "-b:a",
        encoder["audio_bitrate"],
        "-movflags",
        encoder["movflags"],
    ]


def render_outputs(
    *,
    video: Path,
    on_vocal_audio: Path | None,
    off_vocal_audio: Path | None,
    match_reference_audio: Path | None,
    trim_start: float,
    trim_end: float,
    ass_by_output: dict[str, Path],
    output_paths: dict[str, Path],
    frame_mode: Literal["preserve", "pad"] = "preserve",
    target_width: int | None = None,
    target_height: int | None = None,
    prefer_early_seconds: float | None = None,
    minimum_correlation: float = 0.60,
    minimum_margin: float = 0.03,
    reuse_outputs: bool = True,
) -> MediaRenderReport:
    if trim_end <= trim_start:
        raise MediaRenderError("裁剪结束时间必须晚于开始时间")
    if set(ass_by_output) != set(output_paths):
        raise MediaRenderError("每个成片输出必须绑定一个 ASS")
    if len({path.resolve() for path in output_paths.values()}) != len(output_paths):
        raise MediaRenderError("多个成片输出路径不得重复")
    protected = {video.resolve(), *(path.resolve() for path in ass_by_output.values())}
    for source in (on_vocal_audio, off_vocal_audio, match_reference_audio):
        if source is not None:
            protected.add(source.resolve())
    for output in output_paths.values():
        if output.resolve() in protected:
            raise MediaRenderError(f"输出不得覆盖任何输入: {output}")
    if on_vocal_audio is None:
        ensure_embedded_audio(video)
    else:
        _stream(on_vocal_audio, "audio")
    duration = trim_end - trim_start
    match: AudioOpeningMatch | None = None
    external_start = leading_silence = 0.0
    if off_vocal_audio is not None and "off_vocal_karaoke" in output_paths:
        try:
            reference = match_reference_audio or on_vocal_audio or video
            match_key = {
                "reference": file_identity(reference),
                "external": file_identity(off_vocal_audio),
                "prefer_early_seconds": prefer_early_seconds,
                "minimum_correlation": minimum_correlation,
                "minimum_margin": minimum_margin,
                "code": file_identity(Path(__file__).with_name("audio_match.py")),
            }
            match_record = output_paths["off_vocal_karaoke"].with_suffix(".opening.json")
            try:
                previous_match = json.loads(match_record.read_text(encoding="utf-8"))
                if previous_match.get("signature") == match_key:
                    match = AudioOpeningMatch(**previous_match["match"])
            except (OSError, ValueError, TypeError, KeyError):
                match = None
            if match is None:
                match = match_audio_opening(
                    reference,
                    off_vocal_audio,
                    prefer_early_seconds=prefer_early_seconds,
                    minimum_correlation=minimum_correlation,
                    minimum_margin=minimum_margin,
                )
                write_record(match_record, {"signature": match_key, "match": asdict(match)})
        except AudioOpeningMatchError as exc:
            raise MediaRenderError(str(exc)) from exc
        external_start = trim_start - match.offset_seconds
        leading_silence = max(0.0, -external_start)
        external_start = max(0.0, external_start)

    font_settings = section("fonts")
    font_paths = list(
        dict.fromkeys(
            configured_path(font_settings[key]) for key in ("japanese_path", "chinese_path")
        )
    )
    with tempfile.TemporaryDirectory(prefix="karaoke-fonts-") as font_root:
        fonts_directory = Path(font_root)
        for index, font in enumerate(font_paths):
            shutil.copy2(font, fonts_directory / f"{index}{font.suffix}")
        rendered: dict[str, RenderedFile] = {}
        for name, output in output_paths.items():
            ass = ass_by_output[name]
            video_filter = _video_filter(
                video,
                ass,
                frame_mode=frame_mode,
                target_width=target_width,
                target_height=target_height,
                fonts_directory=fonts_directory,
            )
            command = _base_command(video, trim_start)
            if name == "off_vocal_karaoke":
                if off_vocal_audio is None:
                    raise MediaRenderError("请求了 off_vocal_karaoke，但没有提供 off-vocal 音频")
                command.extend(["-ss", f"{external_start:.6f}", "-i", str(off_vocal_audio)])
                audio_map = "1:a:0"
                audio_filter = (
                    f"adelay={round(leading_silence * 1000)}:all=1,asetpts=PTS-STARTPTS,apad"
                )
            elif on_vocal_audio is not None:
                command.extend(["-ss", f"{trim_start:.6f}", "-i", str(on_vocal_audio)])
                audio_map, audio_filter = "1:a:0", "asetpts=PTS-STARTPTS,apad"
            else:
                audio_map, audio_filter = "0:a:0", "asetpts=PTS-STARTPTS,apad"
            command.extend(
                [
                    "-t",
                    f"{duration:.6f}",
                    "-map",
                    "0:v:0",
                    "-map",
                    audio_map,
                    "-vf",
                    video_filter,
                    "-af",
                    audio_filter,
                    *_encode(),
                ]
            )
            # ASS text is cheap to compare; source media use metadata only. Each
            # output has an independent receipt, so translation/off-vocal changes
            # do not invalidate unrelated versions.
            inputs = [video]
            if name == "off_vocal_karaoke":
                inputs.append(off_vocal_audio)
                inputs.append(match_reference_audio or on_vocal_audio or video)
            elif on_vocal_audio is not None:
                inputs.append(on_vocal_audio)
            signature = {
                "command": [
                    arg.replace(str(fonts_directory), "{configured_fonts}") for arg in command
                ],
                "fonts": [file_identity(path) for path in font_paths],
                "inputs": [file_identity(path) for path in inputs if path is not None],
                "ass": ass.read_text(encoding="utf-8"),
                "renderer": file_identity(Path(__file__)),
            }
            receipt = output.with_name(f".{output.name}.render.json")
            try:
                previous = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                previous = {}
            if (
                reuse_outputs
                and output.is_file()
                and previous.get("signature") == signature
                and previous.get("output") == file_identity(output)
            ):
                rendered[name] = RenderedFile(output, 0, reused=True)
                print(f"[复用成片] {output}", file=sys.stderr, flush=True)
                continue
            started_at = datetime.now(UTC).isoformat()
            rendered[name] = _run_ffmpeg(command, output)
            write_record(
                receipt,
                {
                    "signature": signature,
                    "output": file_identity(output),
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": rendered[name].elapsed_seconds,
                    "ffmpeg_exit_code": rendered[name].ffmpeg_exit_code,
                },
            )
        return MediaRenderReport(rendered, match)
