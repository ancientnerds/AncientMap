"""Clean raw filenames out of inline image titles + captions.

Walks `result_json.report` and rewrites alt text + the first segment of each
`*Title. Photo: Artist / Source.*` caption using `_clean_title()` — strips
.jpg/.png extensions, trailing Wikimedia upload-id groups, and collapses
underscores into spaces.

No external API calls, no reliance on stored probative_images metadata — this
backfill works on the markdown alone, which matters for papers whose
convergence run pre-dated the worker's probative_images persistence fix.

Usage:
    python -m pipeline.lyra.clean_image_titles --slug SLUG             # dry-run
    python -m pipeline.lyra.clean_image_titles --slug SLUG --apply     # write
    python -m pipeline.lyra.clean_image_titles --all --apply           # every public paper
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from pipeline.database import engine
from pipeline.lyra.theo_image_captions import _clean_title

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# Match any inline image block. Alt + optional caption + optional [Source].
# Non-greedy on caption so adjacent blocks don't bleed into one match.
_BLOCK_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<path>/data/research-images/[^)]+)\)"
    r"(?P<tail>\s*\n\n\*(?P<caption>[^*\n][^*]*?)\*"
    r"(?:\s*\n\[Source\]\([^)]+\))?)?",
    re.MULTILINE,
)


def _rewrite_caption(caption: str) -> str:
    """Clean just the lead (pre-`. Photo:`) segment of the caption."""
    # Caption pattern: `Lead. Photo: X / Y. Tail.` — split on the first `. Photo:`
    m = re.match(r"^(?P<lead>.*?)(?P<rest>\.\s*Photo:.*)$", caption, re.DOTALL)
    if not m:
        # No photo-line; clean the whole caption as a title.
        return _clean_title(caption) or caption
    lead = m.group("lead").strip().rstrip(".")
    cleaned_lead = _clean_title(lead)
    if not cleaned_lead or cleaned_lead == lead:
        return caption
    return f"{cleaned_lead}{m.group('rest')}"


def _rewrite_report(report: str) -> tuple[str, int]:
    """Clean alt + caption lead on every inline image block. Returns (new, count)."""
    rewrites = 0

    def _sub(match: re.Match) -> str:
        nonlocal rewrites
        alt = match.group("alt") or ""
        path = match.group("path")
        caption = match.group("caption") or ""
        tail = match.group("tail") or ""

        cleaned_alt = _clean_title(alt) or alt

        new_tail = tail
        if caption:
            new_caption = _rewrite_caption(caption)
            if new_caption != caption:
                new_tail = tail.replace(f"*{caption}*", f"*{new_caption}*", 1)

        if cleaned_alt == alt and new_tail == tail:
            return match.group(0)

        rewrites += 1
        return f"![{cleaned_alt}]({path}){new_tail}"

    new_text = _BLOCK_RE.sub(_sub, report)
    return new_text, rewrites


def _clean_probative_entries(entries: list[dict]) -> tuple[list[dict], int]:
    """Apply _clean_title to stored probative_images entries in place."""
    changed = 0
    out: list[dict] = []
    for e in entries or []:
        raw = e.get("title") or ""
        cleaned = _clean_title(raw)
        if cleaned and cleaned != raw:
            e = {**e, "title": cleaned}
            changed += 1
        out.append(e)
    return out, changed


def _fetch_papers(slug: str | None, request_id: str | None) -> list[dict]:
    with engine.connect() as conn:
        if request_id:
            # Accept raw UUID; don't require is_public so unpublished drafts
            # can be cleaned up before publish.
            rows = conn.execute(
                text(
                    "SELECT id::text, slug, result_json FROM research_requests "
                    "WHERE id::text = :rid AND status = 'completed'"
                ),
                {"rid": request_id},
            ).fetchall()
        elif slug:
            rows = conn.execute(
                text(
                    "SELECT id::text, slug, result_json FROM research_requests "
                    "WHERE slug = :slug AND status = 'completed'"
                ),
                {"slug": slug},
            ).fetchall()
        else:
            rows = conn.execute(
                text(
                    "SELECT id::text, slug, result_json FROM research_requests "
                    "WHERE is_public = TRUE AND status = 'completed' "
                    "ORDER BY published_at DESC"
                )
            ).fetchall()
    return [{"id": r.id, "slug": r.slug or r.id, "result_json": r.result_json} for r in rows]


def _process(paper: dict, apply: bool) -> tuple[str, int, str]:
    slug = paper["slug"]
    try:
        result = json.loads(paper["result_json"]) if paper["result_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return (slug, 0, "invalid result_json")

    report = result.get("report", "") or ""
    if not report:
        return (slug, 0, "empty report")

    new_report, count = _rewrite_report(report)

    probative = result.get("probative_images") or []
    cleaned_entries, entry_changes = _clean_probative_entries(probative)

    if count == 0 and entry_changes == 0:
        return (slug, 0, "no titles to clean")

    if not apply:
        return (
            slug,
            count,
            f"would clean {count} image block(s) + {entry_changes} probative entry title(s) (dry-run)",
        )

    result["report"] = new_report
    if entry_changes:
        result["probative_images"] = cleaned_entries
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE research_requests SET result_json = :json WHERE id = :id"),
            {"json": json.dumps(result), "id": paper["id"]},
        )
        conn.commit()
    return (
        slug,
        count,
        f"cleaned {count} image block(s) + {entry_changes} probative entry title(s)",
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Clean raw filenames out of inline image titles")
    p.add_argument("--slug", type=str, default=None)
    p.add_argument("--id", dest="request_id", type=str, default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    if not args.slug and not args.all and not args.request_id:
        logger.error("Refusing to run without --slug, --id, or --all")
        return

    if not args.apply:
        logger.info("DRY RUN — no changes written (use --apply to confirm)")

    papers = _fetch_papers(args.slug, args.request_id)
    if not papers:
        logger.info("No papers found.")
        return

    logger.info("Found %d paper(s)", len(papers))
    total = 0
    for paper in papers:
        slug, n, reason = _process(paper, args.apply)
        logger.info("  %s — %s", slug, reason)
        total += n

    logger.info("")
    logger.info("=== Summary ===")
    logger.info("  Image blocks %s: %d", "cleaned" if args.apply else "would clean", total)


if __name__ == "__main__":
    main()
