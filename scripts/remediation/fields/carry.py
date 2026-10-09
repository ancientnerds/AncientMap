"""Lane wd5: the existing decisions of the refused points, carried into the run (D19, map step 10).

Owner decision D19 of 2026-10-08: a point within about 2 km off its country's coast counts as in the
country, and the 23 points the country guard refused are written. Those 23 are not a new question.
Earlier lanes already decided each of them with a quote (a `replace` of the stored point) and the
write plan refused it as `country-changes`, so the decision stands and only the plan's country check
is run again - now with the coast tolerance (`bcases.classify.COAST_KM`) and the Cyprus equivalence
(master plan X3). Asking an agent the same question again would only risk a different answer to a
question that was answered with a quote.

    carry.py carry-points --run RUN       CARRIED.jsonl and CARRIED.json beside CLASSIFIED.jsonl

A decision is **carried** into a wd5 run when every one of these holds, and the reason it is not is
recorded (`CARRIED.json`, `not_carried`) so that the cell is asked as any other:

* the earlier plans refused it as `country-changes` (a `SKIPPED.jsonl` of a WD1, WD3 or WD4 step) and
  nothing has written the point since;
* the run's population holds the point as an open field (`CLASSIFIED.jsonl`);
* the latest decision of the point (`population.read_history`) is a counted `replace` with a value -
  not `unresolved`, `held` or `keep` - and not one a MiniMax model answered (master plan X6: MiniMax
  answers are never ground truth, the point is asked again by Claude);
* it was made about the point the run holds (`stored` equals the run's stored point), so the plan's
  `moved-since-classification` does not refuse it for a different reason;
* the country check the plan runs would agree now. A point the guard still refuses (inside another
  country, beyond the tolerance, Kosovo) is not carried: it is asked, because only a new question
  can find a better point.

`export` leaves a carried cell out of the questions and `import` adds the carried decision to
`DECISIONS.jsonl` (`via: "carried"`, with `origin` naming the run it was made in and the pages it was
quoted from), so the decisions of the run are complete and the plan reads one file. The adversarial
re-check (`adversarial.py`) checks a carried `replace` like any other.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402

CARRIED_FILE = "CARRIED.jsonl"
CARRIED_META = "CARRIED.json"
#: The `via` of a carried decision (`handoff.COUNTED` and `EXHAUSTED` are the others).
CARRIED = "carried"
FIELD = "coordinates"
#: The write plan's refusal for a point in another country, and the column it is filed under.
COUNTRY_REFUSAL = "country-changes"
REFUSED_COLUMN = "lat"
#: The runs that hold decisions, in the order the lanes ran: the latest decision of a cell is the
#: last of these that holds one (`population.read_history`).
RUN_NAMES = (*POP.WD1_RUN_NAMES, *POP.HISTORY_RUNS)
#: The waves of the lanes whose plans refused a point, under each lane's own run directory.
WAVE_LANES = ("wd1", "wd3", "wd4")


class CarryError(ValueError):
    """The decisions cannot be carried into this run. Nothing was written."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def refused_sites(waves: Sequence[Path]) -> dict[str, str]:
    """`{site_id: the SKIPPED.jsonl that last refused it}` of every point the plans of the given
    `write` directories refused as `country-changes`. A directory that is not there is refused: a
    lane's waves are the record of what it refused, and a missing one would silently shrink the set."""
    refused: dict[str, str] = {}
    for root in waves:
        if not root.is_dir():
            raise CarryError(f"{root} is not there: the waves of a lane are the record it refused")
        for path in sorted(root.glob("*/s*/SKIPPED.jsonl")):
            for row in _read_jsonl(path):
                if row.get("reason") == COUNTRY_REFUSAL and row.get("column") == REFUSED_COLUMN:
                    refused[str(row["site_id"])] = POP._shown(path)
    return refused


def origin_run(decision: Mapping[str, Any], fields_dir: Path) -> Path:
    """The run whose `DECISIONS.jsonl` holds exactly this decision - the pages its quotes were read
    from are that run's `pages/`. Latest run first; `CarryError` when none holds it."""
    for name in reversed(RUN_NAMES):
        path = fields_dir / name / "DECISIONS.jsonl"
        if not path.exists():
            continue
        for row in _read_jsonl(path):
            if (
                row["site_id"] == decision["site_id"]
                and row["field"] == decision["field"]
                and row["round"] == decision["round"]
                and row["answered_by"] == decision["answered_by"]
                and row["value"] == decision["value"]
            ):
                return path.parent
    raise CarryError(
        f"no run under {fields_dir} holds the decision of {decision['site_id']}/{decision['field']}"
    )


def not_carried_reason(
    line: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    country_check: Callable[[str, float, float], Mapping[str, Any]],
) -> str | None:
    """Why the earlier decision of this point is not carried, or `None` when it is."""
    if decision is None:
        return "no earlier decision"
    if decision["decision"] != A.REPLACE or not decision["value"]:
        return f"the earlier decision is {decision['decision']}, not a replace with a value"
    if decision["via"] != "counted":
        return f"the earlier decision came {decision['via']}, not from a counted answer"
    if "minimax" in str(decision.get("model") or "").lower():
        return "a MiniMax model answered it: Claude asks the point again (D10)"
    if decision["stored"] != line["fields"][FIELD]["stored"]:
        return (
            f"the decision was made about {decision['stored']}, the run holds "
            f"{line['fields'][FIELD]['stored']}"
        )
    lat, lon = (float(x) for x in str(decision["value"]).split(","))
    country = country_check(str(line["country"]), lat, lon)
    if not country["agrees"]:
        return (
            f"the country guard still refuses it: the point lies in "
            f"{country['polygon'] or 'no country polygon, beyond the coast tolerance'}, "
            f"the site says {line['country']}"
        )
    return None


def carry_points(
    run: Path,
    *,
    history: Mapping[tuple[str, str], Mapping[str, Any]],
    fields_dir: Path,
    waves: Sequence[Path],
    country_check: Callable[[str, float, float], Mapping[str, Any]],
) -> dict[str, Any]:
    """CARRIED.jsonl and CARRIED.json of a wd5 run: the refused points whose earlier decision stands.

    Refused: a run that is not a wd5 run, a run asked already (the carried cells are left out of the
    questions at the export, so they are chosen before it), a run that has carried already, a run
    without a classification."""
    if R.read_rule(run) is not R.RECHECK:
        raise CarryError(f"{run} is not a wd5 run (its rule is {R.read_rule(run).name!r})")
    if (run / "ROUNDS.jsonl").exists():
        raise CarryError(f"{run} was asked already (ROUNDS.jsonl): carry before the export")
    if (run / CARRIED_META).exists() or (run / CARRIED_FILE).exists():
        raise CarryError(f"{run} has carried already: a run carries once")
    path = run / C.CLASSIFIED_FILE
    if not path.exists():
        raise CarryError(f"{path} is missing - build the population first")
    lines = {row["site_id"]: row for row in _read_jsonl(path)}
    refused = refused_sites(waves)
    carried: list[dict[str, Any]] = []
    not_carried: dict[str, str] = {}
    outside: list[str] = []
    for site in sorted(refused):
        line = lines.get(site)
        if line is None or FIELD not in line["asked"]:
            outside.append(site)
            continue
        decision = history.get((site, FIELD))
        reason = not_carried_reason(line, decision, country_check)
        if reason is not None:
            not_carried[site] = reason
            continue
        assert decision is not None  # not_carried_reason refused a missing decision
        origin = origin_run(decision, fields_dir)
        carried.append(
            {
                **{k: v for k, v in decision.items() if k != "run"},
                "via": CARRIED,
                "origin": {"run": POP._shown(origin), "via": decision["via"]},
            }
        )
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in carried)
    (run / CARRIED_FILE).write_text(text, encoding="utf-8", newline="\n")
    meta = {
        "built_at": H.now(),
        "refused_points": len(refused),
        "carried": len(carried),
        "sites": [row["site_id"] for row in carried],
        "not_carried": not_carried,
        "refused_outside_this_run": outside,
        "classified_sha256": _sha256_text(path),
        "carried_sha256": _sha256_text(run / CARRIED_FILE),
        "waves": [POP._shown(w) for w in waves],
    }
    (run / CARRIED_META).write_text(
        json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta


def read_carried(run: Path) -> list[dict[str, Any]]:
    """The carried decisions of a run, in file order - none for a run that carried nothing. A file
    that is not the one `CARRIED.json` pins is refused (an edit after `carry-points`), and so is a
    file without its pin: a decision nobody recorded carrying is not a decision of the run."""
    file, meta = run / CARRIED_FILE, run / CARRIED_META
    if not file.exists() and not meta.exists():
        return []
    if not (file.exists() and meta.exists()):
        raise CarryError(f"{run}: {CARRIED_FILE} and {CARRIED_META} come together")
    pinned = json.loads(meta.read_text(encoding="utf-8"))["carried_sha256"]
    if _sha256_text(file) != pinned:
        raise CarryError(f"{file} is not the file {CARRIED_META} pins: it was edited")
    return _read_jsonl(file)


def carried_cells(run: Path) -> frozenset[tuple[str, str]]:
    """The `(site, field)` pairs a run carries - what its export does not ask."""
    return frozenset((str(row["site_id"]), str(row["field"])) for row in read_carried(run))


# ------------------------------------------------------------------------------------------ the CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("carry-points", help="CARRIED.jsonl and CARRIED.json of a wd5 run")
    cmd.add_argument("--run", type=Path, required=True)
    cmd.add_argument(
        "--fields-dir",
        type=Path,
        default=POP.FIELDS_DIR,
        help="where the runs of WD1, WD3 and WD4 and their waves live (default: this checkout's)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        from fields import plan as FP  # noqa: PLC0415 - plan imports handoff, which imports this

        wd1 = POP.read_wd1(*POP.wd1_files(args.fields_dir))
        result = carry_points(
            args.run,
            history=POP.read_history(wd1, args.fields_dir),
            fields_dir=args.fields_dir,
            waves=[args.fields_dir / lane / "write" for lane in WAVE_LANES],
            country_check=FP._country_check(),
        )
    except (CarryError, POP.PopulationError, R.RuleError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
