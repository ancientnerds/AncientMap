# SPDX-License-Identifier: AGPL-3.0-only
"""The boot-time FK policy must exempt every site-owned CASCADE table.

The API boot (api/boot_schema.py, run from api/main.py) rewrites every FK onto
unified_sites to ON DELETE SET NULL and drops NOT NULL on the column. A
site-owned table whose site_id is part of its PRIMARY KEY cannot have NOT NULL
dropped — on 2026-09-15 the deploy of site_external_ids (migration 0015)
crash-looped the API on `column "site_id" is in a primary key` until the table
was added to the exemption list. Any future site-owned table must be listed
here AND there.
"""

import inspect
import re
from pathlib import Path

from api import boot_schema
from pipeline import database

SITE_OWNED_CASCADE_TABLES = {
    "unified_site_names",
    "site_content_links",
    "wiki_images",
    "card_stats",
    "site_external_ids",
    "research_paper_sites",
}


def _exemption_tuple() -> set[str]:
    src = inspect.getsource(boot_schema)
    block = src[src.index("FK policy (2026-08-17)") :]
    m = re.search(r"NOT IN \(([^)]*)\)", block)
    assert m, "FK policy exemption tuple not found"
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


def test_every_site_owned_cascade_table_is_exempt():
    assert SITE_OWNED_CASCADE_TABLES <= _exemption_tuple()


def test_models_with_cascade_onto_unified_sites_match_the_list():
    """Catch a new CASCADE model that was not added to the exemption list."""
    cascading = set()
    for mapper in database.Base.registry.mappers:
        table = mapper.local_table
        for fk in table.foreign_keys:
            if fk.column.table.name == "unified_sites" and fk.ondelete == "CASCADE":
                cascading.add(table.name)
    assert cascading <= _exemption_tuple(), (
        f"unexempted CASCADE tables: {cascading - _exemption_tuple()}"
    )


def test_migrations_with_cascade_onto_unified_sites_match_the_list():
    """A table created by a migration alone has no model, so the test above cannot see
    it: research_paper_sites (migration 0031) crash-looped the API on 2026-10-20."""
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    cascading = set()
    for sql in migrations.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        text = sql.read_text(encoding="utf-8")
        for table, body in re.findall(
            r"CREATE TABLE(?: IF NOT EXISTS)?\s+([a-z_]+)\s*\((.*?)\);", text, re.S | re.I
        ):
            if re.search(r"REFERENCES\s+unified_sites\s*\([^)]*\)\s+ON DELETE CASCADE", body, re.I):
                cascading.add(table.lower())
    assert "research_paper_sites" in cascading
    assert cascading <= _exemption_tuple(), (
        f"unexempted CASCADE tables: {cascading - _exemption_tuple()}"
    )
