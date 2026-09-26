"""The snapshot-driven plan: every site asked about its own fields, with no census finding.

Piece 5 of the Phase-3 runner (`output/remediation/phase3_runner/PIECE5_BRIEF.md`). The
finding-driven plan (`phase3.run plan`) can only reach sites the census flagged, because it is
built from `WORKLIST.jsonl`'s findings: 1,813 of the 5,004 sites. Measured against it, the
blinded check's false-negative rate is 60.0 % - 24 of 40 errors were on sites the census had left
alone (`output/remediation/gold_standard/fnr_result.json`), and 13 of the 17 sites carrying those
24 errors are not in the worklist at all. A finding-driven planner has no way to reach them; this
module builds the plan that does. Its records are states of the database, not of the census: one
site per row of the offline snapshot, and its findings are the site's **own stored values**.

Where each value comes from - read, not assumed:

* `description`, `period_start`, `site_type`, `country` - `unified_sites`, exactly as
  `gold_standard/truth_fields.json`'s `stored_in` key names them (16 of its 24 entries).
* `card_description` - **`card_stats`**, the other table (5 of its 24 entries): the column is not
  on `unified_sites`, which is the mistake that key was added to prevent.
* `wikidata_qid` - **`site_external_ids`** (`kind='wikidata_qid'`, 4,618 of its 9,237 rows), which
  is what routes this pass to a Wikidata item. **Measured on the snapshot (2026-09-21):
  `card_stats.wikidata_qid` is NULL in all 5,004 rows**, and nothing in this repository ever
  writes that column - `api/boot_schema.py::API_BOOT_SCHEMA` creates it with
  `ADD COLUMN IF NOT EXISTS` and the only writer of a Q-id is
  `pipeline/lyra/prospector/external_ids.py:55`, into `site_external_ids`.
  `recon/reusable-tooling.md:292` names the same 4,618 QIDs in the same file as this project's
  input of record, and `mechanical/PLAN.md:30` counts the same rows as its anchor
  (`site_external_ids:wikidata_qid`). Reading the column the brief's §3 sentence names would route
  **no** site to Wikidata; the value is read from the table that carries it.

`scope` is deliberately **not** one of the fields. The truth fixture's 3 remaining entries are
scope decisions - `stored_in: null`, `stored_value: null`, "out of scope - the record should be
hidden or removed" - and they are not a value in any column, so no per-field value question can
produce them (`FIELD_STORED_IN` names only the five fields this pass asks about). Those 3 entries
are out of reach for this piece by construction; `PIECE5.md` reports it as a known cap rather than
letting it read as a recall result.

Determinism is piece 1's standard: the snapshot's own file order is the plan's order, keys are
sorted, the newline is pinned, and **no timestamp is written**. A site-id list *selects*; it does
not order, so two files holding the same ids in different orders cannot produce two different
plans. Two runs on the same inputs are byte-identical.
"""

from __future__ import annotations

import gzip
import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

# Dual use: `python -m phase3.snapshot_plan` and `python scripts/remediation/phase3/run.py`. The
# package is not installed, so the parent directory must be importable first (same shim as
# `run.py`).
if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3.fetch_stage import QID_PATTERN  # noqa: E402  - one spelling of "a Wikidata Q-number"
from phase3.run import DISCOVER_PASS, REPO, InputError  # noqa: E402

#: Where the offline export lives. `MANIFEST.txt` in it names the export this plan was built
#: against (2026-09-20T20:20:01+02:00, host `ancientnerds`, 5,004 `unified_sites` rows).
DEFAULT_SNAPSHOT_DIR = REPO / "output" / "remediation" / "snapshot"
UNIFIED_SITES_FILE = "unified_sites.jsonl.gz"
CARD_STATS_FILE = "card_stats.jsonl.gz"
SITE_EXTERNAL_IDS_FILE = "site_external_ids.jsonl.gz"

#: The field whose value lives in another table. `truth_fields.json` is explicit about it: its 5
#: `card_description` entries are the `stored_in: card_stats` ones, and reading the value off
#: `unified_sites` finds no such column at all.
DISCOVER_FIELDS: tuple[str, ...] = (
    "description",
    "period_start",
    "site_type",
    "country",
    "card_description",
)

#: Which table each planned field's value is read from. This is `truth_fields.json`'s own
#: `stored_in` mapping for the fields that have one; the fixture is not read at plan time (the plan
#: must not depend on the gold standard), and `test_every_planned_value_comes_from_the_table_truth_
#: fields_json_names` asserts the two agree for all 21 entries that name a table.
FIELD_STORED_IN: dict[str, str] = {
    "description": "unified_sites",
    "period_start": "unified_sites",
    "site_type": "unified_sites",
    "country": "unified_sites",
    "card_description": "card_stats",
}

#: The `site_external_ids` kind that carries a Wikidata item id.
QID_KIND = "wikidata_qid"

#: Every planned field's finding gets this severity, because the pass has no finding from which to
#: read one: nothing flagged these sites, so there is no check family and no measured level. What
#: the census itself calls this level (`phase3.model.Severity`): "visibly wrong on an indexed page
#: (name, country, type, period bucket)" - which is what a wrong country, type or year is. It is a
#: placeholder with a stated reason, not a judgement: the verdict that carries the real severity is
#: the one a later piece writes from an answer, and this value is what the record says until then.
DISCOVER_SEVERITY = "moderate"

#: `phase3.model.Finding`'s own dimension for a Phase-3 finding, and the `test_id` prefix piece 1
#: fixed: `P3/<field>`, one per field, so an answer can be filed against the field it answered.
DISCOVER_DIMENSION = "phase3"
TEST_ID_PREFIX = "P3/"


def site_type_vocabulary(*, snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> tuple[str, ...]:
    """The `site_type` values the catalogue uses, sorted - the buckets a stored type is drawn from.

    The pass judges a stored `site_type` against the evidence's own phrasing, and the evidence almost
    never uses a catalogue value ("triumphal arch" is not one of the 70). Without the list the
    question can only be answered by guessing whether a phrase and a bucket are the same thing, and
    the second live run guessed wrong on all four `site_type` flags it raised - `Castle/palace`
    against "folly castle", `Gate/archway/bridge` against "triumphal arch", `Fortress/citadel`
    against "hill fort", `Megalithic statues` against "ahu" - because it compared the evidence's
    wording with the stored bucket as if the wording were the target value.

    Read from the snapshot, so the question cannot be built from a hand-copy of the list that has
    since drifted, and an empty result raises instead of yielding a question with no list in it.
    """
    path = snapshot_dir / UNIFIED_SITES_FILE
    values = {
        str(row["site_type"]).strip()
        for row in read_snapshot_jsonl(path)
        if str(row.get("site_type") or "").strip()
    }
    if not values:
        raise InputError(
            f"{path}: no non-empty site_type value at all; the discover question asks which of the "
            "catalogue's values the evidence describes, so a plan built from this snapshot would "
            "ask a question it cannot answer"
        )
    return tuple(sorted(values))


def read_snapshot_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a gzipped JSONL export in file order, refusing anything odd.

    Fail-closed like `phase3.run.read_jsonl`: a blank line, a line that is not JSON, or a line that
    is not an object is an input error rather than something to skip past. A plan built from a
    quietly shorter file is a plan that audits fewer sites than its own count says.
    """
    if not path.exists():
        raise InputError(
            f"{path} does not exist; the snapshot is exported to {DEFAULT_SNAPSHOT_DIR} and its "
            "MANIFEST.txt names the export"
        )
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for number, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                raise InputError(f"{path}:{number}: empty line")
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InputError(f"{path}:{number}: not JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise InputError(f"{path}:{number}: expected a JSON object, got {type(row)}")
            rows.append(row)
    if not rows:
        raise InputError(f"{path}: holds no rows")
    return rows


def read_site_ids(path: Path, *, uuids: bool = False) -> list[str]:
    """One site id per line, in file order. A blank or repeated line is refused.

    `output/remediation/gold_standard/truth_sites.txt` is such a file. A blank line is refused
    because a file that grew a hole is a file whose own count no longer means what it says, and a
    repeated id is refused because it would buy that site's calls twice while the batch says 15
    sites.

    With `uuids`, every line must be a site id as production prints it (`unified_sites.id::text`:
    a lowercase, hyphenated UUID), because the ids are compared with production's as text - an
    upper-case or braced id would match nothing and exclude nothing. The one reader of such a list:
    Phase 4's `plan4.py build --exclude` and `write_gate4.py --audited` read through it with
    `uuids`, `audit4.py`'s `--written`, `--exclude` and `--site-ids` without it (each id there must
    be a reviewed site of the run).
    """
    if not path.exists():
        raise InputError(f"no site-id list at {path}")
    ids: list[str] = []
    seen: set[str] = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        site_id = raw.strip()
        if not site_id:
            raise InputError(f"{path}:{number}: empty line; one site id per line, no holes")
        if uuids and not _canonical_uuid(site_id):
            raise InputError(f"{path}:{number}: {site_id!r} is not a site id")
        if site_id in seen:
            raise InputError(f"{path}:{number}: {site_id} appears twice")
        seen.add(site_id)
        ids.append(site_id)
    if not ids:
        raise InputError(f"{path}: holds no site ids")
    return ids


def _canonical_uuid(text: str) -> bool:
    """`text` is a UUID in its canonical form: lowercase, hyphenated, no braces."""
    try:
        return str(uuid.UUID(text)) == text
    except ValueError:
        return False


def qids_by_site(rows: Iterable[Mapping[str, Any]], *, origin: str) -> dict[str, str]:
    """`{site_id: qid}` from the `wikidata_qid` rows of `site_external_ids.jsonl.gz`.

    A value that is not a Q-number, a row without a site, or one site carrying two different ids
    raises: a mangled id would build a `wbgetentities` URL that answers with **no entities**, and
    an empty answer reads as "the item says nothing about this site" - evidence against the stored
    value that nobody ever fetched.
    """
    qids: dict[str, str] = {}
    for number, row in enumerate(rows, start=1):
        if row.get("kind") != QID_KIND:
            continue
        site_id = str(row.get("site_id") or "")
        value = str(row.get("value") or "")
        if not site_id or not QID_PATTERN.fullmatch(value):
            raise InputError(
                f"{origin}:{number}: a {QID_KIND} row is not a (site, Q-number) pair: "
                f"site_id={site_id!r} value={value!r}"
            )
        if site_id in qids and qids[site_id] != value:
            raise InputError(
                f"{origin}:{number}: {site_id} carries two {QID_KIND} values "
                f"({qids[site_id]!r} and {value!r}); a record cannot be routed to two items"
            )
        qids[site_id] = value
    return qids


def stored_value(*, site: Mapping[str, Any], card: Mapping[str, Any] | None, field: str) -> Any:
    """The field's value, read from the table `FIELD_STORED_IN` names. Nothing is derived.

    A `card_stats` row that does not exist is `None` and stays `None`: the field stores nothing for
    that site, and a missing table row is not emptier than a NULL column - both mean "there is no
    value here", which is the case the field question has to be able to answer.
    """
    table = FIELD_STORED_IN[field]
    if table == "card_stats":
        return None if card is None else card.get(field)
    return site.get(field)


def finding_row(field: str, value: Any) -> dict[str, Any]:
    """One planned finding: the field, its stored value, and where that value was read from."""
    return {
        "current_value": value,
        "dimension": DISCOVER_DIMENSION,
        "field": field,
        "note": (
            f"discover pass: no census check flagged this site, so nothing points at its own "
            f"stored {field}; the value is read from {FIELD_STORED_IN[field]} and judged against "
            "this message's evidence"
        ),
        "severity": DISCOVER_SEVERITY,
        "test_id": f"{TEST_ID_PREFIX}{field}",
    }


def discover_site_record(
    *, site: Mapping[str, Any], card: Mapping[str, Any] | None, qid: str | None
) -> dict[str, Any]:
    """One plan record: the site's name, its qid when it has one, and one finding per field.

    The caller has already checked that the row carries an `id` (`build_discover_sites` needs it to
    find this site's `card_stats` row and qid, and a row without one cannot be named in an error
    either) - so this function checks the name, which is what its own routes start from.
    """
    site_id = str(site.get("id") or "")
    name = site.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InputError(
            f"{site_id}: name is {name!r}; every route this pass uses starts from the stored name, "
            "and a record without one would be planned and then unfetchable"
        )
    record: dict[str, Any] = {
        "findings": [
            finding_row(field, stored_value(site=site, card=card, field=field))
            for field in DISCOVER_FIELDS
        ],
        "name": name,
        "site_id": site_id,
    }
    if qid:
        record["wikidata_qid"] = qid
    return record


def build_discover_sites(
    *, snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR, site_ids: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    """Every site of the snapshot, or just `site_ids`, **in the snapshot's own file order**.

    `site_ids` selects; the file order is the order. An id that is not in the snapshot raises and is
    named, because dropping it would leave a plan whose own count hides the site that was asked for
    and never audited.
    """
    unified_path = snapshot_dir / UNIFIED_SITES_FILE
    unified = read_snapshot_jsonl(unified_path)
    cards = {
        str(row.get("site_id") or ""): row
        for row in read_snapshot_jsonl(snapshot_dir / CARD_STATS_FILE)
    }
    qids = qids_by_site(
        read_snapshot_jsonl(snapshot_dir / SITE_EXTERNAL_IDS_FILE),
        origin=str(snapshot_dir / SITE_EXTERNAL_IDS_FILE),
    )

    ids_in_order = [str(row.get("id") or "") for row in unified]
    duplicates = len(ids_in_order) - len(set(ids_in_order))
    if duplicates:
        raise InputError(
            f"{unified_path}: {duplicates} duplicate site id(s); a repeated row would be planned "
            "twice and its calls bought twice"
        )

    rows = unified
    if site_ids is not None:
        if len(set(site_ids)) != len(site_ids):
            raise InputError(
                f"the site-id list carries {len(site_ids) - len(set(site_ids))} repeat(s)"
            )
        known = set(ids_in_order)
        missing = [site_id for site_id in site_ids if site_id not in known]
        if missing:
            shown = ", ".join(missing[:5])
            more = f" (and {len(missing) - 5} more)" if len(missing) > 5 else ""
            raise InputError(
                f"{len(missing)} site id(s) are not in {unified_path}: {shown}{more}. A plan that "
                "silently drops them audits fewer sites than it was asked to"
            )
        wanted = set(site_ids)
        rows = [row for row in unified if str(row["id"]) in wanted]

    records: list[dict[str, Any]] = []
    for row in rows:
        site_id = str(row.get("id") or "")
        if not site_id:
            raise InputError(f"a {UNIFIED_SITES_FILE} row carries no 'id': {dict(row)!r}")
        records.append(
            discover_site_record(site=row, card=cards.get(site_id), qid=qids.get(site_id))
        )
    return records
