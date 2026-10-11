# 架构与工作流程

## 流程

逐行歌词 → 正文与注音解析 → 罗马音演唱单位 → 16 kHz 单声道音频 → Yohane 强制对齐 → 原始时值记录 → ASS 模板 → 配置字体测宽 → 连续扫色字幕 → FFmpeg 视频输出。

`produce` 串联完整流程，`resume` 读取保存的制作请求并按输入变化复用步骤。每个项目保存输入副本、歌词结构、模型版本、原始时间和编辑记录。浏览器编辑器通过本地 FastAPI 接口读取及更新项目。

## 源码目录

| 路径 | 内容 |
| --- | --- |
| `src/karaoke_studio/config.py` | TOML 合并、资源路径与运行环境选择 |
| `src/karaoke_studio/config/defaults.toml` | Python 包内置配置 |
| `config.toml` | 源码安装默认配置 |
| `lyrics.py`, `mora.py`, `structure.py` | 正文、假名、罗马音和逐音映射 |
| `yohane_adapter.py`, `yohane_worker.py` | 独立对齐进程和模型加载 |
| `ass.py`, `derived_ass.py` | 时值模板、动态字幕和中文变体 |
| `media_render.py`, `audio_match.py` | 视频输出与外部音轨匹配 |
| `service.py`, `cli.py` | 制作流程和命令入口 |
| `api.py`, `web/` | 浏览器服务与 React 编辑器 |
| `scripts/` | 环境安装和模型下载 |
| `patches/` | 固定 Yohane 版本的运行适配补丁 |
| `schemas/`, `examples/` | JSON 格式定义与使用示例 |
| `tests/` | 文本、时间、配置和渲染验证 |

## Yohane 适配

安装脚本获取配置中的 Yohane revision，然后应用随附补丁。补丁增加 CPU/CUDA/MPS 设备选择，使用 soundfile 读取预处理音频，并把对齐输出转回 CPU 进行时值计算。源码保留上游 MIT 许可。

主程序与对齐环境分别安装，主程序通过 JSON 请求和结果调用工作进程。模型权重存放在 Hugging Face 缓存或用户指定缓存目录，下载脚本读取同一配置。
