<div align="center">

# ♬ anastasia

**Karaoke Studio**

把一份歌词，变成会唱的字幕。

[![CI](https://github.com/Vestuallung/anastasia/actions/workflows/ci.yml/badge.svg)](https://github.com/Vestuallung/anastasia/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Platforms](https://img.shields.io/badge/Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-6366F1)
![License](https://img.shields.io/badge/Code-MIT-22C55E)
![Demo](https://img.shields.io/badge/Status-Demo-F59E0B)

[简体中文](README.zh_CN.md) · [English](README.en.md) · [日本語](README.ja.md)

</div>

---

视频、逐行歌词和可选的独立演唱音轨，组成一个可编辑的卡拉 OK 项目。新建制作、截取、AI 对齐、逐字打轴和导出都可以在图形界面中完成。

## 第一次制作

1. 解压发行包。在 macOS 双击 `Start-Studio-11月7日.command`，在 Windows 双击 `Start-Studio-11月7日.cmd`，在 Linux 打开终端运行 `sh Start-Studio-11月7日.sh`。首次运行会准备环境并打开项目库。
2. 点击首页齿轮，在「环境与模型」中检查状态并下载对齐模型。这里也可设置字体、团体配色和自定义模型。
3. 点击「新建制作」，选择视频和歌词。视频自带演唱音轨时可略过独立音轨。填写起止时间，结束留空表示到视频末尾。
4. 选「对齐并进入编辑」可逐句预览、拖动正文或读音边界，也可设置倍速、循环和遮黑。点「导出成片」生成所选版本。「直接生成成片」从首页一次完成制作。

新建制作和编辑器都可选择主成片的「视频码率」。选择默认画质、6／8／10.5／15／25／35 Mbps，或输入自定义值。指定码率时，macOS 优先使用 H.264 硬件编码，其余情况使用 H.264 软件编码。实际体积取决于片长和编码结果。命令行可在 `produce`、`specialize` 和 `resume` 使用 `--video-bitrate 10.5`。

需要严格满足 500 MB 上限时，可另外勾选「同时生成上传版（500 MB 以内）」。已有 MP4 可用 `karaoke compress INPUT.mp4 --output UPLOAD.mp4 --max-mb 500` 单独压缩。

歌词按原有行分句。日文可写成 `漢字《かな》`；双语文本用 `日文：…` 和 `中文：…` 交替成对填写，中文按该日文句的时间显示。空行用于划分段落。制作任务会保留进度和结果，可回到项目库查看。「从头重做」使用当前项目设置完整执行，「从断点继续」复用仍有效的阶段和视频分段。

Apple Silicon macOS 可在首次安装后打开同目录的 `KaraokeStudio-11月7日.app`。Windows 如需把环境、模型和项目放到其他盘，在解压目录运行 `Start-Studio-11月7日.cmd -DataDir D:\KaraokeStudio`。

## 从歌词到成片

**歌词与注音 → 音频准备 → Yohane 对齐 → ASS 字幕 → FFmpeg 成片**

| 功能 | 内容 |
| --- | --- |
| 歌词解析 | TXT、LRC、ASS；`漢字《かな》` 显式注音；保留原始换行、空格、标点 |
| 逐音对齐 | 用演唱音频和罗马音计算时值，保存原始对齐记录 |
| 动态字幕 | 正文与注音连续扫色、三点倒数、片假名转平假名注音、96px 正文与实际字体测宽 |
| 团体配色 | 乃木坂46、日向坂46、櫻坂46、欅坂46、≠ME；自定义名称与颜色 |
| 视频处理 | 起止截取、独立音轨、等比缩放、居中补黑、底部及分时段遮黑 |
| 多版本输出 | 演唱版、伴奏版、日中双语版 |
| 时间轴编辑 | 波形预览、逐音拖动、整句移动、读音调整、撤销与重做 |
| 自动化 | 一条命令制作、阶段复用、正式 JSON 作业、结果与进度输出 |

## 一键安装

在 GitHub 选择 **Code → Download ZIP**，解压并进入项目文件夹。也可以使用 `git clone https://github.com/Vestuallung/anastasia.git`。

### Windows · x64

将项目放到希望使用的磁盘，例如 `D:\anastasia`，在该文件夹打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

脚本自动准备 uv、Python 3.12、便携式 Git 和 FFmpeg，安装主程序与对齐环境，并下载配置中的模型。默认安装数据位于项目的 `.runtime`；工具和缓存随着数据目录存放。

指定数据盘：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DataDir D:\anastasia-data
```

### macOS · Apple Silicon / Intel

在解压后的项目文件夹打开终端：

```bash
sh install.sh
```

脚本准备 uv 与 Python 3.12，通过 Homebrew 安装 Git 和带 libass 的 `ffmpeg-full`，然后安装运行环境及模型。Homebrew 首次安装和系统依赖安装期间，按终端提示完成系统授权。应用数据默认位于项目 `.runtime`。

```bash
sh install.sh --data-dir "$HOME/anastasia-data"
```

### Linux · Ubuntu / Debian

在项目文件夹打开终端：

```bash
sh install.sh
```

脚本准备 uv 与 Python 3.12，通过 `apt-get` 安装 Git 和 FFmpeg，再安装运行环境及模型。系统软件安装使用 `sudo`；已有依赖会直接复用。脚本还可识别 `dnf`、`pacman` 和 `zypper`，使用所在发行版提供的 Git 与 FFmpeg 包。

```bash
sh install.sh --data-dir "$HOME/anastasia-data"
```

### 安装选项与目录

| 目的 | Windows | macOS / Linux |
| --- | --- | --- |
| 完整安装与模型下载 | `install.ps1` | `sh install.sh` |
| 编辑、烧录已有 ASS | `install.ps1 -MainOnly` | `sh install.sh --main-only` |
| 先装环境，随后下载模型 | `install.ps1 -SkipModel` | `sh install.sh --skip-model` |
| 指定数据目录 | `-DataDir PATH` | `--data-dir PATH` |
| 指定应用配置 | `-Config FILE` | `--config FILE` |
| 查看安装计划 | `-Plan` | `--plan` |

完整命令使用上方各系统的启动方式。安装脚本会记录运行位置，`karaoke-local` 启动时自动读取。

| 数据目录内的路径 | 内容 |
| --- | --- |
| `main/`、`align/` | 主程序环境与对齐环境 |
| `python/`、`tools/` | Python 和便携式工具 |
| `cache/uv/`、`cache/huggingface/` | 依赖与模型缓存 |
| `temp/`、`downloads/` | 安装临时文件和下载包 |
| `yohane/` | 固定版本的对齐后端 |

模型通过下载脚本获取，源码发行包包含程序、预构建界面、字体与下载配置。首次完整安装的时间取决于网络和 PyTorch、模型下载。

## 制作第一首歌

歌词 `lyrics.txt`：

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

截取使用 `--trim-start 01:39:01 --trim-end 01:42:42`，时间支持秒数、`分:秒` 和 `时:分:秒`。伴奏音轨使用 `--off-vocal backing.m4a`；译文使用 `--translation translation.json`。参数详情可运行 `produce --help`。

继续已有项目或调整颜色：

```bash
./karaoke-local resume projects/song
./karaoke-local resume projects/song --color "#00B379" --reuse --force-render
./karaoke-local serve projects/song
```

Windows 将 `./karaoke-local` 换成 `.\karaoke-local.ps1`。`serve` 打开时间轴编辑器；`resume` 默认完整重跑，`--reuse` 复用已有结果。超宽报告会列出所有需要调整断句的行，修订后继续运行。

| 输出 | 内容 |
| --- | --- |
| `on_vocal_karaoke.mp4` | 日文演唱版 |
| `off_vocal_karaoke.mp4` | 日文伴奏版 |
| `on_vocal_karaoke_zh.mp4` | 日中双语演唱版 |
| `project.karaoke.json` 与 ASS | 可继续编辑的项目与字幕 |

## 配置、团体与模型

编辑 `config.toml`；单次任务可使用 `--config custom.toml`。配置中的相对路径以该 TOML 所在文件夹为基准。

```toml
[groups.my_group]
label = "My Group"
sung = "#00B379"

[production]
default_theme = "my_group"
```

| 配置 | 作用 |
| --- | --- |
| `[tools]` | FFmpeg、ffprobe 程序名或路径 |
| `[fonts]` / `[appearance]` / `[layout]` | 字体文件与名称、字号、测宽、位置、描边 |
| `[groups.*]` / `[encoder]` | 团体颜色、视频与音频编码 |
| `[model]` | 模型 ID、revision、链接、许可、缓存 |
| `[runtime]` | 对齐解释器与 `cpu` / `cuda` / `mps` 设备 |
| `installer.toml` | uv、便携工具下载地址及 CPU 版 PyTorch 源 |

默认模型：[NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn)。自定义模型使用与日文罗马音演唱单位匹配的 **Wav2Vec2 CTC** tokenizer 和输出词表。模型配置用于新建项目，已有项目保留其记录的模型版本。默认安装 CPU 运行环境；更换设备时按所用 PyTorch 构建配置。

完整字段见 [配置参考](docs/configuration.md)。独立下载模型可运行 `scripts/download_model.py`，正式渲染作业和中文字幕格式见 [examples](examples/)。

## 自动化与接口

`produce` 执行全流程，`resume` 继续项目，`render-job` 接受 JSON 作业。最终 JSON 结果写到标准输出，阶段进度写到标准错误；退出码 `0` 为成功，`1` 为执行错误，`2` 为歌词超宽。

```bash
./karaoke-local render-job examples/render-job.json
```

图形界面使用 React、TypeScript 和 Canvas 绘制结构化字幕。FastAPI 提供本地接口与 SSE 任务进度；Yohane 和 PyTorch 负责对齐，FFmpeg 与 libass 输出 MP4。项目和作业格式见 [schemas](schemas/)。

| 接口 | 作用 |
| --- | --- |
| `GET /api/project`、`POST /api/import` | 读取与导入项目 |
| `POST /api/lines/{line_id}/reading`、`.../timing` | 调整读音与时间 |
| `POST /api/jobs/align` | 启动整曲对齐 |
| `GET /api/jobs/{job_id}/events`、`POST .../cancel` | 进度与取消 |
| `GET /api/export.ass` | 导出字幕模板 |

## 技术与许可

Python 3.12 · Typer · Pydantic · FastAPI · React / TypeScript / Vite · JASSUB · fugashi / UniDic-lite / pykakasi · Yohane / PyTorch / Transformers · Pillow · FFmpeg / libass。

程序使用 **MIT**，Noto 字体使用 **SIL OFL 1.1**，默认模型使用 **CC BY-NC-SA 4.0**。组件许可与来源见 [第三方说明](THIRD_PARTY_NOTICES.md)。
