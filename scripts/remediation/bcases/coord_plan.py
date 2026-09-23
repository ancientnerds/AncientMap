"""The coordinate write plan for the owner cases: rendered here, applied by nobody here.

Built from the classifier's `move` verdicts (`coords.jsonl`, `classify.weigh`): a site is in the plan
only when two independent witnesses agree within the tolerance and its stored point lies outside it.
FIELD_CONTRACT section 4.6 reserves coordinate changes for the owner, so this plan is **not applied**:
it is the reviewed, reversible form of the change, ready for the owner's decision (HUMAN_ONLY B1/B2).

It has the guarded shape of `output/remediation/tools/qid_repair.py` - render, a read-only `check`
before, a read-only `verify` after, and the undo - and it writes through `apply_remediation_change()`
(migrations 0017/0018/0022), which finds its row by `unified_sites.id` in the key's own type, refuses a
row that no longer holds the old value, re-reads what it wrote and journals it in the same statement.

**Three journalled changes per site: `lat`, `lon` and `geom`.** `unified_sites` has no trigger
(`pg_trigger`, read 2026-09-22), and every writer in the code base that moves a point sets
`geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)` next to it (`api/routes/sites.py`); the prospector's
dedup measures distance on `geom` (`pipeline/lyra/prospector/dedup.py`). A plan that moved `lat`/`lon`
alone would leave the spatial index on the old point. On 2026-09-23, 5,003 of the 5,004 curated rows
hold exactly that `geom` (the one other holds NULL) - read-only count.

Files, in `output/remediation/bcases/coords_plan/`:

* `PLAN.jsonl` - one row per journalled change, with the witnesses as its evidence;
* `APPLY.sql` - one transaction: server-side bounds, guards, one `apply_remediation_change()` per
  row, invariants (every site holds the new point and a `geom` equal to it; journal = plan), `COMMIT`;
* `REHEARSAL.sql` - the same statement ending in `ROLLBACK` (not versioned: it keeps nothing);
* `ROLLBACK.sql` - the inverse, conditional on the new values, under its own stamp;
* `PLAN.md` - per site: the witnesses, the distance moved, the reason.

Every statement carries `-- plan sha256 <digest>` (`prod_write.pin_line`) and `check`/`verify` refuse a
file on disk that is not, byte for byte, what the plan renders.

**Two waves, one renderer** (`Wave`). Wave 1 (`2026-09-23_owner-case-coordinates`, applied) is the
classifier's `move` verdicts (`coords.jsonl`) in `coords_plan/`; its files still render byte for byte.
Wave 2 (`2026-09-23_owner-case-coordinates-wave2`, `--wave 2`) is the `move` verdicts of
`coords3/VERDICTS.jsonl` - the first wave's review cases weighed again with the web witnesses
`web_witness.py` proved from the live page - in `coords_plan_wave2/`, under its own stamp, so its
journal guard and its `verify` see its own rows only. A site of wave 1's plan is refused in wave 2.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mechanical.lane import LOCK_TIMEOUT, STATEMENT_TIMEOUT, sql_literal
from mechanical.plan import UUID_RE, psql_json_reader
from phase3.write_stage import plan_digest  # sha256 over the rows' JSON lines, for any row type
from prod_write import pin_line

from bcases import inputs
from bcases.classify import label_of

RUN_STAMP = "2026-09-23_owner-case-coordinates"
ROLLBACK_STAMP = RUN_STAMP + "-rollback"
TEST_ID = "B1B2/coordinates"
CONFIDENCE = "two_source"
COLUMNS = ("geom", "lat", "lon")
PLAN_TABLE = "_coord_plan"
LABEL = "owner-case coordinates"
PLAN_DIR = "coords_plan"


class PlanError(RuntimeError):
    """The plan or a statement on disk is not what the classifier's verdicts render."""


@dataclass(frozen=True)
class Wave:
    """One coordinate plan: its verdicts, its journal stamp, where it renders, how PLAN.md reads."""

    number: int
    run_stamp: str
    #: The verdict file under `--out` whose `move` rows this wave plans.
    verdicts: str
    plan_dir: str
    title: str
    #: What the moves were rendered from, as PLAN.md's first paragraph says it.
    source: str
    #: Paragraphs PLAN.md adds after the independence rule.
    notes: tuple[str, ...] = ()
    #: The plan directories of earlier waves: a site planned there is never planned here.
    earlier: tuple[str, ...] = ()

    @property
    def rollback_stamp(self) -> str:
        return self.run_stamp + "-rollback"

    @property
    def flag(self) -> str:
        """The `run.py` option that selects this wave ("" for wave 1, the default)."""
        return "" if self.number == 1 else f" --wave {self.number}"


WAVE1 = Wave(
    1,
    RUN_STAMP,
    "coords.jsonl",
    PLAN_DIR,
    "# Owner-case coordinates - planned, not applied",
    "the classifier's `move` verdicts",
)
WAVE2 = Wave(
    2,
    "2026-09-23_owner-case-coordinates-wave2",
    "coords3/VERDICTS.jsonl",
    "coords_plan_wave2",
    "# Owner-case coordinates, wave 2 (a third witness from the web) - planned, not applied",
    "the `move` verdicts of `coords3/VERDICTS.jsonl` (`web_witness.py reweigh`: the first wave's "
    "review cases weighed again with the web witnesses proven from the live page)",
    (
        "A web witness is a page outside Wikipedia, Wikidata and their mirrors whose coordinates "
        "`scripts/remediation/bcases/web_witness.py` read from the live page: the quoted text occurs "
        "in the page, parses to exactly the stated numbers, and stands within 1,500 characters of a "
        "distinctive word of the site's name. Pages of one publisher (a registered domain) are one "
        "witness; two web witnesses pair only across publishers, under the same independence rule. "
        "Where a web witness takes part, two witnesses that are each one with a third are one with "
        "each other (`copy_groups`), and a P625 whose references name the page's publisher is that "
        "page (`cited_publishers`). A move into another country than the stored one is not in this "
        "plan (it is read first).",
    ),
    (PLAN_DIR,),
)
WAVES = {wave.number: wave for wave in (WAVE1, WAVE2)}


@dataclass(frozen=True)
class Change:
    """One conditional change of one column of one curated site, and what the journal records."""

    site_id: str
    name: str
    column: str
    old_value: str
    new_value: str
    evidence: tuple[dict[str, Any], ...]
    change_key: str

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def change_key(site_id: str, column: str, old: str, new: str) -> str:
    parts = json.dumps([site_id, "unified_sites", column, old, new, TEST_ID], ensure_ascii=False)
    return "coordinates:" + hashlib.sha256(parts.encode("utf-8")).hexdigest()


def number(value: float) -> str:
    """A coordinate as text that parses back to exactly this double (Python's shortest repr)."""
    if not math.isfinite(value):
        raise PlanError(f"{value!r} is not a coordinate")
    return repr(float(value))


def ewkt(lat: float, lon: float) -> str:
    """The point `geom` must hold for `lat`/`lon`: `ST_SetSRID(ST_MakePoint(lon, lat), 4326)`."""
    return f"SRID=4326;POINT({number(lon)} {number(lat)})"


def _evidence(row: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    entries = [
        {"source": f"witness:{label_of(w)}", "quote": w["quote"], "url": w["url"]}
        for w in row["witnesses"]
        if label_of(w) in row["agreeing"]
    ]
    entries.append(
        {
            "source": "owner-case classifier",
            "quote": f"{row['reason']}; tolerance {row['tolerance_m']} m; rule {row['rule']}",
            "url": None,
        }
    )
    return tuple(entries)


def changes(rows: Sequence[Mapping[str, Any]]) -> list[Change]:
    """Three changes per `move` verdict, in site order then column order. Nothing else is planned."""
    out: list[Change] = []
    seen: set[str] = set()
    for row in sorted((r for r in rows if r["verdict"] == "move"), key=lambda r: r["site_id"]):
        sid = str(row["site_id"])
        if not UUID_RE.match(sid):
            raise PlanError(f"{sid!r} is not a UUID")
        if sid in seen:
            raise PlanError(f"{sid} is planned twice")
        seen.add(sid)
        if len(row["agreeing"]) < 2:
            raise PlanError(
                f"{row['name']}: a move needs two agreeing witnesses, not {row['agreeing']}"
            )
        lat, lon = float(row["new"]["lat"]), float(row["new"]["lon"])
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise PlanError(f"{row['name']}: {lat}, {lon} is not a point on Earth")
        old = {"lat": row["lat_text"], "lon": row["lon_text"], "geom": row["geom_text"]}
        if old["geom"] is None:
            raise PlanError(f"{row['name']}: no geom to condition the write on")
        new = {"lat": number(lat), "lon": number(lon), "geom": ewkt(lat, lon)}
        if float(old["lat"]) == lat and float(old["lon"]) == lon:
            raise PlanError(f"{row['name']}: the new point is the stored point - not a change")
        evidence = _evidence(row)
        for column in COLUMNS:
            out.append(
                Change(
                    site_id=sid,
                    name=str(row["name"]),
                    column=column,
                    old_value=str(old[column]),
                    new_value=new[column],
                    evidence=evidence,
                    change_key=change_key(sid, column, str(old[column]), new[column]),
                )
            )
    return out


def render(
    rows: Sequence[Change], *, reversal: bool, rehearsal: bool = False, wave: Wave = WAVE1
) -> str:
    """One transaction over every row, or nothing: guards, the writes, invariants, COMMIT/ROLLBACK."""
    if not rows:
        raise PlanError("refusing to render a statement with no rows")
    if len(rows) % len(COLUMNS):
        raise PlanError(f"{len(rows)} rows are not {len(COLUMNS)} columns per site")
    stamp = wave.rollback_stamp if reversal else wave.run_stamp
    what = "reversal" if reversal else "move"
    values = []
    for row in rows:
        old, new = (row.new_value, row.old_value) if reversal else (row.old_value, row.new_value)
        key = row.change_key + ("-rollback" if reversal else "")
        # sort_keys: the plan is read back from PLAN.jsonl (written with sorted keys), and the statement
        # it renders must be the same bytes as the one rendered before the round trip.
        evidence = (
            sql_literal(json.dumps(list(row.evidence), ensure_ascii=False, sort_keys=True))
            + "::jsonb"
        )
        values.append(
            f"    ({sql_literal(row.site_id)}::uuid, {sql_literal(row.column)}, {sql_literal(old)}, "
            f"{sql_literal(new)}, {sql_literal(key)}, {evidence})"
        )
    sites = len({row.site_id for row in rows})
    t = PLAN_TABLE
    lines = [
        "-- Generated by scripts/remediation/bcases/coord_plan.py - do not edit by hand.",
        pin_line(plan_digest(rows)),
        f"-- the coordinate {what} of {sites} curated site(s): {len(rows)} journalled changes "
        f"(geom, lat, lon each); run stamp '{stamp}'.",
        "-- Every change goes through apply_remediation_change(): conditional on the old value, one",
        "-- row by unified_sites.id, re-read, journalled in the same statement.",
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        f"SET LOCAL lock_timeout = {sql_literal(LOCK_TIMEOUT)};",
        f"SET LOCAL statement_timeout = {sql_literal(STATEMENT_TIMEOUT)};",
        "",
        f"CREATE TEMP TABLE {t} (",
        "    site_id     UUID NOT NULL,",
        "    column_name TEXT NOT NULL,",
        "    old_value   TEXT NOT NULL,",
        "    new_value   TEXT NOT NULL,",
        "    change_key  TEXT NOT NULL,",
        "    evidence    JSONB NOT NULL,",
        "    PRIMARY KEY (site_id, column_name)",
        ") ON COMMIT DROP;",
        "",
        f"INSERT INTO {t} (site_id, column_name, old_value, new_value, change_key, evidence) VALUES",
        ",\n".join(values) + ";",
        "",
        "DO $$",
        "DECLARE",
        "    bad      INTEGER;",
        "    moved    INTEGER := 0;",
        f"    expected INTEGER := {len(rows)};",
        "    r        RECORD;",
        "BEGIN",
        "    -- guard 1: every site is a curated site that still exists",
        f"    SELECT count(*) INTO bad FROM {t} p LEFT JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{LABEL}: % row(s) are not curated sites', bad;",
        "    END IF;",
        "    -- guard 2: every site moves as a whole - geom, lat and lon, nothing else",
        "    SELECT count(*) INTO bad FROM (",
        f"        SELECT site_id FROM {t} GROUP BY site_id",
        "        HAVING array_agg(column_name ORDER BY column_name) <> ARRAY['geom', 'lat', 'lon']",
        "    ) x;",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{LABEL}: % site(s) do not move geom, lat and lon together', bad;",
        "    END IF;",
        "    -- guard 3: every row still holds the planned old value, compared in the column's type",
        f"    SELECT count(*) INTO bad FROM {t} p JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE (p.column_name = 'lat' AND u.lat IS DISTINCT FROM p.old_value::double precision)",
        "        OR (p.column_name = 'lon' AND u.lon IS DISTINCT FROM p.old_value::double precision)",
        "        OR (p.column_name = 'geom' AND u.geom IS DISTINCT FROM p.old_value::geometry);",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{LABEL}: % row(s) no longer hold the planned old value', bad;",
        "    END IF;",
        "    -- guard 4: the planned geom is the planned point",
        f"    SELECT count(*) INTO bad FROM {t} g",
        f"      JOIN {t} a ON a.site_id = g.site_id AND a.column_name = 'lat'",
        f"      JOIN {t} o ON o.site_id = g.site_id AND o.column_name = 'lon'",
        "     WHERE g.column_name = 'geom' AND g.new_value::geometry IS DISTINCT FROM",
        "           ST_SetSRID(ST_MakePoint(o.new_value::double precision,",
        "                                   a.new_value::double precision), 4326);",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{LABEL}: % planned geom value(s) are not the planned point', bad;",
        "    END IF;",
        "    -- the writes: apply_remediation_change raises unless exactly one row matched",
        f"    FOR r IN SELECT * FROM {t} ORDER BY site_id, column_name LOOP",
        "        moved := moved + apply_remediation_change(",
        "            'unified_sites', r.column_name, 'id', r.site_id::text,",
        "            r.old_value, r.new_value,",
        f"            {sql_literal(TEST_ID)}, {sql_literal(stamp)}, r.change_key, "
        f"{sql_literal(CONFIDENCE)}, r.evidence, r.site_id);",
        "    END LOOP;",
        "    IF moved <> expected THEN",
        f"        RAISE EXCEPTION '{LABEL}: % row(s) changed, % planned', moved, expected;",
        "    END IF;",
        "    -- invariant 1: every site holds the new point, and a geom that is that point",
        f"    SELECT count(*) INTO bad FROM {t} p JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE (p.column_name = 'lat' AND u.lat IS DISTINCT FROM p.new_value::double precision)",
        "        OR (p.column_name = 'lon' AND u.lon IS DISTINCT FROM p.new_value::double precision)",
        "        OR (p.column_name = 'geom' AND u.geom IS DISTINCT FROM",
        "            ST_SetSRID(ST_MakePoint(u.lon, u.lat), 4326));",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{LABEL}: % row(s) do not hold the new point', bad;",
        "    END IF;",
        "    -- invariant 2: the journal and the plan agree in both directions",
        f"    SELECT count(*) INTO bad FROM {t} p LEFT JOIN remediation_change_log l",
        f"        ON l.run_stamp = {sql_literal(stamp)} AND l.change_key = p.change_key",
        "       AND l.table_name = 'unified_sites' AND l.column_name = p.column_name",
        "       AND l.row_pk = p.site_id::text",
        "       AND l.old_value = p.old_value AND l.new_value = p.new_value",
        "     WHERE l.id IS NULL;",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{LABEL}: % row(s) have no matching journal row', bad;",
        "    END IF;",
        "    SELECT count(*) INTO bad FROM remediation_change_log l",
        f"     WHERE l.run_stamp = {sql_literal(stamp)}",
        f"       AND NOT EXISTS (SELECT 1 FROM {t} p WHERE p.change_key = l.change_key);",
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{LABEL}: this stamp journalled % row(s) outside the plan', bad;",
        "    END IF;",
        f"    RAISE NOTICE '{LABEL}: % row(s) changed and journalled', moved;",
        "END $$;",
        "",
        "ROLLBACK;" if rehearsal else "COMMIT;",
        "",
        "SELECT 'journal rows for this stamp' AS metric, count(*)::text AS value",
        f"  FROM remediation_change_log WHERE run_stamp = {sql_literal(stamp)};",
        "",
    ]
    return "\n".join(lines)


def statements(rows: Sequence[Change], wave: Wave = WAVE1) -> dict[str, str]:
    return {
        "APPLY.sql": render(rows, reversal=False, wave=wave),
        "REHEARSAL.sql": render(rows, reversal=False, rehearsal=True, wave=wave),
        "ROLLBACK.sql": render(rows, reversal=True, wave=wave),
    }


def assert_rendered(directory: Path, rows: Sequence[Change], wave: Wave = WAVE1) -> None:
    """Refuse a statement on disk that is not, byte for byte, the one `render` makes from the plan."""
    for name, sql in statements(rows, wave).items():
        path = directory / name
        if not path.exists():
            raise PlanError(f"{path} does not exist; run `plan` first")
        if path.read_text(encoding="utf-8") != sql:
            raise PlanError(
                f"{path} is not the statement this plan renders (edited by hand, or rendered from "
                "another plan); run `plan` again and read the diff"
            )


def plan_markdown(
    rows: Sequence[Change], verdicts: Sequence[Mapping[str, Any]], wave: Wave = WAVE1
) -> str:
    moves = sorted((v for v in verdicts if v["verdict"] == "move"), key=lambda v: -v["moved_km"])
    directory = f"output/remediation/bcases/{wave.plan_dir}"
    lines = [
        wave.title,
        "",
        f"{len(moves)} curated sites, {len(rows)} journalled changes (geom, lat, lon each), run stamp "
        f"`{wave.run_stamp}`. Rendered by `scripts/remediation/bcases/coord_plan.py` from "
        f"{wave.source}: two independent witnesses agree within the tolerance and the stored point "
        "lies outside it. **Not applied**: FIELD_CONTRACT section 4.6 reserves coordinate changes "
        "for the owner (HUMAN_ONLY B1/B2).",
        "",
        "Independent means: neither says it was imported from the other, neither is the other "
        "rounded or truncated to the grid its digits are written on (decimals, whole arcseconds or "
        "arcminutes), and the two points lie further apart than one arcsecond, one step of either "
        "grid and the Wikidata precision (`scripts/remediation/bcases/classify.py`, "
        "`independent`).",
        "",
    ]
    for note in wave.notes:
        lines += [note, ""]
    lines += [
        "| site | stored | new | moved | witnesses | reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for v in moves:
        witnesses = "<br>".join(
            f"[{label_of(w)}]({w['url']}) {w['quote']}"
            for w in v["witnesses"]
            if label_of(w) in v["agreeing"]
        )
        lines.append(
            f"| {v['name']} (`{v['site_id']}`) | {v['stored'][0]:.5f}, {v['stored'][1]:.5f} | "
            f"{v['new']['lat']:.5f}, {v['new']['lon']:.5f} | {v['moved_km']:.2f} km | {witnesses} | "
            f"{v['reason']} |"
        )
    run = "$PY scripts/remediation/bcases/run.py"
    lines += [
        "",
        "## How to run it (the orchestrator's job, in this order, after the owner's go)",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        f"{run} plan{wave.flag}     # REHEARSAL.sql is not versioned",
        f"{run} check{wave.flag}    # read-only: every old value still holds",
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        f'-v ON_ERROR_STOP=1" < {directory}/REHEARSAL.sql',
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        f'-v ON_ERROR_STOP=1" < {directory}/APPLY.sql',
        f"{run} verify{wave.flag}   # read-only: new values and the journal",
        "```",
        "",
    ]
    return "\n".join(lines)


def load_verdicts(out: Path, wave: Wave = WAVE1) -> list[dict[str, Any]]:
    return inputs.read_jsonl(out / wave.verdicts)


def wave_changes(out: Path, wave: Wave = WAVE1) -> list[Change]:
    """The wave's changes from its verdicts; a site an earlier wave planned is refused."""
    rows = changes(load_verdicts(out, wave))
    for earlier in wave.earlier:
        planned = {str(r["site_id"]) for r in inputs.read_jsonl(out / earlier / "PLAN.jsonl")}
        again = sorted({row.name for row in rows if row.site_id in planned})
        if again:
            raise PlanError(f"wave {wave.number} plans sites {earlier}/ already planned: {again}")
    return rows


def write_files(out: Path, wave: Wave = WAVE1) -> list[Change]:
    verdicts = load_verdicts(out, wave)
    rows = wave_changes(out, wave)
    if not rows:
        raise PlanError(f"{wave.verdicts} holds no move: wave {wave.number} has nothing to plan")
    directory = out / wave.plan_dir
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "PLAN.jsonl").write_text(
        "".join(row.to_json_line() + "\n" for row in rows), encoding="utf-8", newline="\n"
    )
    for name, sql in statements(rows, wave).items():
        (directory / name).write_text(sql, encoding="utf-8", newline="\n")
    (directory / "PLAN.md").write_text(
        plan_markdown(rows, verdicts, wave), encoding="utf-8", newline="\n"
    )
    return rows


def read_rows(
    rows: Sequence[Change], *, reader: Callable[[str], list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    """`{site_id: {lat, lon, geom, geom_is_point}}` of the planned sites, read-only."""
    ids = sorted({row.site_id for row in rows})
    for sid in ids:
        if not UUID_RE.match(sid):
            raise PlanError(f"{sid!r} is not a UUID")
    sql = (
        "SELECT u.id::text AS site_id, u.lat::text AS lat, u.lon::text AS lon, "
        "u.geom::text AS geom, "
        "(u.geom IS NOT DISTINCT FROM ST_SetSRID(ST_MakePoint(u.lon, u.lat), 4326)) AS geom_is_point "
        "FROM unified_sites u WHERE u.id IN ("
        + ", ".join(f"{sql_literal(i)}::uuid" for i in ids)
        + ")"
    )
    return {str(r["site_id"]): r for r in reader(sql)}


def compare(
    rows: Sequence[Change], found: Mapping[str, Mapping[str, Any]], *, want: str
) -> list[str]:
    """What differs from the plan's old values (`check`) or new values (`verify`)."""
    problems: list[str] = []
    for row in rows:
        live = found.get(row.site_id)
        if live is None:
            problems.append(f"{row.name}: the site is not in production")
            continue
        expected = row.old_value if want == "old" else row.new_value
        if row.column == "geom":
            if want == "old" and live["geom"] != expected:
                problems.append(f"{row.name} geom: expected {expected!r}, found {live['geom']!r}")
            if not live["geom_is_point"]:
                problems.append(f"{row.name} geom: not the point lat/lon names")
        elif float(live[row.column]) != float(expected):
            problems.append(
                f"{row.name} {row.column}: expected {expected}, found {live[row.column]}"
            )
    return problems


def run_readonly(
    command: str,
    out: Path,
    *,
    reader: Callable[[str], list[dict[str, Any]]] | None = None,
    wave: Wave = WAVE1,
) -> int:
    """`check` (the old values hold) or `verify` (the new values and the journal), read-only.

    The default reader is the mechanical lanes' (`psql_json_reader`: ssh to `prod_write.SSH_HOST`).
    """
    if command not in ("check", "verify"):
        raise PlanError(f"unknown command {command!r}")
    directory = out / wave.plan_dir
    rows = [
        Change(**{**r, "evidence": tuple(r["evidence"])})
        for r in inputs.read_jsonl(directory / "PLAN.jsonl")
    ]
    if rows != wave_changes(out, wave):
        raise PlanError("PLAN.jsonl is not the plan the verdicts render; run `plan` again")
    assert_rendered(directory, rows, wave)
    read = reader if reader is not None else psql_json_reader()
    problems = compare(
        rows, read_rows(rows, reader=read), want="old" if command == "check" else "new"
    )
    if command == "verify" and not problems:
        journal = read(
            "SELECT change_key FROM remediation_change_log WHERE run_stamp = "
            + sql_literal(wave.run_stamp)
        )
        keys = {str(r["change_key"]) for r in journal}
        if keys != {row.change_key for row in rows}:
            problems.append(
                f"journal holds {len(keys)} rows for {wave.run_stamp}, the plan {len(rows)}"
            )
    for problem in problems:
        print(f"  DEVIATION {problem}")
    print(f"{command}: {len(rows)} rows, {len(problems)} deviation(s)")
    return 1 if problems else 0
