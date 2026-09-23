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

G0b (`--source rejected-kinds`, 2026-09-23) is that follow-up. `scripts/remediation/vlm_pilot/
rejected_kinds.py` proved the match: `output/remediation/vlm_pilot/REJECTED_KINDS.jsonl` maps each
of the 30 rejections to exactly one `wiki_images` row, by the short's own candidate pool and the
snapshot agreeing (verdict `PROVEN`, 30 of 30). Only `PROVEN` records are written, only the kind
the rejection states verbatim (`reason = "kind=<kind>"`), only where `image_kind` is NULL, and only
where production still holds the row on the site and under the filename the proof names. The batch
lives in `gallery_audit/rejected_kinds/` and journals under a stamp derived from its own identity
set - never under the landed G0 stamp.

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
    persist_verdicts.py --rehearse-rollback
                                          # run ROLLBACK.sql inside a transaction and roll it back
    persist_verdicts.py --check-primitive # probe the journalled primitive itself on a scratch row
    persist_verdicts.py --apply           # the write (requires the rollout decision)
    persist_verdicts.py --verify          # read-only: prove the landed state

Every command takes `--source stills` (the default: G0, `gallery_audit/`) or `--source
rejected-kinds` (G0b, `gallery_audit/rejected_kinds/`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "remediation"))

#: The production transport, the timeout rule and the pin format live in `prod_write.py` since
#: 2026-09-22 - moved there from this module so the mechanical lanes use the same code.
from prod_write import DIGEST_RE, SSH_HOST, OutcomeUnknown, send  # noqa: E402

OUTPUT = ROOT / "output" / "remediation" / "gallery_audit"
SELECTION = ROOT / "video-assets" / "shorts"
#: G0b's input: the proven filename -> row mapping of the 30 kind-labelled rejections. Versioned
#: (`git ls-files output/remediation/vlm_pilot`), so a clean checkout carries it.
REJECTED_KINDS = ROOT / "output" / "remediation" / "vlm_pilot" / "REJECTED_KINDS.jsonl"

#: The vocabulary migration 0019 enforces with a CHECK constraint. Kept as a literal copy rather
#: than imported. What keeps it honest is **not** `--verify`: `load_verdicts` refuses any kind
#: outside this set before a plan is built, and every vocabulary list this module renders into SQL
#: is built *from* this set, so the two cannot drift apart. The tie to the migration file itself
#: is the test `test_the_vocabulary_is_the_one_the_migration_enforces`; a third hand-written copy
#: used to sit in the verify query, which meant this comment described a comparison that did not
#: exist.
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

#: The run stamp of the batch that is already in production: 105 rows in `remediation_change_log`
#: carry exactly this string (measured 2026-09-21). It stays a literal because it names rows that
#: exist - a value recomputed today would not match them, and changing it would orphan the journal
#: of the landed write. It is not mutated here; every *other* batch derives its own stamp from its
#: own identity set (`run_stamp_for`).
RUN_STAMP = "2026-09-21_gallery-verdicts-persist"

#: Prefix for a derived stamp. A single module-wide constant would let a second batch journal
#: under the first batch's name, and two batches sharing one stamp are indistinguishable in
#: `remediation_change_log` - the counts still agree, which is how that defect stays hidden.
BATCH_STAMP_PREFIX = "gallery-verdicts-persist"

#: `authoritative` per 0017's own vocabulary (`authoritative|two_source|weak|unverifiable`).
#: The provenance being asserted is "the pipeline recorded this verdict about this image", and
#: the record is that pipeline's own file. Note the caveat this does NOT claim: GALLERY proved
#: the vision model is *reachable* and correctly labels colour, but its semantic **competence**
#: on archaeological imagery is unverified. These 105 rows are therefore a first reviewable
#: batch, not a validated classifier. Recorded in evidence below and in the audit log.
CONFIDENCE = "authoritative"



@dataclass(frozen=True)
class Source:
    """Where a batch of verdicts comes from, the label its SQL raises under, and where it lives."""

    name: str
    scope: str
    subdir: str | None


#: `stills` is G0, already landed (105 rows under RUN_STAMP): its files stay where they are and
#: render byte for byte as before. `rejected-kinds` is G0b, in its own directory, so its plan can
#: never overwrite G0's APPLY.sql and ROLLBACK.sql - the record and the only undo of a landed write.
SOURCES = {
    "stills": Source("stills", "G0", None),
    "rejected-kinds": Source("rejected-kinds", "G0b", "rejected_kinds"),
}


def output_for(source: str) -> Path:
    """The directory a source's plan and scripts live in. `OUTPUT` is read at call time."""
    sub = SOURCES[source].subdir
    return OUTPUT if sub is None else OUTPUT / sub


EXIT_OK = 0
EXIT_INPUT = 1
EXIT_NOTHING = 2
EXIT_INCONSISTENT = 3
EXIT_VERIFY_FAILED = 4
EXIT_UNKNOWN = 5


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
    source: str = "stills"
    #: The site the verdict's own record names for this image, when it names one (G0b's proof
    #: does; a G0 still carries only the id). `build_plan` compares it with production.
    site_id: str | None = None


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


MAPPING_VERDICTS = frozenset({"PROVEN", "AMBIGUOUS", "UNPROVABLE"})
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def record_sha256(record: Mapping[str, object]) -> str:
    """sha256 of one mapping record in canonical JSON - the pointer the journal evidence carries."""
    blob = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_rejected_kinds(path: Path | None = None) -> tuple[list[Verdict], list[Skipped]]:
    """G0b's verdicts: the PROVEN records of REJECTED_KINDS.jsonl, and a named refusal for the rest.

    Raises on anything malformed - a record whose stated kind is not the kind its reason names, a
    kind outside the vocabulary, an id that is not an integer, one image with two kinds. A record
    that is not PROVEN is never a guess: it is returned as a `Skipped` with its own evidence.
    """
    path = REJECTED_KINDS if path is None else path
    if not path.is_file():
        raise PersistError(f"{path} does not exist - run vlm_pilot/rejected_kinds.py first")
    out: list[Verdict] = []
    skipped: list[Skipped] = []
    seen: dict[int, str] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PersistError(f"{path}:{lineno} is not JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise PersistError(f"{path}:{lineno} is {type(record).__name__}, expected an object")
        where = f"{path.name}:{lineno}"
        mapping = record.get("verdict")
        if mapping not in MAPPING_VERDICTS:
            raise PersistError(f"{where}: mapping verdict {mapping!r} is none of {sorted(MAPPING_VERDICTS)}")
        slug = str(record.get("slug"))
        kind = record.get("kind_stated")
        reason = str(record.get("reason") or "")
        if kind not in VOCAB:
            raise PersistError(f"{where}: kind {kind!r} is not one of {sorted(VOCAB)}")
        named = reason.split("kind=", 1)[1].split()[0].rstrip(",;)") if "kind=" in reason else None
        if named != kind:
            raise PersistError(f"{where}: kind_stated {kind!r} is not the kind the reason names ({reason!r})")
        if mapping != "PROVEN":
            skipped.append(
                Skipped(
                    record.get("image_id") if isinstance(record.get("image_id"), int) else None,
                    slug,
                    "mapping-not-proven",
                    f"{mapping}: {'; '.join(str(e) for e in record.get('evidence') or [])}",
                )
            )
            continue
        image_id = _as_int(record.get("image_id"), what=f"{where} image_id")
        site_id = record.get("site_id")
        if not isinstance(site_id, str) or not _UUID.fullmatch(site_id):
            raise PersistError(f"{where}: site_id {site_id!r} is not a UUID")
        if image_id in seen and seen[image_id] != kind:
            raise PersistError(f"{where}: image {image_id} was already stated {seen[image_id]!r}")
        if image_id in seen:
            continue
        seen[image_id] = kind
        out.append(
            Verdict(
                image_id=image_id,
                kind=str(kind),
                slug=slug,
                file=path,
                verdict={"kind": kind, "reason": reason},
                entry={
                    "filename": record.get("filename"),
                    "mapping_evidence": list(record.get("evidence") or []),
                    "record_sha256": record_sha256(record),
                },
                source="rejected-kinds",
                site_id=site_id,
            )
        )
    if not out:
        raise PersistError(f"{path}: no PROVEN record - nothing G0b may write")
    return out, skipped


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def evidence_for(v: Verdict) -> list[dict[str, object]]:
    """The chain that lets a reader re-derive this write without trusting this script."""
    if v.source == "rejected-kinds":
        return rejected_evidence_for(v)
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


def rejected_evidence_for(v: Verdict) -> list[dict[str, object]]:
    """G0b's chain: the rejection, the proof that maps it to this row, the stage, the column."""
    return [
        {
            "source": "shorts selection record (the rejection being persisted)",
            "url": f"video-assets/shorts/{v.slug}/selection.json",
            "quote": (
                f"rejected[] entry filename={v.entry.get('filename')!r} "
                f"reason={v.verdict.get('reason')!r}"
            ),
        },
        {
            "source": "filename -> wiki_images row mapping, verdict PROVEN",
            "url": _relative(v.file),
            "sha256": v.entry.get("record_sha256"),
            "quote": f"image_id={v.image_id} site_id={v.site_id}: "
            + "; ".join(str(e) for e in v.entry.get("mapping_evidence") or []),
        },
        {
            "source": "pipeline/video/shorts_select.py (the stage that produced the verdict)",
            "url": "pipeline/video/shorts_select.py",
            "quote": (
                "reject_reason returns 'kind=<kind>' for a verdict whose kind is not site_photo; "
                "the reason carries the vision model's kind verbatim"
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
            "source": "caveat, recorded with the write rather than after it",
            "url": "output/remediation/gallery_design/DESIGN.md",
            "quote": (
                "the vision model's semantic competence on archaeological imagery is unverified; "
                "these rows record the pipeline's existing verdicts, not a validated classifier"
            ),
        },
    ]


# --------------------------------------------------------------------------------------
# production reads
# --------------------------------------------------------------------------------------


def run_psql(
    sql: str, *, host: str = SSH_HOST, timeout: int = 900, rows: bool = False, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Send `sql` to production the way this project does it: ssh, then psql in the container.

    A timeout is not an error like any other: psql may be halfway through a transaction whose
    COMMIT never reached us. `prod_write.send` reports it as `OutcomeUnknown`, never as a plain
    failure, so a caller cannot read it as "nothing happened" and retry blindly.
    """
    proc = send(sql, host=host, timeout=timeout, rows=rows)
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
        if v.site_id is not None and (
            row.get("site_id") != v.site_id or row.get("filename") != v.entry.get("filename")
        ):
            skipped.append(
                Skipped(
                    v.image_id,
                    v.slug,
                    "row-no-longer-matches-the-proof",
                    f"production holds site {row.get('site_id')!r} and filename "
                    f"{row.get('filename')!r}; the proof names {v.site_id!r} and "
                    f"{v.entry.get('filename')!r} - the mapping is not re-proven here",
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
# the record set, the run stamp, and the delivered scripts
# --------------------------------------------------------------------------------------


def change_key_of(image_id: int) -> str:
    """The journal's idempotency key for this row. One definition, used by plan and undo."""
    return f"g0-vlm-kind:{image_id}"


def rollback_change_key_of(image_id: int) -> str:
    return f"g0-vlm-kind-rollback:{image_id}"


def rollback_stamp(run_stamp: str = RUN_STAMP) -> str:
    """The reversal's journal stamp: derived from the write's stamp, never equal to it."""
    return f"{run_stamp}-rollback"


def plan_records(
    write: list[Verdict], state: dict[int, dict[str, object]]
) -> list[dict[str, object]]:
    """The record set the SQL is rendered from - one plain dict per planned row.

    This is what `APPLY.sql` and `ROLLBACK.sql` are tied to by hash. A row *count* is satisfied by
    105 right values on 105 wrong rows, and by a plan of entirely different rows.
    """
    return [
        {
            "image_id": v.image_id,
            "site_id": str(state[v.image_id]["site_id"]),
            "old_value": state[v.image_id].get("image_kind"),
            "new_value": v.kind,
        }
        for v in sorted(write, key=lambda v: v.image_id)
    ]


#: The fields a G0 record is identified by. `gallery_audit/chunk_writer.py` digests its own,
#: wider rows (table, column, key, change key) through the same function.
PLAN_DIGEST_KEYS = ("image_id", "site_id", "old_value", "new_value")


def plan_digest(
    records: Iterable[Mapping[str, object]], keys: Sequence[str] = PLAN_DIGEST_KEYS
) -> str:
    """sha256 over a record set: order-independent, one canonical JSON line per row."""
    lines = [
        json.dumps(
            {key: record.get(key) for key in keys},
            sort_keys=True,
            ensure_ascii=False,
        )
        for record in records
    ]
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def _identity_digest(image_ids: Iterable[int]) -> str:
    return hashlib.sha256("\n".join(str(i) for i in sorted(set(image_ids))).encode()).hexdigest()[
        :8
    ]


def load_plan_records(path: Path) -> list[dict[str, object]]:
    """`PLAN.jsonl` as records. The plan is the independent source the scripts are tied to."""
    if not path.is_file():
        raise PersistError(
            f"{path} does not exist - it is the record of the write, and nothing can be checked "
            "against the plan without it"
        )
    out: list[dict[str, object]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PersistError(f"{path}:{lineno} is not JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise PersistError(
                f"{path}:{lineno} is {type(parsed).__name__}, expected an object per line"
            )
        out.append(parsed)
    if not out:
        raise PersistError(f"{path} holds no records - an empty plan is not a plan")
    return out


def load_plan_stamp(records: list[dict[str, object]], *, path: Path) -> str:
    """The one run stamp the plan's records carry: two stamps in one plan is not one batch."""
    stamps = {str(record.get("run_stamp")) for record in records}
    if len(stamps) != 1:
        raise PersistError(
            f"{path} carries the run stamps {sorted(stamps)} - that is not one batch"
        )
    return stamps.pop()


def planned_ids(records: Iterable[Mapping[str, object]]) -> set[int]:
    return {_as_int(record.get("image_id"), what="PLAN.jsonl image_id") for record in records}


def delivered_plan_ids(output: Path | None = None) -> set[int]:
    """The image ids of the delivered plan. Empty when there is no plan file on disk."""
    output = OUTPUT if output is None else output
    path = output / "PLAN.jsonl"
    if not path.is_file():
        return set()
    return planned_ids(load_plan_records(path))


def run_stamp_for(write: list[Verdict], *, output: Path | None = None) -> str:
    """The stamp this batch journals under.

    `RUN_STAMP` for the batch that is already recorded - the delivered `PLAN.jsonl` *is* that
    batch's record, so re-rendering it reproduces the landed stamp and leaves the journal of the
    landed write readable. Any other batch gets a stamp derived from its own identity set, because
    a module-wide constant would let a second batch journal under the first batch's name: the two
    batches would then be indistinguishable in `remediation_change_log`, and every count would
    still agree.
    """
    ids = {v.image_id for v in write}
    if ids and ids == delivered_plan_ids(output):
        return RUN_STAMP
    return f"{BATCH_STAMP_PREFIX}-{_identity_digest(ids)}"


#: The first four fields of a `_kind_plan` tuple, each on its own line: the id, the site, the old
#: value and the new one. The remaining fields (change key, reason, evidence) are free text.
VALUE_ROW_RE = re.compile(
    r"^    \((\d+), '([0-9a-fA-F-]{36})'::uuid, (NULL|'[^']*'), (NULL|'[^']*'), ", re.MULTILINE
)


def _unquote(field: str) -> object:
    return None if field == "NULL" else field[1:-1]


def script_records(path: Path) -> list[dict[str, object]]:
    """The record set the *script itself* carries, read out of `_kind_plan`'s VALUES list.

    The header digest ties a script to a plan; this ties its body to the same plan, so a file that
    was edited after rendering is refused rather than sent.
    """
    rows: list[dict[str, object]] = []
    for match in VALUE_ROW_RE.finditer(path.read_text(encoding="utf-8")):
        image_id, site_id, old_value, new_value = match.groups()
        rows.append(
            {
                "image_id": int(image_id),
                "site_id": site_id,
                "old_value": _unquote(old_value),
                "new_value": _unquote(new_value),
            }
        )
    return rows


def inverted_records(records: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """The same record set as the reversal writes it: the new value becomes the old one.

    This lane's undo restores NULL, so it is only defined for a plan whose old values are NULL
    (`render_rollback` writes `old_value = <the kind>`, `new_value = NULL`). A plan that does not
    have that shape is refused here rather than checked against the wrong expectation.
    """
    out: list[dict[str, object]] = []
    for record in records:
        if record.get("old_value") is not None:
            raise PersistError(
                f"the plan's row {record.get('image_id')} has old_value "
                f"{record.get('old_value')!r}, so the reversal is not a simple inversion of it"
            )
        out.append(
            {
                "image_id": record["image_id"],
                "site_id": record["site_id"],
                "old_value": record.get("new_value"),
                "new_value": record.get("old_value"),
            }
        )
    return out


def verify_delivered(path: Path, records: list[dict[str, object]], *, invert: bool = False) -> str:
    """Prove a delivered script is the one rendered from this plan, or refuse to send it.

    Fails closed in both directions: a script with no digest header, a script whose digest is not
    the plan's, and a script whose own record set is not the plan's (nor its inversion, for the
    undo) are all refused. Without this, `--apply` sends whatever `APPLY.sql` happens to contain -
    and the undo a reviewer checked is tied to nothing.
    """
    text = path.read_text(encoding="utf-8")
    expected_records = inverted_records(records) if invert else list(records)
    expected = plan_digest(expected_records)
    match = DIGEST_RE.search(text)
    if match is None:
        raise PersistError(
            f"{path} carries no '-- plan sha256' header - it was not rendered from a plan, or it "
            "was edited after rendering; refusing to send it to production"
        )
    if match.group(1) != plan_digest(records):
        raise PersistError(
            f"{path} declares plan sha256 {match.group(1)}, but PLAN.jsonl hashes to "
            f"{plan_digest(records)}: the script and the plan it is supposed to reproduce have "
            "drifted apart; refusing to send it to production"
        )
    body = plan_digest(script_records(path))
    if body != expected:
        raise PersistError(
            f"{path} carries records that hash to {body}, not to {expected}: the plan's record set "
            "is not what this file would apply; refusing to send it to production"
        )
    return plan_digest(records)


# --------------------------------------------------------------------------------------
# emitting the SQL
# --------------------------------------------------------------------------------------


def _sql_literal(value: str) -> str:
    """A single-quoted SQL literal, or a refusal.

    Control characters are refused outright rather than escaped. These scripts are piped to psql
    as a *file*, where psql's own line reader is live: a newline inside an open literal survives
    as a line break, and a backslash at the start of the next line is a meta-command, not data.
    Every external value that reaches a literal is `repr`-ed (`!r`) or JSON-encoded before it gets
    here, so this refusal is the backstop for the caller that one day forgets - not the first line
    of defence. It fails closed, which is the direction this lane must fail in.
    """
    offenders = sorted({f"U+{ord(ch):04X}" for ch in value if ord(ch) < 32 or ord(ch) == 127})
    if offenders:
        raise PersistError(
            f"refusing to render a SQL literal containing control character(s) {offenders}: "
            "repr() or json.dumps() the value instead of embedding it raw"
        )
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
        if v.source == "rejected-kinds":
            reason = (
                f"G0b: the shorts pipeline rejected image {v.image_id} "
                f"({v.entry.get('filename')!r}) on {v.slug!r} as {v.verdict.get('reason')!r}; "
                "the row is the one REJECTED_KINDS.jsonl proves"
            )
        else:
            reason = (
                f"G0: the shorts pipeline judged image {v.image_id} ({v.entry.get('filename')!r}) "
                f"{v.kind!r} on {v.slug!r}; recorded verbatim from its own selection record"
            )
        tuples.append(
            "    ({}, {}::uuid, {}, {}, {}, {}, {}::jsonb)".format(
                v.image_id,
                _sql_literal(str(row["site_id"])),
                old_literal,
                _sql_literal(v.kind),
                _sql_literal(change_key_of(v.image_id)),
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
        RAISE EXCEPTION '{scope} image_kind: % planned row(s) do not exist', bad;
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
        RAISE EXCEPTION '{scope} image_kind: % planned row(s) are outside source_id %', bad, {source_arg};
    END IF;

    -- scope guard 3: every planned row still holds the old value the plan names. NULL-safe:
    -- `image_kind = NULL` is NULL, not true, and would match nothing.
    SELECT count(*) INTO bad
      FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
     WHERE w.image_kind IS DISTINCT FROM p.old_value;
    IF bad > 0 THEN
        RAISE EXCEPTION '{scope} image_kind: % planned row(s) no longer hold the planned old value', bad;
    END IF;
"""


def guards_sql(scope: str, *, source: str = CURATED_SOURCE) -> str:
    """The guard block, one definition for the write and for its undo.

    The undo used to carry a hand-shortened copy of this: three guards fewer (existence,
    curated scope, journal reconciliation), which is how a rollback that cannot fail first looks.
    """
    return (
        GUARDS.replace("{scope}", scope)
        .replace("{source}", _sql_literal(source))
        .replace("{source_arg}", _sql_literal(source))
        .rstrip()
    )


INVARIANTS = """
    -- invariant 1: every planned row now holds the new value
    SELECT count(*) INTO bad
      FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
     WHERE w.image_kind IS DISTINCT FROM p.new_value;
    IF bad > 0 THEN
        RAISE EXCEPTION '{scope} image_kind: % planned row(s) do not hold the new value', bad;
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
        RAISE EXCEPTION '{scope} image_kind: % planned row(s) disagree with the journal', bad;
    END IF;

    -- invariant 3: this run stamp journalled nothing outside wiki_images.image_kind. In the
    -- transaction, before COMMIT: the mechanical lane raises here, and G0 used to print the same
    -- number among its post-commit reads - which aborts *after* the COMMIT instead of before it.
    -- Fail-closed means fail early.
    SELECT count(*) INTO bad FROM remediation_change_log l
     WHERE l.run_stamp = {stamp}
       AND (l.table_name <> {tbl} OR l.column_name <> {col});
    IF bad > 0 THEN
        RAISE EXCEPTION
            '{scope} image_kind: this run stamp journalled % row(s) outside wiki_images.image_kind',
            bad;
    END IF;
"""

#: The reversal's invariants, read after its own loop: the rows are back to NULL and the reversal's
#: journal names the same rows, holds the undone value as old_value and NULL as the new one.
ROLLBACK_INVARIANTS = """
    -- invariant 1: every planned row is back to NULL, the pre-state this reversal restores
    SELECT count(*) INTO bad
      FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id
     WHERE w.image_kind IS NOT NULL;
    IF bad > 0 THEN
        RAISE EXCEPTION '{scope}: % row(s) are still not NULL', bad;
    END IF;

    -- invariant 2: the reversal's journal and the data agree, row for row, in both directions.
    -- The counts agreeing is not enough: the journal must name the same rows, record the value it
    -- undid as old_value, and record the NULL it restored as new_value.
    SELECT count(*) INTO bad
      FROM _kind_plan p LEFT JOIN remediation_change_log l
        ON l.row_pk = p.image_id::text AND l.table_name = {tbl}
       AND l.column_name = {col}
       AND l.run_stamp = {stamp}
     WHERE l.id IS NULL
        OR l.new_value IS NOT NULL
        OR l.old_value IS DISTINCT FROM p.old_value;
    IF bad > 0 THEN
        RAISE EXCEPTION '{scope}: % planned row(s) disagree with the reversal journal', bad;
    END IF;

    -- invariant 3: the reversal stamp journalled nothing outside wiki_images.image_kind
    SELECT count(*) INTO bad FROM remediation_change_log l
     WHERE l.run_stamp = {stamp}
       AND (l.table_name <> {tbl} OR l.column_name <> {col});
    IF bad > 0 THEN
        RAISE EXCEPTION
            '{scope}: this run stamp journalled % row(s) outside wiki_images.image_kind',
            bad;
    END IF;
"""


def invariants_sql(template: str, scope: str, *, run_stamp: str) -> str:
    return (
        template.replace("{scope}", scope)
        .replace("{tbl}", _sql_literal(TABLE))
        .replace("{col}", _sql_literal(COLUMN))
        .replace("{stamp}", _sql_literal(run_stamp))
        .rstrip()
    )


def kinds_of(records: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    """The kinds a batch writes, sorted - the set its verification reads for."""
    return tuple(sorted({str(r.get("new_value") if "new_value" in r else r.get("kind")) for r in records}))


def kind_test(kinds: Sequence[str]) -> tuple[str, str]:
    """(the SQL test for `kinds`, its label). One kind renders as G0 always rendered it."""
    if not kinds or any(kind not in VOCAB for kind in kinds):
        raise PersistError(f"{list(kinds)!r} is not a set of image kinds")
    if len(kinds) == 1:
        return f"= {_sql_literal(kinds[0])}", f"= {kinds[0]}"
    return (
        "IN (" + ", ".join(_sql_literal(k) for k in kinds) + ")",
        "in (" + ", ".join(kinds) + ")",
    )


def verify_in_tx_sql(run_stamp: str = RUN_STAMP, kinds: Sequence[str] = ("site_photo",)) -> str:
    """The read-backs that run INSIDE the transaction, before COMMIT.

    These read `_kind_plan`, which is `ON COMMIT DROP`: after a COMMIT the table is gone, so these
    queries only ever work here.
    """
    vocab = ", ".join(_sql_literal(kind) for kind in sorted(VOCAB))
    test, label = kind_test(kinds)
    return f"""
SELECT 'planned rows written', count(*)::text FROM wiki_images
 WHERE image_kind {test} AND id IN (SELECT image_id FROM _kind_plan);
SELECT 'rows still NULL among planned', count(*)::text
  FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id WHERE w.image_kind IS NULL;
SELECT 'journal rows for this run', count(*)::text FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)};
SELECT 'journal rows for this run outside wiki_images.image_kind', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)}
   AND (table_name <> 'wiki_images' OR column_name <> 'image_kind');
SELECT 'journal rows for this run with no evidence', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)} AND (evidence IS NULL OR evidence = '[]'::jsonb);
SELECT 'table-wide context: rows with image_kind {label} (never compared to the journal)',
       count(*)::text FROM wiki_images WHERE image_kind {test};
SELECT 'context only: curated rows still without a kind', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds' AND w.image_kind IS NULL;
SELECT 'rows with a kind outside the vocabulary', count(*)::text FROM wiki_images
 WHERE image_kind IS NOT NULL AND image_kind NOT IN ({vocab});
SELECT 'curated images', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds';
"""


def unjournalled_label(kinds: Sequence[str]) -> str:
    """The must-be-zero metric: rows holding a kind this run writes, with no journal row of it."""
    return f"rows with image_kind {kind_test(kinds)[1]} and no journal row for this run"


def verify_sql(run_stamp: str = RUN_STAMP, kinds: Sequence[str] = ("site_photo",)) -> str:
    """Post-hoc verification, run as its own psql call.

    It must NOT reference `_kind_plan`: that table is `ON COMMIT DROP`, so once the write has
    committed the table is gone and a query against it fails. The first run of `--apply` reported
    `EXIT_VERIFY_FAILED` on a write that had in fact succeeded and whose in-transaction numbers
    were all correct, for exactly that reason. Only facts that outlive the transaction belong here.

    Identity, not cardinality. This query used to compare the run-local journal count with a
    **table-wide** `count(*) FROM wiki_images WHERE image_kind = 'site_photo'`. The two agreed on
    the day of the write only because G0 was the first writer of `site_photo`; the next legitimate
    write would have raised a false alarm. The table-wide number is still printed - under a label
    that says what it is - and is never compared to the journal. The row-for-row comparison lives
    in `command_verify` (`_journalled_ids`), because only a set of ids can show that the journal
    names the same rows as the plan.

    The vocabulary list is rendered *from* `VOCAB`, so the query and the input validation cannot
    drift apart. (The migration's own CHECK constraint is the authority and is not readable from
    here; the tie to it is the test, not a third hand-written copy of the list.)
    """
    vocab = ", ".join(_sql_literal(kind) for kind in sorted(VOCAB))
    test, label = kind_test(kinds)
    return f"""
SELECT 'journal rows for this run', count(*)::text FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)};
SELECT '{unjournalled_label(kinds)}', count(*)::text
  FROM wiki_images w WHERE w.image_kind {test}
   AND NOT EXISTS (SELECT 1 FROM remediation_change_log l
                    WHERE l.run_stamp = {_sql_literal(run_stamp)}
                      AND l.table_name = 'wiki_images' AND l.column_name = 'image_kind'
                      AND l.row_pk = w.id::text);
SELECT 'journal rows for this run outside wiki_images.image_kind', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)}
   AND (table_name <> 'wiki_images' OR column_name <> 'image_kind');
SELECT 'journal rows for this run with no evidence', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(run_stamp)} AND (evidence IS NULL OR evidence = '[]'::jsonb);
SELECT 'table-wide context: rows with image_kind {label} (never compared to the journal)',
       count(*)::text FROM wiki_images WHERE image_kind {test};
SELECT 'context only: curated rows still without a kind', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds' AND w.image_kind IS NULL;
SELECT 'rows with a kind outside the vocabulary', count(*)::text FROM wiki_images
 WHERE image_kind IS NOT NULL AND image_kind NOT IN ({vocab});
SELECT 'curated images', count(*)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds';
SELECT 'distinct curated sites now carrying a kind', count(DISTINCT w.site_id)::text
  FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
 WHERE s.source_id = 'ancient_nerds' AND w.image_kind IS NOT NULL;
"""


def render_apply(
    write: list[Verdict],
    state: dict[int, dict[str, object]],
    *,
    run_stamp: str = RUN_STAMP,
) -> str:
    """The write, as one transaction.

    An empty plan is refused, not rendered: an APPLY.sql over zero rows still looks like the plan
    (it has a header, a transaction and a guard block) and would replace the real one.
    """
    if not write:
        raise PersistError("refusing to render an APPLY.sql for an empty plan")
    scope = scope_of(write)
    expected = len(write)
    digest = plan_digest(plan_records(write, state))
    head = f"""-- Generated by scripts/remediation/gallery_audit/persist_verdicts.py - do not edit by hand.
-- {expected} row(s) over {len({v.image_id for v in write})} image(s); scope source_id = '{CURATED_SOURCE}';
-- run stamp {run_stamp!r}; journal test id {TEST_ID!r}.
-- plan sha256 {digest} - the digest of the record set below. --apply recomputes it from
-- PLAN.jsonl and refuses to send this file if the two no longer agree.
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
{guards_sql(scope)}

    -- the only writer: the conditional UPDATE and its journal row commit together, and the
    -- function raises unless exactly one row matched
    FOR r IN SELECT * FROM _kind_plan ORDER BY image_id LOOP
        moved := moved + apply_remediation_change(
            {_sql_literal(TABLE)}, {_sql_literal(COLUMN)}, {_sql_literal(KEY_COLUMN)}, r.image_id::text,
            r.old_value, r.new_value,
            {_sql_literal(TEST_ID)}, {_sql_literal(run_stamp)}, r.change_key, {_sql_literal(CONFIDENCE)},
            r.evidence, r.site_id);
    END LOOP;

    IF moved <> expected THEN
        RAISE EXCEPTION '{scope} image_kind: % row(s) changed, % planned', moved, expected;
    END IF;
{invariants_sql(INVARIANTS, scope, run_stamp=run_stamp)}
END $$;

{verify_in_tx_sql(run_stamp, kinds_of(plan_records(write, state)))}
COMMIT;
"""
    return head


def scope_of(write: list[Verdict]) -> str:
    """The one source a batch comes from, as the label its SQL raises under."""
    sources = {v.source for v in write}
    if len(sources) != 1:
        raise PersistError(f"a batch mixes the sources {sorted(sources)} - that is not one batch")
    return SOURCES[sources.pop()].scope


def render_apply_verification(run_stamp: str = RUN_STAMP) -> str:
    """The verification block that runs inside the write's own transaction."""
    return verify_in_tx_sql(run_stamp)


def render_rollback(
    write: list[Verdict],
    state: dict[int, dict[str, object]],
    *,
    run_stamp: str = RUN_STAMP,
) -> str:
    """Set NULL back on exactly the rows this run touched. NULL is the pre-state, by construction.

    This file is the undo and it is generated with the **same guard block as the write**, not a
    hand-shortened copy of it: the existence guard, the curated-scope guard, the old-value guard
    and the journal reconciliation all have to hold on the state the write left behind. Until
    2026-09-21 this file carried three guards fewer than the apply and had never once been parsed
    by psql - its first parse would have been the real production rollback. `--rehearse-rollback`
    now parses and runs it as a rehearsal, against the rows the write left behind.
    """
    if not write:
        raise PersistError("refusing to render a ROLLBACK.sql for an empty plan")
    scope = scope_of(write)
    stamp = rollback_stamp(run_stamp)
    digest = plan_digest(plan_records(write, state))
    tuples = []
    for v in write:
        row = state[v.image_id]
        evidence = json.dumps(
            [
                {
                    "source": "remediation_change_log (the row this undoes)",
                    "url": f"remediation_change_log.row_pk={v.image_id}",
                    "quote": f"run_stamp={run_stamp!r} wrote image_kind={v.kind!r} where it was NULL",
                },
                {
                    "source": "the verdict this restores NULL over",
                    "url": _relative(v.file),
                    "quote": (
                        f"PROVEN image_id={v.image_id} reason={v.verdict.get('reason')!r}"
                        if v.source == "rejected-kinds"
                        else f"stills[] id={v.image_id} verdict.kind={v.kind!r}"
                    ),
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
        reason = (
            f"rollback of {scope}: image_kind on {v.image_id} returned to NULL (was {v.kind!r})"
        )
        tuples.append(
            "    ({}, {}::uuid, {}, NULL, {}, {}, {}::jsonb)".format(
                v.image_id,
                _sql_literal(str(row["site_id"])),
                _sql_literal(v.kind),
                _sql_literal(rollback_change_key_of(v.image_id)),
                _sql_literal(reason),
                _sql_literal(evidence),
            )
        )

    rows_sql = ",\n".join(tuples)
    return f"""-- Generated by scripts/remediation/gallery_audit/persist_verdicts.py - do not edit by hand.
-- {len(write)} row(s): image_kind returned to NULL, which is the pre-state of every row this
-- run touched (migration 0019: NULL = no verdict recorded).
-- plan sha256 {digest} - the digest of the record set this reversal undoes, as PLAN.jsonl holds it.
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
{rows_sql};

DO $$
DECLARE
    bad      integer;
    moved    integer := 0;
    expected integer := {len(write)};
    r        RECORD;
BEGIN
{guards_sql(f"{scope} rollback")}

    FOR r IN SELECT * FROM _kind_plan ORDER BY image_id LOOP
        moved := moved + apply_remediation_change(
            {_sql_literal(TABLE)}, {_sql_literal(COLUMN)}, {_sql_literal(KEY_COLUMN)}, r.image_id::text,
            r.old_value, r.new_value,
            {_sql_literal(TEST_ID)}, {_sql_literal(stamp)}, r.change_key, {_sql_literal(CONFIDENCE)},
            r.evidence, r.site_id);
    END LOOP;

    IF moved <> expected THEN
        RAISE EXCEPTION '{scope} rollback: % row(s) changed, % planned', moved, expected;
    END IF;
{invariants_sql(ROLLBACK_INVARIANTS, f"{scope} rollback", run_stamp=stamp)}
END $$;

SELECT 'planned rows restored to NULL', count(*)::text
  FROM _kind_plan p JOIN wiki_images w ON w.id = p.image_id WHERE w.image_kind IS NULL;
SELECT 'journal rows for the rollback', count(*)::text FROM remediation_change_log
 WHERE run_stamp = {_sql_literal(stamp)};
COMMIT;
"""


def render_plan_md(
    write: list[Verdict], skipped: list[Skipped], *, run_stamp: str = RUN_STAMP
) -> str:
    if scope_of(write) == SOURCES["rejected-kinds"].scope:
        return render_rejected_plan_md(write, skipped, run_stamp=run_stamp)
    by_reason: dict[str, list[Skipped]] = {}
    for s in skipped:
        by_reason.setdefault(s.reason, []).append(s)

    lines = [
        f"# G0 - persist the already-computed VLM verdicts ({run_stamp})",
        "",
        f"{len(write)} row(s) to write, {len(skipped)} named refusal(s).",
        "",
        "`image_kind` is written only where it is currently NULL, and only for rows whose site",
        "belongs to `source_id = 'ancient_nerds'`. Nothing is overwritten and nothing is deleted.",
        "",
        "The write this plan describes is recorded in `remediation_change_log` under the run stamp",
        f"`{run_stamp}`. `APPLY.sql` and `ROLLBACK.sql` beside this file are the record and the",
        "undo of that batch, not a queue: an `APPLY.sql` whose batch is already journalled is never",
        "re-sent. `--rehearse` and `--rehearse-rollback` run either file and roll it back, which is",
        "the safe way to re-check them.",
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
        "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --rehearse-rollback",
        "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --verify",
        "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --apply",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def _refusals_md(skipped: list[Skipped]) -> list[str]:
    by_reason: dict[str, list[Skipped]] = {}
    for s in skipped:
        by_reason.setdefault(s.reason, []).append(s)
    lines = ["## Named refusals", ""]
    if not by_reason:
        lines.append("None.")
    for reason in sorted(by_reason):
        lines += [f"### `{reason}` ({len(by_reason[reason])})", "", "| image_id | slug | detail |"]
        lines.append("|---|---|---|")
        lines += [f"| {s.image_id} | {s.slug} | {s.detail} |" for s in by_reason[reason]]
        lines.append("")
    return lines


def render_rejected_plan_md(
    write: list[Verdict], skipped: list[Skipped], *, run_stamp: str
) -> str:
    """G0b's PLAN.md: the proven rejections, one row each, and every refusal by name."""
    script = "./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py"
    lines = [
        f"# G0b - persist the kinds the shorts pipeline stated in its rejections ({run_stamp})",
        "",
        f"{len(write)} row(s) to write, {len(skipped)} named refusal(s).",
        "",
        "Input: `output/remediation/vlm_pilot/REJECTED_KINDS.jsonl`, `PROVEN` records only. Each",
        "names the row its rejection belongs to, proven by the short's candidate pool and the",
        "snapshot agreeing; the kind is the one the rejection states verbatim (`kind=<kind>`).",
        "`image_kind` is written only where it is NULL, only where production still holds the row",
        "on the proof's site under the proof's filename, and only for `ancient_nerds` sites.",
        "",
        f"Run stamp `{run_stamp}` - derived from this batch's own ids, never G0's landed stamp.",
        "",
        "## Rows to write",
        "",
        "| image_id | slug | kind | filename |",
        "|---|---|---|---|",
    ]
    for v in sorted(write, key=lambda v: v.image_id):
        lines.append(f"| {v.image_id} | {v.slug} | `{v.kind}` | `{v.entry.get('filename')}` |")
    lines += ["", *_refusals_md(skipped)]
    lines += [
        "## Verification",
        "",
        "```bash",
        *(
            f"{script} --source rejected-kinds --{step}"
            for step in ("plan", "rehearse", "apply", "verify", "rehearse-rollback")
        ),
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def emit(
    write: list[Verdict],
    skipped: list[Skipped],
    state: dict[int, dict[str, object]],
    *,
    run_stamp: str | None = None,
    output: Path | None = None,
) -> dict[str, str]:
    """Write the deliverables. ROLLBACK.sql is written before APPLY.sql, deliberately.

    An empty plan is refused here, before a single file is touched. `ROLLBACK.sql` is the only undo
    for a write that has already landed, `--plan` is the first of the four post-write verification
    commands this lane documents (PLAN.md), and on a landed write the plan's write list is empty -
    so a re-run used to replace the undo with a `ROLLBACK.sql` over nothing.
    """
    if not write:
        raise PersistError(
            "refusing to emit for an empty plan: it would overwrite APPLY.sql and ROLLBACK.sql - "
            "the record and the only undo of the write that is already in the journal"
        )
    scope_of(write)
    source = write[0].source
    output = output_for(source) if output is None else output
    output.mkdir(parents=True, exist_ok=True)
    # The stamp is decided against G0's landed plan, wherever this batch lives: a batch whose ids
    # are not that plan's derives its own. Asking this batch's own directory instead would hand
    # RUN_STAMP to a re-emitted G0b plan and journal it under the landed write's name.
    stamp = run_stamp if run_stamp is not None else run_stamp_for(write)
    paths = {
        "plan_md": output / "PLAN.md",
        "plan_jsonl": output / "PLAN.jsonl",
        "skipped": output / "SKIPPED.jsonl",
        "rollback": output / "ROLLBACK.sql",
        "apply": output / "APPLY.sql",
    }

    paths["plan_md"].write_text(render_plan_md(write, skipped, run_stamp=stamp), encoding="utf-8")

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
                        "reason": (
                            f"G0b: the rejection {v.verdict.get('reason')!r} of "
                            f"{v.entry.get('filename')!r} on {v.slug}"
                            if v.source == "rejected-kinds"
                            else f"G0: pipeline verdict for {v.entry.get('filename')!r} on {v.slug}"
                        ),
                        "change_key": change_key_of(v.image_id),
                        "test_id": TEST_ID,
                        "run_stamp": stamp,
                        "confidence": CONFIDENCE,
                        "source_id": row.get("source_id"),
                        "selection_file": _relative(v.file),
                    }
                    | (
                        {"record_sha256": v.entry.get("record_sha256"), "site_id_proven": v.site_id}
                        if v.source == "rejected-kinds"
                        else {}
                    ),
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
    paths["rollback"].write_text(render_rollback(write, state, run_stamp=stamp), encoding="utf-8")
    paths["apply"].write_text(render_apply(write, state, run_stamp=stamp), encoding="utf-8")

    return {k: str(v) for k, v in paths.items()}


# --------------------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------------------


def command_plan(source: str = "stills") -> int:
    if source == "rejected-kinds":
        verdicts, refused = load_rejected_kinds()
    else:
        verdicts, refused = load_verdicts(), []
    state = read_state([v.image_id for v in verdicts])
    write, skipped = build_plan(verdicts, state)
    skipped = refused + skipped

    print(f"selection records read : {len(verdicts)}")
    print(f"rows in the database   : {len(state)}")
    print(f"rows to write          : {len(write)}")
    print(f"named refusals         : {len(skipped)}")
    if not write:
        # The check comes BEFORE emit, not after it. Re-running --plan on a landed write is
        # documented behaviour - PLAN.md lists it first among the post-write verification commands
        # - and the write list is then empty. Emitting would overwrite ROLLBACK.sql, the only undo.
        print(
            "nothing to write - the plan is already in place; APPLY.sql and ROLLBACK.sql were "
            "left exactly as they are"
        )
        return EXIT_NOTHING
    paths = emit(write, skipped, state, output=output_for(source))
    for name, path in paths.items():
        print(f"  {name:11} {_relative(Path(path))}")
    return EXIT_OK


def rehearsal_of(script: str) -> str:
    """The emitted script with its single final `COMMIT;` replaced by `ROLLBACK;`.

    Refuses anything that does not end in exactly one `COMMIT;`. This is the guard that keeps a
    rehearsal a rehearsal: if the substitution missed, `--rehearse` would run the real statement to
    COMMIT against production and then report REHEARSAL OK - a rehearsal that applies the rows.
    """
    if script.count("COMMIT;") != 1 or not script.rstrip().endswith("COMMIT;"):
        raise PersistError(
            "the script does not end in exactly one COMMIT; - refusing to rehearse a statement "
            "that would not be rolled back"
        )
    return script.rstrip()[: -len("COMMIT;")] + "ROLLBACK;\n"


def command_rehearse(output: Path | None = None) -> int:
    output = OUTPUT if output is None else output
    apply_path = output / "APPLY.sql"
    if not apply_path.is_file():
        raise PersistError(f"{apply_path} does not exist - run --plan first")
    script = apply_path.read_text(encoding="utf-8")
    records = load_plan_records(output / "PLAN.jsonl")
    digest = verify_delivered(apply_path, records)
    test, label = kind_test(kinds_of(records))
    rehearsal = rehearsal_of(script)

    print(f"rehearsing {_relative(apply_path)} ({len(script)} bytes, plan sha256 {digest})")
    proc = run_psql(rehearsal, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"REHEARSAL FAILED: psql exit={proc.returncode}")
        return EXIT_INCONSISTENT

    # Prove the rollback really rolled back: the rehearsal's own verification queries ran inside
    # the transaction, so their numbers describe a state that must no longer exist.
    if proc.stdout.count("planned rows written") == 0:
        print("REHEARSAL INCONCLUSIVE: the verification queries never ran")
        return EXIT_INCONSISTENT
    # And prove that what ran was the rehearsal, not the apply: psql echoes a command tag for the
    # transaction's end. A 'COMMIT' tag here would mean the substitution missed and the rows were
    # written for real - the one outcome a rehearsal must never have.
    if "COMMIT" in proc.stdout or "ROLLBACK" not in proc.stdout:
        print("REHEARSAL INCONCLUSIVE: the statement that ran did not end in ROLLBACK")
        return EXIT_INCONSISTENT
    residue = run_psql(
        f"SELECT 'context only: curated rows holding {label.removeprefix('= ')}', count(*)::text"
        " FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id"
        f" WHERE s.source_id = 'ancient_nerds' AND w.image_kind {test};",
        rows=True,
    ).stdout.strip()
    print(f"after the rehearsal: {residue}")
    print("REHEARSAL OK (the write path executed, its verification passed, and it was rolled back)")
    return EXIT_OK


def command_rehearse_rollback(output: Path | None = None) -> int:
    """Run `ROLLBACK.sql` with `COMMIT` swapped for `ROLLBACK`, against the state the write left.

    The mechanical lane has had this for its own reversal since wave 4. G0 had none, and its
    ROLLBACK.sql had never been parsed by psql once - the first parse would have been the real
    production rollback. No apply is needed first: the reversal starts from the state the landed
    write left behind, its guards and journal are exercised on the real rows, and nothing is kept.
    """
    output = OUTPUT if output is None else output
    rollback_path = output / "ROLLBACK.sql"
    if not rollback_path.is_file():
        raise PersistError(f"{rollback_path} does not exist - run --plan first")
    plan_path = output / "PLAN.jsonl"
    records = load_plan_records(plan_path)
    digest = verify_delivered(rollback_path, records, invert=True)
    run_stamp = load_plan_stamp(records, path=plan_path)
    planned = len(records)
    kinds = ", ".join(
        _sql_literal(kind) for kind in sorted({str(r.get("new_value")) for r in records})
    )
    script = rollback_path.read_text(encoding="utf-8")
    rehearsal = rehearsal_of(script)

    print(f"rehearsing {_relative(rollback_path)} ({len(script)} bytes, plan sha256 {digest})")
    proc = run_psql(rehearsal, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"ROLLBACK REHEARSAL FAILED: psql exit={proc.returncode}")
        return EXIT_INCONSISTENT
    if proc.stdout.count("planned rows restored to NULL") == 0:
        print("ROLLBACK REHEARSAL INCONCLUSIVE: the verification queries never ran")
        return EXIT_INCONSISTENT
    if "COMMIT" in proc.stdout or "ROLLBACK" not in proc.stdout:
        print("ROLLBACK REHEARSAL INCONCLUSIVE: the statement that ran did not end in ROLLBACK")
        return EXIT_INCONSISTENT

    # Nothing may have survived the rehearsal: the rows must still hold the value the write left,
    # and the reversal's own run stamp must have journalled nothing. Both are read outside the
    # transaction, from the database and not from the script.
    after = read_rows(
        "SELECT row_to_json(t) FROM ("
        f" SELECT count(*) FILTER (WHERE w.image_kind IN ({kinds}))::int AS holding_kind,"
        " (SELECT count(*) FROM remediation_change_log"
        f"   WHERE run_stamp = {_sql_literal(rollback_stamp(run_stamp))})::int AS rollback_journal"
        " FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id"
        " WHERE s.source_id = 'ancient_nerds') t"
    )
    if not after:
        print("ROLLBACK REHEARSAL INCONCLUSIVE: the residue read returned nothing")
        return EXIT_INCONSISTENT
    holding = _as_int(after[0]["holding_kind"], what="rows still holding the written kind")
    left = _as_int(after[0]["rollback_journal"], what="journal rows left by the rehearsal")
    print(f"after the rehearsal: {holding} row(s) still hold the written kind, {left} journalled")
    if holding != planned or left != 0:
        print(
            f"ROLLBACK REHEARSAL FAILED: expected {planned} row(s) still holding the written kind "
            f"and 0 journalled; measured {holding} and {left}"
        )
        return EXIT_INCONSISTENT
    print(
        "ROLLBACK REHEARSAL OK (the reversal executed, its guards and journal passed, and it was "
        "rolled back)"
    )
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


def journalled_ids_sql(run_stamp: str) -> str:
    """One row per journalled row: its `row_pk` list as text, and how many disagree with the data."""
    return f"""
SELECT row_to_json(t) FROM (
  SELECT coalesce(string_agg(l.row_pk, ','), '') AS row_pks,
         count(*) FILTER (
             WHERE w.id IS NULL OR w.{COLUMN} IS DISTINCT FROM l.new_value
         )::int AS disagreeing
    FROM remediation_change_log l
    LEFT JOIN wiki_images w ON w.id::text = l.row_pk
   WHERE l.run_stamp = {_sql_literal(run_stamp)}
     AND l.table_name = {_sql_literal(TABLE)}
     AND l.column_name = {_sql_literal(COLUMN)}
) t;
"""


def journalled_ids(run_stamp: str) -> tuple[set[int], int]:
    """(the row ids this run stamp journalled, how many of them disagree with the data).

    Identity, not a count: the journal's `row_pk` set is what has to equal the plan's id set. The
    same read also answers whether every journalled row still holds the value the journal recorded
    - the fact the old table-wide `site_photo` count was standing in for.
    """
    rows = read_rows(journalled_ids_sql(run_stamp))
    if not rows:
        return set(), 0
    out: set[int] = set()
    for token in str(rows[0].get("row_pks") or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.add(int(token))
        except ValueError as exc:
            raise PersistError(
                f"remediation_change_log holds a row_pk that is not an image id: {token!r}"
            ) from exc
    return out, _as_int(rows[0]["disagreeing"], what="journalled rows disagreeing with the data")


def command_apply(output: Path | None = None) -> int:
    output = OUTPUT if output is None else output
    apply_path = output / "APPLY.sql"
    if not apply_path.is_file():
        raise PersistError(f"{apply_path} does not exist - run --plan first")
    plan_path = output / "PLAN.jsonl"
    records = load_plan_records(plan_path)
    run_stamp = load_plan_stamp(records, path=plan_path)
    ids = planned_ids(records)
    script = apply_path.read_text(encoding="utf-8")
    digest = verify_delivered(apply_path, records)
    expected = re.search(r"^-- (\d+) row\(s\)", script, re.MULTILINE)
    if expected is None:
        raise PersistError(
            "APPLY.sql has no row count in its header; it was not emitted by this script"
        )
    if int(expected.group(1)) != len(ids):
        raise PersistError(
            f"APPLY.sql claims {expected.group(1)} row(s) but PLAN.jsonl holds {len(ids)}: the two "
            "files are not the same plan; refusing to send either"
        )
    print(f"applying {_relative(apply_path)}: {len(ids)} row(s), plan sha256 {digest}")

    try:
        proc = run_psql(script, check=False)
    except OutcomeUnknown as exc:
        raise OutcomeUnknown(
            f"{exc} Read the journal before any retry: SELECT count(*) FROM "
            f"remediation_change_log WHERE run_stamp = {run_stamp!r}; "
            f"the write is landed only if that count is {len(ids)}."
        ) from exc
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        if retry_already_applied(ids, run_stamp):
            print(
                f"APPLY NOT NEEDED: psql exited {proc.returncode}, but the journal for "
                f"{run_stamp!r} already holds every one of the {len(ids)} planned row(s) and no "
                "journalled row disagrees with the value it recorded. This is a retry of a write "
                "that landed - nothing was written now. Run --verify for the full read-back."
            )
            return EXIT_NOTHING
        print(f"APPLY FAILED: psql exit={proc.returncode}")
        return EXIT_INCONSISTENT
    print("APPLY OK")
    return command_verify(output)


def retry_already_applied(ids: set[int], run_stamp: str) -> bool:
    """True when the planned rows are already written and journalled under `run_stamp`.

    A retry of a landed write trips guard 3 - it refuses a row that no longer holds the planned
    old value - and reporting that as `APPLY FAILED` invites a second attempt at a write that is
    already in the audit trail.
    """
    journalled, disagreeing = journalled_ids(run_stamp)
    return journalled == ids and disagreeing == 0


def command_verify(output: Path | None = None) -> int:
    """Re-read the landed state, identity by identity.

    The plan is an independent source - it was written before the write - so the journal's row set
    is compared with the plan's id set. A count alone is satisfied by 105 right values on 105 wrong
    rows, and the run-local count used to be compared against a *table-wide* one that agreed only
    because G0 was the first writer of `site_photo`. The table-wide number is printed by
    `verify_sql`, under a label that says what it is, and compared to nothing.
    """
    output = OUTPUT if output is None else output
    plan_path = output / "PLAN.jsonl"
    records = load_plan_records(plan_path)
    run_stamp = load_plan_stamp(records, path=plan_path)
    expected_ids = planned_ids(records)
    kinds = kinds_of(records)

    proc = run_psql(verify_sql(run_stamp, kinds), rows=True, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"VERIFY FAILED: psql exit={proc.returncode}")
        return EXIT_VERIFY_FAILED

    metrics: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "|" in line:
            name, _, value = line.rpartition("|")
            metrics[name.strip()] = value.strip()

    failures = []
    must_be_zero = (
        "journal rows for this run outside",
        "journal rows for this run with no evidence",
        "rows with a kind outside the vocabulary",
        unjournalled_label(kinds),
    )
    for name, value in metrics.items():
        if name.startswith(must_be_zero) and value != "0":
            failures.append(f"{name} = {value} (expected 0)")

    journal = metrics.get("journal rows for this run")
    if journal != str(len(expected_ids)):
        failures.append(
            f"journal rows for this run = {journal}, the plan has {len(expected_ids)} row(s)"
        )

    journalled, disagreeing = journalled_ids(run_stamp)
    if disagreeing != 0:
        failures.append(
            f"{disagreeing} journalled row(s) of {run_stamp!r} no longer hold the value the "
            "journal recorded"
        )
    if journalled != expected_ids:
        missing = sorted(expected_ids - journalled)[:5]
        unexpected = sorted(journalled - expected_ids)[:5]
        failures.append(
            f"the journal for {run_stamp!r} names {len(journalled)} row(s), the plan names "
            f"{len(expected_ids)}: {len(expected_ids - journalled)} planned id(s) not journalled "
            f"{missing}, {len(journalled - expected_ids)} journalled id(s) not in the plan "
            f"{unexpected}"
        )

    if failures:
        print("VERIFY FAILED:")
        for f in failures:
            print(f"  {f}")
        return EXIT_VERIFY_FAILED
    print(
        f"VERIFY OK ({len(journalled)} journalled row(s), the same rows as the plan's "
        f"{len(expected_ids)}, each still holding the value the journal recorded)"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true", help="read-only: emit the plan and its SQL")
    group.add_argument("--rehearse", action="store_true", help="run APPLY.sql and roll it back")
    group.add_argument(
        "--rehearse-rollback",
        action="store_true",
        help="run ROLLBACK.sql with COMMIT swapped for ROLLBACK, then report",
    )
    group.add_argument(
        "--check-primitive", action="store_true", help="probe the journalled primitive"
    )
    group.add_argument("--apply", action="store_true", help="write the planned rows")
    group.add_argument("--verify", action="store_true", help="read-only: prove the landed state")
    parser.add_argument(
        "--source",
        choices=sorted(SOURCES),
        default="stills",
        help="stills: G0, the landed batch (default); rejected-kinds: G0b",
    )
    args = parser.parse_args(argv)
    output = output_for(args.source)

    try:
        if args.plan:
            return command_plan(args.source)
        if args.rehearse:
            return command_rehearse(output)
        if args.rehearse_rollback:
            return command_rehearse_rollback(output)
        if args.check_primitive:
            return command_check_primitive()
        if args.apply:
            return command_apply(output)
        return command_verify(output)
    except OutcomeUnknown as exc:
        print(f"OUTCOME UNKNOWN: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN
    except PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
