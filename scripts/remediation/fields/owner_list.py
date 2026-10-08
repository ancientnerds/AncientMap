"""WD3's and WD4's last step: the owner's list - every open field that stays open, and why.

Owner decisions of 2026-10-01: a field the research cannot source stays empty ("Feld bleibt leer"),
a point without a sourced witness stays ("Recherchieren, sonst behalten") - and the owner gets the
list. This reads the finished WD3 and WD4 runs and their waves, files only, and writes

    <out>/OWNER_LIST.md       per field, per site: what stays open and why (for the owner to read)
    <out>/OWNER_LIST.jsonl    the same rows, one per line (for a later pass)

for every field a question asked, which ended in one of these states:

* `filled` - a `replace` the write plan wrote (its step is accepted with 0 deviations): not listed.
  A later wave of the same lane that planned the decision again finds the value it wrote and
  refuses it as `moved-since-classification: ... holds <that value>`: that is the lane's own write,
  not a refusal - it stays `filled` (measured 2026-10-08: 1,252 written cells were listed `refused`);
* `sourced` - a `keep`: the stored value now has a quote behind it: not listed;
* `rule` - a start a named rule made (evidence `status: RULE`, written by an accepted step): **listed**,
  with the rule's own reason - no source stands behind it, and lane wd5 asks it again;
* `unresolved` - no source could be quoted (the answer, or exhausted after three rounds): **listed**.
  Lane wd5 may have withdrawn the value on that answer (cleared to `Undated`, or restored from the
  journal): the reason then says so;
* `held` - the pages the agents cited could not be read by the checker: **listed**, with the URLs - the
  owner may read them;
* `refused` - a `replace` the write plan refused (a point in another country, a start after the
  period's end, a value that moved since): **listed** with the plan's reason;
* `no-write` - a `replace` whose wave is fully accepted and wrote nothing and refused nothing: listed;
* `pending` - no decision yet, or its wave's step is not accepted: listed apart; the list is final only
  when none is pending (the command prints the count and `--final` refuses while one is).

**The population is what the run asked.** A run classifies every site it can and then puts a part of
that population to the model - WD4 classified 2,636 sites (3,551 questions) and asked 144 of them
(260 questions) over three rounds, measured on its own files 2026-10-04. The list reads each run's
`ROUNDS.jsonl`, which is written when a round is exported and so says what was asked before any
answer existed: a site a run never asked is not an open question of that run, and a site a round did
ask and no answer reached is still `pending`. A run with no rounds (WD3 before the rounds, or a run
that predates the file) is read as its whole classification.

    owner_list.py build [--runs RUN ...] [--waves DIR] [--out DIR] [--final]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
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

from mechanical.lane import FIELDS_ROOTS  # noqa: E402

from fields import classify as C  # noqa: E402
from fields import plan as FP  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402

FILLED, SOURCED = "filled", "sourced"
UNRESOLVED, HELD, REFUSED, NO_WRITE, PENDING, RULE = (
    "unresolved",
    "held",
    "refused",
    "no-write",
    "pending",
    "rule",
)
#: The states the owner reads, in the order the list shows them.
LISTED = (RULE, UNRESOLVED, HELD, REFUSED, NO_WRITE)
OWNER_MD, OWNER_JSONL = "OWNER_LIST.md", "OWNER_LIST.jsonl"
#: The run's own record of what it put to the model, one line per round (a re-ask round is a line
#: of its own). Written when the round is exported, so it exists before any answer does.
ROUNDS_FILE = "ROUNDS.jsonl"
#: The rules whose runs the list can read: both lanes ask the same question under one source family -
#: WD3 (owner decisions of 2026-10-01) and WD4 (2026-10-04, the same plus a named period as a
#: value). They differ in name and stage only, and the stage is in every batch id and write lane, so
#: a WD4 run can never be mistaken for a WD3 one; the list itself reads neither. Lane wd5 (2026-10-08)
#: is WD4's rule aimed at values no source stands behind. WD1 wants two families and is refused.
OWNED_RULES = (R.ONE_FAMILY, R.ONE_FAMILY_PERIOD, R.RECHECK)
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
#: The cells a plan derives from the value it writes: the period label and the point's geometry.
DERIVED_COLUMNS = ("period_name", "geom")


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


def waves_root(stage: str) -> Path:
    """Where a stage's waves live: `output/remediation/fields/<stage>/write`.

    Each stage has its own lane root (`mechanical.lane.FIELDS_ROOTS`), so one list over WD3 and WD4
    reads two directories - `--waves` still names one for every run, which is what it always meant
    for a single-lane list.
    """
    return REPO / "output" / "remediation" / FIELDS_ROOTS[stage]


def read_waves(
    runs: Sequence[Path], waves: Path | None
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str]]:
    """What the write plans did with each (site, field) over every wave of `runs`: `{"written":
    True, "accepted": bool}` for a planned cell (written only once its step is accepted with 0
    deviations) and `{"refused": reason}` for a refusal - and the sites of the waves whose every
    step is accepted (`settled`: whatever they hold no cell or refusal for was not written).

    `waves` is one directory for every run, or `None` for each run's own lane root.
    """
    shown = {_shown(run) for run in runs}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    settled: set[str] = set()
    roots = {waves} if waves is not None else {waves_root(R.read_rule(run).stage) for run in runs}
    for root in sorted(roots):
        if not root.exists():
            continue
        for wave in sorted(p for p in root.iterdir() if (p / FP.WAVE_FILE).exists()):
            _read_wave(wave, shown, out, settled)
    for cell in out.values():
        _settle_refusals(cell)
    return out, settled


def _holds(note: str) -> str | None:
    """What a `moved-since-classification` note says the field holds (`decided about X, holds Y`)."""
    found = re.search(r", holds (.*)\Z", note, re.DOTALL)
    return None if found is None else found.group(1)


def _same_value(column: str, written: str | None, holds: str) -> bool:
    """Whether the value a refusal found (`holds`, as the note prints it: a Python repr, or the
    point as `lat, lon`) is the one an accepted step wrote into `column`."""
    if written is None:
        return False
    if column in ("lat", "lon"):
        point = [part.strip() for part in holds.split(",")]
        index = 0 if column == "lat" else 1
        return len(point) == 2 and float(point[index]) == float(written)
    try:
        return str(ast.literal_eval(holds)) == written
    except (ValueError, SyntaxError):
        return False


def _settle_refusals(cell: dict[str, Any]) -> None:
    """A `moved-since-classification` refusal that found exactly what an accepted step of this
    lane wrote is that step's own write: not a refusal. Any other refusal stands."""
    kept = []
    for column, reason, note in cell.pop("refusals", []):
        holds = _holds(note) if reason == "moved-since-classification" else None
        own = (
            holds is not None
            and cell.get("accepted")
            and _same_value(column, cell.get("values", {}).get(column), holds)
        )
        if not own:
            kept.append(f"{reason}: {note}"[:REASON_CHARS])
    if kept:
        cell["refused"] = kept[-1]


def _read_wave(
    wave: Path,
    shown: set[str],
    out: dict[tuple[str, str], dict[str, Any]],
    settled: set[str],
) -> None:
    """One wave's planned cells and refusals, for the runs of `shown` only."""
    record = FP.read_wave_at(wave)
    if record["run"] not in shown:
        return
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
            cell.setdefault("values", {})[row["column"]] = row["new_value"]
            if row["column"] not in DERIVED_COLUMNS:  # the label and the geom follow the value
                made = [e for e in row["evidence"] if e.get("status") == "RULE"]
                # a later write of the value (lane wd5 replacing a rule's start) overrides it
                cell.update(
                    rule=row["rule"],
                    rule_made=bool(made),
                    rule_note=str(made[0].get("reasoning")) if made else None,
                )
        skipped = step / "SKIPPED.jsonl"
        for row in _rows(skipped) if skipped.exists() else []:
            if row["column"] in FIELD_OF_COLUMN:
                cell = out.setdefault((row["site_id"], FIELD_OF_COLUMN[row["column"]]), {})
                cell.setdefault("refusals", []).append((row["column"], row["reason"], row["note"]))
    if accepted_steps == len(record["steps"]):
        settled |= {site for step_sites in record["steps"] for site in step_sites}


def state_of(
    decision: Mapping[str, Any] | None, cell: Mapping[str, Any] | None, settled: bool
) -> tuple[str, str]:
    """A field's final state and the reason that goes with it."""
    cell = cell or {}
    if cell.get("rule_made") and cell.get("accepted") and cell.get("rule", "").endswith("-replace"):
        return RULE, f"made by a rule, found in no source: {cell['rule_note']}"
    if decision is None:
        return PENDING, "no decision yet: the answers of this field are not imported"
    verdict = decision["decision"]
    if verdict == "keep":
        return SOURCED, str(decision["reasoning"])
    if verdict == "unresolved":
        if cell.get("written") and cell.get("accepted"):  # lane wd5 withdrew the value
            return UNRESOLVED, (
                f"no source; the value was withdrawn ({cell['rule']}): {decision['reasoning']}"
            )
        return UNRESOLVED, str(decision["reasoning"])
    if verdict == POP.HELD:
        return HELD, str(decision["reasoning"])
    if verdict != "replace":
        raise OwnerListError(f"{decision['site_id']}/{decision['field']}: decision {verdict!r}")
    if cell.get("refused"):
        return REFUSED, str(cell["refused"])
    if cell.get("written"):
        if cell["accepted"]:
            return FILLED, str(decision["reasoning"])
        return PENDING, "the write is planned but its step is not accepted yet"
    if settled:
        return NO_WRITE, "its wave is accepted and holds no cell and no refusal for this field"
    return PENDING, "decided, not written yet: its wave is not planned or not accepted"


def asked_by_rounds(run: Path) -> set[tuple[str, str]] | None:
    """The `(site, field)` pairs this run's rounds put to the model - `None` when it has no rounds,
    and then the whole classification is the run's population.

    A run classifies every site it can and then asks the model a part of that population: WD4
    classified 2,636 sites (3,551 questions) and put **144 sites / 260 questions** to the model over
    three rounds, measured on its own files 2026-10-04; every one of its 260 decisions lies inside
    that set. The list is about the questions a run asked - a site it never asked is not an open
    question of that run, it is not its work - and the rounds say what was asked *before* any answer
    existed, so this can never hide a question the run did put: a site a round asked and no answer
    reached is still `pending`.
    """
    path = run / ROUNDS_FILE
    if not path.exists():
        return None
    return {
        (site, field)
        for entry in _rows(path)
        for site, fields in entry.get("fields", {}).items()
        for field in fields
    }


def build(runs: Sequence[Path], waves: Path | None) -> dict[str, Any]:
    """The rows of the list and its counts, from the runs' files."""
    for run in runs:
        if R.read_rule(run) not in OWNED_RULES:
            raise OwnerListError(
                f"{run} is not a WD3, WD4 or wd5 run (its RUN.json pins {R.read_rule(run).name!r})"
            )
    cells, settled = read_waves(runs, waves)
    rows: list[dict[str, Any]] = []
    counts: dict[str, Counter[str]] = {field: Counter() for field in C.FIELDS}
    classified = asked = 0
    for run in runs:
        decisions = (
            {(d["site_id"], d["field"]): d for d in _rows(run / "DECISIONS.jsonl")}
            if (run / "DECISIONS.jsonl").exists()
            else {}
        )
        asked_here = asked_by_rounds(run)
        for line in _rows(run / C.CLASSIFIED_FILE):
            site = line["site_id"]
            for field in line["asked"]:
                classified += 1
                if asked_here is not None:
                    if (site, field) not in asked_here:
                        continue
                    asked += 1
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
    return {
        "rows": rows,
        "counts": {f: dict(sorted(c.items())) for f, c in counts.items()},
        "population": {"classified": classified, "asked": asked},
    }


# ------------------------------------------------------------------------------ the writing
STATE_TITLE = {
    RULE: "a start a rule made, found in no source",
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
    population = result["population"]
    out = [
        "# Owner list (lanes WD3, WD4 and wd5): the fields that stay open",
        "",
        f"Built {datetime.now(UTC).replace(microsecond=0).isoformat()} by "
        "`scripts/remediation/fields/owner_list.py` from "
        + ", ".join(f"`{_shown(run)}`" for run in runs)
        + ". Owner decisions of 2026-10-01: a field no source supports stays empty, a point no source "
        "supports stays where it is - this is the list of both.",
        "",
        f"**{population['asked']} of {population['classified']} classified questions** were put to the "
        "model, and this list is about those: a site a run never asked is not an open question of that "
        "run (each run's rounds say what it asked, in `ROUNDS.jsonl`).",
        "",
        "| field | asked | filled | sourced (kept) | rule | no source | unreadable pages | refused | "
        "no write | pending |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for field in C.FIELDS:
        c = counts[field]
        out.append(
            f"| {field} | {sum(c.values())} | {c.get(FILLED, 0)} | {c.get(SOURCED, 0)} | "
            f"{c.get(RULE, 0)} | {c.get(UNRESOLVED, 0)} | {c.get(HELD, 0)} | {c.get(REFUSED, 0)} | "
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


def write(runs: Sequence[Path], waves: Path | None, out: Path, *, final: bool) -> dict[str, Any]:
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
    return {
        "listed": len(result["rows"]),
        "pending": pending,
        "counts": result["counts"],
        "population": result["population"],
    }


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
        "--waves",
        type=Path,
        default=None,
        help="this directory for every run; default: each run's own lane (fields/<stage>/write)",
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
