"""python -m nova [--check | --download-model small|large | --import-config FILE | --list-mics]"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="nova", description="NOVA desktop voice assistant")
    p.add_argument("--check", action="store_true", help="check this PC's setup and exit")
    p.add_argument("--import-config", metavar="FILE", help="load settings from a JSON file (see config.example.json)")
    p.add_argument("--download-model", choices=("small", "large"), help="download a Vosk speech model and exit")
    p.add_argument("--list-mics", action="store_true", help="list microphones and exit")
    args = p.parse_args(argv)

    if args.check:
        from .diagnostics import run_checks

        return run_checks()
    if args.list_mics:
        from .speech.mic import list_input_devices

        names = list(dict.fromkeys(list_input_devices()))
        print("\n".join(names) if names else "No input devices found.")
        return 0
    if args.download_model:
        from .speech.model_download import DownloadError, download_model

        try:
            download_model(args.download_model)
        except DownloadError as e:
            print(e, file=sys.stderr)
            return 1
        return 0
    if args.import_config:
        from .config import SettingsStore
        from .db import Database

        db = Database()
        try:
            SettingsStore(db).import_file(args.import_config)
        except (OSError, ValueError) as e:
            print(f"Could not import settings: {e}", file=sys.stderr)
            return 1
        print("Settings imported.")
        return 0

    from .log import setup_logging
    from .ui.app import run

    setup_logging()
    return run()


if __name__ == "__main__":
    sys.exit(main())
