"""The rows a step is about to write, one block each, with the reviewer's own reason beside them.

This is the reading material for the owner's rule of 2026-09-21: "in steps of a hundred, and after every
hundred a check" - and the first hundred read by hand. The plan rows themselves carry the reviewer's
verdict, so nothing has to be joined: `verdict.reason` is the sentence the reviewer wrote, and
`verdict.applies` is what the writer acts on.

    ./.venv/Scripts/python.exe output/remediation/logs/show_rows.py --from 1 --count 40
"""

from __future__ import annotations

import argparse
import json
import pathlib

LOGS = pathlib.Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(prog="show-rows")
    parser.add_argument("--rows", default=str(LOGS / "_write_dry" / "ALL_ROWS.jsonl"))
    parser.add_argument("--from", dest="first", type=int, default=1)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--reason", type=int, default=260, help="characters of the reviewer's reason")
    args = parser.parse_args()

    rows: list[dict] = []
    for number, line in enumerate(
        pathlib.Path(args.rows).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{args.rows}:{number}: not readable JSON: {exc}") from exc

    print(f"{len(rows)} geplante Zeilen in {args.rows}")
    for number, row in enumerate(rows[args.first - 1 : args.first - 1 + args.count], start=args.first):
        verdict = row.get("verdict") or {}
        quote = ((row.get("evidence") or [{}])[0]).get("quote", "")
        print(
            f"\n{number:3} {row['site_name'][:30]:31} {row['column']:12} "
            f"{row['old_value'][:26]!r} -> {row['new_value'][:26]!r}"
        )
        print(f"    Grund: {str(verdict.get('reason', ''))[: args.reason]}")
        print(f"    Beleg: {quote[:170]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
