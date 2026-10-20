"""Link published stories to curated sites from a checked proposal list, journalled.

Owner decision C1 (2026-10-20): "Matcher + Vorschlagsliste, jede einzeln
prüfen, dann journalisiert schreiben". The proposals come from the story-text
matcher (story_site_matcher.py), run read-only over the stock; a person checks
each line and marks the ones to write with ``"approved": true``. Nothing else
is written: a line without that mark is skipped.

Each line names the story, the site and the site the story had when the
proposal was made (``current_site_id``, null for none). A line is written only
while the story still has that site - the hourly match step or a person may
have linked it since - and only to a curated site that is not retired, the
sites with a page of their own (articles_html.site_curated).

Every line read gets one journal entry in
/app/logs/story_site_link/journal.jsonl (logs/ on the host): the outcome, the
site before and after, the match reason and the evidence the reviewer saw.
--rollback ID puts the site before back, provided the story still has the site
the link wrote. A dry run writes to dry_run.jsonl and changes nothing.

Each story whose site changed is announced to IndexNow at the end: the story
page now carries the site chip and related stories by site.

Run inside the Lyra container (it mounts logs/ read-write), the list on stdin:

    docker exec -i ancient_nerds_lyra python -m pipeline.lyra.story_site_link --dry-run < approved.jsonl
    docker exec -i ancient_nerds_lyra python -m pipeline.lyra.story_site_link < approved.jsonl
    docker exec ancient_nerds_lyra python -m pipeline.lyra.story_site_link --rollback 6609
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.database import NewsItem, UnifiedSite, get_session
from pipeline.indexnow import page_url, paths_for, submit
from pipeline.utils.public_sites import RETIRED

logger = logging.getLogger(__name__)

JOURNAL_DIR = Path("/app/logs/story_site_link")
CURATED_SOURCE = "ancient_nerds"


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


def _journal(out: Path, line: dict[str, Any]) -> None:
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")


def _outcome(session, proposal: dict[str, Any]) -> tuple[str, NewsItem | None, UnifiedSite | None]:
    """What writing the proposal would do: ``linked`` or why not."""
    if proposal.get("approved") is not True:
        return "not_approved", None, None
    item = session.get(NewsItem, int(proposal["story_id"]))
    if item is None:
        return "missing_story", None, None
    target = session.get(UnifiedSite, uuid.UUID(proposal["site_id"]))
    if target is None or target.source_id != CURATED_SOURCE or target.scope_status == RETIRED:
        return "not_curated", item, None
    if item.site_id == target.id:
        return "already_linked", item, target
    if item.site_id != _uuid_or_none(proposal.get("current_site_id")):
        return "changed_since_proposal", item, target
    return "linked", item, target


def apply(proposals: Iterable[dict[str, Any]], dry_run: bool) -> Counter[str]:
    """Write the approved proposals; see the module docstring."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    out = JOURNAL_DIR / ("dry_run.jsonl" if dry_run else "journal.jsonl")
    outcomes: Counter[str] = Counter()
    changed: list[tuple[int, str]] = []
    with get_session() as session:
        for proposal in proposals:
            outcome, item, target = _outcome(session, proposal)
            before = str(item.site_id) if item is not None and item.site_id else None
            if outcome == "linked":
                item.site_id = target.id
            _journal(
                out,
                {
                    "at": datetime.now(UTC).isoformat(),
                    "item_id": int(proposal["story_id"]),
                    "outcome": outcome,
                    "before": {"site_id": before},
                    "after": {"site_id": str(target.id)} if outcome == "linked" else {},
                    "site_name": proposal.get("site_name"),
                    "match_reason": proposal.get("match_reason"),
                    "evidence_snippet": proposal.get("evidence_snippet"),
                    "dry_run": dry_run,
                },
            )
            if outcome == "linked" and not dry_run:
                session.commit()
                changed.append((item.id, item.headline))
            else:
                session.rollback()
            outcomes[outcome] += 1
            logger.info("story %s: %s", proposal["story_id"], outcome)
    logger.info("IndexNow: %d URLs for %d linked stories", announce(changed), len(changed))
    return outcomes


def announce(stories: list[tuple[int, str]]) -> int:
    """IndexNow for the story pages whose site changed, and their hub."""
    if not stories:
        return 0
    urls = [page_url(path) for path in paths_for(stories, [], [], [])]
    submit(urls)
    return len(urls)


def rollback(item_id: int) -> dict[str, Any]:
    """Put the site before the item's last link back."""
    journal = JOURNAL_DIR / "journal.jsonl"
    entries = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    ]
    entry = next(
        (e for e in reversed(entries) if e["item_id"] == item_id and e["outcome"] == "linked"),
        None,
    )
    if entry is None:
        raise SystemExit(f"story_site_link: no link of story {item_id} in {journal}")
    with get_session() as session:
        item = session.get(NewsItem, item_id)
        written = uuid.UUID(entry["after"]["site_id"])
        if item.site_id != written:
            raise SystemExit(
                f"story_site_link: story {item_id} has site {item.site_id}, not {written} "
                "the link wrote; nothing rolled back"
            )
        item.site_id = _uuid_or_none(entry["before"]["site_id"])
        _journal(
            journal,
            {
                "at": datetime.now(UTC).isoformat(),
                "item_id": item_id,
                "outcome": "rolled_back",
                "before": entry["after"],
                "after": entry["before"],
                "dry_run": False,
            },
        )
        session.commit()
        announce([(item.id, item.headline)])
    return entry["before"]


def read_proposals(lines: Iterable[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in lines if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", type=int, metavar="ITEM_ID")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.rollback is not None:
        print(json.dumps(rollback(args.rollback), ensure_ascii=False))
        return
    print(dict(apply(read_proposals(sys.stdin), args.dry_run)))


if __name__ == "__main__":
    main()
