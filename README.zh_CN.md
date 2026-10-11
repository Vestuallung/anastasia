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

输入 **视频 + 演唱音频 + 逐行歌词**，制作带注音、连续扫色和团体配色的日文卡拉 OK。命令行完成整套制作，浏览器时间轴用于调整读音与演唱时值。

## 从歌词到成片

**歌词与注音 → 音频准备 → Yohane 对齐 → ASS 字幕 → FFmpeg 成片**

| 功能 | 内容 |
| --- | --- |
| 歌词解析 | TXT、LRC、ASS；`漢字《かな》` 显式注音；保留原始换行、空格、标点 |
| 逐音对齐 | 用演唱音频和罗马音计算时值，保存原始对齐记录 |
| 动态字幕 | 正文与注音连续扫色；默认 96px；实际字体测宽 |
| 团体配色 | 乃木坂46、日向坂46、櫻坂46、欅坂46、≠ME；自定义名称与颜色 |
| 视频处理 | 起止截取、独立音轨、等比缩放、居中补黑 |
| 多版本输出 | 演唱版、伴奏版、日中双语版、纯中文字幕版 |
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
./karaoke-local resume projects/song --color "#00B379" --force-render
./karaoke-local serve projects/song
```

Windows 将 `./karaoke-local` 换成 `.\karaoke-local.ps1`。`serve` 打开时间轴编辑器；`resume` 根据输入变化复用步骤。超宽报告会列出所有需要调整断句的行，修订后继续运行。

| 输出 | 内容 |
| --- | --- |
| `on_vocal_karaoke.mp4` | 日文演唱版 |
| `off_vocal_karaoke.mp4` | 日文伴奏版 |
| `on_vocal_karaoke_zh.mp4` | 日中双语演唱版 |
| `on_vocal_zh_only.mp4` | 纯中文字幕演唱版 |
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

编辑器使用 FastAPI REST 与 SSE。启动 `serve` 后，访问服务的 `/docs` 查看参数结构；启动地址里的 token 可作为 `X-Karaoke-Token` 请求头。

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
