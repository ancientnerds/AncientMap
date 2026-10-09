"""The calibration of lane WC's roles (owner decision D6, 2026-10-08), on `calibrate_claude.py`.

`calibrate_claude.py verdict` serves lane WC as it stands (a pool is batches of an answered handoff,
the threshold is sealed first). What lane WC adds is here, because it measures what the lane's own
checks measure and nothing else - and it is **sealed with the threshold**, before the copy is made and
any agent answers (`seal`): the kind of pool, the verdict merge and the list of known errors, with its
sha256. `compare` reads them from the seal and takes no setting of its own, and `calibrate_claude.py`
refuses a lane WC calibration it was not asked to seal (`seal`), to compare (`compare`) or to close with
a comparison that did not come from here (`verdict`).

* **the check pool counts KEEP and KEEP_TRIMMED as one verdict** (`merge`): whether a sentence goes
  whole or with a piece cut off is a second decision on a sentence both answers keep, and the
  agreement of the check is on whether it stays (map `descriptions.md`, D25a);
* **known errors** (`expectations`): the pilots' judges found sentences the check kept and was wrong
  to - a kept sentence WRONG with a found quote, a kept text incoherent. A role is calibrated on the
  pilots' sites, so the fresh answer must not keep such a sentence (check pool: neither KEEP nor
  KEEP_TRIMMED; verify pool: it must be WRONG or UNSUPPORTED) and the fresh judge must find it again
  (judge pool: `must_be WRONG`, `coherent must_be False`). A kept text the judge found incoherent is a
  site whose recorded check pattern produced it: the fresh check must not repeat that pattern, and a
  fresh verification or judge must find the text incoherent. A known error the role misses fails the
  calibration whatever the agreement is (`lane_failures`);
* **extra WRONG verdicts** (judge pool): a fresh judge that calls WRONG what the recorded one did not
  is allowed one (`MAX_EXTRA_WRONG`);
* **the judge pool is registrable** (`register_judge_pool`): `mcode_driver.register_calibration_run`
  knows the check and the verification rounds, not the judge's, so the calibration run of a judge pool
  is written here (`judge/ROUND.json` marked `calibration`, tied to no plan, the `FINAL.jsonl` lines of its sites).

    python scripts/remediation/wc/calibration.py known   --kind check|verify|judge --run R [--run R ...] [--handoff H]
    python scripts/remediation/wc/calibration.py seal    --id ID --kind K --handoff H --batches B [B ...] --threshold T [--run R ...]
    python scripts/remediation/wc/calibration.py prepare --id ID --run R
    python scripts/remediation/wc/calibration.py compare --id ID

`known` prints what `seal` derives (to review it first; a verify pool names its round with `--handoff`);
`seal` derives the expectations of the pool's sites from the pilots' judged runs and seals them with the
threshold; `prepare` is `calibrate_claude.py prepare` with the judge pool registered; `compare` is
`calibrate_claude.py compare` with the merge and the sealed expectations.
`calibrate_claude.py verdict` closes the calibration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Collection, Iterable, Sequence
from pathlib import Path
from typing import Any

_REMEDIATION = Path(__file__).resolve().parents[1]
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

import calibrate_claude as CC  # noqa: E402 - seal, prepare, compare, verdict
import mcode_driver as D  # noqa: E402 - the copy, the comparison, the calibration run
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from phase3.ledger import utc_now  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402

from wc import cli as WC  # noqa: E402 - the verification rounds' records

#: The verdicts of a check answer that count as one (a sentence kept whole or with a piece cut off).
MERGED = frozenset({"KEEP", "KEEP_TRIMMED"})
#: A fresh judge may call WRONG at most this many kept sentences the recorded judge did not.
MAX_EXTRA_WRONG = 1
#: Which role a kind of pool calibrates.
KIND_ROLE = {"check": "fact_checker", "verify": "web_verifier", "judge": "pilot_judge"}
#: The verdicts a fresh verification may give a sentence the judge found WRONG (it may not support it).
NOT_SUPPORTED = ["UNSUPPORTED", "WRONG"]
JUDGE_ROUND = Path("judge") / "ROUND.json"


class WcCalibrationError(ValueError):
    """The calibration cannot take this step. Nothing is guessed."""


# ------------------------------------------------------------------------------------ the merge
def merge(text: str) -> str:
    """A check answer with KEEP_TRIMMED read as KEEP, as JSON; any other answer unchanged."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(data, dict) or not isinstance(data.get("sentences"), list):
        return text
    for row in data["sentences"]:
        if isinstance(row, dict) and row.get("verdict") in MERGED:
            row["verdict"] = "KEEP"
    return json.dumps(data, ensure_ascii=False)


# ------------------------------------------------------------------------------ the expectations
def expectations(
    kind: str,
    runs: Iterable[Path],
    *,
    handoff: Path | None = None,
    labels: Collection[str] | None = None,
) -> list[dict[str, Any]]:
    """What the pilots' judges established, as expectations of a fresh answer (label = site id; only
    the sites in `labels` when it is given):

    * `check`: every kept sentence a judge found WRONG with a found quote must not be kept again,
      whole or trimmed (`sentence-<n>`, `must_not_be ["KEEP", "KEEP_TRIMMED"]`; the sentence's number
      is read from the run's FINAL); a site whose kept text the judge found incoherent must not get
      the recorded pattern of verdicts again (`kept-text`, `must_differ_from_recorded`);
    * `verify`: the same sentence must be WRONG or UNSUPPORTED in the verification of `handoff` (a
      round of each run; `kept-<k>`, k the sentence's place in what that round showed), and a site
      whose kept text the judge found incoherent must be found incoherent (`coherent`, `False`);
    * `judge`: the same sentence must be found WRONG again (`kept-<k>`, `must_be ["WRONG"]`), and a
      site whose kept text the judge found incoherent must be found incoherent (`coherent`,
      `must_be ["False"]`)."""
    if kind not in KIND_ROLE:
        raise WcCalibrationError(f"kind {kind!r} is none of {', '.join(KIND_ROLE)}")
    if kind == "verify" and handoff is None:
        raise WcCalibrationError("a verify pool names the verification round it is: --handoff")
    found: list[dict[str, Any]] = []
    for run in runs:
        finals = {row["site_id"]: row for row in read_jsonl(run / "FINAL.jsonl")}
        shown = WC._verify_round_of(run, handoff)["shown"] if kind == "verify" and handoff else {}
        for judged in read_jsonl(run / "judge" / "JUDGED.jsonl"):
            site_id = judged["site_id"]
            if labels is not None and site_id not in labels:
                continue
            kept_numbers = [d["n"] for d in finals[site_id]["decisions"] if d["text"] is not None]
            for item in judged["items"]:
                if item["kind"] == "kept" and item["verdict"] == "WRONG" and item["quotes_found"]:
                    k = item["number"]
                    if kind == "check":
                        found.append(
                            {
                                "label": site_id,
                                "unit": f"sentence-{kept_numbers[k - 1]}",
                                "must_not_be": sorted(MERGED),
                            }
                        )
                    elif kind == "verify":
                        number = kept_numbers[k - 1]
                        if number not in shown[site_id]:
                            raise WcCalibrationError(
                                f"{site_id}: the judge's WRONG sentence {number} is not among the "
                                f"sentences {handoff} showed ({shown[site_id]})"
                            )
                        found.append(
                            {
                                "label": site_id,
                                "unit": f"kept-{shown[site_id].index(number) + 1}",
                                "must_be": NOT_SUPPORTED,
                            }
                        )
                    else:
                        found.append({"label": site_id, "unit": f"kept-{k}", "must_be": ["WRONG"]})
            if not judged["coherent"]:
                found.append(
                    {"label": site_id, "unit": "kept-text", "must_differ_from_recorded": True}
                    if kind == "check"
                    else {"label": site_id, "unit": "coherent", "must_be": ["False"]}
                )
    return found


def _units(text: str) -> dict[str, str]:
    pairs = D._verdicts(text)
    return dict(pairs) if pairs is not None else {}


def _sentences(text: str) -> dict[str, str]:
    return {unit: verdict for unit, verdict in _units(text).items() if unit.startswith("sentence-")}


def _known(
    known: Sequence[dict[str, Any]], fresh: dict[str, str], recorded: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Every expectation against the fresh answer (unmerged, as the role wrote it): its verdict and
    whether the role missed it. An expectation about a label the pool does not hold stops the
    command: it would measure nothing."""
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for expectation in known:
        label, unit = expectation["label"], expectation["unit"]
        if label not in recorded:
            raise WcCalibrationError(f"expectation {label}/{unit}: the label is not in the pool")
        if expectation.get("must_differ_from_recorded"):
            repeated = label in fresh and _sentences(fresh[label]) == _sentences(recorded[label])
            if label not in fresh:
                verdict = None
            else:
                verdict = "the recorded verdicts" if repeated else "other verdicts"
            missed = verdict is None or repeated
            wanted: Any = "other verdicts than the recorded ones"
        else:
            verdict = _units(fresh[label]).get(unit) if label in fresh else None
            missed = (
                verdict is None
                or ("must_not_be" in expectation and verdict in expectation["must_not_be"])
                or ("must_be" in expectation and verdict not in expectation["must_be"])
            )
            wanted = expectation.get("must_be") or f"not {expectation.get('must_not_be')}"
        rows.append({**expectation, "fresh": verdict, "missed": missed})
        if missed:
            failures.append(
                f"known error {label}/{unit} missed: the fresh answer says {verdict!r}"
                f", expected {wanted}"
            )
    return rows, failures


def _extra_wrong(recorded: dict[str, str], fresh: dict[str, str]) -> int:
    count = 0
    for label, text in fresh.items():
        old = _units(recorded[label]) if label in recorded else {}
        count += sum(
            1
            for unit, verdict in _units(text).items()
            if unit.startswith("kept-") and verdict == "WRONG" and old.get(unit) != "WRONG"
        )
    return count


# ------------------------------------------------------------------------------------- the seal
def _sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def seal(
    root: Path,
    *,
    calibration_id: str,
    kind: str,
    handoff: Path,
    batches: Sequence[str],
    threshold: float,
    runs: Sequence[Path] = (),
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """`calibrate_claude.seal` for a lane WC pool, with the lane's conditions sealed in it: the kind
    (which fixes the role and whether KEEP and KEEP_TRIMMED are one verdict) and the known errors of
    the pool's sites, derived from the pilots' judged `runs`, with their sha256. A known error of a
    site outside the pool is named (`outside_pool`), never dropped silently."""
    if kind not in KIND_ROLE:
        raise WcCalibrationError(f"kind {kind!r} is none of {', '.join(KIND_ROLE)}")
    pool = {case.partition("/")[2] for case in CC.case_ids(handoff, batches)}
    found = expectations(kind, runs, handoff=handoff if kind == "verify" else None)
    inside = [e for e in found if e["label"] in pool]
    lane = {
        "kind": kind,
        "merge": kind == "check",
        "expectations": inside,
        "expectations_sha256": _sha256(inside),
        "outside_pool": sorted({e["label"] for e in found if e["label"] not in pool}),
    }
    return CC.seal(
        root,
        calibration_id=calibration_id,
        role=KIND_ROLE[kind],
        handoff=handoff,
        batches=batches,
        threshold=threshold,
        lane=lane,
        now=now,
    )


def _lane(root: Path, calibration_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The seal of a lane WC calibration and its lane conditions, as they were sealed."""
    sealed = CC._sealed(root, calibration_id)
    lane = sealed.get("lane")
    if lane is None:
        raise WcCalibrationError(
            f"{calibration_id} was sealed without the lane's conditions: seal it with "
            "`wc/calibration.py seal` (a threshold and the known errors are sealed together)"
        )
    if lane["expectations_sha256"] != _sha256(lane["expectations"]):
        raise WcCalibrationError(f"the sealed expectations of {calibration_id} were changed")
    return sealed, lane


def prepare(root: Path, *, calibration_id: str, run: Path) -> dict[str, Any]:
    """`calibrate_claude.prepare` of a sealed lane WC pool, the judge pool registered."""
    _lane(root, calibration_id)
    return CC.prepare(root, calibration_id=calibration_id, run=run, register=register_judge_pool)


def compare(root: Path, *, calibration_id: str) -> dict[str, Any]:
    """`calibrate_claude.compare` for lane WC: the fresh answers against the recorded ones, unit by
    unit (KEEP and KEEP_TRIMMED as one when the seal says so), then the sealed known errors and, for a
    judge pool, the extra WRONG verdicts; written once to `COMPARISON.json`, with `lane_failures`
    that `calibrate_claude.py verdict` requires and counts. The merge and the known errors are the
    seal's: there is no setting to pass."""
    sealed, lane = _lane(root, calibration_id)
    out = root / calibration_id
    recorded_path = out / CC.RECORDED_FILE
    if not recorded_path.exists():
        raise WcCalibrationError(f"{calibration_id} is not prepared: {recorded_path} is missing")
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    fresh = CC._fresh_answers(out, sealed)
    read = merge if lane["merge"] else (lambda text: text)
    report = D.compare_answers(
        sealed["role"],
        sorted(recorded),
        {label: read(text) for label, text in recorded.items()},
        {label: read(text) for label, text in fresh.items()},
    ).to_dict()
    rows, failures = _known(lane["expectations"], fresh, recorded)
    extra = _extra_wrong(recorded, fresh) if lane["kind"] == "judge" else 0
    if extra > MAX_EXTRA_WRONG:
        failures.append(f"{extra} extra WRONG verdict(s), {MAX_EXTRA_WRONG} allowed")
    report.update(
        {
            "kind": lane["kind"],
            "merged": lane["merge"],
            "known": rows,
            "extra_wrong": extra,
            "lane_failures": failures,
        }
    )
    CC._write_once(out / CC.COMPARISON_FILE, report)
    return report


# ------------------------------------------------------------------------------ the judge's pool
def register_judge_pool(
    source_run: Path, source_handoff: Path, out: Path, batches: Sequence[str]
) -> Path:
    """The calibration run of a judge pool: `judge/ROUND.json` (the source's, restricted to the
    calibrated batches and marked `calibration`) and the `FINAL.jsonl` lines of its sites, which are
    what `judge-brief` and `judge-check-answer` read. Any other pool goes to
    `mcode_driver.register_calibration_run`."""
    round_path = source_run / JUDGE_ROUND
    if not round_path.exists():
        return D.register_calibration_run(source_run, source_handoff, out, batches)
    record = json.loads(round_path.read_text(encoding="utf-8"))
    if Path(record["handoff"]).resolve() != source_handoff.resolve():
        return D.register_calibration_run(source_run, source_handoff, out, batches)
    missing = [batch for batch in batches if batch not in record["batches"]]
    if missing:
        raise WcCalibrationError(
            f"{source_handoff}: no batch {', '.join(missing)} in the judge round"
        )
    run_dir = D.calibration_run(out)
    if run_dir.exists():
        raise WcCalibrationError(f"{run_dir} exists: a calibration run is written once")
    labels = [label for batch in batches for label in record["batches"][batch]]
    (run_dir / "judge").mkdir(parents=True)
    (run_dir / "POPULATION.json").write_text(
        json.dumps({"kind": "wc", "pilot": None}, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    calibration_round = {
        "handoff": D._shown(out),
        "exported_at": record.get("exported_at", ""),
        "batches": {batch: list(record["batches"][batch]) for batch in batches},
        "calibration": True,
        "calibrated_from": {
            "run": D._shown(source_run),
            "handoff": D._shown(source_handoff),
            "batches": list(batches),
        },
    }
    (run_dir / JUDGE_ROUND).write_text(
        json.dumps(calibration_round, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (run_dir / "FINAL.jsonl").write_text(
        D._labels_of(source_run / "FINAL.jsonl", labels), encoding="utf-8"
    )
    return run_dir


# ------------------------------------------------------------------------------------------ CLI
def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="wc-calibration", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    known = sub.add_parser("known")
    known.add_argument("--kind", required=True, choices=sorted(KIND_ROLE))
    known.add_argument("--run", required=True, type=Path, action="append")
    known.add_argument("--handoff", type=Path, default=None)
    for name in ("seal", "prepare", "compare"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, default=CC.CALIBRATION_ROOT)
        command.add_argument("--id", required=True, dest="calibration_id")
    sealing = sub.choices["seal"]
    sealing.add_argument("--kind", required=True, choices=sorted(KIND_ROLE))
    sealing.add_argument("--handoff", required=True, type=Path)
    sealing.add_argument("--batches", required=True, nargs="+")
    sealing.add_argument("--threshold", required=True, type=float)
    sealing.add_argument("--run", type=Path, action="append", default=[])
    sub.choices["prepare"].add_argument("--run", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "known":
            payload: Any = expectations(args.kind, args.run, handoff=args.handoff)
        elif args.command == "seal":
            payload = seal(
                args.root,
                calibration_id=args.calibration_id,
                kind=args.kind,
                handoff=args.handoff,
                batches=args.batches,
                threshold=args.threshold,
                runs=args.run,
            )
        elif args.command == "prepare":
            payload = prepare(args.root, calibration_id=args.calibration_id, run=args.run)
        else:
            payload = compare(args.root, calibration_id=args.calibration_id)
    except (
        WcCalibrationError,
        WC.WcRunError,
        CC.CalibrationError,
        RO.RoleError,
        OH.HandoffError,
        D.DriverError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
