"""Objective quality gate for harvested Theo research papers.

Grades every `reports/<slug>.md` the drip-feeder produces (and, with --db, the
live completed rows on the VPS) against the bar the project actually cares
about: substantive length, real inline citations, a resolvable References
section, and the judge's own score/badge. Pure stdlib — no LLM, no deps.

Verdict per paper:
  TOP   — judge Platinum/score>=90 OR (>=15k chars, References present,
          >=20 inline citations, no structural defects)
  OK    — complete and cited but below the TOP bar
  FLAG  — empty / short (<4000) / no References / duplicate H1 / no citations

Usage:
  python scripts/grade_theo_papers.py
  python scripts/grade_theo_papers.py --reports "C:/.../reports" --db
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

DEFAULT_REPORTS = Path(r"C:\PythonProjects\FantasyAdventure\docs\entitaet\research\reports")
MIN_CHARS = 4000
TOP_CHARS = 15000
TOP_CITATIONS = 20

_CITE = re.compile(r"\[\d+\]")
_H1 = re.compile(r"^# .+", re.MULTILINE)
_REFS = re.compile(r"^#+\s*References\s*$", re.MULTILINE | re.IGNORECASE)
_REF_ENTRY = re.compile(r"^\[\d+\]\s", re.MULTILINE)


def _grade_text(body: str, meta: dict) -> dict:
    chars = len(body)
    words = len(body.split())
    citations = len(_CITE.findall(body))
    h1s = _H1.findall(body)
    has_refs = bool(_REFS.search(body))
    ref_entries = len(_REF_ENTRY.findall(body))
    dup_title = len(h1s) >= 2 and h1s[0].strip() == h1s[1].strip()
    score = meta.get("quality_score")
    if isinstance(score, dict):  # DB stores the whole dict; .md sidecar stores int
        badge = score.get("badge")
        score = score.get("score")
    else:
        badge = meta.get("badge")

    flags = []
    if chars < MIN_CHARS:
        flags.append(f"short({chars}c)")
    if not has_refs:
        flags.append("no-References")
    if citations == 0:
        flags.append("no-citations")
    if dup_title:
        flags.append("duplicate-H1")

    if flags:
        verdict = "FLAG"
    elif (
        (isinstance(score, (int, float)) and score >= 90)
        or badge == "Platinum"
        or (chars >= TOP_CHARS and has_refs and citations >= TOP_CITATIONS)
    ):
        verdict = "TOP"
    else:
        verdict = "OK"

    return {
        "verdict": verdict,
        "chars": chars,
        "words": words,
        "citations": citations,
        "ref_entries": ref_entries,
        "score": score,
        "badge": badge,
        "flags": ",".join(flags) or "-",
    }


def grade_reports(reports: Path) -> list[dict]:
    rows = []
    for md in sorted(reports.glob("*.md")):
        if md.name.startswith("_"):
            continue
        body = md.read_text(encoding="utf-8", errors="ignore")
        sidecar = md.with_suffix(".json")
        meta = {}
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                pass
        rows.append({"source": "file", "name": md.stem, **_grade_text(body, meta)})
    return rows


def grade_db() -> list[dict]:
    """Grade live completed rows on the VPS via ssh+psql (read-only)."""
    # json_agg → one JSON blob so multi-line report bodies don't break parsing.
    sql = (
        "SELECT COALESCE(json_agg(json_build_object("
        "'q', left(question,40), "
        "'report', result_json::jsonb->>'report', "
        "'qs', result_json::jsonb->'quality_score')), '[]') "
        "FROM research_requests WHERE status='completed';"
    )
    cmd = [
        "ssh",
        "ancientnerds",
        f'docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -t -A -c "{sql}"',
    ]
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    try:
        records = json.loads((proc.stdout or "[]").strip() or "[]")
    except json.JSONDecodeError:
        print(f"[grade] DB query failed: {(proc.stderr or '')[:200]}")
        return []
    rows = []
    for rec in records:
        meta = {"quality_score": rec.get("qs")}
        rows.append(
            {
                "source": "db",
                "name": rec.get("q") or "?",
                **_grade_text(rec.get("report") or "", meta),
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default=str(DEFAULT_REPORTS))
    ap.add_argument("--db", action="store_true", help="also grade live VPS rows")
    args = ap.parse_args()

    rows = grade_reports(Path(args.reports))
    if args.db:
        rows += grade_db()

    if not rows:
        print("No papers found.")
        return

    hdr = f"{'verdict':7} {'name':32} {'chars':>7} {'cites':>5} {'score':>5} {'badge':>9}  flags"
    print(hdr)
    print("-" * len(hdr))
    for r in sorted(rows, key=lambda x: ("TOP", "OK", "FLAG").index(x["verdict"])):
        print(
            f"{r['verdict']:7} {r['name'][:32]:32} {r['chars']:7} {r['citations']:5} "
            f"{str(r['score'] or '-'):>5} {str(r['badge'] or '-'):>9}  {r['flags']}"
        )
    n = len(rows)
    top = sum(1 for r in rows if r["verdict"] == "TOP")
    flag = sum(1 for r in rows if r["verdict"] == "FLAG")
    print(f"\n{n} papers - {top} TOP, {n - top - flag} OK, {flag} FLAG")


if __name__ == "__main__":
    main()
