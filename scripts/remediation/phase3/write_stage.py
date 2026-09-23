"""The writer: one reviewer-confirmed finding becomes one guarded production write.

Piece 6 of the Phase-3 runner (`output/remediation/phase3_runner/PIECE6_BRIEF.md`). The finder and
the reviewer only *propose*; this module is the only part of the pipeline that changes the database,
so a mistake here is not a wasted call but a changed record.

## What a plan is

One **row** is one single-row update: the table, its primary key column, the key, the column, the old
value, the new value, the `test_id` of the finding it came from, the evidence, the reviewer verdict
that authorised it, and a `change_key`. The plan is the batch's rows in the **snapshot's own line
order**, and that order is what `--chunk-size` cuts: "the first 100" is the same 100 on every run and
after a resume, because it is derived from a file's order rather than from which findings happened to
be ready first.

A row is planned only where all of the following hold, and every refusal is counted and named in the
report rather than dropped:

* the reviewer **cleared** it: `review_stage.ReviewVerdict.applies` is `asked and refuted is False and
  not problems`. A refuted, unresolved, unreviewable or problem-carrying verdict stays visible as "not
  applied, and why".
* the reviewer's own `WHY:` line does not **name a failing half** (`review_stage.failing_half`): a
  `REFUTED: NO` means "both halves hold", and a sentence that says a half fails contradicts it
  (`RULE_REVIEW_CONTRADICTS`, 2026-09-23).
* the finder's own answer (`answers/<site>%2F<field>.txt`, read with `discover_stage.parse_answer`)
  is a complete `WRONG` with a `PROPOSED:` value. The proposal is **not** in `model.json` - the
  `judgements` there are call records - so the answer text is the only place it exists, and the stored
  value comes from the batch's own record (`discover_stage.field_finding`).
* every page the finder cites is a page **this batch fetched**, and every quoted sentence occurs in
  the text stored for it (`discover_stage.source_problems`, over the same excerpts the finder's prompt
  was built from: `model_stage.evidence_excerpts` on the batch's `evidence/` and `fetch.json`). This is
  what `AUDIT_LOG.md` promised piece 6 would do and what the writer did not do until 2026-09-22:
  measured then, 44 of the 994 rows already in production and 2 of the 80 planned-but-unwritten rows
  carry a citation that fails this check (quotes with an ellipsis, re-typed Wikidata JSON, a URL that
  was never fetched). A row whose citation cannot be found in the evidence is refused as
  `finder-citation-not-in-evidence`; a batch whose evidence is missing *with nothing recorded about
  it* raises, because that is a hole in the record rather than a property of one row. A citation of
  a MiniMax **search hit** is checked against the page `phase3/hit_stage.py` fetched from the hit,
  never against its snippet: a hit whose page could not be fetched or read, or whose page was cut at
  the page cap before the quote, is refused as `RULE_HIT_UNVERIFIED`, and one the stage never tried
  raises (2026-09-23).
* a `period_start` change **leaves the stored value's bucket** (`categorize_period`, the card's own):
  a move inside it is refused as `RULE_SAME_BUCKET`, because the value is a bucket sort key.
* the field is one the run was **built to ask**. A lane that re-asks only some fields of a site (the
  gap run re-asks the 5 empty-stream and the 37 no-verdict fields of 42 sites, whose other fields the
  mass run already decided and partly wrote) names them in the record's `rerun_fields`; a field outside
  that list is refused as `field-not-asked-in-this-run` even if the finder answered it and the
  reviewer cleared it, so a lane can never re-decide a field it was not planned for. A record without
  the key is the whole site, as every record before 2026-09-22 was. The list is read by
  `search_evidence.rerun_fields`, the one parser the discover pass reads it with too, so the writer
  and the finder cannot disagree about which fields a run asked.
* the field has a table (`snapshot_plan.FIELD_STORED_IN`), the value is a **fixed point** of every
  producer that rewrites the column on a container start (below), and it is a real change in the
  column's own shape (`docs/procedures/FIELD_CONTRACT.md` §3).

## The fixed-point table, as the code has it

| column | producer | rule | verdict |
| --- | --- | --- | --- |
| `unified_sites.site_type` | `pipeline/lyra/orchestrator.py:1476-1488`, every start | `normalize_site_type(value) == value` | re-checked per row, by the producer's own function |
| `unified_sites.country` | `pipeline/lyra/data_patches.py:48-61` (`fix_countries`) | that UPDATE is guarded `source_id = 'lyra' AND country IS NULL` | **writable**: no `ancient_nerds` row is re-derived |
| `unified_sites.period_start` | `pipeline/lyra/data_patches.py:64-78` (`backfill_periods`) | guarded `source_id = 'lyra' AND period_start IS NULL` | **writable**, same reason |
| `unified_sites.description` | none | text regeneration is Phase 5 | **report-only**, refused |
| `card_stats.card_description` | `api/main.py:506` -> `api/services/card_descriptions.py:35-48`, every API boot | an upsert from `public/data/card_descriptions.json` | **report-only**, refused |
| `unified_sites.name_normalized` | `pipeline/lyra/orchestrator.py:1694-1702` | `left(lower(unaccent(value)), 500)`, which no offline check can evaluate | **cannot be reached here**: `snapshot_plan.FIELD_STORED_IN` has no table for the column, so the plan refuses it as `no-table-mapping`. If that mapping ever grows the column, this table has to grow with it - a branch keyed on `unaccent` would be code no test could reach |

The `site_type` check calls `model.site_type_fixed_point`, i.e. the boot producer's own function, so
there is no second spelling of the normalisation; a value the normaliser would rewrite is refused with
the producer's name in the reason. `country` and `period_start` are writable for the reason their
producers' own `WHERE` clauses give, read rather than assumed - both guard on `source_id = 'lyra'`. The
brief's table calls `fix_countries()` an overwriter of every row in the column; the code says
otherwise and the code is the authority.

## The transaction, and the four guards

`APPLY.sql` is one transaction: `\\set ON_ERROR_STOP on`, `BEGIN;`, a temp plan table
`ON COMMIT DROP`, the guards, the `apply_remediation_change` loop, `moved <> expected`, two post-loop
invariants, `COMMIT;`, then post-commit reads. The guards are

1. every planned row is an existing `source_id='ancient_nerds'` site;
2. every planned row is a real, writable change (the column allowlist, no empty or unchanged value);
3. every planned row still holds the old value the plan names (`IS DISTINCT FROM`, which is
   `NOT (IS NOT DISTINCT FROM)` and, unlike `=`, is true for a NULL old value - the primitive's own
   conditional `WHERE` is literally `IS NOT DISTINCT FROM $3::<column type>`, `0018`);
4. after the loop: every row holds the new value, and the journal and the plan agree **row for row in
   both directions** (a plan row with no journal row, a journal row with other values, and a journal
   row for this run stamp outside the plan are each a refusal).

Nothing is `DELETE`d, no schema is changed, and nothing outside `source_id='ancient_nerds'` is
touched.

## The digest, and what it refuses

`APPLY.sql` and `ROLLBACK.sql` each carry `-- plan digest sha256:<hex>` over the rows they were
generated from, and the apply path refuses when the digest of the plan it is handed is not the pinned
one. The older `--apply` path (`mechanical/apply.py`, `[H] SECURITY 3 / BACKEND B7`) reads `APPLY.sql`
with no cryptographic tie to the plan; that defect is not copied here. The run stamp is a function of
`(batch_id, chunk index)` rather than a clock reading, so a re-render is byte-identical and a resume
finds the same chunk under the same name.

## The step size, and the check after every step

`--chunk-size` defaults to **100**, the owner's step of 2026-09-21 ("in 100er schritten updaten, nach
100 immer prüfung"). The unit is a *row* - one UPDATE and one journal entry - so a chunk of 100 rows
touches at most 100 sites and never more; a site carrying two writable fields is checked twice rather
than made to wait for the next 100. Per chunk, in this order:

1. a **pre-flight** read-only read of the same named rows: a row that no longer holds the planned
   old value is recorded with the value it holds now, and the chunk is **not written at all** - it
   was generated from the chunk as a whole, so writing the rest would be writing a plan that no
   longer exists. The batch carries on with the next chunk, which is the brief's zero-row case
   answered from the database rather than from a warning;
2. the transaction above, once every row of the chunk still holds the value the plan names;
3. **read-back**: every applied row re-read and compared against the intended value, for the same
   named sites, plus the journal in both directions. A count cannot tell "absent" from "changed",
   which is why the comparison is per row;
4. the **inverse**: `ROLLBACK.sql` is run as-is (it ends in `ROLLBACK;`, the way
   `scripts/remediation/0018_migration_selftest.sql` proves its cases), its own in-transaction
   invariant asserts the rows are back at the old value, and the read-back afterwards proves the undo
   left both data and journal exactly as the write left them.

A chunk whose read-back or inverse disagrees **raises** and chunk *n+1* is never sent: that is the
whole point of the step size, and a run that carried on would accumulate 99 successors behind a
discovery made at the end.

## The one seam

Every statement goes through `run_sql`, the module-level seam (`ssh <host> docker exec -i
ancient_nerds_db psql ... -v ON_ERROR_STOP=1`), and every function that talks to a database takes it
as a parameter. Tests substitute a recorder, assert on the exact SQL text and on the comparison logic,
and never open a socket or point anything at production.

Dry run is the default: without `--apply` nothing is sent, no pre-flight is run, and the report says
so.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import hashlib
import json
import shlex
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[3]

# Dual use: `python -m phase3.write_stage` and `python scripts/remediation/phase3/write_stage.py`.
# Same shim as `run.py`: the package is not installed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model as M  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402  - the finder's own evidence excerpts
from phase3 import review_stage as RS  # noqa: E402  - the reviewer's own `applies`, not a copy
from phase3 import search_evidence as SE  # noqa: E402  - the one parser of a run's `rerun_fields`
from phase3 import snapshot_plan as SP  # noqa: E402
from phase3.run import (
    DISCOVER_PASS,  # noqa: E402  - the batch marker this stage needs
    InputError,  # noqa: E402  - one spelling per concept, not a second
)

# `pipeline` is importable once `search_evidence` has put the repository root on the path.
from pipeline.utils.text import categorize_period  # noqa: E402  - the card's own buckets

#: The only source this stage writes. The same value as `mechanical.plan.CURATED_SOURCE`; the
#: mechanical lane is not imported here because it drags its own data readers (Natural Earth, census
#: fetch) into every phase-3 process.
CURATED_SOURCE = "ancient_nerds"
SSH_HOST = "ancientnerds"
#: `-v ON_ERROR_STOP=1` on every call: without it psql walks past a failed statement and commits an
#: empty transaction, which is indistinguishable from success.
PSQL = "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1"
#: `-t -A`: the read-backs are parsed, so psql prints one value per line with no decoration.
PSQL_ROWS = PSQL + " -t -A"

#: The owner's step (2026-09-21): 100 rows per chunk, a check after every one.
DEFAULT_CHUNK_SIZE = 100
INPUT_FILE = "input.json"
REVIEW_FILE = "review.json"
ANSWERS_DIR = "answers"
#: The batch's own evidence and fetch report: what the finder's prompt quoted, and why a target that
#: has no file has none. The citation check reads both, exactly as the finder stage did.
EVIDENCE_DIR = "evidence"
FETCH_REPORT_FILE = "fetch.json"
WRITES_DIR = "writes"
PLAN_FILE = "PLAN.jsonl"
REFUSED_FILE = "REFUSED.jsonl"
REPORT_FILE = "REPORT.json"
CHUNKS_DIR = "chunks"
APPLY_FILE = "APPLY.sql"
ROLLBACK_FILE = "ROLLBACK.sql"

#: The header both SQL files carry. `pinned_digest` reads it; a file without it is refused, because
#: "no digest" and "the digest matches" must not look alike.
DIGEST_HEADER = "-- plan digest sha256:"
#: The journal's identity for one row's *reversal*. The two directions of one transition are two
#: transitions (`mechanical.apply.rollback_change_key`), so they cannot share a key - otherwise the
#: reversal reads as a duplicate of the write it undoes.
ROLLBACK_KEY_SUFFIX = "-rollback"

#: The primary key column per table a planned value can come from. `card_stats` has no `id` column -
#: its key is `site_id` (`scripts/remediation/0018_migration_selftest.sql`, case C3) - which is why
#: the column is named per table rather than assumed. Only `unified_sites` carries a writable field
#: (`description` is report-only and `card_description` is), so no `card_stats` row can be planned.
PK_COLUMN: dict[str, str] = {"unified_sites": "id", "card_stats": "site_id"}

#: What the column holds. `docs/procedures/FIELD_CONTRACT.md` §3, verified against
#: `information_schema.columns` on production 2026-09-20: a varchar limit, or `None` for an integer
#: column whose only shape rule is that it parses as one.
COLUMN_SHAPE: dict[str, int | None] = {"country": 100, "site_type": 100, "period_start": None}

#: The columns this stage may write: every planned field minus the report-only ones, derived so the
#: set cannot drift from `snapshot_plan.FIELD_STORED_IN` / `model.REPORT_ONLY_FIELDS`.
WRITABLE_COLUMNS: tuple[str, ...] = tuple(sorted(set(SP.FIELD_STORED_IN) - M.REPORT_ONLY_FIELDS))

#: How the stored value of a column is compared with a planned one, in SQL. `period_start` is an
#: integer, so the planned text is cast to it - the same cast `apply_remediation_change` performs, and
#: a value that cannot be cast fails the guard loudly rather than writing a wrong year. The keys must
#: be exactly `WRITABLE_COLUMNS`
#: (`test_every_writable_column_has_a_comparison_in_the_guards`), because a column
#: without an entry here has no guard and would pass every comparison vacuously.
COLUMN_COMPARE: dict[str, str] = {
    "country": "u.country IS DISTINCT FROM {planned}",
    "site_type": "u.site_type IS DISTINCT FROM {planned}",
    "period_start": "u.period_start IS DISTINCT FROM {planned}::integer",
}

#: Why the two text fields are report-only, not writable. The reasons differ and must not be merged
#: into "not supported": one is a boot overwriter, the other a phase split. `model.Finding` already
#: refuses both; the writer refuses them again from its own reason, so the refusal cannot depend on
#: which stage read the brief.
REPORT_ONLY_REASON: dict[str, str] = {
    "description": (
        "report-only in Phase 3: `unified_sites.description` has no boot overwriter, but the text "
        "regeneration that would produce a better one is Phase 5, not a SQL update"
    ),
    "card_description": (
        "report-only in Phase 3: `card_stats.card_description` is re-derived on every API boot "
        "(`api/main.py:506` -> `api/services/card_descriptions.py:35-48`, an upsert into "
        "`card_stats`), so a database-only write is reverted at the next start"
    ),
}

#: The journal's `confidence`. The reviewer read the same evidence the finder had, so a second
#: *independent* source does not exist and `two_source` would be a lie; one page that states the value
#: is what `authoritative` means (`census.model.Confidence`).
CONFIDENCE = M.Confidence.AUTHORITATIVE.value

#: The rules a row can be refused by. The report counts refusals by rule rather than by prose.
RULE_REVIEWER = "reviewer-did-not-clear"
RULE_NO_VERDICT = "no-reviewer-verdict"
RULE_NO_ANSWER = "finder-answer-missing"
RULE_NO_PROPOSAL = "finder-proposed-nothing"
RULE_ANSWER_PROBLEMS = "finder-answer-has-problems"
RULE_REPORT_ONLY = "report-only-field"
RULE_FIXED_POINT = "not-a-fixed-point"
RULE_NO_TABLE = "no-table-mapping"
RULE_SHAPE = "not-writable-in-the-columns-shape"
RULE_NOT_A_CHANGE = "not-a-change"
RULE_TEST_ID = "foreign-test-id"
RULE_MATCHED_0 = "matched-0"
#: The finder cited a page this batch never fetched, or a sentence that is not in the page it stored.
#: The reviewer may still have cleared it - the reviewer judges the claim, not the citation's bytes -
#: which is why the writer checks it itself (`discover_stage.source_problems`, the finder's own rule).
RULE_CITATION = "finder-citation-not-in-evidence"
#: The field is not one the run was built to ask (the record's `rerun_fields`, read by
#: `search_evidence.rerun_fields`).
RULE_NOT_RERUN = "field-not-asked-in-this-run"
#: A `period_start` change inside the stored value's bucket is not an error - the value is a bucket
#: sort key (`FIELD_CLAUSE['period_start']`, the plan's false alarm 4.3.1). The bucket is
#: `pipeline.utils.text.categorize_period`, the card's own, lower bound inclusive. Added 2026-09-23:
#: the search pilot decided Aubrey Holes `-4500 -> -4000` wrong against a human CORRECT, and 170 of
#: the 389 `period_start` rows the mass lane wrote are such moves (production journal, read-only).
RULE_SAME_BUCKET = "period-start-inside-the-stored-bucket"
#: The finder cited a MiniMax search hit whose page this batch could not verify: the page was not
#: fetched, the fetch failed, it is not text a quote can be found in, or it was cut at the fetch
#: stage's page cap and its read part does not carry the quote (`_hit_page_refusal`). A snippet is
#: not a page (2026-09-23: the pilot's Las Labradas quote was a travel page's snippet about another
#: site), so such a citation is never accepted on the snippet.
RULE_HIT_UNVERIFIED = "search-hit-page-not-verified"
#: The reviewer cleared the finding (`REFUTED: NO`, "both halves hold") while its own `WHY:` line
#: names a half that fails (`review_stage.failing_half`). Added 2026-09-23 after the pilot's Lake
#: Mungo and Odeon rows; the mass lane met the same class by hand in its 72 held rows.
RULE_REVIEW_CONTRADICTS = "reviewer-why-names-a-failing-half"
#: Carried by a `RULE_REVIEW_CONTRADICTS` refusal whose phrase held correctly cleared rows on the mass
#: lane (`review_stage.HAND_READ_PHRASES`): the row is not written, and it is read by hand before it
#: counts as refused.
HAND_READ_NOTE = "hand-read before it counts as refused (HUMAN_ONLY.md B12)"


class WriteRefused(ValueError):
    """The plan, the digest or the input is not what this stage will write. Raised, never worked
    around."""


class ReadBackFailed(WriteRefused):
    """The database did not come back holding what the plan names. A STOP, not a warning."""


class InverseFailed(WriteRefused):
    """A chunk's reversal did not undo exactly the chunk just written. A STOP, too."""


class SqlRunner(Protocol):
    """One statement in, psql's own output out. The only way this module reaches a database."""

    def __call__(self, sql: str, *, host: str) -> str: ...


def run_sql(sql: str, *, host: str = SSH_HOST, timeout: int = 900) -> str:
    """The seam: `sql` is sent to production the way this project does it - ssh, then psql.

    Every statement in this module goes through here, and every caller takes the runner as a
    parameter, so a test can record the exact text instead of opening a socket. A non-zero exit is
    refused rather than read: with `ON_ERROR_STOP` on, the exit code is what says the transaction was
    not committed.
    """
    proc = subprocess.run(
        shlex.split(f"ssh {host} {PSQL_ROWS}"),
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise WriteRefused(f"psql exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}".strip())
    return proc.stdout


def _exec(runner: SqlRunner | None, sql: str, *, host: str) -> str:
    return (runner or run_sql)(sql, host=host)


def utf8_streams() -> None:
    """Reconfigure stdout and stderr to UTF-8 (unencodable characters replaced) before anything is
    printed. The writers' drivers print site names before they write the first row, so a console
    that cannot encode one - measured 2026-09-22: a cp1252 console died on U+0259 with nothing
    written - would otherwise kill a whole write wave. The one home of this for every writer tool
    (`write_gate.py`, `phase4/write4.exit_line`); a stream without `reconfigure` (a test's capture)
    is left as it is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _sql_text(value: str | None) -> str:
    """A text literal, or `NULL` for a value the row does not have.

    Never coalesced to `''`: an empty string and an absent value are two different stored states, and
    `IS NOT DISTINCT FROM` - which every guard here uses - tells them apart.
    """
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _json_rows(text: str) -> list[dict[str, Any]]:
    """The JSON objects one read printed, one per line. Anything else is refused, not skipped.

    `to_jsonb(...)::text` is how the reads return, because a value containing the field separator (or
    a newline) would silently shift a `psql` column and turn one row into two or into none. jsonb
    output escapes both, so one row is always exactly one line.
    """
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WriteRefused(f"read-back line {number} is not JSON: {exc}") from None
        if not isinstance(payload, dict):
            raise WriteRefused(f"read-back line {number} is not a JSON object: {line[:80]}")
        rows.append(payload)
    return rows


# ------------------------------------------------------------------------------------- the plan
#: The journal lanes a change key can name: this stage's own, and the three row groups of phases 4
#: and 5 (design entry [6], production_write, JOURNAL: `change_key(..., lane='phase4'|'phase4l'|
#: 'phase5')` - the descriptions, the legacy disclosure and the cards). Closed: a key prefixed with
#: a lane nobody registered would name a family no acceptance reads.
CHANGE_KEY_LANES: tuple[str, ...] = ("phase3", "phase4", "phase4l", "phase5")


def change_key(
    *,
    site_id: str,
    table: str,
    column: str,
    old_value: str | None,
    new_value: str | None,
    test_id: str,
    lane: str = "phase3",
) -> str:
    """The digest that names one transition: sha256 over the six parts, JSON-encoded.

    JSON rather than a joined string because the parts cannot then be re-split differently, and a
    digest rather than a readable label because two transitions of one row must be distinguishable
    (`old -> new` and `new -> old` are two) while the same transition re-derived is the same key. The
    `<lane>:` prefix says which lane produced it; the mechanical lane's keys are
    `country-canonical:<uuid>` and the lanes never name the same row.

    `lane` defaults to `phase3`, and for it the key is byte for byte the one this function returned
    before the parameter existed (WB-D1; pinned by `test_the_phase3_change_key_is_byte_identical`),
    so the 994 journalled phase-3 keys stay reproducible. `new_value` may be `None` only for a
    phase-5 card clear (`P5/card-clear`, the one row group that writes NULL); this stage never
    plans one (`validate_rows`).
    """
    if lane not in CHANGE_KEY_LANES:
        raise WriteRefused(
            f"change_key lane {lane!r} is not one of {list(CHANGE_KEY_LANES)}: a key names the "
            "journal family its acceptance reads"
        )
    parts = json.dumps(
        [site_id, table, column, old_value, new_value, test_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"{lane}:" + hashlib.sha256(parts.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WriteRow:
    """One single-row update: the plan's unit and the transaction's unit."""

    site_id: str
    site_name: str
    table: str
    pk_column: str
    pk: str
    column: str
    old_value: str | None
    new_value: str
    test_id: str
    evidence: tuple[dict[str, Any], ...]
    verdict: dict[str, Any]  #: the reviewer verdict that authorised this row, verbatim
    change_key: str

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["evidence"] = [dict(entry) for entry in self.evidence]
        payload["verdict"] = dict(self.verdict)
        return payload

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def plan_digest(rows: Sequence[WriteRow]) -> str:
    """sha256 over the rows' canonical JSON lines: no timestamp, no dict order, LF only.

    The rows *are* the plan, so this covers every field the SQL is generated from - the change keys
    included - which is what makes the pin on `APPLY.sql` a statement about the plan rather than about
    a file that happens to have the right name.
    """
    body = "".join(row.to_json_line() + "\n" for row in rows)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Refusal:
    """A field the plan looked at and did not write, with the rule that refused it.

    `rule` is from a fixed vocabulary so the report can count refusals by cause; `detail` is the
    measured fact or the producer's name, because a count without a reason is what this record exists
    to prevent.
    """

    site_id: str
    field: str
    rule: str
    detail: str

    def to_json_line(self) -> str:
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False, sort_keys=True)


@dataclass
class WritePlan:
    """One batch's write plan: the rows, and every field it looked at and refused."""

    batch_id: str
    pass_name: str | None
    rows: list[WriteRow] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)

    def refused_fields(self, rule: str) -> list[Refusal]:
        return [r for r in self.refusals if r.rule == rule]

    def refusals_by_rule(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for refusal in self.refusals:
            counts[refusal.rule] = counts.get(refusal.rule, 0) + 1
        return dict(sorted(counts.items()))


def _fixed_point_refusal(field_name: str, value: str) -> tuple[str, str] | None:
    """(rule, reason) for a value a producer would rewrite, or `None` when it survives every one.

    The producer is named in the reason because "refused" alone is not actionable: a refused
    `site_type` needs the normaliser's name and the line it runs from. Only the columns the plan can
    actually reach arrive here (`snapshot_plan.FIELD_STORED_IN` minus the report-only fields), and of
    those only `site_type` has a producer that rewrites the value.
    """
    if field_name == "site_type" and not M.site_type_fixed_point(value):
        return (
            RULE_FIXED_POINT,
            f"`{value}` is not a site_type fixed point: "
            "pipeline.normalizers.site_type.normalize_site_type would rewrite it on the next "
            "container start (pipeline/lyra/orchestrator.py:1476-1488), so the write would be a "
            "temporary edit rather than a correction",
        )
    return None


def _shape_refusal(field_name: str, value: str) -> str | None:
    """Why this value does not fit the column, or `None` when it does.

    The database refuses both cases itself - a value too long for a varchar is caught by the
    primitive's round-trip check, an integer cast by the planner - but it refuses *inside* the
    transaction, taking the chunk's other 99 rows with it. The plan-side check refuses the one row and
    counts it, which is what the report is for.
    """
    if field_name not in COLUMN_SHAPE:
        return f"no column shape is known for {field_name!r}, so nothing can be checked against it"
    limit = COLUMN_SHAPE[field_name]
    if limit is not None:
        if len(value) > limit:
            return (
                f"the value is {len(value)} characters and `{field_name}` holds {limit} "
                "(`docs/procedures/FIELD_CONTRACT.md` §3)"
            )
        return None
    try:
        int(value)
    except ValueError:
        return (
            f"`{value}` is not an integer year: `unified_sites.{field_name}` is an integer column "
            "(`docs/procedures/FIELD_CONTRACT.md` §3), and the primitive would cast it"
        )
    return None


def same_bucket(old_value: str | None, new_value: str) -> str | None:
    """The bucket two `period_start` years share (`categorize_period`), or `None` when they differ.

    A field that stores nothing has no bucket to stay inside, so filling it is never "the same
    bucket". Both values must be years: an old value that is not one is a damaged record and raises.
    Used by the writer (`RULE_SAME_BUCKET`) and by the measurement of the rows already written
    (`output/remediation/tools/measure_review_holds.py`), so the two cannot count differently.
    """
    if old_value is None:
        return None
    bucket = categorize_period(int(old_value))
    return bucket if categorize_period(int(new_value)) == bucket else None


def _same_bucket_refusal(
    site_id: str, field_name: str, old_value: str | None, new_value: str
) -> Refusal | None:
    """`RULE_SAME_BUCKET` for a `period_start` move inside the stored value's bucket, else `None`.

    Both values are years by now (`_shape_refusal` has read the new one, and the old one is the
    column's own integer).
    """
    if field_name != "period_start":
        return None
    bucket = same_bucket(old_value, new_value)
    if bucket is None:
        return None
    return Refusal(
        site_id,
        field_name,
        RULE_SAME_BUCKET,
        f"`{old_value}` and `{new_value}` both lie in `{bucket}` "
        "(pipeline.utils.text.categorize_period, lower bound inclusive): a period_start change "
        "inside the stored value's bucket is not an error - the value is a bucket sort key",
    )


def _evidence_for(
    *, answer: DS.DiscoverAnswer, verdict: RS.ReviewVerdict
) -> tuple[dict[str, Any], ...]:
    """The journalled evidence: the finder's cited pages, and the reviewer's own reason.

    Built through `census.model.Evidence` rather than from a re-split of the URL, so the source label
    is the model's own `host`. The reviewer's verdict is added as a last entry with no URL: the
    journal is what a human reads when asking why a row changed, and "the finder said so" without "and
    the reviewer did not refute it" is half the answer. That entry is not a second independent source
    and is not counted as one.
    """
    entries: list[dict[str, Any]] = []
    for claim in answer.sources:
        evidence = M.Evidence(source="finder-answer", url=claim.url, quote=claim.quote)
        entries.append({**dataclasses.asdict(evidence), "host": evidence.host})
    entries.append(
        {
            "source": "reviewer",
            "url": None,
            "quote": verdict.reason,
            "retrieved_at": None,
            "host": "reviewer",
        }
    )
    return tuple(entries)


def _verdict_reason(cleared: RS.ReviewVerdict) -> str:
    """The reviewer's own words, plus which of the four ways it declined to clear the finding."""
    if not cleared.asked:
        why = f"nobody was asked: {cleared.unreviewable}"
    elif cleared.problems:
        why = f"the answer has problems: {'; '.join(cleared.problems)}"
    elif cleared.refuted is True:
        why = "the reviewer refuted the finding"
    elif cleared.refuted is None:
        why = "the reviewer could not settle it (UNRESOLVED)"
    else:  # not reachable through `applies`, and named rather than assumed
        why = "the verdict is not one this writer can act on"
    return f"{why}; reason: {cleared.reason}"


def _tristate(value: Any) -> bool | None:
    """The review's `refuted`: true, false or null. Anything else is not a verdict to read."""
    if value is None or isinstance(value, bool):
        return value
    raise InputError(f"the review's `refuted` is {value!r}; it is true, false or null")


def rebuilt_verdict(raw: Mapping[str, Any]) -> RS.ReviewVerdict:
    """One verdict from `review.json`, rebuilt as the object that owns the rule.

    The file also carries an `applies` boolean, and reading *that* would make the writer trust a
    derived field: it is a copy of `asked and refuted is False and not problems`, and a copy can
    disagree with the three conditions it was derived from (`review_stage.ReviewVerdict.applies`).
    The rule for "a writer may act here" belongs to the stage that owns it, so the verdict is
    rebuilt from its parts and the file's own boolean is never consulted.
    """
    sources = tuple(
        DS.SourceClaim(url=str(claim.get("url")), quote=str(claim.get("quote")))
        for claim in raw.get("sources") or ()
    )
    return RS.ReviewVerdict(
        site_id=str(raw.get("site_id") or ""),
        field=str(raw.get("field") or ""),
        refuted=_tristate(raw.get("refuted")),
        reason=str(raw.get("reason") or ""),
        sources=sources,
        problems=tuple(str(problem) for problem in raw.get("problems") or ()),
        unreviewable=None if raw.get("unreviewable") is None else str(raw["unreviewable"]),
    )


def cited_evidence(
    *,
    site_id: str,
    site: Mapping[str, Any],
    evidence: F.EvidenceStore,
    failures: Mapping[str, str] | None,
) -> list[MS.EvidenceExcerpt]:
    """The site's evidence as the stages read it: the excerpts a citation is checked against.

    Built by the finder's own function (`model_stage.evidence_excerpts`) over the batch's own store
    and its reports, so a fetched target a citation is checked against is byte for byte the page the
    finder was shown - not a re-fetch, and not a second spelling of which targets a site buys. A
    target the fetch stage recorded as failed has no text and is therefore not a page a quote can
    come from; a target with no file and no recorded failure raises `model_stage.EvidenceUnusable`,
    as it does for the finder. A search hit is checked against the page `phase3/hit_stage.py`
    fetched from it (`discover_stage.pages_from_excerpts`), never against its snippet.
    """
    return MS.evidence_excerpts(
        site_id=site_id, site=site, store=evidence, hit_pages=True, failures=failures
    )


def _hand_read(phrase: str) -> str:
    """The hand-read marker for a phrase that misfired on written rows, or nothing."""
    if phrase not in RS.HAND_READ_PHRASES:
        return ""
    false, held = RS.HAND_READ_PHRASES[phrase]
    return (
        f" - {HAND_READ_NOTE}: on the mass lane this phrase held {false} of {held} written rows "
        "whose own sentence argued for the write"
    )


def _hit_page_refusal(
    *,
    site_id: str,
    field_name: str,
    answer: DS.DiscoverAnswer,
    evidence: Sequence[MS.EvidenceExcerpt],
) -> Refusal | None:
    """`RULE_HIT_UNVERIFIED` when a search hit the finder cites has no page that can verify its
    quote, else `None` (then the citation check reads the page as it reads any other).

    Two ways a hit page cannot verify: it could not be fetched or read (`citable is None`), or it was
    cut at the fetch stage's page cap and its read part does not carry the quote. The second is not
    a fabricated citation - the rest of the page was never read - and on the first pilot it was the
    common case: 14 of the 15 stored hit pages were cut, and all 9 citations whose readable page did
    not carry the quote were on cut pages (2026-09-23, the fixer's review). A cited hit nobody tried
    to verify raises in `model_stage.cited_hit_pages`.
    """
    pages = {
        page.url: page
        for page in MS.cited_hit_pages(
            [claim.url for claim in answer.sources], evidence, where=f"{site_id}/{field_name}"
        )
    }
    for claim in answer.sources:
        page = pages.get(claim.url)
        if page is None:
            continue
        if page.citable is None:
            return Refusal(
                site_id,
                field_name,
                RULE_HIT_UNVERIFIED,
                f"the finder cites the search hit {page.url}, and its page cannot verify the quote "
                f"({page.failure}); a snippet is not a page, so the citation is not accepted on it",
            )
        if page.truncated and not DS.quote_occurs(claim.quote, page.citable):
            return Refusal(
                site_id,
                field_name,
                RULE_HIT_UNVERIFIED,
                f"the finder cites the search hit {page.url}, whose page was cut at the fetch "
                f"stage's {F.MAX_PAGE_BYTES:,}-byte page cap (fetch_stage.MAX_PAGE_BYTES), and the "
                f"part that was read does not carry the quote {claim.quote!r}; the rest was never "
                "read, so the citation is neither verified nor shown to be fabricated",
            )
    return None


def _row_for(
    *,
    site_id: str,
    site_name: str,
    site: Mapping[str, Any],
    field_name: str,
    cleared: RS.ReviewVerdict,
    answers: F.EvidenceStore,
    excerpts: Callable[[], Sequence[MS.EvidenceExcerpt]],
) -> WriteRow | Refusal:
    """The row for one cleared finding, or the refusal that stands in its place - never both.

    `excerpts` is called only for a finding that got as far as the citation check, so a batch whose
    rows are all refused earlier never reads its evidence.
    """
    if field_name in M.REPORT_ONLY_FIELDS:
        return Refusal(site_id, field_name, RULE_REPORT_ONLY, REPORT_ONLY_REASON[field_name])
    if field_name not in SP.FIELD_STORED_IN or field_name not in COLUMN_COMPARE:
        return Refusal(
            site_id,
            field_name,
            RULE_NO_TABLE,
            f"neither `phase3.snapshot_plan.FIELD_STORED_IN` nor a column comparison knows "
            f"{field_name!r}, so there is no statement this writer could render",
        )

    path = answers.path_for(site_id, field_name)
    if not path.exists():
        return Refusal(
            site_id,
            field_name,
            RULE_NO_ANSWER,
            f"{path} does not exist: the finder's proposal lives in its answer text, so there is "
            "nothing to write from",
        )
    answer = DS.parse_answer(path.read_text(encoding="utf-8"))
    if answer.problems:
        return Refusal(
            site_id,
            field_name,
            RULE_ANSWER_PROBLEMS,
            "the finder's answer is not shaped as asked: " + "; ".join(answer.problems),
        )
    if answer.verdict != "WRONG" or not answer.proposed:
        return Refusal(
            site_id,
            field_name,
            RULE_NO_PROPOSAL,
            f"the finder's verdict is {answer.verdict!r} and it proposes {answer.proposed!r}, so "
            "there is no value to write",
        )
    evidence = excerpts()
    unverified = _hit_page_refusal(
        site_id=site_id, field_name=field_name, answer=answer, evidence=evidence
    )
    if unverified is not None:
        return unverified
    citation = DS.source_problems(answer, DS.pages_from_excerpts(evidence))
    if citation:
        return Refusal(
            site_id,
            field_name,
            RULE_CITATION,
            "the finder's citation is not in the evidence this batch fetched "
            "(discover_stage.source_problems): " + "; ".join(citation),
        )

    finding = DS.field_finding(site, field_name)
    test_id = str(finding.get("test_id") or "")
    if not test_id.startswith(SP.TEST_ID_PREFIX):
        return Refusal(
            site_id,
            field_name,
            RULE_TEST_ID,
            f"test_id {test_id!r} does not start with {SP.TEST_ID_PREFIX!r} "
            "(`phase3.snapshot_plan.TEST_ID_PREFIX`)",
        )
    stored = finding.get("current_value")
    old_value = None if stored is None else str(stored)
    new_value = answer.proposed

    refused = _fixed_point_refusal(field_name, new_value)
    if refused is not None:
        return Refusal(site_id, field_name, refused[0], refused[1])
    shape = _shape_refusal(field_name, new_value)
    if shape is not None:
        return Refusal(site_id, field_name, RULE_SHAPE, shape)
    if not new_value.strip():
        return Refusal(site_id, field_name, RULE_NOT_A_CHANGE, "the proposed value is empty")
    if new_value == old_value:
        return Refusal(
            site_id,
            field_name,
            RULE_NOT_A_CHANGE,
            f"the row already holds {old_value!r}: a write would journal a change that is not one",
        )
    inside = _same_bucket_refusal(site_id, field_name, old_value, new_value)
    if inside is not None:
        return inside

    table = SP.FIELD_STORED_IN[field_name]
    return WriteRow(
        site_id=site_id,
        site_name=site_name,
        table=table,
        pk_column=PK_COLUMN[table],
        pk=site_id,
        column=field_name,
        old_value=old_value,
        new_value=new_value,
        test_id=test_id,
        evidence=_evidence_for(answer=answer, verdict=cleared),
        verdict=cleared.to_dict(),
        change_key=change_key(
            site_id=site_id,
            table=table,
            column=field_name,
            old_value=old_value,
            new_value=new_value,
            test_id=test_id,
        ),
    )


def build_plan(
    *,
    batch: Mapping[str, Any],
    review: Mapping[str, Any],
    answers: F.EvidenceStore,
    evidence: F.EvidenceStore,
    fetch_failures: Mapping[str, Mapping[str, str]],
) -> WritePlan:
    """Turn one batch's reviewer verdicts into the rows a guarded write can be rendered from.

    It refuses rather than skips: a site or field without a usable verdict is recorded with its rule,
    so an empty plan cannot be mistaken for a batch where everything was already right.

    `evidence` and `fetch_failures` are required, not defaulted: they are what the citation check
    reads (`cited_evidence`), and a writer that could be called without them would be a writer that
    could skip the check.
    """
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    if review.get("batch_id") != batch_id:
        raise InputError(
            f"the review is for batch {review.get('batch_id')!r}, the input for {batch_id!r}: "
            "refusing to join two batches"
        )
    pass_name = batch.get("pass")
    if pass_name != DISCOVER_PASS:
        raise InputError(
            f"batch {batch_id}: this writer applies the discover pass's per-field verdicts; this "
            f"batch carries pass={pass_name!r}"
        )
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"batch {batch_id}: batch carries no sites")
    verdicts = review.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        raise InputError(f"batch {batch_id}: the review carries no verdicts")

    by_field: dict[tuple[str, str], RS.ReviewVerdict] = {}
    for raw in verdicts:
        rebuilt = rebuilt_verdict(raw)
        key = (rebuilt.site_id, rebuilt.field)
        if key in by_field:
            raise InputError(f"batch {batch_id}: two verdicts for {key[1]} of {key[0]}")
        by_field[key] = rebuilt

    plan = WritePlan(batch_id=batch_id, pass_name=str(pass_name))
    for site in sites:
        site_id = str(site.get("site_id") or "")
        if not site_id:
            raise InputError(f"batch {batch_id}: a site record carries no site_id")
        site_name = str(site.get("name") or "")
        try:
            # The discover pass's own parser: the writer and the finder read one list one way.
            asked = SE.rerun_fields(site)
        except InputError as exc:
            raise InputError(f"batch {batch_id}: {exc}") from exc
        # Read once per site, and only when a finding reaches the citation check.
        excerpts = functools.cache(
            functools.partial(
                cited_evidence,
                site_id=site_id,
                site=site,
                evidence=evidence,
                failures=fetch_failures.get(site_id),
            )
        )
        for field_name in DS.DISCOVER_FIELDS:
            if asked is not None and field_name not in asked:
                plan.refusals.append(
                    Refusal(
                        site_id,
                        field_name,
                        RULE_NOT_RERUN,
                        f"batch {batch_id} was built to ask {sorted(asked)} of this site; "
                        f"{field_name} was decided elsewhere and is not re-decided here",
                    )
                )
                continue
            cleared = by_field.get((site_id, field_name))
            if cleared is None:
                plan.refusals.append(
                    Refusal(
                        site_id,
                        field_name,
                        RULE_NO_VERDICT,
                        f"batch {batch_id} holds no reviewer verdict for this field",
                    )
                )
                continue
            if not cleared.applies:
                plan.refusals.append(
                    Refusal(site_id, field_name, RULE_REVIEWER, _verdict_reason(cleared))
                )
                continue
            failing = RS.failing_half(cleared.reason)
            if failing is not None:
                plan.refusals.append(
                    Refusal(
                        site_id,
                        field_name,
                        RULE_REVIEW_CONTRADICTS,
                        f"the reviewer answered REFUTED: NO (both halves hold), and its own WHY "
                        f"line names a failing half ({failing!r}){_hand_read(failing)}; "
                        f"reason: {cleared.reason}",
                    )
                )
                continue
            decided = _row_for(
                site_id=site_id,
                site_name=site_name,
                site=site,
                field_name=field_name,
                cleared=cleared,
                answers=answers,
                excerpts=excerpts,
            )
            if isinstance(decided, WriteRow):
                plan.rows.append(decided)
            else:
                plan.refusals.append(decided)
    validate_rows(plan.rows)
    return plan


def validate_rows(rows: Sequence[WriteRow]) -> None:
    """The plan-side mirror of the transaction's guards. Pure, so a test can break each one.

    The database guards are the authority (`render_apply`); this exists so a corrupted plan is refused
    *before* a statement is rendered as well as inside the transaction - and so a plan that would
    abort a 100-row chunk can be corrected row by row instead.
    """
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.site_id, row.column)
        if key in seen:
            raise WriteRefused(f"{row.site_id}/{row.column} appears twice - the plan is not a set")
        seen.add(key)
        try:
            uuid.UUID(row.site_id)
        except ValueError:
            raise WriteRefused(f"{row.site_id!r} is not a UUID") from None
        if row.table != "unified_sites":
            raise WriteRefused(f"{row.site_id}: this stage writes unified_sites, not {row.table!r}")
        if PK_COLUMN.get(row.table) != row.pk_column:
            raise WriteRefused(
                f"{row.site_id}: {row.table}.{row.pk_column} is not the table's key "
                f"({PK_COLUMN.get(row.table)!r})"
            )
        if row.pk != row.site_id:
            raise WriteRefused(f"{row.site_id}: pk {row.pk!r} is not the site id")
        if row.column not in WRITABLE_COLUMNS:
            raise WriteRefused(
                f"{row.site_id}: {row.column!r} is not writable (writable: {list(WRITABLE_COLUMNS)})"
            )
        if not row.test_id.startswith(SP.TEST_ID_PREFIX):
            raise WriteRefused(f"{row.site_id}: test_id {row.test_id!r} has the wrong prefix")
        if not row.new_value.strip():
            raise WriteRefused(f"{row.site_id}: no new value - this stage never clears a column")
        if row.new_value == row.old_value:
            raise WriteRefused(
                f"{row.site_id}: old and new are both {row.new_value!r} - not a change"
            )
        shape = _shape_refusal(row.column, row.new_value)
        if shape is not None:
            raise WriteRefused(f"{row.site_id}: {shape}")
        if not row.evidence:
            raise WriteRefused(f"{row.site_id}: a write without evidence is not auditable")
        if row.verdict.get("applies") is not True:
            raise WriteRefused(
                f"{row.site_id}: the row's own reviewer verdict does not clear it "
                f"(applies={row.verdict.get('applies')!r})"
            )
        expected = change_key(
            site_id=row.site_id,
            table=row.table,
            column=row.column,
            old_value=row.old_value,
            new_value=row.new_value,
            test_id=row.test_id,
        )
        if row.change_key != expected:
            raise WriteRefused(
                f"{row.site_id}: change_key {row.change_key!r} is not the digest of the row"
            )


def load_plan(batch_dir: Path) -> WritePlan:
    """Read one batch's inputs - record, review, answers, evidence, fetch report - and plan it."""
    return build_plan(
        batch=_load_json(batch_dir / INPUT_FILE),
        review=_load_json(batch_dir / REVIEW_FILE),
        answers=F.EvidenceStore(batch_dir / ANSWERS_DIR),
        evidence=F.EvidenceStore(batch_dir / EVIDENCE_DIR),
        fetch_failures=MS.read_fetch_failures(batch_dir / FETCH_REPORT_FILE),
    )


# ----------------------------------------------------------------------------------- the chunks
@dataclass(frozen=True)
class Chunk:
    """One step: the rows to write, their digest, and the run stamp that names them."""

    batch_id: str
    index: int  #: 1-based
    rows: tuple[WriteRow, ...]

    @property
    def label(self) -> str:
        return f"chunk-{self.index:04d}"

    @property
    def stamp(self) -> str:
        """The journal's `run_stamp` for this chunk, derived rather than clocked.

        `apply_remediation_change` requires one per row (`0018`), and a value derived from the batch
        and the chunk index means a re-render is byte-identical and a resume finds the same chunk
        under the same name - without a schema change to carry a chunk id.
        """
        return f"phase3:{self.batch_id}:{self.label}"

    @property
    def rollback_stamp(self) -> str:
        """The reversal's own stamp: a write and its undo are two runs, not one."""
        return self.stamp + ROLLBACK_KEY_SUFFIX

    @property
    def digest(self) -> str:
        return plan_digest(self.rows)

    @property
    def site_ids(self) -> tuple[str, ...]:
        return tuple(sorted({row.site_id for row in self.rows}))


def chunks_for(plan: WritePlan, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[Chunk]:
    """Cut the plan into chunks **in its own order**: the snapshot's line order, then field order.

    `rows[start:start + chunk_size]` on a list that came out of `build_plan` is stable across runs and
    across a resume, because its order is a property of the files rather than of which findings were
    ready first. An empty plan yields no chunk at all, so "there is nothing to write" cannot look like
    a chunk that wrote nothing.
    """
    if chunk_size < 1:
        raise WriteRefused(f"--chunk-size {chunk_size}: at least one row per chunk")
    rows = plan.rows
    return [
        Chunk(batch_id=plan.batch_id, index=index, rows=tuple(rows[start : start + chunk_size]))
        for index, start in enumerate(range(0, len(rows), chunk_size), start=1)
    ]


# ------------------------------------------------------------------------------------ rendering
def _value_comparison(planned: str) -> list[str]:
    """One `OR (...)` clause per writable column, comparing the row against `planned`.

    One helper for both sides (`p.old_value`, `p.new_value`) so guard 3 and invariant 1 cannot drift:
    they are the same question asked about two different values.
    """
    lines: list[str] = []
    for column in WRITABLE_COLUMNS:
        expression = COLUMN_COMPARE.get(column)
        if expression is None:
            raise WriteRefused(
                f"{column!r} is writable but has no comparison in COLUMN_COMPARE: a guard that "
                "cannot name the column would pass for that column vacuously"
            )
        lines.append(
            f"        OR (p.column_name = {_sql_text(column)} AND "
            f"{expression.format(planned=planned)})"
        )
    return lines


def _plan_table_ddl() -> list[str]:
    return [
        "CREATE TEMP TABLE _phase3_plan (",
        "    site_id     UUID NOT NULL,",
        "    column_name TEXT NOT NULL,",
        "    pk_column   TEXT NOT NULL,",
        "    pk          TEXT NOT NULL,",
        "    old_value   TEXT,",
        "    new_value   TEXT NOT NULL,",
        "    change_key  TEXT NOT NULL,",
        "    test_id     TEXT NOT NULL,",
        "    evidence    JSONB NOT NULL,",
        "    reviewer    JSONB NOT NULL,",
        "    -- one row per (site, column): two rows for one column of one site would be two writes",
        "    -- of one transition, and the second would journal a change it did not make. The key",
        "    -- refuses that here rather than after the fact.",
        "    PRIMARY KEY (site_id, column_name)",
        ") ON COMMIT DROP;",
    ]


def _insert_values(rows: Sequence[WriteRow], *, reversal: bool) -> list[str]:
    """The plan's rows as an INSERT, in the plan's own order.

    `reversal` swaps the two values and suffixes the change key: the undo of one transition is the
    other transition, and it needs its own identity in the journal.
    """
    lines = [
        "INSERT INTO _phase3_plan (site_id, column_name, pk_column, pk, old_value, new_value,",
        "                          change_key, test_id, evidence, reviewer) VALUES",
    ]
    body = []
    for row in rows:
        key = row.change_key + (ROLLBACK_KEY_SUFFIX if reversal else "")
        old, new = (row.new_value, row.old_value) if reversal else (row.old_value, row.new_value)
        body.append(
            "    ("
            + ", ".join(
                [
                    f"{_sql_text(row.site_id)}::uuid",
                    _sql_text(row.column),
                    _sql_text(row.pk_column),
                    _sql_text(row.pk),
                    _sql_text(old),
                    _sql_text(new),
                    _sql_text(key),
                    _sql_text(row.test_id),
                    f"{_sql_text(json.dumps(list(row.evidence), ensure_ascii=False))}::jsonb",
                    f"{_sql_text(json.dumps(row.verdict, ensure_ascii=False, sort_keys=True))}::jsonb",
                ]
            )
            + ")"
        )
    lines.append(",\n".join(body) + ";")
    return lines


def _header(*, chunk: Chunk, reversal: bool, generator: str) -> list[str]:
    what = "reversal" if reversal else "write"
    lines = [
        f"-- Generated by {generator} - do not edit by hand.",
        f"{DIGEST_HEADER}{chunk.digest}",
        f"-- batch {chunk.batch_id}, {chunk.label}: the {what} of {len(chunk.rows)} row(s) over "
        f"{len(chunk.site_ids)} site(s); scope source_id = '{CURATED_SOURCE}'.",
    ]
    if reversal:
        lines.append(f"-- this file reverses run stamp '{chunk.stamp}'.")
    else:
        lines.append(
            f"-- run stamp '{chunk.stamp}'; every row's old value is in its own conditional WHERE."
        )
    lines.append(
        "-- Each row goes through apply_remediation_change(table, column, pk_col, pk, old, new,"
    )
    lines.append(
        "-- test_id, run_stamp, change_key, confidence, evidence, site_id) - the 12 arguments of"
    )
    lines.append("-- migrations/0018_remediation_change_log_boolean.sql, in that order.")
    lines.append("\\set ON_ERROR_STOP on")
    lines.append("BEGIN;")
    return lines


def _old_value_guard() -> list[str]:
    """Guard 3: the row must still hold the old value the plan names."""
    return [
        "    SELECT count(*) INTO bad",
        "      FROM _phase3_plan p JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE 1 = 0",
        *_value_comparison("p.old_value"),
        "       ;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'phase3 write: % planned row(s) no longer hold the planned "
        "old value', bad;",
        "    END IF;",
    ]


def render_apply(
    chunk: Chunk, *, generator: str = "scripts/remediation/phase3/write_stage.py"
) -> str:
    """One transaction that writes the chunk and journals every row, or writes nothing."""
    if not chunk.rows:
        raise WriteRefused("refusing to render a transaction with no rows")
    out = _header(chunk=chunk, reversal=False, generator=generator)
    add = out.append
    add("")
    out.extend(_plan_table_ddl())
    add("")
    out.extend(_insert_values(chunk.rows, reversal=False))
    add("")
    add("DO $$")
    add("DECLARE")
    add("    bad      INTEGER;")
    add("    moved    INTEGER := 0;")
    add(f"    expected INTEGER := {len(chunk.rows)};")
    add("    r        RECORD;")
    add("BEGIN")
    add("    -- expected is the plan's own row count, rendered here, and not a second count of the")
    add("    -- temp table the loop below iterates: counting the same rows twice would make the")
    add("    -- comparison after the loop a tautology.")
    add("")
    add(
        "    -- guard 2: the plan is a set of rows this stage may write, each of them a real change."
    )
    add("    -- The column allowlist is rendered from snapshot_plan.FIELD_STORED_IN minus")
    add(
        "    -- model.REPORT_ONLY_FIELDS, so a plan naming a column no producer leaves alone cannot"
    )
    add("    -- reach the loop; a column missing from the comparisons below cannot pass either.")
    add("    SELECT count(*) INTO bad FROM _phase3_plan p")
    add("     WHERE p.pk_column <> 'id'")
    columns = ", ".join(_sql_text(column) for column in WRITABLE_COLUMNS)
    add(f"        OR p.column_name NOT IN ({columns})")
    add("        OR p.new_value = '' OR p.new_value IS NOT DISTINCT FROM p.old_value;")
    add("    IF bad > 0 THEN")
    add("        RAISE EXCEPTION 'phase3 write: % planned row(s) are not writable changes', bad;")
    add("    END IF;")
    add("")
    add("    -- guard 1: every planned row is a curated site that still exists. The source name is")
    add("    -- a RAISE argument and not part of the message text: a name spliced into a message")
    add("    -- only parses while the name happens to contain no quote.")
    add("    SELECT count(*) INTO bad")
    add("      FROM _phase3_plan p LEFT JOIN unified_sites u ON u.id = p.site_id")
    add(f"     WHERE u.id IS NULL OR u.source_id <> {_sql_text(CURATED_SOURCE)};")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'phase3 write: % planned row(s) are not % sites', bad, "
        f"{CURATED_SOURCE};"
    )
    add("    END IF;")
    add("")
    add("    -- guard 3: every planned row still holds the old value the plan names.")
    add(
        "    -- IS DISTINCT FROM is NOT (IS NOT DISTINCT FROM), and unlike `=` it is true for a NULL"
    )
    add("    -- old value - `col = NULL` is never true and would silently match zero rows. The")
    add("    -- primitive's own conditional WHERE is the same test from the other side:")
    add("    -- `IS NOT DISTINCT FROM $3::<column type>` (migrations/0018, item [H]).")
    out.extend(_old_value_guard())
    add("")
    add(
        "    -- the only writer: the conditional UPDATE and its journal row commit together, and the"
    )
    add("    -- function raises unless exactly one row matched")
    add("    FOR r IN SELECT * FROM _phase3_plan ORDER BY site_id, column_name LOOP")
    add("        moved := moved + apply_remediation_change(")
    add("            'unified_sites', r.column_name, r.pk_column, r.pk,")
    add("            r.old_value, r.new_value,")
    add(f"            r.test_id, {_sql_text(chunk.stamp)}, r.change_key, {_sql_text(CONFIDENCE)},")
    add("            r.evidence, r.site_id);")
    add("    END LOOP;")
    add("")
    add("    IF moved <> expected THEN")
    add("        RAISE EXCEPTION 'phase3 write: % row(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    add("    -- invariant 1: every planned row now holds the new value")
    add("    SELECT count(*) INTO bad")
    add("      FROM _phase3_plan p JOIN unified_sites u ON u.id = p.site_id")
    add("     WHERE 1 = 0")
    out.extend(_value_comparison("p.new_value"))
    add("       ;")
    add("    IF bad > 0 THEN")
    add("        RAISE EXCEPTION 'phase3 write: % planned row(s) do not hold the new value', bad;")
    add("    END IF;")
    add("")
    add(
        "    -- invariant 2: the journal and the plan agree row for row, in both directions - every"
    )
    add("    -- planned row has its journal row, and this run stamp journals nothing else")
    add("    SELECT count(*) INTO bad")
    add("      FROM _phase3_plan p LEFT JOIN remediation_change_log l")
    add("        ON l.row_pk = p.pk AND l.table_name = 'unified_sites'")
    add("       AND l.column_name = p.column_name")
    add(f"       AND l.run_stamp = {_sql_text(chunk.stamp)}")
    add("     WHERE l.id IS NULL")
    add("        OR l.new_value IS DISTINCT FROM p.new_value")
    add("        OR l.old_value IS DISTINCT FROM p.old_value;")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'phase3 write: % planned row(s) have no matching journal row', "
        "bad;"
    )
    add("    END IF;")
    add("")
    add("    SELECT count(*) INTO bad FROM remediation_change_log l")
    add(f"     WHERE l.run_stamp = {_sql_text(chunk.stamp)}")
    add("       AND NOT EXISTS (SELECT 1 FROM _phase3_plan p WHERE p.change_key = l.change_key);")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'phase3 write: this run stamp journalled % row(s) outside the "
        "plan', bad;"
    )
    add("    END IF;")
    add("")
    add("    RAISE NOTICE 'phase3 write: % row(s) changed and journalled, % planned',")
    add("        moved, expected;")
    add("END $$;")
    add("")
    add("COMMIT;")
    add("")
    add(
        POST_COMMIT_READS.format(
            run_stamp=_sql_text(chunk.stamp),
            rollback_stamp=_sql_text(chunk.rollback_stamp),
            source=_sql_text(CURATED_SOURCE),
        )
    )
    return "\n".join(out)


POST_COMMIT_READS = """\
-- Post-commit read: the numbers the report quotes, from the database, not from this plan.
SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT 'journal rows for the rollback stamp', count(*)::text
  FROM remediation_change_log WHERE run_stamp = {rollback_stamp}
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source}
UNION ALL
-- `_phase3_plan` is a CREATE TEMP TABLE, so it lives in this session's `pg_temp_N` schema and
-- `nspname = 'public'` could never match it. `to_regclass` resolves the current session's temp
-- schema and returns NULL once the table is gone, so this reads 1 exactly when one was left behind.
SELECT 'temp table _phase3_plan left behind',
       (to_regclass('pg_temp._phase3_plan') IS NOT NULL)::int::text
"""


def render_rollback(
    chunk: Chunk, *, generator: str = "scripts/remediation/phase3/write_stage.py"
) -> str:
    """The chunk's inverse, proven in a transaction that is rolled back.

    The shape is `scripts/remediation/0018_migration_selftest.sql`'s: the reversal runs for real
    inside `BEGIN; ... ROLLBACK;`, its own post-loop invariant asserts the rows are back at the old
    value *inside* the transaction, and the reads after the `ROLLBACK` assert that nothing of the
    reversal survived. So the reversal is exercised - guards, loop and journal - without keeping it,
    and the proof needs no second copy of the data.
    """
    if not chunk.rows:
        raise WriteRefused("refusing to render the reversal of a chunk with no rows")
    out = _header(chunk=chunk, reversal=True, generator=generator)
    add = out.append
    add("-- The reversal is itself rolled back: this file proves the inverse on the real rows and")
    add("-- keeps none of it, so the write it reverses stays exactly as it was.")
    add("")
    out.extend(_plan_table_ddl())
    add("")
    out.extend(_insert_values(chunk.rows, reversal=True))
    add("")
    add("DO $$")
    add("DECLARE")
    add("    bad      INTEGER;")
    add("    moved    INTEGER := 0;")
    add(f"    expected INTEGER := {len(chunk.rows)};")
    add("    r        RECORD;")
    add("BEGIN")
    add("    -- guard: every planned row still holds the value the write left behind - the planned")
    add("    -- old value of the reversal, which is the write's new value (swapped in the INSERT)")
    add("    SELECT count(*) INTO bad")
    add("      FROM _phase3_plan p JOIN unified_sites u ON u.id = p.site_id")
    add("     WHERE 1 = 0")
    out.extend(_value_comparison("p.old_value"))
    add("       ;")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'phase3 rollback: % planned row(s) do not hold the written "
        "value', bad;"
    )
    add("    END IF;")
    add("")
    add("    FOR r IN SELECT * FROM _phase3_plan ORDER BY site_id, column_name LOOP")
    add("        moved := moved + apply_remediation_change(")
    add("            'unified_sites', r.column_name, r.pk_column, r.pk,")
    add("            r.old_value, r.new_value,")
    add(f"            r.test_id, {_sql_text(chunk.rollback_stamp)}, r.change_key,")
    add(f"            {_sql_text(CONFIDENCE)}, r.evidence, r.site_id);")
    add("    END LOOP;")
    add("")
    add("    IF moved <> expected THEN")
    add("        RAISE EXCEPTION 'phase3 rollback: % row(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    add("    -- the inverse, asserted inside the transaction: every row is back at the old value")
    add("    SELECT count(*) INTO bad")
    add("      FROM _phase3_plan p JOIN unified_sites u ON u.id = p.site_id")
    add("     WHERE 1 = 0")
    out.extend(_value_comparison("p.new_value"))
    add("       ;")
    add("    IF bad > 0 THEN")
    add("        RAISE EXCEPTION 'phase3 rollback: % row(s) are not back at the old value', bad;")
    add("    END IF;")
    add("")
    add("    -- and the reversal's own journal agrees with it")
    add("    SELECT count(*) INTO bad")
    add("      FROM _phase3_plan p LEFT JOIN remediation_change_log l")
    add("        ON l.row_pk = p.pk AND l.table_name = 'unified_sites'")
    add("       AND l.column_name = p.column_name")
    add(f"       AND l.run_stamp = {_sql_text(chunk.rollback_stamp)}")
    add("     WHERE l.id IS NULL")
    add("        OR l.new_value IS DISTINCT FROM p.new_value")
    add("        OR l.old_value IS DISTINCT FROM p.old_value;")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'phase3 rollback: % planned row(s) have no matching journal "
        "row', bad;"
    )
    add("    END IF;")
    add("")
    add(
        "    RAISE NOTICE 'phase3 rollback: % row(s) reversed inside a transaction about to be "
        "rolled back', moved;"
    )
    add("END $$;")
    add("")
    add("ROLLBACK;")
    add("")
    add(
        ROLLBACK_READS.format(
            run_stamp=_sql_text(chunk.stamp),
            rollback_stamp=_sql_text(chunk.rollback_stamp),
            source=_sql_text(CURATED_SOURCE),
        )
    )
    return "\n".join(out)


ROLLBACK_READS = """\
-- After the ROLLBACK: the write must be exactly as it was where it was, and the reversal gone.
-- These are the log lines; `check the inverse` compares the same rows value by value, because a
-- count cannot tell "absent" from "changed".
SELECT 'journal rows for the write stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT 'journal rows for the rollback stamp (must be 0)', count(*)::text
  FROM remediation_change_log WHERE run_stamp = {rollback_stamp}
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source}
UNION ALL
SELECT 'temp table _phase3_plan left behind',
       (to_regclass('pg_temp._phase3_plan') IS NOT NULL)::int::text
"""


def pinned_digest(sql: str) -> str:
    """The digest the statement was generated from. A statement without one is refused."""
    for line in sql.splitlines():
        if line.startswith(DIGEST_HEADER):
            return line[len(DIGEST_HEADER) :].strip()
    raise WriteRefused(f"this statement carries no {DIGEST_HEADER!r} line; refusing to run it")


def assert_pinned(sql: str, rows: Sequence[WriteRow], *, what: str) -> str:
    """Refuse unless `sql` was generated from exactly these rows.

    This is the check the older `--apply` path is missing (`[H] SECURITY 3 / BACKEND B7`): a file on
    disk can be regenerated, hand-edited or left over from another plan, and only a digest over the
    rows makes it the statement for *this* plan.
    """
    want = plan_digest(rows)
    pinned = pinned_digest(sql)
    if pinned != want:
        raise WriteRefused(
            f"{what} is pinned to plan {pinned[:16]}, the plan it is being run for is {want[:16]}: "
            "refusing to run a statement that was generated from different rows"
        )
    return pinned


def write_chunk_files(out: Path, chunk: Chunk) -> tuple[Path, Path]:
    """Write the chunk's two statements, the reversal first.

    The rollback is generated before the apply so a chunk that cannot be undone is visible before
    anything is written - the mechanical lane's rule (`mechanical/apply.py:emit` refuses an apply
    whose rollback is missing).
    """
    directory = out / CHUNKS_DIR / chunk.label
    directory.mkdir(parents=True, exist_ok=True)
    rollback_path = directory / ROLLBACK_FILE
    apply_path = directory / APPLY_FILE
    rollback_path.write_text(render_rollback(chunk), encoding="utf-8", newline="\n")
    apply_path.write_text(render_apply(chunk), encoding="utf-8", newline="\n")
    return apply_path, rollback_path


def write_plan_files(out: Path, plan: WritePlan, *, chunks: Sequence[Chunk]) -> None:
    """Write the plan, the refusals and every chunk's two statements. Deterministic bytes."""
    out.mkdir(parents=True, exist_ok=True)
    (out / PLAN_FILE).write_text(
        "".join(row.to_json_line() + "\n" for row in plan.rows), encoding="utf-8", newline="\n"
    )
    (out / REFUSED_FILE).write_text(
        "".join(refusal.to_json_line() + "\n" for refusal in plan.refusals),
        encoding="utf-8",
        newline="\n",
    )
    for chunk in chunks:
        write_chunk_files(out, chunk)


# ------------------------------------------------------------------------ reads and comparison
def same_value(*, observed: Any, planned: str | None, column: str) -> bool:
    """Does the value the read returned equal the planned one?

    The reads return JSON, so an integer column comes back as a number while the plan carries a text
    value; the comparison happens in the column's own type (`COLUMN_SHAPE[column] is None` means an
    integer column) rather than by re-spelling the value here. `None` means the field stores nothing,
    which is a value of its own: `''` and `NULL` are two different stored states.
    """
    if planned is None or observed is None:
        return observed is None and planned is None
    if COLUMN_SHAPE.get(column) is None:
        try:
            return int(planned) == int(observed)
        except (TypeError, ValueError):
            return False
    return str(observed) == planned


def stored_values_sql(*, column: str, site_ids: Sequence[str]) -> str:
    """The value each named row holds now, one JSON object per row.

    Used for the pre-flight (before the write) and the read-back (after it): the same question asked
    twice. The column is spliced into the statement, which is why it must be one of
    `WRITABLE_COLUMNS` - checked here rather than trusted.
    """
    if column not in WRITABLE_COLUMNS:
        raise WriteRefused(f"{column!r} is not writable, so it cannot be read back this way")
    ids = ", ".join(f"{_sql_text(site_id)}::uuid" for site_id in site_ids)
    return (
        "-- the value each named row holds now: one JSON object per row\n"
        "\\pset footer off\n"
        "SELECT to_jsonb(t)::text FROM (\n"
        f"  SELECT u.id::text AS id, u.{column} AS value, u.source_id AS source_id\n"
        "    FROM unified_sites u\n"
        f"   WHERE u.id IN ({ids})\n"
        ") t ORDER BY 1"
    )


def journal_rows_sql(*, change_keys: Sequence[str], run_stamp: str) -> str:
    """The journal rows of the named changes written under one run stamp, as JSON.

    The stamp is part of the question, not only of the comparison: a change key names a transition,
    not a write, so a batch written again after a revert (a Phase-4/5 write round) journals the same
    keys under a second stamp, and one round's read-back must never read the other round's row.
    """
    keys = ", ".join(_sql_text(key) for key in change_keys)
    return (
        "-- the journal rows of this chunk's changes, one JSON object per row\n"
        "\\pset footer off\n"
        "SELECT to_jsonb(t)::text FROM (\n"
        "  SELECT l.row_pk, l.table_name, l.column_name, l.change_key, l.old_value, l.new_value,\n"
        "         l.test_id, l.run_stamp\n"
        "    FROM remediation_change_log l\n"
        f"   WHERE l.change_key IN ({keys}) AND l.run_stamp = {_sql_text(run_stamp)}\n"
        ") t ORDER BY 1"
    )


def journal_mismatches(
    rows: Sequence[WriteRow],
    *,
    run_stamp: str,
    run_sql_runner: SqlRunner | None = None,
    host: str = SSH_HOST,
) -> list[str]:
    """Every planned row against its journal row of `run_stamp`, field for field.

    A row without a journal row, and a journal row whose table, column, key, values, test id or stamp
    differ from the plan, is a mismatch. Shared by every writer's read-back (Phase 3's `read_back`,
    Phase 4's `write4.read_back`), so the two cannot ask the journal different questions. The rows
    are duck-typed: anything with `site_id`, `column`, `change_key`, `pk`, `table`, `old_value`,
    `new_value` and `test_id`.
    """
    journal = {
        str(entry["change_key"]): entry
        for entry in _json_rows(
            _exec(
                run_sql_runner,
                journal_rows_sql(change_keys=[row.change_key for row in rows], run_stamp=run_stamp),
                host=host,
            )
        )
    }
    mismatches: list[str] = []
    for row in rows:
        entry = journal.get(row.change_key)
        if entry is None:
            mismatches.append(f"{row.site_id}/{row.column}: no journal row for {row.change_key}")
            continue
        for field_name, wanted in (
            ("row_pk", row.pk),
            ("table_name", row.table),
            ("column_name", row.column),
            ("old_value", row.old_value),
            ("new_value", row.new_value),
            ("test_id", row.test_id),
            ("run_stamp", run_stamp),
        ):
            if entry.get(field_name) != wanted:
                mismatches.append(
                    f"{row.site_id}/{row.column}: the journal's {field_name} is "
                    f"{entry.get(field_name)!r}, the plan says {wanted!r}"
                )
    return mismatches


def journal_count_sql(*, run_stamp: str) -> str:
    """How many journal rows one run stamp has, whatever their keys."""
    return (
        "-- how many journal rows this stamp has, whatever their keys\n"
        "\\pset footer off\n"
        "SELECT count(*)::text FROM remediation_change_log "
        f"WHERE run_stamp = {_sql_text(run_stamp)}"
    )


def journal_rows_for_stamp(
    run_stamp: str, *, run_sql_runner: SqlRunner | None = None, host: str = SSH_HOST
) -> int:
    """The count itself - used to prove that the reversal kept none of its rows."""
    text = _exec(run_sql_runner, journal_count_sql(run_stamp=run_stamp), host=host)
    stripped = text.strip()
    return int(stripped.splitlines()[-1]) if stripped else 0


@dataclass(frozen=True)
class Preflight:
    """What the rows held when the write was about to be run."""

    held: tuple[WriteRow, ...]
    not_held: tuple[Refusal, ...]


def preflight(
    chunk: Chunk, *, run_sql_runner: SqlRunner | None = None, host: str = SSH_HOST
) -> Preflight:
    """Read the chunk's rows back before writing: rows that moved are dropped and named.

    A row whose value moved since the snapshot invalidates *that row's* plan entry (brief §4.3): the
    write affects 0 rows and says so, rather than overwriting a change somebody else made. The
    remaining rows go through together, which is why this is a read before the write and not a warning
    after it. The result keeps the plan's own order (`chunk.rows`), so a resumed chunk is the same
    statement it was.
    """
    held: list[WriteRow] = []
    not_held: list[Refusal] = []
    by_column: dict[str, list[WriteRow]] = {}
    for row in chunk.rows:
        by_column.setdefault(row.column, []).append(row)
    for column in sorted(by_column):
        rows = by_column[column]
        text = _exec(
            run_sql_runner,
            stored_values_sql(column=column, site_ids=[row.site_id for row in rows]),
            host=host,
        )
        current = {str(entry["id"]): entry for entry in _json_rows(text)}
        for row in rows:
            observed = current.get(row.site_id)
            if observed is None:
                not_held.append(
                    Refusal(
                        row.site_id,
                        column,
                        RULE_MATCHED_0,
                        f"no unified_sites row with id {row.site_id}",
                    )
                )
                continue
            if observed.get("source_id") != CURATED_SOURCE:
                not_held.append(
                    Refusal(
                        row.site_id,
                        column,
                        RULE_MATCHED_0,
                        f"source_id is {observed.get('source_id')!r}, not {CURATED_SOURCE!r}",
                    )
                )
                continue
            if not same_value(observed=observed.get("value"), planned=row.old_value, column=column):
                not_held.append(
                    Refusal(
                        row.site_id,
                        column,
                        RULE_MATCHED_0,
                        f"the row holds {observed.get('value')!r}, the plan names the old value "
                        f"{row.old_value!r}",
                    )
                )
                continue
            held.append(row)
    order = {id(row): index for index, row in enumerate(chunk.rows)}
    return Preflight(held=tuple(sorted(held, key=lambda r: order[id(r)])), not_held=tuple(not_held))


@dataclass(frozen=True)
class ReadBack:
    """The result of comparing every applied row against the plan, after the fact."""

    checked: int
    held: int
    journal_rows: int
    mismatches: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches and self.checked > 0 and self.checked == self.held

    def describe(self) -> str:
        head = (
            f"{self.held}/{self.checked} row(s) hold the planned value, "
            f"{self.journal_rows} journal row(s) for this run stamp"
        )
        return head if self.ok else head + ": " + "; ".join(self.mismatches)


def read_back(
    chunk: Chunk, *, run_sql_runner: SqlRunner | None = None, host: str = SSH_HOST
) -> ReadBack:
    """Re-read the written rows and the journal, and compare row for row.

    Every applied value is compared against the intended one for the same named site, and a site the
    read does not return is a mismatch rather than a smaller number. The journal is read the other way
    round too: a row of this run stamp whose `change_key` is not in the plan is a mismatch, so a
    statement that wrote more than it said cannot pass.
    """
    rows = chunk.rows
    mismatches: list[str] = []
    held = 0
    by_column: dict[str, list[WriteRow]] = {}
    for row in rows:
        by_column.setdefault(row.column, []).append(row)
    for column in sorted(by_column):
        group = by_column[column]
        text = _exec(
            run_sql_runner,
            stored_values_sql(column=column, site_ids=[row.site_id for row in group]),
            host=host,
        )
        current = {str(entry["id"]): entry for entry in _json_rows(text)}
        for row in group:
            observed = current.get(row.site_id)
            if observed is None:
                mismatches.append(f"{row.site_id}/{column}: the row is not there at all")
                continue
            if not same_value(observed=observed.get("value"), planned=row.new_value, column=column):
                mismatches.append(
                    f"{row.site_id}/{column}: holds {observed.get('value')!r}, the plan wrote "
                    f"{row.new_value!r}"
                )
                continue
            held += 1

    mismatches.extend(
        journal_mismatches(rows, run_stamp=chunk.stamp, run_sql_runner=run_sql_runner, host=host)
    )
    total = journal_rows_for_stamp(chunk.stamp, run_sql_runner=run_sql_runner, host=host)
    if total != len(rows):
        mismatches.append(
            f"run stamp {chunk.stamp} has {total} journal row(s), the plan has {len(rows)}"
        )
    return ReadBack(checked=len(rows), held=held, journal_rows=total, mismatches=tuple(mismatches))


# -------------------------------------------------------------------------------- the commands
@dataclass
class ChunkOutcome:
    """What one chunk did, in numbers, for the report."""

    chunk: Chunk
    planned: int
    preflight_held: int | None
    written: int
    not_held: tuple[Refusal, ...] = ()
    read_back: ReadBack | None = None
    inverse: ReadBack | None = None
    rollback_rows: int | None = None
    skipped: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk": self.chunk.label,
            "run_stamp": self.chunk.stamp,
            "digest": self.chunk.digest,
            "rows_planned": self.planned,
            "rows_preflight_held": self.preflight_held,
            "rows_written": self.written,
            "rows_matched_0": [
                {"site_id": r.site_id, "field": r.field, "reason": r.detail} for r in self.not_held
            ],
            "journal_rows_added": None if self.read_back is None else self.read_back.journal_rows,
            "read_back": None if self.read_back is None else self.read_back.describe(),
            "inverse": None if self.inverse is None else self.inverse.describe(),
            "rollback_rows_left": self.rollback_rows,
            "skipped": self.skipped,
        }


def apply_chunk(
    chunk: Chunk,
    *,
    out: Path,
    run_sql_runner: SqlRunner | None = None,
    host: str = SSH_HOST,
) -> ChunkOutcome:
    """Pre-flight, write, read back, invert - in that order, and stop on the first disagreement.

    The statements are read from `chunks/<label>/` and each is pinned to the rows of the chunk it is
    handed, so a file generated from another plan - or edited after it was rendered - cannot be run.
    Nothing is sent before the pre-flight has answered which rows still hold the value the plan
    names, and if any row moved nothing of the chunk is sent: the statement was generated from the
    chunk as a whole, so writing the rest of it would be writing a plan that no longer exists. The
    chunk is recorded with the rows that moved and the batch carries on with the next one.
    """
    if not chunk.rows:
        raise WriteRefused("refusing to apply an empty chunk")
    apply_path = out / CHUNKS_DIR / chunk.label / APPLY_FILE
    rollback_path = out / CHUNKS_DIR / chunk.label / ROLLBACK_FILE
    for path in (apply_path, rollback_path):
        if not path.exists():
            raise WriteRefused(f"{path} does not exist: render the plan before applying it")
    apply_sql = apply_path.read_text(encoding="utf-8")
    rollback_sql = rollback_path.read_text(encoding="utf-8")
    assert_pinned(apply_sql, chunk.rows, what=str(apply_path))
    assert_pinned(rollback_sql, chunk.rows, what=str(rollback_path))

    flight = preflight(chunk, run_sql_runner=run_sql_runner, host=host)
    if len(flight.held) != len(chunk.rows):
        return ChunkOutcome(
            chunk=chunk,
            planned=len(chunk.rows),
            preflight_held=len(flight.held),
            written=0,
            not_held=flight.not_held,
            skipped=(
                f"{len(flight.not_held)} of {len(chunk.rows)} row(s) no longer hold the planned "
                "old value, so none of them was written: the statement on disk was generated from "
                "the whole chunk. Re-render the plan for the state the rows are in now, then "
                "apply again."
            ),
        )

    _exec(run_sql_runner, apply_sql, host=host)
    back = read_back(chunk, run_sql_runner=run_sql_runner, host=host)
    if not back.ok:
        raise ReadBackFailed(
            f"{chunk.label} of {chunk.batch_id}: the read-back disagrees with the plan - "
            f"{back.describe()}. Stopping before this chunk's successor: the difference has to be "
            "understood first."
        )
    _exec(run_sql_runner, rollback_sql, host=host)
    inverse = read_back(chunk, run_sql_runner=run_sql_runner, host=host)
    if not inverse.ok:
        raise InverseFailed(
            f"{chunk.label} of {chunk.batch_id}: the reversal did not leave the write exactly as "
            f"it was - {inverse.describe()}"
        )
    rollback_rows = journal_rows_for_stamp(
        chunk.rollback_stamp, run_sql_runner=run_sql_runner, host=host
    )
    if rollback_rows != 0:
        raise InverseFailed(
            f"{chunk.label}: {rollback_rows} journal row(s) survived for the reversal's stamp "
            f"{chunk.rollback_stamp}; a reversal that is kept is a second write"
        )
    return ChunkOutcome(
        chunk=chunk,
        planned=len(chunk.rows),
        preflight_held=len(flight.held),
        written=len(chunk.rows),
        not_held=flight.not_held,
        read_back=back,
        inverse=inverse,
        rollback_rows=rollback_rows,
    )


def report(
    plan: WritePlan,
    *,
    chunks: Sequence[Chunk],
    outcomes: Sequence[ChunkOutcome],
    chunk_size: int,
    execute: bool,
) -> dict[str, Any]:
    """The batch's numbers, as numbers: what was planned, written, refused, and why."""
    fixed_point = plan.refused_fields(RULE_FIXED_POINT)
    backs = [outcome.read_back for outcome in outcomes if outcome.read_back is not None]
    return {
        "batch_id": plan.batch_id,
        "pass": plan.pass_name,
        "dry_run": not execute,
        "chunk_size": chunk_size,
        "chunks": len(chunks),
        "rows_planned": len(plan.rows),
        "sites_planned": len({row.site_id for row in plan.rows}),
        "rows_written": sum(outcome.written for outcome in outcomes),
        "rows_matched_0": sum(len(outcome.not_held) for outcome in outcomes),
        "rows_matched_0_reasons": [
            {"site_id": r.site_id, "field": r.field, "reason": r.detail}
            for outcome in outcomes
            for r in outcome.not_held
        ],
        "journal_rows_added": None if not execute else sum(b.journal_rows for b in backs),
        "refused_by_fixed_point": len(fixed_point),
        "refused_by_fixed_point_detail": [
            {"site_id": r.site_id, "field": r.field, "rule": r.rule, "reason": r.detail}
            for r in fixed_point
        ],
        "refused_by_rule": plan.refusals_by_rule(),
        "not_cleared_by_the_reviewer": len(plan.refused_fields(RULE_REVIEWER)),
        "chunk_results": [outcome.to_dict() for outcome in outcomes],
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise WriteRefused(f"{path} does not exist")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WriteRefused(f"{path} is not a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phase3-write",
        description=(
            "Turn one batch's reviewer-cleared findings into guarded, digest-pinned writes "
            "(dry run by default)"
        ),
    )
    parser.add_argument(
        "--batch-dir",
        required=True,
        help=f"a batch directory holding {INPUT_FILE}, {REVIEW_FILE} and {ANSWERS_DIR}/",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"where the plan and the chunk statements go (default: <batch-dir>/{WRITES_DIR})",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--host", default=SSH_HOST)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="pre-flight, write, read back and invert each chunk (needs the matching digest)",
    )
    parser.add_argument("--chunk", type=int, default=None, help="only this 1-based chunk")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    batch_dir = Path(args.batch_dir)
    out = Path(args.out) if args.out else batch_dir / WRITES_DIR
    plan = load_plan(batch_dir)
    chunks = chunks_for(plan, chunk_size=args.chunk_size)
    if args.chunk is not None:
        chunks = [chunk for chunk in chunks if chunk.index == args.chunk]
        if not chunks:
            raise WriteRefused(f"--chunk {args.chunk}: this plan has no such chunk")
    write_plan_files(out, plan, chunks=chunks)
    outcomes = (
        [apply_chunk(chunk, out=out, host=args.host) for chunk in chunks] if args.apply else []
    )
    payload = report(
        plan,
        chunks=chunks,
        outcomes=outcomes,
        chunk_size=args.chunk_size,
        execute=bool(args.apply),
    )
    payload["plan_file"] = str(out / PLAN_FILE)
    payload["refused_file"] = str(out / REFUSED_FILE)
    (out / REPORT_FILE).write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
