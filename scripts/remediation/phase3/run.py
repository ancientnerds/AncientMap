"""The Phase-3 CLI: `plan`, `prepare`, `fetch`, `judge`, `status`.

The runner the audit asks for (`output/remediation/AUDIT_LOG.md`: "build the Phase-3 runner,
which must emit the `defect` flag and the `true_but_no_correction` verdict ... and which should
run one instrumented batch of 15 sites with real token accounting before scaling to 1,813") is
built in three pieces: the schema and the plan, then the evidence fetch, then the model call.

The sequence is plan -> prepare -> fetch -> judge. `judge` reads the `input.json` that `prepare`
wrote, so a batch that was never prepared has no input to judge and raises rather than judging an
empty one.

* `plan`   - assign the Phase-3 worklist to batches of K (default 15, brief decision 12) and
             write them as JSONL. Deterministic by construction: the worklist's own order is
             preserved, batch ids come from the ordinal, keys are sorted, the newline is
             pinned, and **no timestamp is written**. Two runs on the same input are
             byte-identical (proved in `tests/remediation/test_phase3_runner.py` and in
             `output/remediation/phase3_runner/PIECE1.md`).
* `prepare` - materialise one input file per batch under the run directory. No fetch, no model.
* `fetch`   - collect the evidence a batch's findings buy (`phase3/fetch_stage.py`). **Offline
             unless `--live` is given**: without it the command only lists the targets and the
             URLs, so what a batch would cost is reviewable before it costs a request.
* `judge`   - run one stage over one prepared batch (`phase3/model_stage.py`). **Dry run unless
             `--live` is given**: without it the command renders the exact argv and the exact
             prompt text of every call in the batch and starts no process, so a batch is readable
             - and its prompt sizes visible - before any money is spent.
* `status` - read the run directory and the ledger and report what is actually on disk.

Fail-closed: a worklist record whose shape is not the one the run needs raises, rather than
being skipped. A silently smaller plan is the failure this whole phase is paid to avoid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Dual use: `python -m phase3.run` and `python scripts/remediation/phase3/run.py`. The package
# is not installed, so the parent directory must be importable first.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import ledger as L  # noqa: E402
from phase3.model import Stage  # noqa: E402

#: Ratified run shape (brief decision 12): 15 sites per run, two stages per batch.
DEFAULT_BATCH_SIZE = 15

#: The marker a batch carries when it comes from the snapshot plan instead of the worklist
#: (`phase3/snapshot_plan.py`, piece 5). It is part of the batch shape, so it lives here with it,
#: and it is what tells `judge` that a batch's unit is one (site, field) rather than one site: a
#: discover batch is judged one call per (site, field), one question per call, and refuses the
#: reviewer stage, which judges a finder's finding and has none here.
DISCOVER_PASS = "discover"  # noqa: S105 - a batch marker, not a credential (bandit reads "PASS")

REPO = Path(__file__).resolve().parents[3]
DEFAULT_WORKLIST = REPO / "output" / "remediation" / "phase3_worklist" / "WORKLIST.jsonl"
DEFAULT_RUN_DIR = REPO / "output" / "remediation" / "phase3_runner" / "runs"
DEFAULT_PLAN = REPO / "output" / "remediation" / "phase3_runner" / "PLAN.jsonl"
DEFAULT_LEDGER = REPO / "output" / "remediation" / "phase3_runner" / "LEDGER.jsonl"
#: Where the cross-process host pace keeps its lock and stamp files. Machine-local by design
#: (`fetch_stage.HostPacer`): two machines share no per-host state, so what this supports is "this
#: machine does not hammer a host", not a worldwide rate limit.
DEFAULT_PACING_DIR = REPO / "output" / "remediation" / "logs" / "pacing"


class InputError(ValueError):
    """The input is not the shape the run needs. Raised, never worked around."""


@dataclass(frozen=True)
class Batch:
    """One agent run: the sites one stage processes, in worklist order."""

    batch_id: str
    ordinal: int
    sites: tuple[dict[str, Any], ...]
    #: `"pass"` in the written JSON, and only when it is set: the worklist plan's bytes are pinned
    #: (piece 1's hash) and gaining a field would change them. `None` is the finding-driven plan.
    pass_name: str | None = None

    def to_json(self) -> str:
        payload = {"batch_id": self.batch_id, "ordinal": self.ordinal, "sites": list(self.sites)}
        if self.pass_name is not None:
            payload["pass"] = self.pass_name
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file. Every line must be a JSON object; nothing is skipped."""
    if not path.exists():
        raise FileNotFoundError(f"no such file: {path}")
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            text = raw.strip()
            if not text:
                raise InputError(f"{path}:{lineno}: empty line")
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InputError(f"{path}:{lineno}: not JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise InputError(f"{path}:{lineno}: expected a JSON object, got {type(record)}")
            records.append(record)
    return records


def select_phase3(records: list[dict[str, Any]], origin: Path) -> list[dict[str, Any]]:
    """The Phase-3 records, in file order (the worklist is already worst-first).

    A record without the `phase3` flag or without a `site_id` is not "not Phase 3" - it is a
    record this runner cannot place, so it raises.
    """
    selected: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if "phase3" not in record:
            raise InputError(f"{origin}: record {index} carries no `phase3` flag")
        if "site_id" not in record or not record["site_id"]:
            raise InputError(f"{origin}: record {index} carries no `site_id`")
        if record["phase3"] is True:
            selected.append(record)
    return selected


def assign_batches(
    records: list[dict[str, Any]], size: int, *, pass_name: str | None = None
) -> list[Batch]:
    """Chunk the records, preserving their order. `size` must be a positive integer."""
    if size < 1:
        raise InputError(f"batch size must be >= 1, got {size}")
    return [
        Batch(
            batch_id=f"batch-{ordinal:04d}",
            ordinal=ordinal,
            sites=tuple(records[start : start + size]),
            pass_name=pass_name,
        )
        for ordinal, start in enumerate(range(0, len(records), size), start=1)
    ]


def write_batches(path: Path, batches: list[Batch]) -> None:
    """Write the plan: one JSON object per batch, sorted keys, LF newlines, no timestamp."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(batch.to_json() + "\n" for batch in batches)
    path.write_text(body, encoding="utf-8", newline="\n")


def cmd_plan(args: argparse.Namespace) -> int:
    """Write the plan: the worklist's records, or every site of the snapshot (piece 5)."""
    if args.from_snapshot:
        return _plan_from_snapshot(args)
    if args.site_ids:
        raise InputError(
            "--site-ids selects sites of the snapshot plan; without --from-snapshot it means "
            "nothing, and the worklist plan ignores it"
        )
    records = read_jsonl(Path(args.worklist))
    selected = select_phase3(records, Path(args.worklist))
    batches = assign_batches(selected, args.batch_size)
    write_batches(Path(args.out), batches)
    print(
        json.dumps(
            {
                "batches": len(batches),
                "batch_size": args.batch_size,
                "out": str(args.out),
                "pass": None,
                "sha256": _sha256(Path(args.out)),
                "sites": len(selected),
                "worklist": str(args.worklist),
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


def _sha256(path: Path) -> str:
    """The written plan's own hash. Printed so an operator can compare it without a second tool."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _plan_from_snapshot(args: argparse.Namespace) -> int:
    """The discover plan: one record per snapshot site, one finding per field (piece 5).

    Imported here because `snapshot_plan` imports this module's `InputError` (the same shim
    `fetch_stage` uses), so a top-level import would be circular.
    """
    from phase3 import snapshot_plan as SP

    if args.worklist != str(DEFAULT_WORKLIST):
        raise InputError(
            "--worklist and --from-snapshot are two different inputs: the worklist plan reads "
            "census findings, the snapshot plan reads the database export"
        )
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else SP.DEFAULT_SNAPSHOT_DIR
    site_ids = SP.read_site_ids(Path(args.site_ids)) if args.site_ids else None
    records = SP.build_discover_sites(snapshot_dir=snapshot_dir, site_ids=site_ids)
    batches = assign_batches(records, args.batch_size, pass_name=DISCOVER_PASS)
    write_batches(Path(args.out), batches)
    print(
        json.dumps(
            {
                "batches": len(batches),
                "batch_size": args.batch_size,
                "calls": len(records) * len(SP.DISCOVER_FIELDS),
                "fields": list(SP.DISCOVER_FIELDS),
                "out": str(args.out),
                "pass": DISCOVER_PASS,
                "sha256": _sha256(Path(args.out)),
                "site_ids": str(args.site_ids) if args.site_ids else None,
                "sites": len(records),
                "snapshot_dir": str(snapshot_dir),
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    """Materialise the batch inputs under the run directory. No network, no model call."""
    plan = Path(args.plan)
    batches = read_jsonl(plan)
    run_dir = Path(args.run_dir)
    wanted = set(args.batch_id or [])
    written: list[str] = []
    seen: set[str] = set()
    for line_no, batch in enumerate(batches, start=1):
        batch_id = batch.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id:
            raise InputError(f"{plan}:{line_no}: batch without a batch_id")
        if batch_id in seen:
            raise InputError(f"{plan}:{line_no}: duplicate batch_id {batch_id}")
        seen.add(batch_id)
        if wanted and batch_id not in wanted:
            continue
        target = run_dir / batch_id / "input.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(batch, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(batch_id)
    if wanted and wanted != set(written):
        raise InputError(f"asked for batches that are not in the plan: {sorted(wanted - seen)}")
    print(
        json.dumps(
            {"batches": len(written), "run_dir": str(run_dir), "written": written},
            indent=1,
            sort_keys=True,
        )
    )
    return 0


def _run_dir_state(run_dir: Path) -> dict[str, Any]:
    """What is on disk. A run directory that does not exist yet is a fact, not an error.

    `phase3-run status` is the operator's own report command, and it ran on a fresh run for the
    first time in the first live batch - where it died with `FileNotFoundError` before it reported
    anything. Nothing under the run directory is invented here: absent means `exists: false`.
    """
    if not run_dir.exists():
        return {
            "batches_with_input": [],
            "batches_with_result": [],
            "exists": False,
            "run_dir": str(run_dir),
        }
    prepared: list[str] = []
    results: list[str] = []
    for child in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        if (child / "input.json").exists():
            prepared.append(child.name)
        if (child / "result.json").exists():
            results.append(child.name)
    return {
        "batches_with_input": prepared,
        "batches_with_result": results,
        "exists": True,
        "run_dir": str(run_dir),
    }


def _ledger_state(ledger: Path) -> dict[str, Any]:
    """The ledger, totalled. **Absence is the only thing handled here.**

    A ledger that does not exist yet means nothing has been measured: zero lines, zero dollars -
    a sum over no lines, which is what the numbers say rather than a guess. A ledger that exists
    and cannot be read (a truncated line, a byte that is not JSON, no permission) is a *different*
    fact and raises out of `L.summarise`: an unreadable ledger must never be reported as an empty
    one.
    """
    if not ledger.exists():
        empty = L.LedgerSummary()
        return {
            "lines": 0,
            "measured": False,
            "path": str(ledger),
            "reason": f"no ledger at {ledger}: nothing has been measured yet",
            "stages": {},
            "total": empty.total.as_dict(),
        }
    summary = L.summarise(ledger)
    return {
        "lines": summary.lines,
        "measured": True,
        "path": str(ledger),
        "stages": {stage: totals.as_dict() for stage, totals in summary.by_stage.items()},
        "total": summary.total.as_dict(),
    }


def cmd_status(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = _run_dir_state(Path(args.run_dir))
    if args.plan:
        plan = Path(args.plan)
        payload["plan"] = str(plan)
        payload["planned"] = plan.exists()
        if plan.exists():
            batches = read_jsonl(plan)
            payload["planned_batches"] = len(batches)
            payload["planned_sites"] = sum(len(b.get("sites") or []) for b in batches)
    if args.ledger:
        payload["ledger"] = _ledger_state(Path(args.ledger))
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


def _single_batch(path: Path, batch_id: str) -> dict[str, Any]:
    """The one batch prepared at `path`. Not zero, not two: a missing input is not an empty run."""
    records = read_jsonl(path)
    if len(records) != 1:
        raise InputError(f"{path}: expected exactly one batch, found {len(records)}")
    if records[0].get("batch_id") != batch_id:
        raise InputError(f"{path}: holds batch {records[0].get('batch_id')!r}, not {batch_id!r}")
    return records[0]


def cmd_fetch(args: argparse.Namespace) -> int:
    """Collect evidence for one prepared batch. Nothing happens unless `--live` is passed."""
    # Imported here because `fetch_stage` imports this module's `InputError`.
    from phase3 import fetch_stage as F

    run_dir = Path(args.run_dir)
    batch_id = args.batch_id
    batch = _single_batch(run_dir / batch_id / "input.json", batch_id)
    stage = Stage(args.stage)

    if not args.live:
        targets = [t for site in batch["sites"] for t in F.targets_for_site(site)]
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "live": False,
                    "run_dir": str(run_dir),
                    "sites": len(batch["sites"]),
                    "stage": stage.value,
                    "targets": [
                        {
                            "feature": t.feature,
                            "label": t.label,
                            "reason": t.reason,
                            "url": t.url,
                        }
                        for t in targets
                    ],
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 0

    http = F.HttpFetcher(timeout=args.timeout)
    # The pace sits on the `Fetcher` seam, so it covers the reachability probe, every retry and every
    # target without a call site having to remember. The transport is what closes: `Fetcher` has one
    # method (`get`), and `PacedFetcher` is a decorator over it - a pace, not a second owner of the
    # connection.
    fetcher: F.Fetcher = http
    if args.pacing_dir:
        fetcher = F.PacedFetcher(http, F.HostPacer(Path(args.pacing_dir)))
    try:
        report = F.collect_batch(
            batch=batch,
            fetcher=fetcher,
            store=F.EvidenceStore(run_dir / batch_id / "evidence"),
            ledger=L.Ledger(Path(args.ledger)),
            stage=stage,
        )
    finally:
        http.close()

    # No `except F.TransportFailure` here any more, and that is the fix, not a relaxation: a
    # transport failure is one target's recorded outcome now (`phase3/fetch_stage.py`), written to
    # the ledger with its reason and to this report, so the batch continues and the report below
    # shows it. Exit code 2 was exactly the defect the first live batch exposed.
    F.write_report(run_dir / batch_id / "fetch.json", report)
    payload = json.loads(report.to_json())
    payload.update({"ledger": str(args.ledger), "live": True, "run_dir": str(run_dir)})
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    """Run one stage over one prepared batch. No model call unless `--live` is passed."""
    # Imported here because `model_stage` imports `fetch_stage`, which imports this module.
    from phase3 import fetch_stage as F
    from phase3 import model_stage as MS

    run_dir = Path(args.run_dir)
    batch_id = args.batch_id
    batch = _single_batch(run_dir / batch_id / "input.json", batch_id)
    stage = Stage(args.stage)
    store = F.EvidenceStore(run_dir / batch_id / "evidence")
    # The batch's own fetch report is the record of what could not be read (piece 4). Reading it
    # for the dry run too keeps the preview and the live prompt the same text: a preview that hid
    # a failed target would be a preview of a call nobody is going to make.
    failures = MS.read_fetch_failures(run_dir / batch_id / "fetch.json")

    if batch.get("pass") == DISCOVER_PASS:
        return _judge_discover(
            args, batch=batch, run_dir=run_dir, batch_id=batch_id, failures=failures
        )
    if batch.get("pass") is not None:
        raise InputError(
            f"{batch_id}: the batch carries pass={batch.get('pass')!r}, which this runner does not "
            f"know (known: {DISCOVER_PASS!r}; a batch without `pass` is the finding-driven plan)"
        )

    if not args.live:
        prepared = MS.prepare_batch(
            batch=batch, store=store, stage=stage, allow_absent=True, failures=failures
        )
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "calls": len(prepared),
                    "live": False,
                    "model": MS.MODEL,
                    "program": MS.PROGRAM,
                    "run_dir": str(run_dir),
                    "sites": [
                        {
                            "argv": MS.pi_argv(),
                            "evidence": [
                                {
                                    "chars": e.chars,
                                    "failure": e.failure,
                                    "feature": e.feature,
                                    "path": str(e.path),
                                    "present": e.present,
                                    "url": e.url,
                                }
                                for e in item.excerpts
                            ],
                            "label": item.call.label,
                            "prompt": item.call.prompt,
                            "prompt_chars": len(item.call.prompt),
                            "site_id": item.call.site_id,
                        }
                        for item in prepared
                    ],
                    "stage": stage.value,
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 0

    runner = MS.PiRunner(timeout=args.timeout)
    answers = F.EvidenceStore(run_dir / batch_id / "answers")
    try:
        report = MS.judge_batch(
            batch=batch,
            runner=runner,
            store=store,
            answers=answers,
            ledger=L.Ledger(Path(args.ledger)),
            stage=stage,
            failures=failures,
        )
    except MS.ModelCallFailed as exc:
        # Fail-closed and loud: the batch stops at the call that could not be measured. Answers
        # already stored stay, and the ledger already carries the calls that did happen.
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "error": str(exc),
                    "live": True,
                    "model": MS.MODEL,
                    "run_dir": str(run_dir),
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 2

    MS.write_report(run_dir / batch_id / "model.json", report)
    payload = json.loads(report.to_json())
    payload.update(
        {
            "answers": str(answers.root),
            "ledger": str(args.ledger),
            "live": True,
            "model": MS.MODEL,
            "run_dir": str(run_dir),
        }
    )
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


def _has_answers(root: Path) -> bool:
    """True when the batch carries at least one of the finder's answers.

    The question is asked about the answers, not about the directory: an empty `answers/` is the
    same as no answers for a reviewer, and a folder a crash left behind must not buy a review pass
    that produces nothing. `is_dir` alone would be satisfied by that empty folder.
    """
    if not root.is_dir():
        return False
    return any(root.glob("*.txt"))


def _judge_discover_reviewer(
    args: argparse.Namespace,
    *,
    batch: dict[str, Any],
    batch_id: str,
    run_dir: Path,
    failures: dict[str, dict[str, str]],
) -> int:
    """`judge --stage reviewer` for a discover batch: one verdict per usable finding.

    The unit is the finder's finding, so there are fewer calls than the finder bought: only a field
    whose finder answer is a complete `WRONG` proposes a change, and only a change can be refuted.
    Everything not reviewed is written into the same report with its reason, so "nothing to
    review" and "not reviewed yet" never look alike.

    The report goes to `review.json`, not to the finder's `model.json`: a batch directory is the
    finder's record, and a second stage writing over its numbers would destroy the evidence of what
    the finder said and what it cost.
    """
    from phase3 import discover_stage as DS
    from phase3 import fetch_stage as F
    from phase3 import model_stage as MS
    from phase3 import review_stage as RS

    store = F.EvidenceStore(run_dir / batch_id / "evidence")
    answers = F.EvidenceStore(run_dir / batch_id / "answers")
    reviews = F.EvidenceStore(run_dir / batch_id / "reviews")

    if not args.live:
        plan = RS.plan_batch(batch=batch, answers=answers, store=store, failures=failures)
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "calls": len(plan.calls),
                    "fields": list(DS.DISCOVER_FIELDS),
                    "live": False,
                    "model": MS.MODEL,
                    "pass": DISCOVER_PASS,
                    "program": MS.PROGRAM,
                    "run_dir": str(run_dir),
                    "sites": [
                        {
                            "argv": MS.pi_argv(),
                            "evidence": [
                                {
                                    "chars": e.chars,
                                    "failure": e.failure,
                                    "feature": e.feature,
                                    "path": str(e.path),
                                    "present": e.present,
                                    "url": e.url,
                                }
                                for e in item.excerpts
                            ],
                            "field": item.call.field,
                            "label": item.call.label,
                            "prompt": item.call.prompt,
                            "prompt_chars": len(item.call.prompt),
                            "site_id": item.call.site_id,
                        }
                        for item in plan.calls
                    ],
                    "stage": args.stage,
                    "unreviewable": [v.to_dict() for v in plan.unreviewable],
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 0

    runner = MS.PiRunner(timeout=args.timeout)
    try:
        report = RS.judge_review_batch(
            batch=batch,
            runner=runner,
            store=store,
            answers=answers,
            reviews=reviews,
            ledger=L.Ledger(Path(args.ledger)),
            failures=failures,
        )
    except MS.ModelCallFailed as exc:
        # Same rule as the finder's path: the batch stops at the call that could not be measured,
        # and says so in the JSON a caller reads instead of writing a report that pretends to be
        # complete.
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "error": str(exc),
                    "live": True,
                    "model": MS.MODEL,
                    "pass": DISCOVER_PASS,
                    "run_dir": str(run_dir),
                    "stage": args.stage,
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 2

    RS.write_report(run_dir / batch_id / "review.json", report)
    payload = json.loads(report.to_json())
    payload.update(
        {
            "answers": str(answers.root),
            "ledger": str(args.ledger),
            "live": True,
            "model": MS.MODEL,
            "pass": DISCOVER_PASS,
            "reviews": str(reviews.root),
            "run_dir": str(run_dir),
        }
    )
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


def _judge_discover(
    args: argparse.Namespace,
    *,
    batch: dict[str, Any],
    run_dir: Path,
    batch_id: str,
    failures: dict[str, dict[str, str]],
) -> int:
    """`judge` for a discover batch: one call per (site, field), one question per call.

    Two differences from the finding-driven judge, both from the batch's own `pass` marker:

    * the unit is one (site, field), so a batch of 15 sites buys 75 calls and every call carries
      its field (the label, the answer file and the report entry are per field);
    * a site whose evidence is over the bound is **that site's own** `unverifiable` outcome and the
      batch carries on - `discover_stage.plan_batch` records it before any call is bought, which is
      also why the dry run below shows those sites instead of dying on the first one.

    `--stage reviewer` is this pass's second question, and it is allowed **only** when the batch
    carries the finding it is about: the reviewer refutes a finding the finder made, so `answers/`
    must hold at least one answer file. A reviewer pass over a batch nobody judged would buy
    nothing and write empty verdicts - a silent zero that reads like a finished review, which is
    exactly what the condition below prevents.
    """
    from phase3 import discover_stage as DS
    from phase3 import fetch_stage as F
    from phase3 import model_stage as MS
    from phase3 import snapshot_plan as SP

    if args.stage == Stage.REVIEWER.value:
        answers_root = run_dir / batch_id / "answers"
        if not _has_answers(answers_root):
            raise InputError(
                f"{batch_id}: --stage reviewer refutes a finding the finder made, and this batch "
                f"carries none ({answers_root} holds no answer file); judge it with --stage "
                "finder first"
            )
        return _judge_discover_reviewer(
            args, batch=batch, batch_id=batch_id, run_dir=run_dir, failures=failures
        )
    if args.stage != Stage.FINDER.value:
        raise InputError(
            f"{batch_id}: a discover batch is judged with --stage finder or --stage reviewer; "
            "every other stage asks about a value, and this pass asks about the fields themselves"
        )
    store = F.EvidenceStore(run_dir / batch_id / "evidence")
    # The catalogue's own `site_type` list, read from the snapshot this plan was built from: one
    # field's question asks which of those values the evidence describes, and cannot be asked
    # without them. Read once per invocation, not per call.
    vocabulary = SP.site_type_vocabulary()

    if not args.live:
        plan = DS.plan_batch(
            batch=batch, store=store, vocabulary=vocabulary, allow_absent=True, failures=failures
        )
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "calls": len(plan.calls),
                    "fields": list(DS.DISCOVER_FIELDS),
                    "live": False,
                    "model": MS.MODEL,
                    "pass": DISCOVER_PASS,
                    "program": MS.PROGRAM,
                    "run_dir": str(run_dir),
                    "sites": [
                        {
                            "argv": MS.pi_argv(),
                            "evidence": [
                                {
                                    "chars": e.chars,
                                    "failure": e.failure,
                                    "feature": e.feature,
                                    "path": str(e.path),
                                    "present": e.present,
                                    "url": e.url,
                                }
                                for e in item.excerpts
                            ],
                            "field": item.call.field,
                            "label": item.call.label,
                            "prompt": item.call.prompt,
                            "prompt_chars": len(item.call.prompt),
                            "site_id": item.call.site_id,
                        }
                        for item in plan.calls
                    ],
                    "skipped": [s.to_dict() for s in plan.skipped],
                    "stage": args.stage,
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 0

    runner = MS.PiRunner(timeout=args.timeout)
    answers = F.EvidenceStore(run_dir / batch_id / "answers")
    try:
        report = DS.judge_discover_batch(
            batch=batch,
            runner=runner,
            store=store,
            answers=answers,
            ledger=L.Ledger(Path(args.ledger)),
            vocabulary=vocabulary,
            failures=failures,
        )
    except MS.ModelCallFailed as exc:
        # Same rule as the finding-driven path: the batch stops at the call that could not be
        # measured. What the over-bound rule already decided is in the report's `skipped`, and a
        # batch that stops there never writes one - the ledger carries the calls that did happen.
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "error": str(exc),
                    "live": True,
                    "model": MS.MODEL,
                    "pass": DISCOVER_PASS,
                    "run_dir": str(run_dir),
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 2

    MS.write_report(run_dir / batch_id / "model.json", report)
    payload = json.loads(report.to_json())
    payload.update(
        {
            "answers": str(answers.root),
            "ledger": str(args.ledger),
            "live": True,
            "model": MS.MODEL,
            "pass": DISCOVER_PASS,
            "run_dir": str(run_dir),
        }
    )
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Imported here, not at module level: `model_stage` imports `fetch_stage`, which imports this
    # module, so a top-level import of it would be circular.
    from phase3 import model_stage as MS

    parser = argparse.ArgumentParser(
        prog="phase3-run",
        description="Phase-3 runner: plan, prepare and report a two-stage audit run",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="assign the Phase-3 worklist to batches (offline)")
    plan.add_argument("--worklist", default=str(DEFAULT_WORKLIST))
    plan.add_argument("--out", default=str(DEFAULT_PLAN))
    plan.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    plan.add_argument(
        "--from-snapshot",
        action="store_true",
        help=(
            "plan every site of the offline snapshot instead of the worklist: one finding per "
            "(site, field) for description, period_start, site_type, country and "
            "card_description (piece 5)"
        ),
    )
    plan.add_argument(
        "--site-ids",
        default=None,
        help=(
            "a file with one site id per line, selecting sites of the snapshot plan; "
            "output/remediation/gold_standard/truth_sites.txt is such a file. Needs "
            "--from-snapshot"
        ),
    )
    plan.add_argument(
        "--snapshot-dir",
        default=None,
        help="where the snapshot export lives (default: output/remediation/snapshot)",
    )
    plan.set_defaults(func=cmd_plan)

    prepare = sub.add_parser("prepare", help="write one input file per batch (offline)")
    prepare.add_argument("--plan", default=str(DEFAULT_PLAN))
    prepare.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    prepare.add_argument("--batch-id", action="append", default=None)
    prepare.set_defaults(func=cmd_prepare)

    fetch = sub.add_parser(
        "fetch", help="collect evidence for one prepared batch (offline unless --live)"
    )
    fetch.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    fetch.add_argument("--batch-id", required=True)
    fetch.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    fetch.add_argument(
        "--stage",
        choices=[s.value for s in Stage],
        default=Stage.FINDER.value,
        help="which stage the ledger line belongs to (the reviewer reuses this command)",
    )
    fetch.add_argument(
        "--live",
        action="store_true",
        help="actually open sockets; without it the command only lists the targets",
    )
    fetch.add_argument("--timeout", type=float, default=40.0)
    fetch.add_argument(
        "--pacing-dir",
        default="",
        help=(
            "directory the cross-process host pace keeps its locks in. Empty (the default) paces "
            "nothing, because a lone fetch has nobody to pace against; the mass-run driver passes "
            f"{DEFAULT_PACING_DIR} for every batch, and with --jobs N those batches are separate "
            "processes"
        ),
    )
    fetch.set_defaults(func=cmd_fetch)

    judge = sub.add_parser(
        "judge",
        help="run one stage over one prepared batch (dry run unless --live)",
        description=(
            "Without --live this renders the exact argv and prompt of every call in the batch and "
            "starts nothing. Run it with PYTHONIOENCODING=utf-8: the prompts carry site names, "
            "notes and page text, and the Windows console code page raises on non-ASCII."
        ),
    )
    judge.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    judge.add_argument("--batch-id", required=True)
    judge.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    judge.add_argument(
        "--stage",
        choices=[s.value for s in Stage],
        default=Stage.FINDER.value,
        help=(
            "which question the stage asks (phase3/model_stage.py pins one question per stage; a "
            "discover batch is judged by --stage finder and then, once its answers exist, by "
            "--stage reviewer)"
        ),
    )
    judge.add_argument(
        "--live",
        action="store_true",
        help="actually run one Pi process per site; without it nothing is executed",
    )
    judge.add_argument("--timeout", type=float, default=MS.DEFAULT_TIMEOUT)
    judge.set_defaults(func=cmd_judge)

    status = sub.add_parser("status", help="report what is on disk, plus the ledger (offline)")
    status.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    status.add_argument("--plan", default=str(DEFAULT_PLAN))
    status.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
