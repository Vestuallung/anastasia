# Contributing

Use Python 3.12 and Node.js 22 for development. Run `uv sync --all-extras`, then `npm --prefix web ci`. Backend modules live under `src/karaoke_studio`; frontend components live under `web/src`.

Describe the input or action that triggers the change, the resulting behavior, and the checks performed. Configuration additions should include a default value in `src/karaoke_studio/config/defaults.toml`, a matching root `config.toml` entry and a description in `docs/configuration.md`.

Run the relevant Python tests and rebuild the frontend when its source changes. `uv build` creates the Python wheel and source archive; the wheel includes the browser editor, fonts, schemas and default TOML.
