#!/usr/bin/env python
"""Verify every citation in a journal is legit.

For each [N] in the body, checks if the sentence and source share
topic relevance. Reports every mismatch.

Usage:
    python scripts/verify_journal.py --id 33
    python scripts/verify_journal.py --all          # all active
    python scripts/verify_journal.py --all --fix    # verify via LLM + fix
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["POSTGRES_PORT"] = "15432"
os.environ["POSTGRES_USER"] = "ancient_map"
os.environ["POSTGRES_PASSWORD"] = "ancient_map_dev_password"  # noqa: S105
os.environ["POSTGRES_DB"] = "ancient_map"
os.environ["DATABASE_URL"] = (
    "postgresql://ancient_map:ancient_map_dev_password@localhost:15432/ancient_map"
)

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def verify_article(article_id: int, fix: bool = False) -> dict:
    """Verify all citations in an article. Returns stats."""
    import psycopg2

    conn = psycopg2.connect(
        host="localhost", port=15432, user="ancient_map",
        password="ancient_map_dev_password", dbname="ancient_map",
    )
    cur = conn.cursor()
    cur.execute("SELECT title, content FROM news_articles WHERE id = %s", (article_id,))
    row = cur.fetchone()
    if not row:
        print(f"Article #{article_id} not found")
        return {}

    title, content = row

    # Parse sources
    src_idx = max(content.find("### Sources"), content.find("## Sources"))
    body = content[:src_idx] if src_idx > 0 else content
    sources_text = content[src_idx:] if src_idx > 0 else ""

    sources = {}
    for line in sources_text.split("\n"):
        m = re.match(r"^(\d+)\.\s+\[(.+?)\]\((https?://\S+?)\)", line.strip())
        if m:
            sources[int(m.group(1))] = {"label": m.group(2), "url": m.group(3)}
        else:
            m2 = re.match(r"^(\d+)\.\s+(.+)", line.strip())
            if m2:
                sources[int(m2.group(1))] = {"label": m2.group(2), "url": ""}

    # Check every citation
    sentences = re.split(r"(?<=[.!?])\s+", body)
    total = 0
    verified = 0
    mismatches = []

    for sent in sentences:
        cites = re.findall(r"\[(\d+)\]", sent)
        for c in cites:
            num = int(c)
            if num not in sources:
                continue
            total += 1
            src = sources[num]
            # Keyword overlap check
            sent_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", sent)}
            src_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", src["label"])}
            overlap = sent_words & src_words
            if len(overlap) >= 1:
                verified += 1
            else:
                mismatches.append({
                    "citation": num,
                    "sentence": sent[:100],
                    "source": src["label"][:80],
                    "overlap": list(overlap),
                })

    # Report
    pct = (verified / total * 100) if total > 0 else 0
    status = "CLEAN" if not mismatches else "DIRTY"

    print(f"\n{'=' * 60}")
    print(f"Article #{article_id}: {title[:50]}")
    print(f"Citations: {total} total, {verified} verified, {len(mismatches)} mismatches")
    print(f"Score: {pct:.0f}% — {status}")

    if mismatches:
        print(f"\nMismatches:")
        for mm in mismatches[:20]:
            print(f"  [{mm['citation']}] {mm['sentence'][:70]}...")
            print(f"       Source: {mm['source']}")

    if fix and mismatches:
        print(f"\nRunning LLM verification to fix...")
        from pipeline.lyra.citation_verifier import verify_all_citations
        from pipeline.lyra.config import _get_settings

        settings = _get_settings()
        sources_list = [
            {"citation": num, "label": s["label"], "url": s["url"], "snippet": s["label"]}
            for num, s in sources.items()
        ]
        fixed = verify_all_citations(content, sources_list, settings=settings)
        if fixed != content:
            cur.execute("UPDATE news_articles SET content = %s WHERE id = %s", (fixed, article_id))
            conn.commit()
            print("FIXED and saved")
        else:
            print("No changes needed")

    conn.close()
    return {"total": total, "verified": verified, "mismatches": len(mismatches)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="Article ID")
    parser.add_argument("--all", action="store_true", help="All active articles")
    parser.add_argument("--fix", action="store_true", help="Run LLM verification + fix")
    args = parser.parse_args()

    if args.id:
        verify_article(args.id, fix=args.fix)
    elif args.all:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=15432, user="ancient_map",
            password="ancient_map_dev_password", dbname="ancient_map",
        )
        cur = conn.cursor()
        cur.execute("SELECT id FROM news_articles WHERE active = true ORDER BY week_start")
        ids = [r[0] for r in cur.fetchall()]
        conn.close()

        if not ids:
            print("No active articles")
            return

        all_clean = True
        for aid in ids:
            result = verify_article(aid, fix=args.fix)
            if result.get("mismatches", 0) > 0:
                all_clean = False

        print(f"\n{'=' * 60}")
        if all_clean:
            print("ALL ARTICLES CLEAN")
        else:
            print("SOME ARTICLES HAVE MISMATCHED CITATIONS")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
