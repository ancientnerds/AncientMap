"""The calibration of a Claude role against already-judged cases (owner decision D6, 2026-10-08).

Before a role (`roles.ROLES`) gives its first answer of a lane, it re-answers cases that were judged
already and is measured against them. The bar is O18's: at least the sealed share of judged units in
agreement, every question answered, and 0 false sources. The threshold is **sealed before the run**;
a role that fails moves up one tier (Haiku to Sonnet to Opus) and is calibrated again.

This is `mcode_driver`'s calibration without its `mcode exec` transport: the copy, the registered
calibration run and the comparison are `mcode_driver.copy_for_calibration`,
`register_calibration_run` and `compare_answers`; the agents that answer are the orchestrator's own
(workflow agents running as the role), through `opus_handoff.py answer --role`. Nothing here calls a
model or opens a socket.

    seal     bind a calibration id to a role, a pool (batches of an answered handoff) and a
             threshold, in `<root>/THRESHOLDS.json`: the cases, the sha256 of the recorded answers
             and of the role's registry entry and `roles.py`. Refused when the id is sealed, has a
             verdict or has begun, and for a pool a MiniMax agent answered (master plan X6).
    prepare  copy the pool into `<root>/<id>` without its answers (the recorded ones go to
             `RECORDED.json`) and register the calibration run. Refused when the pool or the role
             changed after the seal.
    compare  once the role has re-answered into `<root>/<id>`: unit by unit against the recorded
             answers, into `COMPARISON.json`. Refused for an answer that is not the role's model.
    verdict  `passed` and, when it did not, the tier move (or the hold at the top) into
             `<root>/verdicts/<id>.json`. `--false-sources` is the count of the spot check of every
             disagreement's URL and quote (O18), made by the orchestrator, never assumed.

    python scripts/remediation/calibrate_claude.py seal --id ID --role ROLE --handoff DIR \\
        --batches B [B ...] --threshold 0.9
    python scripts/remediation/calibrate_claude.py prepare --id ID --run RUN
    python scripts/remediation/calibrate_claude.py compare --id ID
    python scripts/remediation/calibrate_claude.py verdict --id ID --false-sources N
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import mcode_driver as D  # noqa: E402 - the copy, the calibration run and the comparison
import opus_handoff as OH  # noqa: E402 - the stamps
import roles as RO  # noqa: E402 - the registry
from phase3.ledger import utc_now  # noqa: E402 - the ledger's clock

#: The data root's calibration directory: `<id>/` copies, `THRESHOLDS.json`, `verdicts/`.
CALIBRATION_ROOT = D.REPO / "output" / "remediation" / "calibration"
THRESHOLDS_FILE = "THRESHOLDS.json"
VERDICTS_DIR = "verdicts"
RECORDED_FILE = "RECORDED.json"
COMPARISON_FILE = "COMPARISON.json"
ANSWER_SUFFIX = ".answer.json"
#: O18: a calibration allows no false source.
MAX_FALSE_SOURCES = 0


class CalibrationError(ValueError):
    """The calibration cannot take this step. Nothing is guessed and nothing is half-written."""


def _write_once(path: Path, payload: Any) -> None:
    if path.exists():
        raise CalibrationError(f"{path} exists: a calibration file is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read(path: Path, what: str) -> Any:
    if not path.exists():
        raise CalibrationError(f"{what}: {path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def _answer_files(handoff: Path, batches: Sequence[str]) -> list[Path]:
    """Every answer file of the batches, in path order."""
    files: list[Path] = []
    for batch in batches:
        folder = handoff / OH._batch_component(batch)
        if not folder.is_dir():
            raise CalibrationError(f"{handoff} has no batch {batch}")
        files.extend(sorted(f for f in folder.rglob(f"*{ANSWER_SUFFIX}") if f.is_file()))
    return files


def case_ids(handoff: Path, batches: Sequence[str]) -> list[str]:
    """`<batch>/<label>` of every recorded answer of the pool, in the order of `batches`."""
    return [
        f"{f.relative_to(handoff).parts[0]}/{f.name[: -len(ANSWER_SUFFIX)]}"
        for f in _answer_files(handoff, batches)
    ]


def pool_sha256(handoff: Path, batches: Sequence[str]) -> str:
    """The sha256 of the pool: every recorded answer's path and bytes, so a changed answer, a added
    case or a removed one changes it."""
    rows = [
        [f.relative_to(handoff).as_posix(), hashlib.sha256(f.read_bytes()).hexdigest()]
        for f in _answer_files(handoff, batches)
    ]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def _check_pool(handoff: Path, batches: Sequence[str]) -> None:
    """The recorded answers of the pool must be ground truth: written, stamped, and not by MiniMax
    (master plan X6: D10 re-checks every MiniMax answer, so none can judge a role)."""
    files = _answer_files(handoff, batches)
    if not files:
        raise CalibrationError(f"{handoff}: no recorded answer in {list(batches)}")
    for file in files:
        stamp = json.loads(file.read_text(encoding="utf-8")).get("model")
        if stamp == OH.MINIMAX_MODEL:
            raise CalibrationError(
                f"{file}: answered by MiniMax - a MiniMax answer is never ground truth (D10)"
            )
        if stamp not in OH.ANSWER_MODELS.values():
            raise CalibrationError(f"{file}: carries no stamp of ANSWER_MODELS ({stamp!r})")


def _seals(root: Path) -> dict[str, dict[str, Any]]:
    path = root / THRESHOLDS_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _sealed(root: Path, calibration_id: str) -> dict[str, Any]:
    seals = _seals(root)
    if calibration_id not in seals:
        raise CalibrationError(f"{calibration_id} is not sealed: seal its threshold first")
    return seals[calibration_id]


def _need_unchanged_role(seal: dict[str, Any]) -> None:
    if RO.role_sha256(seal["role"]) != seal["role_sha256"]:
        raise CalibrationError(
            f"the registry entry of role {seal['role']} changed after the seal: seal a new "
            "calibration"
        )


def seal(
    root: Path,
    *,
    calibration_id: str,
    role: str,
    handoff: Path,
    batches: Sequence[str],
    threshold: float,
    max_false_sources: int = MAX_FALSE_SOURCES,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """Seal `calibration_id` before its run, and return the seal.

    Refused: an id already sealed; a verdict for the id; a calibration copy of the id; a threshold
    that is not a number in (0, 1]; a role that is not registered; a pool with a missing batch, no
    recorded answer, or a MiniMax or unstamped answer."""
    OH._component(calibration_id, "calibration id")
    if isinstance(threshold, bool) or not isinstance(threshold, int | float):
        raise CalibrationError(f"threshold {threshold!r} is not a number")
    if not 0 < threshold <= 1:
        raise CalibrationError(f"threshold {threshold!r} is not in (0, 1]")
    entry = RO.role(role)
    if (root / VERDICTS_DIR / f"{calibration_id}.json").exists():
        raise CalibrationError(
            f"{calibration_id} has a verdict already: a threshold is sealed first"
        )
    if (root / calibration_id).exists():
        raise CalibrationError(
            f"{calibration_id} has already begun: {root / calibration_id} exists"
        )
    seals = _seals(root)
    if calibration_id in seals:
        raise CalibrationError(f"{calibration_id} is already sealed")
    _check_pool(handoff, batches)
    sealed = {
        "calibration_id": calibration_id,
        "role": role,
        "model": entry.model,
        "effort": entry.effort,
        "calibration_set": entry.calibration_set,
        "handoff": str(handoff.resolve()),
        "batches": list(batches),
        "case_ids": case_ids(handoff, batches),
        "pool_sha256": pool_sha256(handoff, batches),
        "role_sha256": RO.role_sha256(role),
        "roles_sha256": RO.registry_sha256(),
        "threshold": threshold,
        "max_false_sources": max_false_sources,
        "sealed_at": now(),
    }
    root.mkdir(parents=True, exist_ok=True)
    path = root / THRESHOLDS_FILE
    path.write_text(
        json.dumps({**seals, calibration_id: sealed}, ensure_ascii=False, indent=1, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return sealed


def prepare(root: Path, *, calibration_id: str, run: Path) -> dict[str, Any]:
    """Copy the sealed pool into `<root>/<id>` without its answers and register the calibration run
    (`mcode_driver.register_calibration_run`). The recorded answers go to `RECORDED.json`."""
    sealed = _sealed(root, calibration_id)
    _need_unchanged_role(sealed)
    handoff = Path(sealed["handoff"])
    if pool_sha256(handoff, sealed["batches"]) != sealed["pool_sha256"]:
        raise CalibrationError(f"the pool of {calibration_id} changed after the seal")
    out = root / calibration_id
    if out.exists():
        raise CalibrationError(f"{out} exists: a calibration copy is written once")
    recorded = D.copy_for_calibration(handoff, out, sealed["batches"])
    _write_once(out / RECORDED_FILE, recorded)
    calibration_run = D.register_calibration_run(run, handoff, out, sealed["batches"])
    return {
        "prepared": str(out),
        "calibration_run": str(calibration_run),
        "batches": list(sealed["batches"]),
        "labels": sorted(recorded),
        "questions": len(recorded),
    }


def _fresh_answers(out: Path, sealed: dict[str, Any]) -> dict[str, str]:
    """The role's answers in the copy, by label; each must be the role's model's."""
    fresh: dict[str, str] = {}
    for file in _answer_files(out, sealed["batches"]):
        answer = json.loads(file.read_text(encoding="utf-8"))
        named = RO.role_of(answer["answered_by"])
        if named is not None and named != sealed["role"]:
            raise CalibrationError(
                f"{file}: recorded under role {named}, but {sealed['calibration_id']} calibrates "
                f"role {sealed['role']}"
            )
        RO.require_stamp(sealed["role"], answer["model"])
        fresh[file.name[: -len(ANSWER_SUFFIX)]] = answer["text"]
    return fresh


def compare(root: Path, *, calibration_id: str) -> dict[str, Any]:
    """The role's fresh answers against the recorded ones, unit by unit (`compare_answers`); written
    once to `COMPARISON.json`. A question without a fresh answer is unanswered, never agreement."""
    sealed = _sealed(root, calibration_id)
    out = root / calibration_id
    recorded_path = out / RECORDED_FILE
    if not recorded_path.exists():
        raise CalibrationError(f"{calibration_id} is not prepared: {recorded_path} is missing")
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    fresh = _fresh_answers(out, sealed)
    report = D.compare_answers(sealed["role"], sorted(recorded), recorded, fresh).to_dict()
    _write_once(out / COMPARISON_FILE, report)
    return report


def _failures(report: dict[str, Any], sealed: dict[str, Any], false_sources: int) -> list[str]:
    failures: list[str] = []
    if report["unanswered"]:
        failures.append(f"{len(report['unanswered'])} question(s) unanswered")
    if report["units"] == 0:
        failures.append("no judged unit was measured")
    elif report["agreement"] < sealed["threshold"]:
        failures.append(
            f"agreement {report['agreement']} is below the sealed threshold {sealed['threshold']}"
        )
    if false_sources > sealed["max_false_sources"]:
        failures.append(
            f"{false_sources} false source(s) counted, {sealed['max_false_sources']} allowed"
        )
    return failures


def verdict(
    root: Path,
    *,
    calibration_id: str,
    false_sources: int,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """The verdict of a compared calibration, written once to `<root>/verdicts/<id>.json`.

    `false_sources` is the orchestrator's own count from the spot check of every disagreement's
    URL and quote (O18): it is required, never assumed. A failing role carries its `tier_move`
    (`roles.escalation`); at the top tier it carries `held` instead, because there is nothing above
    Opus and the owner decides."""
    if isinstance(false_sources, bool) or not isinstance(false_sources, int) or false_sources < 0:
        raise CalibrationError(f"false_sources {false_sources!r} is not a count of 0 or more")
    sealed = _sealed(root, calibration_id)
    _need_unchanged_role(sealed)
    comparison_path = root / calibration_id / COMPARISON_FILE
    if not comparison_path.exists():
        raise CalibrationError(f"{calibration_id} is not compared: {comparison_path} is missing")
    report = json.loads(comparison_path.read_text(encoding="utf-8"))
    failures = _failures(report, sealed, false_sources)
    result: dict[str, Any] = {
        "calibration_id": calibration_id,
        "role": sealed["role"],
        "model": sealed["model"],
        "passed": not failures,
        "agreement": report["agreement"],
        "threshold": sealed["threshold"],
        "units": report["units"],
        "agreed": report["agreed"],
        "unanswered": report["unanswered"],
        "false_sources": false_sources,
        "tier_move": None,
        "decided_at": now(),
    }
    if failures:
        try:
            result["tier_move"] = RO.escalation(
                sealed["role"], calibration_id=calibration_id, reason="; ".join(failures)
            )
        except RO.RoleError as exc:
            result["held"] = f"{exc}: the owner decides"
    _write_once(root / VERDICTS_DIR / f"{calibration_id}.json", result)
    return result


# ------------------------------------------------------------------------------------------ CLI
def main(argv: Iterable[str] | None = None) -> int:
    """0: the step is done (and a verdict passed). 1: the verdict is a fail. 2: refused."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="calibrate-claude", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seal", "prepare", "compare", "verdict"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, default=CALIBRATION_ROOT)
        command.add_argument("--id", required=True, dest="calibration_id")
    seal_cli = sub.choices["seal"]
    seal_cli.add_argument("--role", required=True)
    seal_cli.add_argument("--handoff", required=True, type=Path)
    seal_cli.add_argument("--batches", required=True, nargs="+")
    seal_cli.add_argument("--threshold", required=True, type=float)
    sub.choices["prepare"].add_argument("--run", required=True, type=Path)
    sub.choices["verdict"].add_argument("--false-sources", required=True, type=int)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "seal":
            payload = seal(
                args.root,
                calibration_id=args.calibration_id,
                role=args.role,
                handoff=args.handoff,
                batches=args.batches,
                threshold=args.threshold,
            )
        elif args.command == "prepare":
            payload = prepare(args.root, calibration_id=args.calibration_id, run=args.run)
        elif args.command == "compare":
            payload = compare(args.root, calibration_id=args.calibration_id)
        else:
            payload = verdict(
                args.root, calibration_id=args.calibration_id, false_sources=args.false_sources
            )
    except (CalibrationError, RO.RoleError, OH.HandoffError, D.DriverError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if args.command != "verdict" or payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
