from __future__ import annotations

import hashlib
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
from functools import lru_cache
from pathlib import Path
from typing import Literal

from .audio_match import AudioOpeningMatch, AudioOpeningMatchError, match_audio_opening
from .config import configured_path, section, tool_path
from .derived_ass import FONT_PATH, ZH_FONT_PATH, Canvas

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
    segments_total: int = 0
    segments_reused: int = 0


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
    if isinstance(value, str) and "@" in value:
        try:
            clock, rate_text = value.strip().split("@")
            hours, minutes, seconds, frame = map(int, clock.split(":"))
            rate = Fraction(rate_text)
            if (
                rate <= 0
                or min(hours, minutes, seconds, frame) < 0
                or minutes >= 60
                or seconds >= 60
                or frame >= math.ceil(rate)
            ):
                raise ValueError()
            return hours * 3600 + minutes * 60 + seconds + float(frame / rate)
        except (ValueError, ZeroDivisionError) as exc:
            raise MediaRenderError(f"帧时间码格式应为 HH:MM:SS:FF@FPS: {value}") from exc
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
            raise MediaRenderError(f"无法解析时间: {value}；帧时间码请注明帧率，例如00:04:33:50@60")
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


def _filter_option(value: str) -> str:
    """Escape an option value at both FFmpeg filter parsing levels."""
    for char in ("\\", "'", ":"):
        value = value.replace(char, "\\" + char)
    for char in ("\\", "'", "[", "]", ",", ";"):
        value = value.replace(char, "\\" + char)
    return value


def _ass_filter(path: Path, fonts_directory: Path | None = None) -> str:
    source = _filter_option(path.resolve().as_posix())
    directory = fonts_directory or configured_path(section("fonts")["japanese_path"]).parent
    fonts = _filter_option(directory.resolve().as_posix())
    return f"ass=filename={source}:fontsdir={fonts}"


def _video_filter(
    video: Path,
    ass: Path,
    *,
    frame_mode: Literal["preserve", "pad"],
    target_width: int | None,
    target_height: int | None,
    blackout: list[dict] | None = None,
    timeline_offset: float = 0.0,
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
    masks = []
    for region in blackout or []:
        x, y, w, h = (
            region.get(k, default)
            for k, default in (("x", 0), ("y", 0), ("width", 1920), ("height", 1080))
        )
        box = f"drawbox=x=iw*{x}/1920:y=ih*{y}/1080:w=iw*{w}/1920:h=ih*{h}/1080:color=black:t=fill"
        begin, end = region.get("start", 0), region.get("end")
        box += f":enable='gte(t,{begin})'" if end is None else f":enable='between(t,{begin},{end})'"
        masks.append(box)
    return ",".join(
        [
            f"setpts=PTS-STARTPTS+{timeline_offset:.9f}/TB",
            geometry,
            *masks,
            _ass_filter(ass, fonts_directory),
            "setpts=PTS-STARTPTS",
        ]
    )


def _run_ffmpeg(
    command: list[str], output: Path, expected_frames: int | None = None, lock_fd: int | None = None
) -> RenderedFile:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
    if temporary.exists():
        temporary.unlink()
    started = time.perf_counter()
    last_update = 0.0
    frames = 0
    with tempfile.TemporaryFile(mode="w+") as errors:
        with subprocess.Popen(
            [*command, "-progress", "pipe:1", "-nostats", str(temporary)],
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            **({"pass_fds": (lock_fd,)} if lock_fd is not None and sys.platform != "win32" else {}),
        ) as process:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    if line.startswith("frame="):
                        frames = int(line.split("=", 1)[1].strip())
                    if line.startswith("out_time=") and time.monotonic() - last_update >= 5:
                        print(
                            f"[编码] {output.name}: {line.strip().split('=', 1)[1]}",
                            file=sys.stderr,
                            flush=True,
                        )
                        last_update = time.monotonic()
            except BaseException:
                process.terminate()
                process.wait()
                raise
            returncode = process.wait()
        errors.seek(0)
        message = errors.read().strip()
    if returncode != 0:
        if temporary.exists():
            temporary.unlink()
        raise MediaRenderError(f"ffmpeg 烧录失败: {output}: {message}")
    if not temporary.is_file():
        raise MediaRenderError(f"ffmpeg 返回成功但没有生成文件: {output}")
    if expected_frames is not None and frames != expected_frames:
        temporary.unlink()
        raise MediaRenderError(f"分段帧数不完整: {output}: {frames}/{expected_frames}")
    temporary.replace(output)
    return RenderedFile(output, returncode, elapsed_seconds=round(time.perf_counter() - started, 3))


def compress_upload(source: Path, output: Path, max_mb: int = 500) -> RenderedFile:
    """Create an MP4 copy that fits a decimal MB limit without resizing."""
    if source.suffix.lower() != ".mp4" or output.suffix.lower() != ".mp4":
        raise MediaRenderError("上传压缩需要 MP4 输入和输出")
    if source.resolve() == output.resolve() or max_mb <= 0:
        raise MediaRenderError("请指定独立的上传版路径及正数体积上限")
    limit = max_mb * 1_000_000
    started = time.perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".mp4", dir=output.parent, delete=False) as handle:
        scratch = Path(handle.name)
    try:
        if source.stat().st_size <= limit:
            shutil.copyfile(source, scratch)
        else:
            info = _probe(source)
            duration = float(info.get("format", {}).get("duration") or 0)
            if not math.isfinite(duration) or duration <= 0:
                raise MediaRenderError("无法读取成片时长，不能计算上传码率")
            audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
            audio_rate = str(audio.get("bit_rate", "")) if audio else "0"
            audio_bps = int(audio_rate) if audio_rate.isdigit() else 320_000
            bitrate = int(limit * 8 * .9 / duration) - audio_bps
            codec = "h264_videotoolbox" if sys.platform == "darwin" else "libx264"
            for _ in range(3):
                if bitrate < 100_000:
                    raise MediaRenderError(f"{max_mb} MB 上限不足以容纳当前音轨和视频")
                base = [str(FFMPEG), "-y", "-v", "error", "-i", str(source), "-map", "0:v:0",
                        "-map", "0:a:0?", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart"]
                if codec == "h264_videotoolbox":
                    try:
                        _run_ffmpeg([*base, "-c:v", codec, "-b:v", str(bitrate)], scratch)
                    except MediaRenderError:
                        codec = "libx264"
                if codec == "libx264":
                    _run_ffmpeg([*base, "-c:v", codec, "-preset", "veryfast", "-b:v", str(bitrate)], scratch)
                size = scratch.stat().st_size
                if size <= limit:
                    break
                bitrate = int(bitrate * limit / size * .85)
            else:
                raise MediaRenderError(f"上传版未达到 {max_mb} MB 上限")
        if not 0 < scratch.stat().st_size <= limit:
            raise MediaRenderError(f"上传版为空或超过 {max_mb} MB 上限")
        scratch.replace(output)
    finally:
        scratch.unlink(missing_ok=True)
    return RenderedFile(output, 0, elapsed_seconds=round(time.perf_counter() - started, 3))


def upload_copies(files: dict[str, str], max_mb: int = 500) -> dict[str, str]:
    today = datetime.now()
    date = f"{today.month}月{today.day}日"
    copies = {}
    original_paths = {Path(value).resolve() for value in files.values()}
    for name, path in files.items():
        source = Path(path)
        destination = source.with_name(f"{source.stem}-upload-{date}.mp4")
        if destination.resolve() in original_paths:
            raise MediaRenderError("上传版路径与其他成片重复")
        copies[f"{name}_upload"] = str(compress_upload(source, destination, max_mb).path)
    return {**files, **copies}


def _checkpoint_render(
    *,
    video: Path,
    ass: Path,
    output: Path,
    signature: dict,
    trim_start: float,
    duration: float,
    segment_seconds: float,
    audio: Path,
    audio_start: float,
    audio_filter: str,
    frame_mode: str,
    target_width: int | None,
    target_height: int | None,
    blackout: list[dict],
    reuse: bool,
    fonts_directory: Path,
    encoding: list[str],
) -> RenderedFile:
    """Video checkpoints share one ASS clock; encode audio once after concatenation."""
    from .service import _production_lock

    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    audio_options = encoding.index("-c:a")
    with _production_lock(
        output.with_name(f".{output.name}.lock"), f"该成片已有烧录任务: {output}"
    ) as lock:
        stream = _stream(video, "video")
        rate = Fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1")
        if rate <= 0:
            raise MediaRenderError("分段烧录需要有效视频帧率")
        fps = float(rate)
        total_frames = math.ceil(duration * fps - 1e-7)
        step = max(1, round(segment_seconds * fps))
        key = hashlib.sha256(
            json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        cache = output.parent / ".karaoke-work" / "render-segments" / output.stem / key
        cache.mkdir(parents=True, exist_ok=True)
        parts, reused = [], 0
        total = math.ceil(total_frames / step)
        for number, frame in enumerate(range(0, total_frames, step)):
            count = min(step, total_frames - frame)
            part = cache / f"part-{number:05d}.mkv"
            receipt = part.with_suffix(".json")
            try:
                previous = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                previous = {}
            if reuse and part.is_file() and previous.get("output") == file_identity(part):
                reused += 1
                print(
                    f"[复用分段] {output.name}: {number + 1}/{total}", file=sys.stderr, flush=True
                )
            else:
                offset = frame / fps
                vf = _video_filter(
                    video,
                    ass,
                    frame_mode=frame_mode,
                    target_width=target_width,
                    target_height=target_height,
                    blackout=blackout,
                    timeline_offset=offset,
                    fonts_directory=fonts_directory,
                )
                command = [
                    *_base_command(video, trim_start + offset),
                    "-an",
                    "-vf",
                    f"fps={rate},{vf}",
                    "-frames:v",
                    str(count),
                    "-r",
                    str(rate),
                    *encoding[:audio_options],
                ]
                print(
                    f"[烧录分段] {output.name}: {number + 1}/{total}", file=sys.stderr, flush=True
                )
                _run_ffmpeg(command, part, expected_frames=count, lock_fd=lock.fileno())
                write_record(receipt, {"output": file_identity(part), "frames": count})
            parts.append(part)
        # Relative filenames keep ffconcat quoting independent of user paths.
        concat = cache / "parts.ffconcat"
        concat.write_text(
            "ffconcat version 1.0\n"
            + "".join(
                f"file {p.name}\nduration {min(step, total_frames - n * step) / fps:.12f}\n"
                for n, p in enumerate(parts)
            ),
            encoding="utf-8",
        )
        command = [
            str(FFMPEG),
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-ss",
            f"{audio_start:.9f}",
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.9f}",
            "-c:v",
            "copy",
            "-af",
            audio_filter,
            *encoding[audio_options:],
        ]
        _run_ffmpeg(command, output, lock_fd=lock.fileno())
        return RenderedFile(
            output,
            0,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            segments_total=total,
            segments_reused=reused,
        )


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


@lru_cache(maxsize=16)
def _videotoolbox_available(canvas: Canvas, pixel_format: str, bitrate: str) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(
            [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
             f"color=size={canvas.width}x{canvas.height}:rate=24", "-frames:v", "1",
             "-c:v", "h264_videotoolbox", "-b:v", bitrate, "-pix_fmt", pixel_format,
             "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _encode(video_bitrate_mbps: float | None = None, canvas: Canvas | None = None) -> list[str]:
    encoder = section("encoder")
    if video_bitrate_mbps is None:
        video = ["-c:v", encoder["video_codec"], "-preset", encoder["preset"], "-crf", str(encoder["crf"])]
    else:
        if not 0.1 <= video_bitrate_mbps <= 1000:
            raise MediaRenderError("视频码率必须在 0.1 到 1000 Mbps 之间")
        bitrate = str(round(video_bitrate_mbps * 1_000_000))
        if canvas is not None and _videotoolbox_available(canvas, encoder["pixel_format"], bitrate):
            video = ["-c:v", "h264_videotoolbox", "-b:v", bitrate]
        else:
            video = ["-c:v", "libx264", "-preset", encoder["preset"], "-b:v", bitrate]
    return [
        *video,
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
    reuse_outputs: bool = False,
    blackout: list[dict] | None = None,
    segment_seconds: float = 30,
    video_bitrate_mbps: float | None = None,
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
    canvas = None if video_bitrate_mbps is None else resolve_output_canvas(
        video, frame_mode=frame_mode, target_width=target_width, target_height=target_height
    )
    encoding = _encode(video_bitrate_mbps, canvas)
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
                if reuse_outputs and previous_match.get("signature") == match_key:
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

    with tempfile.TemporaryDirectory(prefix="karaoke-fonts-") as folder:
        fonts_directory = Path(folder)
        font_paths = tuple(dict.fromkeys(Path(path) for path in (FONT_PATH, ZH_FONT_PATH)))
        for index, font in enumerate(font_paths):
            if not font.is_file():
                raise MediaRenderError(f"找不到配置的字体文件: {font}")
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
                blackout=blackout,
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
                    *encoding,
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
                    arg.replace(
                        _filter_option(fonts_directory.resolve().as_posix()), "{configured_fonts}"
                    )
                    for arg in command
                ],
                "inputs": [file_identity(path) for path in inputs if path is not None],
                "ass": ass.read_text(encoding="utf-8"),
                "renderer": file_identity(Path(__file__)),
                "font": file_identity(Path(ZH_FONT_PATH)),
                "japanese_font": file_identity(Path(FONT_PATH)),
                "segment_seconds": segment_seconds,
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
            if segment_seconds > 0:
                audio_source = (
                    off_vocal_audio if name == "off_vocal_karaoke" else (on_vocal_audio or video)
                )
                rendered[name] = _checkpoint_render(
                    video=video,
                    ass=ass,
                    output=output,
                    signature=signature,
                    trim_start=trim_start,
                    duration=duration,
                    segment_seconds=segment_seconds,
                    audio=audio_source,
                    audio_start=external_start if name == "off_vocal_karaoke" else trim_start,
                    audio_filter=audio_filter,
                    frame_mode=frame_mode,
                    target_width=target_width,
                    target_height=target_height,
                    blackout=blackout or [],
                    reuse=reuse_outputs,
                    fonts_directory=fonts_directory,
                    encoding=encoding,
                )
            else:
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
