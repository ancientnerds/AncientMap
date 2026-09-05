"""Snapshot the homepage hub lists: country pages + public research papers.

Writes ancient-nerds-map/src/data/hubs.snapshot.json, which the Vite build
bakes into index.html (vite.config.ts → landingHubs, src/landing/hubsHtml.ts).
The homepage is static, so this is the only way its crawlable links reach
the 98 /sites/{country} hubs and the /research/{slug} papers — in the
2026-09-05 GSC sample 45 % of the hubs and 11 of 25 papers had never been
crawled because nothing but the sitemap pointed at them.

A snapshot, not a --verify'd generator: the data comes from the DB, so CI
cannot recompute it (unlike pipeline/generate_shared_data.py). Re-run after
publishing papers or when a new country gains curated sites, then commit:

    python scripts/export_hubs.py            # against DATABASE_URL
    docker exec ancient_nerds_api python scripts/export_hubs.py   # on the VPS

Country paths and the public-paper filter come from the same helpers the
sitemap and the SSR pages use, so nothing can be listed here and 404 there.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.sites_html_renderer import country_path  # noqa: E402

SNAPSHOT_PATH = PROJECT_ROOT / "ancient-nerds-map" / "src" / "data" / "hubs.snapshot.json"


def build_hubs_payload(country_rows: list[Any], paper_rows: list[Any]) -> dict:
    """Rows → the JSON the frontend build consumes.

    country_rows: objects with .country and .sites (count of curated sites).
    paper_rows:   objects with .slug, .title, .question — newest first, as
                  the research listing orders them; a paper without a stored
                  title is shown under its question, like everywhere else
                  (paper_summary_kwargs).
    """
    countries = [
        {"country": row.country, "path": country_path(row.country), "sites": int(row.sites)}
        for row in sorted(country_rows, key=lambda r: r.country)
    ]
    papers = [
        {"slug": row.slug, "path": f"/research/{row.slug}", "title": row.title or row.question}
        for row in paper_rows
    ]
    return {
        "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "countries": countries,
        "papers": papers,
    }


def fetch_rows() -> tuple[list[Any], list[Any]]:
    """The two queries, identical in scope to sitemap-countries.xml and /research/."""
    # Imported here, not at module level: the builder above must stay usable
    # (and testable) without a database or the FastAPI stack.
    from sqlalchemy import text

    from api.routes.public_v1 import PUBLIC_PAPER_WHERE
    from pipeline.database import get_session

    with get_session() as session:
        countries = session.execute(
            text("""
                SELECT country, COUNT(*) AS sites
                FROM unified_sites
                WHERE source_id = 'ancient_nerds'
                  AND country IS NOT NULL AND country != ''
                GROUP BY country
                ORDER BY country
            """)
        ).fetchall()
        papers = session.execute(
            text(f"""
                SELECT r.slug, r.question, r.result_json::jsonb->>'title' AS title
                FROM research_requests r
                WHERE {PUBLIC_PAPER_WHERE}
                ORDER BY r.published_at DESC NULLS LAST
            """)
        ).fetchall()
    return list(countries), list(papers)


def write_snapshot(payload: dict, path: Path = SNAPSHOT_PATH) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    countries, papers = fetch_rows()
    payload = build_hubs_payload(countries, papers)
    write_snapshot(payload)
    print(
        f"{SNAPSHOT_PATH}: {len(payload['countries'])} countries, {len(payload['papers'])} papers"
    )


if __name__ == "__main__":
    main()
