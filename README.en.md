<div align="center">

# ♬ anastasia

**Karaoke Studio**

Turn lyrics into subtitles that sing.

[![CI](https://github.com/Vestuallung/anastasia/actions/workflows/ci.yml/badge.svg)](https://github.com/Vestuallung/anastasia/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Platforms](https://img.shields.io/badge/Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-6366F1)
![License](https://img.shields.io/badge/Code-MIT-22C55E)
![Demo](https://img.shields.io/badge/Status-Demo-F59E0B)

[简体中文](README.zh_CN.md) · [English](README.en.md) · [日本語](README.ja.md)

</div>

---

Turn a video, line-by-line lyrics, and optional separate vocals into an editable karaoke project. The studio handles setup, trimming, AI alignment, timing edits, and video export.

## Make your first video

1. Extract the release. Double-click `Start-Studio-11月7日.command` on macOS or `Start-Studio-11月7日.cmd` on Windows. On Linux, run `sh Start-Studio-11月7日.sh` in the extracted folder. The first launch prepares the environment and opens the project library.
2. Use the gear on the home page to check the environment and download the alignment model. The same panel manages fonts, group colors, and custom models.
3. Choose **New production** and select the video and lyrics. A separate vocal track is optional when the video already has vocals. Enter a start and end time. A blank end uses the end of the video.
4. Choose **Align and edit** to preview lyrics, drag character or reading boundaries, and adjust playback speed, looping, or blackout. Export the selected versions from the editor, or choose **Create video directly** in the new production form.

Use **视频码率** (video bitrate) in the new production form or editor to choose a target bitrate for the main export. Choose the default quality, a preset, or a custom value in Mbps. Target bitrate mode uses H.264 hardware encoding on macOS when available and software encoding otherwise. Use `--video-bitrate 10.5` with `produce`, `specialize`, or `resume` on the command line.

For a strict 500 MB limit, also select **同时生成上传版（500 MB 以内）**. To compress an existing export, run `karaoke compress INPUT.mp4 --output UPLOAD.mp4 --max-mb 500`.

Each lyric line keeps its original boundaries. Use `漢字《かな》` for explicit readings. For bilingual lyrics, alternate `日文：…` and `中文：…`. Each Chinese line follows the timing of its Japanese partner. Blank lines mark sections. The project library retains job progress and results. **Run from scratch** uses current settings, and **Continue from checkpoint** reuses valid stages and video segments.

After setup, Apple Silicon macOS users can open `KaraokeStudio-11月7日.app` from the same folder. On Windows, run `Start-Studio-11月7日.cmd -DataDir D:\KaraokeStudio` from the extracted folder to choose the drive for the environment, models, and projects.

## From lyrics to video

**Lyrics & furigana → Audio preparation → Yohane alignment → ASS subtitles → FFmpeg video**

| Feature | What it does |
| --- | --- |
| Lyrics | TXT, LRC and ASS; explicit `漢字《かな》` readings; original line breaks, spaces and punctuation |
| Alignment | Per-unit timing from on-vocal audio and romanized lyrics, with raw results preserved |
| Karaoke | Continuous sweeps, three-dot cues, hiragana ruby for katakana, and real-font width measurement at 96px by default |
| Themes | Nogizaka46, Hinatazaka46, Sakurazaka46, Keyakizaka46, ≠ME and custom groups |
| Media | Time-range trimming, separate audio, proportional scaling, centered padding, and timed blackout regions |
| Variants | On-vocal, off-vocal, Japanese/Chinese and Chinese-only videos |
| Editor | Waveform, mora dragging, line shifts, reading edits, undo and redo |
| Automation | One-command production, stage reuse, JSON jobs and machine-readable results |

## One-command installation

Choose **Code → Download ZIP** on GitHub, extract it and open a terminal in the project folder. You can also run `git clone https://github.com/Vestuallung/anastasia.git`.

### Windows · x64

Place the project on your preferred drive, for example `D:\anastasia`, and open PowerShell there:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The script prepares uv, Python 3.12, portable Git and FFmpeg, installs the application and alignment environments, and downloads the configured model. Installation data defaults to the project’s `.runtime` folder; tools and caches follow the selected data directory.

Choose a data drive:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DataDir D:\anastasia-data
```

### macOS · Apple Silicon / Intel

Open Terminal in the extracted project folder:

```bash
sh install.sh
```

The script prepares uv and Python 3.12, installs Git and `ffmpeg-full` with libass through Homebrew, then installs the runtimes and model. Follow the terminal’s system authorization prompts during Homebrew and system-package installation. Application data defaults to `.runtime`.

```bash
sh install.sh --data-dir "$HOME/anastasia-data"
```

### Linux · Ubuntu / Debian

Open a terminal in the project folder:

```bash
sh install.sh
```

The script prepares uv and Python 3.12, installs Git and FFmpeg through `apt-get`, and prepares the runtimes and model. System packages use `sudo`; existing dependencies are reused. The script also recognizes `dnf`, `pacman` and `zypper` and uses the distribution’s Git and FFmpeg packages.

```bash
sh install.sh --data-dir "$HOME/anastasia-data"
```

### Options and storage

| Purpose | Windows | macOS / Linux |
| --- | --- | --- |
| Full setup and model download | `install.ps1` | `sh install.sh` |
| Edit and burn existing ASS | `install.ps1 -MainOnly` | `sh install.sh --main-only` |
| Set up runtimes, download the model later | `install.ps1 -SkipModel` | `sh install.sh --skip-model` |
| Data directory | `-DataDir PATH` | `--data-dir PATH` |
| Application configuration | `-Config FILE` | `--config FILE` |
| Installation plan | `-Plan` | `--plan` |

Use each platform’s launcher shown above. The installer records runtime locations, which `karaoke-local` loads automatically.

| Path inside the data directory | Contents |
| --- | --- |
| `main/`, `align/` | Application and alignment environments |
| `python/`, `tools/` | Python and portable tools |
| `cache/uv/`, `cache/huggingface/` | Dependency and model caches |
| `temp/`, `downloads/` | Temporary installation files and archives |
| `yohane/` | Pinned alignment backend |

Models are obtained through the download script. The source distribution contains application code, the prebuilt editor, fonts and download configuration. Initial full setup duration depends on the network and PyTorch/model downloads.

## Your first song

Create `lyrics.txt`:

```text
歌《うた》を歌《うた》う
明日《あした》へ歩《ある》こう
```

**Windows PowerShell**

```powershell
.\karaoke-local.ps1 produce video.mp4 "Song" --lyrics-file lyrics.txt --audio audio.m4a --project projects/song --theme not_equal_me --title-text "Song/≠ME"
```

**macOS / Linux**

```bash
./karaoke-local produce video.mp4 "Song" \
  --lyrics-file lyrics.txt --audio audio.m4a \
  --project projects/song --theme not_equal_me --title-text "Song/≠ME"
```

Trim with `--trim-start 01:39:01 --trim-end 01:42:42`. Times accept seconds, `minutes:seconds` or `hours:minutes:seconds`. Add a backing track with `--off-vocal backing.m4a` and Chinese translations with `--translation translation.json`. Run `produce --help` for the complete parameter list.

Resume, recolor or open the editor:

```bash
./karaoke-local resume projects/song
./karaoke-local resume projects/song --color "#00B379" --reuse --force-render
./karaoke-local serve projects/song
```

On Windows, replace `./karaoke-local` with `.\karaoke-local.ps1`. `serve` opens the timeline editor; `resume` reruns from scratch by default, and `--reuse` reuses valid stages. Width reports list every line needing revised breaks so you can edit the input and resume.

| Output | Contents |
| --- | --- |
| `on_vocal_karaoke.mp4` | Japanese on-vocal karaoke |
| `off_vocal_karaoke.mp4` | Japanese off-vocal karaoke |
| `on_vocal_karaoke_zh.mp4` | Japanese/Chinese on-vocal karaoke |
| `project.karaoke.json` and ASS | Editable project and subtitles |

## Configuration, groups and models

Edit `config.toml`, or choose `--config custom.toml` for a run. Relative paths resolve from the TOML file’s folder.

```toml
[groups.my_group]
label = "My Group"
sung = "#00B379"

[production]
default_theme = "my_group"
```

| Configuration | Purpose |
| --- | --- |
| `[tools]` | FFmpeg and ffprobe executable names or paths |
| `[fonts]` / `[appearance]` / `[layout]` | Font files/names, size, width, position and outline |
| `[groups.*]` / `[encoder]` | Group colors and media encoding |
| `[model]` | Model ID, revision, URL, license and cache |
| `[runtime]` | Alignment interpreter and `cpu` / `cuda` / `mps` |
| `installer.toml` | uv/tool download sources and the CPU PyTorch index |

Default model: [NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn). Custom models use **Wav2Vec2 CTC** tokenizers and vocabularies compatible with the romanized Japanese singing units. Model configuration applies to new projects; existing projects retain their recorded versions. The default installer prepares a CPU runtime; configure an appropriate PyTorch build when selecting another device.

See the [configuration reference](docs/configuration.md) for all fields. `scripts/download_model.py` downloads a model independently. Formal render jobs and translation formats are in [examples](examples/).

## Automation and API

`produce` runs the pipeline, `resume` continues a project, and `render-job` reads a JSON job. Final JSON goes to stdout; progress goes to stderr. Exit codes: `0` success, `1` execution error, `2` overwide lyrics.

```bash
./karaoke-local render-job examples/render-job.json
```

React, TypeScript, and Canvas draw the structured preview. FastAPI provides the local API and SSE job progress, Yohane and PyTorch align lyrics, and FFmpeg with libass exports MP4. See [schemas](schemas/) for the project and job formats.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/project`, `POST /api/import` | Read and import projects |
| `POST /api/lines/{line_id}/reading`, `.../timing` | Edit readings and timing |
| `POST /api/jobs/align` | Start full-song alignment |
| `GET /api/jobs/{job_id}/events`, `POST .../cancel` | Progress and cancellation |
| `GET /api/export.ass` | Export subtitle templates |

## Technology and licenses

Python 3.12 · Typer · Pydantic · FastAPI · React / TypeScript / Vite · JASSUB · fugashi / UniDic-lite / pykakasi · Yohane / PyTorch / Transformers · Pillow · FFmpeg / libass.

Application: **MIT**. Noto fonts: **SIL OFL 1.1**. Default model: **CC BY-NC-SA 4.0**. Component sources and licenses appear in [third-party notices](THIRD_PARTY_NOTICES.md).
