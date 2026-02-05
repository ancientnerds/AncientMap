"""
Enrich unified_site_names with alternate names from multiple sources.

Sources of alternate names:
1. Wikidata: labels + aliases in all languages via wbgetentities API
2. Pleiades: raw_data.names (comma-separated ancient/modern names)
3. GeoNames: raw_data.alternatenames (comma-separated)
4. DARE: raw_data.ancient_name / raw_data.name (ancient vs modern)

Usage:
    # Fetch Wikidata labels and save to file:
    python -m pipeline.enrich_site_names --fetch-wikidata

    # Load saved labels + extract from raw_data, insert into DB:
    python -m pipeline.enrich_site_names --load

    # Both in one go:
    python -m pipeline.enrich_site_names --fetch-wikidata --load
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import text

from pipeline.database import get_session
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)

LABELS_FILE = Path("pipeline/data/wikidata_labels.json")


def fetch_wikidata_labels() -> Path:
    """Fetch labels/aliases for all Wikidata unified_sites and save to JSON."""
    from pipeline.ingesters.wikidata import WikidataIngester

    logger.info("Fetching QIDs from unified_sites where source_id='wikidata'...")

    with get_session() as session:
        rows = session.execute(text(
            "SELECT id, source_record_id FROM unified_sites WHERE source_id = 'wikidata'"
        )).fetchall()

    if not rows:
        logger.warning("No Wikidata sites found in unified_sites")
        return LABELS_FILE

    qid_to_site_id = {row.source_record_id: str(row.id) for row in rows}
    qids = list(qid_to_site_id.keys())
    logger.info(f"Found {len(qids):,} Wikidata QIDs to fetch labels for")

    ingester = WikidataIngester.__new__(WikidataIngester)
    ingester.REQUEST_DELAY = 2.0
    labels = ingester.fetch_labels(qids, batch_size=50)

    # Save with site_id mapping
    output = {}
    for qid, data in labels.items():
        site_id = qid_to_site_id.get(qid)
        if site_id:
            output[site_id] = {
                "qid": qid,
                "labels": data["labels"],
                "aliases": data["aliases"],
            }

    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LABELS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    logger.info(f"Saved labels for {len(output):,} sites to {LABELS_FILE}")
    return LABELS_FILE


def _insert_name(session, site_id: str, name: str, lang: str | None, name_type: str) -> bool:
    """Insert a single name into unified_site_names. Returns True if inserted."""
    normalized = normalize_name(name)
    if not normalized or len(normalized) < 2:
        return False

    session.execute(
        text("""
            INSERT INTO unified_site_names (site_id, name, name_normalized, language_code, name_type)
            VALUES (:site_id, :name, :name_normalized, :lang, :name_type)
            ON CONFLICT ON CONSTRAINT uq_usn DO NOTHING
        """),
        {
            "site_id": site_id,
            "name": name.strip()[:500],
            "name_normalized": normalized[:500],
            "lang": lang[:10] if lang else None,
            "name_type": name_type[:50],
        },
    )
    return True


def load_wikidata_labels(labels_path: Path = LABELS_FILE) -> int:
    """Load Wikidata labels from JSON file into unified_site_names."""
    if not labels_path.exists():
        logger.warning(f"Labels file not found: {labels_path}. Run with --fetch-wikidata first.")
        return 0

    with open(labels_path, encoding="utf-8") as f:
        data = json.load(f)

    logger.info(f"Loading labels for {len(data):,} Wikidata sites...")
    inserted = 0

    with get_session() as session:
        for site_id, info in data.items():
            # Insert all labels (one per language)
            for lang, label in info.get("labels", {}).items():
                if _insert_name(session, site_id, label, lang, "label"):
                    inserted += 1

            # Insert all aliases
            for lang, alias_list in info.get("aliases", {}).items():
                for alias in alias_list:
                    if _insert_name(session, site_id, alias, lang, "alias"):
                        inserted += 1

        session.commit()

    logger.info(f"Inserted {inserted:,} Wikidata name variants")
    return inserted


def extract_pleiades_names() -> int:
    """Extract alternate names from Pleiades raw_data.names field."""
    logger.info("Extracting Pleiades alternate names from raw_data...")
    inserted = 0

    with get_session() as session:
        rows = session.execute(text(
            "SELECT id, name, raw_data FROM unified_sites "
            "WHERE source_id = 'pleiades' AND raw_data IS NOT NULL"
        )).fetchall()

        for row in rows:
            raw = row.raw_data or {}
            names_str = raw.get("names", "")
            if not names_str:
                continue

            primary_normalized = normalize_name(row.name)
            for name_part in names_str.split(","):
                name_part = name_part.strip()
                if not name_part:
                    continue
                normalized = normalize_name(name_part)
                if normalized == primary_normalized:
                    continue
                if _insert_name(session, str(row.id), name_part, None, "pleiades_name"):
                    inserted += 1

        session.commit()

    logger.info(f"Inserted {inserted:,} Pleiades name variants")
    return inserted


def extract_geonames_names() -> int:
    """Extract alternate names from GeoNames raw_data.alternatenames field."""
    logger.info("Extracting GeoNames alternate names from raw_data...")
    inserted = 0

    with get_session() as session:
        rows = session.execute(text(
            "SELECT id, name, raw_data FROM unified_sites "
            "WHERE source_id = 'geonames' AND raw_data IS NOT NULL"
        )).fetchall()

        for row in rows:
            raw = row.raw_data or {}
            alt_str = raw.get("alternatenames", "")
            if not alt_str:
                continue

            primary_normalized = normalize_name(row.name)
            for name_part in alt_str.split(","):
                name_part = name_part.strip()
                if not name_part:
                    continue
                normalized = normalize_name(name_part)
                if normalized == primary_normalized:
                    continue
                if _insert_name(session, str(row.id), name_part, None, "geonames_alt"):
                    inserted += 1

        session.commit()

    logger.info(f"Inserted {inserted:,} GeoNames name variants")
    return inserted


def extract_dare_names() -> int:
    """Extract alternate names from DARE raw_data (ancient_name + modern name)."""
    logger.info("Extracting DARE alternate names from raw_data...")
    inserted = 0

    with get_session() as session:
        rows = session.execute(text(
            "SELECT id, name, raw_data FROM unified_sites "
            "WHERE source_id = 'dare' AND raw_data IS NOT NULL"
        )).fetchall()

        for row in rows:
            raw = row.raw_data or {}
            primary_normalized = normalize_name(row.name)

            # DARE stores both ancient_name and name (modern)
            for field in ("ancient_name", "name"):
                alt = raw.get(field, "")
                if not alt:
                    continue
                normalized = normalize_name(alt)
                if normalized == primary_normalized:
                    continue
                if _insert_name(session, str(row.id), alt, None, f"dare_{field}"):
                    inserted += 1

        session.commit()

    logger.info(f"Inserted {inserted:,} DARE name variants")
    return inserted


def insert_primary_names() -> int:
    """Insert primary names from unified_sites into unified_site_names.

    This ensures every site has at least its primary name in the table,
    so the site matcher can use a single lookup path.
    """
    logger.info("Inserting primary names from unified_sites...")

    with get_session() as session:
        result = session.execute(text("""
            INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
            SELECT id, name, name_normalized, 'primary'
            FROM unified_sites
            WHERE name_normalized IS NOT NULL
            ON CONFLICT ON CONSTRAINT uq_usn DO NOTHING
        """))
        session.commit()
        count = result.rowcount

    logger.info(f"Inserted {count:,} primary names")
    return count


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(description="Enrich unified_site_names with alternate names")
    parser.add_argument("--fetch-wikidata", action="store_true", help="Fetch Wikidata labels via API")
    parser.add_argument("--load", action="store_true", help="Load all alt names into DB")
    args = parser.parse_args()

    if not args.fetch_wikidata and not args.load:
        parser.print_help()
        return

    if args.fetch_wikidata:
        fetch_wikidata_labels()

    if args.load:
        # Primary names first (so every site has at least one entry)
        insert_primary_names()

        # Wikidata labels (the biggest source of alt names)
        load_wikidata_labels()

        # Extract from raw_data for other sources
        extract_pleiades_names()
        extract_geonames_names()
        extract_dare_names()

        # Final count
        with get_session() as session:
            count = session.execute(text("SELECT count(*) FROM unified_site_names")).scalar()
            logger.info(f"Total unified_site_names: {count:,}")


if __name__ == "__main__":
    main()
