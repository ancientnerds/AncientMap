"""Run the current web verifier over published stories, in waves.

Stories written before 2026-10-09 went through a verifier that corrected the
post alone and forbade attributing a claim to the video: in a sample of 40
public stories 27.5 % stated a disputed claim as fact and 32.5 % carried a
wrong fact or a contradiction between headline, key facts and post (SEO audit
2026-10-08). The owner decided on 2026-10-09 to re-run the stock in waves.

What a wave does with each story, by the verifier's verdict:

* CORRECTED - headline, key facts and post are replaced together, exactly as
  the live verifier does (tweet_verifier.apply_web_verdict). A new headline
  changes the slug; the old URL answers 301, since the page resolves by id.
* REJECT - NOT applied. The live cycle withdraws a rejected new story; a
  re-run does not withdraw a story that may be indexed and visited, because a
  mass withdrawal of indexed URLs cost search traffic on 2026-09-11. The
  verdict is journalled for a person to review.
* VERIFIED - nothing changes; journalled.

Every story a wave touches gets one journal line in
/app/logs/story_reverify/journal.jsonl (logs/ on the host): the verdict, the
reason and the headline, facts and post before and after. A story in the
journal is never picked again, and --rollback ID puts its before-values back.
A dry run writes to dry_run.jsonl, changes nothing and marks nothing as done.

Run inside the Lyra container (it mounts logs/ and has the MiniMax key):

    docker exec ancient_nerds_lyra python -m pipeline.lyra.story_reverify --limit 50
    docker exec ancient_nerds_lyra python -m pipeline.lyra.story_reverify --limit 20 --dry-run
    docker exec ancient_nerds_lyra python -m pipeline.lyra.story_reverify --rollback 6609
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import _get_settings
from pipeline.lyra.tweet_verifier import apply_web_verdict, open_web_verifier, web_verify_item
from pipeline.news_visibility import public_story_criteria

logger = logging.getLogger(__name__)

JOURNAL_DIR = Path("/app/logs/story_reverify")
#: When the summary prompt that attributes a video's claims went live (deploy
#: 2556cc4, UTC): stories written since were born with it and need no re-run.
SUMMARY_FIX_LIVE = datetime(2026, 10, 9, 8, 42)
#: Outcomes that settle a story. A failed check or one without search results
#: settled nothing, so a later wave tries the story again.
SETTLED = ("corrected", "verified", "reject_held", "not_applied")

#: The fields a correction may change (and the sources the check appends): what a rollback restores.
FIELDS = ("headline", "facts", "post_text", "web_sources")
#: Alt-history channels first (owner: "zuerst Alt-Kanäle"): 10 of 25 of their
#: stories in the audit sample stated a disputed claim as fact, 1 of 15 of the
#: mainstream ones. Names as in pipeline/lyra/channels.json.
ALT_CHANNELS = (
    "Ancient Architects",
    "Curious Being",
    "Bright Insight",
    "Wandering Wolf",
    "MegalithomaniaUK",
    "Funny Olde World",
    "Universe Inside You",
    "Dark5 Ancient Mysteries",
    "UnchartedX",
    "Timeless with Fred Snyder",
    "One-eyed giant building walls",
    "Institute for Natural Philosophy",
    "Luke Caverns",
    "Matthew LaCroix",
    "Michael Button",
    "The Randall Carlson",
    "SPIRIT in STONE",
    "Pillars of the Past",
    "Earth Explorer",
    "GeoCosmic REX",
    "Brothers of the Serpent",
    "PraveenMohan",
    "Brien Foerster",
    "Anyextee",
    "Viking Superpowers",
    "Ancient Builders Project",
    "The Cosmic Summit",
    "The Archivist's Journal",
)


def _snapshot(item: NewsItem) -> dict[str, Any]:
    return {f: getattr(item, f) for f in FIELDS}


def journalled_ids(journal: Path) -> set[int]:
    if not journal.exists():
        return set()
    entries = (
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    )
    return {e["item_id"] for e in entries if e["outcome"] in SETTLED}


def pick(session, limit: int, done: set[int], alt_first: bool) -> list[NewsItem]:
    """The next public stories no wave has touched: alt-history channels first,
    newest video first within each group."""
    from pipeline.database import NewsChannel

    rows = (
        session.query(NewsItem.id, NewsChannel.name)
        .join(NewsVideo, NewsItem.video_id == NewsVideo.id)
        .join(NewsChannel, NewsVideo.channel_id == NewsChannel.id)
        .filter(*public_story_criteria(), NewsItem.created_at < SUMMARY_FIX_LIVE)
        .order_by(NewsVideo.published_at.desc(), NewsItem.id.desc())
        .all()
    )
    ids = [r.id for r in rows if r.id not in done and (not alt_first or r.name in ALT_CHANNELS)]
    if alt_first and len(ids) < limit:
        ids += [r.id for r in rows if r.id not in done and r.name not in ALT_CHANNELS]
    chosen = ids[:limit]
    if not chosen:
        return []
    by_id = {i.id: i for i in session.query(NewsItem).filter(NewsItem.id.in_(chosen)).all()}
    return [by_id[i] for i in chosen]


def run_wave(limit: int, dry_run: bool, alt_first: bool = True) -> Counter[str]:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    journal = JOURNAL_DIR / "journal.jsonl"
    out = JOURNAL_DIR / ("dry_run.jsonl" if dry_run else "journal.jsonl")
    settings = _get_settings()
    verifier = open_web_verifier(settings)
    if verifier is None:
        raise SystemExit("story_reverify: MiniMax is not configured (no MiniMax key)")
    outcomes: Counter[str] = Counter()
    with get_session() as session:
        for item in pick(session, limit, journalled_ids(journal), alt_first):
            before = _snapshot(item)
            status, result = web_verify_item(item, verifier, settings)
            outcome = (
                apply_web_verdict(item, result, withdraw_on_reject=False)
                if result is not None
                else status
            )
            after = _snapshot(item)
            line = {
                "at": datetime.now(UTC).isoformat(),
                "item_id": item.id,
                "outcome": outcome,
                "reason": (result or {}).get("reason"),
                "before": before,
                "after": {f: v for f, v in after.items() if v != before[f]},
                "dry_run": dry_run,
            }
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
            if dry_run:
                session.rollback()
            else:
                session.commit()
            outcomes[outcome] += 1
            logger.info("story %s: %s", item.id, outcome)
    return outcomes


def rollback(item_id: int) -> dict[str, Any]:
    """Put the before-values of the item's journal line back."""
    lines = [
        json.loads(line)
        for line in (JOURNAL_DIR / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    entry = next(e for e in reversed(lines) if e["item_id"] == item_id)
    with get_session() as session:
        item = session.get(NewsItem, item_id)
        for field, value in entry["before"].items():
            setattr(item, field, value)
        session.commit()
    return entry["before"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all-channels", action="store_true", help="no alt-history channels first")
    parser.add_argument("--rollback", type=int, metavar="ITEM_ID")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.rollback is not None:
        print(json.dumps(rollback(args.rollback), ensure_ascii=False, default=str))
        return
    print(dict(run_wave(args.limit, args.dry_run, alt_first=not args.all_channels)))


if __name__ == "__main__":
    main()
