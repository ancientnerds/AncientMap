"""Rewrite image captions + [Source] links on already-embedded papers.

No external API calls — walks `result_json.report`, locates each stored image
block by its `web_path`, and regenerates the caption + [Source] using the
metadata already saved in `result_json.probative_images` via the current
`build_caption` rules.

Use this after changing caption formatting (dropping license, changing source
URL precedence, etc.) so existing papers reflect the new rules without having
to re-run the full probative backfill.

Usage:
    python -m pipeline.lyra.rewrite_image_captions --slug SLUG             # dry-run
    python -m pipeline.lyra.rewrite_image_captions --slug SLUG --apply     # write
    python -m pipeline.lyra.rewrite_image_captions --all --apply           # every public paper
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
from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.theo_image_captions import build_caption

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# Matches: ![alt](web_path)\n\n*caption*[\n[Source](url)]?
# Alt may or may not carry the gallery: prefix.
_BLOCK_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<path>/data/research-images/[^)]+)\)"
    r"\s*\n\n"
    r"\*(?P<caption>[^*\n][^*]*?)\*"
    r"(?:\s*\n\[Source\]\((?P<src>[^)]+)\))?",
    re.MULTILINE,
)


def _cand_from_entry(entry: dict) -> ImageCandidate:
    """Reconstruct an ImageCandidate from a stored probative_images entry."""
    return ImageCandidate(
        url=entry.get("source_url", "") or "",
        source=entry.get("source_name", "") or "",
        title=entry.get("title", "") or "",
        artist=entry.get("artist", "") or "",
        license=entry.get("license", "") or "",
        license_url=entry.get("license_url", "") or "",
    )


def _rewrite_report(report: str, probative_images: list[dict]) -> tuple[str, int]:
    """Rebuild caption + [Source] for every stored image. Returns (new_text, count)."""
    by_path: dict[str, dict] = {e["web_path"]: e for e in probative_images if e.get("web_path")}
    if not by_path:
        return report, 0

    rewrites = 0

    def _sub(match: re.Match) -> str:
        nonlocal rewrites
        path = match.group("path")
        entry = by_path.get(path)
        if not entry:
            return match.group(0)  # unknown image — leave alone
        cand = _cand_from_entry(entry)
        rationale = entry.get("rationale", "") or ""
        new_caption = build_caption(cand, rationale)
        # Source URL: prefer cand.url (image origin page), fall back to license_url
        source_url = cand.url or cand.license_url
        alt = match.group("alt")
        source_part = f"\n[Source]({source_url})" if source_url else ""
        rewrites += 1
        return f"![{alt}]({path})\n\n{new_caption}{source_part}"

    new_text = _BLOCK_RE.sub(_sub, report)
    return new_text, rewrites


def _fetch_papers(slug: str | None) -> list[dict]:
    with engine.connect() as conn:
        if slug:
            rows = conn.execute(
                text(
                    "SELECT id::text, slug, result_json FROM research_requests "
                    "WHERE slug = :slug AND is_public = TRUE AND status = 'completed'"
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
    return [{"id": r.id, "slug": r.slug, "result_json": r.result_json} for r in rows]


def _process(paper: dict, apply: bool) -> tuple[str, int, str]:
    slug = paper["slug"]
    try:
        result = json.loads(paper["result_json"]) if paper["result_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return (slug, 0, "invalid result_json")

    report = result.get("report", "") or ""
    probative = result.get("probative_images") or []
    if not report or not probative:
        return (slug, 0, "no report or no probative_images")

    new_report, count = _rewrite_report(report, probative)
    if count == 0:
        return (slug, 0, "no matching image blocks found")
    if new_report == report:
        return (slug, 0, f"{count} block(s) matched but caption text unchanged")

    if not apply:
        return (slug, count, f"would rewrite {count} caption(s) (dry-run)")

    result["report"] = new_report
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE research_requests SET result_json = :json WHERE id = :id"),
            {"json": json.dumps(result), "id": paper["id"]},
        )
        conn.commit()
    return (slug, count, f"rewrote {count} caption(s)")


def main() -> None:
    p = argparse.ArgumentParser(description="Rewrite image captions on existing papers")
    p.add_argument("--slug", type=str, default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    if not args.slug and not args.all:
        logger.error("Refusing to run without --slug or --all")
        return

    if not args.apply:
        logger.info("DRY RUN — no changes written (use --apply to confirm)")

    papers = _fetch_papers(args.slug)
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
    logger.info("  Captions %s: %d", "rewritten" if args.apply else "would rewrite", total)


if __name__ == "__main__":
    main()
