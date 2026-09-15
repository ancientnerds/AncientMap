# SPDX-License-Identifier: AGPL-3.0-only
"""The boot-time FK policy must exempt every site-owned CASCADE table.

api/main.py rewrites every FK onto unified_sites to ON DELETE SET NULL and
drops NOT NULL on the column. A site-owned table whose site_id is part of
its PRIMARY KEY cannot have NOT NULL dropped — on 2026-09-15 the deploy of
site_external_ids (migration 0015) crash-looped the API on
`column "site_id" is in a primary key` until the table was added to the
exemption list. Any future site-owned table must be listed here AND there.
"""

import inspect
import re

from api import main
from pipeline import database

SITE_OWNED_CASCADE_TABLES = {
    "unified_site_names",
    "site_content_links",
    "wiki_images",
    "card_stats",
    "site_external_ids",
}


def _exemption_tuple() -> set[str]:
    src = inspect.getsource(main)
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
