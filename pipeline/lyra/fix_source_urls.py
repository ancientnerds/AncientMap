"""Percent-encode raw parens inside stored `[Source](url)` markdown.

Wikimedia Commons filenames contain literal parens (e.g.
`File_(1904)_(14781541291).jpg`). Standard markdown `[label](url)` parsing
terminates at the first unescaped `)`, so the remainder of the URL spills
into the prose as raw text. The pipeline now URL-encodes parens at emit
time (`theo_image_captions.image_markdown`), but existing papers still have
broken markdown baked into `result_json.report`.

This script walks the report markdown, finds every `[Source](` opening, and
scans forward to the *real* URL terminator (a `)` immediately followed by
whitespace or end-of-string — we always emit `\\n` after the link). Every
`(` or `)` between opener and terminator becomes `%28` / `%29`. Also walks
`probative_images[].source_url` and encodes the same chars there so
subsequent backfills/reflows see clean URLs.

Idempotent — re-running on already-encoded markdown is a no-op.

Usage:
    python -m pipeline.lyra.fix_source_urls --slug SLUG             # dry-run
    python -m pipeline.lyra.fix_source_urls --slug SLUG --apply
    python -m pipeline.lyra.fix_source_urls --all --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from pipeline.database import engine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _encode_parens(url: str) -> str:
    return url.replace("(", "%28").replace(")", "%29") if url else url


def _encode_source_links(report: str) -> tuple[str, int]:
    """Rewrite every `[Source](url)` so parens in the URL become %28/%29.

    Returns (new_report, number_of_links_modified). A link is counted as
    "modified" only if it actually contained a raw `(` or `)` — already-clean
    links stay byte-identical.
    """
    if not report:
        return report, 0

    out: list[str] = []
    modified = 0
    i = 0
    marker = "[Source]("
    while i < len(report):
        j = report.find(marker, i)
        if j == -1:
            out.append(report[i:])
            break
        # Everything up to and including "[Source]("
        out.append(report[i:j])
        out.append(marker)
        url_start = j + len(marker)

        # Scan forward for the URL terminator: a `)` immediately followed by
        # whitespace or end-of-string. Everything before is URL content.
        k = url_start
        terminator = -1
        while k < len(report):
            if report[k] == ")":
                nxt = report[k + 1] if k + 1 < len(report) else ""
                # Real terminator if end-of-string or next char is whitespace/eol.
                if nxt == "" or nxt in " \t\r\n":
                    terminator = k
                    break
            k += 1

        if terminator == -1:
            # No clean terminator found — leave the remainder untouched rather
            # than risk corrupting valid text. (This path shouldn't hit in
            # practice because every [Source] line ends with \n.)
            out.append(report[url_start:])
            break

        raw_url = report[url_start:terminator]
        encoded = _encode_parens(raw_url)
        if encoded != raw_url:
            modified += 1
        out.append(encoded)
        out.append(")")
        i = terminator + 1

    return "".join(out), modified


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


def _process(paper: dict, apply: bool) -> tuple[str, str]:
    slug = paper["slug"]
    try:
        result = json.loads(paper["result_json"]) if paper["result_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return (slug, "invalid result_json")

    report = result.get("report", "") or ""
    new_report, link_hits = _encode_source_links(report)

    probative = result.get("probative_images") or []
    pi_hits = 0
    new_probative = []
    for entry in probative:
        if not isinstance(entry, dict):
            new_probative.append(entry)
            continue
        su = entry.get("source_url", "") or ""
        wp = entry.get("web_path", "") or ""
        su_enc = _encode_parens(su)
        wp_enc = _encode_parens(wp)
        if su_enc != su or wp_enc != wp:
            pi_hits += 1
        new_entry = dict(entry)
        new_entry["source_url"] = su_enc
        new_entry["web_path"] = wp_enc
        new_probative.append(new_entry)

    if link_hits == 0 and pi_hits == 0:
        return (slug, "clean — nothing to encode")

    if not apply:
        return (
            slug,
            f"would encode {link_hits} [Source] link(s), {pi_hits} probative entries (dry-run)",
        )

    result["report"] = new_report
    if new_probative:
        result["probative_images"] = new_probative
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE research_requests SET result_json = :json WHERE id = :id"),
            {"json": json.dumps(result), "id": paper["id"]},
        )
        conn.commit()
    return (slug, f"encoded {link_hits} [Source] link(s), {pi_hits} probative entries")


def main() -> None:
    p = argparse.ArgumentParser(description="Percent-encode parens inside [Source](url) markdown")
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
    updated = 0
    for paper in papers:
        slug, reason = _process(paper, args.apply)
        logger.info("  %s — %s", slug, reason)
        if reason.startswith("encoded") or reason.startswith("would encode"):
            updated += 1

    logger.info("")
    logger.info("=== Summary ===")
    logger.info("  Papers %s: %d", "encoded" if args.apply else "would encode", updated)


if __name__ == "__main__":
    main()
