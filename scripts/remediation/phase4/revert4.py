"""Revert Phase-4/5 writes from the journal itself: the reversal needs no local file.

Design entry [6], production_write, ROLLBACK (the graft from "minimal-change"). Work item WB-D2.
Every chunk also has its own `ROLLBACK.sql` next to its `APPLY.sql`; this module is the reversal
that still works when every local file is lost, because it reads what to undo from
`remediation_change_log`: the rows of the matched run stamps, newest first, each written back from
its `new_value` to its `old_value` through `apply_remediation_change`, whose conditional `WHERE`
requires the row still to hold the value the write left. A row that moved since - a later write, a
boot import, a hand edit - makes the function raise and the whole reversal commits nothing.

It is the design's answer to a red CI in the P5 sitting ("run revert4.py over the phase5 stamps and
git revert the JSON commit") and to a systematic cause found by the mass-run audits.

What it refuses, before anything runs: a pattern outside the three phase-4/5 families (`phase4:`,
`phase4l:`, `phase5:` - never phase 3, never the mechanical lanes) and a pattern naming reversals;
inside the transaction, a pattern that matches no write, a pattern whose every matched write is
reverted already, and a row outside the three written columns or outside the curated sites.
After the loop it asserts that every reverted field holds the old value of its oldest reverted link
and that each reversal is journalled with the values swapped. Reversals are journalled under the
write's stamp and key plus `-rollback` (`journal_chain.ROLLBACK_SUFFIX`), so every acceptance
already reads them as reversals.

**A write that already has its own reversal is skipped, not refused** (review of 2026-09-23). A
change key names a transition, not a write: a batch written again after a revert (write round 2)
journals the same keys as round 1 under its own stamp, so a pattern such as `phase5:%` then matches
both rounds. Refusing the whole pattern - the first version did, on the key alone - left the live
round revertable only by its exact stamp, and the red-CI answer of the P5 sitting would have failed
the second time it was needed. Reverting the reverted round again is no option either: it needs the
field to hold its written value, which round 2 may have put back, and it would undo round 2's write
under round 1's stamp. So the set is fixed first, inside the transaction, as the matched writes
without their own reversal (the key **and** the stamp plus `-rollback`), and every guard, the loop
and both invariants run over exactly that set.

    python scripts/remediation/phase4/revert4.py --stamp-like 'phase5:%'             # render
    python scripts/remediation/phase4/revert4.py --stamp-like 'phase5:%' --rehearse  # BEGIN..ROLLBACK
    python scripts/remediation/phase4/revert4.py --stamp-like 'phase5:%' --apply

Each run prints its own `WRITE_EXIT=` line; that line is what is read.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import write_stage as W  # noqa: E402 - the psql seam and quoting

from phase4 import write4 as W4  # noqa: E402 - the families, the targets, the plan table's name

#: The families this module may revert: exactly the writer's.
FAMILIES: tuple[str, ...] = tuple(f"{family}:" for family in W4.GROUP_FAMILY.values())
#: A LIKE pattern over run stamps: the stamp alphabet plus `%` and `_`.
_PATTERN = re.compile(r"[a-z0-9:%_-]+")


class RevertRefused(W.WriteRefused):
    """The pattern is not one this module may revert."""


def check_pattern(stamp_like: str) -> str:
    """Refuse a pattern outside the phase-4/5 families, or one that names reversals."""
    if not _PATTERN.fullmatch(stamp_like):
        raise RevertRefused(f"{stamp_like!r} is not a run-stamp LIKE pattern")
    if not stamp_like.startswith(FAMILIES):
        raise RevertRefused(
            f"{stamp_like!r} does not start with one of {list(FAMILIES)}: revert4 reverts phase-4 "
            "and phase-5 writes and nothing else"
        )
    if W.ROLLBACK_KEY_SUFFIX in stamp_like:
        raise RevertRefused(f"{stamp_like!r} names reversals; a reversal is not reverted again")
    return stamp_like


def _set(alias: str, pattern: str) -> str:
    """The matched set: the write rows whose stamp matches, never their reversals."""
    return (
        f"{alias}.run_stamp LIKE {pattern} AND {alias}.run_stamp NOT LIKE "
        f"{W._sql_text('%' + W.ROLLBACK_KEY_SUFFIX)}"
    )


def _reversed(alias: str) -> str:
    """The write row `alias` has its own reversal in the journal: its key **and** its stamp plus
    `-rollback`. The key alone does not name a write: a change key names a transition, so a batch
    written again after a revert (write round 2) journals the same keys as the reverted round, and
    only the stamp tells the reversal of round 1 from one of round 2."""
    suffix = W._sql_text(W.ROLLBACK_KEY_SUFFIX)
    return (
        "EXISTS (SELECT 1 FROM remediation_change_log k\n"
        f"                          WHERE k.change_key = {alias}.change_key || {suffix}\n"
        f"                            AND k.run_stamp = {alias}.run_stamp || {suffix})"
    )


def _targets() -> str:
    return ", ".join(
        f"({W._sql_text(target.table)}, {W._sql_text(target.column)})"
        for target in W4.TARGETS.values()
    )


def _pk_case() -> str:
    tables = sorted({target.table for target in W4.TARGETS.values()})
    whens = " ".join(f"WHEN {W._sql_text(t)} THEN {W._sql_text(W.PK_COLUMN[t])}" for t in tables)
    return f"CASE r.table_name {whens} END"


def _back_at_old() -> list[str]:
    """`WHERE` over the oldest reverted link `o`: the field does not hold `o.old_value`, compared
    in the column's own type by the writer's own comparisons (`write4.TARGETS`, `only_for`)."""
    lines = []
    for index, target in enumerate(W4.TARGETS.values()):
        test = W4.only_for(
            f"o.table_name = {W._sql_text(target.table)} AND o.column_name = "
            f"{W._sql_text(target.column)}",
            target.compare.format(planned="o.old_value"),
        )
        lines.append(("     WHERE " if index == 0 else "        OR ") + test)
    lines[-1] += ";"
    return lines


def render_revert(stamp_like: str, *, rehearse: bool = False) -> str:
    """The reversal of every journalled write whose run stamp matches `stamp_like`.

    `rehearse=True` ends in `ROLLBACK`: the reversal runs for real on the live rows - guards, loop,
    invariants - and none of it is kept.
    """
    pattern = W._sql_text(check_pattern(stamp_like))
    suffix = W._sql_text(W.ROLLBACK_KEY_SUFFIX)
    in_set = _set("l", pattern)
    out = [
        "-- Generated by scripts/remediation/phase4/revert4.py - do not edit by hand.",
        f"-- reverts every journalled write whose run stamp is LIKE {pattern} and that is not",
        "-- reverted yet, newest first, read from remediation_change_log itself; "
        + ("a REHEARSAL: it ends in ROLLBACK." if rehearse else "it ends in COMMIT."),
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        "DO $$",
        "DECLARE",
        "    bad      INTEGER;",
        "    matched  INTEGER;",
        "    expected INTEGER;",
        "    ids      BIGINT[];",
        "    moved    INTEGER := 0;",
        "    r        RECORD;",
        "BEGIN",
        f"    SELECT count(*) INTO matched FROM remediation_change_log l WHERE {in_set};",
        "    IF matched = 0 THEN",
        f"        RAISE EXCEPTION 'revert: no journalled write matches %', {pattern};",
        "    END IF;",
        "",
        "    -- the set, fixed before anything moves: every matched write whose own reversal (its key",
        "    -- and its stamp plus -rollback) is not journalled; a reverted write is never reverted again",
        "    ids := ARRAY(SELECT l.id FROM remediation_change_log l",
        f"                  WHERE {in_set}",
        f"                    AND NOT {_reversed('l')}",
        "                  ORDER BY l.id);",
        "    expected := cardinality(ids);",
        "    IF expected = 0 THEN",
        "        RAISE EXCEPTION 'revert: all % matched write(s) were reverted already', matched;",
        "    END IF;",
        "",
        "    -- guard: only the three written columns, only curated sites, the key is the site",
        "    SELECT count(*) INTO bad",
        "      FROM remediation_change_log l LEFT JOIN unified_sites u ON u.id = l.site_id_ref",
        "     WHERE l.id = ANY(ids)",
        f"       AND ((l.table_name, l.column_name) NOT IN (VALUES {_targets()})",
        f"            OR u.id IS NULL OR u.source_id <> {W._sql_text(W.CURATED_SOURCE)}",
        "            OR l.row_pk <> l.site_id_ref::text);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'revert: % journal row(s) are outside the phase-4/5 targets', bad;",
        "    END IF;",
        "",
        "    -- newest first; each row's conditional WHERE needs it to hold its written value",
        "    FOR r IN SELECT * FROM remediation_change_log l",
        "              WHERE l.id = ANY(ids) ORDER BY l.id DESC LOOP",
        "        moved := moved + apply_remediation_change(",
        f"            r.table_name, r.column_name, {_pk_case()}, r.row_pk,",
        "            r.new_value, r.old_value, r.test_id,",
        f"            r.run_stamp || {suffix}, r.change_key || {suffix},",
        "            r.confidence, r.evidence, r.site_id_ref);",
        "    END LOOP;",
        "    IF moved <> expected THEN",
        "        RAISE EXCEPTION 'revert: % row(s) changed, % journalled', moved, expected;",
        "    END IF;",
        "",
        "    -- invariant: every reverted field holds the old value of its oldest reverted link",
        "    SELECT count(*) INTO bad FROM (",
        "        SELECT DISTINCT ON (l.table_name, l.column_name, l.row_pk) l.*",
        "          FROM remediation_change_log l WHERE l.id = ANY(ids)",
        "         ORDER BY l.table_name, l.column_name, l.row_pk, l.id",
        "    ) o",
        "      LEFT JOIN unified_sites u ON o.table_name = 'unified_sites' AND u.id = o.row_pk::uuid",
        "      LEFT JOIN card_stats c ON o.table_name = 'card_stats' AND c.site_id = o.row_pk::uuid",
        *_back_at_old(),
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'revert: % field(s) are not back at their old value', bad;",
        "    END IF;",
        "",
        "    -- invariant: each reversal is journalled once, with the values swapped",
        "    SELECT count(*) INTO bad FROM remediation_change_log l",
        "      LEFT JOIN remediation_change_log k",
        f"        ON k.change_key = l.change_key || {suffix} AND k.run_stamp = l.run_stamp || {suffix}",
        "     WHERE l.id = ANY(ids)",
        "       AND (k.id IS NULL OR k.old_value IS DISTINCT FROM l.new_value",
        "            OR k.new_value IS DISTINCT FROM l.old_value);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'revert: % row(s) have no matching reversal journal row', bad;",
        "    END IF;",
        "",
        "    RAISE NOTICE 'revert: % row(s) reverted', moved;",
        "END $$;",
        "",
        "ROLLBACK;" if rehearse else "COMMIT;",
        "",
        "-- after the transaction: the write rows matched, and those with their own reversal kept",
        "SELECT 'journalled writes matched' AS metric, count(*)::text AS value",
        f"  FROM remediation_change_log l WHERE {in_set}",
        "UNION ALL",
        "SELECT 'reversals kept', count(*)::text FROM remediation_change_log l",
        f" WHERE {in_set}",
        f"   AND {_reversed('l')}",
    ]
    return "\n".join(out) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="revert4",
        description="Render (and optionally rehearse or apply) the reversal of phase-4/5 writes",
    )
    parser.add_argument("--stamp-like", required=True, help="e.g. 'phase5:%%' or one exact stamp")
    parser.add_argument("--out", default=None, help="write the SQL here (default: print it)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rehearse", action="store_true", help="run it, ending in ROLLBACK")
    mode.add_argument("--apply", action="store_true", help="run it for real")
    parser.add_argument("--host", default=W.SSH_HOST)
    return parser


def _run(argv: list[str] | None, runner: W.SqlRunner | None) -> int:
    args = build_parser().parse_args(argv)
    sql = render_revert(args.stamp_like, rehearse=args.rehearse)
    if args.out:
        Path(args.out).write_text(sql, encoding="utf-8", newline="\n")
        print(f"rendered {args.out}")
    if not (args.rehearse or args.apply):
        if not args.out:
            print(sql)
        return 0
    print(W._exec(runner, sql, host=args.host))
    return 0


def main(argv: list[str] | None = None, *, runner: W.SqlRunner | None = None) -> int:
    return W4.exit_line("WRITE", lambda: _run(argv, runner))


if __name__ == "__main__":
    raise SystemExit(main())
