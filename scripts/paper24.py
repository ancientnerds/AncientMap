#!/usr/bin/env python3
"""paper24: the driver's side of the owner's 24 paper topics.

The research runs on the VPS; this drives the studio half of the same chain, on this
workstation, so a dossier never sits waiting for a session to notice it:

    paper24 scan              read-only: the 24 rows, what is ready, what is written
    paper24 pull   REQUEST    dossier + brief + archived texts into the workspace
    paper24 draft  REQUEST    what the writer owes this workspace (the one manual step)
    paper24 check  REQUEST    every gate; writes check_report.json, counts an iteration
    paper24 claims REQUEST    export, answer on MiniMax, import
    paper24 images REQUEST    export, answer on MiniMax, import
    paper24 finish REQUEST    number -> check (the second iteration) -> bundle
    paper24 ledger            append the run to the ledger from the reports on disk

One deliberate gap: `draft` is a report, not a step. The model writes `draft.md`,
`paper_meta.json` and `evidence.json` (house format, spec 3.2), and nothing else in
this file may write prose. Every other step is mechanical and this file owns it.

Read-only boundary: this driver never touches production. The one production write
of the campaign - resuming the runs - is already done (research_requests 24 rows
queued on the full-speed lane, 2026-10-04). `paper publish` is deliberately absent.

On the workstation the repo root is not on `sys.path` for a script run by path, so
the local invocation is

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/paper24.py scan

(the repo's venv, explicitly - a bare `python` is a different interpreter). Inside
the API image it is `python scripts/paper24.py`, where `pipeline` is installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.studio import config, mcode, mcode_checks, remote
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import bundle, claims, gates, images, numbering, pull
from pipeline.studio.paper.workspace import PaperWorkspace, parse_dossier, workspace

# The owner's batch: created 2026-07-05, paused by the owner, resumed 2026-10-04.
BATCH_USER = "442000112756064260"
BATCH_DAY = "2026-07-05"
LEDGER = Path(__file__).resolve().parents[1] / "docs" / "reports" / "theo-24-run-ledger.md"

#: The driver's own list of the topics it owns. Resolved per call, not at import:
#: a module-level constant would point at the real campaign for any caller that
#: sets STUDIO_ASSETS after the import - the tests did exactly that and wrote the
#: campaign's state file with fixture ids.
STATE_NAME = "paper24_state.json"


def state_path() -> Path:
    """Where the driver keeps its list, for the assets root in force right now."""
    return config.studio_assets() / STATE_NAME


#: `theo_dossier list` over ssh into the API image; the same timeout the CLI's
#: `paper list` uses.
LIST_TIMEOUT_S = 120


def _dossiers() -> list[dict[str, Any]]:
    """`theo_dossier list`: the researched runs with a complete dossier, oldest first."""
    out = remote.check_module("pipeline.lyra.theo_dossier", ["list"], timeout=LIST_TIMEOUT_S)
    data = json.loads(out.decode("utf-8"))
    if not isinstance(data, list):
        raise StudioError(f"theo_dossier list did not return a list: {type(data).__name__}")
    return data


def _state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return {"pulled": [], "bundled": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _ws(request_id: str) -> PaperWorkspace:
    return workspace(config.check_request_id(request_id))


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


# --- scan ---------------------------------------------------------------------


def cmd_scan(_args: argparse.Namespace) -> int:
    """What is ready and what is already written. Never writes anything."""
    state = _state()
    pulled = set(state.get("pulled") or [])
    bundled = set(state.get("bundled") or [])
    ready, waiting, listed = [], [], 0
    for d in _dossiers():
        listed += 1
        rid = str(d.get("request_id") or d.get("id") or "")
        if not rid:
            raise StudioError(f"theo_dossier list returned a row without an id: {d}")
        row = {
            "request_id": rid,
            "question": (d.get("question") or "")[:90],
            "status": d.get("status"),
            "pulled": rid in pulled,
            "bundled": rid in bundled,
        }
        (bundled if rid in bundled else pulled if rid in pulled else ready).append(row)
    if ready:
        ready.sort(key=lambda r: r["request_id"])
    stop_reason = mcode.weekly_stop()
    _print(
        {
            "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "dossiers_on_record": listed,
            "ready_to_pull": ready,
            "already_pulled": waiting,
            "bundled": sorted(bundled),
            "mcode": {
                "model": mcode.MODEL,
                "effort": mcode.EFFORT,
                "weekly_remaining_percent": mcode.weekly_remaining_percent(),
                "weekly_stopped": bool(stop_reason),
                "weekly_stop_reason": stop_reason,
                "tree_state": mcode.tree_state(config.REPO),
            },
        }
    )
    return 0


# --- steps --------------------------------------------------------------------


def register_pulled(request_id: str) -> None:
    """Record a workspace the driver owns, whoever filled it.

    `paper24 pull` takes the workspace from a Theo dossier and `paper24_seed`
    builds the same workspace from research done in this session; both are the
    driver's topic from that moment on, and `scan` and `ledger` read this list.
    """
    state = _state()
    if request_id not in state["pulled"]:
        state["pulled"].append(request_id)
    _save(state)


def cmd_pull(args: argparse.Namespace) -> int:
    ws = pull.pull(config.check_request_id(args.request_id))
    register_pulled(ws.request_id)
    _print(
        {
            "request_id": ws.request_id,
            "workspace": str(ws.root),
            "brief": str(ws.brief),
            "texts": len(list(ws.texts_dir.glob("*.txt"))) if ws.texts_dir.exists() else 0,
        }
    )
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    """The writing order for this workspace: the brief, the budget, the three files."""
    ws = _ws(args.request_id)
    brief = ws.brief.read_text(encoding="utf-8")
    _print(
        {
            "request_id": ws.request_id,
            "workspace": str(ws.root),
            "brief_chars": len(brief),
            "brief_path": str(ws.brief),
            "to_write": ["draft.md", "paper_meta.json", "evidence.json"],
            "then": "paper24 check " + ws.request_id,
        }
    )
    return 0


def _count_issues(ws: PaperWorkspace) -> dict[str, Any]:
    """The gate's own finding classes, for the ledger and for the next iteration."""
    if not ws.check_report.exists():
        return {}
    report = json.loads(ws.check_report.read_text(encoding="utf-8"))
    out: dict[str, Any] = {}
    for gate in report.get("gates", []):
        detail = gate.get("detail") or {}
        issues = detail.get("issues")
        if issues is None:
            continue
        rules: dict[str, int] = {}
        for issue in issues:
            rules[issue.get("rule", "?")] = rules.get(issue.get("rule", "?"), 0) + 1
        out[gate["name"]] = {"total": len(issues), "rules": rules}
    return out


def cmd_check(args: argparse.Namespace) -> int:
    ws = _ws(args.request_id)
    result = gates.run_check(ws)
    iteration = _record_check(ws, result)
    _print(
        {
            "request_id": ws.request_id,
            "iteration": iteration,
            "passed": result["passed"],
            "failing": [g["name"] for g in result["gates"] if not g["passed"]],
            "findings": _count_issues(ws),
            "report": str(ws.check_report),
        }
    )
    return 0 if result["passed"] else 1


def cmd_claims(args: argparse.Namespace) -> int:
    ws = _ws(args.request_id)
    exported = claims.export_claims(ws)
    result = mcode_checks.answer_claims(ws, repo=config.REPO, limit=args.limit)
    imported = claims.import_claims(ws)
    _print(
        {
            "request_id": ws.request_id,
            "exported": exported,
            "answered": result.answered,
            "counts": result.counts,
            "overruled_by_skeptic": result.overruled_by_skeptic,
            "not_answered": result.not_answered,
            "stopped": result.stopped,
            "imported": imported,
        }
    )
    return 0 if not result.not_answered else 1


def cmd_images(args: argparse.Namespace) -> int:
    ws = _ws(args.request_id)
    exported = images.export_images(ws)
    result = mcode_checks.answer_images(ws, repo=config.REPO, limit=args.limit)
    imported = images.import_images(ws)
    _print(
        {
            "request_id": ws.request_id,
            "exported": exported,
            "answered": result.answered,
            "counts": result.counts,
            "not_answered": result.not_answered,
            "stopped": result.stopped,
            "imported": imported,
        }
    )
    return 0 if not result.not_answered else 1


def cmd_finish(args: argparse.Namespace) -> int:
    ws = _ws(args.request_id)
    built = numbering.number(ws)
    result = gates.run_check(ws)
    iteration = _record_check(ws, result)
    if not result["passed"]:
        _print(
            {
                "request_id": ws.request_id,
                "numbered": {"sources": len(built.sources), "images": len(built.probative_images)},
                "iteration": iteration,
                "passed": False,
                "failing": [g["name"] for g in result["gates"] if not g["passed"]],
                "findings": _count_issues(ws),
            }
        )
        return 1
    written = bundle.write_bundle(ws)
    state = _state()
    if ws.request_id not in state["bundled"]:
        state["bundled"].append(ws.request_id)
    _save(state)
    _print(
        {
            "request_id": ws.request_id,
            "iteration": iteration,
            "bundle": str(ws.bundle),
            "images": bundle.upload_names(written["result"]),
            "published": False,
        }
    )
    return 0


# --- ledger -------------------------------------------------------------------


def _iterations(ws: PaperWorkspace) -> int | None:
    """How many times the gates have run here, or None when nothing recorded it.

    `None` is the honest answer for a workspace with no `checks.jsonl`, and it is not
    the same answer as `0`. The campaigns of 2026-10-06 and 07 ran the gates from the
    studio CLI rather than through this driver, so six of the ten published papers
    carry no history at all; a counter that answered `0` for them would put a paper
    that went through eleven check cycles in the ledger as one that went through
    none, and would read as the campaign limit being met. A missing record is
    reported as a missing record.
    """
    if not ws.checks.exists():
        return None
    return sum(1 for line in ws.checks.read_text(encoding="utf-8").splitlines() if line.strip())


def _iterations_cell(ws: PaperWorkspace) -> str:
    """The `iterations` cell: a count, or `nicht gemessen` where the count is unknown.

    `0` is not an acceptable cell. No paper reaches a bundle without the gates having
    run at least once, so a zero here can only be a lost record.
    """
    count = _iterations(ws)
    return "nicht gemessen" if count is None else str(count)


def _record_check(ws: PaperWorkspace, result: dict[str, Any]) -> int:
    """Append this gate run to the workspace's history and return the iteration number.

    Every path that runs the gates records here, `check` and `finish` alike, because
    the campaign's own limit is "at most two check iterations per paper": a counter
    that only one of them writes would answer a question nobody asked.
    """
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": bool(result.get("passed")),
        "failing": [g["name"] for g in result.get("gates", []) if not g["passed"]],
    }
    ws.root.mkdir(parents=True, exist_ok=True)
    with ws.checks.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return _iterations(ws)


#: The table's own header, written once. The columns are the DONE WHEN criteria, so a
#: row is the whole claim for one topic: it is a bundle, it is green, it took at most
#: two iterations, and the chain change that came out of it is named.
LEDGER_HEADER = (
    "| # | request_id | topic | iterations | green | rote Gates | support findings |"
    " bundle | chain change |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
)


def _failing_gates(report: dict[str, Any]) -> str:
    """The gate names that were red, `quality` left out.

    `quality` is a rollup of the other gates plus the quality score, so naming it
    beside them says nothing the others do not. This column is the defect index of
    the run: which gate a topic keeps failing on is the signal that decides whether
    the next paper needs a different chain, and it has to be measured rather than
    remembered.
    """
    names = [
        gate["name"]
        for gate in report.get("gates", [])
        if not gate.get("passed") and gate.get("name") != "quality"
    ]
    return ", ".join(names) if names else "-"


def _ledger_row(index: int, rid: str) -> str | None:
    """The markdown row for one workspace, or None if it has no report yet.

    Re-running the command replaces a row instead of appending a second one: the
    ledger is the record of the current state, not a log of every check.
    """
    ws = workspace(rid)
    if not ws.check_report.exists():
        return None
    report = json.loads(ws.check_report.read_text(encoding="utf-8"))
    support = _count_issues(ws).get("support", {})
    passed = "yes" if report.get("passed") else "no"
    return (
        f"| {index} | `{rid}` | {_topic_of(ws)} | {_iterations_cell(ws)} | {passed} | "
        f"{_failing_gates(report)} | {support.get('total', 0)} | "
        f"{'yes' if ws.bundle.exists() else 'no'} | |"
    )


def _topic_of(ws: PaperWorkspace) -> str:
    """The research question, in one table cell: no pipes, no newlines.

    Taken from the dossier, because that is where the question is a field. Reading it
    out of the brief means guessing which line is the question, and the brief's first
    line is its heading.
    """
    if ws.dossier_gz.exists():
        question = parse_dossier(ws.dossier_gz.read_bytes()).question
        if question:
            return " ".join(question.split())[:70]
    return "(no dossier)"


def _row_number(line: str) -> int | None:
    """The `#` a row claims, or None for the header, the separator and anything else."""
    parts = [cell.strip() for cell in line.split("|")]
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


def _refuse_colliding_numbers(rows: list[str], foreign: list[str]) -> None:
    """Stop before a table can carry the same campaign number twice.

    A kept foreign row whose `#` is a number the rewritten rows also use is not a
    foreign campaign: it is a topic of this campaign that the driver's list lost, and
    writing the table anyway would renumber the campaign and hide the loss. The state
    file is the only thing that knows the order, so its loss is repaired by hand, not
    by a guess here.
    """
    claimed = {_row_number(row) for row in rows} - {None}
    for line in foreign:
        number = _row_number(line)
        if number in claimed:
            kept = [cell.strip() for cell in line.split("|")][2]
            raise StudioError(
                f"ledger number {number} is claimed twice: the rewritten rows and the "
                f"kept row {kept}. That kept row is a topic of this campaign that "
                f"{state_path().name} no longer lists; add its request id back to "
                f"`pulled` in the campaign order, then re-run."
            )


def cmd_ledger(_args: argparse.Namespace) -> int:
    """Rewrite the run table from the reports on disk, one row per workspace.

    A workspace the driver owns is rewritten from its current report, so re-running
    the command updates a row instead of appending a second one; rows for other
    campaigns that share the file are left alone. The `chain change` column is empty
    on purpose: the driver can measure what happened, but which defect of a paper
    caused which change in the chain is a judgement, and that judgement is the
    campaign's point.
    """
    state = _state()
    rows: list[str] = []
    # In registration order, not sorted: the `#` column is the campaign's running
    # number, so a paper finished second is paper 2 however its uuid sorts.
    for rid in dict.fromkeys(state.get("pulled") or []):
        row = _ledger_row(len(rows) + 1, rid)
        if row is not None:
            rows.append(row)
    owned = [f"`{rid}`" for rid in state.get("pulled") or []]
    previous = LEDGER.read_text(encoding="utf-8").splitlines() if LEDGER.exists() else []
    foreign = [
        line
        for line in previous
        if line.startswith("| ")
        and not line.startswith("| # |")
        and not any(r in line for r in owned)
    ]
    _refuse_colliding_numbers(rows, foreign)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(
        LEDGER_HEADER + "\n".join(rows + foreign) + ("\n" if rows or foreign else ""),
        encoding="utf-8",
    )
    unmeasured = [
        rid
        for rid in dict.fromkeys(state.get("pulled") or [])
        if _iterations(workspace(rid)) is None
    ]
    _print(
        {
            "rows": len(rows),
            "kept_foreign_rows": len(foreign),
            "ledger": str(LEDGER),
            "iterations_not_measured": len(unmeasured),
            "iterations_not_measured_ids": unmeasured,
        }
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    """The steps go straight into `sub`, so the usage reads `paper24 scan`."""
    for name, func, text, takes_id in [
        ("scan", cmd_scan, "read-only: what is ready, what is written", False),
        ("pull", cmd_pull, "dossier + brief + texts into the workspace", True),
        ("draft", cmd_draft, "the writing order for this workspace", True),
        ("check", cmd_check, "every gate, one iteration", True),
        ("claims", cmd_claims, "export, answer on MiniMax, import", True),
        ("images", cmd_images, "export, answer on MiniMax, import", True),
        ("finish", cmd_finish, "number, check, bundle", True),
        ("ledger", cmd_ledger, "the run table from the reports on disk", False),
    ]:
        step = sub.add_parser(name, help=text)
        if takes_id:
            step.add_argument("request_id")
            step.add_argument("--limit", type=int, help="answer at most N tasks (claim/image)")
        step.set_defaults(func=func)


def main(argv: list[str] | None = None) -> int:
    """`main()` so the driver can be called and tested like any other module."""
    parser = argparse.ArgumentParser(prog="paper24", description=__doc__)
    register(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return args.func(args)
    except StudioError as exc:
        # The house rule for every studio CLI: the message names the cause, exit 2.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
