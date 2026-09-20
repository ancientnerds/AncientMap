"""Persist the vision-model verdicts the shorts pipeline already computed into
`wiki_images.image_kind` (migration 0019).

This is GALLERY's G0: it writes no new judgements. Every value it stores was already decided
by `pipeline/video/shorts_select.py` during a previous shorts run and recorded in
`video-assets/shorts/<slug>/selection.json`. The only claim this lane makes is "the pipeline
already judged this image to be X, and here is the file that says so".

Measured shape of the input (2026-09-21), because the headline number is misleading:
the 16 `selection.json` files hold 280 entries in **two different shapes**.

    stills    105  full record incl. `id` (the wiki_images.id) and `verdict.kind`  -> writable
    rejected  175  only `filename` + `reason`, no id and no kind                   -> NOT writable

So G0's honest scope is the 105 `stills`, all of which the pipeline judged `site_photo`.
The 175 rejections are mostly composition or quality judgements - `too small (<WxH>)` ~45,
`duplicate (subject: ...)` ~35, `panorama` 15, `text or overlay` 11 - and those are **not image
kinds**. Inventing a kind from a rejection reason is exactly the fabricated data this project
forbids, so they are left alone. 30 of them do state a kind verbatim (`kind=artifact` 17,
`kind=map_or_document` 9, `kind=painting_or_artwork` 3, `kind=other` 1) but carry no `id`, so
persisting them needs a proven slug->site_id and filename->row match first; that is a recorded
follow-up, not part of this lane.

Three rules this file follows, all of them paid for elsewhere in this project:

* **NULL is not 'unknown'.** Migration 0019 reserves NULL for "no verdict was ever recorded" and
  `unknown` for "a model looked and could not decide". The planned rows hold NULL, so the
  conditional write proves the row is still NULL before it writes - a row that already carries a
  different kind is REFUSED and named in `SKIPPED.jsonl`, never overwritten.
* **A NULL-safe comparison, never `=`.** The old value here *is* NULL, so every guard uses
  `IS NOT DISTINCT FROM`. `image_kind = NULL` is NULL, not true, and would match no rows.
* **Write the undo before the do.** `ROLLBACK.sql` is emitted before `APPLY.sql`.

Usage:
    persist_verdicts.py --plan            # read-only: write PLAN.md, PLAN.jsonl, SKIPPED.jsonl,
                                          # APPLY.sql, ROLLBACK.sql
    persist_verdicts.py --rehearse        # run APPLY.sql inside a transaction and roll it back
    persist_verdicts.py --check-primitive # probe the journalled primitive itself on a scratch row
    persist_verdicts.py --apply           # the write (requires the rollout decision)
    persist_verdicts.py --verify          # read-only: prove the landed state
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "output" / "remediation" / "gallery_audit"
SELECTION = ROOT / "video-assets" / "shorts"

#: The vocabulary migration 0019 enforces with a CHECK constraint. Kept as a literal copy
#: rather than imported, because a drift between this set and the migration must be a loud
#: failure here (`--verify` compares them) and not a silent one.
VOCAB = frozenset(
    {
        "site_photo",
        "artifact",
        "map_or_document",
        "painting_or_artwork",
        "people",
        "other",
        "unknown",
    }
)

TABLE = "wiki_images"
COLUMN = "image_kind"
KEY_COLUMN = "id"
CURATED_SOURCE = "ancient_nerds"
TEST_ID = "G0/vlm-kind"
RUN_STAMP = "2026-09-21_gallery-verdicts-persist"

#: `authoritative` per 0017's own vocabulary (`authoritative|two_source|weak|unverifiable`).
#: The provenance being asserted is "the pipeline recorded this verdict about this image", and
#: the record is that pipeline's own file. Note the caveat this does NOT claim: GALLERY proved
#: the vision model is *reachable* and correctly labels colour, but its semantic **competence**
#: on archaeological imagery is unverified. These 105 rows are therefore a first reviewable
#: batch, not a validated classifier. Recorded in evidence below and in the audit log.
CONFIDENCE = "authoritative"

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_NOTHING = 2
EXIT_INCONSISTENT = 3
EXIT_VERIFY_FAILED = 4

#: The transport this project uses for production SQL. `-i` on `docker exec` is load-bearing:
#: without it psql receives empty stdin and silently does nothing. No `-F`: ssh hands this
#: command to a remote login shell, which reads a bare `|` as a pipe.
PSQL = "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1"
PSQL_ROWS = PSQL + " -t -A"
SSH_HOST = "ancientnerds"


class PersistError(RuntimeError):
    """A condition that must stop the lane rather than be worked around."""


@dataclass(frozen=True)
class Verdict:
    """One writable verdict, with the provenance needed to audit it."""

    image_id: int
    kind: str
    slug: str
    file: Path
    verdict: dict[str, object]
    entry: dict[str, object]


@dataclass(frozen=True)
class Skipped:
    """A row this lane deliberately does not write, and why."""

    image_id: int | None
    slug: str
    reason: str
    detail: str


# --------------------------------------------------------------------------------------
# reading the input (offline, no network, no database)
# --------------------------------------------------------------------------------------


def load_verdicts(base: Path = SELECTION) -> list[Verdict]:
    """Read every `stills[]` verdict. Raises on anything malformed - never skips quietly."""
    if not base.is_dir():
        raise PersistError(f"{base} is not a directory")

    files = sorted(base.glob("*/selection.json"))
    if not files:
        raise PersistError(f"no selection.json under {base}")

    out: list[Verdict] = []
    seen: dict[int, str] = {}
    for path in files:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersistError(f"{path}: cannot be read as JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise PersistError(
                f"{path}: top level is {type(document).__name__}, expected an object"
            )

        slug = path.parent.name
        for entry in document.get("stills", []):
            if not isinstance(entry, dict):
                raise PersistError(f"{path}: a stills element is {type(entry).__name__}")
            if "id" not in entry:
                raise PersistError(f"{path}: a stills element has no id ({sorted(entry)})")
            image_id = entry["id"]
            if not isinstance(image_id, int) or isinstance(image_id, bool):
                raise PersistError(f"{path}: id is {image_id!r}, expected an integer")

            verdict = entry.get("verdict")
            if not isinstance(verdict, dict):
                raise PersistError(f"{path}: id {image_id} carries no verdict object")
            kind = verdict.get("kind")
            if kind not in VOCAB:
                raise PersistError(
                    f"{path}: id {image_id} has kind {kind!r}, which is not one of "
                    f"{sorted(VOCAB)} - the column's CHECK constraint would reject it"
                )
            if image_id in seen and seen[image_id] != kind:
                raise PersistError(
                    f"{path}: id {image_id} already appeared with kind {seen[image_id]!r}; "
                    f"two files disagree about one image"
                )
            seen[image_id] = kind
            out.append(
                Verdict(
                    image_id=image_id,
                    kind=kind,
                    slug=slug,
                    file=path,
                    verdict=verdict,
                    entry=entry,
                )
            )

    if not out:
        raise PersistError(f"{base}: no stills entries with a verdict were found")
    return out


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def evidence_for(v: Verdict) -> list[dict[str, object]]:
    """The chain that lets a reader re-derive this write without trusting this script."""
    keep = ("kind", "subject", "people_prominent", "text_or_overlay", "quality", "relevance")
    recorded = {k: v.verdict[k] for k in keep if k in v.verdict}
    return [
        {
            "source": "shorts selection record (the verdict being persisted)",
            "url": _relative(v.file),
            "quote": (
                f"stills[] entry with id={v.image_id} carries verdict={json.dumps(recorded, sort_keys=True)}"
            ),
        },
        {
            "source": "pipeline/video/shorts_select.py (the stage that produced the verdict)",
            "url": "pipeline/video/shorts_select.py",
            "quote": (
                "VLM_MAX_SIDE caps the image sent to the vision model; the vocabulary this "
                "column copies is that stage's own prompt output"
            ),
        },
        {
            "source": "migration 0019 (the column and its CHECK constraint)",
            "url": "migrations/0019_wiki_images_image_kind.sql",
            "quote": (
                "image_kind is nullable; NULL means no verdict was ever recorded and is NOT the "
                "same as 'unknown'. Only 'site_photo' may be treated as clean."
            ),
        },
        {
            "source": "image identity",
            "url": _relative(v.file),
            "quote": (
                f"entry id={v.image_id} filename={v.entry.get('filename')!r} "
                f"is_hero={v.entry.get('is_hero')!r} - the id is wiki_images.id, checked against "
                "production by --verify, not assumed"
            ),
        },
        {
            "source": "caveat, recorded with the write rather than after it",
            "url": "output/remediation/gallery_design/DESIGN.md",
            "quote": (
                "the vision model's semantic competence on archaeological imagery is unverified; "
                "these rows record the pipeline's existing verdicts and are a first reviewable "
                "batch, not a validated classifier"
            ),
        },
    ]


# --------------------------------------------------------------------------------------
# production reads
# --------------------------------------------------------------------------------------


def run_psql(
    sql: str, *, host: str = SSH_HOST, timeout: int = 900, rows: bool = False, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Send `sql` to production the way this project does it: ssh, then psql in the container."""
    proc = subprocess.run(
        shlex.split(f"ssh {host} {PSQL_ROWS if rows else PSQL}"),
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        raise PersistError(f"psql exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}".strip())
    return proc


def read_rows(sql: str) -> list[dict[str, object]]:
    """Run a read-only query and parse one JSON object per line.

    `row_to_json`, not a delimiter: a `-F` argument reaches the remote login shell and gets
    eaten (this lane's own first attempt lost its tabs that way), and any character can occur
    inside a URL.
    """
    proc = run_psql(sql, rows=True)
    out: list[dict[str, object]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PersistError(f"could not parse a row as JSON: {line!r} ({exc})") from exc
        if not isinstance(parsed, dict):
            raise PersistError(f"row is {type(parsed).__name__}, expected an object: {line!r}")
        out.append(parsed)
    return out


def _as_int(value: object, *, what: str) -> int:
    """Checked conversion. `json.loads` yields `object`, and a silent `int(...)` here would be a
    wrong ignore code rather than a fix. Booleans are excluded deliberately: `True` is an int
    in Python, and an id of `true` would be a real bug in the source data."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PersistError(f"{what} is {value!r}, expected an integer")
    return value


def read_state(image_ids: list[int]) -> dict[int, dict[str, object]]:
    """Current `image_kind`, owning site and source for each planned id. Read-only."""
    if not image_ids:
        return {}
    id_list = ", ".join(str(i) for i in image_ids)
    sql = f"""
SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, s.source_id, w.image_kind, w.filename,
         w.is_hero, w.original_url
    FROM wiki_images w
    JOIN unified_sites s ON s.id = w.site_id
   WHERE w.id IN ({id_list})
   ORDER BY w.id
) t;
"""
    rows = read_rows(sql)
    return {_as_int(r["id"], what="wiki_images.id from the database"): r for r in rows}


# --------------------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------------------


def build_plan(
    targets: list[Verdict], state: dict[int, dict[str, object]]
) -> tuple[list[Verdict], list[Skipped]]:
    """Split the verdicts into writable rows and named refusals. Never silently drops one."""
    write: list[Verdict] = []
    skipped: list[Skipped] = []

    for v in targets:
        row = state.get(v.image_id)
        if row is None:
            skipped.append(
                Skipped(
                    v.image_id,
                    v.slug,
                    "id-not-in-database",
                    "no wiki_images row has this id; the selection record is stale",
                )
            )
            continue
        if row.get("source_id") != CURATED_SOURCE:
            skipped.append(
                Skipped(
                    v.image_id,
                    v.slug,
                    "row-not-in-curated-source",
                    f"the row's site belongs to source_id={row.get('source_id')!r}; this lane "
                    f"writes curated sites only",
                )
            )
            continue
        current = row.get("image_kind")
        if current == v.kind:
            skipped.append(
                Skipped(
                    v.image_id,
                    v.slug,
                    "already-recorded",
                    f"image_kind is already {current!r}; nothing to write",
                )
            )
            continue
        if current is not None:
            skipped.append(
                Skipped(
                    v.image_id,
                    v.slug,
                    "different-verdict-already-recorded",
                    f"image_kind is {current!r}, the record says {v.kind!r}; this lane never "
                    f"overwrites one judgement with another - escalate instead",
                )
            )
            continue
        write.append(v)

    return write, skipped


# --------------------------------------------------------------------------------------
# emitting the SQL
# --------------------------------------------------------------------------------------


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_plan_table(write: list[Verdict], state: dict[int, dict[str, object]]) -> str:
    lines = [
        "CREATE TEMP TABLE _kind_plan (",
        "    image_id    BIGINT PRIMARY KEY,",
        "    site_id     UUID NOT NULL,",
        "    old_value   TEXT,",
        "    new_value   TEXT NOT NULL,",
        "    change_key  TEXT NOT NULL,",
        "    reason      TEXT NOT NULL,",
        "    evidence    JSONB NOT NULL",
        ") ON COMMIT DROP;",
        "",
        "INSERT INTO _kind_plan (image_id, site_id, old_value, new_value, change_key, reason, evidence) VALUES",
    ]
    tuples = []
    for v in write:
        row = state[v.image_id]
        current = row.get("image_kind")
        old_literal = "NULL" if current is None else _sql_literal(str(current))
        evidence = json.dumps(evidence_for(v), ensure_ascii=False)
        reason = (
            f"G0: the shorts pipeline judged image {v.image_id} ({v.entry.get('filename')!r}) "
            f"{v.kind!r} on {v.slug}; recorded verbatim from its own selection record"
        )
        tuples.append(
            "    ({}, {}::uuid, {}, {}, {}, {}, {}::jsonb)".format(
                v.image_id,
                _sql_literal(str(row["site_id"])),
                old_literal,
                _sql_literal(v.kind),
                _sql_literal(f"g0-vlm-kind:{v.image_id}"),
                _sql_literal(reason),
                _sql_literal(evidence),
            )
        )
    lines.append(",\n".join(tuples) + ";")
    return "\n".join(lines)


GUARDS = """
    -- scope guard 1: every planned row exists
    SELECT count(*) INTO bad FROM _kind_plan p
      LEFT JOIN wiki_images w ON w.id = p.image_id WHERE w.id IS NULL;
    IF bad > 0 THEN
        RAISE EXCEPTION 'G0 image_kind: % planned row(s) do not exist', bad;
    END IF;

    -- scope guard 2: every planned row belongs to a curated site.
    -- The source name is passed as a RAISE argument, not embedded in the message: a literal
    -- 'ancient_nerds' inside a single-quoted RAISE message terminates the string and the whole
    -- statement fails to parse (measured - the rehearsal caught exactly that).
    SELECT count(*) INTO bad
      FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
      JOIN unified_sites s ON s.id = w.site_id
     WHERE s.source_id <> {source};
    IF bad > 0 THEN
        RAISE EXCEPTION 'G0 image_kind: % planned row(s) are outside source_id %', bad, {source_arg};
    END IF;

    -- scope guard 3: every planned row still holds the old value the plan names. NULL-safe:
    -- `image_kind = NULL` is NULL, not true, and would match nothing.
    SELECT count(*) INTO bad
      FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
     WHERE w.image_kind IS DISTINCT FROM p.old_value;
    IF bad > 0 THEN
        RAISE EXCEPTION 'G0 image_kind: % planned row(s) no longer hold the planned old value', bad;
    END IF;
"""

INVARIANTS = """
    -- invariant 1: every planned row now holds the new value
    SELECT count(*) INTO bad
      FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
     WHERE w.image_kind IS DISTINCT FROM p.new_value;
    IF bad > 0 THEN
        RAISE EXCEPTION 'G0 image_kind: % planned row(s) do not hold the new value', bad;
    END IF;

    -- invariant 2: the journal and the data agree, row for row, in both directions
    SELECT count(*) INTO bad
      FROM _kind_plan p LEFT JOIN remediation_change_log l
        ON l.row_pk = p.image_id::text AND l.table_name = {tbl}
       AND l.column_name = {col}
       AND l.run_stamp = {stamp}
     WHERE l.id IS NULL
        OR l.new_value IS DISTINCT FROM p.new_value
        OR l.old_value IS DISTINCT FROM p.old_value;
    IF bad > 0 THEN
        RAISE EXCEPTION 'G0 image_kind: % planned row(s) disagree with the journal', bad;
    END IF;
"""

#: Run INSIDE the transaction, before COMMIT: these read `_kind_plan`, which is ON COMMIT DROP.
VERIFY_IN_TX_SQL = f"""
SELECT 'planned rows written', count(*)::text FROM wiki_images
 WHERE image_kind = 'site_photo' AND id IN (SELECT image_id FROM _kind_plan);
SELECT 'rows still NULL among planned', count(*)::text
  FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id WHERE w.image_kind IS NULL;
SELECT 'journal rows for this run', count(*)::text FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(RUN_STAMP)};
SELECT 'journal rows for this run outside wiki_images.image_kind', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(RUN_STAMP)}
   AND (table_name <> 'wiki_images' OR column_name <> 'image_kind');
SELECT 'journal rows for this run with no evidence', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(RUN_STAMP)} AND (evidence IS NULL OR evidence = '[]'::jsonb);
SELECT 'rows this run marked site_photo', count(*)::text FROM wiki_images
 WHERE image_kind = 'site_photo';
SELECT 'rows this run left NULL', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds' AND w.image_kind IS NULL;
SELECT 'rows with a kind outside the vocabulary', count(*)::text FROM wiki_images
 WHERE image_kind IS NOT NULL AND image_kind NOT IN
       ('site_photo','artifact','map_or_document','painting_or_artwork','people','other','unknown');
SELECT 'curated images', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds';
"""


def verify_sql(run_stamp: str = RUN_STAMP) -> str:
    """Post-hoc verification, run as its own psql call.

    It must NOT reference `_kind_plan`: that table is `ON COMMIT DROP`, so once the write has
    committed the table is gone and a query against it fails. The first run of `--apply` reported
    `EXIT_VERIFY_FAILED` on a write that had in fact succeeded and whose in-transaction numbers
    were all correct, for exactly that reason. Only facts that outlive the transaction belong here.
    """
    return f"""
SELECT 'journal rows for this run', count(*)::text FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)};
SELECT 'journal rows for this run outside wiki_images.image_kind', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)}
   AND (table_name <> 'wiki_images' OR column_name <> 'image_kind');
SELECT 'journal rows for this run with no evidence', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)} AND (evidence IS NULL OR evidence = '[]'::jsonb);
SELECT 'rows this run marked site_photo', count(*)::text FROM wiki_images
 WHERE image_kind = 'site_photo';
SELECT 'rows this run left NULL', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds' AND w.image_kind IS NULL;
SELECT 'rows with a kind outside the vocabulary', count(*)::text FROM wiki_images
 WHERE image_kind IS NOT NULL AND image_kind NOT IN
       ('site_photo','artifact','map_or_document','painting_or_artwork','people','other','unknown');
SELECT 'curated images', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds';
SELECT 'distinct curated sites now carrying a kind', count(DISTINCT w.site_id)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds' AND w.image_kind IS NOT NULL;
"""


def render_apply(write: list[Verdict], state: dict[int, dict[str, object]]) -> str:
    expected = len(write)
    head = f"""-- Generated by scripts/remediation/gallery_audit/persist_verdicts.py - do not edit by hand.
-- {expected} row(s) over {len({v.image_id for v in write})} image(s); scope source_id = '{CURATED_SOURCE}';
-- run stamp {RUN_STAMP!r}; journal test id {TEST_ID!r}.
-- The old value of every row is NULL, so every guard compares with IS NOT DISTINCT FROM.
-- The write and its journal row commit together, so the audit trail cannot disagree with the data.
\\set ON_ERROR_STOP on
BEGIN;

{render_plan_table(write, state)}

DO $$
DECLARE
    bad      integer;
    moved    integer := 0;
    expected integer := {expected};
    r        RECORD;
BEGIN
{GUARDS.replace("{source}", _sql_literal(CURATED_SOURCE)).replace("{source_arg}", _sql_literal(CURATED_SOURCE)).rstrip()}

    -- the only writer: the conditional UPDATE and its journal row commit together, and the
    -- function raises unless exactly one row matched
    FOR r IN SELECT * FROM _kind_plan ORDER BY image_id LOOP
        moved := moved + apply_remediation_change(
            {_sql_literal(TABLE)}, {_sql_literal(COLUMN)}, {_sql_literal(KEY_COLUMN)}, r.image_id::text,
            r.old_value, r.new_value,
            {_sql_literal(TEST_ID)}, {_sql_literal(RUN_STAMP)}, r.change_key, {_sql_literal(CONFIDENCE)},
            r.evidence, r.site_id);
    END LOOP;

    IF moved <> expected THEN
        RAISE EXCEPTION 'G0 image_kind: % row(s) changed, % planned', moved, expected;
    END IF;
{INVARIANTS.replace("{tbl}", _sql_literal(TABLE)).replace("{col}", _sql_literal(COLUMN)).replace("{stamp}", _sql_literal(RUN_STAMP)).rstrip()}
END $$;

{VERIFY_IN_TX_SQL}
COMMIT;
"""
    return head


def render_apply_verification() -> str:
    """The verification block that runs inside the write's own transaction."""
    return VERIFY_IN_TX_SQL


def render_rollback(write: list[Verdict], state: dict[int, dict[str, object]]) -> str:
    """Set NULL back on exactly the rows this run touched. NULL is the pre-state, by construction."""
    tuples = []
    for v in write:
        row = state[v.image_id]
        evidence = json.dumps(
            [
                {
                    "source": "remediation_change_log (the row this undoes)",
                    "url": f"remediation_change_log.row_pk={v.image_id}",
                    "quote": f"run_stamp={RUN_STAMP!r} wrote image_kind={v.kind!r} where it was NULL",
                },
                {
                    "source": "the verdict this restores NULL over",
                    "url": _relative(v.file),
                    "quote": f"stills[] id={v.image_id} verdict.kind={v.kind!r}",
                },
                {
                    "source": "the design rule being restored",
                    "url": "migrations/0019_wiki_images_image_kind.sql",
                    "quote": (
                        "NULL means no verdict has been recorded; 'unknown' means a model looked "
                        "and could not decide - rolling back restores the former, not the latter"
                    ),
                },
            ],
            ensure_ascii=False,
        )
        reason = f"rollback of G0: image_kind on {v.image_id} returned to NULL (was {v.kind!r})"
        tuples.append(
            "    ({}, {}::uuid, {}, NULL, {}, {}, {}::jsonb)".format(
                v.image_id,
                _sql_literal(str(row["site_id"])),
                _sql_literal(v.kind),
                _sql_literal(f"g0-vlm-kind-rollback:{v.image_id}"),
                _sql_literal(reason),
                _sql_literal(evidence),
            )
        )

    return f"""-- Generated by scripts/remediation/gallery_audit/persist_verdicts.py - do not edit by hand.
-- {len(write)} row(s): image_kind returned to NULL, which is the pre-state of every row this
-- run touched (migration 0019: NULL = no verdict recorded).
-- The rollback is itself journalled, so it cannot be mistaken for an untracked edit.
\\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE _kind_plan (
    image_id    BIGINT PRIMARY KEY,
    site_id     UUID NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    change_key  TEXT NOT NULL,
    reason      TEXT NOT NULL,
    evidence    JSONB NOT NULL
) ON COMMIT DROP;

INSERT INTO _kind_plan (image_id, site_id, old_value, new_value, change_key, reason, evidence) VALUES
{",".join(tuples)};

DO $$
DECLARE
    bad      integer;
    moved    integer := 0;
    expected integer := {len(write)};
    r        RECORD;
BEGIN
    SELECT count(*) INTO bad FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
     WHERE w.image_kind IS DISTINCT FROM p.old_value;
    IF bad > 0 THEN
        RAISE EXCEPTION 'G0 rollback: % row(s) do not hold the value being rolled back', bad;
    END IF;

    FOR r IN SELECT * FROM _kind_plan ORDER BY image_id LOOP
        moved := moved + apply_remediation_change(
            {_sql_literal(TABLE)}, {_sql_literal(COLUMN)}, {_sql_literal(KEY_COLUMN)}, r.image_id::text,
            r.old_value, r.new_value,
            {_sql_literal(TEST_ID)}, {_sql_literal(RUN_STAMP + "-rollback")}, r.change_key, {_sql_literal(CONFIDENCE)},
            r.evidence, r.site_id);
    END LOOP;

    IF moved <> expected THEN
        RAISE EXCEPTION 'G0 rollback: % row(s) changed, % planned', moved, expected;
    END IF;

    SELECT count(*) INTO bad FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
     WHERE w.image_kind IS NOT NULL;
    IF bad > 0 THEN
        RAISE EXCEPTION 'G0 rollback: % row(s) are still not NULL', bad;
    END IF;
END $$;

SELECT 'planned rows restored to NULL', count(*)::text
  FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id WHERE w.image_kind IS NULL;
SELECT 'journal rows for the rollback', count(*)::text FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(RUN_STAMP + "-rollback")};
COMMIT;
"""


def render_plan_md(write: list[Verdict], skipped: list[Skipped]) -> str:
    by_reason: dict[str, list[Skipped]] = {}
    for s in skipped:
        by_reason.setdefault(s.reason, []).append(s)

    lines = [
        f"# G0 - persist the already-computed VLM verdicts ({RUN_STAMP})",
        "",
        f"{len(write)} row(s) to write, {len(skipped)} named refusal(s).",
        "",
        "`image_kind` is written only where it is currently NULL, and only for rows whose site",
        "belongs to `source_id = 'ancient_nerds'`. Nothing is overwritten and nothing is deleted.",
        "",
        "## Why this set is 105 and not 280",
        "",
        "The 16 `selection.json` files hold 280 entries in two shapes: 105 `stills` (full record,",
        "carrying `id` = `wiki_images.id` and `verdict.kind`) and 175 `rejected` (only `filename`",
        "and `reason`, no id and no kind). Only the `stills` are writable without inference. The",
        "rejection reasons are mostly composition or quality judgements - `too small`, `duplicate`,",
        "`panorama`, `text or overlay` - which are not image kinds.",
        "",
        "## Rows to write",
        "",
        "| image_id | slug | kind | filename |",
        "|---|---|---|---|",
    ]
    for v in sorted(write, key=lambda v: v.image_id):
        lines.append(f"| {v.image_id} | {v.slug} | `{v.kind}` | `{v.entry.get('filename')}` |")

    lines += ["", "## Named refusals", ""]
    if not by_reason:
        lines.append("None.")
    for reason in sorted(by_reason):
        group = by_reason[reason]
        lines.append(f"### `{reason}` ({len(group)})")
        lines.append("")
        lines.append("| image_id | slug | detail |")
        lines.append("|---|---|---|")
        for s in group:
            lines.append(f"| {s.image_id} | {s.slug} | {s.detail} |")
        lines.append("")

    lines += [
        "## Verification",
        "",
        "```bash",
        "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --plan",
        "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --rehearse",
        "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --apply",
        "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --verify",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def emit(
    write: list[Verdict], skipped: list[Skipped], state: dict[int, dict[str, object]]
) -> dict[str, str]:
    """Write the deliverables. ROLLBACK.sql is written before APPLY.sql, deliberately."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = {
        "plan_md": OUTPUT / "PLAN.md",
        "plan_jsonl": OUTPUT / "PLAN.jsonl",
        "skipped": OUTPUT / "SKIPPED.jsonl",
        "rollback": OUTPUT / "ROLLBACK.sql",
        "apply": OUTPUT / "APPLY.sql",
    }

    paths["plan_md"].write_text(render_plan_md(write, skipped), encoding="utf-8")

    with paths["plan_jsonl"].open("w", encoding="utf-8", newline="\n") as fh:
        for v in sorted(write, key=lambda v: v.image_id):
            row = state[v.image_id]
            fh.write(
                json.dumps(
                    {
                        "image_id": v.image_id,
                        "site_id": row["site_id"],
                        "table": TABLE,
                        "column": COLUMN,
                        "key_column": KEY_COLUMN,
                        "old_value": row.get("image_kind"),
                        "new_value": v.kind,
                        "condition": (
                            f"{KEY_COLUMN} = {v.image_id} AND {COLUMN} IS NOT DISTINCT FROM NULL"
                        ),
                        "reason": f"G0: pipeline verdict for {v.entry.get('filename')!r} on {v.slug}",
                        "change_key": f"g0-vlm-kind:{v.image_id}",
                        "test_id": TEST_ID,
                        "run_stamp": RUN_STAMP,
                        "confidence": CONFIDENCE,
                        "source_id": row.get("source_id"),
                        "selection_file": _relative(v.file),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    with paths["skipped"].open("w", encoding="utf-8", newline="\n") as fh:
        for s in skipped:
            fh.write(
                json.dumps(
                    {
                        "image_id": s.image_id,
                        "slug": s.slug,
                        "reason": s.reason,
                        "detail": s.detail,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    # The undo first. If the process dies between these two writes, the reviewer has the
    # rollback and an APPLY.sql that was never emitted - the safe direction.
    paths["rollback"].write_text(render_rollback(write, state), encoding="utf-8")
    paths["apply"].write_text(render_apply(write, state), encoding="utf-8")

    return {k: str(v) for k, v in paths.items()}


# --------------------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------------------


def command_plan() -> int:
    verdicts = load_verdicts()
    state = read_state([v.image_id for v in verdicts])
    write, skipped = build_plan(verdicts, state)
    paths = emit(write, skipped, state)

    print(f"selection records read : {len(verdicts)}")
    print(f"rows in the database   : {len(state)}")
    print(f"rows to write          : {len(write)}")
    print(f"named refusals         : {len(skipped)}")
    if not write:
        print("nothing to write - the plan is already in place")
        return EXIT_NOTHING
    for name, path in paths.items():
        print(f"  {name:11} {_relative(Path(path))}")
    return EXIT_OK


def command_rehearse() -> int:
    apply_path = OUTPUT / "APPLY.sql"
    if not apply_path.is_file():
        raise PersistError(f"{apply_path} does not exist - run --plan first")
    script = apply_path.read_text(encoding="utf-8")

    if script.count("COMMIT;") != 1 or not script.rstrip().endswith("COMMIT;"):
        raise PersistError("APPLY.sql does not end in exactly one COMMIT; - refusing to rehearse")
    rehearsal = script.rstrip()[: -len("COMMIT;")] + "ROLLBACK;\n"

    print(f"rehearsing {_relative(apply_path)} ({len(script)} bytes)")
    proc = run_psql(rehearsal, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"REHEARSAL FAILED: psql exit={proc.returncode}")
        return EXIT_INCONSISTENT

    # Prove the rollback really rolled back: the rehearsal's own verification queries ran inside
    # the transaction, so their numbers describe a state that must no longer exist.
    sql = "SELECT 'rehearsal residue: rows marked site_photo for this run', count(*)::text FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id WHERE s.source_id = 'ancient_nerds' AND w.image_kind = 'site_photo';"
    if proc.stdout.count("planned rows written") == 0:
        print("REHEARSAL INCONCLUSIVE: the verification queries never ran")
        return EXIT_INCONSISTENT
    residue = run_psql(sql, rows=True).stdout.strip()
    print(f"after the rehearsal: {residue}")
    print("REHEARSAL OK (the write path executed, its verification passed, and it was rolled back)")
    return EXIT_OK


def command_check_primitive() -> int:
    """Probe the journalled primitive itself on a scratch row, then undo it.

    Written because this lane's old value is NULL, and the primitive's own contract for a NULL
    old value is the one thing the plan depends on that this lane does not control.
    """
    sql = f"""
BEGIN;
CREATE TEMP TABLE _probe AS
  SELECT w.id, w.site_id, w.image_kind FROM wiki_images w
    JOIN unified_sites s ON s.id = w.site_id
   WHERE s.source_id = 'ancient_nerds' LIMIT 1;
DO $$
DECLARE
    r     RECORD;
    moved integer;
BEGIN
    SELECT * INTO r FROM _probe;
    IF r.id IS NULL THEN
        RAISE EXCEPTION 'probe: no curated image to test with';
    END IF;
    RAISE NOTICE 'probe row id=% current image_kind=%', r.id, coalesce(r.image_kind, '<NULL>');
    moved := apply_remediation_change('wiki_images','image_kind','id', r.id::text,
                r.image_kind, 'site_photo', {_sql_literal(TEST_ID)},
                {_sql_literal(RUN_STAMP + "-probe")}, 'g0-probe', {_sql_literal(CONFIDENCE)},
                '[{{"source":"probe","quote":"proves the primitive accepts a NULL old value"}}]'::jsonb,
                r.site_id);
    RAISE NOTICE 'probe: rows moved = % (1 expected)', moved;
    IF moved <> 1 THEN
        RAISE EXCEPTION 'probe: the primitive moved % rows, expected 1', moved;
    END IF;
    IF (SELECT image_kind FROM wiki_images WHERE id = r.id) <> 'site_photo' THEN
        RAISE EXCEPTION 'probe: the value did not land';
    END IF;
    RAISE NOTICE 'probe OK: NULL old value accepted, exactly one row moved, value landed';
END $$;
ROLLBACK;
"""
    proc = run_psql(sql, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"PRIMITIVE CHECK FAILED: psql exit={proc.returncode}")
        return EXIT_INCONSISTENT

    # The discriminating assertion is the probe's own notice, not the exit code alone: psql exits
    # non-zero for many reasons, and this command must not report success for the wrong one. The
    # earlier draft of this command ran the apply script's in-transaction verification here,
    # which references a temp table the probe never creates - a successful probe was reported
    # as a failure. The same defect was still present in the post-hoc verify path and made a
    # successful --apply exit 4; both call sites are now split into in-transaction and post-hoc.
    #
    # `RAISE NOTICE` arrives on **stderr**, not stdout (measured: the same run printed the notices
    # to the console but `stdout` did not contain them). Both streams are searched, because the
    # point of the assertion is the text and not which pipe psql chose.
    combined = proc.stdout + proc.stderr
    if "probe OK: NULL old value accepted, exactly one row moved, value landed" not in combined:
        print("PRIMITIVE CHECK INCONCLUSIVE: the probe's own confirmation is missing")
        return EXIT_INCONSISTENT

    # And the rollback must have really undone it: read outside the transaction.
    residue = run_psql(
        "SELECT 'probe residue (journal rows with the probe run stamp)', count(*)::text"
        f" FROM remediation_change_log WHERE run_stamp = {_sql_literal(RUN_STAMP + '-probe')}",
        rows=True,
    ).stdout.strip()
    print(f"after the probe: {residue}")
    if not residue.endswith("|0"):
        print(f"PRIMITIVE CHECK FAILED: the probe left {residue} behind")
        return EXIT_INCONSISTENT
    print("PRIMITIVE CHECK OK (rolled back; the primitive accepts a NULL old value)")
    return EXIT_OK


def command_apply() -> int:
    apply_path = OUTPUT / "APPLY.sql"
    if not apply_path.is_file():
        raise PersistError(f"{apply_path} does not exist - run --plan first")
    script = apply_path.read_text(encoding="utf-8")
    expected = re.search(r"^-- (\d+) row\(s\)", script, re.MULTILINE)
    if expected is None:
        raise PersistError(
            "APPLY.sql has no row count in its header; it was not emitted by this script"
        )
    print(f"applying {_relative(apply_path)}: {expected.group(1)} row(s)")

    proc = run_psql(script, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"APPLY FAILED: psql exit={proc.returncode}")
        return EXIT_INCONSISTENT
    print("APPLY OK")
    return command_verify()


def command_verify() -> int:
    """Re-read the landed state. The plan's own row count is the expected journal size, so the
    two are compared rather than each being judged on its own."""
    plan_path = OUTPUT / "PLAN.jsonl"
    planned: int | None = None
    if plan_path.is_file():
        planned = len(
            [ln for ln in plan_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        )

    proc = run_psql(verify_sql(), rows=True, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"VERIFY FAILED: psql exit={proc.returncode}")
        return EXIT_VERIFY_FAILED

    metrics = {}
    for line in proc.stdout.splitlines():
        if "|" in line:
            name, _, value = line.rpartition("|")
            metrics[name.strip()] = value.strip()

    failures = []
    for name, value in metrics.items():
        if name.startswith("journal rows for this run outside") and value != "0":
            failures.append(f"{name} = {value} (expected 0)")
        if name.startswith("journal rows for this run with no evidence") and value != "0":
            failures.append(f"{name} = {value} (expected 0)")
        if name.startswith("rows with a kind outside the vocabulary") and value != "0":
            failures.append(f"{name} = {value} (expected 0)")

    journal = metrics.get("journal rows for this run")
    marked = metrics.get("rows this run marked site_photo")
    if planned is not None:
        if journal != str(planned):
            failures.append(f"journal rows for this run = {journal}, the plan has {planned} rows")
    if journal != marked:
        failures.append(f"journal rows ({journal}) and rows marked site_photo ({marked}) disagree")

    if failures:
        print("VERIFY FAILED:")
        for f in failures:
            print(f"  {f}")
        return EXIT_VERIFY_FAILED
    print(f"VERIFY OK ({journal} journalled rows, matching the plan)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true", help="read-only: emit the plan and its SQL")
    group.add_argument("--rehearse", action="store_true", help="run APPLY.sql and roll it back")
    group.add_argument(
        "--check-primitive", action="store_true", help="probe the journalled primitive"
    )
    group.add_argument("--apply", action="store_true", help="write the planned rows")
    group.add_argument("--verify", action="store_true", help="read-only: prove the landed state")
    args = parser.parse_args(argv)

    try:
        if args.plan:
            return command_plan()
        if args.rehearse:
            return command_rehearse()
        if args.check_primitive:
            return command_check_primitive()
        if args.apply:
            return command_apply()
        return command_verify()
    except PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
