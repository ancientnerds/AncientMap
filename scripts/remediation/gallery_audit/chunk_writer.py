"""The shared writer of the image lanes: planned rows in chunks of 100 sites, every row journalled.

Every image lane (liveness, attribution, the gallery verdicts, hero re-derivation, the thumbnail
repoint) ends in the same thing: a set of planned `(table, column, row, old value, new value)`
changes that must reach production through `apply_remediation_change()` (migrations
0017/0018/0022), conditioned on the old value, with a journal row, a rollback and a read-back. This
module is that path, once, so no lane writes its own.

A lane builds `Change` records and calls `emit_chunks`. Each chunk is one directory:

    chunk-NNN/CHUNK.json    the lane identity, the chunk number, the run stamp, the sites the
                            chunk may leave without a live image
    chunk-NNN/PLAN.jsonl    one record per planned row
    chunk-NNN/ROLLBACK.sql  the reversal - written before the write, never after
    chunk-NNN/APPLY.sql     the write: one transaction

Both statements carry `-- plan sha256 <digest>` of CHUNK.json + PLAN.jsonl, and every command
re-renders them from those two files and refuses to send a byte that differs.

The production steps, per chunk and in this order (owner rule 2026-09-21, PIECE6_BRIEF section 7):

    chunk_writer.py <chunk dir> --check              offline: the files are the plan's, 0 DELETE
    chunk_writer.py <chunk dir> --rehearse           APPLY.sql with COMMIT -> ROLLBACK
    chunk_writer.py <chunk dir> --apply              the write, then the two-way read-back
    chunk_writer.py <chunk dir> --readback           read-only: plan <-> journal <-> data
    chunk_writer.py <chunk dir> --rehearse-rollback  ROLLBACK.sql with COMMIT -> ROLLBACK, run
                                                     against the post-apply state

What the transaction proves before it commits: every planned site is curated, every planned image
row lives on the site the plan names, every row still holds its planned old value; exactly the
planned number of rows moved; each holds its new value; the journal and the plan agree row for row
in both directions; at most one hero per touched site (`hero_repair.apply.one_hero_invariant_sql`,
the hero repair's own check in its at-most form); no hero on an excluded row; every touched site
that had a live image still has one unless the chunk names it; every image kind is in 0019's
vocabulary. Any deviation raises, and ON_ERROR_STOP ends the script before its COMMIT.

The production transport, the timeout rule, the digest, the rehearsal transform, the row reader
and the SQL literal are `persist_verdicts`'s (itself built on `prod_write`): a timeout is
`OutcomeUnknown`, never a plain failure, and an outcome is settled from the journal - never by a
retry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT / "scripts" / "remediation", _HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import persist_verdicts as pv  # noqa: E402
from hero_repair.apply import LABEL_RE, one_hero_invariant_sql  # noqa: E402
from mechanical.apply import OPEN_SESSIONS_SQL, PSQL_SCRIPT_ERROR  # noqa: E402
from mechanical.plan import UUID_RE  # noqa: E402
from persist_verdicts import OutcomeUnknown  # noqa: E402
from prod_write import pin_line  # noqa: E402

from pipeline.lyra.site_key import site_key_sql  # noqa: E402  (repo root: mechanical.apply)

CURATED_SOURCE = "ancient_nerds"
SITES_PER_CHUNK = 100
KEY_COLUMN = "id"
PLAN_TABLE = "_img_plan"

#: Every column an image lane may write, and the text form its values take. The journal primitive
#: allows whole tables; this is the narrower list the image lanes were designed for (design entry
#: 7, "MAPPING TO WRITES"). A value is compared in its text form (`column::text`), so a boolean is
#: 'true'/'false' and an integer its decimal digits - exactly what PostgreSQL prints.
WRITABLE: dict[tuple[str, str], str] = {
    ("wiki_images", "is_excluded"): "boolean",
    ("wiki_images", "is_hero"): "boolean",
    ("wiki_images", "image_kind"): "text",
    ("wiki_images", "author"): "text",
    ("wiki_images", "author_url"): "text",
    ("wiki_images", "commons_page_url"): "text",
    ("wiki_images", "original_url"): "text",
    ("wiki_images", "filename"): "text",
    ("wiki_images", "width"): "integer",
    ("wiki_images", "height"): "integer",
    ("wiki_images", "file_size_bytes"): "integer",
    ("unified_sites", "thumbnail_url"): "text",
    # The match keys (Phase 6 item 2, scripts/remediation/name_key/plan.py): each written value
    # must be the key Postgres derives from its row's name at write time (guard 2c).
    ("unified_sites", "name_normalized"): "text",
    ("unified_site_names", "name_normalized"): "text",
}
#: The key type of each table, so a key is compared in its own type and the primary-key index is
#: used (the reason migration 0022 exists).
KEY_TYPES = {"wiki_images": "integer", "unified_sites": "uuid", "unified_site_names": "integer"}
#: The tables whose rows carry a name the match key is derived from, and the alias guard 2c reads
#: them under.
NAME_KEY_TABLES = {"unified_sites": "s", "unified_site_names": "n"}
#: 0017's confidence vocabulary.
CONFIDENCES = frozenset({"authoritative", "two_source", "weak", "unverifiable"})

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]*")

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_NOT_COMMITTED = 3
EXIT_COMMITTED_UNCLEAN = 4
EXIT_UNKNOWN = 5
EXIT_COMMITTED_UNCONFIRMED = 6
EXIT_REHEARSAL_FAILED = 7

READBACK_LABEL = "journal rows for this run"


class ChunkError(pv.PersistError):
    """A chunk that must not be written, sent or trusted. Nothing was sent when this is raised."""


# ---------------------------------------------------------------------------------- the model
@dataclass(frozen=True)
class Lane:
    """Who writes: the journal identity every chunk of one lane carries."""

    name: str
    test_id: str
    stamp: str
    confidence: str
    label: str

    def __post_init__(self) -> None:
        for what, value in (("name", self.name), ("stamp", self.stamp)):
            if not TOKEN_RE.fullmatch(value):
                raise ChunkError(f"lane {what} {value!r} is not a lower-case token")
        if self.confidence not in CONFIDENCES:
            raise ChunkError(f"confidence {self.confidence!r} is not one of {sorted(CONFIDENCES)}")
        if not LABEL_RE.fullmatch(self.label) or not LABEL_RE.fullmatch(self.test_id):
            raise ChunkError("a lane label or test id must stand inside a quoted RAISE message")


@dataclass(frozen=True)
class Change:
    """One planned row: what it holds now, what it will hold, why, and the pointers that prove it."""

    table: str
    column: str
    row_key: str
    site_id: str
    old_value: str | None
    new_value: str | None
    rule: str
    reason: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Chunk:
    lane: Lane
    number: int
    changes: tuple[Change, ...]
    #: Sites this chunk may leave without a live image (an exclusion of a site's last image).
    #: Every other touched site that had one must still have one when the chunk commits.
    may_empty: frozenset[str] = frozenset()

    @property
    def run_stamp(self) -> str:
        return f"{self.lane.stamp}-{self.number:03d}"

    @property
    def rollback_stamp(self) -> str:
        return f"{self.run_stamp}-rollback"

    @property
    def sites(self) -> list[str]:
        return sorted({c.site_id for c in self.changes})


def change_key(lane: Lane, change: Change, *, rollback: bool = False) -> str:
    """The journal's identity for one row's write (or its reversal)."""
    kind = f"{lane.name}-rollback" if rollback else lane.name
    return f"{kind}:{change.table}.{change.column}:{change.row_key}"


#: Characters no planned value may carry: the C0 controls, DEL, the C1 controls (U+0085 among
#: them) and the Unicode line and paragraph separators. Together they are every character
#: `str.splitlines()` breaks a line at, and `json.dumps(..., ensure_ascii=False)` writes U+0085,
#: U+2028 and U+2029 raw - a value carrying one would split its own PLAN.jsonl record (measured
#: 2026-09-23: the chunk then failed its check with a JSONDecodeError).
LINE_BREAKERS = frozenset({"\u2028", "\u2029"})


def has_control(value: str) -> bool:
    """True when `value` carries a control character or a Unicode line separator."""
    return any(ord(ch) < 32 or 127 <= ord(ch) <= 159 or ch in LINE_BREAKERS for ch in value)


def _no_control(value: str, *, what: str) -> None:
    if has_control(value):
        raise ChunkError(f"{what} carries a control character: {value!r}")


def validate_change(change: Change) -> None:
    """Refuse a change the writer cannot express exactly. Raises; never repairs."""
    kind = WRITABLE.get((change.table, change.column))
    if kind is None:
        raise ChunkError(
            f"{change.table}.{change.column} is not a column the image lanes write "
            f"(allowed: {sorted(f'{t}.{c}' for t, c in WRITABLE)})"
        )
    if not UUID_RE.fullmatch(change.site_id):
        raise ChunkError(f"site_id {change.site_id!r} is not a lower-case UUID")
    if KEY_TYPES[change.table] == "integer":
        if not re.fullmatch(r"[1-9][0-9]*", change.row_key):
            raise ChunkError(f"{change.table} key {change.row_key!r} is not a row id")
    elif change.row_key != change.site_id:
        raise ChunkError(f"a unified_sites row is its site: {change.row_key!r} != {change.site_id}")
    if change.old_value == change.new_value:
        raise ChunkError(
            f"{change.table}.{change.column} {change.row_key}: a no-op is not a change"
        )
    for what, value in (("old value", change.old_value), ("new value", change.new_value)):
        if value is None:
            continue
        _no_control(value, what=f"{change.table}.{change.column} {change.row_key} {what}")
        if kind == "boolean" and value not in ("true", "false"):
            raise ChunkError(f"{change.column} {what} {value!r} is not 'true' or 'false'")
        if kind == "integer" and not re.fullmatch(r"-?[0-9]+", value):
            raise ChunkError(f"{change.column} {what} {value!r} is not an integer")
    if change.new_value is None and kind != "text":
        raise ChunkError(f"{change.column} is never cleared to NULL by an image lane")
    if change.column == "name_normalized" and change.new_value is None:
        raise ChunkError(f"{change.table} {change.row_key}: a match key is never cleared to NULL")
    if change.column == "image_kind" and change.new_value not in pv.VOCAB | {None}:
        raise ChunkError(f"image_kind {change.new_value!r} is outside 0019's vocabulary")
    if not TOKEN_RE.fullmatch(change.rule.lower()):
        raise ChunkError(f"rule {change.rule!r} is not a rule id")
    if not change.reason.strip():
        raise ChunkError(f"{change.row_key}: a change without a reason")
    _no_control(change.reason, what="a reason")
    if not change.evidence or not all(
        isinstance(e, dict) and e.get("source") for e in change.evidence
    ):
        raise ChunkError(f"{change.row_key}: a change without evidence pointers")


# ------------------------------------------------------------------------------- the chunking
def chunk_changes(
    lane: Lane,
    changes: Sequence[Change],
    *,
    sites_per_chunk: int = SITES_PER_CHUNK,
    may_empty: Iterable[str] = (),
) -> list[Chunk]:
    """Split a lane's changes into chunks of at most `sites_per_chunk` whole sites.

    Sites keep the order of their first change (the caller's order - export order), and a site is
    never split across two chunks: a hero move or an exclusion and its consequences land together
    or not at all. A row planned twice is refused.
    """
    if not changes:
        raise ChunkError("refusing to chunk an empty plan")
    if not 1 <= sites_per_chunk <= SITES_PER_CHUNK:
        raise ChunkError(f"a chunk holds 1..{SITES_PER_CHUNK} sites, not {sites_per_chunk}")
    seen: set[tuple[str, str, str]] = set()
    by_site: dict[str, list[Change]] = {}
    for change in changes:
        validate_change(change)
        ident = (change.table, change.column, change.row_key)
        if ident in seen:
            raise ChunkError(f"{change.table}.{change.column} {change.row_key} is planned twice")
        seen.add(ident)
        by_site.setdefault(change.site_id, []).append(change)
    emptied = frozenset(may_empty)
    unknown = emptied - set(by_site)
    if unknown:
        raise ChunkError(f"may_empty names sites the plan does not touch: {sorted(unknown)[:5]}")
    order = list(by_site)
    chunks = []
    for number, start in enumerate(range(0, len(order), sites_per_chunk), start=1):
        sites = order[start : start + sites_per_chunk]
        rows = tuple(c for s in sites for c in by_site[s])
        chunks.append(Chunk(lane, number, rows, emptied & set(sites)))
    return chunks


# ------------------------------------------------------------------------ the records on disk
ROW_KEYS = ("table", "column", "row_key", "site_id", "old_value", "new_value", "change_key")


def ordered(chunk: Chunk) -> list[Change]:
    """The one row order every file of a chunk uses: by site, then table, column and key."""
    return sorted(
        chunk.changes,
        key=lambda c: (c.site_id, c.table, c.column, int(c.row_key) if c.row_key.isdigit() else 0),
    )


def header(chunk: Chunk) -> dict[str, Any]:
    return {
        "lane": chunk.lane.name,
        "test_id": chunk.lane.test_id,
        "stamp": chunk.lane.stamp,
        "confidence": chunk.lane.confidence,
        "label": chunk.lane.label,
        "chunk": chunk.number,
        "run_stamp": chunk.run_stamp,
        "rollback_stamp": chunk.rollback_stamp,
        "sites": len(chunk.sites),
        "rows": len(chunk.changes),
        "may_empty": sorted(chunk.may_empty),
    }


def records(chunk: Chunk) -> list[dict[str, Any]]:
    return [
        {
            "seq": seq,
            "table": c.table,
            "column": c.column,
            "row_key": c.row_key,
            "site_id": c.site_id,
            "old_value": c.old_value,
            "new_value": c.new_value,
            "change_key": change_key(chunk.lane, c),
            "rule": c.rule,
            "reason": c.reason,
            "evidence": c.evidence,
        }
        for seq, c in enumerate(ordered(chunk), start=1)
    ]


def chunk_digest(head: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> str:
    """sha256 over the chunk's identity and its row set (`persist_verdicts.plan_digest`)."""
    blob = json.dumps(dict(head), sort_keys=True, ensure_ascii=False)
    blob += "\n" + pv.plan_digest(rows, keys=ROW_KEYS)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_chunk(directory: Path) -> Chunk:
    """A chunk exactly as its two plan files describe it, re-validated row by row."""
    head_path, plan_path = directory / "CHUNK.json", directory / "PLAN.jsonl"
    for path in (head_path, plan_path):
        if not path.is_file():
            raise ChunkError(f"{path} does not exist - this is not an emitted chunk")
    head = json.loads(head_path.read_text(encoding="utf-8"))
    lane = Lane(head["lane"], head["test_id"], head["stamp"], head["confidence"], head["label"])
    changes = []
    for lineno, line in enumerate(pv.jsonl_lines(plan_path.read_text(encoding="utf-8")), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        change = Change(
            table=row["table"],
            column=row["column"],
            row_key=row["row_key"],
            site_id=row["site_id"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            rule=row["rule"],
            reason=row["reason"],
            evidence=row["evidence"],
        )
        if row["change_key"] != change_key(lane, change):
            raise ChunkError(f"{plan_path}:{lineno} carries a change key this lane does not make")
        changes.append(change)
    if not changes:
        raise ChunkError(f"{plan_path} holds no records - an empty plan is not a plan")
    chunk = Chunk(lane, int(head["chunk"]), tuple(changes), frozenset(head["may_empty"]))
    for change in chunk.changes:
        validate_change(change)
    if header(chunk) != head:
        raise ChunkError(f"{head_path} does not describe the rows of {plan_path}")
    return chunk


# ----------------------------------------------------------------------------- the statements
L = pv._sql_literal


def _value(value: str | None) -> str:
    return "NULL" if value is None else L(value)


def _key(table: str, expr: str) -> str:
    return f"{expr}::{KEY_TYPES[table]}"


def _plan_key(table: str) -> str:
    """A plan row's key in its table's type - cast only on that table's rows.

    PostgreSQL does not promise to filter `p.table_name` before it evaluates a join
    condition, and `'<uuid>'::integer` raises. The CASE makes the cast unreachable for the
    other table's rows.
    """
    return f"CASE WHEN p.table_name = {L(table)} THEN {_key(table, 'p.row_key')} END"


def _groups(rows: Sequence[Change]) -> list[tuple[str, str]]:
    return sorted({(c.table, c.column) for c in rows})


def _per_column(rows: Sequence[Change], template: str) -> list[str]:
    """One block per (table, column) the chunk writes; the column is a checked identifier."""
    out = []
    for table, column in _groups(rows):
        out.append(
            template.replace("{table}", table)
            .replace("{column}", column)
            .replace("{key}", _plan_key(table))
            .replace("{t}", L(table))
            .replace("{c}", L(column))
        )
    return out


GUARD_OLD = """
    SELECT count(*) INTO bad FROM {plan} p JOIN {table} t ON t.id = {key}
     WHERE p.table_name = {t} AND p.column_name = {c}
       AND t.{column}::text IS DISTINCT FROM p.old_value;
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % planned {column} row(s) no longer hold the planned old value', bad;
    END IF;"""

#: Guard 2b, rendered only for a chunk that writes a unified_site_names row: the row exists and
#: belongs to the site the plan names (the image rows' guard 2, for name rows).
GUARD_NAME_ROW = """
    -- guard 2b: every planned name row exists and belongs to the site the plan names
    SELECT count(*) INTO bad FROM {plan} p
      LEFT JOIN unified_site_names n ON n.id = {key}
     WHERE p.table_name = 'unified_site_names' AND (n.id IS NULL OR n.site_id IS DISTINCT FROM p.site_id);
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % planned name row(s) do not belong to the site the plan names', bad;
    END IF;"""

#: Guard 2c, rendered only for the write of a chunk that writes a match key: the planned key is the
#: one Postgres derives from the row's name now (pipeline/lyra/site_key.py). A name changed since
#: the read makes the plan stale, and the whole transaction refuses. The rollback restores the
#: journalled old key, which is by definition not that key, so it renders no premise.
GUARD_NAME_KEY = """
    -- guard 2c: every planned {table} key is the key Postgres derives from the row's name now
    SELECT count(*) INTO bad FROM {plan} p JOIN {table} {alias} ON {alias}.id = {key}
     WHERE p.table_name = {t} AND p.column_name = 'name_normalized'
       AND p.new_value IS DISTINCT FROM {derived};
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % planned key(s) are not the key Postgres derives from the name', bad;
    END IF;"""


def _name_key_guards(rows: Sequence[Change], *, rollback: bool) -> str:
    """Guards 2b and 2c for the key rows of a chunk; empty for a chunk that writes none, so every
    image chunk renders byte for byte as it did before the key columns existed."""
    blocks = []
    if any(c.table == "unified_site_names" for c in rows):
        blocks.append(GUARD_NAME_ROW.replace("{key}", _plan_key("unified_site_names")))
    if not rollback:
        for table, alias in sorted(NAME_KEY_TABLES.items()):
            if any(c.table == table and c.column == "name_normalized" for c in rows):
                blocks.append(
                    GUARD_NAME_KEY.replace("{table}", table)
                    .replace("{alias}", alias)
                    .replace("{key}", _plan_key(table))
                    .replace("{t}", L(table))
                    .replace("{derived}", site_key_sql(f"{alias}.name"))
                )
    return "".join("\n" + block for block in blocks)


INVARIANT_NEW = """
    SELECT count(*) INTO bad FROM {plan} p JOIN {table} t ON t.id = {key}
     WHERE p.table_name = {t} AND p.column_name = {c}
       AND t.{column}::text IS DISTINCT FROM p.new_value;
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % planned {column} row(s) do not hold the new value', bad;
    END IF;"""


def render_statement(chunk: Chunk, *, rollback: bool = False) -> str:
    """APPLY.sql (or, with `rollback`, ROLLBACK.sql) of one chunk. Deterministic, byte for byte."""
    lane = chunk.lane
    stamp = chunk.rollback_stamp if rollback else chunk.run_stamp
    label = f"{lane.label} {'rollback ' if rollback else ''}chunk {chunk.number:03d}"
    rows = ordered(chunk)
    digest = chunk_digest(header(chunk), records(chunk))
    tuples = []
    for seq, c in enumerate(rows, start=1):
        old, new = (c.new_value, c.old_value) if rollback else (c.old_value, c.new_value)
        if rollback:
            reason = (
                f"rollback of {lane.name} chunk {chunk.number:03d}: {c.table}.{c.column} "
                f"on {c.row_key} returned to {old!r} -> {new!r}"
            )
            evidence = [
                {
                    "source": "remediation_change_log (the row this undoes)",
                    "url": f"remediation_change_log.run_stamp={chunk.run_stamp}",
                    "quote": f"{change_key(lane, c)}: {c.old_value!r} -> {c.new_value!r}",
                }
            ]
        else:
            reason, evidence = f"{c.rule}: {c.reason}", c.evidence
        tuples.append(
            f"    ({seq}, {L(c.table)}, {L(c.column)}, {L(c.row_key)}, {L(c.site_id)}::uuid, "
            f"{_value(old)}, {_value(new)}, {L(change_key(lane, c, rollback=rollback))}, "
            f"{L(reason)}, {L(json.dumps(evidence, ensure_ascii=False, sort_keys=True))}::jsonb)"
        )
    may_empty = ", ".join(f"({L(s)}::uuid)" for s in sorted(chunk.may_empty))
    what = "reversal" if rollback else "write"
    values = ",\n".join(tuples)
    empty_rows = (
        f"INSERT INTO _img_may_empty (site_id) VALUES {may_empty};"
        if may_empty
        else "-- no site of this chunk may lose its last live image"
    )

    def fill(template: str) -> str:
        return template.replace("{plan}", PLAN_TABLE).replace("{label}", label)

    guards = "\n".join(fill(block) for block in _per_column(rows, GUARD_OLD))
    name_guards = fill(_name_key_guards(rows, rollback=rollback))
    invariants = "\n".join(fill(block) for block in _per_column(rows, INVARIANT_NEW))
    hero = "\n".join(one_hero_invariant_sql(PLAN_TABLE, label=label, at_most=True))
    vocab = ", ".join(L(k) for k in sorted(pv.VOCAB))
    s = L(stamp)
    return f"""-- Generated by scripts/remediation/gallery_audit/chunk_writer.py - do not edit by hand.
{pin_line(digest)}
-- The {what} of lane {lane.name!r}, chunk {chunk.number:03d}: {len(rows)} row(s) over {len(chunk.sites)} site(s);
-- scope source_id = '{CURATED_SOURCE}'; run stamp {stamp!r}; journal test id {lane.test_id!r}.
-- Every row goes through apply_remediation_change() (migrations 0017/0018/0022): the conditional
-- UPDATE and its journal row are one statement. This file holds no DELETE and no UPDATE.
\\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE {PLAN_TABLE} (
    seq         INTEGER PRIMARY KEY,
    table_name  TEXT NOT NULL,
    column_name TEXT NOT NULL,
    row_key     TEXT NOT NULL,
    site_id     UUID NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    change_key  TEXT NOT NULL,
    reason      TEXT NOT NULL,
    evidence    JSONB NOT NULL
) ON COMMIT DROP;

INSERT INTO {PLAN_TABLE} (seq, table_name, column_name, row_key, site_id, old_value, new_value, change_key, reason, evidence) VALUES
{values};

CREATE TEMP TABLE _img_may_empty (site_id UUID PRIMARY KEY) ON COMMIT DROP;
{empty_rows}

CREATE TEMP TABLE _img_live_before ON COMMIT DROP AS
  SELECT DISTINCT w.site_id FROM wiki_images w
   WHERE w.site_id IN (SELECT site_id FROM {PLAN_TABLE}) AND w.is_excluded IS NOT TRUE;

DO $$
DECLARE
    bad      integer;
    moved    integer := 0;
    expected integer := {len(rows)};
    r        RECORD;
BEGIN
    -- guard 1: every planned site is a curated site (the source is a RAISE argument, never
    -- part of the quoted message)
    SELECT count(*) INTO bad FROM (SELECT DISTINCT site_id FROM {PLAN_TABLE}) p
      LEFT JOIN unified_sites u ON u.id = p.site_id
     WHERE u.id IS NULL OR u.source_id <> {L(CURATED_SOURCE)};
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % planned site(s) are not % sites', bad, {L(CURATED_SOURCE)};
    END IF;

    -- guard 2: every planned image row exists and lives on the site the plan names
    SELECT count(*) INTO bad FROM {PLAN_TABLE} p
      LEFT JOIN wiki_images w ON w.id = {_plan_key("wiki_images")}
     WHERE p.table_name = 'wiki_images' AND (w.id IS NULL OR w.site_id IS DISTINCT FROM p.site_id);
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % planned image row(s) do not live on the site the plan names', bad;
    END IF;{name_guards}

    -- guard 3: every planned row still holds the planned old value (NULL-safe)
{guards}

    -- the only writer
    FOR r IN SELECT * FROM {PLAN_TABLE} ORDER BY seq LOOP
        moved := moved + apply_remediation_change(
            r.table_name, r.column_name, {L(KEY_COLUMN)}, r.row_key, r.old_value, r.new_value,
            {L(lane.test_id)}, {s}, r.change_key, {L(lane.confidence)}, r.evidence, r.site_id);
    END LOOP;
    IF moved <> expected THEN
        RAISE EXCEPTION '{label}: % row(s) changed, % planned', moved, expected;
    END IF;

    -- invariant 1: every planned row now holds its new value
{invariants}

    -- invariant 2: plan -> journal, row for row, with the planned values and keys
    SELECT count(*) INTO bad FROM {PLAN_TABLE} p
      LEFT JOIN remediation_change_log l
        ON l.run_stamp = {s} AND l.table_name = p.table_name
       AND l.column_name = p.column_name AND l.row_pk = p.row_key
     WHERE l.id IS NULL OR l.old_value IS DISTINCT FROM p.old_value
        OR l.new_value IS DISTINCT FROM p.new_value OR l.change_key IS DISTINCT FROM p.change_key;
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % planned row(s) disagree with the journal', bad;
    END IF;

    -- invariant 3: journal -> plan: this run stamp journalled the planned rows and nothing else
    SELECT count(*) INTO bad FROM remediation_change_log l
     WHERE l.run_stamp = {s}
       AND NOT EXISTS (SELECT 1 FROM {PLAN_TABLE} p
                        WHERE p.table_name = l.table_name AND p.column_name = l.column_name
                          AND p.row_key = l.row_pk);
    IF bad > 0 OR (SELECT count(*) FROM remediation_change_log WHERE run_stamp = {s}) <> expected THEN
        RAISE EXCEPTION '{label}: the journal of this run stamp is not the plan (% unplanned row(s))', bad;
    END IF;

    -- invariant 4: at most one hero per touched site
{hero}

    -- invariant 5: no hero on an excluded row of a touched site
    SELECT count(*) INTO bad FROM wiki_images w
     WHERE w.site_id IN (SELECT site_id FROM {PLAN_TABLE}) AND w.is_hero AND w.is_excluded IS TRUE;
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % hero row(s) are excluded', bad;
    END IF;

    -- invariant 6: a touched site that had a live image still has one, unless the chunk names it
    SELECT count(*) INTO bad FROM _img_live_before b
     WHERE NOT EXISTS (SELECT 1 FROM wiki_images w
                        WHERE w.site_id = b.site_id AND w.is_excluded IS NOT TRUE)
       AND b.site_id NOT IN (SELECT site_id FROM _img_may_empty);
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % site(s) lost their last live image', bad;
    END IF;

    -- invariant 7: every image kind of a touched row is in migration 0019's vocabulary
    SELECT count(*) INTO bad FROM wiki_images w
     WHERE w.site_id IN (SELECT site_id FROM {PLAN_TABLE})
       AND w.image_kind IS NOT NULL AND w.image_kind NOT IN ({vocab});
    IF bad > 0 THEN
        RAISE EXCEPTION '{label}: % image kind(s) outside the vocabulary', bad;
    END IF;
END $$;

SELECT '{READBACK_LABEL}', count(*)::text FROM remediation_change_log WHERE run_stamp = {s};
SELECT 'planned rows', count(*)::text FROM {PLAN_TABLE};
COMMIT;
"""


def _strip_literals_and_comments(sql: str) -> str:
    code = re.sub(r"'(?:[^']|'')*'", "''", sql)
    # a temp table's lifetime clause, not a DROP statement
    code = re.sub(r"\bON COMMIT DROP\b", "", code)
    return "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("--"))


def lint_statement(sql: str) -> None:
    """0 DELETE, 0 hand-written UPDATE, and no INSERT but into this file's own temp tables.

    Judged on code only: comments and quoted literals are blanked first, so a reason that quotes
    the word does not trip it and a keyword hidden in a comment does not pass for code.
    """
    code = _strip_literals_and_comments(sql)
    for word in ("DELETE", "UPDATE", "TRUNCATE", "DROP", "ALTER"):
        if re.search(rf"\b{word}\b", code, re.IGNORECASE):
            raise ChunkError(f"the statement carries {word} - only apply_remediation_change writes")
    for target in re.findall(r"\bINSERT\s+INTO\s+(\w+)", code, re.IGNORECASE):
        if target not in (PLAN_TABLE, "_img_may_empty"):
            raise ChunkError(f"the statement inserts into {target}")
    if len(re.findall(r"\bCOMMIT\b", code)) != 1 or not sql.rstrip().endswith("\nCOMMIT;"):
        raise ChunkError("the statement does not end in exactly one COMMIT;")


# ------------------------------------------------------------------------------------ emitting
def chunk_dir(out: Path, chunk: Chunk) -> Path:
    return out / f"chunk-{chunk.number:03d}"


def emit_chunk(out: Path, chunk: Chunk) -> Path:
    """Write one chunk: CHUNK.json, PLAN.jsonl, then ROLLBACK.sql, then APPLY.sql.

    A directory that already holds a chunk is never overwritten: its ROLLBACK.sql may be the only
    undo of a write that has landed. Re-emitting the identical chunk is a no-op after the files on
    disk are proven identical.
    """
    directory = chunk_dir(out, chunk)
    apply_sql = render_statement(chunk)
    rollback_sql = render_statement(chunk, rollback=True)
    for sql in (apply_sql, rollback_sql):
        lint_statement(sql)
    if directory.exists() and any(directory.iterdir()):
        delivered = check_delivered(directory)
        if chunk_digest(header(delivered), records(delivered)) != chunk_digest(
            header(chunk), records(chunk)
        ) or records(delivered) != records(chunk):
            raise ChunkError(
                f"{directory} holds another chunk - a delivered chunk is never replaced"
            )
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "CHUNK.json").write_text(
        json.dumps(header(chunk), ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with (directory / "PLAN.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in records(chunk):
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    # The undo first: a process that dies between the two leaves an undo and no write.
    (directory / "ROLLBACK.sql").write_text(rollback_sql, encoding="utf-8", newline="\n")
    (directory / "APPLY.sql").write_text(apply_sql, encoding="utf-8", newline="\n")
    return directory


def emit_chunks(out: Path, chunks: Sequence[Chunk]) -> list[Path]:
    return [emit_chunk(out, chunk) for chunk in chunks]


def _read(path: Path) -> str:
    """A delivered file's text with universal newlines.

    Chunks are versioned, and this checkout's `core.autocrlf=true` hands them back with CRLF. The
    rendered statement holds no bare carriage return (`validate_change` refuses control characters),
    so a line ending is the only difference that translation can hide.
    """
    return path.read_text(encoding="utf-8")


def check_delivered(directory: Path) -> Chunk:
    """The files on disk are exactly what the plan renders, or nothing is sent. Offline."""
    chunk = load_chunk(directory)
    digest = chunk_digest(header(chunk), records(chunk))
    for name, rollback in (("APPLY.sql", False), ("ROLLBACK.sql", True)):
        path = directory / name
        if not path.is_file():
            raise ChunkError(f"{path} does not exist")
        text = _read(path)
        pin = pv.DIGEST_RE.search(text)
        if pin is None or pin.group(1) != digest:
            raise ChunkError(f"{path} is not pinned to this plan (plan sha256 {digest})")
        if text != render_statement(chunk, rollback=rollback):
            raise ChunkError(
                f"{path} is not the statement its plan renders - edited or stale; refusing to send"
            )
        lint_statement(text)
    return chunk


# ------------------------------------------------------------------------------ production
def journal_rows(run_stamp: str) -> list[dict[str, Any]]:
    return pv.read_rows(
        "SELECT row_to_json(t) FROM (SELECT table_name, column_name, row_pk, old_value,"
        " new_value, change_key, test_id, confidence FROM remediation_change_log"
        f" WHERE run_stamp = {L(run_stamp)} ORDER BY id) t;"
    )


def current_values(changes: Sequence[Change]) -> dict[tuple[str, str, str], str | None]:
    """The value every planned (table, column, row) holds now, in its text form. Read-only."""
    out: dict[tuple[str, str, str], str | None] = {}
    for table, column in _groups(changes):
        keys = sorted({c.row_key for c in changes if (c.table, c.column) == (table, column)})
        typed = ", ".join(_key(table, L(k)) for k in keys)
        rows = pv.read_rows(
            f"SELECT row_to_json(t) FROM (SELECT {KEY_COLUMN}::text AS row_key,"
            f" {column}::text AS value FROM {table} WHERE {KEY_COLUMN} IN ({typed})) t;"
        )
        for row in rows:
            out[(table, column, str(row["row_key"]))] = row["value"]
    return out


AFTER_SQL = """SELECT row_to_json(t) FROM (SELECT
  (SELECT count(*) FROM (SELECT w.site_id FROM wiki_images w WHERE w.site_id IN ({sites})
     GROUP BY w.site_id HAVING count(*) FILTER (WHERE w.is_hero) > 1) x)::int AS sites_with_two_heroes,
  (SELECT count(*) FROM wiki_images w WHERE w.site_id IN ({sites})
     AND w.is_hero AND w.is_excluded IS TRUE)::int AS excluded_heroes,
  (SELECT count(*) FROM wiki_images w WHERE w.site_id IN ({sites})
     AND w.image_kind IS NOT NULL AND w.image_kind NOT IN ({vocab}))::int AS kinds_outside_vocabulary,
  (SELECT count(*) FROM unified_sites u WHERE u.id IN ({sites})
     AND u.source_id <> {source})::int AS sites_outside_the_curated_source
) t;"""


def readback(chunk: Chunk, *, rollback: bool = False) -> list[str]:
    """Every difference between the plan, the journal and the data. Empty means confirmed.

    Identity, not counts: every planned row must have its journal row (plan -> journal), every
    journal row of the stamp must be planned (journal -> plan), each with the planned old value,
    new value, change key, test id and confidence, and the data must hold the new value.
    """
    lane = chunk.lane
    stamp = chunk.rollback_stamp if rollback else chunk.run_stamp
    planned: dict[tuple[str, str, str], Change] = {
        (c.table, c.column, c.row_key): c for c in chunk.changes
    }
    problems: list[str] = []
    journal: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in journal_rows(stamp):
        ident = (str(row["table_name"]), str(row["column_name"]), str(row["row_pk"]))
        if ident in journal:
            problems.append(f"journal holds {ident} twice under {stamp}")
        journal[ident] = row
    for ident in sorted(set(journal) - set(planned)):
        problems.append(f"journal -> plan: {ident} is journalled under {stamp} but not planned")
    for ident, change in sorted(planned.items()):
        row = journal.get(ident)
        if row is None:
            problems.append(f"plan -> journal: {ident} has no journal row under {stamp}")
            continue
        old, new = (
            (change.new_value, change.old_value)
            if rollback
            else (change.old_value, change.new_value)
        )
        want = {
            "old_value": old,
            "new_value": new,
            "change_key": change_key(lane, change, rollback=rollback),
            "test_id": lane.test_id,
            "confidence": lane.confidence,
        }
        for name, value in want.items():
            if row.get(name) != value:
                problems.append(f"{ident}: journal {name} is {row.get(name)!r}, planned {value!r}")
    now = current_values(chunk.changes)
    for ident, change in sorted(planned.items()):
        want_value = change.old_value if rollback else change.new_value
        if ident not in now:
            problems.append(f"{ident}: the row no longer exists")
        elif now[ident] != want_value:
            problems.append(f"{ident}: holds {now[ident]!r}, planned {want_value!r}")
    sites = ", ".join(f"{L(s)}::uuid" for s in chunk.sites)
    after = pv.read_rows(
        AFTER_SQL.replace("{sites}", sites)
        .replace("{vocab}", ", ".join(L(k) for k in sorted(pv.VOCAB)))
        .replace("{source}", L(CURATED_SOURCE))
    )
    if len(after) != 1:
        problems.append(f"the invariant read returned {len(after)} rows")
    else:
        for name, value in sorted(after[0].items()):
            if value != 0:
                problems.append(f"invariant {name} = {value}")
    return problems


def journal_count(run_stamp: str) -> int:
    rows = pv.read_rows(
        "SELECT row_to_json(t) FROM (SELECT count(*)::int AS n FROM remediation_change_log"
        f" WHERE run_stamp = {L(run_stamp)}) t;"
    )
    if len(rows) != 1:
        raise ChunkError(f"the journal count for {run_stamp!r} came back as {rows!r}")
    return pv._as_int(rows[0]["n"], what=f"journal rows of {run_stamp}")


def _unknown(chunk: Chunk, detail: str) -> OutcomeUnknown:
    query = f"SELECT count(*) FROM remediation_change_log WHERE run_stamp = {L(chunk.run_stamp)};"
    return OutcomeUnknown(
        f"{detail} Before any retry: wait until {OPEN_SESSIONS_SQL} lists no session of this "
        f"write, then run: {query} - the chunk landed only if it reads {len(chunk.changes)}, and "
        "nothing was written if it reads 0."
    )


def settle(chunk: Chunk, what: str, *, session_ended: bool) -> int:
    """After a timeout or a failed psql exit: say from the journal what happened, never retry.

    All planned rows journalled means the transaction COMMITTED - a committed row cannot vanish.
    None means NOT COMMITTED only when psql itself stopped the script (its exit 3): its session is
    gone and an uncommitted transaction with it. After a timeout or a dropped channel the server
    may still be running the script towards its COMMIT, so an empty journal is UNKNOWN.
    """
    try:
        count = journal_count(chunk.run_stamp)
    except (OutcomeUnknown, pv.PersistError) as exc:
        raise _unknown(chunk, f"{what}; the journal could not be read either ({exc}).") from exc
    if count == 0 and session_ended:
        print(f"NOT COMMITTED: {what}; the journal holds 0 rows for {chunk.run_stamp!r}.")
        return EXIT_NOT_COMMITTED
    if count == 0:
        raise _unknown(chunk, f"{what}; the journal holds 0 rows so far.")
    if count != len(chunk.changes):
        raise _unknown(
            chunk,
            f"{what}; the journal holds {count} of {len(chunk.changes)} rows - one "
            "transaction cannot leave that behind.",
        )
    print(f"COMMITTED: {what}, but the journal holds all {count} rows. Reading it back:")
    problems = readback(chunk)
    if problems:
        return _unconfirmed(problems)
    print("APPLY LANDED: the read-back matches the plan both ways; psql did not finish cleanly.")
    return EXIT_COMMITTED_UNCLEAN


def _unconfirmed(problems: Sequence[str]) -> int:
    print("COMMITTED BUT NOT CONFIRMED: the write is in the database, but its read-back differs:")
    for problem in problems:
        print(f"  {problem}")
    return EXIT_COMMITTED_UNCONFIRMED


def _ran_as_rehearsal(proc_stdout: str) -> bool:
    return (
        READBACK_LABEL in proc_stdout and "ROLLBACK" in proc_stdout and "COMMIT" not in proc_stdout
    )


def command_rehearse(directory: Path) -> int:
    """APPLY.sql with its one COMMIT swapped for ROLLBACK: every guard runs, nothing is kept."""
    chunk = check_delivered(directory)
    script = pv.rehearsal_of(_read(directory / "APPLY.sql"))
    proc = pv.run_psql(script, check=False)
    print(proc.stdout)
    if proc.returncode != 0 or not _ran_as_rehearsal(proc.stdout):
        print(proc.stderr, file=sys.stderr)
        print(f"REHEARSAL FAILED: psql exit {proc.returncode}")
        return EXIT_REHEARSAL_FAILED
    left = journal_count(chunk.run_stamp)
    if left != 0:
        print(f"REHEARSAL FAILED: {left} journal row(s) of {chunk.run_stamp!r} survived it")
        return EXIT_REHEARSAL_FAILED
    print(f"REHEARSAL OK: chunk {chunk.number:03d}, {len(chunk.changes)} row(s), rolled back")
    return EXIT_OK


def command_rehearse_rollback(directory: Path) -> int:
    """ROLLBACK.sql with COMMIT -> ROLLBACK, against the state the landed write left behind."""
    chunk = check_delivered(directory)
    script = pv.rehearsal_of(_read(directory / "ROLLBACK.sql"))
    proc = pv.run_psql(script, check=False)
    print(proc.stdout)
    if proc.returncode != 0 or not _ran_as_rehearsal(proc.stdout):
        print(proc.stderr, file=sys.stderr)
        print(f"ROLLBACK REHEARSAL FAILED: psql exit {proc.returncode}")
        return EXIT_REHEARSAL_FAILED
    left = journal_count(chunk.rollback_stamp)
    problems = readback(chunk)
    if left != 0 or problems:
        print(f"ROLLBACK REHEARSAL FAILED: {left} reversal row(s) kept; {problems}")
        return EXIT_REHEARSAL_FAILED
    print("ROLLBACK REHEARSAL OK: the reversal ran on the landed rows and was rolled back")
    return EXIT_OK


def command_apply(directory: Path) -> int:
    chunk = check_delivered(directory)
    already = journal_count(chunk.run_stamp)
    if already:
        raise ChunkError(
            f"run stamp {chunk.run_stamp!r} already journals {already} row(s): this chunk has "
            "landed, or something else wrote under its stamp - run --readback; never apply twice"
        )
    try:
        proc = pv.run_psql(_read(directory / "APPLY.sql"), check=False)
    except OutcomeUnknown as exc:
        return settle(chunk, f"psql timed out ({exc})", session_ended=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return settle(
            chunk,
            f"psql exited {proc.returncode}",
            session_ended=proc.returncode == PSQL_SCRIPT_ERROR,
        )
    try:
        problems = readback(chunk)
    except (OutcomeUnknown, pv.PersistError) as exc:
        return _unconfirmed([f"the read-back could not run: {exc}"])
    if problems:
        return _unconfirmed(problems)
    print(f"APPLY OK: chunk {chunk.number:03d}, the read-back matches plan and journal both ways")
    return EXIT_OK


def command_readback(directory: Path) -> int:
    chunk = check_delivered(directory)
    problems = readback(chunk)
    if problems:
        print("READBACK FAILED:")
        for problem in problems:
            print(f"  {problem}")
        return EXIT_COMMITTED_UNCONFIRMED
    print(f"READBACK OK: {len(chunk.changes)} row(s), plan = journal = data")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("chunk", type=Path, help="an emitted chunk directory")
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ("check", "rehearse", "apply", "readback", "rehearse-rollback"):
        group.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            chunk = check_delivered(args.chunk)
            print(f"CHECK OK: {args.chunk} is the plan's, {len(chunk.changes)} row(s)")
            return EXIT_OK
        if args.rehearse:
            return command_rehearse(args.chunk)
        if args.apply:
            return command_apply(args.chunk)
        if args.readback:
            return command_readback(args.chunk)
        return command_rehearse_rollback(args.chunk)
    except OutcomeUnknown as exc:
        print(f"OUTCOME UNKNOWN: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN
    except pv.PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
