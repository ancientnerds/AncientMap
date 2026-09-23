"""Migration 0023 keeps control characters out of unified_sites.source_url, and cannot run early.

Read from the file itself, statement by statement: the CHECK is the control class
`pipeline/lyra/prospector/wiki.py` refuses; the first transaction counts the offending rows with a
plain read and raises before it adds anything, so a run before the data fix (wave 4 of
`qid_repair.py`) commits nothing; the constraint is added NOT VALID only when the catalog lacks it
and validated in its own transaction; the selftest reads the catalog with `strpos` (LIKE would read
the pattern's backslashes as escapes and never match - measured 2026-09-23 on a temp table).
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline.lyra.prospector.wiki import CONTROL_RE

REPO = Path(__file__).resolve().parents[2]
M0023 = REPO / "migrations" / "0023_source_url_no_control_chars.sql"
NAME = "unified_sites_source_url_no_control_chars"


def _text() -> str:
    return M0023.read_text(encoding="utf-8").replace("\r\n", "\n")


def _code() -> str:
    """The statements without their comment lines."""
    return "\n".join(line for line in _text().splitlines() if not line.lstrip().startswith("--"))


def _transactions() -> tuple[str, str]:
    """The first transaction (BEGIN ... COMMIT) and everything after it."""
    code = _code()
    assert code.count("\nBEGIN;\n") == 1 and code.count("\nCOMMIT;\n") == 1
    start = code.index("\nBEGIN;\n")
    end = code.index("\nCOMMIT;\n")
    return code[start:end], code[end + len("\nCOMMIT;\n") :]


def test_the_file_is_the_only_0023() -> None:
    assert [p.name for p in (REPO / "migrations").glob("0023_*.sql")] == [M0023.name]


def test_the_check_is_the_control_class_the_wiki_parser_refuses() -> None:
    code = _code()
    classes = re.findall(r"source_url (?:~|!~) '(\[[^']*\])'", code)
    # the guard's count, the CHECK - and the selftest's strpos compares the same text
    assert classes == [CONTROL_RE.pattern, CONTROL_RE.pattern]
    assert f"CHECK (source_url !~ '{CONTROL_RE.pattern}')" in code
    assert f"strpos(v_def, 'source_url !~ ''{CONTROL_RE.pattern}''') = 0" in code
    # the class is exactly C0 and DEL: a space, a tab-free URL and a NULL pass
    python = re.compile(CONTROL_RE.pattern)
    assert [c for c in range(256) if python.fullmatch(chr(c))] == [*range(32), 127]


def test_the_first_transaction_refuses_before_it_adds_anything() -> None:
    first, _ = _transactions()
    guard = first.index(
        "SELECT count(*) INTO v_bad FROM unified_sites WHERE source_url ~ '[\\x00-\\x1f\\x7f]';"
    )
    raise_ = first.index("IF v_bad > 0 THEN\n        RAISE EXCEPTION")
    alter = first.index("ALTER TABLE unified_sites\n            ADD CONSTRAINT")
    assert guard < raise_ < alter
    assert "'0023: % unified_sites row(s) carry a control character in source_url" in first


def test_the_constraint_is_added_not_valid_and_only_when_the_catalog_lacks_it() -> None:
    first, _ = _transactions()
    assert (
        "    IF NOT EXISTS (\n"
        "        SELECT 1\n"
        "          FROM pg_constraint\n"
        "         WHERE conrelid = 'unified_sites'::regclass\n"
        f"           AND conname  = '{NAME}'\n"
        "    ) THEN\n"
        "        ALTER TABLE unified_sites\n"
        f"            ADD CONSTRAINT {NAME}\n"
        "            CHECK (source_url !~ '[\\x00-\\x1f\\x7f]')\n"
        "            NOT VALID;\n"
    ) in first


def test_the_validation_runs_in_its_own_transaction_then_the_catalog_is_asserted() -> None:
    first, rest = _transactions()
    assert "VALIDATE" not in first
    validate = rest.index(f"ALTER TABLE unified_sites VALIDATE CONSTRAINT {NAME};")
    selftest = rest.index("SELFTEST FAILED")
    assert validate < selftest
    assert "IF NOT v_valid THEN" in rest and "IF v_def IS NULL THEN" in rest
    assert " LIKE " not in _code()


def test_the_header_says_it_runs_only_after_the_data_fix() -> None:
    header = _text().split("\nBEGIN;\n")[0]
    assert "The deploy applies this file AFTER the orchestrator has applied the data fix" in header
    assert "output/remediation/qid_repair/wave4" in header
    assert "it fails with\n-- exactly the 20 rows" in header
