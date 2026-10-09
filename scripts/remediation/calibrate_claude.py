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
             A pool whose gold is not an answer but a fact (a bucket a hand check confirmed, an
             audit's keep or revert) is sealed with `--truth FILE`: its batches carry only the
             questions, the file maps each case to its expected value and is pinned with them.
             `--comparison` names how `compare` measures it (`all` units, or one a tool registers,
             `fields/pools.py`), `--max-undecided-excess` bounds how far the fresh rate of cells
             nobody decided may lie above the gold's.
    prepare  copy the pool into `<root>/<id>` without its answers (the recorded ones go to
             `RECORDED.json`) and register the calibration run. Refused when the pool or the role
             changed after the seal.
    compare  once the role has re-answered into `<root>/<id>`: unit by unit against the recorded
             answers, into `COMPARISON.json`. Refused for an answer that is not the role's model.
    verdict  `passed` and, when it did not, the tier move (or the hold at the top) into
             `<root>/verdicts/<id>.json`. `--false-sources` is the count of the spot check of every
             disagreement's URL and quote (O18), made by the orchestrator, never assumed.

    python scripts/remediation/calibrate_claude.py seal --id ID --role ROLE --handoff DIR \\
        --batches B [B ...] --threshold 0.9 [--truth FILE] [--comparison NAME] \\
        [--max-undecided-excess 0.1]
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
PROMPT_SUFFIX = ".prompt.txt"
#: How `compare` measures a pool: every judged unit (`mcode_driver.compare_answers`), the default.
#: A pool whose gold is not a recorded answer, or that measures with a rule of its own, names another
#: comparison at the seal and is compared by the tool that owns it (`compare(comparators=...)`).
COMPARE_ALL = "all"
#: O18: a calibration allows no false source.
MAX_FALSE_SOURCES = 0
#: The name a lane WC handoff starts with (`wc-pilot-2026-09-27-r1`): its pools carry the lane's
#: conditions (`seal(lane=...)`).
LANE_WC_PREFIX = "wc-"


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


def _files(handoff: Path, batches: Sequence[str], suffix: str) -> list[Path]:
    """Every file with this suffix in the batches, in path order."""
    files: list[Path] = []
    for batch in batches:
        folder = handoff / OH._batch_component(batch)
        if not folder.is_dir():
            raise CalibrationError(f"{handoff} has no batch {batch}")
        files.extend(sorted(f for f in folder.rglob(f"*{suffix}") if f.is_file()))
    return files


def _answer_files(handoff: Path, batches: Sequence[str]) -> list[Path]:
    """Every answer file of the batches, in path order."""
    return _files(handoff, batches, ANSWER_SUFFIX)


def case_ids(handoff: Path, batches: Sequence[str], *, truth: bool = False) -> list[str]:
    """`<batch>/<label>` of every case of the pool, in the order of `batches`: every recorded answer,
    or - for a pool whose gold is a truth file - every question."""
    suffix = PROMPT_SUFFIX if truth else ANSWER_SUFFIX
    return [
        f"{f.relative_to(handoff).parts[0]}/{f.name[: -len(suffix)]}"
        for f in _files(handoff, batches, suffix)
    ]


def pool_sha256(handoff: Path, batches: Sequence[str], truth: Path | None = None) -> str:
    """The sha256 of the pool: every recorded answer's path and bytes, so a changed answer, a added
    case or a removed one changes it. A truth pool is its questions and its truth file."""
    suffix = ANSWER_SUFFIX if truth is None else PROMPT_SUFFIX
    rows = [
        [f.relative_to(handoff).as_posix(), hashlib.sha256(f.read_bytes()).hexdigest()]
        for f in _files(handoff, batches, suffix)
    ]
    if truth is not None:
        rows.append(["truth", hashlib.sha256(truth.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def _check_truth_pool(handoff: Path, batches: Sequence[str], truth: Path) -> None:
    """A truth pool carries the questions and no recorded answer, and its truth file names exactly
    those cases: a case without a truth value measures nothing, a truth value without a case is a
    different pool."""
    if not truth.is_file():
        raise CalibrationError(f"{truth} is not there")
    if _answer_files(handoff, batches):
        raise CalibrationError(
            f"{handoff}: a truth pool carries no recorded answer - the gold is the truth file"
        )
    wanted = {f.name[: -len(PROMPT_SUFFIX)] for f in _files(handoff, batches, PROMPT_SUFFIX)}
    if not wanted:
        raise CalibrationError(f"{handoff}: no question in {list(batches)}")
    held = json.loads(truth.read_text(encoding="utf-8"))
    if not isinstance(held, dict) or set(held) != wanted:
        raise CalibrationError(
            f"{truth} names {sorted(set(held) ^ wanted)[:3]} that the questions of the pool do "
            "not (or the other way round): it maps exactly the pool's cases"
        )


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
    max_undecided_excess: float | None = None,
    comparison: str = COMPARE_ALL,
    truth: Path | None = None,
    lane: dict[str, Any] | None = None,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """Seal `calibration_id` before its run, and return the seal. `lane` is a lane's own pass
    conditions (lane WC: the known errors and the verdict merge, `wc/calibration.py seal`), sealed
    with the threshold: `compare` of this module refuses such a calibration and `verdict` refuses one
    whose comparison does not carry the lane's `lane_failures`.

    Refused: an id already sealed; a verdict for the id; a calibration copy of the id; a threshold
    that is not a number in (0, 1]; an undecided-rate bound outside [0, 1]; a role that is not
    registered; a pool with a missing batch, no recorded answer, or a MiniMax or unstamped answer;
    a truth pool that carries an answer or whose truth file is not exactly its cases; a pool of
    lane WC (a handoff named `wc-...`) without the lane's conditions."""
    OH._component(calibration_id, "calibration id")
    OH._component(comparison, "comparison")
    if isinstance(threshold, bool) or not isinstance(threshold, int | float):
        raise CalibrationError(f"threshold {threshold!r} is not a number")
    if not 0 < threshold <= 1:
        raise CalibrationError(f"threshold {threshold!r} is not in (0, 1]")
    if max_undecided_excess is not None and (
        isinstance(max_undecided_excess, bool)
        or not isinstance(max_undecided_excess, int | float)
        or not 0 <= max_undecided_excess <= 1
    ):
        raise CalibrationError(f"max_undecided_excess {max_undecided_excess!r} is not in [0, 1]")
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
    if handoff.name.startswith(LANE_WC_PREFIX) and lane is None:
        raise CalibrationError(
            f"{handoff.name} is a lane WC pool: seal it with `wc/calibration.py seal`, which seals "
            "the known errors with the threshold"
        )
    if truth is None:
        _check_pool(handoff, batches)
    else:
        _check_truth_pool(handoff, batches, truth)
    sealed = {
        "calibration_id": calibration_id,
        "role": role,
        "model": entry.model,
        "effort": entry.effort,
        "calibration_set": entry.calibration_set,
        "handoff": str(handoff.resolve()),
        "batches": list(batches),
        "case_ids": case_ids(handoff, batches, truth=truth is not None),
        "pool_sha256": pool_sha256(handoff, batches, truth),
        "truth": None if truth is None else str(truth.resolve()),
        "comparison": comparison,
        "max_undecided_excess": max_undecided_excess,
        "role_sha256": RO.role_sha256(role),
        "roles_sha256": RO.registry_sha256(),
        "threshold": threshold,
        "max_false_sources": max_false_sources,
        "sealed_at": now(),
    }
    if lane is not None:
        sealed["lane"] = lane
    root.mkdir(parents=True, exist_ok=True)
    path = root / THRESHOLDS_FILE
    path.write_text(
        json.dumps({**seals, calibration_id: sealed}, ensure_ascii=False, indent=1, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return sealed


def prepare(
    root: Path,
    *,
    calibration_id: str,
    run: Path,
    register: Callable[[Path, Path, Path, Sequence[str]], Path] = D.register_calibration_run,
) -> dict[str, Any]:
    """Copy the sealed pool into `<root>/<id>` without its answers and register the calibration run
    (`register`, by default `mcode_driver.register_calibration_run`; a lane whose pool is a kind of
    round that one does not know passes its own, as `wc/calibration.py` does for the judge's). The
    recorded answers go to `RECORDED.json`."""
    sealed = _sealed(root, calibration_id)
    _need_unchanged_role(sealed)
    handoff = Path(sealed["handoff"])
    truth = None if sealed.get("truth") is None else Path(sealed["truth"])
    if truth is not None and not truth.is_file():
        raise CalibrationError(f"the truth file of {calibration_id} is gone: {truth}")
    if pool_sha256(handoff, sealed["batches"], truth) != sealed["pool_sha256"]:
        raise CalibrationError(f"the pool of {calibration_id} changed after the seal")
    out = root / calibration_id
    if out.exists():
        raise CalibrationError(f"{out} exists: a calibration copy is written once")
    recorded = D.copy_for_calibration(handoff, out, sealed["batches"])
    _write_once(out / RECORDED_FILE, recorded)
    calibration_run = register(run, handoff, out, sealed["batches"])
    return {
        "prepared": str(out),
        "calibration_run": str(calibration_run),
        "batches": list(sealed["batches"]),
        "labels": sorted(recorded) or sorted(c.split("/", 1)[1] for c in sealed["case_ids"]),
        "questions": len(recorded) or len(sealed["case_ids"]),
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


#: A comparison: the seal, the recorded answers by label, the fresh answers by label and the
#: calibration copy -> the report `verdict` reads (`units`, `agreed`, `agreement`, `unanswered`,
#: `disagreements`, and `undecided_excess` when the seal bounds it).
Comparator = Callable[[dict[str, Any], dict[str, str], dict[str, str], Path], dict[str, Any]]


def _compare_all(
    sealed: dict[str, Any], recorded: dict[str, str], fresh: dict[str, str], out: Path
) -> dict[str, Any]:
    return D.compare_answers(sealed["role"], sorted(recorded), recorded, fresh).to_dict()


COMPARATORS: dict[str, Comparator] = {COMPARE_ALL: _compare_all}


def compare(
    root: Path, *, calibration_id: str, comparators: dict[str, Comparator] | None = None
) -> dict[str, Any]:
    """The role's fresh answers against the recorded ones, unit by unit (`compare_answers`); written
    once to `COMPARISON.json`. A question without a fresh answer is unanswered, never agreement.

    A seal that names another comparison (`comparators` of the tool that owns it) is measured by
    that one; a comparison nobody here knows is refused by name."""
    sealed = _sealed(root, calibration_id)
    if "lane" in sealed:
        raise CalibrationError(
            f"{calibration_id} was sealed with its lane's conditions: compare it with the lane's "
            "own command (`wc/calibration.py compare`)"
        )
    kind = sealed.get("comparison", COMPARE_ALL)
    comparator = {**COMPARATORS, **(comparators or {})}.get(kind)
    if comparator is None:
        raise CalibrationError(
            f"{calibration_id} is sealed for the comparison {kind!r}, which this tool does not "
            "make: run the tool that owns it (scripts/remediation/fields/pools.py compare)"
        )
    out = root / calibration_id
    recorded_path = out / RECORDED_FILE
    if not recorded_path.exists():
        raise CalibrationError(f"{calibration_id} is not prepared: {recorded_path} is missing")
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    fresh = _fresh_answers(out, sealed)
    report = comparator(sealed, recorded, fresh, out)
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
    # a lane's own conditions, named by the lane when it compared (`wc/calibration.py`: a known
    # error the role missed, more extra WRONG verdicts than the lane allows)
    failures.extend(report.get("lane_failures", []))
    if false_sources > sealed["max_false_sources"]:
        failures.append(
            f"{false_sources} false source(s) counted, {sealed['max_false_sources']} allowed"
        )
    bound = sealed.get("max_undecided_excess")
    if bound is not None:
        excess = report.get("undecided_excess")
        if excess is None:
            failures.append("the seal bounds the undecided rate and the comparison reports none")
        elif excess > bound:
            failures.append(
                f"the fresh undecided rate is {excess} above the gold's, {bound} allowed"
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
    if "lane" in sealed and "lane_failures" not in report:
        raise CalibrationError(
            f"{calibration_id} was sealed with its lane's conditions, but its comparison carries no "
            "`lane_failures`: it was not compared with the lane's command"
        )
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
        "undecided_excess": report.get("undecided_excess"),
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


def require_passed(root: Path, needs: Iterable[tuple[str, str]]) -> None:
    """Refuse unless every `(role, comparison)` of `needs` has a passing verdict whose seal names the
    role and the comparison and binds the role's registry entry as it is now: the calibration of a
    role that was edited (a tier move) since its seal no longer vouches for it, and neither does a
    failed one. All the unmet needs are named in one refusal."""
    seals = _seals(root)
    verdicts_dir = root / VERDICTS_DIR
    passed = [
        seals[path.stem]
        for path in sorted(verdicts_dir.glob("*.json"))
        if path.stem in seals and json.loads(path.read_text(encoding="utf-8"))["passed"]
    ]
    unmet = [
        f"{role}/{comparison}"
        for role, comparison in needs
        if not any(
            seal["role"] == role
            and seal["comparison"] == comparison
            and seal["role_sha256"] == RO.role_sha256(role)
            for seal in passed
        )
    ]
    if unmet:
        raise CalibrationError(
            f"no passing verdict under {verdicts_dir} for {', '.join(unmet)} (sealed against the "
            "role's registry entry as it is now): calibrate before the lane writes"
        )


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
    seal_cli.add_argument("--comparison", default=COMPARE_ALL)
    seal_cli.add_argument("--max-undecided-excess", type=float, default=None)
    seal_cli.add_argument(
        "--truth",
        type=Path,
        default=None,
        help="a truth pool: the file mapping each case to its gold",
    )
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
                comparison=args.comparison,
                max_undecided_excess=args.max_undecided_excess,
                truth=args.truth,
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
