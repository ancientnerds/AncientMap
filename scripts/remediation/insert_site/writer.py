"""D57 step 4: the insert's one transaction, its undo, and the mechanical lanes' write procedure.

`apply_remediation_change()` (migrations 0017/0018/0022) is a conditional UPDATE, so it cannot
create a row - the reason the image lane's INSERT has a writer of its own (`import_hero/
insert_writer.py`). This module is that pattern for a curated site: **no migration is needed**, the
journal's own columns carry an insert (one row per column written, `old_value` NULL, `new_value` read
back from the created row, `row_pk` the new row's key), and the row and its journal commit together.

    W="./.venv/Scripts/python.exe scripts/remediation/insert_site/run.py"
    $W emit              --run R --step 1    APPLY.sql, pinned to the plan (ROLLBACK.sql must exist)
    $W rehearse          --run R --step 1    APPLY.sql with COMMIT -> ROLLBACK, on production
    $W probe-guards      --run R --step 1    corrupted copies, each refused by its own guard
    $W apply             --run R --step 1    the one write, then the read-back
    $W readback          --run R --step 1    plan = journal = data, both ways (read-only)
    $W rehearse-rollback --run R --step 1    ROLLBACK.sql with COMMIT -> ROLLBACK, on the landed rows
    $W accept            --run R --step 1    the read-back at 0 deviations, recorded once

The exit codes are the shared writers' (`mechanical/apply.py`): 0 ok, 1 refused (nothing sent), 3 not
committed, 4 committed but psql did not finish cleanly, 5 outcome unknown (read the journal, never
retry), 6 committed but the read-back differs, 7 a rehearsal or a probe did not do what it must.

**The guards** (inside the transaction, before anything is written; each refusal names its guard,
which is how `probe-guards` tells that the right one refused):

1. no row of `unified_sites` holds a planned id or shares its 8-hex page prefix (the SSR route
   resolves a page by that prefix, `api/routes/sites_html.py`);
2. no curated row holds a planned `source_record_id` (`d57-<QID>`, unique per source);
3. no curated row holds the item or the article in `site_external_ids` (the site exists already);
4. no shown curated row carries the name's key, as its name or as one of its
   `unified_site_names`, within `plan.NAME_TWIN_METRES` (a possible D14 duplicate);
5. every planned name key is the key Postgres gives the name (`site_key_sql`);
6. every proposal the step closes still holds each value the plan read (and mirrors the same
   radar contribution);
7. a planned parent is a shown curated site of the child's country within 5 km at depth one (the
   D25 lane's invariants, `mechanical/lane.parent_invariants`, checked again after the write);
8. every radar contribution the step promotes still holds the values the plan read.

**The old-value guard rides on the write too.** `site_proposals` and `user_contributions` are no
target of `apply_remediation_change()`, so their UPDATEs carry what that function carries: every
value the plan read is part of the UPDATE's own `WHERE`, and the transaction raises unless the
UPDATE changed exactly the planned rows. A founder who approves or merges a proposal between guard 6
and the write therefore stops the insert instead of being overwritten, and the journal's `old_value`
(the plan's value) is the value the UPDATE replaced.

**The invariants** (after the writes, same transaction): each row stands with its planned values,
its key, its point and its bucket label, and has a page (`curated_page`); its two `field_prov`
markers hash the values they describe; each site has exactly its planned names and ids; each closed
proposal is `approved` and names the site; each mirrored radar contribution is `promoted` and names
the site (`api/routes/proposals.py:_mirror_contribution`); the parent invariants hold; and the
journal holds exactly the planned rows per site.

**The undo is a retirement, never a DELETE** (`ancient_nerds` is a protected source). `ROLLBACK.sql`
moves each site `in_scope -> retired` and its reason to the undo's, through
`apply_remediation_change()` - the scope lanes' own write path - under the stamp
`<run stamp>-rollback`, and puts each closed proposal and each promoted radar contribution back to
the values the plan read (locked first, then restored only from the values the insert wrote, the
row count checked). The site's
names and ids stay with the retired row: a retired site is hidden everywhere but kept for matching
(migration 0020), so the Prospector does not propose it again. Running it is a decision, never
automatic: `ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map
-v ON_ERROR_STOP=1" < ROLLBACK.sql`, then `readback --rollback`.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import apply as MA  # noqa: E402 - the transport, the exit codes, the rehearsal
from mechanical.field_prov import COORD, PERIOD, SPECS, _kinds_sql, _stale  # noqa: E402
from mechanical.lane import (  # noqa: E402
    LOCK_TIMEOUT,
    PARENT_METRES,
    STATEMENT_TIMEOUT,
    bucket_case,
    parent_invariants,
    sql_literal,
)
from mechanical.plan import psql_json_reader  # noqa: E402
from prod_write import OutcomeUnknown, pin_line  # noqa: E402

from insert_site import candidates as C  # noqa: E402
from insert_site import plan as P  # noqa: E402
from pipeline.lyra.site_key import site_key_sql  # noqa: E402
from pipeline.utils.public_sites import RETIRED, curated_page, not_retired  # noqa: E402

APPLY_FILE, ROLLBACK_FILE, ACCEPTED_FILE = "APPLY.sql", "ROLLBACK.sql", "ACCEPTED.json"
INSERTED_FILE = "INSERTED_SITES.txt"
PROBES_DIR = "probes"
GEOM = "geom"
READBACK_LABEL = "journal rows for this run"
PIN_RE = re.compile(r"(?m)^-- plan sha256 ([0-9a-f]{64})\s*$")

#: What each guard says when it refuses, after `<stamp>: <count> `. `probe-guards` counts a probe as
#: proven only when psql's error carries its own guard's text.
GUARD_SAYS = {
    1: "planned site(s) share an id or a page prefix with an existing row",
    2: "planned site(s) carry a source_record_id a curated row holds",
    3: "planned site(s) name an item or an article a curated row holds",
    4: f"planned site(s) carry the name key of a shown curated site within {P.NAME_TWIN_METRES} m",
    5: "planned name(s) do not carry the key Postgres gives them",
    6: "planned proposal(s) no longer hold the values the plan read",
    7: (
        "planned site(s) name a parent that is not a shown curated site of their country within "
        f"{PARENT_METRES} m at depth one"
    ),
    8: "planned radar contribution(s) no longer hold the values the plan read",
}
#: What the old-value check on a write says: the UPDATE changed fewer rows than planned, because a
#: row no longer held the values the plan read when the UPDATE reached it.
WRITE_SAYS = {
    "proposals": "planned proposal(s) changed between their guard and their write",
    "contributions": "planned radar contribution(s) changed between their guard and their write",
}
INVARIANT_SAYS = {
    "rows": "inserted site(s) do not stand as planned",
    "markers": "inserted site(s) hold a provenance marker that does not hash its value",
    "names": "inserted site(s) do not hold exactly their planned names",
    "ids": "inserted site(s) do not hold exactly their planned external ids",
    "proposals": "closed proposal(s) do not name the inserted site as approved",
    "contributions": "promoted radar contribution(s) do not name the inserted site",
    "parents": "inserted site(s) break a parent invariant",
    "journal": "inserted site(s) do not have exactly their planned journal rows",
}
UNDO_SAYS = {
    1: "planned site(s) no longer hold the scope the insert wrote",
    2: "planned proposal(s) no longer hold what the insert wrote",
    3: "planned radar contribution(s) no longer hold what the insert wrote",
    "rows": "undone site(s) are not retired with the reason of the undo",
    "proposals": "restored proposal(s) do not hold the values the plan read",
    "contributions": "restored radar contribution(s) do not hold the values the plan read",
    "journal": "the undo did not journal exactly its planned rows",
}
UNDO_WRITE_SAYS = {
    "proposals": "planned proposal(s) changed between their guard and their restore",
    "contributions": "planned radar contribution(s) changed between their guard and their restore",
}


class WriterError(ValueError):
    """A statement that must not be sent or trusted. Nothing was sent when this is raised."""


# ------------------------------------------------------------------------------------ rendering
def _lit(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return P.pg_float(value)
    return sql_literal(str(value))


def _json(value: Any) -> str:
    return sql_literal(json.dumps(value, ensure_ascii=False, sort_keys=True)) + "::jsonb"


def review_notes(step: P.Step, site_id: str) -> str:
    """What a closed proposal's `review_notes` say: the lane, the decision and the row it promoted."""
    return json.dumps(
        {"lane": C.LANE, "decision": "D57", "run_stamp": step.run_stamp, "site_id": site_id},
        sort_keys=True,
    )


def _site_rows(inserts: Sequence[P.Insert]) -> list[str]:
    rows = []
    for seq, i in enumerate(inserts, start=1):
        rows.append(
            "    ("
            + ", ".join(
                [
                    str(seq),
                    f"{_lit(i.site_id)}::uuid",
                    _lit(i.qid),
                    _lit(i.source_record_id),
                    _lit(i.name),
                    _lit(i.name_key),
                    f"{_lit(i.lat)}::double precision",
                    f"{_lit(i.lon)}::double precision",
                    _lit(i.site_type),
                    f"{_lit(i.period_start)}::integer",
                    _lit(i.period_name),
                    _lit(i.country),
                    _lit(i.source_url),
                    _lit(i.enwiki_title),
                    _json(i.raw_data),
                    _lit(i.scope_reason),
                    f"{_lit(i.parent_site_id)}::uuid",
                    _lit(i.change_key),
                    _json(i.evidence),
                    str(i.journal_rows),
                ]
            )
            + ")"
        )
    return rows


def _name_rows(inserts: Sequence[P.Insert]) -> list[str]:
    rows = []
    seq = 0
    for i in inserts:
        for n in i.names:
            seq += 1
            rows.append(
                f"    ({seq}, {_lit(i.site_id)}::uuid, {_lit(n['name'])}, {_lit(n['name_key'])}, "
                f"{_lit(n['name_type'])})"
            )
    return rows


def _ext_rows(inserts: Sequence[P.Insert]) -> list[str]:
    return [
        f"    ({_lit(i.site_id)}::uuid, {_lit(x['kind'])}, {_lit(x['value'])})"
        for i in inserts
        for x in i.external_ids
    ]


def _proposal_rows(step: P.Step, inserts: Sequence[P.Insert]) -> list[str]:
    rows = []
    for i in inserts:
        for p in i.proposals:
            old = p["old"]
            rows.append(
                f"    ({_lit(p['proposal_id'])}::uuid, {_lit(i.site_id)}::uuid, "
                f"{_lit(review_notes(step, i.site_id))}, "
                + ", ".join(_lit(old[c]) for c in P.PROPOSAL_COLUMNS)
                + f", {_lit(p['contribution_id'])}, {_lit(i.change_key)})"
            )
    return rows


def _contribution_rows(inserts: Sequence[P.Insert]) -> list[str]:
    rows = []
    for i in inserts:
        for p in i.proposals:
            c = p["contribution"]
            if c is None:
                continue
            old = c["old"]
            rows.append(
                f"    ({_lit(c['contribution_id'])}::uuid, {_lit(i.site_id)}::uuid, "
                f"{_lit(old['enrichment_status'])}, "
                f"{_lit(old['promoted_site_id'])}, {_lit(i.change_key)})"
            )
    return rows


#: The columns of the row, each as the journal records it: read back from the created row.
SITE_JOURNAL = (
    ("id", "u.id::text"),
    ("source_id", "u.source_id"),
    ("source_record_id", "u.source_record_id"),
    ("name", "u.name"),
    ("name_normalized", "u.name_normalized"),
    ("lat", "u.lat::text"),
    ("lon", "u.lon::text"),
    ("geom", "ST_AsEWKT(u.geom)"),
    ("site_type", "u.site_type"),
    ("period_start", "u.period_start::text"),
    ("period_name", "u.period_name"),
    ("country", "u.country"),
    ("source_url", "u.source_url"),
    ("edited_by", "u.edited_by"),
    ("raw_data", "u.raw_data::text"),
    ("scope_status", "u.scope_status"),
    ("scope_reason", "u.scope_reason"),
    ("updated_at", "u.updated_at::text"),
    ("parent_site_id", "u.parent_site_id::text"),
)

_PROPOSAL_TEMP = (
    "    proposal_id       UUID NOT NULL,\n"
    "    site_id           UUID NOT NULL,\n"
    "    review_notes      TEXT NOT NULL,\n"
    "    old_status        TEXT NOT NULL,\n"
    "    old_promoted      TEXT,\n"
    "    old_reviewed_by   TEXT,\n"
    "    old_reviewed_at   TEXT,\n"
    "    old_review_notes  TEXT,\n"
    "    old_updated_at    TEXT NOT NULL,\n"
    "    contribution_id   TEXT,\n"
    "    change_key        TEXT NOT NULL"
)
_CONTRIBUTION_TEMP = (
    "    contribution_id       UUID NOT NULL UNIQUE,\n"
    "    site_id               UUID NOT NULL,\n"
    "    old_enrichment_status TEXT,\n"
    "    old_promoted          TEXT,\n"
    "    change_key            TEXT NOT NULL"
)


#: A refusal's text is spliced into a RAISE literal: no quote (it would end the literal), no `%`
#: (it would read as a placeholder and take an argument) - `mechanical/lane.py`'s `_LABEL` rule.
_SAYS = re.compile(r"^[A-Za-z0-9 _/(),.-]+\Z")


def _raise(stamp: str, says: str) -> str:
    if not _SAYS.match(says):
        raise WriterError(f"{says!r} cannot stand in a RAISE literal")
    return f"RAISE EXCEPTION '%: % {says}', {_lit(stamp)}, bad;"


def _guard(stamp: str, number: int, sql: str) -> str:
    return (
        f"    -- guard {number}\n"
        f"    SELECT count(*) INTO bad FROM ({sql}) g;\n"
        f"    IF bad > 0 THEN\n        {_raise(stamp, GUARD_SAYS[number])}\n    END IF;\n"
    )


def _check(stamp: str, says: str, sql: str) -> str:
    return (
        f"    SELECT count(*) INTO bad FROM ({sql}) g;\n"
        f"    IF bad > 0 THEN\n        {_raise(stamp, says)}\n    END IF;\n"
    )


def _old(column: str) -> str:
    """The temp table's column that holds a proposal column's value as the plan read it."""
    return {"promoted_site_id": "old_promoted"}.get(column, f"old_{column}")


def _written(stamp: str, says: str, table: str, journal_per_row: int) -> str:
    """After a `WITH upd AS (UPDATE ...) INSERT INTO remediation_change_log ...`: raise unless the
    UPDATE changed every row of `table` (each changed row journals `journal_per_row` rows)."""
    return (
        "    GET DIAGNOSTICS written = ROW_COUNT;\n"
        f"    bad := (SELECT count(*) FROM {table}) - written / {journal_per_row};\n"
        f"    IF bad <> 0 THEN\n        {_raise(stamp, says)}\n    END IF;\n"
    )


def proposal_held(sp: str = "sp", q: str = "q") -> str:
    """The proposal still holds every value the plan read, and mirrors the same contribution: the
    UPDATE's own old-value condition (guard 6 is its negation)."""
    return " AND ".join(
        [f"{sp}.{c}::text IS NOT DISTINCT FROM {q}.{_old(c)}" for c in P.PROPOSAL_COLUMNS]
        + [f"{sp}.contribution_id::text IS NOT DISTINCT FROM {q}.contribution_id"]
    )


def contribution_held(uc: str = "uc", c: str = "c") -> str:
    """The radar contribution still holds the values the plan read (guard 8 is its negation)."""
    return (
        f"{uc}.enrichment_status::text IS NOT DISTINCT FROM {c}.old_enrichment_status AND "
        f"{uc}.promoted_site_id::text IS NOT DISTINCT FROM {c}.old_promoted"
    )


def proposal_written(sp: str = "sp", q: str = "q") -> str:
    """The proposal holds what the insert wrote (the undo's guard 2 and its restore's condition)."""
    return (
        f"{sp}.status = 'approved' AND {sp}.promoted_site_id IS NOT DISTINCT FROM {q}.site_id AND "
        f"{sp}.reviewed_by IS NOT DISTINCT FROM {_lit(P.REVIEWED_BY)} AND {sp}.review_notes IS NOT "
        f"DISTINCT FROM {q}.review_notes"
    )


def contribution_written(uc: str = "uc", c: str = "c") -> str:
    """The contribution holds what the insert wrote (the undo's guard 3 and its restore's condition)."""
    return (
        f"{uc}.enrichment_status IS NOT DISTINCT FROM {_lit(P.PROMOTED)} AND "
        f"{uc}.promoted_site_id IS NOT DISTINCT FROM {c}.site_id"
    )


_JOURNAL = (
    "INSERT INTO remediation_change_log\n"
    "        (run_stamp, test_id, table_name, column_name, row_pk, old_value, new_value,\n"
    "         change_key, confidence, evidence, site_id_ref)"
)
_LO = "(left(replace(p.site_id::text, '-', ''), 8) || '-0000-0000-0000-000000000000')::uuid"
_HI = "(left(replace(p.site_id::text, '-', ''), 8) || '-ffff-ffff-ffff-ffffffffffff')::uuid"


def _metres(a: str, b: str) -> str:
    return f"ST_DistanceSphere(ST_MakePoint({a}.lon, {a}.lat), ST_MakePoint({b}.lon, {b}.lat))"


def apply_guards() -> dict[int, str]:
    """Each guard's query over the plan's temp tables: a row for every planned row it refuses."""
    curated = sql_literal(P.CURATED)
    return {
        1: f"SELECT p.site_id FROM _ins_site p JOIN unified_sites u ON u.id >= {_LO} AND u.id <= {_HI}",
        2: (
            "SELECT p.site_id FROM _ins_site p JOIN unified_sites u ON u.source_id = "
            f"{curated} AND u.source_record_id = p.source_record_id"
        ),
        3: (
            "SELECT p.site_id FROM _ins_site p JOIN site_external_ids e ON (e.kind = "
            "'wikidata_qid' AND e.value = p.qid) OR (e.kind = 'enwiki_title' AND e.value = "
            f"p.enwiki_title) JOIN unified_sites u ON u.id = e.site_id AND u.source_id = {curated}"
        ),
        4: (
            f"SELECT p.site_id FROM _ins_site p JOIN unified_sites u ON u.source_id = {curated} "
            f"AND {not_retired('u')} AND {P.twin_predicate('u', 'p.name_key')} "
            f"AND {_metres('u', 'p')} <= {P.NAME_TWIN_METRES}"
        ),
        5: (
            "SELECT n.seq FROM _ins_name n WHERE n.name_key IS DISTINCT FROM "
            f"{site_key_sql('n.name')}"
        ),
        6: (
            "SELECT q.proposal_id FROM _ins_prop q LEFT JOIN site_proposals sp ON sp.id = "
            "q.proposal_id WHERE sp.id IS NULL OR sp.status IN ('approved', 'merged') OR NOT "
            f"({proposal_held()})"
        ),
        7: (
            "SELECT p.site_id FROM _ins_site p LEFT JOIN unified_sites s ON s.id = "
            "p.parent_site_id WHERE p.parent_site_id IS NOT NULL AND (s.id IS NULL OR "
            f"s.source_id <> {curated} OR s.scope_status IS NOT DISTINCT FROM "
            f"{sql_literal(RETIRED)} OR s.parent_site_id IS NOT NULL OR s.country IS DISTINCT "
            f"FROM p.country OR {_metres('s', 'p')} > {PARENT_METRES})"
        ),
        8: (
            "SELECT c.contribution_id FROM _ins_contrib c LEFT JOIN user_contributions uc ON "
            f"uc.id = c.contribution_id WHERE uc.id IS NULL OR uc.enrichment_status IS NOT "
            f"DISTINCT FROM {_lit(P.PROMOTED)} OR NOT ({contribution_held()})"
        ),
    }


def apply_invariants(stamp: str) -> dict[str, str]:
    """Each invariant's query after the writes: a row for every planned row that breaks it."""
    st = _lit(stamp)
    row_breaks = " OR ".join(
        [
            "u.id IS NULL",
            f"NOT ({curated_page('u')})",
            "u.source_record_id IS DISTINCT FROM p.source_record_id",
            "u.name IS DISTINCT FROM p.name",
            "u.name_normalized IS DISTINCT FROM p.name_key",
            f"u.name_normalized IS DISTINCT FROM {site_key_sql('u.name')}",
            "u.lat IS DISTINCT FROM p.lat",
            "u.lon IS DISTINCT FROM p.lon",
            "u.geom IS NULL",
            "NOT ST_Equals(u.geom, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326))",
            "u.site_type IS DISTINCT FROM p.site_type",
            "u.period_start IS DISTINCT FROM p.period_start",
            "u.period_name IS DISTINCT FROM p.period_name",
            f"u.period_name IS DISTINCT FROM {bucket_case('u.period_start')}",
            "u.country IS DISTINCT FROM p.country",
            "u.source_url IS DISTINCT FROM p.source_url",
            "u.raw_data IS DISTINCT FROM p.raw_data",
            f"u.scope_status IS DISTINCT FROM {_lit(P.IN_SCOPE)}",
            "u.scope_reason IS DISTINCT FROM p.scope_reason",
            "u.parent_site_id IS DISTINCT FROM p.parent_site_id",
            "u.description IS NOT NULL",
            "u.thumbnail_url IS NOT NULL",
        ]
    )
    markers = " OR ".join(
        f"NOT (u.raw_data ? '{SPECS[k].key}') OR (u.raw_data -> '{SPECS[k].key}' ->> 'kind') "
        f"NOT IN ({_kinds_sql(SPECS[k])}) OR ({_stale(SPECS[k], 'u.')})"
        for k in (PERIOD, COORD)
    )
    parent_bad = " OR ".join(f"({inv.predicate})" for inv in parent_invariants())
    return {
        "rows": (
            "SELECT p.site_id FROM _ins_site p LEFT JOIN unified_sites u ON u.id = p.site_id "
            f"WHERE {row_breaks}"
        ),
        "markers": (
            "SELECT p.site_id FROM _ins_site p JOIN unified_sites u ON u.id = p.site_id "
            f"WHERE {markers}"
        ),
        "names": (
            "SELECT n.seq FROM _ins_name n LEFT JOIN unified_site_names x ON x.site_id = "
            "n.site_id AND x.name = n.name AND x.name_normalized = n.name_key AND x.name_type = "
            "n.name_type AND x.language_code IS NULL WHERE x.id IS NULL UNION ALL SELECT p.seq "
            "FROM _ins_site p WHERE (SELECT count(*) FROM unified_site_names x WHERE x.site_id = "
            "p.site_id) <> (SELECT count(*) FROM _ins_name n WHERE n.site_id = p.site_id)"
        ),
        "ids": (
            "SELECT x.site_id FROM _ins_ext x LEFT JOIN site_external_ids e ON e.site_id = "
            "x.site_id AND e.kind = x.kind AND e.value = x.value WHERE e.site_id IS NULL UNION "
            "ALL SELECT p.site_id FROM _ins_site p WHERE (SELECT count(*) FROM site_external_ids "
            "e WHERE e.site_id = p.site_id) <> (SELECT count(*) FROM _ins_ext x WHERE x.site_id "
            "= p.site_id)"
        ),
        "proposals": (
            "SELECT q.proposal_id FROM _ins_prop q LEFT JOIN site_proposals sp ON sp.id = "
            "q.proposal_id WHERE sp.id IS NULL OR sp.status <> 'approved' OR sp.promoted_site_id "
            f"IS DISTINCT FROM q.site_id OR sp.reviewed_by IS DISTINCT FROM {_lit(P.REVIEWED_BY)} "
            "OR sp.review_notes IS DISTINCT FROM q.review_notes"
        ),
        "contributions": (
            "SELECT c.contribution_id FROM _ins_contrib c LEFT JOIN user_contributions uc ON "
            f"uc.id = c.contribution_id WHERE uc.id IS NULL OR NOT ({contribution_written()})"
        ),
        "parents": (
            "SELECT p.site_id FROM _ins_site p JOIN unified_sites u ON u.id = p.site_id WHERE "
            f"p.parent_site_id IS NOT NULL AND ({parent_bad})"
        ),
        "journal": (
            "SELECT p.site_id FROM _ins_site p LEFT JOIN (SELECT site_id_ref, count(*) AS n FROM "
            f"remediation_change_log WHERE run_stamp = {st} GROUP BY site_id_ref) l ON "
            "l.site_id_ref = p.site_id WHERE COALESCE(l.n, 0) <> p.journal_rows UNION ALL SELECT "
            f"l.site_id_ref FROM remediation_change_log l WHERE l.run_stamp = {st} AND "
            "l.site_id_ref NOT IN (SELECT site_id FROM _ins_site)"
        ),
    }


def _values_block(table: str, rows: Sequence[str]) -> str:
    """`INSERT INTO <table> VALUES ...;`, or nothing for no rows (a VALUES list cannot be empty)."""
    if not rows:
        return ""
    return f"INSERT INTO {table} VALUES\n" + ",\n".join(rows) + ";\n"


def render_apply(step: P.Step) -> str:
    """APPLY.sql: the guards, the writes and their journal, the invariants - one transaction."""
    if not step.inserts:
        raise WriterError("refusing to render a transaction with no site")
    stamp = step.run_stamp
    st = _lit(stamp)
    test, conf = _lit(P.TEST_ID), _lit(P.CONFIDENCE)
    guards = "".join(_guard(stamp, n, sql) for n, sql in apply_guards().items())
    checks = "".join(
        f"    -- invariant: {name}\n" + _check(stamp, INVARIANT_SAYS[name], sql)
        for name, sql in apply_invariants(stamp).items()
    )
    site_values = ",\n".join(f"            ({_lit(c)}, {e})" for c, e in SITE_JOURNAL)
    proposals = _values_block("_ins_prop", _proposal_rows(step, step.inserts))
    contributions = _values_block("_ins_contrib", _contribution_rows(step.inserts))
    sites = _values_block("_ins_site", _site_rows(step.inserts))
    names = _values_block("_ins_name", _name_rows(step.inserts))
    ext = _values_block("_ins_ext", _ext_rows(step.inserts))
    key_p, key_n = site_key_sql("p.name"), site_key_sql("n.name")
    return f"""-- Generated by scripts/remediation/insert_site/writer.py - do not edit by hand.
{pin_line(step.digest)}
-- lane {C.LANE!r} (D57), {len(step.inserts)} site(s) to create; run stamp {stamp!r}.
-- Every row is created together with its journal rows inside this transaction; the undo is
-- ROLLBACK.sql, a retirement (never a DELETE: ancient_nerds is a protected source).
\\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '{LOCK_TIMEOUT}';
SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}';

CREATE TEMP TABLE _ins_site (
{_SITE_TEMP}
) ON COMMIT DROP;
{sites}
CREATE TEMP TABLE _ins_name (
    seq               INTEGER PRIMARY KEY,
    site_id           UUID NOT NULL,
    name              TEXT NOT NULL,
    name_key          TEXT NOT NULL,
    name_type         TEXT NOT NULL
) ON COMMIT DROP;
{names}
CREATE TEMP TABLE _ins_ext (
    site_id           UUID NOT NULL,
    kind              TEXT NOT NULL,
    value             TEXT NOT NULL
) ON COMMIT DROP;
{ext}
CREATE TEMP TABLE _ins_prop (
{_PROPOSAL_TEMP}
) ON COMMIT DROP;
{proposals}
CREATE TEMP TABLE _ins_contrib (
{_CONTRIBUTION_TEMP}
) ON COMMIT DROP;
{contributions}
DO $$
DECLARE
    bad     integer;
    written integer;
BEGIN
{guards}
    -- the rows
    INSERT INTO unified_sites
        (id, source_id, source_record_id, name, name_normalized, lat, lon, geom, site_type,
         period_start, period_name, country, source_url, edited_by, raw_data, scope_status,
         scope_reason, updated_at, parent_site_id)
    SELECT p.site_id, {_lit(P.CURATED)}, p.source_record_id, p.name, {key_p}, p.lat, p.lon,
           ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326), p.site_type, p.period_start,
           p.period_name, p.country, p.source_url, {_lit(P.EDITED_BY)}, p.raw_data,
           {_lit(P.IN_SCOPE)}, p.scope_reason, now(), p.parent_site_id
      FROM _ins_site p ORDER BY p.seq;

    -- their journal: one row per written column, read back from the created row
    {_JOURNAL}
    SELECT {st}, {test}, 'unified_sites', t.col, u.id::text, NULL, t.val,
           p.change_key || ':' || t.col, {conf}, p.evidence, u.id
      FROM _ins_site p JOIN unified_sites u ON u.id = p.site_id
     CROSS JOIN LATERAL (VALUES
{site_values}
           ) AS t(col, val)
     WHERE t.val IS NOT NULL;

    -- the names: the label, and the aliases of the closed proposals
    WITH ins AS (
        INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
        SELECT n.site_id, n.name, {key_n}, n.name_type FROM _ins_name n ORDER BY n.seq
        RETURNING id, site_id, name, name_normalized, name_type)
    {_JOURNAL}
    SELECT {st}, {test}, 'unified_site_names', t.col, ins.id::text, NULL, t.val,
           p.change_key || ':name:' || ins.id::text || ':' || t.col, {conf}, p.evidence,
           ins.site_id
      FROM ins JOIN _ins_site p ON p.site_id = ins.site_id
     CROSS JOIN LATERAL (VALUES ('site_id', ins.site_id::text), ('name', ins.name),
                                ('name_normalized', ins.name_normalized),
                                ('name_type', ins.name_type)) AS t(col, val);

    -- the external ids: the item and the article (the Prospector's rung 0)
    WITH ins AS (
        INSERT INTO site_external_ids (site_id, kind, value)
        SELECT x.site_id, x.kind, x.value FROM _ins_ext x
        RETURNING site_id, kind, value)
    {_JOURNAL}
    SELECT {st}, {test}, 'site_external_ids', 'value', ins.site_id::text || '|' || ins.kind,
           NULL, ins.value, p.change_key || ':ext:' || ins.kind, {conf}, p.evidence, ins.site_id
      FROM ins JOIN _ins_site p ON p.site_id = ins.site_id;

    -- the proposals the insert closes (D57: approved, with promoted_site_id), each only while it
    -- holds every value the plan read - the old-value guard of apply_remediation_change()
    WITH upd AS (
        UPDATE site_proposals sp
           SET status = 'approved', promoted_site_id = q.site_id,
               reviewed_by = {_lit(P.REVIEWED_BY)}, reviewed_at = now(),
               review_notes = q.review_notes, updated_at = now()
          FROM _ins_prop q
         WHERE sp.id = q.proposal_id
           AND {proposal_held()}
        RETURNING sp.id, sp.status, sp.promoted_site_id, sp.reviewed_by, sp.reviewed_at,
                  sp.review_notes, sp.updated_at, q.site_id AS for_site, q.old_status,
                  q.old_promoted, q.old_reviewed_by, q.old_reviewed_at, q.old_review_notes,
                  q.old_updated_at)
    {_JOURNAL}
    SELECT {st}, {test}, 'site_proposals', t.col, upd.id::text, t.old, t.val,
           p.change_key || ':proposal:' || upd.id::text || ':' || t.col, {conf}, p.evidence,
           upd.for_site
      FROM upd JOIN _ins_site p ON p.site_id = upd.for_site
     CROSS JOIN LATERAL (VALUES
            ('status', upd.old_status, upd.status),
            ('promoted_site_id', upd.old_promoted, upd.promoted_site_id::text),
            ('reviewed_by', upd.old_reviewed_by, upd.reviewed_by),
            ('reviewed_at', upd.old_reviewed_at, upd.reviewed_at::text),
            ('review_notes', upd.old_review_notes, upd.review_notes),
            ('updated_at', upd.old_updated_at, upd.updated_at::text)) AS t(col, old, val);
{_written(stamp, WRITE_SAYS["proposals"], "_ins_prop", len(P.PROPOSAL_COLUMNS))}
    -- the radar contributions those proposals mirror: promoted with the site, as
    -- POST /api/proposals/{{id}}/approve does (_mirror_contribution), under the same guard
    WITH upd AS (
        UPDATE user_contributions uc
           SET enrichment_status = {_lit(P.PROMOTED)}, promoted_site_id = c.site_id
          FROM _ins_contrib c
         WHERE uc.id = c.contribution_id
           AND {contribution_held()}
        RETURNING uc.id, uc.enrichment_status, uc.promoted_site_id, c.site_id AS for_site,
                  c.old_enrichment_status, c.old_promoted)
    {_JOURNAL}
    SELECT {st}, {test}, 'user_contributions', t.col, upd.id::text, t.old, t.val,
           p.change_key || ':contribution:' || upd.id::text || ':' || t.col, {conf}, p.evidence,
           upd.for_site
      FROM upd JOIN _ins_site p ON p.site_id = upd.for_site
     CROSS JOIN LATERAL (VALUES
            ('enrichment_status', upd.old_enrichment_status, upd.enrichment_status::text),
            ('promoted_site_id', upd.old_promoted, upd.promoted_site_id::text)) AS t(col, old, val);
{_written(stamp, WRITE_SAYS["contributions"], "_ins_contrib", len(P.CONTRIBUTION_COLUMNS))}
{checks}END $$;

SELECT '{READBACK_LABEL}', count(*)::text FROM remediation_change_log WHERE run_stamp = {st};
SELECT 'planned sites', count(*)::text FROM _ins_site;
COMMIT;
"""


_SITE_TEMP = (
    "    seq               INTEGER PRIMARY KEY,\n"
    "    site_id           UUID NOT NULL UNIQUE,\n"
    "    qid               TEXT NOT NULL UNIQUE,\n"
    "    source_record_id  TEXT NOT NULL,\n"
    "    name              TEXT NOT NULL,\n"
    "    name_key          TEXT NOT NULL,\n"
    "    lat               DOUBLE PRECISION NOT NULL,\n"
    "    lon               DOUBLE PRECISION NOT NULL,\n"
    "    site_type         TEXT,\n"
    "    period_start      INTEGER,\n"
    "    period_name       TEXT NOT NULL,\n"
    "    country           TEXT NOT NULL,\n"
    "    source_url        TEXT NOT NULL,\n"
    "    enwiki_title      TEXT NOT NULL,\n"
    "    raw_data          JSONB NOT NULL,\n"
    "    scope_reason      TEXT NOT NULL,\n"
    "    parent_site_id    UUID,\n"
    "    change_key        TEXT NOT NULL,\n"
    "    evidence          JSONB NOT NULL,\n"
    "    journal_rows      INTEGER NOT NULL"
)


def retire_reason(step: P.Step) -> str:
    return (
        f"D57 insert undone ({step.rollback_stamp}): retired, never deleted - ancient_nerds is a "
        "protected source"
    )


def undo_checks(stamp: str, planned: int) -> dict[Any, str]:
    """The undo's guards (1, 2) and invariants, each a query with a row for every refusal."""
    restored = " OR ".join(f"sp.{c}::text IS DISTINCT FROM q.{_old(c)}" for c in P.PROPOSAL_COLUMNS)
    return {
        1: (
            "SELECT p.site_id FROM _ins_undo p LEFT JOIN unified_sites u ON u.id = p.site_id "
            f"WHERE u.id IS NULL OR u.source_id <> {_lit(P.CURATED)} OR u.scope_status IS "
            f"DISTINCT FROM {_lit(P.IN_SCOPE)} OR u.scope_reason IS DISTINCT FROM p.scope_reason"
        ),
        2: (
            "SELECT q.proposal_id FROM _ins_prop q LEFT JOIN site_proposals sp ON sp.id = "
            f"q.proposal_id WHERE sp.id IS NULL OR NOT ({proposal_written()})"
        ),
        3: (
            "SELECT c.contribution_id FROM _ins_contrib c LEFT JOIN user_contributions uc ON "
            f"uc.id = c.contribution_id WHERE uc.id IS NULL OR NOT ({contribution_written()})"
        ),
        "rows": (
            "SELECT p.site_id FROM _ins_undo p LEFT JOIN unified_sites u ON u.id = p.site_id "
            f"WHERE u.scope_status IS DISTINCT FROM {_lit(RETIRED)} OR u.scope_reason IS "
            "DISTINCT FROM p.retire_reason"
        ),
        "proposals": (
            "SELECT q.proposal_id FROM _ins_prop q JOIN site_proposals sp ON sp.id = "
            f"q.proposal_id WHERE {restored}"
        ),
        "contributions": (
            "SELECT c.contribution_id FROM _ins_contrib c JOIN user_contributions uc ON uc.id = "
            f"c.contribution_id WHERE NOT ({contribution_held()})"
        ),
        "journal": (
            "SELECT 1 FROM (SELECT count(*) AS n FROM remediation_change_log WHERE run_stamp = "
            f"{_lit(stamp)}) c WHERE c.n <> {planned}"
        ),
    }


def render_rollback(step: P.Step) -> str:
    """ROLLBACK.sql: each site `in_scope -> retired` through `apply_remediation_change()`, each
    closed proposal back to the values the plan read - one transaction, journalled."""
    if not step.inserts:
        raise WriterError("refusing to render a reversal with no site")
    stamp = step.rollback_stamp
    st = _lit(stamp)
    test, conf = _lit(P.TEST_ID), _lit(P.CONFIDENCE)
    undo_rows = [
        f"    ({seq}, {_lit(i.site_id)}::uuid, {_lit(i.scope_reason)}, "
        f"{_lit(retire_reason(step))}, {_lit(i.change_key)}, {_json(i.evidence)})"
        for seq, i in enumerate(step.inserts, start=1)
    ]
    proposal_rows = _proposal_rows(step, step.inserts)
    contribution_rows = _contribution_rows(step.inserts)
    planned = (
        2 * len(step.inserts)
        + len(P.PROPOSAL_COLUMNS) * len(proposal_rows)
        + len(P.CONTRIBUTION_COLUMNS) * len(contribution_rows)
    )
    checks = undo_checks(stamp, planned)
    guards = "".join(
        f"    -- guard {n}\n" + _check(stamp, UNDO_SAYS[n], checks[n]) for n in (1, 2, 3)
    )
    invariants = "".join(
        f"    -- invariant: {n}\n" + _check(stamp, UNDO_SAYS[n], checks[n])
        for n in ("rows", "proposals", "contributions", "journal")
    )
    undo = _values_block("_ins_undo", undo_rows)
    proposals = _values_block("_ins_prop", proposal_rows)
    contributions = _values_block("_ins_contrib", contribution_rows)
    retired = _lit(RETIRED)
    in_scope = _lit(P.IN_SCOPE)
    return f"""-- Generated by scripts/remediation/insert_site/writer.py - do not edit by hand.
{pin_line(step.digest)}
-- The undo of lane {C.LANE!r} (D57), run stamp {step.run_stamp!r}: {len(step.inserts)} site(s)
-- retired (never deleted - ancient_nerds is a protected source), {len(proposal_rows)} proposal(s)
-- and {len(contribution_rows)} radar contribution(s) restored. Journalled under {stamp!r}.
-- Running it is a decision, never automatic.
\\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '{LOCK_TIMEOUT}';
SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}';

CREATE TEMP TABLE _ins_undo (
    seq               INTEGER PRIMARY KEY,
    site_id           UUID NOT NULL UNIQUE,
    scope_reason      TEXT NOT NULL,
    retire_reason     TEXT NOT NULL,
    change_key        TEXT NOT NULL,
    evidence          JSONB NOT NULL
) ON COMMIT DROP;
{undo}
CREATE TEMP TABLE _ins_prop (
{_PROPOSAL_TEMP}
) ON COMMIT DROP;
{proposals}
CREATE TEMP TABLE _ins_contrib (
{_CONTRIBUTION_TEMP}
) ON COMMIT DROP;
{contributions}
DO $$
DECLARE
    bad     integer;
    written integer;
    r       RECORD;
BEGIN
    -- the rows the undo restores, locked before they are judged: the journal reads their values
    -- before the restore, and nobody may change them in between
    PERFORM 1 FROM site_proposals sp JOIN _ins_prop q ON q.proposal_id = sp.id
      ORDER BY sp.id FOR UPDATE OF sp;
    PERFORM 1 FROM user_contributions uc JOIN _ins_contrib c ON c.contribution_id = uc.id
      ORDER BY uc.id FOR UPDATE OF uc;
{guards}
    -- the retirement, through the scope lanes' one write path
    FOR r IN SELECT * FROM _ins_undo ORDER BY seq LOOP
        PERFORM apply_remediation_change('unified_sites', 'scope_status', 'id', r.site_id::text,
            {in_scope}, {retired}, {test}, {st}, r.change_key || ':undo:scope_status',
            {conf}, r.evidence, r.site_id);
        PERFORM apply_remediation_change('unified_sites', 'scope_reason', 'id', r.site_id::text,
            r.scope_reason, r.retire_reason, {test}, {st}, r.change_key || ':undo:scope_reason',
            {conf}, r.evidence, r.site_id);
    END LOOP;

    -- the proposals, back to the values the plan read (the table is no target of
    -- apply_remediation_change(), so the restore journals itself, from the rows before and after)
    WITH before AS (
        SELECT sp.id, sp.status, sp.promoted_site_id::text AS promoted, sp.reviewed_by,
               sp.reviewed_at::text AS reviewed_at, sp.review_notes,
               sp.updated_at::text AS updated_at
          FROM site_proposals sp JOIN _ins_prop q ON q.proposal_id = sp.id),
    upd AS (
        UPDATE site_proposals sp
           SET status = q.old_status, promoted_site_id = q.old_promoted::uuid,
               reviewed_by = q.old_reviewed_by, reviewed_at = q.old_reviewed_at::timestamptz,
               review_notes = q.old_review_notes, updated_at = q.old_updated_at::timestamptz
          FROM _ins_prop q
         WHERE sp.id = q.proposal_id
           AND {proposal_written()}
        RETURNING sp.id, sp.status, sp.promoted_site_id::text AS promoted, sp.reviewed_by,
                  sp.reviewed_at::text AS reviewed_at, sp.review_notes,
                  sp.updated_at::text AS updated_at, q.site_id AS for_site, q.change_key)
    {_JOURNAL}
    SELECT {st}, {test}, 'site_proposals', t.col, upd.id::text, t.old, t.val,
           upd.change_key || ':undo:proposal:' || upd.id::text || ':' || t.col, {conf},
           u.evidence, upd.for_site
      FROM upd JOIN before b ON b.id = upd.id JOIN _ins_undo u ON u.site_id = upd.for_site
     CROSS JOIN LATERAL (VALUES
            ('status', b.status, upd.status), ('promoted_site_id', b.promoted, upd.promoted),
            ('reviewed_by', b.reviewed_by, upd.reviewed_by),
            ('reviewed_at', b.reviewed_at, upd.reviewed_at),
            ('review_notes', b.review_notes, upd.review_notes),
            ('updated_at', b.updated_at, upd.updated_at)) AS t(col, old, val);
{_written(stamp, UNDO_WRITE_SAYS["proposals"], "_ins_prop", len(P.PROPOSAL_COLUMNS))}
    -- the radar contributions, back to the values the plan read
    WITH upd AS (
        UPDATE user_contributions uc
           SET enrichment_status = c.old_enrichment_status, promoted_site_id = c.old_promoted::uuid
          FROM _ins_contrib c
         WHERE uc.id = c.contribution_id
           AND {contribution_written()}
        RETURNING uc.id, uc.enrichment_status, uc.promoted_site_id::text AS promoted,
                  c.site_id AS for_site, c.change_key)
    {_JOURNAL}
    SELECT {st}, {test}, 'user_contributions', t.col, upd.id::text, t.old, t.val,
           upd.change_key || ':undo:contribution:' || upd.id::text || ':' || t.col, {conf},
           u.evidence, upd.for_site
      FROM upd JOIN _ins_undo u ON u.site_id = upd.for_site
     CROSS JOIN LATERAL (VALUES
            ('enrichment_status', {_lit(P.PROMOTED)}, upd.enrichment_status::text),
            ('promoted_site_id', upd.for_site::text, upd.promoted)) AS t(col, old, val);
{_written(stamp, UNDO_WRITE_SAYS["contributions"], "_ins_contrib", len(P.CONTRIBUTION_COLUMNS))}
{invariants}END $$;

SELECT '{READBACK_LABEL}', count(*)::text FROM remediation_change_log WHERE run_stamp = {st};
COMMIT;
"""


def code_of(sql: str) -> str:
    """The statement as code: every `-- comment` dropped to its line end and every `'literal'`
    blanked to `''`, in one pass (a quote inside a comment opens no literal, `--` inside a literal
    opens no comment). The literals carry web quotes (`raw_data`, `evidence`), and a quote that says
    DELETE is text, not a statement (`gallery_audit/chunk_writer.py`'s rule)."""
    out: list[str] = []
    i, end = 0, len(sql)
    while i < end:
        ch = sql[i]
        if ch == "-" and sql.startswith("--", i):
            stop = sql.find("\n", i)
            i = end if stop < 0 else stop
        elif ch == "'":
            j = i + 1
            while True:
                j = sql.find("'", j)
                if j < 0:
                    raise WriterError("the statement holds an unterminated literal")
                if sql.startswith("''", j):
                    j += 2
                    continue
                break
            out.append("''")
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def lint(sql: str, kind: str) -> None:
    """Refuse anything but this lane's two shapes (`import_hero/insert.lint_statement`'s rules),
    judged on the code (`code_of`): neither a comment nor a quoted text can trip or pass it."""
    if kind not in ("apply", "rollback"):
        raise WriterError(f"unknown statement kind {kind!r}")
    code = code_of(sql)
    begins = re.findall(r"(?im)^BEGIN;\s*$", code)
    commits = list(re.finditer(r"(?im)^COMMIT;\s*$", code))
    if len(begins) != 1 or len(commits) != 1:
        raise WriterError(
            f"the statement must open and close one transaction: {len(begins)} BEGIN, "
            f"{len(commits)} COMMIT"
        )
    for forbidden in (r"DELETE", r"TRUNCATE", r"DROP\s+TABLE", r"ALTER\s+TABLE"):
        if re.search(rf"\b{forbidden}\b", code, re.IGNORECASE):
            raise WriterError(f"{forbidden} is not a statement this lane may make")
    inserting = re.search(r"\bINSERT\s+INTO\s+unified_sites\b", code) is not None
    if kind == "apply" and not inserting:
        raise WriterError("the statement creates no unified_sites row")
    if kind == "rollback":
        if inserting:
            raise WriterError("an undo creates no row")
        if (
            "apply_remediation_change('unified_sites', 'scope_status'" not in sql
            or "PERFORM apply_remediation_change(''" not in code
        ):
            raise WriterError("the undo retires through apply_remediation_change()")
    if "remediation_change_log" not in code[: commits[0].start()]:
        raise WriterError("the statement journals nothing before its COMMIT")


def render_checked(step: P.Step) -> tuple[str, str]:
    """APPLY.sql and ROLLBACK.sql rendered and linted, before any file of the step is written:
    `run.py plan` calls it first, so a statement the lint refuses leaves no plan behind."""
    apply_sql, rollback_sql = render_apply(step), render_rollback(step)
    lint(apply_sql, "apply")
    lint(rollback_sql, "rollback")
    return apply_sql, rollback_sql


# ------------------------------------------------------------------------------------ the files
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_rollback(step: P.Step, target: Path) -> Path:
    sql = render_rollback(step)
    lint(sql, "rollback")
    path = target / ROLLBACK_FILE
    path.write_text(sql, encoding="utf-8", newline="\n")
    return path


def emit(target: Path) -> dict[str, Any]:
    """APPLY.sql of a planned step - refused unless ROLLBACK.sql exists and is this plan's undo."""
    step = P.load_step(target)
    rollback = target / ROLLBACK_FILE
    if not rollback.is_file():
        raise WriterError(f"{rollback} does not exist: the undo is written before the write")
    if _read(rollback) != render_rollback(step):
        raise WriterError(f"{rollback} is not the undo this plan renders - edited or stale")
    sql = render_apply(step)
    lint(sql, "apply")
    (target / APPLY_FILE).write_text(sql, encoding="utf-8", newline="\n")
    return {"apply": str(target / APPLY_FILE), "digest": step.digest, "sites": len(step.inserts)}


def check_delivered(target: Path) -> P.Step:
    """The files on disk are exactly what the plan renders, pinned to it, or nothing is sent."""
    step = P.load_step(target)
    for name, render, kind in (
        (APPLY_FILE, render_apply, "apply"),
        (ROLLBACK_FILE, render_rollback, "rollback"),
    ):
        path = target / name
        if not path.is_file():
            raise WriterError(f"{path} does not exist")
        text = _read(path)
        pin = PIN_RE.search(text)
        if pin is None or pin.group(1) != step.digest:
            raise WriterError(f"{path} is not pinned to this plan (plan sha256 {step.digest})")
        if text != render(step):
            raise WriterError(f"{path} is not the statement its plan renders - refusing to send")
        lint(text, kind)
    return step


# ------------------------------------------------------------------------------------ production
def journal_count(stamp: str) -> int:
    return MA.journal_count(stamp)


def _reader():
    return psql_json_reader(read_only=True)


def _ids(step: P.Step) -> str:
    return ", ".join(f"{_lit(i.site_id)}::uuid" for i in step.inserts)


def readback(step: P.Step, *, read=None) -> list[str]:
    """Every difference between the plan, the journal and the data. Empty means confirmed."""
    read = read or _reader()
    ids = _ids(step)
    rows = {
        str(r["id"]): r
        for r in read(
            "SELECT u.id::text AS id, u.source_id, u.source_record_id, u.name, u.name_normalized, "
            "u.lat, u.lon, ST_X(u.geom) AS gx, ST_Y(u.geom) AS gy, ST_SRID(u.geom) AS srid, "
            "u.site_type, u.period_start, u.period_name, "
            "u.country, u.source_url, u.edited_by, u.raw_data, u.scope_status, u.scope_reason, "
            f"u.parent_site_id::text AS parent_site_id FROM unified_sites u WHERE u.id IN ({ids})"
        )
    }
    names = read(
        "SELECT site_id::text AS site_id, name, name_normalized, name_type, language_code "
        f"FROM unified_site_names WHERE site_id IN ({ids})"
    )
    ext = read(
        f"SELECT site_id::text AS site_id, kind, value FROM site_external_ids WHERE site_id IN ({ids})"
    )
    proposal_ids = [p["proposal_id"] for i in step.inserts for p in i.proposals]
    props = (
        {
            str(r["id"]): r
            for r in read(
                "SELECT id::text AS id, status, promoted_site_id::text AS promoted_site_id, "
                "reviewed_by, review_notes FROM site_proposals WHERE id IN ("
                + ", ".join(f"{_lit(x)}::uuid" for x in proposal_ids)
                + ")"
            )
        }
        if proposal_ids
        else {}
    )
    contribution_ids = [c["contribution_id"] for i in step.inserts for c in i.contributions]
    contribs = (
        {
            str(r["id"]): r
            for r in read(
                "SELECT id::text AS id, enrichment_status, promoted_site_id::text AS "
                "promoted_site_id FROM user_contributions WHERE id IN ("
                + ", ".join(f"{_lit(x)}::uuid" for x in contribution_ids)
                + ")"
            )
        }
        if contribution_ids
        else {}
    )
    journal = read(
        "SELECT site_id_ref::text AS site_id, table_name, column_name, new_value, test_id, "
        f"confidence FROM remediation_change_log WHERE run_stamp = {_lit(step.run_stamp)}"
    )
    problems: list[str] = []
    by_site: dict[str, list[Mapping[str, Any]]] = {}
    for row in journal:
        by_site.setdefault(str(row["site_id"]), []).append(row)
    for i in step.inserts:
        held = rows.get(i.site_id)
        if held is None:
            problems.append(f"{i.qid}: no row holds {i.site_id}")
            continue
        for column, want in i.site_columns().items():
            if column == GEOM:
                continue  # compared as a point below: PostGIS prints its own digits
            got = held.get(column)
            got_text = (
                P.pg_float(got) if isinstance(got, float) else (None if got is None else str(got))
            )
            if got_text != want:
                problems.append(f"{i.qid}: {column} is {got_text!r}, the plan wrote {want!r}")
        if (held.get("gx"), held.get("gy"), held.get("srid")) != (i.lon, i.lat, 4326):
            problems.append(
                f"{i.qid}: geom is {held.get('gx')}, {held.get('gy')} (SRID {held.get('srid')}), "
                f"not the point {i.lat}, {i.lon}"
            )
        if held.get("raw_data") != i.raw_data:
            problems.append(f"{i.qid}: raw_data is not the planned provenance")
        mine_names = sorted(
            (n["name"], n["name_normalized"], n["name_type"], n["language_code"])
            for n in names
            if n["site_id"] == i.site_id
        )
        want_names = sorted((n["name"], n["name_key"], n["name_type"], None) for n in i.names)
        if mine_names != want_names:
            problems.append(f"{i.qid}: names {mine_names} are not the planned {want_names}")
        mine_ext = sorted((x["kind"], x["value"]) for x in ext if x["site_id"] == i.site_id)
        if mine_ext != sorted((x["kind"], x["value"]) for x in i.external_ids):
            problems.append(f"{i.qid}: external ids {mine_ext} are not the planned ones")
        for p in i.proposals:
            got = props.get(p["proposal_id"])
            if (
                got is None
                or got["status"] != "approved"
                or got["promoted_site_id"] != i.site_id
                or got["review_notes"] != review_notes(step, i.site_id)
            ):
                problems.append(f"{i.qid}: proposal {p['proposal_id']} is {got}")
        for c in i.contributions:
            held_c = contribs.get(c["contribution_id"])
            if (
                held_c is None
                or held_c["enrichment_status"] != P.PROMOTED
                or held_c["promoted_site_id"] != i.site_id
            ):
                problems.append(f"{i.qid}: radar contribution {c['contribution_id']} is {held_c}")
        logged = by_site.get(i.site_id, [])
        if len(logged) != i.journal_rows:
            problems.append(
                f"{i.qid}: the journal holds {len(logged)} row(s), the plan writes {i.journal_rows}"
            )
        for row in logged:
            if row["test_id"] != P.TEST_ID or row["confidence"] != P.CONFIDENCE:
                problems.append(
                    f"{i.qid}: a journal row carries {row['test_id']}/{row['confidence']}"
                )
            if row["table_name"] == "unified_sites" and row["column_name"] != GEOM:
                want = i.site_columns().get(str(row["column_name"]))
                if want is not None and row["new_value"] != want:
                    problems.append(
                        f"{i.qid}: the journal says {row['column_name']} is {row['new_value']!r}, "
                        f"the plan wrote {want!r}"
                    )
    extra = sorted(set(by_site) - {i.site_id for i in step.inserts})
    if extra:
        problems.append(f"{len(extra)} site(s) outside the plan carry the stamp: {extra[:5]}")
    return problems


def rollback_readback(step: P.Step, *, read=None) -> list[str]:
    """After a committed undo: every site retired with the undo's reason, every proposal restored."""
    read = read or _reader()
    rows = read(
        "SELECT id::text AS id, scope_status, scope_reason FROM unified_sites WHERE id IN ("
        + _ids(step)
        + ")"
    )
    problems = [
        f"{r['id']}: {r['scope_status']} / {r['scope_reason']}"
        for r in rows
        if r["scope_status"] != RETIRED or r["scope_reason"] != retire_reason(step)
    ]
    if len(rows) != len(step.inserts):
        problems.append(f"{len(rows)} of {len(step.inserts)} planned rows exist")
    proposals = [p for i in step.inserts for p in i.proposals]
    if proposals:
        held = {
            str(r["id"]): r
            for r in read(
                "SELECT id::text AS id, "
                + ", ".join(f"{c}::text AS {c}" for c in P.PROPOSAL_COLUMNS)
                + " FROM site_proposals WHERE id IN ("
                + ", ".join(f"{_lit(p['proposal_id'])}::uuid" for p in proposals)
                + ")"
            )
        }
        for p in proposals:
            got = held.get(p["proposal_id"])
            if got is None or any(got[c] != p["old"][c] for c in P.PROPOSAL_COLUMNS):
                problems.append(f"proposal {p['proposal_id']} is {got}, not {p['old']}")
    contributions = [c for i in step.inserts for c in i.contributions]
    if contributions:
        held = {
            str(r["id"]): r
            for r in read(
                "SELECT id::text AS id, enrichment_status, promoted_site_id::text AS "
                "promoted_site_id FROM user_contributions WHERE id IN ("
                + ", ".join(f"{_lit(c['contribution_id'])}::uuid" for c in contributions)
                + ")"
            )
        }
        for c in contributions:
            got = held.get(c["contribution_id"])
            if got is None or any(got[k] != c["old"][k] for k in P.CONTRIBUTION_COLUMNS):
                problems.append(
                    f"radar contribution {c['contribution_id']} is {got}, not {c['old']}"
                )
    return problems


def _ran_as_rehearsal(stdout: str) -> bool:
    return READBACK_LABEL in stdout and "ROLLBACK" in stdout and "COMMIT" not in stdout


def rehearsal_of(sql: str, what: str) -> str:
    return MA._before_the_one_commit(sql, what) + "\nROLLBACK;\n"


def _send_rehearsal(sql: str, what: str) -> tuple[int, str, str]:
    proc = MA.run_psql(rehearsal_of(sql, what), check=False)
    return proc.returncode, proc.stdout, proc.stderr


def command_rehearse(target: Path) -> int:
    step = check_delivered(target)
    code, out, err = _send_rehearsal(_read(target / APPLY_FILE), APPLY_FILE)
    print(out)
    if code != 0 or not _ran_as_rehearsal(out):
        print(err, file=sys.stderr)
        print(f"REHEARSAL FAILED: psql exit {code}")
        return MA.EXIT_PROBE_FAILED
    left = journal_count(step.run_stamp)
    if left:
        print(f"REHEARSAL FAILED: {left} journal row(s) of {step.run_stamp!r} survived it")
        return MA.EXIT_PROBE_FAILED
    print(f"REHEARSAL OK: {len(step.inserts)} site(s), rolled back")
    return MA.EXIT_OK


def command_rehearse_rollback(target: Path) -> int:
    """ROLLBACK.sql rehearsed against the landed write: its guards must pass on the real rows."""
    step = check_delivered(target)
    if journal_count(step.run_stamp) != sum(i.journal_rows for i in step.inserts):
        raise WriterError("the write has not landed: the undo is rehearsed on the landed rows")
    code, out, err = _send_rehearsal(_read(target / ROLLBACK_FILE), ROLLBACK_FILE)
    print(out)
    if code != 0 or not _ran_as_rehearsal(out):
        print(err, file=sys.stderr)
        print(f"ROLLBACK REHEARSAL FAILED: psql exit {code}")
        return MA.EXIT_PROBE_FAILED
    problems = readback(step)
    if problems or journal_count(step.rollback_stamp):
        print("ROLLBACK REHEARSAL FAILED: the landed write differs after the rehearsal:")
        for problem in problems[:20]:
            print(f"  {problem}")
        return MA.EXIT_PROBE_FAILED
    print("ROLLBACK REHEARSAL OK: the undo ran on the landed rows and was rolled back")
    return MA.EXIT_OK


def _unknown(step: P.Step, detail: str) -> OutcomeUnknown:
    planned = sum(i.journal_rows for i in step.inserts)
    return OutcomeUnknown(
        f"{detail} Before any retry: wait until {MA.OPEN_SESSIONS_SQL} lists no session of this "
        f"write, then count the journal rows of {step.run_stamp!r}: the step landed only if they "
        f"are {planned}, and nothing was written if they are 0."
    )


def settle(step: P.Step, what: str, *, session_ended: bool) -> int:
    """After a timeout or a failed exit: say from the journal what happened, never retry."""
    planned = sum(i.journal_rows for i in step.inserts)
    try:
        count = journal_count(step.run_stamp)
    except (OutcomeUnknown, MA.PlanError) as exc:
        raise _unknown(step, f"{what}; the journal could not be read either ({exc}).") from exc
    if count == 0 and session_ended:
        print(f"NOT COMMITTED: {what}; the journal holds 0 rows for {step.run_stamp!r}.")
        return MA.EXIT_NOT_COMMITTED
    if count != planned:
        raise _unknown(step, f"{what}; the journal holds {count} of {planned} rows.")
    print(f"COMMITTED: {what}, but the journal holds all {count} rows. Reading it back:")
    problems = readback(step)
    if problems:
        return _unconfirmed(problems)
    print("APPLY LANDED: the read-back matches the plan; psql did not finish cleanly.")
    return MA.EXIT_COMMITTED_UNCLEAN


def _unconfirmed(problems: Sequence[str]) -> int:
    print("COMMITTED BUT NOT CONFIRMED: the write is in the database, but its read-back differs:")
    for problem in problems:
        print(f"  {problem}")
    return MA.EXIT_COMMITTED_UNCONFIRMED


def command_apply(target: Path) -> int:
    step = check_delivered(target)
    already = journal_count(step.run_stamp)
    if already:
        raise WriterError(
            f"run stamp {step.run_stamp!r} already journals {already} row(s): the step has landed "
            "or something else wrote under its stamp - run readback; never apply twice"
        )
    try:
        proc = MA.run_psql(_read(target / APPLY_FILE), check=False)
    except OutcomeUnknown as exc:
        return settle(step, f"psql timed out ({exc})", session_ended=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return settle(
            step,
            f"psql exited {proc.returncode}",
            session_ended=proc.returncode == MA.PSQL_SCRIPT_ERROR,
        )
    try:
        problems = readback(step)
    except (OutcomeUnknown, MA.PlanError) as exc:
        return _unconfirmed([f"the read-back could not run: {exc}"])
    if problems:
        return _unconfirmed(problems)
    print(f"APPLY OK: {len(step.inserts)} site(s); the read-back matches plan and journal")
    return MA.EXIT_OK


def command_readback(target: Path, *, rollback: bool = False) -> int:
    step = check_delivered(target)
    problems = rollback_readback(step) if rollback else readback(step)
    if problems:
        print("READBACK FAILED:")
        for problem in problems:
            print(f"  {problem}")
        return MA.EXIT_COMMITTED_UNCONFIRMED
    print(f"READBACK OK: {len(step.inserts)} site(s)" + (" retired" if rollback else ""))
    return MA.EXIT_OK


# ------------------------------------------------------------------------------------ the probes
def probe_cases(step: P.Step) -> list[tuple[int, P.Step]]:
    """One corrupted copy of the step per guard, each made to fail exactly that guard, from rows
    the plan read (`step.probe`: a shown curated site with an item and no parent, a retired one).
    The first site carries the corruption; the copies are rehearsed, never applied."""
    shown, retired = step.probe.get("shown"), step.probe.get("retired")
    if shown is None or retired is None:
        raise WriterError("the plan read no probe rows (a shown and a retired curated site)")
    first = step.inserts[0]
    bad_key = first.names[0]["name_key"] + " (not the key)"
    cases: list[tuple[int, P.Insert]] = [
        (1, replace(first, site_id=str(shown["site_id"]))),
        (2, replace(first, source_record_id=str(shown["source_record_id"]))),
        (3, replace(first, qid=str(shown["qid"]))),
        (
            4,
            replace(
                first,
                name=str(shown["name"]),
                name_key=str(shown["name_normalized"]),
                lat=float(shown["lat"]),
                lon=float(shown["lon"]),
            ),
        ),
        # guard 5 reads `_ins_name` only, which renders from `names`: the label's key is corrupted
        # there, while `Insert.name_key` (`_ins_site`, guard 4's input) keeps its true key
        (5, replace(first, names=[{**first.names[0], "name_key": bad_key}, *first.names[1:]])),
        (7, replace(first, parent_site_id=str(retired["site_id"]))),
    ]
    proposal_holder = next((i for i in step.inserts if i.proposals), None)
    out = [(n, replace(step, inserts=[i, *step.inserts[1:]])) for n, i in cases]
    if proposal_holder is not None:
        p = proposal_holder.proposals[0]
        moved = [{**p, "old": {**p["old"], "status": "rejected"}}, *proposal_holder.proposals[1:]]
        others = [
            i if i is not proposal_holder else replace(i, proposals=moved) for i in step.inserts
        ]
        out.append((6, replace(step, inserts=others)))
    contribution_holder = next((i for i in step.inserts if i.contributions), None)
    if contribution_holder is not None:
        # production holds no promoted_site_id on a contribution the plan promotes (`plan._proposals`
        # refuses one that names a site), so a shown site's id is a value it never holds
        k = next(n for n, p in enumerate(contribution_holder.proposals) if p["contribution"])
        p = contribution_holder.proposals[k]
        c = p["contribution"]
        corrupted = {
            **p,
            "contribution": {**c, "old": {**c["old"], "promoted_site_id": str(shown["site_id"])}},
        }
        moved = [
            *contribution_holder.proposals[:k],
            corrupted,
            *contribution_holder.proposals[k + 1 :],
        ]
        others = [
            i if i is not contribution_holder else replace(i, proposals=moved) for i in step.inserts
        ]
        out.append((8, replace(step, inserts=others)))
    return sorted(out, key=lambda c: c[0])


def command_probe_guards(target: Path) -> int:
    """Each corrupted copy is rehearsed and must be refused by its own guard (its text in psql's
    error); a probe refused by another guard, or not at all, proves nothing and fails the run."""
    step = check_delivered(target)
    probes = target / PROBES_DIR
    probes.mkdir(exist_ok=True)
    failed = []
    for number, corrupted in probe_cases(step):
        sql = render_apply(corrupted)
        (probes / f"guard-{number}.sql").write_text(sql, encoding="utf-8", newline="\n")
        code, out, err = _send_rehearsal(sql, f"probe {number}")
        own = GUARD_SAYS[number] in err
        print(
            f"guard {number}: psql exit {code}, {'refused by its guard' if own else 'NOT PROVEN'}"
        )
        if code == 0 or not own:
            failed.append(number)
            print(err, file=sys.stderr)
    if journal_count(step.run_stamp):
        print(f"PROBES FAILED: journal rows of {step.run_stamp!r} survived")
        return MA.EXIT_PROBE_FAILED
    if failed:
        print(f"PROBES FAILED: guard(s) {failed} did not refuse their own probe")
        return MA.EXIT_PROBE_FAILED
    print(f"PROBES OK: {len(probe_cases(step))} guard(s), each refused its own probe")
    return MA.EXIT_OK


# ------------------------------------------------------------------------------------ the acceptance
def accept(target: Path, *, read=None) -> dict[str, Any]:
    """The read-back at 0 deviations, recorded once (`ACCEPTED.json`), and the site list the
    follow-up lanes take (`INSERTED_SITES.txt`, one id per line)."""
    step = check_delivered(target)
    accepted = target / ACCEPTED_FILE
    if accepted.exists():
        raise WriterError(f"{accepted} exists: a step is accepted once")
    problems = readback(step, read=read)
    result = {
        "run_stamp": step.run_stamp,
        "digest": step.digest,
        "sites": len(step.inserts),
        "journal_rows": sum(i.journal_rows for i in step.inserts),
        "deviations": len(problems),
        "problems": problems,
    }
    if problems:
        return {"accepted": False, **result}
    C.write_json(
        accepted, {**result, "accepted_at": datetime.now(UTC).isoformat(timespec="seconds")}
    )
    (target / INSERTED_FILE).write_text(
        "".join(f"{i.site_id}\n" for i in step.inserts), encoding="utf-8", newline="\n"
    )
    return {"accepted": True, **result}
