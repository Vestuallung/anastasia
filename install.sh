#!/usr/bin/env sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
task_data="$task_root/.runtime"
previous=""
for argument in "$@"; do
    if [ "$previous" = "--data-dir" ]; then task_data="$argument"; fi
    case "$argument" in --data-dir=*) task_data=${argument#*=} ;; esac
    previous="$argument"
done
mkdir -p "$task_data/cache/uv" "$task_data/temp" "$task_data/tools/uv"
task_data=$(CDPATH= cd -- "$task_data" && pwd)
export UV_CACHE_DIR="${UV_CACHE_DIR:-$task_data/cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$task_data/python}"
export UV_TOOL_DIR="${UV_TOOL_DIR:-$task_data/tools/envs}"
export UV_TOOL_BIN_DIR="${UV_TOOL_BIN_DIR:-$task_data/tools/bin}"
export TMPDIR="$task_data/temp"
if command -v uv >/dev/null 2>&1; then
    task_uv=$(command -v uv)
elif [ -x "$task_data/tools/uv/uv" ]; then
    task_uv="$task_data/tools/uv/uv"
else
    task_url=$(sed -n 's/^unix_installer = "\(.*\)"$/\1/p' "$task_root/installer.toml")
    if command -v curl >/dev/null 2>&1; then
        curl -fLsS --retry 3 "$task_url" -o "$task_data/temp/uv-install.sh"
    else
        wget -qO "$task_data/temp/uv-install.sh" "$task_url"
    fi
    UV_INSTALL_DIR="$task_data/tools/uv" UV_NO_MODIFY_PATH=1 sh "$task_data/temp/uv-install.sh"
    task_uv="$task_data/tools/uv/uv"
fi
export KARAOKE_UV="$task_uv"
exec "$task_uv" run --no-project --python 3.12 "$task_root/scripts/bootstrap.py" --data-dir "$task_data" "$@"
