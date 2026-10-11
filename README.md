# Karaoke Studio

Karaoke Studio 是一套本地日文卡拉 OK 制作工作台。输入视频、演唱音频和逐行歌词，即可完成读音解析、歌词时间对齐、动态字幕生成和视频输出。项目同时提供命令行流程与浏览器时间轴编辑器，适合单曲制作、字幕调整与连续重跑。

## 功能

- **完整制作**：`produce` 依次执行歌词解析、输入归档、16 kHz 单声道音频准备、Yohane 强制对齐、ASS 模板导出、字幕展开和视频编码。
- **歌词与注音**：支持 TXT、LRC、ASS 导入，以及 `漢字《かな》` 显式注音。换行、空格、标点和大小写按输入保留；空行作为段落信息处理。
- **日文读音准备**：MeCab/UniDic 与 pykakasi 提供假名和罗马音；显式注音及读音覆盖文件用于指定人名、专名和英文读音。
- **逐音时间对齐**：Yohane 根据音频和罗马音计算每个演唱单位的时值，原始对齐记录保存在项目中。
- **连续扫色字幕**：正文和注音随演唱连续变色。默认正文为 96 逻辑像素，注音为正文的一半，未唱白字黑边，已唱团体色白边。
- **团体主题**：附带乃木坂46、日向坂46、櫻坂46、欅坂46、≠ME 和红色主题。新增团体可直接编辑 TOML 配置。
- **宽度计算**：按实际配置字体测量歌词宽度，默认上限 1700 逻辑像素。超宽报告包含句子、下标、时间与宽度，便于调整断句后继续制作。
- **视频截取**：支持起止时间、独立演唱音频、原画面比例输出以及指定尺寸的等比缩放和居中补黑。
- **多版本导出**：支持演唱版、伴奏版、日中双语演唱版和纯中文字幕演唱版。伴奏音轨使用开头匹配计算偏移；中文时间继承日文时间轴。
- **阶段复用**：`resume` 根据输入与参数变化复用已有步骤。改色、位置和标题会重新生成字幕；`--force-render` 强制重新编码视频。
- **浏览器编辑器**：包含视频预览、假名显示、波形、逐音时间轴、整句移动、相邻时间边界拖动、读音编辑、撤销重做以及 ASS 下载。
- **可配置运行环境**：工具路径、字体、主题、布局、模型、推理设备与编码参数统一由 `config.toml` 管理。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 主程序与命令行 | Python 3.12、Typer、Pydantic |
| 浏览器服务 | FastAPI、Uvicorn、REST/SSE |
| 前端编辑器 | React、TypeScript、Vite、JASSUB |
| 日文文本处理 | fugashi/MeCab、UniDic-lite、pykakasi |
| 音频对齐 | Yohane、PyTorch、Torchaudio、Transformers |
| 字幕与视频 | ASS、Pillow、FFmpeg/libass |
| 安装与构建 | uv、Hatchling、npm |

## 安装

入口覆盖 Windows、macOS 和 Linux。GitHub CI 在三个系统上运行后端测试、前端测试及安装包构建。

准备 Python 3.12、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Git，以及带 `ass` 滤镜的 [FFmpeg/ffprobe](https://ffmpeg.org/download.html)。前端开发和重新构建使用 Node.js 22。

在仓库根目录运行：

```bash
python scripts/setup.py --with-model
```

安装脚本创建主程序环境 `.venv` 和对齐环境 `.runtime/align`，按配置中的固定 revision 获取 Yohane，应用 `patches/yohane-runtime.patch`，安装对齐依赖，并下载配置中的模型到 Hugging Face 缓存。

分开运行安装与模型下载：

```bash
python scripts/setup.py
python scripts/download_model.py
```

安装参数：

| 参数 | 用途 |
| --- | --- |
| `--config config.local.toml` | 使用自定义配置文件 |
| `--main-only` | 安装主程序环境，适合 ASS 编辑和已有轨迹渲染 |
| `--build-web` | 安装前端依赖并重建编辑器 |
| `--with-model` | 环境安装结束后下载模型 |
| `--dry-run` | 输出安装步骤供查看 |

仓库提供已构建的浏览器界面及 Noto 字体，安装后即可使用。

### Windows PowerShell

准备 uv、Git 和带 ASS 滤镜的 Windows FFmpeg，运行以下入口。uv 会按项目要求准备 Python 3.12，并在项目目录创建独立环境：

```powershell
.\scripts\setup-windows.ps1 -WithModel
.\karaoke-local.ps1 --help
.\karaoke-local.ps1 produce video.mp4 "Song" --lyrics-file lyrics.txt --audio audio.m4a --project projects/song --theme not_equal_me
```

`-MainOnly` 用于安装主程序、编辑 ASS 和烧录已有时间轴；`-DryRun` 显示安装步骤；`-Config` 选择 TOML 文件；`-BuildWeb` 重建界面。便携式环境可把全部安装数据集中到指定磁盘，例如：

```powershell
$env:UV_CACHE_DIR = "D:\karaoke-demo\cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "D:\karaoke-demo\python"
$env:UV_TOOL_DIR = "D:\karaoke-demo\tools\envs"
$env:UV_TOOL_BIN_DIR = "D:\karaoke-demo\tools\bin"
$env:TEMP = "D:\karaoke-demo\temp"
$env:TMP = $env:TEMP
$env:HF_HOME = "D:\karaoke-demo\cache\huggingface"
$env:TORCH_HOME = "D:\karaoke-demo\cache\torch"
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.\scripts\setup-windows.ps1 -MainOnly
```

将仓库放在相同磁盘后，应用环境 `.venv` 与对齐环境 `.runtime/align` 也会创建在该磁盘。FFmpeg 可加入当前会话的 PATH，或通过 `[tools]` 设置所在路径。uv 与 FFmpeg 获取方式见 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/) 和 [FFmpeg 下载页](https://ffmpeg.org/download.html)。

## 模型下载

默认模型为 [NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn)，使用 CC BY-NC-SA 4.0 许可。模型权重通过下载脚本获取，模型标识、版本、链接和缓存位置在 `[model]` 中配置。

```bash
python scripts/download_model.py --print-config
python scripts/download_model.py --cache-dir ./models/cache
```

指定缓存目录时，将同一路径填写到配置：

```toml
[model]
cache_dir = "models/cache"
```

脚本使用固定 revision 下载完整模型快照。后续运行从配置缓存或 Hugging Face 默认缓存加载。模型版本和快照信息随项目记录保存。其它兼容的 CTC 对齐模型可通过 `[model]` 的 `id`、`revision` 与 `url` 配置。

## 制作一首歌

歌词文件示例：

```text
歌《うた》を歌《うた》う
明日《あした》へ歩《ある》こう
```

完整制作：

```bash
./karaoke-local produce video.mp4 "Song" \
  --lyrics-file lyrics.txt --audio audio.m4a \
  --project projects/song --theme not_equal_me \
  --title-text "Song/≠ME"
```

Windows PowerShell 使用 `./karaoke-local.ps1` 执行相同参数。安装到 Python 环境后，也可直接使用 `karaoke` 命令。

截取某个时间段：

```bash
./karaoke-local produce concert.mp4 "Song" \
  --lyrics-file lyrics.txt --audio concert.m4a \
  --project projects/song --trim-start 01:39:01 --trim-end 01:42:42 \
  --theme nogizaka46 --title-text "Song/乃木坂46"
```

时间支持 `秒数`、`分:秒` 和 `时:分:秒`。起止时间同时作用于所选视频与演唱音频；最终编码时截取视频。

继续已有项目：

```bash
./karaoke-local resume projects/song
./karaoke-local resume projects/song --color '#00B379' --force-render
```

### 制作参数

| 参数 | 作用 |
| --- | --- |
| `--lyrics-file` / `--project` | 歌词文件与项目目录 |
| `--audio` | 独立演唱音轨；默认使用视频内的音频 |
| `--trim-start` / `--trim-end` | 截取起止时间；默认使用整段视频 |
| `--theme` | TOML 中的团体主题键名 |
| `--color` | 本次主色，标题默认继承主色 |
| `--color-override` | 单独设置唱色、文字填色、描边和标题颜色，可重复使用 |
| `--title-text` | 右上角标题文字 |
| `--top-y` / `--bottom-y` / `--margin-x` | 两行歌词位置和水平边距 |
| `--canvas-width` / `--canvas-height` | 目标画布尺寸，使用等比缩放与居中补黑 |
| `--off-vocal` | 伴奏音轨，增加伴奏版本 |
| `--translation` | 中文字幕 JSON，增加双语及纯中文版本 |
| `--only` | 指定输出版本，可重复使用 |
| `--force-render` | 强制重新编码 |

### 输出文件

| 名称 | 内容 |
| --- | --- |
| `on_vocal_karaoke.mp4` | 演唱音轨与日文卡拉 OK 字幕 |
| `off_vocal_karaoke.mp4` | 伴奏音轨与日文卡拉 OK 字幕 |
| `on_vocal_karaoke_zh.mp4` | 演唱音轨与日中双语字幕 |
| `on_vocal_zh_only.mp4` | 演唱音轨与中文字幕 |
| `字幕模板-日期.ass` | 逐音时值与正文注音模板 |
| `卡拉OK-日期.ass` | 展开后的动态字幕 |
| `project.karaoke.json` | 歌词、读音、对齐信息及编辑记录 |
| `.karaoke-work/` | 输入副本、准备音频与复用记录 |

提供的音轨、译文与 `--only` 共同决定本次输出集合。CLI 输出包含阶段进度、编码时间和最终 JSON 结果。

## 配置与自定义团体

根目录的 `config.toml` 保存完整默认值。用户文件会逐项覆盖默认配置：

```bash
./karaoke-local --config examples/custom-group.toml produce video.mp4 "Song" \
  --lyrics-file lyrics.txt --project projects/custom
```

同样可以通过 `KARAOKE_CONFIG` 环境变量指定配置。配置中的相对文件路径以该 TOML 所在目录为起点；`bundle:` 路径指向程序内置资源。

新增一个团体：

```toml
[groups.my_group]
label = "My Group"
sung = "#00B379"

[production]
default_theme = "my_group"
```

字体同时配置测宽文件和字幕字体名称：

```toml
[fonts]
japanese_family = "My Japanese Font"
japanese_path = "fonts/my-font.ttf"
chinese_family = "My Chinese Font"
chinese_path = "fonts/my-chinese-font.ttf"
```

完整字段说明见 [配置参考](docs/configuration.md)。

## 浏览器编辑器

```bash
./karaoke-local serve projects/song
```

打开命令显示的地址，在歌词列表选择一句即可预览。时间轴支持拖动整句、句首句尾和逐音共享边界；读音面板可修改假名、罗马音及显示文本，编辑结果写入项目。编辑后可导出 ASS，或再次运行 `resume` 完成成片。

## 已有 ASS 与中文字幕

已有对齐轨迹可通过正式渲染作业直接展开：

```bash
./karaoke-local render-job examples/render-job.json
./karaoke-local specialize source.ass video.mp4 --trim-end 2:00 \
  --theme not_equal_me --audio audio.m4a --title-text "Song/≠ME"
```

`examples/render-job.json` 展示输入、主题、字幕、画布和音轨配置。中文字幕格式见 `examples/translation.json`：每条包含从 0 开始的 `index`、对应日文 `source_text` 和中文 `text`，文件外层使用 `schema_version: 1`、`language: zh-Hans` 和 `lines` 数组，时间由日文轨迹继承。`end_index` 可用于延长某条中文显示到后续句末。

## 自动化与接口

批量制作或外部程序调用以 CLI 为入口：`produce` 执行整套流程，`resume` 继续项目，`render-job` 接受正式 JSON 作业。最终结果写到标准输出，阶段进度写到标准错误；退出码 0 表示成功，1 表示执行失败，2 表示需要处理歌词宽度。外部程序可据此读取结果和输出文件路径。

编辑器提供本地 REST 接口与任务 SSE 事件流。运行 `serve` 后，浏览器会打开带会话参数的地址；接口说明由服务的 `/docs` 页面生成。主要接口如下：

| 接口 | 用途 |
| --- | --- |
| `GET /api/project` | 读取歌词、读音、时间与项目状态 |
| `POST /api/import` | 上传歌词和媒体输入 |
| `POST /api/lines/{line_id}/reading` | 更新一段读音 |
| `POST /api/lines/{line_id}/timing` | 更新逐音时间边界 |
| `POST /api/jobs/align` | 启动整曲对齐 |
| `GET /api/jobs/{job_id}/events` | 获取 SSE 阶段进度 |
| `POST /api/jobs/{job_id}/cancel` | 取消对齐任务 |
| `GET /api/export.ass` | 下载字幕模板 |

API 请求使用启动地址里的会话 token，可作为 `X-Karaoke-Token` 请求头。完整视频制作通过 CLI 或 JSON 作业调用；REST 接口服务于项目编辑和对齐。

自定义模型通过 `[model]` 的 Hugging Face 模型 ID、revision、说明链接、许可和缓存位置配置。当前对齐后端是 Yohane 的 Wav2Vec2 CTC，使用日文罗马音转录，因此模型的 tokenizer 和输出词表应与这些演唱单位匹配。`[runtime].device` 可设置为 `cpu`、`cuda` 或 `mps`。模型配置用于新建项目，已有项目保留记录中的模型版本。

## 打包与上传

```bash
uv build
```

目录结构、工作流程和接口说明见 [架构说明](docs/architecture.md)。源码发布目录可以直接建立 Git 仓库并推送。已初始化仓库时，从添加远程仓库开始执行：

```bash
git init -b main
git add .
git commit -m "Prepare Karaoke Studio release"
git remote add origin https://github.com/YOUR_NAME/karaoke-studio.git
git push -u origin main
```

## 许可

Karaoke Studio 程序使用 MIT 许可。Yohane 使用 MIT；Noto 字体使用 SIL OFL 1.1；前端渲染组件保留各自许可。默认模型使用 CC BY-NC-SA 4.0，FFmpeg 的许可由所选发行构建确定。组件来源、补丁与许可文本见 [第三方说明](THIRD_PARTY_NOTICES.md)。
