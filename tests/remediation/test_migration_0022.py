"""Migration 0022 changes exactly the key lookup of apply_remediation_change, and nothing else.

0018 found the row with `WHERE %I::text = $2`, which casts the key column and makes the primary-key
index unusable: every call scanned the whole table twice (EXPLAIN on production, 2026-09-23:
cost 232,500 against 8.45 through the index). 0022 is built from 0018's function text by four
edits. These tests read both files and prove that: undoing the four edits on 0022's body gives
0018's body back byte for byte, so no guard of 0018 can have been lost on the way.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
M0018 = REPO / "migrations" / "0018_remediation_change_log_boolean.sql"
M0022 = REPO / "migrations" / "0022_remediation_change_by_key.sql"


def _function(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("CREATE OR REPLACE FUNCTION apply_remediation_change(")
    return text[start : text.index("$fn$;", start) + len("$fn$;")]


def test_both_lookups_compare_the_key_in_its_own_type() -> None:
    body = _function(M0022)
    assert "WHERE %I::text = $2" not in body
    assert body.count("WHERE %I = $2::%s") == 2
    # the key type comes from the catalog, like the value column's type
    assert "INTO v_pk_type" in body and "a.attname  = p_pk_col" in body
    assert "has no key column" in body


def test_undoing_the_four_edits_gives_0018_back_byte_for_byte() -> None:
    body = _function(M0022)
    undo = [
        (
            "    -- The key column's own type (0022): the key is compared in it, so the primary-key\n"
            "    -- index is used. `%I::text = $2` cast the COLUMN and scanned the whole table.\n"
            "    v_pk_type TEXT;\n",
            "",
        ),
        (
            "    SELECT format_type(a.atttypid, NULL)\n"
            "      INTO v_pk_type\n"
            "      FROM pg_attribute a\n"
            "     WHERE a.attrelid = p_table::regclass\n"
            "       AND a.attname  = p_pk_col\n"
            "       AND a.attnum   > 0\n"
            "       AND NOT a.attisdropped;\n"
            "    IF v_pk_type IS NULL THEN\n"
            "        RAISE EXCEPTION\n"
            "            'apply_remediation_change: table % has no key column % - refusing to build a '\n"
            "            'statement against a key that does not exist', p_table, p_pk_col;\n"
            "    END IF;\n",
            "",
        ),
        (
            "WHERE %I = $2::%s AND %I IS NOT DISTINCT FROM $3::%s',\n"
            "        p_table, p_column, v_type, p_pk_col, v_pk_type, p_column, v_type\n",
            "WHERE %I::text = $2 AND %I IS NOT DISTINCT FROM $3::%s',\n"
            "        p_table, p_column, v_type, p_pk_col, p_column, v_type\n",
        ),
        (
            "FROM %I WHERE %I = $2::%s',\n        p_column, v_base_type, p_table, p_pk_col, v_pk_type\n",
            "FROM %I WHERE %I::text = $2',\n        p_column, v_base_type, p_table, p_pk_col\n",
        ),
        (
            "    -- The conditional WHERE, now type-safe. Since 0022 the key is compared in the key\n"
            "    -- column's own type (`%I = $2::<key type>`), so the primary-key index is used.",
            "    -- The conditional WHERE, now type-safe. `%I::text = $2` compares the primary key as\n"
            "    -- text, which works for every key type.",
        ),
    ]
    for new, old in undo:
        assert body.count(new) == 1, new[:60]
        body = body.replace(new, old)
    assert body == _function(M0018)


def test_the_migration_is_one_transaction_and_keeps_the_signature() -> None:
    text = M0022.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.count("\nBEGIN;\n") == 1 and text.rstrip().endswith("COMMIT;")
    signature = _function(M0022).split(") RETURNS INTEGER", 1)[0]
    assert signature == _function(M0018).split(") RETURNS INTEGER", 1)[0]
