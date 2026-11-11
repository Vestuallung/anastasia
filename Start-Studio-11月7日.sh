#!/usr/bin/env sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$task_root"
if [ ! -f .runtime/environment.sh ]; then
    sh ./install.sh --skip-model "$@"
fi
exec sh ./karaoke-local desktop --port 0 --open
