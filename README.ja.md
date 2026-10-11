<div align="center">

# ♬ anastasia

**Karaoke Studio**

歌詞から、歌に合わせて色づく字幕へ。

[![CI](https://github.com/Vestuallung/anastasia/actions/workflows/ci.yml/badge.svg)](https://github.com/Vestuallung/anastasia/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Platforms](https://img.shields.io/badge/Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-6366F1)
![License](https://img.shields.io/badge/Code-MIT-22C55E)
![Demo](https://img.shields.io/badge/Status-Demo-F59E0B)

[简体中文](README.zh_CN.md) · [English](README.en.md) · [日本語](README.ja.md)

</div>

---

**動画 + 歌入り音声 + 1 行ごとの歌詞**から、ふりがな・連続した色変化・グループ別の配色を備えた日本語カラオケ動画を作成します。CLI で制作工程を実行し、ブラウザーのタイムラインで読み方や歌唱タイミングを調整できます。

## 歌詞から動画へ

**歌詞とふりがな → 音声の準備 → Yohane による時間合わせ → ASS 字幕 → FFmpeg による動画出力**

| 機能 | 内容 |
| --- | --- |
| 歌詞の取り込み | TXT・LRC・ASS、`漢字《かな》` 形式の読み指定、元の改行・空白・句読点の保持 |
| 時間合わせ | 歌入り音声とローマ字の歌詞から単位ごとの時刻を求め、元の結果を保存 |
| カラオケ字幕 | 本文とふりがなの連続した色変化、標準 96px、実際のフォントによる幅計測 |
| グループ配色 | 乃木坂46・日向坂46・櫻坂46・欅坂46・≠ME と独自のグループ |
| 映像処理 | 開始・終了時刻による切り出し、別音声、縦横比を保った拡大縮小と余白 |
| 出力形式 | 歌入り・伴奏・日中併記・中国語字幕のみの動画 |
| 編集画面 | 波形、音単位のドラッグ、行の移動、読みの編集、元に戻す・やり直す |
| 自動化 | 1 コマンドでの制作、工程の再利用、JSON ジョブ、結果と進捗の出力 |

## 1 コマンドでインストール

GitHub の **Code → Download ZIP** を選び、展開したプロジェクトフォルダーでターミナルを開きます。`git clone https://github.com/Vestuallung/anastasia.git` でも取得できます。

### Windows · x64

プロジェクトを希望するドライブ（例：`D:\anastasia`）に置き、そのフォルダーで PowerShell を開きます。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

スクリプトが uv・Python 3.12・ポータブル版 Git と FFmpeg を準備し、アプリと時間合わせ用の環境を作成して、設定されたモデルをダウンロードします。標準のデータ保存先はプロジェクトの `.runtime` です。ツールとキャッシュも指定したデータフォルダーに保存されます。

保存先を指定する場合：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DataDir D:\anastasia-data
```

### macOS · Apple Silicon / Intel

展開したプロジェクトフォルダーでターミナルを開きます。

```bash
sh install.sh
```

uv と Python 3.12 を準備し、Homebrew で Git と libass 対応の `ffmpeg-full` をインストールした後、実行環境とモデルを用意します。Homebrew の初回導入やシステムパッケージの導入時は、ターミナルに表示される認証手順に従ってください。アプリのデータは標準で `.runtime` に保存されます。

```bash
sh install.sh --data-dir "$HOME/anastasia-data"
```

### Linux · Ubuntu / Debian

プロジェクトフォルダーでターミナルを開きます。

```bash
sh install.sh
```

uv と Python 3.12 を準備し、`apt-get` で Git と FFmpeg を導入して、実行環境とモデルを用意します。システムパッケージの導入には `sudo` を使い、導入済みの依存関係は再利用します。`dnf`・`pacman`・`zypper` も検出し、各ディストリビューションの Git と FFmpeg パッケージを利用します。

```bash
sh install.sh --data-dir "$HOME/anastasia-data"
```

### オプションと保存先

| 目的 | Windows | macOS / Linux |
| --- | --- | --- |
| 環境とモデルをまとめて導入 | `install.ps1` | `sh install.sh` |
| 既存 ASS の編集・動画出力 | `install.ps1 -MainOnly` | `sh install.sh --main-only` |
| 環境を導入し、モデルを後で取得 | `install.ps1 -SkipModel` | `sh install.sh --skip-model` |
| データ保存先 | `-DataDir PATH` | `--data-dir PATH` |
| アプリの設定ファイル | `-Config FILE` | `--config FILE` |
| 導入手順の確認 | `-Plan` | `--plan` |

上記の OS ごとの起動方法でオプションを指定します。インストーラーが実行環境の場所を記録し、`karaoke-local` が起動時に読み込みます。

| データフォルダー内のパス | 内容 |
| --- | --- |
| `main/`・`align/` | アプリと時間合わせ用の環境 |
| `python/`・`tools/` | Python とポータブルツール |
| `cache/uv/`・`cache/huggingface/` | 依存関係とモデルのキャッシュ |
| `temp/`・`downloads/` | 一時ファイルと取得したアーカイブ |
| `yohane/` | バージョン固定の時間合わせバックエンド |

モデルはダウンロードスクリプトで取得します。ソース配布物には、アプリ、ビルド済みの編集画面、フォント、ダウンロード設定を含みます。初回の導入時間は通信速度と PyTorch・モデルの取得時間によって変わります。

## 最初の曲を作る

`lyrics.txt` の例：

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

切り出しには `--trim-start 01:39:01 --trim-end 01:42:42` を使います。時刻は秒数・`分:秒`・`時:分:秒` に対応します。伴奏音声は `--off-vocal backing.m4a`、中国語訳は `--translation translation.json` で指定します。全オプションは `produce --help` で確認できます。

続きの制作・配色の変更・編集画面：

```bash
./karaoke-local resume projects/song
./karaoke-local resume projects/song --color "#00B379" --force-render
./karaoke-local serve projects/song
```

Windows では `./karaoke-local` を `.\karaoke-local.ps1` に置き換えます。`serve` は編集画面を開き、`resume` は入力の変更に応じて工程を再利用します。幅を超えた歌詞は対象行をまとめて表示するので、改行を調整して続行できます。

| 出力 | 内容 |
| --- | --- |
| `on_vocal_karaoke.mp4` | 日本語・歌入り版 |
| `off_vocal_karaoke.mp4` | 日本語・伴奏版 |
| `on_vocal_karaoke_zh.mp4` | 日本語・中国語併記の歌入り版 |
| `on_vocal_zh_only.mp4` | 中国語字幕のみの歌入り版 |
| `project.karaoke.json` と ASS | 続けて編集できるプロジェクトと字幕 |

## 設定・グループ・モデル

`config.toml` を編集するか、実行時に `--config custom.toml` を指定します。相対パスは TOML ファイルのあるフォルダーを基準に解決されます。

```toml
[groups.my_group]
label = "My Group"
sung = "#00B379"

[production]
default_theme = "my_group"
```

| 設定 | 用途 |
| --- | --- |
| `[tools]` | FFmpeg・ffprobe の実行ファイル名とパス |
| `[fonts]` / `[appearance]` / `[layout]` | フォント、サイズ、幅計測、配置、縁取り |
| `[groups.*]` / `[encoder]` | グループ配色と映像・音声のエンコード |
| `[model]` | モデル ID・revision・URL・ライセンス・キャッシュ |
| `[runtime]` | 時間合わせ用 Python と `cpu` / `cuda` / `mps` |
| `installer.toml` | uv・ツールの取得元と CPU 版 PyTorch の配布元 |

標準モデル：[NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn)。独自モデルには、日本語のローマ字歌唱単位に適合する **Wav2Vec2 CTC** の tokenizer と出力語彙を使います。モデル設定は新規プロジェクトに適用され、既存プロジェクトは記録済みのモデルバージョンを保持します。標準インストールは CPU 用の環境を準備します。デバイス変更時は対応する PyTorch ビルドを設定してください。

全項目は [設定リファレンス](docs/configuration.md) にあります。`scripts/download_model.py` でモデルを個別に取得できます。JSON ジョブと中国語訳の形式は [examples](examples/) を参照してください。

## 自動化と API

`produce` は全工程、`resume` は続きの制作、`render-job` は JSON ジョブを実行します。最終結果の JSON は標準出力、進捗は標準エラー出力へ送ります。終了コードは `0` が成功、`1` が実行エラー、`2` が歌詞の幅超過です。

```bash
./karaoke-local render-job examples/render-job.json
```

編集画面は FastAPI REST と SSE を利用します。`serve` の起動後、サービスの `/docs` でリクエスト形式を確認できます。起動 URL の token は `X-Karaoke-Token` ヘッダーとして送信できます。

| エンドポイント | 用途 |
| --- | --- |
| `GET /api/project`・`POST /api/import` | プロジェクトの取得・取り込み |
| `POST /api/lines/{line_id}/reading`・`.../timing` | 読み方・時刻の調整 |
| `POST /api/jobs/align` | 曲全体の時間合わせ |
| `GET /api/jobs/{job_id}/events`・`POST .../cancel` | 進捗・キャンセル |
| `GET /api/export.ass` | 字幕テンプレートの出力 |

## 技術とライセンス

Python 3.12 · Typer · Pydantic · FastAPI · React / TypeScript / Vite · JASSUB · fugashi / UniDic-lite / pykakasi · Yohane / PyTorch / Transformers · Pillow · FFmpeg / libass。

アプリは **MIT**、Noto フォントは **SIL OFL 1.1**、標準モデルは **CC BY-NC-SA 4.0** です。コンポーネントの取得元とライセンスは [第三者ライセンス](THIRD_PARTY_NOTICES.md) に記載しています。
