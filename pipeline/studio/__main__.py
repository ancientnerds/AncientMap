"""CLI entry: `python -m pipeline.studio <area> <command> ...` (see the package docstring)."""

from __future__ import annotations

import argparse
import logging
import sys

from pipeline.studio import cli_episode, cli_paper, config, doctor
from pipeline.studio.errors import StudioError


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m pipeline.studio")
    sub = ap.add_subparsers(dest="area", required=True)
    cli_paper.register(sub)
    cli_episode.register(sub)
    doctor.register(sub)
    return ap


def main(argv: list[str] | None = None) -> int:
    # The JSON the commands print is UTF-8 whatever the console code page: Claude Code's Bash
    # tool on Windows gives Python a cp1252 pipe, where 'Şanlıurfa' would not encode.
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs every request URL at INFO, and the Mapbox Static API (access_token=) and the
    # Europeana connector (wskey=) carry their credential in it; stderr goes into the model's
    # transcript (pipeline/lyra/orchestrator.py silences httpx for the same reason).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    config.load_env()
    try:
        return args.func(args)
    except StudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
