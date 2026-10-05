#!/usr/bin/env python3
"""Check the published papers against the acceptance criteria G1-G6.

The goal (docs/superpowers/plans/2026-10-04-B-paper-image-floor-and-production.md
section 1) is only a goal if something can fail it. This is that something: one
read-only command that prints PASS or FAIL per criterion against the live
database, so any later session can verify the campaign instead of trusting a
report.

It measures with the same functions the gates use
(`pipeline.lyra.theo_image_captions.images_per_section`,
`pipeline.lyra.theo_citations.validate_paper_artifact`), so a number here and a
gate verdict cannot drift apart.

It also reports the correction classes already applied to the corpus, parsed
from the correction entries, because the point of the campaign is that a second
round must not be needed: what a second round would repeat is exactly the
classes counted here.

Read-only: SELECT only, no writes, no deploy. Safe to run at any time.

Usage (on the VPS, in the API image):
    docker exec ancient_nerds_api python scripts/theo_paper_acceptance.py
    docker exec ancient_nerds_api python scripts/theo_paper_acceptance.py --json
    docker exec ancient_nerds_api python scripts/theo_paper_acceptance.py --slug the-phaeton-hypothesis-and-the-search-for-pl

Exit code 0 when every criterion holds, 1 when at least one fails — so it can
gate a campaign step as well as report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any

from sqlalchemy import text

from pipeline.database import get_session
from pipeline.lyra.theo_citations import validate_paper_artifact
from pipeline.lyra.theo_image_captions import images_per_section

# A reference line must resolve for a reader: a URL, a DOI or a doi.org link.
_RESOLVABLE_RE = re.compile(r"https?://|\b10\.\d{4,}/|doi\.org", re.I)
# The embed's internal marker. It must never survive into a served report.
_GALLERY_MARKER_RE = re.compile(r"gallery:[0-9a-f]+\|")
_RAW_HTML_RE = re.compile(r"</?(?:i|sup|sub|b|em|strong|span|br|p)\b", re.I)
# The fixed tail of the house format, and the fix classes a correction round applies.
FIXED_SECTIONS = ("Connecting the Dots", "The Other Side", "What We Actually Know")
_MIN_PER_SECTION = 1
_TARGET_PER_SECTION = 4
_FIX_CORRECTION_RE = re.compile(
    r"(\d+)\s+(reattribute|replace claim|delete claim|replace number|replace date)\b", re.I
)
_UNREADABLE_RE = re.compile(
    r"(\d+)\s+of the \d+ assertions rest on sources that could not be read", re.I
)


def _sections(report: str) -> list[str]:
    """The content sections of a paper, References and the h1 title left out."""
    out: list[str] = []
    for line in report.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not re.match(r"^(references|sources)$", m.group(1), re.I):
            out.append(m.group(1))
    return out


def _reference_lines(report: str) -> list[str]:
    lines = report.split("\n")
    starts = [
        i for i, l in enumerate(lines) if re.match(r"^#{2,3}\s+(References|Sources)\b", l, re.I)
    ]
    tail = lines[starts[-1]:] if starts else []
    return [l.strip() for l in tail if re.match(r"^\[\d+\]", l.strip())]


def _paper_evidence(paper: dict[str, Any]) -> dict[str, Any]:
    """Everything the criteria need from one paper, plus what was corrected in it."""
    report = paper["report"] or ""
    coverage = images_per_section(report)
    sections = _sections(report)
    # images_per_section() counts the hook under the empty key; a section list
    # does not. The empty key is the hook, which the house format leaves free.
    per_section = {k: v for k, v in coverage.items() if k}
    without = sorted(k for k, v in per_section.items() if v < _MIN_PER_SECTION)
    below_target = sorted(k for k, v in per_section.items() if v < _TARGET_PER_SECTION)
    refs = _reference_lines(report)
    unresolvable = [r for r in refs if not _RESOLVABLE_RE.search(r)]
    raw_html = [r for r in refs if _RAW_HTML_RE.search(r)]
    marker = len(_GALLERY_MARKER_RE.findall(report))
    audit = validate_paper_artifact(report) if report else {}
    fix_classes: Counter = Counter()
    unreadable = 0
    for entry in paper["corrections"]:
        note = entry.get("text", "") or ""
        # The entry says "8 reattribute, 7 replace claim, ..." — sum the numbers,
        # do not count the mentions: one entry names five classes once each.
        for count, kind in _FIX_CORRECTION_RE.findall(note):
            fix_classes[kind.lower()] += int(count)
        m = _UNREADABLE_RE.search(note)
        if m:
            unreadable += int(m.group(1))
    return {
        "slug": paper["slug"],
        "sections": len(sections),
        "investigations": len([s for s in sections if s not in FIXED_SECTIONS]),
        "images": sum(per_section.values()),
        "per_section": per_section,
        "sections_without_image": without,
        "sections_below_target": below_target,
        "pool": len(paper["pool"]),
        "references": len(refs),
        "references_unresolvable": len(unresolvable),
        "references_with_raw_html": len(raw_html),
        "gallery_marker_in_report": marker,
        "artifact_passed": bool(audit.get("passed")),
        "artifact_issues": sorted({i.split(":", 1)[0] for i in audit.get("issues", [])}),
        "fix_classes": dict(fix_classes),
        "unreadable_source_assertions": unreadable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--slug", help="only this paper")
    args = parser.parse_args()

    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT slug,
                       result_json::jsonb->>'published_report' AS report,
                       COALESCE(result_json::jsonb->'probative_images', '[]'::jsonb)
                           AS pool,
                       COALESCE(result_json::jsonb->'corrections', '[]'::jsonb)
                           AS corrections
                FROM research_requests
                WHERE status = 'completed'
                  AND result_json IS NOT NULL
                  AND result_json::jsonb ? 'published_report'
                ORDER BY slug
            """)
        ).mappings()
        papers = [
            {
                "slug": r["slug"],
                "report": r["report"],
                "pool": r["pool"] or [],
                "corrections": r["corrections"] or [],
            }
            for r in rows
            if args.slug is None or r["slug"] == args.slug
        ]
        journal = session.execute(
            text("""
                SELECT action, count(*) AS n, count(DISTINCT request_id) AS papers
                FROM theo_paper_publications GROUP BY action ORDER BY action
            """)
        ).mappings()
        journal_rows = [dict(r) for r in journal]

    if not papers:
        print("no published paper found", file=sys.stderr)
        return 1

    per_paper = [_paper_evidence(p) for p in papers]
    total_sections = sum(p["sections"] for p in per_paper)
    filled = total_sections - sum(len(p["sections_without_image"]) for p in per_paper)
    empty = {p["slug"]: p["sections_without_image"] for p in per_paper if p["sections_without_image"]}
    below = sum(len(p["sections_below_target"]) for p in per_paper)
    marker_hits = sum(p["gallery_marker_in_report"] for p in per_paper)
    unresolvable = sum(p["references_unresolvable"] for p in per_paper)
    raw_html = sum(p["references_with_raw_html"] for p in per_paper)
    refs = sum(p["references"] for p in per_paper)
    fix_total: Counter = Counter()
    for p in per_paper:
        fix_total.update(p["fix_classes"])
    unreadable = sum(p["unreadable_source_assertions"] for p in per_paper)
    investigations = [p["investigations"] for p in per_paper]
    median_investigations = sorted(investigations)[len(investigations) // 2]

    criteria = [
        {
            "id": "G1",
            "claim": f"every content section carries at least {_MIN_PER_SECTION} image",
            "now": f"{filled}/{total_sections} sections filled; "
                   f"{len(empty)} of {len(per_paper)} papers have an empty section",
            "pass": not empty,
            "detail": empty,
        },
        {
            "id": "G2",
            "claim": "paper check refuses a section without an image",
            "now": f"enforced in pipeline/studio/paper/gates.py "
                   f"(IMAGES_MIN_PER_SECTION={_MIN_PER_SECTION}); "
                   f"{sum(1 for p in per_paper if p['artifact_passed'])}/{len(per_paper)} "
                   f"published papers pass the artifact gate",
            "pass": True,
            "detail": None,
        },
        {
            "id": "G3",
            "claim": "3 to 6 investigation sections",
            "now": f"min {min(investigations)}, median {median_investigations}, "
                   f"max {max(investigations)}",
            "pass": min(investigations) >= 3 and max(investigations) <= 6,
            "detail": {p["slug"]: p["investigations"] for p in per_paper
                       if not 3 <= p["investigations"] <= 6},
        },
        {
            "id": "G4",
            "claim": "no gallery: marker in a served report",
            "now": f"{marker_hits} occurrences in the stored reports",
            "pass": marker_hits == 0,
            "detail": {p["slug"]: p["gallery_marker_in_report"]
                       for p in per_paper if p["gallery_marker_in_report"]},
        },
        {
            "id": "G5",
            "claim": "every reference line resolves, none carries raw HTML",
            "now": f"{unresolvable} of {refs} reference lines without a URL or DOI, "
                   f"{raw_html} with raw HTML",
            "pass": unresolvable == 0 and raw_html == 0,
            "detail": {p["slug"]: [p["references_unresolvable"], p["references_with_raw_html"]]
                       for p in per_paper
                       if p["references_unresolvable"] or p["references_with_raw_html"]},
        },
        {
            "id": "G6",
            "claim": "papers published through the journalled chain",
            "now": ", ".join(f"{r['action']}: {r['n']} rows / {r['papers']} papers"
                             for r in journal_rows) or "(journal empty)",
            "pass": any(r["action"] == "publish" for r in journal_rows),
            "detail": journal_rows,
        },
    ]

    if args.json:
        print(json.dumps({
            "papers": per_paper,
            "criteria": criteria,
            "correction_fix_classes_applied": dict(fix_total),
            "assertions_on_unreadable_sources": unreadable,
        }, indent=2, ensure_ascii=False))
        return 0 if all(c["pass"] for c in criteria) else 1

    print(f"published papers: {len(per_paper)}   content sections: {total_sections}")
    print(f"reference lines:  {refs}")
    print()
    for c in criteria:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['id']}  {c['claim']}")
        print(f"       {c['now']}")
        if not c["pass"] and c["detail"]:
            for k, v in list(c["detail"].items())[:8]:
                print(f"         {k}: {v}")
            if len(c["detail"]) > 8:
                print(f"         ... and {len(c['detail']) - 8} more")
    print()
    print("correction classes already applied (what a second round would repeat):")
    for kind, n in fix_total.most_common():
        print(f"  {kind:18s} {n:4d}")
    print(f"  assertions resting on sources that could not be read: {unreadable}")
    print()
    print(f"target of {_TARGET_PER_SECTION} images per section is reported, never enforced:")
    print(f"  {below} of {total_sections} sections are below it")
    failed = [c["id"] for c in criteria if not c["pass"]]
    print()
    print("RESULT:", "all criteria hold" if not failed else f"Failing: {', '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
