"""Load a selected configuration before importing the CLI."""

from __future__ import annotations

import os
import sys


def main() -> None:
    args = sys.argv[1:]
    for index, value in enumerate(args):
        if value == "--config":
            if index + 1 >= len(args):
                raise SystemExit("--config requires a TOML path")
            os.environ["KARAOKE_CONFIG"] = args[index + 1]
            del sys.argv[index + 1 : index + 3]
            break
        if value.startswith("--config="):
            os.environ["KARAOKE_CONFIG"] = value.split("=", 1)[1]
            del sys.argv[index + 1]
            break
    from .cli import app

    app()


if __name__ == "__main__":
    main()
