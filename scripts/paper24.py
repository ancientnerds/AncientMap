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

#: Dossier ids the studio has already pulled, in the order the driver took them.
STATE = config.studio_assets() / "paper24_state.json"


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
    if not STATE.exists():
        return {"pulled": [], "checked": {}, "bundled": []}
    return json.loads(STATE.read_text(encoding="utf-8"))


def _save(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


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


def cmd_pull(args: argparse.Namespace) -> int:
    ws = pull.pull(config.check_request_id(args.request_id))
    state = _state()
    if ws.request_id not in state["pulled"]:
        state["pulled"].append(ws.request_id)
    _save(state)
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
    state = _state()
    state.setdefault("checked", {})[ws.request_id] = state["checked"].get(ws.request_id, 0) + 1
    _save(state)
    _print(
        {
            "request_id": ws.request_id,
            "iteration": state["checked"][ws.request_id],
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
    if not result["passed"]:
        _print(
            {
                "request_id": ws.request_id,
                "numbered": {"sources": len(built.sources), "images": len(built.probative_images)},
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
            "bundle": str(ws.bundle),
            "images": bundle.upload_names(written["result"]),
            "published": False,
        }
    )
    return 0


# --- ledger -------------------------------------------------------------------


def _iterations(state: dict[str, Any], rid: str) -> int:
    return int((state.get("checked") or {}).get(rid) or 0)


#: The table's own header, written once. The columns are the DONE WHEN criteria, so a
#: row is the whole claim for one topic: it is a bundle, it is green, it took at most
#: two iterations, and the chain change that came out of it is named.
LEDGER_HEADER = (
    "| # | request_id | topic | iterations | green | support findings | bundle | chain change |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


def _ledger_row(index: int, rid: str, state: dict[str, Any]) -> str | None:
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
        f"| {index} | `{rid}` | {_topic_of(ws)} | {_iterations(state, rid)} | {passed} | "
        f"{support.get('total', 0)} | {'yes' if ws.bundle.exists() else 'no'} | |"
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
    for index, rid in enumerate(sorted(state.get("pulled") or []), start=1):
        row = _ledger_row(index, rid, state)
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
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(
        LEDGER_HEADER + "\n".join(rows + foreign) + ("\n" if rows or foreign else ""),
        encoding="utf-8",
    )
    _print({"rows": len(rows), "kept_foreign_rows": len(foreign), "ledger": str(LEDGER)})
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
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
