# Third-party notices

Karaoke Studio application code is distributed under the MIT License.

## Yohane

[Yohane](https://github.com/Japan7/yohane) is MIT licensed. Setup fetches the revision specified in `config.toml` and applies `patches/yohane-runtime.patch`. The patch adapts audio loading and device selection for this runtime. The fetched checkout retains its upstream LICENSE and authorship.

## Alignment model

[NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn) uses CC BY-NC-SA 4.0. Model downloads are managed by `scripts/download_model.py`, which displays the model URL, license and revision and saves the snapshot in the configured cache. See the linked model card for its terms.

## Fonts

The bundled Noto Sans JP variable font and Noto Sans CJK JP regular font originate from the [Google Fonts](https://github.com/google/fonts) and [Noto CJK](https://github.com/notofonts/noto-cjk) projects. They use the SIL Open Font License 1.1, included at `src/karaoke_studio/assets/fonts/OFL.txt`.

## Browser editor

The editor uses React, Vite, Lucide React and JASSUB. JASSUB includes libass and associated WebAssembly components under their respective licenses. The supplied license text is `src/karaoke_studio/assets/licenses/JASSUB-LICENSE.txt`; upstream source is [ThaUnknown/jassub](https://github.com/ThaUnknown/jassub). Frontend versions are recorded in `web/package-lock.json`.

## Python dependencies

Python dependency versions and source locations are recorded in `uv.lock`; direct dependencies are listed in `pyproject.toml`. Runtime dependencies retain the license supplied by each package. The separate alignment dependencies are specified in `[yohane].packages`.

## FFmpeg

FFmpeg is supplied through the user's installed distribution. Its license follows that build's selected components. Source and license information are available at [FFmpeg](https://ffmpeg.org/legal.html).
