"""Which licences ask for a credit: the one rule of the image lanes (owner decision D18, 2026-10-08).

D18 says "author + licence URL suffice, no author_url needed" and orchestrator decision X4 reads it
for the file the licence asks nothing of: 5,952 curated rows are "Public domain", none carries a
licence URL and 350 no author, so "author and licence URL for every file" would refuse them all.
Two lanes ask the same question and must not answer it twice: the fetch manifest
(`import_hero/fetch.py`: which columns an entry must carry) and the attribution backfill
(`gallery_audit/attribution.py`: which rows are in scope for an author).

`credit_columns` is the rule; `needs_attribution_sql` is the same rule as a SQL predicate over a
`license` column, built from the same constants so the two cannot drift.
"""

from __future__ import annotations

#: Licence names that ask for no credit at all: a CC0 dedication, Commons' "PD", "No restrictions"
#: and "Copyrighted free use". Compared case-folded.
FREE_LICENSES = frozenset({"cc0", "pd", "no restrictions", "copyrighted free use"})
#: Prefixes of the free names Commons spells in more than one way (`Public domain`, `PD-old-100`,
#: `CC0 1.0`).
FREE_LICENSE_PREFIXES = ("public domain", "pd-", "cc0 ")
#: Commons' "Attribution" names a licence that asks for the author but has no licence page: none of
#: its 135 curated rows carries a licence URL.
AUTHOR_ONLY_LICENSES = frozenset({"attribution"})


def is_free(license_name: str) -> bool:
    """Whether the licence asks for no credit (`FREE_LICENSES`, `FREE_LICENSE_PREFIXES`)."""
    name = license_name.strip().casefold()
    return name in FREE_LICENSES or name.startswith(FREE_LICENSE_PREFIXES)


def credit_columns(license_name: str) -> tuple[str, ...]:
    """The credit columns a licence demands of the row that shows its file.

    `author_url` is never one of them (D18: it is a link to the author's page, which a file may not
    have). A free licence demands neither the author nor the licence URL; Commons' "Attribution"
    demands the author; every other licence - CC BY*, CC BY-SA*, GFDL, OGL, FAL, KOGL and the rest -
    demands both, because its terms are the thing a reader must be able to follow. A name this
    function does not know is therefore strict, never free."""
    if is_free(license_name):
        return ()
    if license_name.strip().casefold() in AUTHOR_ONLY_LICENSES:
        return ("author",)
    return ("author", "license_url")


def needs_attribution_sql(column: str = "license") -> str:
    """The SQL predicate of a row whose licence demands an author (`credit_columns` holds
    "author"): a licence name that is present and not free."""
    exact = ", ".join(f"'{name}'" for name in sorted(FREE_LICENSES))
    likes = " OR ".join(f"lower({column}) LIKE '{prefix}%'" for prefix in FREE_LICENSE_PREFIXES)
    return (
        f"({column} IS NOT NULL AND {column} <> '' "
        f"AND lower({column}) NOT IN ({exact}) AND NOT ({likes}))"
    )
