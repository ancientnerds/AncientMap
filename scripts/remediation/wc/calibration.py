"""The calibration of lane WC's roles (owner decision D6, 2026-10-08), on `calibrate_claude.py`.

`calibrate_claude.py seal` and `verdict` serve lane WC as they stand (a pool is batches of an answered
handoff, the threshold is sealed first). What lane WC adds is here, because it measures what the
lane's own checks measure and nothing else:

* **the check pool counts KEEP and KEEP_TRIMMED as one verdict** (`merge`): whether a sentence goes
  whole or with a piece cut off is a second decision on a sentence both answers keep, and the
  agreement of the check is on whether it stays (map `descriptions.md`, D25a);
* **known errors** (`expectations`): the pilots' judges found sentences the check kept and was wrong
  to - a kept sentence WRONG with a found quote, a kept text incoherent. A role is calibrated on the
  pilots' sites, so the fresh answer must not keep such a sentence (check pool: `must_not_be KEEP`)
  and the fresh judge must find it again (judge pool: `must_be WRONG`, `coherent must_be False`). A
  known error the role misses fails the calibration whatever the agreement is (`lane_failures`);
* **extra WRONG verdicts** (judge pool): a fresh judge that calls WRONG what the recorded one did not
  is allowed one (`MAX_EXTRA_WRONG`);
* **the judge pool is registrable** (`register_judge_pool`): `mcode_driver.register_calibration_run`
  knows the check and the verification rounds, not the judge's, so the calibration run of a judge pool
  is written here (`judge/ROUND.json` marked `calibration`, the `FINAL.jsonl` lines of its sites).

    python scripts/remediation/wc/calibration.py known  --kind check|judge --run R [--run R ...]
    python scripts/remediation/wc/calibration.py prepare --id ID --run R
    python scripts/remediation/wc/calibration.py compare --id ID [--merge] [--known F]

`known` prints the expectation list (write it to a file, review it, pass it to `compare`); `prepare`
is `calibrate_claude.py prepare` with the judge pool registered; `compare` is `calibrate_claude.py
compare` with the merge and the expectations. `calibrate_claude.py verdict` closes the calibration.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

_REMEDIATION = Path(__file__).resolve().parents[1]
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

import calibrate_claude as CC  # noqa: E402 - seal, prepare, compare, verdict
import mcode_driver as D  # noqa: E402 - the copy, the comparison, the calibration run
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402

#: The verdicts of a check answer that count as one (a sentence kept whole or with a piece cut off).
MERGED = frozenset({"KEEP", "KEEP_TRIMMED"})
#: A fresh judge may call WRONG at most this many kept sentences the recorded judge did not.
MAX_EXTRA_WRONG = 1
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
def expectations(kind: str, runs: Iterable[Path]) -> list[dict[str, Any]]:
    """What the pilots' judges established, as expectations of a fresh answer (label = site id):

    * `check`: every kept sentence a judge found WRONG with a found quote must not be KEPT again
      (`sentence-<n>`, `must_not_be ["KEEP"]`; the sentence's number is read from the run's FINAL);
    * `judge`: the same sentence must be found WRONG again (`kept-<k>`, `must_be ["WRONG"]`), and a
      site whose kept text the judge found incoherent must be found incoherent (`coherent`,
      `must_be ["False"]`)."""
    if kind not in ("check", "judge"):
        raise WcCalibrationError(f"kind {kind!r} is none of check, judge")
    found: list[dict[str, Any]] = []
    for run in runs:
        finals = {row["site_id"]: row for row in read_jsonl(run / "FINAL.jsonl")}
        for judged in read_jsonl(run / "judge" / "JUDGED.jsonl"):
            site_id = judged["site_id"]
            kept_numbers = [d["n"] for d in finals[site_id]["decisions"] if d["text"] is not None]
            for item in judged["items"]:
                if item["kind"] == "kept" and item["verdict"] == "WRONG" and item["quotes_found"]:
                    k = item["number"]
                    found.append(
                        {
                            "label": site_id,
                            "unit": f"sentence-{kept_numbers[k - 1]}",
                            "must_not_be": ["KEEP"],
                        }
                        if kind == "check"
                        else {"label": site_id, "unit": f"kept-{k}", "must_be": ["WRONG"]}
                    )
            if kind == "judge" and not judged["coherent"]:
                found.append({"label": site_id, "unit": "coherent", "must_be": ["False"]})
    return found


def _units(text: str) -> dict[str, str]:
    pairs = D._verdicts(text)
    return dict(pairs) if pairs is not None else {}


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
        verdict = _units(fresh[label]).get(unit) if label in fresh else None
        missed = (
            verdict is None
            or ("must_not_be" in expectation and verdict in expectation["must_not_be"])
            or ("must_be" in expectation and verdict not in expectation["must_be"])
        )
        rows.append({**expectation, "fresh": verdict, "missed": missed})
        if missed:
            failures.append(
                f"known error {label}/{unit} missed: the fresh answer says {verdict!r}"
                f", expected {expectation.get('must_be') or 'not ' + str(expectation['must_not_be'])}"
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


def compare(
    root: Path,
    *,
    calibration_id: str,
    merge_check: bool = False,
    known: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """`calibrate_claude.compare` for lane WC: the fresh answers against the recorded ones, unit by
    unit (`merge_check`: KEEP and KEEP_TRIMMED as one), then the known errors and, for a judge pool,
    the extra WRONG verdicts; written once to `COMPARISON.json`, with `lane_failures` that
    `calibrate_claude.py verdict` counts."""
    sealed = CC._sealed(root, calibration_id)
    out = root / calibration_id
    recorded_path = out / CC.RECORDED_FILE
    if not recorded_path.exists():
        raise WcCalibrationError(f"{calibration_id} is not prepared: {recorded_path} is missing")
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    fresh = CC._fresh_answers(out, sealed)
    read = merge if merge_check else (lambda text: text)
    report = D.compare_answers(
        sealed["role"],
        sorted(recorded),
        {label: read(text) for label, text in recorded.items()},
        {label: read(text) for label, text in fresh.items()},
    ).to_dict()
    rows, failures = _known(known, fresh, recorded)
    is_judge = all(batch.startswith("judge-") for batch in sealed["batches"])
    extra = _extra_wrong(recorded, fresh) if is_judge else 0
    if extra > MAX_EXTRA_WRONG:
        failures.append(f"{extra} extra WRONG verdict(s), {MAX_EXTRA_WRONG} allowed")
    report.update(
        {"merged": merge_check, "known": rows, "extra_wrong": extra, "lane_failures": failures}
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
        "plan_sha256": record["plan_sha256"],
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
    known.add_argument("--kind", required=True, choices=("check", "judge"))
    known.add_argument("--run", required=True, type=Path, action="append")
    for name in ("prepare", "compare"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, default=CC.CALIBRATION_ROOT)
        command.add_argument("--id", required=True, dest="calibration_id")
    sub.choices["prepare"].add_argument("--run", required=True, type=Path)
    sub.choices["compare"].add_argument("--merge", action="store_true")
    sub.choices["compare"].add_argument("--known", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "known":
            payload: Any = expectations(args.kind, args.run)
        elif args.command == "prepare":
            payload = CC.prepare(
                args.root,
                calibration_id=args.calibration_id,
                run=args.run,
                register=register_judge_pool,
            )
        else:
            payload = compare(
                args.root,
                calibration_id=args.calibration_id,
                merge_check=args.merge,
                known=[]
                if args.known is None
                else json.loads(args.known.read_text(encoding="utf-8")),
            )
    except (
        WcCalibrationError,
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
