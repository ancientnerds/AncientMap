"""The ONE definition of the site-name match key.

`unified_sites.name_normalized` and `unified_site_names.name_normalized` are
maintained by Postgres as ``left(lower(unaccent(name)), 500)`` (the startup
UPDATEs in pipeline/lyra/orchestrator.py — one per column, plus the
curated-source reconciliation that embeds this fragment itself). Any comparison
against those columns must compute its side of the key with the identical
expression, in Postgres, from the raw string — never with
pipeline.utils.text.normalize_name, which folds neither the Turkish dotless ı nor
ø and strips parenthesised suffixes the column keeps. Measured 2026-09-14: 124
of the 5,004 curated sites were unreachable from a Python-computed key.

Both site_matcher (single-name lookups) and the prospector's batched dedup
embed this fragment, so the expression exists exactly once in the codebase.
"""

KEY_SQL_TEMPLATE = "left(lower(unaccent({expr})), 500)"


def site_key_sql(expr: str) -> str:
    """SQL fragment computing the match key of `expr` (a column or bind param).

    >>> site_key_sql(":raw")
    'left(lower(unaccent(:raw)), 500)'
    """
    return KEY_SQL_TEMPLATE.format(expr=expr)
