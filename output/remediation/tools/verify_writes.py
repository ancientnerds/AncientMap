"""The acceptance for a write lane: the journal says what changed, the database must agree.

A check the writer's own driver runs is not an acceptance, so this asks production directly - in both
directions. Every journal row of the lane must find its new value in the database, and every planned
row *without* a journal row must still hold its old value, which covers the withheld and the
boundary-refused rows in the same pass.

**It follows the journal chain** (2026-09-22). A phase-3 row can legitimately be changed again by a
later journalled lane - the Northern-Ireland spelling lane re-spells five `country` rows phase 3 wrote -
and a per-row comparison would then report five deviations for five correct writes. So for every
`(table, column, row)` the lane touched or planned, **every** journal row for it is read, in `id` order
and across all stamps (a reversal that was kept is a change like any other and is part of the chain),
and three things must hold:

1. the chain is continuous: each link's `old_value` is the previous link's `new_value`;
2. the live value is the last link's `new_value`;
3. a lane row is either the last link (it **carries** the new value) or a later link of another stamp
   **supersedes** it - reported separately, by stamp, and not a deviation.

A planned row with no journal row of the lane must still hold its planned old value, unless another
stamp journalled a change to it - then its chain must be continuous, contain the planned old value and
end at the live value (reported as **moved by** that stamp). A lane journal row for a row that is not
in the plan is a deviation too: the plan is what the writes were reviewed against. Every check here is
the old per-row check or strictly stronger: a live value that matches but whose chain is broken is now a
deviation where it used to pass.

Which lane it accepts is `lanes.py`'s: the default is the mass run's rows and `phase3:batch-%`, as it
always was; `--lane gap` reads `_write_dry_gap/ALL_ROWS.jsonl` and `phase3:gap-%`. `--rows` and
`--stamp-like` override the two.

    ./.venv/Scripts/python.exe output/remediation/logs/verify_writes.py
    ./.venv/Scripts/python.exe output/remediation/logs/verify_writes.py --lane gap
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths and the one JSON-lines reader

HOST = "ancientnerds"
TABLE = "unified_sites"
COLUMNS = ("site_type", "period_start", "country")
PSQL = "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1 -t -A"
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
    untouched: int = 0  #: planned rows without a journal row that still hold the old value
    moved: dict[str, int] = field(default_factory=collections.Counter)  #: planned rows, by stamp
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
                f"KETTE GERISSEN {where}: Eintrag {link.id} ({link.stamp}) beginnt bei "
                f"{link.old!r}, der vorige Eintrag {previous.id} ({previous.stamp}) endete bei "
                f"{previous.new!r}"
            )
    last = chain[-1].new if chain else None
    if missing:
        problems.append(f"FEHLT      {where}: die Zeile ist nicht in der Datenbank")
    elif chain and live != last:
        problems.append(
            f"NICHT NEU  {where}: der letzte Journaleintrag {chain[-1].id} ({chain[-1].stamp}) "
            f"sagt {last!r}, gelesen {live!r}"
        )
    return problems, last


def accept(
    *,
    planned: Iterable[Mapping],
    lane_links: Iterable[Link],
    chains: Mapping[Key, list[Link]],
    live: Mapping[tuple[str, str], str | None],
    present: set[str],
) -> Acceptance:
    """The whole acceptance, as a pure function of what the database returned.

    `planned` are the lane's planned rows (`ALL_ROWS.jsonl`), `lane_links` the lane's journal rows,
    `chains` every journal row per key (all stamps, `id` order), `live` the value each row holds now
    keyed by `(column, pk)`, and `present` the ids the live read returned at all.
    """
    result = Acceptance()
    plan_keys: dict[Key, Mapping] = {}
    for row in planned:
        plan_keys[(TABLE, row["column"], row["pk"])] = row
    lane_by_key: dict[Key, list[Link]] = collections.defaultdict(list)
    for link in lane_links:
        lane_by_key[link.key].append(link)

    for key, links in sorted(lane_by_key.items()):
        chain = chains.get(key, [])
        problems, _ = check_chain(
            key, chain, live.get((key[1], key[2])), missing=key[2] not in present
        )
        result.deviations.extend(problems)
        if key not in plan_keys:
            result.deviations.append(
                f"AUSSERHALB {key[2]} {key[1]}: die Spur hat eine Zeile journalisiert, die nicht im "
                "Plan steht"
            )
        ids = [link.id for link in chain]
        for link in links:
            if link.id not in ids:
                result.deviations.append(
                    f"KETTE UNVOLLSTAENDIG {key[2]} {key[1]}: Eintrag {link.id} fehlt in der Kette"
                )
                continue
            later = chain[ids.index(link.id) + 1 :]
            if not later:
                result.carried += 1
            else:
                result.superseded[later[-1].stamp] += 1

    for key, row in sorted(plan_keys.items()):
        if key in lane_by_key:
            continue
        where = f"{key[2]} {key[1]}"
        planned_old = _text(row["old_value"])
        chain = chains.get(key, [])
        value = live.get((key[1], key[2]))
        if key[2] not in present:
            result.deviations.append(f"FEHLT      {row.get('site_name', '')} ({key[2]})")
            continue
        if not chain:
            if value != planned_old:
                result.deviations.append(
                    f"DOCH GEAENDERT {where}: erwartet alt {planned_old!r}, gelesen {value!r}, "
                    "und kein Journaleintrag erklaert es"
                )
            else:
                result.untouched += 1
            continue
        problems, last = check_chain(key, chain, value, missing=False)
        result.deviations.extend(problems)
        states = {chain[0].old, *(link.new for link in chain)}
        if planned_old not in states:
            result.deviations.append(
                f"FREMDE KETTE {where}: der geplante alte Wert {planned_old!r} kommt in der Kette "
                "dieses Feldes nicht vor"
            )
        if value == planned_old and last == planned_old:
            result.untouched += 1
        else:
            result.moved[chain[-1].stamp] += 1
    return result


# ------------------------------------------------------------------------------------ the reads
def psql(sql: str, *, host: str = HOST) -> str:
    result = subprocess.run(
        ["ssh", host, PSQL],
        input=sql.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"psql failed ({result.returncode}): {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout.decode("utf-8")


def json_rows(text: str) -> list[dict]:
    """One `to_jsonb(...)::text` object per line; anything else is damage, not a line to skip."""
    rows: list[dict] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"psql line {number} is not JSON: {line[:120]!r}") from exc
    return rows


def _literals(values: Iterable[str]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


JOURNAL_COLUMNS = "id, table_name, column_name, row_pk, old_value, new_value, run_stamp"


def lane_journal_sql(stamp_like: str) -> str:
    return (
        f"SELECT to_jsonb(t)::text FROM (SELECT {JOURNAL_COLUMNS} FROM remediation_change_log "
        f"WHERE run_stamp LIKE {_literals([stamp_like])} "
        f"AND run_stamp NOT LIKE {_literals(['%' + ROLLBACK_SUFFIX])} ORDER BY id) t;\n"
    )


def chain_sql(pks: list[str]) -> str:
    return (
        f"SELECT to_jsonb(t)::text FROM (SELECT {JOURNAL_COLUMNS} FROM remediation_change_log "
        f"WHERE table_name = '{TABLE}' AND column_name IN ({_literals(COLUMNS)}) "
        f"AND row_pk IN ({_literals(pks)}) ORDER BY id) t;\n"
    )


def live_sql(pks: list[str]) -> str:
    return (
        "SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, site_type, "
        "period_start::text AS period_start, country FROM unified_sites "
        f"WHERE id::text IN ({_literals(pks)})) t;\n"
    )


def read_database(
    pks: list[str], *, stamp_like: str, run: Callable[[str], str]
) -> tuple[list[Link], dict[Key, list[Link]], dict[tuple[str, str], str | None], set[str]]:
    """The lane's journal, every chain the plan or the lane touches, and the live values."""
    lane_links = [Link.from_row(row) for row in json_rows(run(lane_journal_sql(stamp_like)))]
    everyone = sorted(set(pks) | {link.pk for link in lane_links})
    chains: dict[Key, list[Link]] = collections.defaultdict(list)
    live: dict[tuple[str, str], str | None] = {}
    present: set[str] = set()
    for start in range(0, len(everyone), WINDOW):
        window = everyone[start : start + WINDOW]
        for row in json_rows(run(chain_sql(window))):
            link = Link.from_row(row)
            chains[link.key].append(link)
        for row in json_rows(run(live_sql(window))):
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
    parser.add_argument("--stamp-like", default=None, help="override the lane's stamp pattern")
    parser.add_argument("--host", default=HOST)
    args = parser.parse_args(argv)
    paths = lanes.lane(args.lane)
    rows_path = pathlib.Path(args.rows) if args.rows else paths.rows
    stamp_like = args.stamp_like or paths.stamp_like

    planned = lanes.read_jsonl(rows_path)
    pks = sorted({row["pk"] for row in planned})
    lane_links, chains, live, present = read_database(
        pks, stamp_like=stamp_like, run=lambda sql: psql(sql, host=args.host)
    )
    in_columns = [link for link in lane_links if link.column in COLUMNS and link.table == TABLE]
    print(f"Spur {paths.name}: {rows_path} | Stempel {stamp_like}")
    print(
        f"Journaleintraege dieser Spur: {len(lane_links)} | davon in den drei Feldern: "
        f"{len(in_columns)} | geplante Zeilen: {len(planned)}"
    )
    print(f"aus der Datenbank gelesen: {len(present)} von {len(set(pks))} geplanten Sites")

    result = accept(
        planned=planned, lane_links=in_columns, chains=chains, live=live, present=present
    )
    for line in result.deviations:
        print(f"  {line}")
    superseded = sum(result.superseded.values())
    moved = sum(result.moved.values())
    print(
        f"\n{result.carried} Zeilen tragen den neuen Wert, {superseded} wurden spaeter von einer "
        f"anderen Spur ueberschrieben, {result.untouched} geplante Zeilen tragen unveraendert den "
        f"alten, {moved} geplante Zeilen hat eine andere Spur geaendert"
    )
    for stamp, count in sorted(result.superseded.items()):
        print(f"  ueberschrieben von {stamp}: {count}")
    for stamp, count in sorted(result.moved.items()):
        print(f"  geaendert von {stamp}: {count}")
    print(f"ERGEBNIS: {len(result.deviations)} Abweichungen")
    return 1 if result.deviations else 0


if __name__ == "__main__":
    sys.exit(main())
