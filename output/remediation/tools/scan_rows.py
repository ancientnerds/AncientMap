"""The marker scan, complete: every flagged row and every unreadable evidence quote.

The first run of this filter printed into a truncated view, so part of its hits were never read. This
writes the whole hit list to a file and prints only the rows that are **not yet in HOLDS.jsonl** - the
ones still to be judged. The filter is a reading aid, never the verdict: it narrows what has to be read.

    ./.venv/Scripts/python.exe output/remediation/logs/scan_rows.py
"""

from __future__ import annotations

import json
import pathlib
import re

LOGS = pathlib.Path(__file__).resolve().parent
ROWS = LOGS / "_write_dry" / "ALL_ROWS.jsonl"
HOLDS = LOGS / "_write_apply" / "HOLDS.jsonl"
OUT = LOGS / "_mark_hits.txt"

#: The reviewer says, in these words, that its own finding does not carry. A hit is a candidate.
REFUTES = re.compile(
    "not shown to be wrong|does not show|no basis|not established|not undercut|is not shown to|"
    "nothing shows|the reason fails|finding fails|no evidence (states|shows|supports)|not warranted|"
    "does not support|not supported by|neither half|both halves fail|contradicted by|"
    "supports the stored|not a correction|less specific|arbitrar|stylistic|does not establish|"
    "may also hold|not the value the sources|does not contradict|not contradicted|"
    "no evidence|not materially|terminus ante quem|same bucket|same era|"
    "does not prove|silent on|unclear|neither source",
    re.IGNORECASE,
)


def read_jsonl(path: pathlib.Path) -> list[dict]:
    """Read a JSON-lines file, naming the line that does not parse."""
    records: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not readable JSON: {exc}") from exc
    return records


def unreadable(quote: str) -> str:
    """An evidence quote that is not a sentence shows no value: a bare property id or raw JSON."""
    stripped = quote.strip()
    if re.fullmatch(r"P\d+", stripped):
        return "the quote is only the property name"
    if stripped.startswith("{") or stripped.startswith("["):
        return "the quote is raw Wikidata JSON"
    if len(stripped) < 25:
        return f"the quote is {len(stripped)} characters long"
    return ""


def main() -> int:
    rows = read_jsonl(ROWS)
    hold_keys = {record["change_key"] for record in read_jsonl(HOLDS)}
    hits: list[str] = []
    fresh: list[str] = []
    for number, row in enumerate(rows, start=1):
        reason = str((row.get("verdict") or {}).get("reason") or "")
        quote = ""
        for item in row.get("evidence") or []:
            if isinstance(item, dict) and item.get("quote"):
                quote = str(item["quote"])
                break
        marks = []
        if REFUTES.search(reason):
            marks.append("reason")
        complaint = unreadable(quote)
        if complaint:
            marks.append(f"quote({complaint})")
        if not marks:
            continue
        line = (
            f"{number:3} {row['site_name'][:30]:31} {row['column']:12} "
            f"{row['old_value']!r} -> {row['new_value']!r} [{'+'.join(marks)}]\n"
            f"     {reason}"
        )
        hits.append(line)
        if row["change_key"] not in hold_keys:
            fresh.append(
                f"{number:3} {row['site_name'][:30]:31} {row['column']:12} "
                f"{row['old_value']!r} -> {row['new_value']!r} [{'+'.join(marks)}]\n"
                f"     {reason[:300]}"
            )
    OUT.write_text(
        f"{len(hits)} Treffer, {len(hits) - len(fresh)} davon bereits entschieden\n\n"
        + "\n".join(hits)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Treffer gesamt: {len(hits)} | bereits entschieden: {len(hits) - len(fresh)} | offen: {len(fresh)}"
    )
    print(f"vollstaendig in {OUT}")
    print()
    print("\n".join(fresh))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
