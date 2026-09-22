"""The acceptance for a write lane: the journal says what changed, the database must agree.

A check the writer's own driver runs is not an acceptance, so this asks production directly - in both
directions. Every journal row of the lane must find its new value in the database, and every planned
row *without* a journal row must be one the wave was meant to leave alone and must still hold its old
value.

**It follows the journal chain** (2026-09-22). A phase-3 row can legitimately be changed again by a
later journalled lane - the Northern-Ireland spelling lane re-spells five `country` rows phase 3 wrote -
and a per-row comparison would then report five deviations for five correct writes. So for every
`(table, column, row)` the lane touched or planned, **every** journal row for it is read, in `id` order
and across all stamps (a reversal that was kept is a change like any other and is part of the chain),
and it must be continuous: each link's `old_value` is the previous link's `new_value`, and the live
value is the last link's `new_value`.

**What must hold per row** (2026-09-23, after a review found the first version too forgiving):

* a lane journal row must be a planned row's, must carry exactly the planned old and new value, must
  be the lane's only write of that row, and must not be a row the wave withheld (a hold of the
  hand-read or a boundary refusal of `write_gate.gate` - the same decision the gate wrote by);
* it is **carried** when it is the chain's last link, **superseded** when every later link belongs to a
  stamp the operator names with `--allow-stamp` (the Northern-Ireland lane) - any other later stamp
  is a deviation;
* a planned row without a lane journal row must be a withheld one - a planned, allowed row that is
  not in the database is a write that did not happen (a batch the writer skipped, a wave that stopped),
  and is reported as such, never counted as "unchanged";
* a withheld row must still hold its planned old value, or have been changed only by allowed stamps
  after it (**moved**), through a chain that contains that old value.

Relative to the per-row check it replaced, two cases are accepted **by design** and only for a stamp
the operator lists: a lane row whose live value is a later allowed stamp's (the old check said
`NICHT NEU`), and a withheld row an allowed stamp changed (the old check said `DOCH GEAENDERT`).
Everything else the old check refused is still refused, and more is: a broken chain behind a matching
live value, a lane write of an unplanned value, a withheld row that was written, a planned row that
was silently not written, and a lane that wrote one row twice.

Which lane it accepts is `lanes.py`'s: the default is the mass run's rows and `phase3:batch-%`, as it
always was; `--lane gap` reads `_write_dry_gap/ALL_ROWS.jsonl` and `phase3:gap-%`. `--rows`,
`--hold` and `--stamp-like` override the lane's three. A written lane's rows file must be the plan it
was written from (`lanes.REVIEWED_PLAN_KEYS_SHA256`).

    ./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py
    ./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --lane gap
    ./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --allow-stamp <later stamp>
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths, the JSON-lines reader and the database seam
import write_gate  # noqa: E402 - the gate's withheld rows: the decision the wave was written by

TABLE = "unified_sites"
COLUMNS = ("site_type", "period_start", "country")
#: A reversal's stamp suffix (`write_stage.ROLLBACK_KEY_SUFFIX`). Such a row is never counted as a
#: write of the lane - but it is part of the chain, because a kept reversal changed the value.
ROLLBACK_SUFFIX = "-rollback"
WINDOW = 200

Key = tuple[str, str, str]  #: (table, column, row_pk)


@dataclass(frozen=True)
class Link:
    """One journal row, as the chain sees it."""

    id: int
    table: str
    column: str
    pk: str
    old: str | None
    new: str | None
    stamp: str

    @property
    def key(self) -> Key:
        return (self.table, self.column, self.pk)

    @classmethod
    def from_row(cls, row: Mapping) -> Link:
        return cls(
            id=int(row["id"]),
            table=str(row["table_name"]),
            column=str(row["column_name"]),
            pk=str(row["row_pk"]),
            old=row["old_value"],
            new=row["new_value"],
            stamp=str(row["run_stamp"]),
        )


@dataclass
class Acceptance:
    """What the database says about one lane, counted and named."""

    carried: int = 0  #: lane rows whose new value is the live value and the last link
    superseded: dict[str, int] = field(default_factory=collections.Counter)  #: by later stamp
    untouched: int = 0  #: withheld rows that still hold the old value
    moved: dict[str, int] = field(default_factory=collections.Counter)  #: withheld rows, by stamp
    deviations: list[str] = field(default_factory=list)


def _text(value: object) -> str | None:
    """The journal stores text; a live integer column is compared in the same spelling."""
    return None if value is None else str(value)


def check_chain(
    key: Key, chain: list[Link], live: str | None, *, missing: bool
) -> tuple[list[str], str | None]:
    """(deviations, the chain's last new value) for one row's whole journal history."""
    problems: list[str] = []
    where = f"{key[2]} {key[1]}"
    for previous, link in zip(chain, chain[1:], strict=False):
        if link.old != previous.new:
            problems.append(
                f"BROKEN CHAIN {where}: journal row {link.id} ({link.stamp}) starts at "
                f"{link.old!r}, the row before it, {previous.id} ({previous.stamp}), ended at "
                f"{previous.new!r}"
            )
    last = chain[-1].new if chain else None
    if missing:
        problems.append(f"MISSING {where}: the row is not in the database")
    elif chain and live != last:
        problems.append(
            f"NOT NEW {where}: the last journal row {chain[-1].id} ({chain[-1].stamp}) says "
            f"{last!r}, the database holds {live!r}"
        )
    return problems, last


def _unlisted(links: Iterable[Link], allowed: Collection[str]) -> list[str]:
    """The stamps among `links` the operator did not list, in chain order, each once."""
    return list(dict.fromkeys(link.stamp for link in links if link.stamp not in allowed))


def accept(
    *,
    planned: Iterable[Mapping],
    lane_links: Iterable[Link],
    chains: Mapping[Key, list[Link]],
    live: Mapping[tuple[str, str], str | None],
    present: set[str],
    withheld: Collection[str],
    allowed: Collection[str],
) -> Acceptance:
    """The whole acceptance, as a pure function of what the database returned.

    `planned` are the lane's planned rows (`ALL_ROWS.jsonl`), `lane_links` the lane's journal rows,
    `chains` every journal row per key (all stamps, `id` order), `live` the value each row holds now
    keyed by `(column, pk)`, `present` the ids the live read returned at all, `withheld` the change
    keys the wave was meant to leave alone (holds and boundary refusals) and `allowed` the stamps that
    may change a planned row after the lane.
    """
    result = Acceptance()
    plan_keys: dict[Key, Mapping] = {}
    for row in planned:
        plan_keys[(TABLE, row["column"], row["pk"])] = row
    lane_by_key: dict[Key, list[Link]] = collections.defaultdict(list)
    for link in lane_links:
        lane_by_key[link.key].append(link)
    lane_stamps = {link.stamp for links in lane_by_key.values() for link in links}

    for key, links in sorted(lane_by_key.items()):
        where = f"{key[2]} {key[1]}"
        chain = chains.get(key, [])
        problems, _ = check_chain(
            key, chain, live.get((key[1], key[2])), missing=key[2] not in present
        )
        result.deviations.extend(problems)
        row = plan_keys.get(key)
        if row is None:
            result.deviations.append(
                f"OUTSIDE THE PLAN {where}: the lane journalled a row that is not in the plan"
            )
        elif row["change_key"] in withheld:
            result.deviations.append(
                f"WRITTEN THOUGH WITHHELD {where}: the wave was to leave this row alone (a hold or "
                "a boundary refusal), and the lane journalled a write of it"
            )
        if len(links) > 1:
            result.deviations.append(
                f"WRITTEN TWICE {where}: the lane journalled {len(links)} writes of this row "
                f"({', '.join(str(link.id) for link in links)})"
            )
        ids = [link.id for link in chain]
        for link in links:
            if row is not None and (link.old, link.new) != (
                _text(row["old_value"]),
                _text(row["new_value"]),
            ):
                result.deviations.append(
                    f"OTHER VALUE {where}: journal row {link.id} wrote {link.old!r} -> "
                    f"{link.new!r}, the plan says {_text(row['old_value'])!r} -> "
                    f"{_text(row['new_value'])!r}"
                )
            if link.id not in ids:
                result.deviations.append(
                    f"CHAIN INCOMPLETE {where}: journal row {link.id} is missing from the chain"
                )
                continue
            later = chain[ids.index(link.id) + 1 :]
            if not later:
                result.carried += 1
                continue
            foreign = _unlisted(
                (other for other in later if other.stamp not in lane_stamps), allowed
            )
            if foreign:
                result.deviations.append(
                    f"CHANGED LATER BY AN UNLISTED STAMP {where}: {foreign} wrote after journal row "
                    f"{link.id}; name a stamp with --allow-stamp once you know it is right"
                )
                continue
            if any(other.stamp in lane_stamps for other in later):
                continue  # the lane's own second write: WRITTEN TWICE above says so
            result.superseded[later[-1].stamp] += 1

    for key, row in sorted(plan_keys.items()):
        if key in lane_by_key:
            continue
        where = f"{key[2]} {key[1]}"
        planned_old = _text(row["old_value"])
        chain = chains.get(key, [])
        value = live.get((key[1], key[2]))
        if key[2] not in present:
            result.deviations.append(f"MISSING {row.get('site_name', '')} ({key[2]})")
            continue
        if row["change_key"] not in withheld:
            result.deviations.append(
                f"NOT WRITTEN {where}: planned {planned_old!r} -> {_text(row['new_value'])!r}, "
                f"neither held nor refused at the boundary, and the lane journalled no write of it; "
                f"the database holds {value!r}"
            )
            continue
        if not chain:
            if value != planned_old:
                result.deviations.append(
                    f"CHANGED ANYWAY {where}: expected the old value {planned_old!r}, the "
                    f"database holds {value!r}, and no journal row explains it"
                )
            else:
                result.untouched += 1
            continue
        problems, last = check_chain(key, chain, value, missing=False)
        result.deviations.extend(problems)
        states = [chain[0].old, *(link.new for link in chain)]
        if planned_old not in states:
            result.deviations.append(
                f"FOREIGN CHAIN {where}: the planned old value {planned_old!r} never occurs in "
                "this field's chain"
            )
            continue
        # the changes after the field last held the planned old value
        after = chain[len(states) - 1 - states[::-1].index(planned_old) :]
        if not after:
            result.untouched += 1
            continue
        foreign = _unlisted(after, allowed)
        if foreign:
            result.deviations.append(
                f"CHANGED BY AN UNLISTED STAMP {where}: {foreign} changed a withheld row after its "
                "planned old value; name a stamp with --allow-stamp once you know it is right"
            )
            continue
        result.moved[after[-1].stamp] += 1
    return result


# ------------------------------------------------------------------------------------ the reads
JOURNAL_COLUMNS = "id, table_name, column_name, row_pk, old_value, new_value, run_stamp"


def lane_journal_sql(stamp_like: str) -> str:
    return (
        f"SELECT to_jsonb(t)::text FROM (SELECT {JOURNAL_COLUMNS} FROM remediation_change_log "
        f"WHERE run_stamp LIKE {lanes.sql_text(stamp_like)} "
        f"AND run_stamp NOT LIKE {lanes.sql_text('%' + ROLLBACK_SUFFIX)} ORDER BY id) t;\n"
    )


def chain_sql(pks: list[str]) -> str:
    return (
        f"SELECT to_jsonb(t)::text FROM (SELECT {JOURNAL_COLUMNS} FROM remediation_change_log "
        f"WHERE table_name = '{TABLE}' AND column_name IN ({lanes.sql_literals(COLUMNS)}) "
        f"AND row_pk IN ({lanes.sql_literals(pks)}) ORDER BY id) t;\n"
    )


def live_sql(pks: list[str]) -> str:
    return (
        "SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, site_type, "
        "period_start::text AS period_start, country FROM unified_sites "
        f"WHERE id::text IN ({lanes.sql_literals(pks)})) t;\n"
    )


def read_database(
    pks: list[str], *, stamp_like: str, run: Callable[[str], str]
) -> tuple[list[Link], dict[Key, list[Link]], dict[tuple[str, str], str | None], set[str]]:
    """The lane's journal, every chain the plan or the lane touches, and the live values."""
    lane_links = [Link.from_row(row) for row in lanes.json_rows(run(lane_journal_sql(stamp_like)))]
    everyone = sorted(set(pks) | {link.pk for link in lane_links})
    chains: dict[Key, list[Link]] = collections.defaultdict(list)
    live: dict[tuple[str, str], str | None] = {}
    present: set[str] = set()
    for start in range(0, len(everyone), WINDOW):
        window = everyone[start : start + WINDOW]
        for row in lanes.json_rows(run(chain_sql(window))):
            link = Link.from_row(row)
            chains[link.key].append(link)
        for row in lanes.json_rows(run(live_sql(window))):
            present.add(row["id"])
            for column in COLUMNS:
                live[(column, row["id"])] = _text(row[column])
    for chain in chains.values():
        chain.sort(key=lambda link: link.id)
    return lane_links, dict(chains), live, present


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify-writes")
    parser.add_argument("--lane", default=lanes.MASS, help="which run's paths (lanes.py)")
    parser.add_argument("--rows", default=None, help="override the lane's ALL_ROWS.jsonl")
    parser.add_argument("--hold", default=None, help="override the lane's HOLDS.jsonl")
    parser.add_argument("--stamp-like", default=None, help="override the lane's stamp pattern")
    parser.add_argument(
        "--allow-stamp",
        action="append",
        default=[],
        help="a later stamp that may change the lane's rows (repeatable), e.g. the UK lane's",
    )
    parser.add_argument("--host", default=lanes.HOST)
    args = parser.parse_args(argv)
    paths = lanes.lane(args.lane)
    rows_path = pathlib.Path(args.rows) if args.rows else paths.rows
    hold_path = pathlib.Path(args.hold) if args.hold else paths.holds
    stamp_like = args.stamp_like or paths.stamp_like

    planned = lanes.read_jsonl(rows_path)
    lanes.assert_reviewed_plan(paths.name, planned, path=rows_path)
    holds = write_gate.load_holds(hold_path, planned)
    positions = write_gate.coordinates(
        {row["site_id"] for row in planned if row["column"] == "country"}, host=args.host
    )
    verdicts = write_gate.withheld(planned, positions=positions, holds=holds)
    withheld = {key for key, (allowed, _) in verdicts.items() if not allowed}
    pks = sorted({row["pk"] for row in planned})
    lane_links, chains, live, present = read_database(
        pks, stamp_like=stamp_like, run=lambda sql: lanes.psql(sql, host=args.host)
    )
    in_columns = [link for link in lane_links if link.column in COLUMNS and link.table == TABLE]
    print(
        f"lane {paths.name}: {rows_path} | stamps {stamp_like} | allowed later {args.allow_stamp}"
    )
    print(
        f"journal rows of this lane: {len(lane_links)} | in the three fields: {len(in_columns)} | "
        f"planned rows: {len(planned)} | withheld: {len(withheld)} ({len(holds)} held, "
        f"{len(withheld) - len(holds)} refused at the boundary)"
    )
    print(f"read from the database: {len(present)} of {len(set(pks))} planned sites")

    result = accept(
        planned=planned,
        lane_links=in_columns,
        chains=chains,
        live=live,
        present=present,
        withheld=withheld,
        allowed=set(args.allow_stamp),
    )
    for line in result.deviations:
        print(f"  {line}")
    superseded = sum(result.superseded.values())
    moved = sum(result.moved.values())
    print(
        f"\n{result.carried} rows carry the new value, {superseded} were superseded later by an "
        f"allowed stamp, {result.untouched} withheld rows still hold the old one, {moved} withheld "
        "rows an allowed stamp changed"
    )
    for stamp, count in sorted(result.superseded.items()):
        print(f"  superseded by {stamp}: {count}")
    for stamp, count in sorted(result.moved.items()):
        print(f"  changed by {stamp}: {count}")
    print(f"RESULT: {len(result.deviations)} deviation(s)")
    return 1 if result.deviations else 0


if __name__ == "__main__":
    sys.exit(main())
