"""Owner decision D136 (2026-11-07): the epoch -> period band table, written from the code.

`EPOCH_BANDS.md` is the owner's view of `pipeline.periods.epoch_band`: one row per epoch of
`PERIODS` (169 on 2026-11-07), its conventional span, the band its conventional start falls in,
and every country whose own start (`REGIONAL_STARTS`) puts it in another band. It is generated,
never edited, so the table the owner reads and the function that writes the year cannot drift.

    ./.venv/Scripts/python.exe scripts/remediation/fields/epoch_bands.py table [--out FILE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pipeline import periods as P  # noqa: E402
from pipeline.utils.text import PERIOD_BUCKETS, categorize_period  # noqa: E402

DEFAULT_OUT = REPO / "output" / "remediation" / "fields" / "epoch_bands" / "EPOCH_BANDS.md"


def _year(year: int) -> str:
    return f"{-year} v. Chr." if year < 0 else f"{year} n. Chr."


def other_bands(key: str) -> dict[str, list[str]]:
    """`{band: [countries]}` for the countries whose own start of epoch `key` lies in another band
    than its conventional start; empty for an epoch without regional starts."""
    conventional = P.epoch_band(key, country=None).label
    found: dict[str, list[str]] = {}
    for country in sorted(P.REGIONAL_STARTS.get(key, {})):
        label = P.epoch_band(key, country=country).label
        if label != conventional:
            found.setdefault(label, []).append(country)
    return found


def table() -> str:
    order = {label: i for i, (label, _lo, _hi) in enumerate(PERIOD_BUCKETS)}
    rows = sorted(P.PERIODS.items(), key=lambda item: (item[1][0], item[1][1], item[0]))
    lines = [
        "# Epochen -> Zeitband (D136, aus dem Code erzeugt)",
        "",
        "Erzeugt von `scripts/remediation/fields/epoch_bands.py table` aus "
        "`pipeline.periods.epoch_band` - nicht von Hand ändern.",
        "",
        "Regel: Eine Site mit Epochenwort kommt in das Zeitband, in dem die Epoche **beginnt** "
        "(im Land der Site, wo `REGIONAL_STARTS` einen Landeswert hat, sonst beim üblichen Beginn "
        "aus `PERIODS`). Gespeichert wird die Kante des Bandes (`bucket_edge`, wie bei den 511 "
        "Band-Zeilen vom 04.10.).",
        "",
        f"{len(rows)} Epochen.",
        "",
        "| Epoche | Zeitraum | Zeitband | gespeichertes Jahr | endet in | Länder mit anderem Band |",
        "|---|---|---|---|---|---|",
    ]
    for key, (start, end) in rows:
        band = P.epoch_band(key, country=None)
        others = other_bands(key)
        other_text = "; ".join(
            f"{label}: {', '.join(countries)}"
            for label, countries in sorted(others.items(), key=lambda kv: order[kv[0]])
        )
        lines.append(
            f"| {key} | {_year(start)} – {_year(end)} | {band.label} | {band.edge} | "
            f"{categorize_period(end)} | {other_text} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("table", help="write EPOCH_BANDS.md from pipeline.periods")
    write.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if args.command == "table":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(table(), encoding="utf-8")
        print(f"wrote {args.out} ({len(P.PERIODS)} epochs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
