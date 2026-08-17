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
from pathlib import Path

from loguru import logger
from PIL import Image
from sqlalchemy import text

from pipeline.database import get_session
from pipeline.wiki_image_downloader import (
    COMMONS_API_URL,
    WIKIPEDIA_ACTION_API,
    _download_client,
    _http_client,
    commons_page_url_for,
    extract_title_from_url,
    parse_attribution,
    wikipedia_opensearch,
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


def load_candidates(limit: int | None) -> list[tuple[int, str, str]]:
    """(id, site_id, filename) of every row still missing all attribution fields."""
    sql = """
        SELECT id, site_id::text AS site_id, filename FROM wiki_images
        WHERE author IS NULL AND license IS NULL AND commons_page_url IS NULL
        ORDER BY id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_session() as session:
        return [
            (row.id, row.site_id, row.filename) for row in session.execute(text(sql)).fetchall()
        ]


RATIO_TOLERANCE = 0.02


def ratio_matches(local_path: Path, remote_width, remote_height) -> bool:
    """Whether the local file's aspect ratio matches the Commons candidate.

    The stem is an exact title, but extensions are guessed in rounds — if the
    original was X.png and a DIFFERENT X.jpg exists on Commons, the stem
    resolves to the wrong photograph. The local file is the ground truth the
    site actually shows; a diverging aspect ratio kills the match. A missing
    local file accepts the title match (nothing is displayed either way), and
    missing remote dimensions never happen for real files.
    """
    if not remote_width or not remote_height:
        return False
    if not local_path.exists():
        return True
    with Image.open(local_path) as img:
        local_ratio = img.width / img.height
    remote_ratio = remote_width / remote_height
    return abs(local_ratio - remote_ratio) / remote_ratio <= RATIO_TOLERANCE


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
        unresolved: list[tuple[int, str, str]] = []
        for start in range(0, len(pending), BATCH_SIZE):
            chunk = pending[start : start + BATCH_SIZE]
            titles = {title_candidates(fn, ext): (rid, sid, fn) for rid, sid, fn in chunk}
            try:
                found = fetch_batch(list(titles.keys()))
            except Exception as exc:
                # One failed request must not lose the resumable run — the
                # rows stay NULL and the next invocation picks them up.
                logger.warning(f"batch failed ({exc}); rows deferred")
                unresolved.extend(chunk)
                time.sleep(REQUEST_DELAY * 10)
                continue

            resolved: dict[int, dict] = {}
            for title, meta in found.items():
                rid, sid, fn = titles[title]
                local_path = HERO_DIR / sid.replace("-", "")[:8] / fn
                if ratio_matches(local_path, meta.get("width"), meta.get("height")):
                    resolved[rid] = meta
                # A ratio mismatch means the guessed extension hit a different
                # photograph — the row stays NULL for a later, verified round.
            missing = [(rid, sid, fn) for rid, sid, fn in chunk if rid not in resolved]
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
        sample = ", ".join(fn for _, _, fn in pending[:5])
        logger.info(f"  examples: {sample}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--limit", type=int, default=None, help="only the first N rows")
    parser.add_argument(
        "--heroes",
        action="store_true",
        help="phase 2: resolve the renamed hero.webp files via the article lead image",
    )
    args = parser.parse_args()
    if args.heroes:
        backfill_heroes(args.limit)
    else:
        run(args.limit)


if __name__ == "__main__":
    main()


# =============================================================================
# Phase 2: heroes. The importer renamed every lead image to hero.webp, so the
# stem carries no Commons title. The article's lead image is the obvious
# candidate — but articles change, and a wrong credit is worse than none
# (source-integrity rule). So the candidate must PROVE itself: its thumbnail
# is downloaded and perceptually compared against the local hero.webp;
# attribution is only written on a match.
# =============================================================================

HERO_DIR = Path("public/data/images/wiki")

# 64-bit difference hash; distance <= 6 on re-encoded/re-scaled copies of the
# same photo, typically > 20 between different photos of the same site.
DHASH_MAX_DISTANCE = 6


def dhash(image) -> int:
    """64-bit difference hash of a PIL image (9x8 grayscale gradient)."""
    gray = image.convert("L").resize((9, 8), Image.LANCZOS)
    pixels = list(gray.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _lead_image_title(article_title: str) -> str | None:
    """The article's lead image file title via prop=pageimages."""
    resp = _http_client.get(
        WIKIPEDIA_ACTION_API,
        params={
            "action": "query",
            "titles": article_title,
            "prop": "pageimages",
            "piprop": "name",
            "redirects": "1",
            "format": "json",
        },
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    page: dict = next(iter(pages.values()), {})
    name = page.get("pageimage")
    return f"File:{name}" if name else None


def _hero_rows() -> list[dict]:
    sql = """
        SELECT w.id, w.site_id::text AS site_id, s.source_url, s.name
        FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
        WHERE w.filename = 'hero.webp'
          AND w.author IS NULL AND w.license IS NULL AND w.commons_page_url IS NULL
        ORDER BY w.id
    """
    with get_session() as session:
        return [dict(row._mapping) for row in session.execute(text(sql)).fetchall()]


def backfill_heroes(limit: int | None) -> None:
    import io

    rows = _hero_rows()
    if limit:
        rows = rows[:limit]
    logger.info(f"{len(rows)} hero rows without attribution")

    written = no_article = no_lead = no_local = mismatch = 0
    for i, row in enumerate(rows):
        local_path = HERO_DIR / row["site_id"].replace("-", "")[:8] / "hero.webp"
        if not local_path.exists():
            no_local += 1
            continue

        article = None
        if row["source_url"] and "wikipedia.org" in row["source_url"]:
            article = extract_title_from_url(row["source_url"])
        if not article:
            article = wikipedia_opensearch(row["name"])
            time.sleep(REQUEST_DELAY)
        if not article:
            no_article += 1
            continue

        try:
            lead = _lead_image_title(article)
            time.sleep(REQUEST_DELAY)
            if not lead:
                no_lead += 1
                continue

            found = fetch_batch([lead])
            time.sleep(REQUEST_DELAY)
            meta = found.get(lead)
            if not meta or not meta.get("original_url"):
                no_lead += 1
                continue

            local = Image.open(local_path)
            # Commons thumbnail at the local hero's width — same scale, so the
            # perceptual comparison sees the same crop.
            thumb_url = (
                meta["original_url"].replace("/commons/", "/commons/thumb/", 1)
                + f"/{local.width}px-{meta['original_url'].rsplit('/', 1)[-1]}"
            )
            thumb_resp = _download_client.get(thumb_url)
            time.sleep(REQUEST_DELAY)
            if thumb_resp.status_code != 200:
                no_lead += 1
                continue
            remote = Image.open(io.BytesIO(thumb_resp.content))

            distance = hamming(dhash(local), dhash(remote))
            if distance > DHASH_MAX_DISTANCE:
                mismatch += 1
                continue

            apply_batch({row["id"]: meta})
            written += 1
        except Exception as exc:
            logger.warning(f"hero {row['site_id'][:8]} failed ({exc}); left NULL")

        if i % 100 == 0:
            logger.info(
                f"  heroes {i}/{len(rows)}: written={written} mismatch={mismatch} "
                f"no_lead={no_lead} no_article={no_article}"
            )

    logger.info("=" * 60)
    logger.info(f"Hero attribution written: {written}")
    logger.info(
        f"Left NULL: mismatch={mismatch} (lead image changed since import), "
        f"no_lead={no_lead}, no_article={no_article}, no_local_file={no_local}"
    )
