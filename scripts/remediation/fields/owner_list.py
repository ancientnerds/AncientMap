"""WD3's and WD4's last step: the owner's list - every open field that stays open, and why.

Owner decisions of 2026-10-01: a field the research cannot source stays empty ("Feld bleibt leer"),
a point without a sourced witness stays ("Recherchieren, sonst behalten") - and the owner gets the
list. This reads the finished WD3 and WD4 runs and their waves, files only, and writes

    <out>/OWNER_LIST.md       per field, per site: what stays open and why (for the owner to read)
    <out>/OWNER_LIST.jsonl    the same rows, one per line (for a later pass)

for every field a question asked, which ended in one of these states:

* `filled` - a `replace` the write plan wrote (its step is accepted with 0 deviations): not listed;
* `sourced` - a `keep`: the stored value now has a quote behind it: not listed;
* `unresolved` - no source could be quoted (the answer, or exhausted after three rounds): **listed**;
* `held` - the pages the agents cited could not be read by the checker: **listed**, with the URLs - the
  owner may read them;
* `refused` - a `replace` the write plan refused (a point in another country, a start after the
  period's end, a value that moved since): **listed** with the plan's reason;
* `no-write` - a `replace` whose wave is fully accepted and wrote nothing and refused nothing: listed;
* `pending` - no decision yet, or its wave's step is not accepted: listed apart; the list is final only
  when none is pending (the command prints the count and `--final` refuses while one is).

    owner_list.py build [--runs RUN ...] [--waves DIR] [--out DIR] [--final]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import classify as C  # noqa: E402
from fields import plan as FP  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402

FILLED, SOURCED = "filled", "sourced"
UNRESOLVED, HELD, REFUSED, NO_WRITE, PENDING = (
    "unresolved",
    "held",
    "refused",
    "no-write",
    "pending",
)
#: The states the owner reads, in the order the list shows them.
LISTED = (UNRESOLVED, HELD, REFUSED, NO_WRITE)
OWNER_MD, OWNER_JSONL = "OWNER_LIST.md", "OWNER_LIST.jsonl"
#: The rules whose runs the list can read: both lanes ask the same question under one source family -
#: WD3 (owner decisions of 2026-10-01) and WD4 (2026-10-04, the same plus a named period as a
#: value). They differ in name and stage only, and the stage is in every batch id and write lane, so
#: a WD4 run can never be mistaken for a WD3 one; the list itself reads neither. WD1 wants two
#: families and is refused.
OWNED_RULES = (R.ONE_FAMILY, R.ONE_FAMILY_PERIOD)
DEFAULT_RUNS = tuple(POP.FIELDS_DIR / name for name in ("wd3-pilot", "wd3"))
REASON_CHARS = 500
#: The columns a field is written through (a point is three cells).
COLUMNS = {
    "coordinates": ("lat", "lon", "geom"),
    "period_start": ("period_start", "period_name"),
    "site_type": ("site_type",),
    "source_url": ("source_url",),
}
FIELD_OF_COLUMN = {column: field for field, columns in COLUMNS.items() for column in columns}


class OwnerListError(RuntimeError):
    """The list cannot be built from these files."""


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        # the resolved path, never the path as spelled: a run reached through a junction or a
        # `..` component is the same run, and a wave's `run` is compared against this (2026-10-04)
        return path.resolve().as_posix()


def read_waves(
    runs: Sequence[Path], waves: Path
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str]]:
    """What the write plans did with each (site, field) over every wave of `runs`: `{"written":
    True, "accepted": bool}` for a planned cell (written only once its step is accepted with 0
    deviations) and `{"refused": reason}` for a refusal - and the sites of the waves whose every
    step is accepted (`settled`: whatever they hold no cell or refusal for was not written)."""
    shown = {_shown(run) for run in runs}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    settled: set[str] = set()
    if not waves.exists():
        return out, settled
    for wave in sorted(p for p in waves.iterdir() if (p / FP.WAVE_FILE).exists()):
        record = FP.read_wave_at(wave)
        if record["run"] not in shown:
            continue
        accepted_steps = 0
        for number in range(1, len(record["steps"]) + 1):
            step = wave / f"s{number:03d}"
            accepted_path = step / FP.ACCEPTED_FILE
            accepted = (
                accepted_path.exists()
                and json.loads(accepted_path.read_text(encoding="utf-8"))["deviations"] == 0
            )
            accepted_steps += accepted
            planned = step / "PLAN.jsonl"
            for row in _rows(planned) if planned.exists() else []:
                cell = out.setdefault((row["site_id"], FIELD_OF_COLUMN[row["column"]]), {})
                cell.update(written=True, accepted=accepted)
            skipped = step / "SKIPPED.jsonl"
            for row in _rows(skipped) if skipped.exists() else []:
                if row["column"] in FIELD_OF_COLUMN:
                    cell = out.setdefault((row["site_id"], FIELD_OF_COLUMN[row["column"]]), {})
                    cell.update(refused=f"{row['reason']}: {row['note']}"[:REASON_CHARS])
        if accepted_steps == len(record["steps"]):
            settled |= {site for step_sites in record["steps"] for site in step_sites}
    return out, settled


def state_of(
    decision: Mapping[str, Any] | None, cell: Mapping[str, Any] | None, settled: bool
) -> tuple[str, str]:
    """A field's final state and the reason that goes with it."""
    if decision is None:
        return PENDING, "no decision yet: the answers of this field are not imported"
    verdict = decision["decision"]
    if verdict == "keep":
        return SOURCED, str(decision["reasoning"])
    if verdict == "unresolved":
        return UNRESOLVED, str(decision["reasoning"])
    if verdict == POP.HELD:
        return HELD, str(decision["reasoning"])
    if verdict != "replace":
        raise OwnerListError(f"{decision['site_id']}/{decision['field']}: decision {verdict!r}")
    cell = cell or {}
    if cell.get("refused"):
        return REFUSED, str(cell["refused"])
    if cell.get("written"):
        if cell["accepted"]:
            return FILLED, str(decision["reasoning"])
        return PENDING, "the write is planned but its step is not accepted yet"
    if settled:
        return NO_WRITE, "its wave is accepted and holds no cell and no refusal for this field"
    return PENDING, "decided, not written yet: its wave is not planned or not accepted"


def build(runs: Sequence[Path], waves: Path) -> dict[str, Any]:
    """The rows of the list and its counts, from the runs' files."""
    for run in runs:
        if R.read_rule(run) not in OWNED_RULES:
            raise OwnerListError(
                f"{run} is not a WD3 or WD4 run (its RUN.json pins "
                f"{R.read_rule(run).name!r})"
            )
    cells, settled = read_waves(runs, waves)
    rows: list[dict[str, Any]] = []
    counts: dict[str, Counter[str]] = {field: Counter() for field in C.FIELDS}
    for run in runs:
        decisions = (
            {(d["site_id"], d["field"]): d for d in _rows(run / "DECISIONS.jsonl")}
            if (run / "DECISIONS.jsonl").exists()
            else {}
        )
        for line in _rows(run / C.CLASSIFIED_FILE):
            for field in line["asked"]:
                site = line["site_id"]
                decision = decisions.get((site, field))
                state, reason = state_of(decision, cells.get((site, field)), site in settled)
                counts[field][state] += 1
                if state == SOURCED or state == FILLED:
                    continue
                rows.append(
                    {
                        "site_id": site,
                        "name": line["name"],
                        "country": line["country"],
                        "field": field,
                        "state": state,
                        "open_because": line["open"][field]["why"],
                        "stored": line["fields"][field]["stored"],
                        "reason": reason,
                        "asked": None if decision is None else decision["asked"],
                    }
                )
    rows.sort(
        key=lambda r: (C.FIELDS.index(r["field"]), str(r["country"]), r["name"], r["site_id"])
    )
    return {"rows": rows, "counts": {f: dict(sorted(c.items())) for f, c in counts.items()}}


# ------------------------------------------------------------------------------ the writing
STATE_TITLE = {
    UNRESOLVED: "no source could be found",
    HELD: "the pages the agents cited could not be read by the checker",
    REFUSED: "a sourced value the write plan refused",
    NO_WRITE: "decided, nothing written",
    PENDING: "not finished yet",
}
FIELD_TITLE = {
    "coordinates": "coordinates (the stored point stays)",
    "period_start": "period_start (the field stays as it is)",
    "site_type": "site_type (the field stays as it is)",
    "source_url": "source_url (the field stays as it is)",
}


def _cell(text: Any) -> str:
    return str(text if text is not None else "-").replace("|", "/").replace("\n", " ")


def render(result: Mapping[str, Any], runs: Sequence[Path]) -> str:
    counts = result["counts"]
    out = [
        "# Owner list (lanes WD3 and WD4): the fields that stay open",
        "",
        f"Built {datetime.now(UTC).replace(microsecond=0).isoformat()} by "
        "`scripts/remediation/fields/owner_list.py` from "
        + ", ".join(f"`{_shown(run)}`" for run in runs)
        + ". Owner decisions of 2026-10-01: a field no source supports stays empty, a point no source "
        "supports stays where it is - this is the list of both.",
        "",
        "| field | asked | filled | sourced (kept) | no source | unreadable pages | refused | "
        "no write | pending |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for field in C.FIELDS:
        c = counts[field]
        out.append(
            f"| {field} | {sum(c.values())} | {c.get(FILLED, 0)} | {c.get(SOURCED, 0)} | "
            f"{c.get(UNRESOLVED, 0)} | {c.get(HELD, 0)} | {c.get(REFUSED, 0)} | "
            f"{c.get(NO_WRITE, 0)} | {c.get(PENDING, 0)} |"
        )
    for field in C.FIELDS:
        mine = [r for r in result["rows"] if r["field"] == field]
        if not mine:
            continue
        out += ["", f"## {FIELD_TITLE[field]}: {len(mine)}", ""]
        for state in (*LISTED, PENDING):
            part = [r for r in mine if r["state"] == state]
            if not part:
                continue
            out += [
                f"### {STATE_TITLE[state]}: {len(part)}",
                "",
                "| site | country | stored | open because | what was found |",
                "|---|---|---|---|---|",
            ]
            out += [
                f"| {_cell(r['name'])} (`{r['site_id']}`) | {_cell(r['country'])} | "
                f"{_cell(r['stored'])} | {r['open_because']} | "
                f"{_cell(str(r['reason'])[:REASON_CHARS])} |"
                for r in part
            ]
            out.append("")
    return "\n".join(out) + "\n"


def write(runs: Sequence[Path], waves: Path, out: Path, *, final: bool) -> dict[str, Any]:
    result = build(runs, waves)
    pending = sum(1 for r in result["rows"] if r["state"] == PENDING)
    if final and pending:
        raise OwnerListError(f"{pending} field(s) are pending: the list is final only without them")
    out.mkdir(parents=True, exist_ok=True)
    (out / OWNER_MD).write_text(render(result, runs), encoding="utf-8", newline="\n")
    (out / OWNER_JSONL).write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in result["rows"]),
        encoding="utf-8",
        newline="\n",
    )
    return {"listed": len(result["rows"]), "pending": pending, "counts": result["counts"]}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("build")
    cmd.add_argument("--runs", type=Path, nargs="+", default=list(DEFAULT_RUNS))
    cmd.add_argument(
        "--waves", type=Path, default=REPO / "output" / "remediation" / "fields" / "wd3" / "write"
    )
    cmd.add_argument("--out", type=Path, default=POP.DEFAULT_OUT)
    cmd.add_argument("--final", action="store_true", help="refuse while a field is pending")
    args = parser.parse_args(argv)
    try:
        result = write(args.runs, args.waves, args.out, final=args.final)
    except (OwnerListError, R.RuleError, FP.PlanError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
