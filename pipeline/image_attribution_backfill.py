"""
Backfill Wikimedia attribution (author, licence, Commons link) on wiki_images.

All 49,766 rows were written by a one-day importer run on 2026-03-14 that
stored neither author nor licence nor even the Commons URL — original_url
holds the LOCAL file path. Commons licences (CC BY-SA et al.) require
attribution, so these fields are not optional.

The only recoverable key is the local filename stem, which the importer
derived from the Commons file title (extension swapped for .webp). MediaWiki
treats spaces and underscores as the same title, so the stem resolves
directly; only the original extension is unknown. The backfill therefore
asks the Commons API in rounds — File:{stem}.jpg first (the vast majority),
then .JPG/.png/.jpeg/.PNG — 50 titles per request, one request per second
per the robot policy, with redirects=1 so renamed files still resolve.

Resumable by design: only rows with author IS NULL AND license IS NULL AND
commons_page_url IS NULL are candidates, and every resolved batch commits
immediately. Rows whose title no longer resolves (deleted or renamed beyond
redirect) stay NULL and are counted — no data is invented for them.

Usage (inside a container with DB access):
    python -m pipeline.image_attribution_backfill             # full run
    python -m pipeline.image_attribution_backfill --limit 200 # trial slice
"""

import argparse
import time

from loguru import logger
from sqlalchemy import text

from pipeline.database import get_session
from pipeline.wiki_image_downloader import (
    COMMONS_API_URL,
    _http_client,
    commons_page_url_for,
    parse_attribution,
)

# The importer swapped the original extension for .webp; these cover the
# Commons reality in descending frequency. Each round only re-queries the
# stems the previous round could not resolve.
EXTENSION_ROUNDS = ("jpg", "JPG", "png", "jpeg", "PNG", "gif", "tif")

BATCH_SIZE = 50  # MediaWiki maximum for titles=
REQUEST_DELAY = 1.0  # seconds, per Wikimedia robot policy


def title_candidates(filename: str, ext: str) -> str:
    """Commons File: title guess for a local .webp filename and an extension."""
    stem = filename[:-5] if filename.endswith(".webp") else filename
    return f"File:{stem}.{ext}"


def fetch_batch(titles: list[str]) -> dict[str, dict]:
    """Resolve up to 50 File: titles to attribution dicts.

    Returns {queried_title: attribution} — the API normalises titles
    (underscores to spaces, first-letter case) and reports renames under
    `redirects`; both mappings are folded back onto the QUERIED title so the
    caller can match results to database rows.
    """
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "extmetadata|size|url",
        "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
        "redirects": "1",
        "format": "json",
    }
    resp = _http_client.get(COMMONS_API_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    query = data.get("query", {})

    # response title -> queried title, through both rewrite layers
    back: dict[str, str] = {}
    for mapping in query.get("normalized", []):
        back[mapping["to"]] = mapping["from"]
    for mapping in query.get("redirects", []):
        source = back.get(mapping["from"], mapping["from"])
        back[mapping["to"]] = source

    results: dict[str, dict] = {}
    for page in query.get("pages", {}).values():
        if "missing" in page:
            continue
        info_list = page.get("imageinfo", [])
        if not info_list:
            continue
        response_title = page.get("title", "")
        queried = back.get(response_title, response_title)
        meta = parse_attribution(info_list[0])
        # The canonical (possibly redirected) title makes the better page link.
        meta["commons_page_url"] = commons_page_url_for(response_title)
        results[queried] = meta
    return results


def load_candidates(limit: int | None) -> list[tuple[int, str]]:
    """(id, filename) of every row still missing all attribution fields."""
    sql = """
        SELECT id, filename FROM wiki_images
        WHERE author IS NULL AND license IS NULL AND commons_page_url IS NULL
        ORDER BY id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_session() as session:
        return [(row.id, row.filename) for row in session.execute(text(sql)).fetchall()]


def apply_batch(resolved: dict[int, dict]) -> int:
    """Write resolved attribution; original_url only where it stays unique."""
    written = 0
    with get_session() as session:
        for row_id, meta in resolved.items():
            session.execute(
                text("""
                    UPDATE wiki_images
                    SET author = :author, author_url = :author_url,
                        license = :license, license_url = :license_url,
                        commons_page_url = :commons_page_url
                    WHERE id = :id
                """),
                {
                    "id": row_id,
                    "author": meta["author"],
                    "author_url": meta["author_url"],
                    "license": meta["license"],
                    "license_url": meta["license_url"],
                    "commons_page_url": meta["commons_page_url"],
                },
            )
            # original_url currently holds the LOCAL path (importer bug). The
            # real Commons URL is worth repairing, but (site_id, original_url)
            # is unique — a same-site duplicate keeps its local path instead
            # of failing the whole batch.
            if meta.get("original_url"):
                session.execute(
                    text("""
                        UPDATE wiki_images SET original_url = :url
                        WHERE id = :id AND NOT EXISTS (
                            SELECT 1 FROM wiki_images other
                            WHERE other.site_id = (
                                SELECT site_id FROM wiki_images WHERE id = :id
                            )
                            AND other.original_url = :url AND other.id <> :id
                        )
                    """),
                    {"id": row_id, "url": meta["original_url"]},
                )
            written += 1
        session.commit()
    return written


def run(limit: int | None) -> None:
    candidates = load_candidates(limit)
    logger.info(f"{len(candidates)} rows missing attribution")

    pending = candidates
    total_written = 0
    for ext in EXTENSION_ROUNDS:
        if not pending:
            break
        logger.info(f"Round .{ext}: {len(pending)} unresolved rows")
        unresolved: list[tuple[int, str]] = []
        for start in range(0, len(pending), BATCH_SIZE):
            chunk = pending[start : start + BATCH_SIZE]
            titles = {title_candidates(fn, ext): rid for rid, fn in chunk}
            try:
                found = fetch_batch(list(titles.keys()))
            except Exception as exc:
                # One failed request must not lose the resumable run — the
                # rows stay NULL and the next invocation picks them up.
                logger.warning(f"batch failed ({exc}); rows deferred")
                unresolved.extend(chunk)
                time.sleep(REQUEST_DELAY * 10)
                continue

            resolved = {titles[t]: meta for t, meta in found.items()}
            missing = [(rid, fn) for rid, fn in chunk if rid not in resolved]
            unresolved.extend(missing)
            if resolved:
                total_written += apply_batch(resolved)
            if (start // BATCH_SIZE) % 20 == 0:
                logger.info(
                    f"  .{ext} progress {start + len(chunk)}/{len(pending)}, "
                    f"written so far {total_written}"
                )
            time.sleep(REQUEST_DELAY)
        pending = unresolved

    logger.info("=" * 60)
    logger.info(f"Attribution written: {total_written}")
    logger.info(f"Unresolvable (deleted/renamed beyond redirect): {len(pending)}")
    if pending:
        sample = ", ".join(fn for _, fn in pending[:5])
        logger.info(f"  examples: {sample}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--limit", type=int, default=None, help="only the first N rows")
    args = parser.parse_args()
    run(args.limit)


if __name__ == "__main__":
    main()
