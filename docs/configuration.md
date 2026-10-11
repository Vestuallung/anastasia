# 配置参考

应用从内置默认配置读取设置，再合并 `--config`、`KARAOKE_CONFIG` 或仓库根目录 `config.toml`。用户配置逐项覆盖默认值。命令行的单次颜色、位置和主题参数在本次任务中优先生效。

| 分组 | 字段 | 内容 |
| --- | --- | --- |
| `tools` | `ffmpeg`, `ffprobe` | 可执行程序名或路径，默认从 PATH 解析 |
| `runtime` | `yohane_python`, `device` | 对齐解释器与推理设备；解释器自动选择 `.runtime/align`，设备默认 `cpu` |
| `model` | `id`, `revision`, `url`, `license`, `cache_dir` | 模型标识、固定版本、说明链接、许可与缓存目录 |
| `yohane` | `repository`, `revision`, `packages` | 安装脚本使用的上游仓库、版本和依赖清单 |
| `fonts` | `japanese_family`, `japanese_path`, `chinese_family`, `chinese_path` | 字幕字体名称及对应测宽字体文件 |
| `appearance` | `main_size`, `width_limit`, `ruby_ratio`, `ruby_rise_ratio` | 正文字号、最大宽度、注音大小比例和抬升比例 |
| `appearance` | `bold`, `outline` | 日文加粗与描边宽度 |
| `appearance` | `title_size`, `title_y`, `title_outline` | 标题字号、垂直坐标与描边 |
| `appearance` | `chinese_size`, `chinese_outline`, `chinese_glow`, `chinese_blur` | 中文字号、文字边线、团体色柔光与模糊 |
| `layout` | `canvas_width`, `canvas_height`, `margin_x`, `top_y`, `bottom_y` | 逻辑画布、水平边距与两行歌词中心 |
| `production` | `default_theme` | 默认团体主题键名 |
| `encoder` | `video_codec`, `preset`, `crf`, `pixel_format`, `audio_codec`, `audio_bitrate`, `movflags` | FFmpeg 编码设置 |
| `groups.NAME` | `label`, `sung` | 团体显示名与主色 |
| `groups.NAME` | `unsung_fill`, `unsung_outline`, `sung_outline`, `title_fill`, `title_outline` | 文字、描边与标题配色 |
| `groups.NAME` | `light`, `mid` | 扩展颜色槽位，供后续样式使用 |

颜色使用 `#RRGGBB`。团体最小配置为 `label` 与 `sung`，文字默认白色，未唱边线默认黑色，已唱边线默认白色。标题默认继承 `sung`。

环境变量 `KARAOKE_FFMPEG`、`KARAOKE_FFPROBE`、`KARAOKE_YOHANE_PYTHON` 可覆盖工具路径。`KARAOKE_HOME` 指定源码安装的运行根目录。设置通过启动时加载；重新运行命令或浏览器服务会应用更新。

模型配置用于新建项目。已有项目保留其模型 ID 与 revision；制作参数和对齐记录随项目保存。

## 安装配置

`installer.toml` 保存 uv、Windows 便携式工具、macOS Homebrew 和 Linux 系统包的下载地址及包名。macOS 使用带 libass 的 `ffmpeg-full`，脚本读取其安装前缀。Windows 与 Linux 默认 CPU 环境从 PyTorch CPU 索引安装 torch、torchaudio，其余包按常规索引安装。

`install.ps1 -DataDir PATH` 或 `sh install.sh --data-dir PATH` 指定主环境、对齐环境、Python、缓存和模型所在目录。安装结果记录到项目 `.runtime/environment.sh` 与 `environment.ps1`；启动入口自动读取。使用 `-Config FILE` 或 `--config FILE` 可在安装时选择应用配置。
