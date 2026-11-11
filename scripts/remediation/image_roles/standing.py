"""How an image role comes to stand after its clean-gold calibration (D117), and the gold's audit trail.

The clean-gold directories (`clean_gold.py`: `image-roles-v3` for the depicts judge and the hero
re-check, `image-roles-v3p` for the prefilter) write one verdict per slot. A slot that failed on Opus
is held for the owner - there is no tier above. Three owner decisions of 2026-11-07 act on those
verdicts, and this module is their record:

* **release** (D125 `image_depicts`, D126 `image_prefilter`, D128 `adversarial` under its condition):
  the decision to let a held verdict stand, written once to `<dir>/releases/<slot>.json` with who
  decided, why, and the sha256 of what it rests on - the verdict file, the sealed thresholds, the
  fixed gold, the role's registry entry and every evidence file (`calibrate_claude.evidence_records`,
  the project's one form of release evidence). Refused: a verdict that passed, one with a tier move,
  one not held, a release written already.
* **correct** (D127): a case of the fixed gold whose truth the owner's rule changes. GOLD.jsonl is
  sealed and never rewritten; the change goes to the gold's audit trail `<dir>/GOLD_AUDIT.jsonl`,
  one line per case with the old and the new truth, the decision and the reason, bound to the fixed
  gold's sha256. A case is corrected once.
* **rescore** (D127/D128): the existing answers of a slot measured again against the gold with its
  audit trail applied - no new answer - into `<dir>/verdicts/<slot>.<decision>.json`, once. The
  sealed thresholds decide, as in `clean_gold.evaluate`; a failure on Opus is held for the owner.

`require_standing` is the gate the image lane's exports call (`run.py`): a slot stands when its
verdict passed or a release still rests on the verdict, the seal, the gold, the registry entry and
the evidence it was made on - or, since owner decisions D153 (2026-11-10, Fable 5.2) and D157
(2026-11-11, Opus 5.5) moved every role with no calibration run (D154), when its role stands by
that decision
(`roles.owner_standing`), which the gate asks first and names in what it returns. Nothing here
calls a model.

    standing.py correct --dir D --case ID --truth depicts|not_depicts --decision D127 --reason R
    standing.py rescore --dir D --slot adversarial --decision D127
    standing.py release --dir D --slot S --verdict FILE --decided-by T --reason R --evidence F [F ...]
    standing.py check   [--slot S ...]                    every slot of STANDING, or the named ones
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import calibrate_claude as CC  # noqa: E402 - the release evidence records
import roles as RO  # noqa: E402
from served_image import state as ST  # noqa: E402

from image_roles import calibrate as CAL  # noqa: E402
from image_roles import clean_gold as CG  # noqa: E402
from image_roles import stage as SG  # noqa: E402

GOLD_AUDIT = "GOLD_AUDIT.jsonl"
RELEASES_DIR = "releases"
TRUTHS = ("depicts", "not_depicts")
#: The calibration directory each production slot of the image lane stands on (relative to the
#: main checkout: run data is gitignored, a worktree has none).
CALIBRATION_ROOT = Path("output") / "remediation" / "calibration"
STANDING = {
    "image_prefilter": "image-roles-v3p",
    "image_depicts": "image-roles-v3",
    "adversarial": "image-roles-v3",
}


class StandingError(ST.StateError):
    """A release, a correction or a gate cannot be made from what the directory holds."""


def _gold_sha(directory: Path) -> str:
    entries = [e for e in CAL._log(directory) if "gold_sha256" in e]
    if len(entries) != 1:
        raise StandingError(f"{directory} has no fixed gold")
    return str(entries[0]["gold_sha256"])


# ------------------------------------------------------------------------------ the audit trail
def audit(directory: Path) -> list[dict[str, Any]]:
    """The gold's corrections, oldest first; refused when one was made on another gold."""
    path = directory / GOLD_AUDIT
    if not path.is_file():
        return []
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    gold = _gold_sha(directory)
    for row in rows:
        if row["gold_sha256"] != gold:
            raise StandingError(
                f"{path}: {row['case_id']} corrects another gold than the fixed one"
            )
    return rows


def corrected_gold(directory: Path) -> tuple[list[dict[str, Any]], str]:
    """`(cases, fixed_at)` of the fixed gold with the audit trail's truths applied."""
    cases, fixed_at = CAL.fixed_gold(directory)
    changed = {r["case_id"]: r["to"] for r in audit(directory)}
    return [{**c, "truth": changed.get(c["case_id"], c["truth"])} for c in cases], fixed_at


def correct(
    directory: Path,
    *,
    case_id: str,
    truth: str,
    decision: str,
    reason: str,
    now: Callable[[], str] = CG._now,
) -> dict[str, Any]:
    """One line of the gold's audit trail: case `case_id` takes `truth` under `decision`."""
    CG.sealed(directory)
    if truth not in TRUTHS:
        raise StandingError(f"truth {truth!r} is not one of {TRUTHS}")
    if not decision.strip() or not reason.strip():
        raise StandingError("a correction names its decision and its reason")
    cases, _ = CAL.fixed_gold(directory)
    by_id = {c["case_id"]: c for c in cases}
    if case_id not in by_id:
        raise StandingError(f"{case_id} is not a case of the fixed gold")
    if by_id[case_id]["truth"] not in TRUTHS:
        raise StandingError(
            f"{case_id} is not a depicts case: its truth is {by_id[case_id]['truth']}"
        )
    if any(r["case_id"] == case_id for r in audit(directory)):
        raise StandingError(f"{case_id} is corrected already - a case is corrected once")
    if by_id[case_id]["truth"] == truth:
        raise StandingError(f"{case_id} is {truth} already: nothing to correct")
    row = {
        "case_id": case_id,
        "role": by_id[case_id]["role"],
        "from": by_id[case_id]["truth"],
        "to": truth,
        "decision": decision,
        "reason": reason,
        "gold_sha256": _gold_sha(directory),
        "corrected_at": now(),
    }
    with open(directory / GOLD_AUDIT, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


# ------------------------------------------------------------------------------------ re-scoring
def rescore(
    directory: Path,
    slot: str,
    *,
    decision: str,
    now: Callable[[], str] = CG._now,
    cp: Callable[[int, int], tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """The slot's existing answers against the corrected gold -> `verdicts/<slot>.<decision>.json`."""
    document = CG.sealed(directory)
    if slot not in CAL.measured_slots(document):
        raise StandingError(f"slot {slot} is not measured in {directory.name}")
    trail = [r for r in audit(directory) if r["decision"] == decision]
    if not trail:
        raise StandingError(f"no correction of {decision} in {directory / GOLD_AUDIT}")
    cases, fixed_at = corrected_gold(directory)
    results = SG.read_results(directory, CAL.ROLE_SPECS[slot])
    for row in results:
        if row["answered_at"] < fixed_at:
            raise StandingError(
                f"{row['batch_id']}/{row['label']}: answered before the gold was fixed"
            )
    cp = cp or CAL.clopper_pearson()
    if slot == "image_prefilter":
        metrics = CG.measure_kinds(cases, results, cp)
    elif slot == "image_depicts":
        metrics = CG.measure_depicts(cases, results, cp)
    else:
        metrics = CG.measure_adversarial(cases, results, cp)
    failures = CAL.decide(slot, document, metrics)
    name = CAL.slot_role(slot)
    verdict: dict[str, Any] = {
        "role": name,
        "slot": slot,
        "model": RO.role(name).model,
        "effort": RO.role(name).effort,
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
        "rescored_under": decision,
        "corrections": [r["case_id"] for r in trail if r["role"] == slot],
        "audit_sha256": ST.file_sha256(directory / GOLD_AUDIT),
        "answers": len(results),
        "new_answers": 0,
        "decided_at": now(),
        "tier_move": None,
    }
    if failures:
        try:
            verdict["tier_move"] = RO.escalation(
                name, calibration_id=f"{directory.name}:{decision}", reason="; ".join(failures)
            )
        except RO.RoleError as exc:
            verdict["held"] = f"{exc}: the owner decides"
    path = directory / CAL.VERDICTS_DIR / f"{slot}.{decision}.json"
    ST.write_text_once(path, ST.json_text(verdict))
    return verdict


# ------------------------------------------------------------------------------------- releases
def _verdict_path(directory: Path, slot: str, verdict: Path) -> Path:
    path = verdict if verdict.is_absolute() else directory / CAL.VERDICTS_DIR / verdict.name
    if path.parent.resolve() != (directory / CAL.VERDICTS_DIR).resolve():
        raise StandingError(f"{verdict} is not a verdict of {directory}")
    if not path.is_file():
        raise StandingError(f"{path} does not exist")
    return path


def _bindings(directory: Path, slot: str) -> dict[str, str]:
    _, thresholds_sha, _ = CAL.sealed(directory)
    return {
        "thresholds_sha256": thresholds_sha,
        "gold_sha256": _gold_sha(directory),
        "role_sha256": RO.role_sha256(CAL.slot_role(slot)),
    }


def release(
    directory: Path,
    slot: str,
    *,
    verdict: Path,
    decided_by: str,
    reason: str,
    evidence: Sequence[Path],
    now: Callable[[], str] = CG._now,
) -> dict[str, Any]:
    """Let a held verdict of `slot` stand: `<dir>/releases/<slot>.json`, once."""
    document = CG.sealed(directory)
    if slot not in CAL.measured_slots(document):
        raise StandingError(f"slot {slot} is not measured in {directory.name}")
    if not decided_by.strip():
        raise StandingError("decided by is empty: a release names who decided it")
    if not reason.strip():
        raise StandingError("reason is empty: a release names why the verdict stands")
    path = _verdict_path(directory, slot, verdict)
    held = json.loads(path.read_text(encoding="utf-8"))
    if held["slot"] != slot or held["role"] != CAL.slot_role(slot):
        raise StandingError(f"{path} is the verdict of slot {held['slot']}, not {slot}")
    if held["passed"]:
        raise StandingError(f"{path} passed: there is nothing to release")
    if held["tier_move"] is not None:
        raise StandingError(f"{path} carries a tier move: the role moves up, it is not released")
    if not held.get("held"):
        raise StandingError(f"{path} failed but is not held at the top tier")
    record = {
        "slot": slot,
        "role": held["role"],
        "model": held["model"],
        "calibration": directory.name,
        "verdict": path.name,
        "verdict_sha256": ST.file_sha256(path),
        **_bindings(directory, slot),
        "decided_by": decided_by,
        "reason": reason,
        "evidence": CC.evidence_records(evidence),
        "decided_at": now(),
    }
    ST.write_text_once(directory / RELEASES_DIR / f"{slot}.json", ST.json_text(record))
    return record


def standing(directory: Path, slot: str) -> dict[str, Any]:
    """How `slot` stands in `directory`: its verdict passed, or a release still rests on what it was
    made on. Refused otherwise, naming what is missing or what moved.

    A slot whose role stands by the owner's decision (`roles.owner_standing`: D153 and D157 moved
    it with no calibration, D154) has no verdict of its own: the answer is that decision,
    in words, and the directory - sealed for the role's earlier model - is not asked."""
    by_owner = RO.owner_standing(CAL.slot_role(slot))
    if by_owner is not None:
        return {"slot": slot, **by_owner}
    CG.sealed(directory)
    plain = directory / CAL.VERDICTS_DIR / f"{slot}.json"
    if plain.is_file() and json.loads(plain.read_text(encoding="utf-8"))["passed"]:
        return {"slot": slot, "calibration": directory.name, "standing": CC.PASSED}
    path = directory / RELEASES_DIR / f"{slot}.json"
    if not path.is_file():
        raise StandingError(
            f"slot {slot} has no passing verdict and no release in {directory}: it does not stand"
        )
    record = json.loads(path.read_text(encoding="utf-8"))
    moved = f"the release of {slot} ({path})"
    verdict = directory / CAL.VERDICTS_DIR / record["verdict"]
    if not verdict.is_file() or ST.file_sha256(verdict) != record["verdict_sha256"]:
        raise StandingError(f"{moved}: the verdict changed after the release")
    now_bound = _bindings(directory, slot)
    for key, value in now_bound.items():
        if record[key] != value:
            raise StandingError(f"{moved}: {key} changed after the release")
    if not record["evidence"]:
        raise StandingError(f"{moved}: it rests on no evidence")
    try:
        CC.verify_evidence(record["evidence"], moved)
    except CC.CalibrationError as exc:
        raise StandingError(str(exc)) from exc
    return {
        "slot": slot,
        "calibration": directory.name,
        "standing": CC.RELEASED,
        "decided_by": record["decided_by"],
        "verdict": record["verdict"],
    }


def require_standing(slots: Sequence[str], root: Path) -> list[dict[str, Any]]:
    """The gate of the image lane: every slot of `slots` stands (`standing`) on its calibration under
    `root`, or one refusal names every slot that does not."""
    out, unmet = [], []
    for slot in slots:
        try:
            out.append(standing(root / STANDING[slot], slot))
        except (ST.StateError, RO.RoleError) as exc:
            unmet.append(f"{slot}: {exc}")
    if unmet:
        raise StandingError("the image roles do not stand: " + " | ".join(unmet))
    return out


def calibration_root() -> Path:
    """The calibration root of the main checkout (found through git's common directory)."""
    from identity import common as IC

    return IC.main_checkout() / CALIBRATION_ROOT


# ------------------------------------------------------------------------------------------ CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="image_roles/standing.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("correct", "rescore", "release"):
        sub.add_parser(name).add_argument("--dir", required=True, type=Path)
    c = sub.choices["correct"]
    c.add_argument("--case", required=True)
    c.add_argument("--truth", required=True, choices=TRUTHS)
    c.add_argument("--decision", required=True)
    c.add_argument("--reason", required=True)
    r = sub.choices["rescore"]
    r.add_argument("--slot", required=True, choices=CAL.MEASURED)
    r.add_argument("--decision", required=True)
    rel = sub.choices["release"]
    rel.add_argument("--slot", required=True, choices=CAL.MEASURED)
    rel.add_argument("--verdict", required=True, type=Path)
    rel.add_argument("--decided-by", required=True)
    rel.add_argument("--reason", required=True)
    rel.add_argument("--evidence", required=True, nargs="+", type=Path)
    check = sub.add_parser("check")
    check.add_argument("--slot", action="append", choices=sorted(STANDING), default=None)
    check.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "correct":
            payload: Any = correct(
                args.dir, case_id=args.case, truth=args.truth, decision=args.decision,
                reason=args.reason,
            )  # fmt: skip
        elif args.command == "rescore":
            payload = rescore(args.dir, args.slot, decision=args.decision)
        elif args.command == "release":
            payload = release(
                args.dir, args.slot, verdict=args.verdict, decided_by=args.decided_by,
                reason=args.reason, evidence=args.evidence,
            )  # fmt: skip
        else:
            payload = require_standing(
                args.slot or sorted(STANDING), args.root or calibration_root()
            )
    except (ST.StateError, RO.RoleError, CC.CalibrationError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
