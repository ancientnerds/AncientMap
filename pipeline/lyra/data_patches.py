"""One-time data quality patches for Lyra-sourced sites.

All patches are idempotent (guarded by NULL / NOT EXISTS checks).
To add a new fix, add an entry to the relevant dict — no raw SQL needed.
"""

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Country corrections ──────────────────────────────────────────────
# {name_pattern (LIKE): correct_country}
# Only applied where country IS NULL, so safe to re-run.
COUNTRY_FIXES: dict[str, str] = {
    "%callanish%": "United Kingdom",
}

# ── Period backfills for well-known sites ─────────────────────────────
# {lowercase_name: (period_start, period_name)}
# Only applied where period_start IS NULL, so safe to re-run.
PERIOD_BACKFILLS: dict[str, tuple[int, str]] = {
    "göbekli tepe": (-9500, "< 4500 BC"),
    "giza plateau": (-2560, "3000 - 1500 BC"),
    "giza pyramids (egypt)": (-2560, "3000 - 1500 BC"),
    "sayburç": (-9000, "< 4500 BC"),
    "callanish": (-2900, "3000 - 1500 BC"),
    "chaco culture nhp- fajada butte": (850, "500 - 1000 AD"),
    "pnyx (athens)": (-500, "500 BC - 1 AD"),
    "tomb of kar (megarid)": (-2400, "3000 - 1500 BC"),
    "paracas": (-800, "1500 - 500 BC"),
    "slack farm": (800, "500 - 1000 AD"),
    "hanabila mosque": (1200, "1000 - 1500 AD"),
}

# ── Site name aliases ─────────────────────────────────────────────────
# {base_site_pattern (LIKE): [(display_name, normalized_name), ...]}
# Only inserted when NOT EXISTS, so safe to re-run.
SITE_ALIASES: dict[str, list[tuple[str, str]]] = {
    "%great pyramid%giza%": [
        ("Great Pyramid of Khufu", "great pyramid of khufu"),
        ("Pyramid of Khufu", "pyramid of khufu"),
    ],
}


def fix_countries(conn) -> int:
    """Fix NULL countries for known sites."""
    total = 0
    for pattern, country in COUNTRY_FIXES.items():
        r = conn.execute(
            text("""
                UPDATE unified_sites SET country = :country
                WHERE lower(name) LIKE :pattern
                  AND source_id = 'lyra' AND country IS NULL
            """),
            {"pattern": pattern, "country": country},
        )
        total += r.rowcount
    return total


def backfill_periods(conn) -> int:
    """Backfill period_start + period_name for well-known sites missing them."""
    total = 0
    for name, (period_start, period_name) in PERIOD_BACKFILLS.items():
        r = conn.execute(
            text("""
                UPDATE unified_sites
                SET period_start = :ps, period_name = :pn
                WHERE source_id = 'lyra' AND period_start IS NULL
                  AND lower(name) = :name
            """),
            {"ps": period_start, "pn": period_name, "name": name},
        )
        total += r.rowcount
    return total


def add_aliases(conn) -> int:
    """Insert missing aliases into unified_site_names."""
    total = 0
    for base_pattern, aliases in SITE_ALIASES.items():
        for display_name, normalized in aliases:
            r = conn.execute(
                text("""
                    INSERT INTO unified_site_names
                        (site_id, name, name_normalized, name_type)
                    SELECT id, :name, :norm, 'alias'
                    FROM unified_sites
                    WHERE lower(name) LIKE :pattern
                      AND NOT EXISTS (
                          SELECT 1 FROM unified_site_names
                          WHERE name_normalized = :norm
                      )
                    LIMIT 1
                """),
                {"name": display_name, "norm": normalized, "pattern": base_pattern},
            )
            total += r.rowcount
    return total


def run_data_patches(conn) -> None:
    """Run all data quality patches. Called from orchestrator startup."""
    n = fix_countries(conn)
    if n:
        logger.info(f"Data patches: fixed {n} site countries")

    n = backfill_periods(conn)
    if n:
        logger.info(f"Data patches: backfilled {n} site periods")

    n = add_aliases(conn)
    if n:
        logger.info(f"Data patches: added {n} site aliases")
