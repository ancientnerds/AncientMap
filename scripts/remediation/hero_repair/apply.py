"""Turn the hero-repair plan into one journalled transaction, and check it against production.

The write path is the one the project mandates: `apply_remediation_change()` from
`migrations/0017_remediation_change_log.sql` (see `docs/procedures/FIELD_CONTRACT.md` §1). It
does the conditional UPDATE and the journal INSERT in a single statement, refuses to write
unless exactly one row matches the expected old value, and allows only the six remediation
tables. This module adds the two things a 5,438-row repair needs on top of it:

* **one transaction for the whole plan** - a half-applied hero move is worse than none, because
  the site is left serving whatever `ORDER BY is_hero DESC, is_lead DESC, sort_order` picks from
  two flagged rows;
* **a scope guard inside the transaction** - every planned image must live on a
  `source_id = 'ancient_nerds'` site. `wiki_images` also holds two rows of `list_inscriptions`
  (measured 2026-09-20), and a repair that is not scoped by site would be a defect.

Known blocker at the time of writing, fixed by migration 0018 before the write
---------------------------------------------------------------------------
`apply_remediation_change()` could not write a **boolean** column. Its generated statement was
``UPDATE %I SET %I = $1 WHERE %I::text = $2 AND %I IS NOT DISTINCT FROM $3`` with `$1`/`$3`
bound from TEXT parameters, and PostgreSQL has no `boolean = text` operator:

    ERROR:  operator does not exist: boolean = text
    LINE 1: ... SET is_hero = $1 WHERE id::text = $2 AND is_hero IS NOT DIS...
    CONTEXT:  PL/pgSQL function apply_remediation_change(...) line 24 at EXECUTE

Reproduced against production inside a rolled-back transaction on a non-existent pk
(id = -1), so no row could match even had the statement been planned: the failure happens while
the statement is planned, before any row is considered. The old self-test missed it because it
exercised a `country TEXT` column only.

`migrations/0018_remediation_change_log_boolean.sql` replaced the body with a catalog-derived
cast (`format_type` from `pg_attribute`), so both operands take the column's own type, and it
added a re-read that refuses a write whose stored value differs from the value given. This
module therefore calls the function for every row and writes the journal table nowhere itself;
`--check-primitive` reports whether the deployed body is the type-safe one, so the write cannot
silently fall back to something weaker.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _parent in (_HERE.parent.parent, _HERE.parent.parent.parent.parent):
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))

REPO = _HERE.parents[3]

#: The production transport is `prod_write.send` (ssh, then psql in the container). Until
#: 2026-09-23 this module carried its own copy without a timeout rule, so a psql that did not
#: answer surfaced as a bare `subprocess.TimeoutExpired`: a caller could read it as "nothing
#: happened" and retry a write whose COMMIT may already have landed.
from prod_write import SSH_HOST, OutcomeUnknown, send  # noqa: E402

from hero_repair.plan import (  # noqa: E402
    CONFIDENCE,
    CURATED_SOURCE,
    RUN_STAMP,
    TEST_ID,
    ChangeRecord,
    PlanError,
)

log = logging.getLogger("hero_repair.apply")

#: The exit code of a run whose write may or may not have landed (the other lanes use 5 too).
EXIT_UNKNOWN = 5

#: The rollback is its own run stamp, so `remediation_change_history` can tell a reversal from
#: the change it reverses.
ROLLBACK_RUN_STAMP = "2026-09-20_remediation-rollback"

DEFAULT_PLAN = REPO / "output/remediation/hero_repair/PLAN.jsonl"
DEFAULT_OUT = REPO / "output/remediation/hero_repair"

VERIFY_SQL = f"""\
-- Read-only. The same file before and after the apply, so the two runs are comparable.
\\pset footer off
SELECT 'curated sites' AS metric, count(*)::text AS value
  FROM unified_sites WHERE source_id = 'ancient_nerds'
UNION ALL
SELECT 'sites with at least one image', count(DISTINCT u.id)::text
  FROM unified_sites u JOIN wiki_images w ON w.site_id = u.id
 WHERE u.source_id = 'ancient_nerds'
UNION ALL
SELECT 'hero rows (curated)', count(*)::text
  FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id
 WHERE u.source_id = 'ancient_nerds' AND w.is_hero
UNION ALL
SELECT 'sites with exactly one hero', count(*)::text FROM (
  SELECT u.id FROM unified_sites u JOIN wiki_images w ON w.site_id = u.id
   WHERE u.source_id = 'ancient_nerds' GROUP BY u.id
  HAVING count(*) FILTER (WHERE w.is_hero) = 1) x
UNION ALL
SELECT 'sites with more than one hero', count(*)::text FROM (
  SELECT u.id FROM unified_sites u JOIN wiki_images w ON w.site_id = u.id
   WHERE u.source_id = 'ancient_nerds' GROUP BY u.id
  HAVING count(*) FILTER (WHERE w.is_hero) > 1) x
UNION ALL
SELECT 'heroes outside the curated source', count(*)::text
  FROM wiki_images w LEFT JOIN unified_sites u ON u.id = w.site_id
 WHERE w.is_hero AND (u.id IS NULL OR u.source_id <> 'ancient_nerds')
UNION ALL
-- the image the site actually serves: the same pick the SSR makes
SELECT 'sites whose served image is narrower than 1600 px', count(*)::text FROM (
  SELECT u.id, w.width FROM unified_sites u CROSS JOIN LATERAL (
    SELECT width FROM wiki_images
     WHERE site_id = u.id AND (is_excluded = false OR is_excluded IS NULL)
     ORDER BY is_hero DESC, is_lead DESC, sort_order LIMIT 1) w
   WHERE u.source_id = 'ancient_nerds' AND (w.width IS NULL OR w.width < 1600)) x
UNION ALL
SELECT 'sites whose served image is shorter than 900 px', count(*)::text FROM (
  SELECT u.id, w.height FROM unified_sites u CROSS JOIN LATERAL (
    SELECT height FROM wiki_images
     WHERE site_id = u.id AND (is_excluded = false OR is_excluded IS NULL)
     ORDER BY is_hero DESC, is_lead DESC, sort_order LIMIT 1) w
   WHERE u.source_id = 'ancient_nerds' AND (w.height IS NULL OR w.height < 900)) x
UNION ALL
SELECT 'journal rows for this run stamp', count(*)::text
  FROM remediation_change_log WHERE run_stamp = '{RUN_STAMP}'
UNION ALL
SELECT 'journal rows for this test id', count(*)::text
  FROM remediation_change_log WHERE test_id = '{TEST_ID}'
ORDER BY 1;
"""

PRIMITIVE_CHECK_SQL = """\
-- Is the deployed body the type-safe one from migrations/0018? Without 0018 the boolean
-- write fails at statement planning; with it, every operand is cast to the column's type.
SELECT p.proname || '(' || coalesce(array_to_string(p.proargtypes::regtype[], ', '), '') || ')'
       AS signature
  FROM pg_proc p WHERE p.proname = 'apply_remediation_change';
SELECT pg_get_functiondef(p.oid) LIKE '%$1::%s WHERE%' AS casts_value_to_column_type,
       pg_get_functiondef(p.oid) LIKE '%IS NOT DISTINCT FROM $3::%s%' AS casts_old_value,
       pg_get_functiondef(p.oid) LIKE '%stored a different value%' AS rereads_stored_value
  FROM pg_proc p WHERE p.proname = 'apply_remediation_change';
"""


# ------------------------------------------------------------------------------- rendering
#: What may stand inside a single-quoted RAISE message: no quote, no percent sign, no backslash.
#: The image lanes' chunk writer checks its lane labels against this same pattern.
LABEL_RE = re.compile(r"[A-Za-z0-9 _./-]+")


def one_hero_invariant_sql(
    plan_table: str = "_hero_plan", *, label: str = "hero repair", at_most: bool = False
) -> list[str]:
    """The hero-count invariant over every site a plan touches, as lines of a DO block.

    The default is the hero repair's own check, byte for byte: every touched site ends with
    *exactly* one `is_hero` row. `at_most=True` is the image lanes' form
    (`gallery_audit/chunk_writer.py`): at most one, because a lane that excludes a site's only
    image may leave it with none, and a second hero is the defect either way - the served pick
    `ORDER BY is_hero DESC, is_lead DESC, sort_order` then chooses between two flagged rows.
    The block expects an `integer` variable `bad` in the enclosing DECLARE.
    """
    if not plan_table.isidentifier() or not plan_table.startswith("_"):
        raise PlanError(f"{plan_table!r} is not a temp plan table name")
    if not LABEL_RE.fullmatch(label):
        raise PlanError(f"{label!r} cannot stand inside a quoted RAISE message")
    if at_most:
        heroes, rows, wrong, says = "at most one hero", "several rows", "> 1", "end with more than one hero"
    else:
        heroes, rows, wrong, says = "one hero", "two rows", "<> 1", "do not end with exactly one hero"
    return [
        f"    -- the invariant the repair must leave behind: {heroes} per touched site",
        f"    -- (DISTINCT: {plan_table} holds {rows} per site, and a plain join would count each",
        "    --  hero row twice - the check would then fail on a correct repair)",
        "    SELECT count(*) INTO bad FROM (",
        f"        SELECT s.site_id FROM (SELECT DISTINCT site_id FROM {plan_table}) s",
        "          JOIN wiki_images w ON w.site_id = s.site_id",
        f"         GROUP BY s.site_id HAVING count(*) FILTER (WHERE w.is_hero) {wrong}) x;",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{label}: % touched site(s) {says}', bad;",
        "    END IF;",
    ]


def _literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def rehearse(sql: str, *, run_stamp: str = RUN_STAMP) -> str:
    """The same file with `COMMIT` swapped for `ROLLBACK`, plus reads of what must be unchanged.

    The point is to run the *identical* statement - the same guards, the same 5,438 calls -
    against production without keeping any of it, so a broken guard is found before it is
    committing rather than after.
    """
    head, sep, _ = sql.partition("\nCOMMIT;\n")
    if not sep:
        raise PlanError("the emitted statement has no COMMIT - refusing to rehearse it")
    return head + "\nROLLBACK;\n" + (
        "-- after ROLLBACK: nothing may have changed\n"
        "SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value\n"
        "  FROM remediation_change_log WHERE run_stamp = "
        f"{_literal(run_stamp)}\n"
        "UNION ALL\n"
        "SELECT 'curated hero rows', count(*)::text\n"
        "  FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id\n"
        f" WHERE u.source_id = {_literal(CURATED_SOURCE)} AND w.is_hero\n"
        "UNION ALL\n"
        "SELECT 'curated sites with more than one hero', count(*)::text FROM (\n"
        "    SELECT u.id FROM unified_sites u JOIN wiki_images w ON w.site_id = u.id\n"
        f"   WHERE u.source_id = {_literal(CURATED_SOURCE)} GROUP BY u.id\n"
        "  HAVING count(*) FILTER (WHERE w.is_hero) > 1) x\n"
        "UNION ALL\n"
        "SELECT 'temp table _hero_plan left behind', count(*)::text\n"
        "  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace\n"
        " WHERE n.nspname = 'public' AND c.relname = '_hero_plan';\n"
    )


def render_transaction(
    records: Sequence[ChangeRecord],
    *,
    run_stamp: str = RUN_STAMP,
    site_ids: Iterable[str],
    source: str = CURATED_SOURCE,
) -> str:
    """One transaction that applies `records` and journals each row, or applies nothing.

    Every row goes through `apply_remediation_change()`, which does the conditional UPDATE and
    the journal INSERT in one statement and raises unless exactly one row matched the expected
    old value. `ON_ERROR_STOP` plus the explicit `COMMIT` at the end means a refusal anywhere
    rolls the whole plan back; `--rehearse` runs the identical file with `COMMIT` replaced by
    `ROLLBACK` to show that without changing anything.
    """
    records = list(records)
    if not records:
        raise PlanError("refusing to render an empty transaction")
    sites = sorted({str(s) for s in site_ids})
    out: list[str] = []
    add = out.append
    add("-- Generated by scripts/remediation/hero_repair/apply.py - do not edit by hand.")
    add(f"-- {len(records)} row(s) over {len(sites)} site(s); scope source_id = '{source}'.")
    add("-- Every UPDATE is conditioned on the old value; every change is journalled in the same")
    add("-- transaction, so the audit trail cannot disagree with the data.")
    add("\\set ON_ERROR_STOP on")
    add("BEGIN;")
    add("")
    add("CREATE TEMP TABLE _hero_plan (")
    add("    image_id    BIGINT PRIMARY KEY,")
    add("    site_id     UUID NOT NULL,")
    add("    old_value   BOOLEAN NOT NULL,")
    add("    new_value   BOOLEAN NOT NULL,")
    add("    change_key  TEXT NOT NULL,")
    add("    reason      TEXT NOT NULL,")
    add("    evidence    JSONB NOT NULL")
    add(") ON COMMIT DROP;")
    add("")
    add("INSERT INTO _hero_plan (image_id, site_id, old_value, new_value, change_key, reason, evidence) VALUES")
    rows = []
    for r in sorted(records, key=lambda r: (r.site_id, r.image_id)):
        change_key = f"hero-repair:{r.site_id}"
        rows.append(
            "    ("
            f"{r.image_id}, {_literal(r.site_id)}, {str(r.old_is_hero).lower()}, "
            f"{str(r.new_is_hero).lower()}, {_literal(change_key)}, {_literal(r.reason)}, "
            f"{_literal(json.dumps(r.evidence, ensure_ascii=False))}::jsonb)"
        )
    add(",\n".join(rows) + ";")
    add("")
    add("DO $$")
    add("DECLARE")
    add("    bad      INTEGER;")
    add("    moved    INTEGER := 0;")
    add("    expected INTEGER;")
    add("    r        RECORD;")
    add("BEGIN")
    add("    SELECT count(*) INTO expected FROM _hero_plan;")
    add("")

    # --- scope guards, before a single row is touched
    add("    -- scope guard 1: every planned site is a curated site")
    add("    SELECT count(*) INTO bad")
    add("      FROM _hero_plan p LEFT JOIN unified_sites u ON u.id = p.site_id")
    add(f"     WHERE u.id IS NULL OR u.source_id <> {_literal(source)};")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION 'hero repair: % planned site(s) are not {source}', bad;")
    add("    END IF;")
    add("")
    add("    -- scope guard 2: every planned image lives on the site the plan names")
    add("    SELECT count(*) INTO bad")
    add("      FROM _hero_plan p JOIN wiki_images w ON w.id = p.image_id")
    add("     WHERE w.site_id IS DISTINCT FROM p.site_id;")
    add("    IF bad > 0 THEN")
    add("        RAISE EXCEPTION 'hero repair: % planned image(s) do not belong to their site', bad;")
    add("    END IF;")
    add("")
    add("    -- scope guard 3: the plan is internally consistent - one promotion and one")
    add("    -- demotion per touched site, and no row twice")
    add("    SELECT count(*) INTO bad FROM (")
    add("        SELECT p.site_id FROM _hero_plan p GROUP BY p.site_id")
    add("         HAVING count(*) FILTER (WHERE p.new_value) <> 1")
    add("             OR count(*) FILTER (WHERE NOT p.new_value) <> 1) x;")
    add("    IF bad > 0 THEN")
    add("        RAISE EXCEPTION 'hero repair: % site(s) without exactly one promotion and one "
        "demotion', bad;")
    add("    END IF;")
    add("")
    add("    -- every row through the journal function, so the UPDATE and its journal row")
    add("    -- commit together or neither does; it raises if the old value does not match")
    add("    FOR r IN SELECT * FROM _hero_plan ORDER BY site_id, new_value, image_id LOOP")
    add("        moved := moved + apply_remediation_change(")
    add("            'wiki_images', 'is_hero', 'id', r.image_id::text, ")
    add("            r.old_value::text, r.new_value::text,")
    add(f"            {_literal(TEST_ID)}, {_literal(run_stamp)}, r.change_key, "
        f"{_literal(CONFIDENCE)}, r.evidence, r.site_id);")
    add("    END LOOP;")
    add("")
    add("    IF moved <> expected THEN")
    add("        RAISE EXCEPTION 'hero repair: % row(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    out.extend(one_hero_invariant_sql())
    add("")
    add("    RAISE NOTICE 'hero repair: % row(s) changed and journalled over % site(s)',")
    add("        moved, (SELECT count(DISTINCT site_id) FROM _hero_plan);")
    add("END $$;")
    add("")
    add("COMMIT;")
    add("")
    add("-- Post-commit read: the numbers the report quotes, from the database, not from the plan.")
    add("SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value")
    add(f"  FROM remediation_change_log WHERE run_stamp = {_literal(run_stamp)}")
    add("UNION ALL")
    add("SELECT 'curated hero rows', count(*)::text")
    add("  FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id")
    add(f" WHERE u.source_id = {_literal(source)} AND w.is_hero")
    add("UNION ALL")
    add("SELECT 'curated sites with more than one hero', count(*)::text FROM (")
    add("    SELECT u.id FROM unified_sites u JOIN wiki_images w ON w.site_id = u.id")
    add(f"   WHERE u.source_id = {_literal(source)} GROUP BY u.id")
    add("  HAVING count(*) FILTER (WHERE w.is_hero) > 1) x;")
    add("")
    return "\n".join(out)


# ------------------------------------------------------------------------------- transport
def run_psql(sql: str, *, host: str = SSH_HOST, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    """Send `sql` to production through `prod_write.send`.

    A timeout raises `OutcomeUnknown` - the COMMIT may or may not have landed, and only the
    journal can say which; a non-zero exit raises `PlanError`.
    """
    proc = send(sql, host=host, timeout=timeout)
    if proc.returncode != 0:
        raise PlanError(
            f"psql exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}".strip()
        )
    return proc


# ---------------------------------------------------------------------------------- CLI
def load_records(path: Path) -> list[ChangeRecord]:
    if not path.exists():
        raise PlanError(f"{path} is missing - build the plan first (plan.py --write)")
    records: list[ChangeRecord] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            records.append(
                ChangeRecord(
                    image_id=int(payload["image_id"]),
                    site_id=str(payload["site_id"]),
                    site_name=str(payload["site_name"]),
                    role=str(payload["role"]),
                    old_is_hero=bool(payload["old_is_hero"]),
                    new_is_hero=bool(payload["new_is_hero"]),
                    condition=str(payload["condition"]),
                    reason=str(payload["reason"]),
                    evidence=list(payload.get("evidence") or []),
                )
            )
    if not records:
        raise PlanError(f"{path} holds no records")
    return records


def emit(records: Sequence[ChangeRecord], out: Path, *, dry_run_sql: Path) -> int:
    sql = render_transaction(
        records,
        run_stamp=RUN_STAMP,
        site_ids={r.site_id for r in records},
    )
    dry_run_sql.parent.mkdir(parents=True, exist_ok=True)
    dry_run_sql.write_text(sql, encoding="utf-8", newline="\n")
    log.info("wrote %s (%d records)", dry_run_sql, len(records))
    out.mkdir(parents=True, exist_ok=True)
    return len(records)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply the hero-repair plan to production")
    ap.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--emit", action="store_true", help="write APPLY.sql only (no database)")
    ap.add_argument("--rehearse", action="store_true",
                    help="run APPLY.sql with COMMIT replaced by ROLLBACK, then report")
    ap.add_argument("--apply", action="store_true", help="send APPLY.sql to production")
    ap.add_argument("--verify", action="store_true", help="run the read-only verification")
    ap.add_argument("--check-primitive", action="store_true",
                    help="report whether apply_remediation_change is the type-safe body")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        return run(args, ap)
    except OutcomeUnknown as exc:
        print(
            f"OUTCOME UNKNOWN: {exc} Before any retry run: SELECT count(*) FROM "
            f"remediation_change_log WHERE run_stamp = {_literal(RUN_STAMP)}; - the write "
            "landed only if it reads the plan's row count, and nothing was written if it reads 0",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN


def run(args: argparse.Namespace, ap: argparse.ArgumentParser) -> int:
    if args.check_primitive:
        print(run_psql(PRIMITIVE_CHECK_SQL).stdout)
        return 0
    if args.verify:
        print(run_psql(VERIFY_SQL).stdout)
        return 0
    if args.emit or args.apply or args.rehearse:
        records = load_records(args.plan)
        emit(records, args.out, dry_run_sql=args.out / "APPLY.sql")
    if args.rehearse:
        script = rehearse((args.out / "APPLY.sql").read_text(encoding="utf-8"))
        path = args.out / "REHEARSAL.sql"
        path.write_text(script, encoding="utf-8", newline="\n")
        log.info("wrote %s (COMMIT -> ROLLBACK)", path)
        proc = run_psql(script)
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
    if args.apply:
        sql = (args.out / "APPLY.sql").read_text(encoding="utf-8")
        proc = run_psql(sql)
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
    if not any((args.emit, args.apply, args.verify, args.check_primitive, args.rehearse)):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
