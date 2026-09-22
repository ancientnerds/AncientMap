"""Startup import of the deployed card descriptions.

`public/data/card_descriptions.json` is the authoritative copy of
`card_stats.card_description`. The chain that keeps it so is documented in
`docs/procedures/CARD_DESCRIPTIONS.md:93-95` and it is a carrier, not a cache:
the generator writes `output/card_descriptions.json`,
`scripts/import_card_descriptions.py` copies that into `public/data/`, the file
is committed and deployed, and this import is how a committed file reaches a row
that already exists in production. Measured 2026-09-20: all 4,996 entries of the
deployed file were byte-identical to their `card_stats` rows in production —
because this import had already propagated them.

So the upsert below OVERWRITES on purpose; a fill-only variant would break the
only path from an edited file to an existing row. What it may not do is discard
a value silently (plan `docs/procedures/SITES_DB_REMEDIATION_2026-09.md` §10.1):
a card text that exists only in the database is a card text the next container
start destroys, and the 2026-09 remediation is about to write card texts. Every
non-empty value this import replaces is therefore logged with its site id and
both values, so the loss is visible in the boot log instead of being noticed
weeks later in the card text.

Nothing here is card-text policy: where the text should come from is decided by
`FIELD_CONTRACT.md` (authoritative copy = the JSON file).
"""

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

CARD_DESCRIPTIONS_PATH = Path("public/data/card_descriptions.json")

# `card_stats.card_description` is VARCHAR(200); the file is allowed to carry
# longer drafts (api/main.py has truncated to 200 since the import was written,
# commit c37cc07).
CARD_DESCRIPTION_MAX_LENGTH = 200

_UPSERT_SQL = text("""
    INSERT INTO card_stats (site_id, card_description, antiquity, fortification,
        cultural_influence, mystery, legacy, total_power, rarity_score, rarity_tier, category_group)
    VALUES (:id, :desc, 0, 0, 0, 0, 0, 0, 0, 0, 'unknown')
    ON CONFLICT (site_id) DO UPDATE SET card_description = :desc
    WHERE card_stats.card_description IS DISTINCT FROM :desc
""")

# Descriptions may reference sites deleted since the JSON was generated — one
# stale id would FK-abort the whole import.
_STALE_IDS_SQL = text("SELECT unnest(CAST(:ids AS uuid[])) EXCEPT SELECT id FROM unified_sites")

_CURRENT_DESCRIPTIONS_SQL = text("""
    SELECT site_id::text, card_description FROM card_stats
    WHERE site_id::text = ANY(:ids)
""")


def load_card_descriptions(path: Path | None = None) -> dict[str, str]:
    """The deployed descriptions, `{site_id: text}`; `{}` if the file is absent."""
    path = path if path is not None else CARD_DESCRIPTIONS_PATH
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    descriptions = data.get("descriptions") or {}
    return {str(site_id): str(value) for site_id, value in descriptions.items()}


def import_card_descriptions(session: Any, descriptions: dict[str, str]) -> dict[str, Any]:
    """Upsert `descriptions` into `card_stats`, reporting every value discarded.

    Returns `imported` (rows the statement actually wrote), `checked`, `stale`
    (site ids not in `unified_sites`) and `discarded` — a list of
    `(site_id, replaced_value, new_value)` for every non-empty value that the
    deployed file overwrote. Each discarded value is also logged at WARNING.

    The caller owns the transaction.
    """
    if not descriptions:
        return {"imported": 0, "checked": 0, "stale": [], "discarded": []}

    stale_rows = session.execute(_STALE_IDS_SQL, {"ids": list(descriptions)}).fetchall()
    stale_ids = {str(row[0]) for row in stale_rows}
    if stale_ids:
        logger.warning(
            "[STARTUP] Skipping %s card descriptions for deleted sites: %s",
            len(stale_ids),
            sorted(stale_ids)[:5],
        )

    live = {sid: value for sid, value in descriptions.items() if sid not in stale_ids}
    stored: dict[str, str | None] = {}
    if live:
        for row in session.execute(_CURRENT_DESCRIPTIONS_SQL, {"ids": list(live)}).fetchall():
            stored[str(row[0])] = row[1]

    imported = 0
    discarded: list[tuple[str, str, str]] = []
    for site_id, raw in live.items():
        # Truncate before comparing: a file value that is long only because it
        # needs cutting is not a value this import discards.
        value = str(raw)[:CARD_DESCRIPTION_MAX_LENGTH]
        previous = stored.get(site_id)
        if previous and previous != value:
            discarded.append((site_id, previous, value))
            logger.warning(
                "[STARTUP] Card description overwritten: %s %r -> %r "
                "(public/data/card_descriptions.json wins — see FIELD_CONTRACT.md)",
                site_id,
                previous,
                value,
            )
        result = session.execute(_UPSERT_SQL, {"id": site_id, "desc": value})
        imported += result.rowcount

    return {
        "imported": imported,
        "checked": len(descriptions),
        "stale": sorted(stale_ids),
        "discarded": discarded,
    }
