"""The Phase-4/5 writer: a verified assembly becomes guarded, journalled production rows.

Design entry [6] (`output/remediation/logs/design_texts_images_2026-09-22.json`), sections
production_write and verification ("A site is written if and only if"). Work item WB-D2. This is the
only part of Phases 4 and 5 that plans a change to the database; `output/remediation/tools/
write_gate4.py` runs what it renders, `phase4/revert4.py` renders the reversal from the journal.

## Row groups

| group | rows per site | test_id | column | change-key lane / stamp family | batch id |
| --- | --- | --- | --- | --- | --- |
| P4 | 2, site-atomic | `P4/description`, `P4/raw_data` | `unified_sites.description`, `.raw_data` | `phase4` | `p4-NNNN` |
| L | 1 | `P4/legacy-provenance` | `unified_sites.raw_data` | `phase4l` | `p4l-NNNN` |
| P5 | 1 | `P5/card`, `P5/card-clear` | `card_stats.card_description` | `phase5` | `p5-NNNN` |
| WC | 2, site-atomic | `WC/description`, `WC/raw_data` (a clear: `WC/description-clear`, `WC/raw_data-clear`) | `unified_sites.description`, `.raw_data` | `phase4wc` | `p4wc-NNNN` |

A write batch is the rows one group takes from one plan batch (`PLAN4.jsonl`, `p4-NNNN`, 15 sites),
under that batch's number with the group's prefix, and it is written as **one chunk**: at most 100
sites (the owner's step, PIECE6_BRIEF section 7), at most 200 rows for P4 and WC and 100 for L and
P5.

**WC** (owner decision O5 of 2026-09-26, `phase4/wc4.py`, runbook `docs/procedures/SENTENCE_CHECK.md`)
writes the March descriptions that stay after the sentence check: the kept sentences with new
markers, and `raw_data` with the rebuilt citations, the check record and lane L's moved provenance -
or, when nothing is kept, the description NULL and `raw_data` without those keys (NULL when nothing
else remains). It plans from its own plan (`wc/cli.py build` -> `WC4.<run>.jsonl`), like L, and each
site's live description and `raw_data` are read at the gate: a site that moved since it was checked
is refused, never written over.
The journal stamp is `<family>:<batch id>:chunk-NNNN`, where the chunk number is the write round
(1 unless a batch is written again after a revert: the stamps of a reverted round stay in the
journal, so a second round needs its own). `write_gate4.py --step 100` walks the batches and
stops after every 100 sites for the acceptance (`verify_writes4.py`), as Phase 3's gate did.

## What is planned, and what is refused (every refusal counted and named in REFUSED.jsonl)

P4 writes a site when all of the design's conditions hold: it carries an assembly after review, no
site-scope hold of any stage (a card-scope hold writes the description with `card: null`), its lane
is one whose pilot passed (`open_lanes`), a lane-T or lane-R site is on the independent audit's
cleared list, `verify` (verify4.verify_site, V1-V15, run here on exactly the text, raw_data and
quotes this row will write) returns no hold, and its journal evidence is complete (its lane's calls
by name - the selector's answer for W, S and T - the reviewer's answer and each call's prompt on
disk, and the calls in the ledger).
L writes the held sites whose text the March chain changed (`legacy4`); P5 writes the card of a site
whose P4 provenance is live in production and clears the old card of a held-card site whose card
carries a Phase-3 reviewer-cleared defect (one of the 709), with that finding as the evidence.

**Before every other rule, P4 and P5 refuse a site outside the owner's defect scope**
(`outside-defect-scope`; owner decision 2026-09-23, `phase4/scope4.py`): Phases 4/5 write only the
sites with proven text defects, and every other site's description and card stay exactly as they
are. Both planners take the scope as a required input - there is no default and no switch. **L takes
none** (owner decision 2026-09-24, "Alle kennzeichnen"): it writes no text, only the provenance that
shows the existing AI footnote, and it marks every March-AI text Phase 4 did not write, inside the
scope or not.

## The transaction (render_apply)

`\\set ON_ERROR_STOP on`, `BEGIN`, the temp plan table `ON COMMIT DROP`; guards before the loop -
(1) every site is an existing `ancient_nerds` site, and a card row has its `card_stats` row, (2) the
table, column, key column and test_id of every row are the group's allow-list, (3) every row is a
real change, in the column's own type, (4) every row still holds its old value (`IS DISTINCT FROM`
in the column's type); the `apply_remediation_change` loop; guards after it - every row holds its
new value, the journal and the plan agree row for row in both directions, and the two in-database
sha256 invariants: `raw_data->'_description_provenance'->>'desc_sha256'` is the sha256 of the
description (P4 and L), and the card's sha256 is the provenance's `card.text_sha256` (P5); `COMMIT`.
`REHEARSE.sql` is the same statement ending in `ROLLBACK`; `ROLLBACK.sql` is the inverse, run inside
a transaction that is itself rolled back (Phase 3's proof). All three carry the plan digest.

No DELETE, no schema change, nothing outside `source_id = 'ancient_nerds'`, and
`unified_sites.updated_at` is never written (it is outside the approved columns; the sitemap reads
the journal instead).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
import uuid
from collections.abc import Callable, Container, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import unquote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402 - the batch's evidence store
from phase3 import write_stage as W  # noqa: E402 - the psql seam, quoting, digests, change keys
from phase3.run import read_jsonl  # noqa: E402 - the one JSON-lines reader

from phase4 import legacy4, wc4  # noqa: E402 - lane L's decision; lane WC's invariants
from phase4 import model4 as M  # noqa: E402
from phase4 import scope4 as S  # noqa: E402 - the owner's defect scope

# ------------------------------------------------------------------------------------------------
# Groups, targets, test ids
# ------------------------------------------------------------------------------------------------


class Group(StrEnum):
    """The three row groups of production_write, and lane WC's (owner decision O5, 2026-09-26)."""

    P4 = "P4"  #: description and raw_data of a written site, site-atomic
    L = "L"  #: raw_data legacy provenance of a held site
    P5 = "P5"  #: card_stats.card_description, and card clears
    WC = "WC"  #: a March description checked sentence by sentence: trimmed or cleared, site-atomic


#: The journal family: `write_stage.change_key`'s lane and the run stamp's first part.
GROUP_FAMILY: Mapping[Group, str] = {
    Group.P4: "phase4",
    Group.L: "phase4l",
    Group.P5: "phase5",
    Group.WC: "phase4wc",
}
#: The write batch's id prefix. `output/remediation/tools/lanes.py` registers these as its lanes.
GROUP_PREFIX: Mapping[Group, str] = {
    Group.P4: "p4",
    Group.L: "p4l",
    Group.P5: "p5",
    Group.WC: "p4wc",
}

TEST_DESCRIPTION = "P4/description"
TEST_RAW_DATA = "P4/raw_data"
TEST_LEGACY = "P4/legacy-provenance"
TEST_CARD = "P5/card"
TEST_CARD_CLEAR = "P5/card-clear"
TEST_WC_DESCRIPTION = "WC/description"
TEST_WC_RAW_DATA = "WC/raw_data"
#: A site whose check kept nothing: the description NULL, raw_data without the WC keys.
TEST_WC_DESCRIPTION_CLEAR = "WC/description-clear"
TEST_WC_RAW_DATA_CLEAR = "WC/raw_data-clear"
#: The test ids whose row may write NULL, by group. Guard 3 renders them (`_null_tests_sql`).
NULL_TESTS: Mapping[Group, frozenset[str]] = {
    Group.P4: frozenset({TEST_CARD_CLEAR}),
    Group.L: frozenset({TEST_CARD_CLEAR}),
    Group.P5: frozenset({TEST_CARD_CLEAR}),
    Group.WC: frozenset({TEST_WC_DESCRIPTION_CLEAR, TEST_WC_RAW_DATA_CLEAR}),
}
#: A WC site's rows are one of these sets: a kept text (its description and raw_data), a clear, a
#: kept text whose every sentence and marker stayed byte for byte (raw_data alone: the rebuilt
#: citations and the check record), or the clear of a site whose raw_data is NULL and stays NULL
#: (the description alone: 12 of the 14 unclaimed texts had no raw_data on 2026-09-26, and a NULL
#: written over NULL is no change).
WC_PAIRS = (
    frozenset({TEST_WC_DESCRIPTION, TEST_WC_RAW_DATA}),
    frozenset({TEST_WC_DESCRIPTION_CLEAR, TEST_WC_RAW_DATA_CLEAR}),
    frozenset({TEST_WC_RAW_DATA}),
    frozenset({TEST_WC_DESCRIPTION_CLEAR}),
)


@dataclass(frozen=True)
class Target:
    """One writable column: its table, and how a stored value is compared with a planned one in
    SQL, in the column's own type. The key column is `write_stage.PK_COLUMN`'s, not restated."""

    table: str
    column: str
    compare: str  #: `{planned}` is the plan table's column; `u` is unified_sites, `c` card_stats

    @property
    def pk_column(self) -> str:
        return W.PK_COLUMN[self.table]


#: The only columns Phases 4 and 5 write (production_write, COLUMNS).
TARGETS: Mapping[str, Target] = {
    "description": Target(
        "unified_sites", "description", "u.description IS DISTINCT FROM {planned}"
    ),
    "raw_data": Target("unified_sites", "raw_data", "u.raw_data IS DISTINCT FROM {planned}::jsonb"),
    "card_description": Target(
        "card_stats", "card_description", "c.card_description IS DISTINCT FROM {planned}"
    ),
}

#: The (column, test_id) pairs each group may write: the allow-list guard 2 renders.
GROUP_ROWS: Mapping[Group, frozenset[tuple[str, str]]] = {
    Group.P4: frozenset({("description", TEST_DESCRIPTION), ("raw_data", TEST_RAW_DATA)}),
    Group.L: frozenset({("raw_data", TEST_LEGACY)}),
    Group.P5: frozenset({("card_description", TEST_CARD), ("card_description", TEST_CARD_CLEAR)}),
    Group.WC: frozenset(
        {
            ("description", TEST_WC_DESCRIPTION),
            ("raw_data", TEST_WC_RAW_DATA),
            ("description", TEST_WC_DESCRIPTION_CLEAR),
            ("raw_data", TEST_WC_RAW_DATA_CLEAR),
        }
    ),
}

#: One chunk is one step: at most 100 sites (the owner's rule), and at most this many rows.
CHUNK_SITES = 100
MAX_CHUNK_ROWS: Mapping[Group, int] = {Group.P4: 200, Group.L: 100, Group.P5: 100, Group.WC: 200}
#: `card_stats.card_description` is varchar(200); a longer card would be refused by the primitive
#: inside the transaction and take the chunk with it, so the plan refuses the one site instead.
CARD_MAX_CHARS = 200

PLAN_TABLE = "_phase4_plan"
PLAN_FILE = "PLAN.jsonl"
REFUSED_FILE = "REFUSED.jsonl"
UNCLAIMED_FILE = "UNCLAIMED.jsonl"
CHUNKS_DIR = "chunks"
APPLY_FILE = "APPLY.sql"
REHEARSE_FILE = "REHEARSE.sql"
ROLLBACK_FILE = "ROLLBACK.sql"
GENERATOR = "scripts/remediation/phase4/write4.py"

#: The folders a model stage leaves in its batch directory (write-once `EvidenceStore`s). The
#: journal records the sha256 of each of the site's files: the selector's and translator's answers
#: (`answers/`), the reviewer's (`reviews/`), and the exact prompt of every call (`prompts/`).
MODEL_FOLDERS = ("answers", "reviews", "prompts")

# Refusal rules: a site the plan looked at and did not write, counted by rule.
RULE_HELD = "site-held"
RULE_LANE_CLOSED = "lane-not-open"
RULE_NOT_AUDITED = "lane-needs-audit"
RULE_VERIFY = "verify4-holds"
RULE_EVIDENCE = "journal-evidence-incomplete"
RULE_NOT_A_CHANGE = W.RULE_NOT_A_CHANGE
RULE_NO_CARD = "no-card"
RULE_CARD_TOO_LONG = "card-too-long"
#: A site without a card_stats row (read-only, production): neither a card nor a clear can be
#: written, and planning one would let the chunk's preflight block the whole batch for it.
RULE_NO_CARD_ROW = "no-card-stats-row"
#: The live P4 provenance names a card P5 does not write (a card-scope hold added after P4 wrote):
#: neither a clear nor the March card may stand beside it - the site is reverted first.
RULE_CARD_NAMED = "live-provenance-names-an-unwritten-card"
RULE_WRITTEN = "written-by-p4"
RULE_NO_CLAIM = "no-legacy-claim"
RULE_MARKED = "provenance-present"
#: The owner's decision of 2026-09-23: a site outside the defect scope is never written (P4, P5;
#: lane L marks every March-AI text since the decision of 2026-09-24).
RULE_OUT_OF_SCOPE = "outside-defect-scope"
#: WC: production no longer holds the description or raw_data the site was checked with (a later
#: write - a P4 text, a revert, a hand edit): the check answers a text that is not served.
RULE_MOVED = "moved-since-check"
#: WC: a later WC plan asks the site again (its batch refused it here, or it was never written), so
#: that plan's answer is the one planned - one site, one planning batch (the review of 2026-09-26).
RULE_TAKEN_OVER = "asked-again-later"

_PLAN_BATCH = re.compile(r"p4-(?P<number>[0-9]{4,})")


class PlanInputError(W.WriteRefused):
    """A batch directory is not what the contract says it holds: a hole, not a refusal."""


# ------------------------------------------------------------------------------------------------
# Values
# ------------------------------------------------------------------------------------------------


def raw_json(value: Mapping[str, Any]) -> str:
    """`raw_data` as the writer serialises it (production_write, P4 raw_data)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def new_raw_data(old: Mapping[str, Any] | None, assembly: M.Assembly) -> dict[str, Any]:
    """The written `raw_data`: the old object with `description_citations` replaced and
    `_description_provenance` added; every other key and value is the old one (V12).

    The driver hands this exact object to `verify4.verify_site`, and the plan writes exactly its
    serialisation, so the verifier judges the bytes the row carries.
    """
    new = dict(old or {})
    new[M.CITATIONS_KEY] = [citation.to_dict() for citation in assembly.citations]
    new[M.PROVENANCE_KEY] = assembly.provenance.to_dict()
    return new


def legacy_raw_data(old: Mapping[str, Any] | None, legacy: M.LegacyProvenance) -> dict[str, Any]:
    """Lane L's `raw_data`: the old object plus `_description_provenance`; nothing else moves."""
    new = dict(old or {})
    new[M.PROVENANCE_KEY] = legacy.to_dict()
    return new


def without_card(assembly: M.Assembly) -> M.Assembly:
    """The assembly of a site whose card is held: the description is written, the card is not,
    and the provenance says so (`card: null`), so nothing claims a card that is not live."""
    return dataclasses.replace(
        assembly, card=None, provenance=dataclasses.replace(assembly.provenance, card=None)
    )


# ------------------------------------------------------------------------------------------------
# The journal evidence (p_evidence)
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelFile:
    """One file a model stage left for a site: its folder, its feature and its sha256."""

    folder: str
    feature: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"folder": self.folder, "feature": self.feature, "sha256": self.sha256}


def model_files(batch_dir: Path, site_id: str) -> tuple[ModelFile, ...]:
    """Every file of this site under `answers/`, `reviews/` and `prompts/`, in a fixed order.

    Read by the store's own naming (`EvidenceStore.slug`: `<site>%2F<feature>.txt`), so no feature
    name is assumed: whatever the stages stored is what the journal records.
    """
    prefix = F.EvidenceStore.slug(site_id, "")
    found: list[ModelFile] = []
    for folder in MODEL_FOLDERS:
        root = batch_dir / folder
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.txt")):
            stem = path.name[: -len(".txt")]
            if not stem.startswith(prefix):
                continue
            found.append(
                ModelFile(
                    folder=folder,
                    feature=unquote(stem[len(prefix) :]),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
    return tuple(found)


def reviewer_lines(batch_dir: Path, site_id: str) -> tuple[str, ...]:
    """The reviewer's answer lines for this site, verbatim, in file order (`reviews/`)."""
    root = batch_dir / "reviews"
    prefix = F.EvidenceStore.slug(site_id, "")
    lines: list[str] = []
    if root.is_dir():
        for path in sorted(root.glob(f"{prefix}*.txt")):
            lines.extend(
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
    return tuple(lines)


def ledger_labels(
    ledger: Sequence[Mapping[str, Any]], *, batch_id: str, site_id: str
) -> tuple[str, ...]:
    """The labels of this site's model calls in this batch (`<site_id>/<answer_key>`, the phase-3
    ledger's call label), in ledger order. `ledger` is the rows of the batch's own run's ledger
    (`<run>/LEDGER.jsonl`, `model4.LEDGER_FILE`; `write_gate4` reads no other): batch ids repeat
    across runs - every pilot is `p4-0001` .. - so a ledger shared across runs would put one
    pilot's calls into another's evidence (pilot 2's open item, 2026-09-24)."""
    return tuple(
        str(row["label"])
        for row in ledger
        if row.get("kind") == "model_call"
        and row.get("batch_id") == batch_id
        and str(row.get("label", "")).startswith(f"{site_id}/")
    )


def evidence_problems(
    files: Sequence[ModelFile], labels: Sequence[str], *, lane: M.Lane
) -> list[str]:
    """What the journal evidence of a written site lacks, call by call.

    A site is written only if the calls its lane makes answered, **by name** (`model4.LANE_ANSWERS`
    under `answers/`: the selector's for lanes W, S and T - the design's p_evidence names the
    "selector-answer sha256" - T's translation beside it, and lane R's one restricted call), and the
    reviewer answered (`model4.REVIEW_FEATURE` under `reviews/`). Every call is complete: each
    answer has the prompt it answered (`prompts/`, the same feature - `judge_site` keys the answer,
    the prompt store and the ledger label by the call's `answer_key`), each answer has its ledger
    line (`<site_id>/<feature>` in this batch), and each ledger call of the site has its answer on
    disk.
    """
    present = {(entry.folder, entry.feature) for entry in files}
    needed = [("answers", feature) for feature in M.LANE_ANSWERS[lane]]
    needed.append(("reviews", M.REVIEW_FEATURE))
    problems = [
        f"no {folder}/{feature}: this lane's site needs that call"
        for folder, feature in needed
        if (folder, feature) not in present
    ]
    if not labels:
        problems.append("no model call in the ledger for this batch")
    prompted = {entry.feature for entry in files if entry.folder == "prompts"}
    answered = {entry.feature: entry.folder for entry in files if entry.folder != "prompts"}
    called = {label.split("/", 1)[1] for label in labels}
    for feature, folder in sorted(answered.items()):
        if feature not in prompted:
            problems.append(f"{folder}/{feature} has no prompt in prompts/")
        if labels and feature not in called:
            problems.append(f"{folder}/{feature} has no ledger line")
    for feature in sorted(called - set(answered)):
        problems.append(f"the ledger call {feature} has no answer on disk")
    return problems


def subject_verdicts(metas: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """The subject gate's verdict of every cited source that carries one (W and T), by source id,
    read from the pinned `src.<id>.meta` (`model4.SourceDoc`)."""
    verdicts: dict[str, str] = {}
    for source_id, meta in sorted(metas.items()):
        gate = M.SourceDoc.from_dict(meta).subject_gate
        if gate is not None:
            verdicts[source_id] = gate.verdict.value
    return verdicts


def journal_evidence(
    assembly: M.Assembly,
    *,
    texts: Mapping[str, str],
    subject_gate: Mapping[str, str],
    lane_detail: str,
    files: Sequence[ModelFile],
    reviews: Sequence[str],
    labels: Sequence[str],
) -> dict[str, Any]:
    """The design's `p_evidence` of a P4 site (production_write, JOURNAL).

    `sentences[i].quote` is `source_text[start:end]` of published sentence `i` - the quote the
    acceptance re-verifies production against, so the database alone can re-check every published
    sentence even if the local store is lost. Lane R's restricted quotes are held here only, never
    in public `raw_data`.
    """
    provenance = assembly.provenance
    sentences = [
        {
            "n": sentence.n,
            "src": sentence.src,
            "quote": texts[sentence.src][sentence.start : sentence.end],
            "start": sentence.start,
            "end": sentence.end,
            "drop": [[low, high] for low, high in sentence.drop],
        }
        for sentence in provenance.sentences
    ]
    return {
        "group": Group.P4.value,
        "lane": provenance.lane.value,
        "run": provenance.run,
        "sources": [
            {
                "id": source.id,
                "url": source.url,
                "revid": source.revid,
                "sha256": source.text_sha256,
                "licence": source.licence.value,
            }
            for source in provenance.sources
        ],
        "sentences": sentences,
        "desc_sha256": provenance.desc_sha256,
        "card": None if provenance.card is None else provenance.card.to_dict(),
        "reviewer_lines": list(reviews),
        "model_files": [entry.to_dict() for entry in files],
        "ledger_labels": list(labels),
        "subject_gate": dict(subject_gate),
        "lane_detail": lane_detail,
    }


# ------------------------------------------------------------------------------------------------
# Rows and plans
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Row4:
    """One single-row update, the plan's unit and the transaction's."""

    group: Group
    site_id: str
    site_name: str
    table: str
    pk_column: str
    pk: str
    column: str
    old_value: str | None
    new_value: str | None  #: `None` only for a card clear
    test_id: str
    evidence: dict[str, Any]
    change_key: str

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["group"] = self.group.value
        return payload

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Row4:
        return cls(**{**data, "group": Group(data["group"])})


def make_row(
    *,
    group: Group,
    site: M.PlanSite,
    column: str,
    old_value: str | None,
    new_value: str | None,
    test_id: str,
    evidence: dict[str, Any],
) -> Row4:
    """A row with its target and change key derived, never typed by hand."""
    target = TARGETS[column]
    return Row4(
        group=group,
        site_id=site.site_id,
        site_name=site.name,
        table=target.table,
        pk_column=target.pk_column,
        pk=site.site_id,
        column=column,
        old_value=old_value,
        new_value=new_value,
        test_id=test_id,
        evidence=evidence,
        change_key=W.change_key(
            site_id=site.site_id,
            table=target.table,
            column=column,
            old_value=old_value,
            new_value=new_value,
            test_id=test_id,
            lane=GROUP_FAMILY[group],
        ),
    )


@dataclass
class WritePlan4:
    """One write batch: its rows, every site it looked at and refused, and (L) the unclaimed."""

    group: Group
    batch_id: str  #: the write batch: `p4-NNNN`, `p4l-NNNN` or `p5-NNNN`
    rows: list[Row4] = field(default_factory=list)
    refusals: list[W.Refusal] = field(default_factory=list)
    unclaimed: list[legacy4.Unclaimed] = field(default_factory=list)

    def refusals_by_rule(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for refusal in self.refusals:
            counts[refusal.rule] = counts.get(refusal.rule, 0) + 1
        return dict(sorted(counts.items()))


def group_batch_id(plan_batch_id: str, group: Group) -> str:
    """The write batch of `group` taken from plan batch `p4-NNNN`: `p4-NNNN`, `p4l-NNNN`, `p5-NNNN`."""
    matched = _PLAN_BATCH.fullmatch(plan_batch_id)
    if matched is None:
        raise PlanInputError(f"{plan_batch_id!r} is not a plan batch id (p4-NNNN)")
    return f"{GROUP_PREFIX[group]}-{matched['number']}"


def validate_rows(group: Group, rows: Sequence[Row4]) -> None:
    """The plan-side mirror of the transaction's guards. Pure, so a test can break each one."""
    seen: set[tuple[str, str]] = set()
    p4_columns: dict[str, set[str]] = {}
    descriptions: dict[str, str] = {}
    for row in rows:
        where = f"{row.site_id}/{row.column}"
        if row.group is not group:
            raise W.WriteRefused(f"{where}: a {row.group.value} row in a {group.value} plan")
        key = (row.site_id, row.column)
        if key in seen:
            raise W.WriteRefused(f"{where} appears twice - the plan is not a set")
        seen.add(key)
        try:
            uuid.UUID(row.site_id)
        except ValueError:
            raise W.WriteRefused(f"{row.site_id!r} is not a UUID") from None
        if (row.column, row.test_id) not in GROUP_ROWS[group]:
            raise W.WriteRefused(
                f"{where}: ({row.column}, {row.test_id}) is not a {group.value} row "
                f"(allowed: {sorted(GROUP_ROWS[group])})"
            )
        target = TARGETS[row.column]
        if (row.table, row.pk_column) != (target.table, target.pk_column):
            raise W.WriteRefused(
                f"{where}: {row.table}.{row.pk_column} is not the column's own table and key"
            )
        if row.pk != row.site_id:
            raise W.WriteRefused(f"{where}: pk {row.pk!r} is not the site id")
        if row.new_value == row.old_value:
            raise W.WriteRefused(f"{where}: old and new are the same value - not a change")
        if row.new_value is None and row.test_id not in NULL_TESTS[group]:
            raise W.WriteRefused(
                f"{where}: only a card clear or a WC clear writes NULL "
                f"({sorted(NULL_TESTS[group])} in a {group.value} plan)"
            )
        if row.new_value is not None and not row.new_value.strip():
            raise W.WriteRefused(f"{where}: an empty new value")
        if row.column == "card_description" and row.new_value is not None:
            if len(row.new_value) > CARD_MAX_CHARS:
                raise W.WriteRefused(f"{where}: {len(row.new_value)} characters in varchar(200)")
        if row.column == "raw_data":
            _validate_raw_data(row)
        if row.column == "description" and row.new_value is not None:
            descriptions[row.site_id] = row.new_value
        if not row.evidence:
            raise W.WriteRefused(f"{where}: a write without evidence is not auditable")
        expected = W.change_key(
            site_id=row.site_id,
            table=row.table,
            column=row.column,
            old_value=row.old_value,
            new_value=row.new_value,
            test_id=row.test_id,
            lane=GROUP_FAMILY[group],
        )
        if row.change_key != expected:
            raise W.WriteRefused(f"{where}: change_key {row.change_key!r} is not the row's digest")
        if group is Group.P4:
            p4_columns.setdefault(row.site_id, set()).add(row.column)
    for site_id, columns in p4_columns.items():
        if columns != {"description", "raw_data"}:
            raise W.WriteRefused(
                f"{site_id}: a P4 site is written site-atomic, description and raw_data together; "
                f"this plan has {sorted(columns)}"
            )
    if group is Group.P4:
        for row in rows:
            if row.column != "raw_data":
                continue
            provenance = M.parse_json(str(row.new_value))[M.PROVENANCE_KEY]
            if provenance["desc_sha256"] != M.text_sha256(descriptions[row.site_id]):
                raise W.WriteRefused(
                    f"{row.site_id}: the provenance's desc_sha256 is not the sha256 of the "
                    "description this plan writes"
                )
    if group is Group.WC:
        _validate_wc_sites(rows)


def _validate_wc_sites(rows: Sequence[Row4]) -> None:
    """A WC site is written site-atomic - its description and raw_data rows together (both
    kept-text rows or both clear rows), or its raw_data alone when the kept text is the stored one
    byte for byte - and the pair it leaves holds lane WC's invariants (`wc4.wc_problems`: the check
    record's and lane L's hashes, the citations D1 needs; a clear carries none of the three keys).
    The description it leaves is the evidence's (`wc4.EVIDENCE_DESCRIPTION`), which the description
    row, where there is one, writes. Every raw_data key outside the three stays as it was."""
    by_site: dict[str, dict[str, Row4]] = {}
    for row in rows:
        by_site.setdefault(row.site_id, {})[row.column] = row
    for site_id, pair in by_site.items():
        tests = frozenset(row.test_id for row in pair.values())
        if tests not in WC_PAIRS:
            raise W.WriteRefused(
                f"{site_id}: a WC site is written site-atomic (a kept text, a clear, a kept text "
                f"that stayed byte for byte, or the clear of a NULL raw_data); this plan has "
                f"{sorted(tests)}"
            )
        evidence = (pair.get("raw_data") or pair["description"]).evidence
        left = evidence[wc4.EVIDENCE_DESCRIPTION]
        if "description" in pair and (
            pair["description"].evidence != evidence
            or pair["description"].new_value != left
            or pair["description"].old_value != evidence["checked"]
        ):
            raise W.WriteRefused(
                f"{site_id}: the description row is not the evidence's transition (the checked "
                "text to the one its decisions compose)"
            )
        if "description" not in pair and (left is None or left != evidence["checked"]):
            raise W.WriteRefused(
                f"{site_id}: a WC raw_data row without its description row leaves the stored text"
            )
        # Without a raw_data row the site's raw_data is NULL and stays NULL (the one such pair is a
        # clear, WC_PAIRS); the transaction's invariant 6 holds the stored value to it.
        raw = pair.get("raw_data")
        new = None if raw is None or raw.new_value is None else M.parse_json(raw.new_value)
        old = None if raw is None or raw.old_value is None else M.parse_json(raw.old_value)
        # the invariants, the recorded marking re-derived from the row's own old value, and the AI
        # disclosure that marking requires (the review of 2026-09-26: required, not only checked)
        marking = evidence["marking"]
        problems = (
            wc4.wc_problems(left, new)
            + wc4.old_marking_problems(marking, evidence["checked"], old)
            + wc4.disclosure_problems(marking, left, new)
        )
        if problems:
            raise W.WriteRefused(f"{site_id}: " + "; ".join(problems))
        kept = {key: value for key, value in (new or {}).items() if key not in wc4.WC_KEYS}
        before = {key: value for key, value in (old or {}).items() if key not in wc4.WC_KEYS}
        if kept != before:
            raise W.WriteRefused(
                f"{site_id}/raw_data: a WC row changes keys outside {sorted(wc4.WC_KEYS)}"
            )


def _validate_raw_data(row: Row4) -> None:
    """A raw_data row writes a JSON object whose provenance is the group's kind (WC: lane L's or
    none, and NULL for a cleared site that has nothing left - `_validate_wc_sites` checks the rest)."""
    if row.group is Group.WC:
        _validate_wc_raw_data(row)
        return
    new = M.parse_json(str(row.new_value))
    if not isinstance(new, dict):
        raise W.WriteRefused(f"{row.site_id}/raw_data: the new value is not a JSON object")
    if row.old_value is not None and not isinstance(M.parse_json(row.old_value), dict):
        raise W.WriteRefused(f"{row.site_id}/raw_data: the old value is not a JSON object")
    provenance = M.provenance_from_dict(new[M.PROVENANCE_KEY])
    legacy = isinstance(provenance, M.LegacyProvenance)
    if legacy != (row.group is Group.L):
        raise W.WriteRefused(
            f"{row.site_id}/raw_data: a {row.group.value} row writes "
            f"{'legacy' if legacy else 'full'} provenance"
        )
    if row.old_value is not None and M.parse_json(row.old_value) == new:
        raise W.WriteRefused(f"{row.site_id}/raw_data: the same JSON value - not a change")


def _validate_wc_raw_data(row: Row4) -> None:
    """A WC raw_data row: JSON objects (or NULL) on both sides and a real change as jsonb (NULL only
    for a clear: guard 3's test ids). What the object may carry - lane L's provenance or none, never
    a full Phase-4 one - is `wc4.wc_problems`, asked of the site's pair by `_validate_wc_sites`."""
    old = None if row.old_value is None else M.parse_json(row.old_value)
    new = None if row.new_value is None else M.parse_json(row.new_value)
    for side, value in (("old", old), ("new", new)):
        if value is not None and not isinstance(value, dict):
            raise W.WriteRefused(f"{row.site_id}/raw_data: the {side} value is not a JSON object")
    if old == new:
        raise W.WriteRefused(f"{row.site_id}/raw_data: the same JSON value - not a change")


# ------------------------------------------------------------------------------------------------
# Reading one plan batch
# ------------------------------------------------------------------------------------------------

Verifier = Callable[..., tuple[M.Hold, ...]]


@dataclass(frozen=True)
class BatchInputs:
    """What one plan batch's directory holds, read strictly."""

    root: Path
    batch_id: str
    sites: tuple[M.PlanSite, ...]
    lanes: Mapping[str, M.LaneAssignment]
    assemblies: Mapping[str, M.Assembly]
    holds: Mapping[str, tuple[M.Hold, ...]]

    @property
    def evidence(self) -> F.EvidenceStore:
        return F.EvidenceStore(self.root / M.EVIDENCE_DIR)

    def site_holds(self, site_id: str, scope: M.HoldScope) -> tuple[M.Hold, ...]:
        return tuple(hold for hold in self.holds.get(site_id, ()) if hold.scope is scope)


def load_batch(batch_dir: Path) -> BatchInputs:
    """Read `input.json`, `lanes.jsonl`, `assembly.jsonl` and `holds.jsonl` of one plan batch.

    Every site must have reached an outcome - an assembly or a site hold - and everything must name
    a site of the batch. A batch that does not is a hole in the record and raises; it is not a set
    of refusals.
    """
    raw = M.parse_json((batch_dir / M.INPUT_FILE).read_text(encoding="utf-8"))
    batch_id = raw["batch_id"]
    if batch_id != batch_dir.name:
        raise PlanInputError(f"{batch_dir}: input.json names batch {batch_id!r}")
    group_batch_id(batch_id, Group.P4)
    for name in (M.LANES_FILE, M.ASSEMBLY_FILE, M.HOLDS_FILE):
        if not (batch_dir / name).exists():
            raise PlanInputError(
                f"{batch_id}: no {name}: the batch has not reached an outcome - the gate plans a "
                "batch once its review is imported"
            )
    sites = tuple(M.PlanSite.from_dict(site) for site in raw["sites"])
    ids = [site.site_id for site in sites]
    if len(set(ids)) != len(ids):
        raise PlanInputError(f"{batch_id}: a site is listed twice")
    known = set(ids)

    lanes: dict[str, M.LaneAssignment] = {}
    for assignment in M.load_jsonl(batch_dir / M.LANES_FILE, M.LaneAssignment):
        if assignment.site_id in lanes or assignment.site_id not in known:
            raise PlanInputError(f"{batch_id}: lanes.jsonl names {assignment.site_id} wrongly")
        lanes[assignment.site_id] = assignment
    if set(lanes) != known:
        raise PlanInputError(f"{batch_id}: lanes.jsonl misses {sorted(known - set(lanes))}")

    assemblies: dict[str, M.Assembly] = {}
    for assembly in M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly):
        if assembly.site_id in assemblies or assembly.site_id not in known:
            raise PlanInputError(f"{batch_id}: assembly.jsonl names {assembly.site_id} wrongly")
        assemblies[assembly.site_id] = assembly

    holds: dict[str, list[M.Hold]] = {}
    for hold in M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold):
        if hold.site_id not in known:
            raise PlanInputError(f"{batch_id}: holds.jsonl names {hold.site_id}, not in the batch")
        holds.setdefault(hold.site_id, []).append(hold)

    for site_id in ids:
        held = any(hold.scope is M.HoldScope.SITE for hold in holds.get(site_id, ()))
        if site_id not in assemblies and not held:
            raise PlanInputError(
                f"{batch_id}: {site_id} has neither an assembly nor a site hold - the batch has "
                "not reached an outcome for it"
            )
    return BatchInputs(
        root=batch_dir,
        batch_id=batch_id,
        sites=sites,
        lanes=lanes,
        assemblies=assemblies,
        holds={site_id: tuple(found) for site_id, found in holds.items()},
    )


def load_legacy_plan(path: Path) -> list[BatchInputs]:
    """Lane L's own plan (`plan4.py legacy`, owner decision 2026-09-24): every curated site of one
    read-only production read, one batch per line, read strictly.

    Every batch carries `legacy4.PLAN_MARK` (a P4 plan's batches carry none, so one is never read as
    the other) and a plan batch id; no batch id and no site is listed twice. An L batch has no
    directory and no stage outcome - `root` is the plan file, and it carries no lanes, assemblies or
    holds: lane L decides on the site's own values alone (`legacy4`).
    """
    batches: list[BatchInputs] = []
    batch_ids: set[str] = set()
    seen: set[str] = set()
    for number, record in enumerate(read_jsonl(path), start=1):
        batch_id = record["batch_id"]
        if record.get("pass") != legacy4.PLAN_MARK:
            raise PlanInputError(
                f"{path}:{number}: batch {batch_id} is not a lane-L plan batch (pass "
                f"{record.get('pass')!r}; plan4.py legacy writes {legacy4.PLAN_MARK!r})"
            )
        group_batch_id(batch_id, Group.L)
        if batch_id in batch_ids:
            raise PlanInputError(f"{path}:{number}: batch {batch_id} twice")
        batch_ids.add(batch_id)
        sites = tuple(M.PlanSite.from_dict(site) for site in record["sites"])
        for site in sites:
            if site.site_id in seen:
                raise PlanInputError(f"{path}:{number}: {site.site_id} is listed twice")
            seen.add(site.site_id)
        batches.append(
            BatchInputs(
                root=path, batch_id=batch_id, sites=sites, lanes={}, assemblies={}, holds={}
            )
        )
    return batches


#: The keys of one WC plan batch (`wc/cli.py build`).
_WC_PLAN_KEYS = frozenset({"batch_id", "ordinal", "pass", "sites", "outcomes"})


#: Lane WC's outcomes by plan batch id, in plan order (`load_wc_plan`): site id -> outcome.
WcOutcomes = Mapping[str, Mapping[str, wc4.WcOutcome]]


def load_wc_plan(
    paths: Sequence[Path],
) -> tuple[list[BatchInputs], dict[str, dict[str, wc4.WcOutcome]]]:
    """Lane WC's gate plans (`wc/cli.py build`, one per run - the pilot's, then each chunk's), read
    strictly and together: every batch carries `wc4.PLAN_MARK` and a plan batch id; no batch id
    occurs twice across the plans, and no site twice within one plan; every site has exactly one
    outcome (`wc4.WcOutcome`) and every outcome a site. The outcomes come back by plan batch, in
    plan order: a site a later plan asks again - its earlier batch refused it, or never wrote it -
    is that later plan's (`plan_wc`, `RULE_TAKEN_OVER`). A WC batch has no directory and no stage
    outcome: `root` is its plan file, and lanes, assemblies and holds are empty."""
    batches: list[BatchInputs] = []
    outcomes: dict[str, dict[str, wc4.WcOutcome]] = {}
    for path in paths:
        in_plan: set[str] = set()
        for number, record in enumerate(read_jsonl(path), start=1):
            where = f"{path}:{number}"
            if set(record) != _WC_PLAN_KEYS or record["pass"] != wc4.PLAN_MARK:
                raise PlanInputError(
                    f"{where}: not a lane-WC plan batch (keys {sorted(record)}, pass "
                    f"{record.get('pass')!r}; wc/cli.py build writes {wc4.PLAN_MARK!r})"
                )
            batch_id = record["batch_id"]
            group_batch_id(batch_id, Group.WC)
            if batch_id in outcomes:
                raise PlanInputError(f"{where}: batch {batch_id} twice")
            sites = tuple(M.PlanSite.from_dict(site) for site in record["sites"])
            own = [wc4.WcOutcome.from_dict(outcome) for outcome in record["outcomes"]]
            if [o.site_id for o in own] != [s.site_id for s in sites]:
                raise PlanInputError(f"{where}: the outcomes are not the batch's sites, in order")
            outcomes[batch_id] = {}
            for site, outcome in zip(sites, own, strict=True):
                if site.site_id in in_plan:
                    raise PlanInputError(f"{where}: {site.site_id} is listed twice in one plan")
                in_plan.add(site.site_id)
                outcomes[batch_id][site.site_id] = outcome
            batches.append(
                BatchInputs(
                    root=path, batch_id=batch_id, sites=sites, lanes={}, assemblies={}, holds={}
                )
            )
    return batches, outcomes


def wc_sites_planned_twice(plans: Sequence[WritePlan4]) -> dict[str, list[str]]:
    """Site id -> the WC write batches that plan rows for it, for every site more than one plans.
    `plan_wc` gives a site to one batch (`RULE_TAKEN_OVER`); two chunks read before either was
    written can still both claim it - two identical clears each read as its own write - and the
    gate then stops before anything is rendered."""
    by_site: dict[str, list[str]] = {}
    for plan in plans:
        for site_id in dict.fromkeys(row.site_id for row in plan.rows):
            by_site.setdefault(site_id, []).append(plan.batch_id)
    return {site_id: ids for site_id, ids in by_site.items() if len(ids) > 1}


def source_files(
    store: F.EvidenceStore, site_id: str, source_ids: Iterable[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """The raw `src.<id>.meta` objects and the pinned `src.<id>.txt` texts of the cited sources."""
    metas: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for source_id in source_ids:
        meta_path = store.path_for(site_id, M.source_feature(source_id, "meta"))
        text_path = store.path_for(site_id, M.source_feature(source_id, "txt"))
        metas[source_id] = M.parse_json(meta_path.read_text(encoding="utf-8"))
        texts[source_id] = text_path.read_bytes().decode("utf-8")
    return metas, texts


def witness_files(
    store: F.EvidenceStore, site_id: str
) -> tuple[dict[str, Any] | None, bytes | None]:
    """The site's Wikidata item as S1 pinned it: the raw `src.D.meta` object and the `src.D` answer's
    bytes, each `None` when S1 stored none. The verifier's `witness` (V6 accepts the item's English
    label for a strong 'own' verdict and checks the pin itself)."""
    meta_path = store.path_for(site_id, M.source_feature("D", "meta"))
    raw_path = store.path_for(site_id, M.source_feature("D", "raw"))
    meta = M.parse_json(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    return meta, raw_path.read_bytes() if raw_path.exists() else None


def _hold_detail(holds: Iterable[M.Hold]) -> str:
    return "; ".join(f"{hold.reason.value} ({hold.scope.value}): {hold.detail}" for hold in holds)


def _holds_json(holds: Iterable[M.Hold]) -> list[dict[str, str]]:
    return [hold.to_dict() for hold in holds]


def outside_scope(scope: S.DefectScope, site_id: str, field_name: str) -> W.Refusal | None:
    """The owner's rule, asked before every other: a site outside the defect scope is refused
    under `outside-defect-scope`, whatever else would hold or write it; `None` for a scope site."""
    if site_id in scope:
        return None
    return W.Refusal(
        site_id,
        field_name,
        RULE_OUT_OF_SCOPE,
        f"not in the owner's defect scope ({scope.label}): its description and card stay as "
        "they are",
    )


# ------------------------------------------------------------------------------------------------
# The three planners
# ------------------------------------------------------------------------------------------------


def plan_p4(
    batch: BatchInputs,
    *,
    scope: S.DefectScope,
    open_lanes: frozenset[M.Lane],
    audited: frozenset[str],
    verify: Verifier,
    ledger: Sequence[Mapping[str, Any]],
) -> WritePlan4:
    """P4: the description and raw_data rows of every site of the batch that may be written."""
    plan = WritePlan4(group=Group.P4, batch_id=group_batch_id(batch.batch_id, Group.P4))
    for site in batch.sites:
        outside = outside_scope(scope, site.site_id, "description")
        decided = outside or _p4_site(
            batch, site, open_lanes=open_lanes, audited=audited, verify=verify, ledger=ledger
        )
        if isinstance(decided, W.Refusal):
            plan.refusals.append(decided)
        else:
            plan.rows.extend(decided)
    validate_rows(Group.P4, plan.rows)
    return plan


def _p4_site(
    batch: BatchInputs,
    site: M.PlanSite,
    *,
    open_lanes: frozenset[M.Lane],
    audited: frozenset[str],
    verify: Verifier,
    ledger: Sequence[Mapping[str, Any]],
) -> list[Row4] | W.Refusal:
    site_id = site.site_id
    held = batch.site_holds(site_id, M.HoldScope.SITE)
    if held:
        return W.Refusal(site_id, "description", RULE_HELD, _hold_detail(held))
    assignment = batch.lanes[site_id]
    lane = assignment.lane
    assembly = batch.assemblies[site_id]
    if assembly.provenance.lane is not lane:
        raise PlanInputError(
            f"{batch.batch_id}: {site_id} is assigned lane {lane.value} and assembled in lane "
            f"{assembly.provenance.lane.value} - a site never changes lane"
        )
    if lane not in open_lanes:
        return W.Refusal(
            site_id,
            "description",
            RULE_LANE_CLOSED,
            f"lane {lane.value} has not passed its pilot (open: {sorted(m.value for m in open_lanes)})",
        )
    if lane in (M.Lane.T, M.Lane.R) and site_id not in audited:
        return W.Refusal(
            site_id,
            "description",
            RULE_NOT_AUDITED,
            f"lane {lane.value} is written only after the independent audit found 0 UNSUPPORTED",
        )
    card_held = batch.site_holds(site_id, M.HoldScope.CARD)
    if card_held:
        assembly = without_card(assembly)

    source_ids = [source.id for source in assembly.provenance.sources]
    metas, texts = source_files(batch.evidence, site_id, source_ids)
    quotes = [texts[s.src][s.start : s.end] for s in assembly.provenance.sentences]
    raw = new_raw_data(site.raw_data, assembly)
    found = verify(
        site,
        assembly,
        metas=metas,
        texts=texts,
        quotes=quotes,
        new_raw_data=raw,
        witness=witness_files(batch.evidence, site_id),
    )
    if found:
        return W.Refusal(site_id, "description", RULE_VERIFY, _hold_detail(found))

    files = model_files(batch.root, site_id)
    labels = ledger_labels(ledger, batch_id=batch.batch_id, site_id=site_id)
    missing = evidence_problems(files, labels, lane=lane)
    if missing:
        return W.Refusal(site_id, "description", RULE_EVIDENCE, "; ".join(missing))
    if assembly.description == site.description:
        return W.Refusal(
            site_id, "description", RULE_NOT_A_CHANGE, "the assembled text is the stored one"
        )

    evidence = journal_evidence(
        assembly,
        texts=texts,
        subject_gate=subject_verdicts(metas),
        lane_detail=assignment.detail,
        files=files,
        reviews=reviewer_lines(batch.root, site_id),
        labels=labels,
    )
    if card_held:
        evidence["card_holds"] = _holds_json(card_held)
    return [
        make_row(
            group=Group.P4,
            site=site,
            column="description",
            old_value=site.description,
            new_value=assembly.description,
            test_id=TEST_DESCRIPTION,
            evidence=evidence,
        ),
        make_row(
            group=Group.P4,
            site=site,
            column="raw_data",
            old_value=None if site.raw_data is None else raw_json(site.raw_data),
            new_value=raw_json(raw),
            test_id=TEST_RAW_DATA,
            evidence=evidence,
        ),
    ]


def plan_legacy(batch: BatchInputs, *, written: Iterable[str]) -> WritePlan4:
    """L: the legacy provenance of the batch's held sites (`legacy4`), once the held set is final.

    `written` are the sites whose full provenance is live in production. There is no scope: lane L
    marks every March-AI text Phase 4 did not write, inside the owner's defect scope or not (owner
    decision 2026-09-24). A held site with no claim is listed in `unclaimed` (for HUMAN_ONLY) and
    refused; a site whose `raw_data` already carries a provenance is refused rather than
    overwritten.
    """
    plan = WritePlan4(group=Group.L, batch_id=group_batch_id(batch.batch_id, Group.L))
    live = set(written)
    for site in batch.sites:
        if site.site_id in live:
            plan.refusals.append(
                W.Refusal(site.site_id, "raw_data", RULE_WRITTEN, "Phase 4 wrote this description")
            )
    held = legacy4.held_sites(batch.sites, written=live)
    plan.unclaimed.extend(legacy4.unclaimed(held))
    for site in held:
        legacy = legacy4.legacy_provenance(site)
        if legacy is None:
            plan.refusals.append(
                W.Refusal(
                    site.site_id,
                    "raw_data",
                    RULE_NO_CLAIM,
                    f"{legacy4.no_claim_reason(site)}: listed for HUMAN_ONLY",
                )
            )
            continue
        if site.raw_data is not None and M.PROVENANCE_KEY in site.raw_data:
            plan.refusals.append(
                W.Refusal(
                    site.site_id,
                    "raw_data",
                    RULE_MARKED,
                    "raw_data already carries _description_provenance; it is never overwritten",
                )
            )
            continue
        evidence = {
            "group": Group.L.value,
            "basis": M.LEGACY_BASIS,
            "snapshot": legacy4.SNAPSHOT,
            "description_sha256": legacy.desc_sha256,
            "snapshot_description_sha256": (
                None
                if site.snapshot_description is None
                else M.text_sha256(site.snapshot_description)
            ),
            "holds": _holds_json(batch.holds.get(site.site_id, ())),
        }
        plan.rows.append(
            make_row(
                group=Group.L,
                site=site,
                column="raw_data",
                old_value=None if site.raw_data is None else raw_json(site.raw_data),
                new_value=raw_json(legacy_raw_data(site.raw_data, legacy)),
                test_id=TEST_LEGACY,
                evidence=evidence,
            )
        )
    validate_rows(Group.L, plan.rows)
    return plan


def _wc_part(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """The keys of `raw_data` a WC write owns (`wc4.WC_KEYS`)."""
    return {key: value for key, value in (raw or {}).items() if key in wc4.WC_KEYS}


def plan_wc(
    batch: BatchInputs,
    *,
    outcomes: WcOutcomes,
    live: Mapping[str, Mapping[str, Any]],
) -> WritePlan4:
    """WC: the rows of each checked site of the batch (owner decision O5, 2026-09-26).

    `outcomes` are every named WC plan's, by plan batch in plan order (`load_wc_plan`); `live` is
    production's description and raw_data of each planned site (`write_gate4`, read-only, at the
    gate). Per site, in this order:

    * a live full Phase-4 provenance: refused (`written-by-p4`);
    * written by this batch - the live description is the outcome's and so are WC's own three
      `raw_data` keys (`wc4.WC_KEYS`; a later lane may have stamped others: lane WB's
      `_card_provenance`, the review of 2026-09-26): its rows, so a written batch re-plans to the
      rows it was written from, as lane L's does from its plan file;
    * named by a later WC plan's batch: refused (`asked-again-later`) - that plan's answer to the
      text now served is the one planned; a site the batch wrote and `revert4 --site` took back
      then leaves the re-plan on the reversal proof the gate asks for (`sites_taken_back`);
    * the pair it was checked with, whole (the transaction holds the old values): its rows;
    * anything else, and no row at all: refused (`moved-since-check`) - the check answers a text
      that is not served.

    No scope: the population is every curated March text that stays (`wc/cli.py`). The rows write
    the outcome's pair: the description (NULL for a clear) and raw_data - raw_data alone when the
    kept text is the stored one byte for byte, the description alone for the clear of a NULL
    raw_data.
    """
    plan = WritePlan4(group=Group.WC, batch_id=group_batch_id(batch.batch_id, Group.WC))
    full = {lane.value for lane in M.LANE_CHANGES}
    order = list(outcomes)
    later = {
        site_id
        for batch_id in order[order.index(batch.batch_id) + 1 :]
        for site_id in outcomes[batch_id]
    }
    for site in batch.sites:
        outcome = outcomes[batch.batch_id].get(site.site_id)
        if outcome is None or outcome.evidence["checked"] != site.description:
            raise PlanInputError(
                f"{batch.batch_id}: {site.site_id} has no outcome for the text it was checked with"
            )
        now = live.get(site.site_id)
        lane = ((now or {}).get("raw_data") or {}).get(M.PROVENANCE_KEY, {}).get("lane")
        if lane in full:
            plan.refusals.append(
                W.Refusal(site.site_id, "description", RULE_WRITTEN, "Phase 4 wrote this text")
            )
            continue
        written = (
            now is not None
            and now["description"] == outcome.description
            and _wc_part(now["raw_data"]) == _wc_part(outcome.raw_data)
        )
        if not written and site.site_id in later:
            plan.refusals.append(
                W.Refusal(
                    site.site_id,
                    "description",
                    RULE_TAKEN_OVER,
                    "a later WC plan asks this site again; its answer is the one planned",
                )
            )
            continue
        checked = now is not None and (now["description"], now["raw_data"]) == (
            site.description,
            site.raw_data,
        )
        if not (written or checked):
            plan.refusals.append(
                W.Refusal(
                    site.site_id,
                    "description",
                    RULE_MOVED,
                    "production no longer holds the description and raw_data it was checked with",
                )
            )
            continue
        cleared = outcome.description is None
        if not cleared and outcome.description == site.description:
            if outcome.raw_data == site.raw_data:
                plan.refusals.append(
                    W.Refusal(site.site_id, "raw_data", RULE_NOT_A_CHANGE, "nothing moves")
                )
                continue
        else:
            plan.rows.append(
                make_row(
                    group=Group.WC,
                    site=site,
                    column="description",
                    old_value=site.description,
                    new_value=outcome.description,
                    test_id=TEST_WC_DESCRIPTION_CLEAR if cleared else TEST_WC_DESCRIPTION,
                    evidence=outcome.evidence,
                )
            )
        if cleared and site.raw_data is None and outcome.raw_data is None:
            continue  # NULL stays NULL: the clear is the description row alone (WC_PAIRS)
        plan.rows.append(
            make_row(
                group=Group.WC,
                site=site,
                column="raw_data",
                old_value=None if site.raw_data is None else raw_json(site.raw_data),
                new_value=None if outcome.raw_data is None else raw_json(outcome.raw_data),
                test_id=TEST_WC_RAW_DATA_CLEAR if cleared else TEST_WC_RAW_DATA,
                evidence=outcome.evidence,
            )
        )
    validate_rows(Group.WC, plan.rows)
    return plan


def card_to_write(
    batch: BatchInputs, site: M.PlanSite, *, written: Mapping[str, str | None]
) -> M.Assembly | None:
    """The assembly whose card P5 writes for this site, or `None` when its card stays held.

    A card is written only for a site with an assembled card, no site or card hold, and a live P4
    provenance that names exactly this card (`written`: site id -> the live provenance's
    `card.text_sha256`, `None` when it was written without a card). Everything else keeps its old
    card - the design's "held card".
    """
    assembly = batch.assemblies.get(site.site_id)
    if assembly is None or assembly.card is None or assembly.provenance.card is None:
        return None
    if batch.site_holds(site.site_id, M.HoldScope.SITE) or batch.site_holds(
        site.site_id, M.HoldScope.CARD
    ):
        return None
    if site.site_id not in written or written[site.site_id] != M.text_sha256(assembly.card):
        return None
    return assembly


def plan_cards(
    batch: BatchInputs,
    *,
    scope: S.DefectScope,
    written: Mapping[str, str | None],
    card_findings: Mapping[str, Sequence[Mapping[str, Any]]],
    card_rows: Container[str],
) -> WritePlan4:
    """P5: the cards of written sites, and the clears of held cards with a cleared defect.

    `card_findings` are the Phase-3 reviewer-cleared card defects (the 709) by site: the evidence
    of a clear (card_texts, HELD CARDS: "known-wrong narration becomes absent"). A site outside the
    defect scope is refused first: no card and no clear. `card_rows` are the sites production holds
    a card_stats row for; any other site is refused next (audit 2026-09-25 m21), so it no longer
    blocks its whole batch at the chunk's preflight.
    """
    plan = WritePlan4(group=Group.P5, batch_id=group_batch_id(batch.batch_id, Group.P5))
    for site in batch.sites:
        assembly = card_to_write(batch, site, written=written)
        outside = outside_scope(scope, site.site_id, "card_description")
        decided: Row4 | W.Refusal
        if outside is not None:
            decided = outside
        elif site.site_id not in card_rows:
            decided = W.Refusal(
                site.site_id,
                "card_description",
                RULE_NO_CARD_ROW,
                "production holds no card_stats row for the site: no card and no clear",
            )
        elif assembly is not None:
            decided = _card_row(batch, site, assembly)
        elif written.get(site.site_id) is not None:
            decided = W.Refusal(
                site.site_id,
                "card_description",
                RULE_CARD_NAMED,
                f"the live provenance names card sha256 {written[site.site_id]}, which P5 does not "
                "write (a site or card hold, or another assembled card): revert the site first",
            )
        elif M.SiteFlag.CLEARED_CARD_DEFECT in site.flags and site.card is not None:
            decided = _clear_row(batch, site, card_findings)
        else:
            decided = W.Refusal(
                site.site_id,
                "card_description",
                RULE_NO_CARD,
                "the card stays held: no assembled card, a site or card hold, or no live P4 "
                "provenance naming this card; the old card carries no cleared defect",
            )
        if isinstance(decided, W.Refusal):
            plan.refusals.append(decided)
        else:
            plan.rows.append(decided)
    validate_rows(Group.P5, plan.rows)
    return plan


def _clear_row(
    batch: BatchInputs, site: M.PlanSite, card_findings: Mapping[str, Sequence[Mapping[str, Any]]]
) -> Row4:
    findings = card_findings.get(site.site_id)
    if not findings:
        raise PlanInputError(
            f"{batch.batch_id}: {site.site_id} is flagged cleared-card-defect and no Phase-3 "
            "finding is given for it - a clear without its evidence is not written"
        )
    return make_row(
        group=Group.P5,
        site=site,
        column="card_description",
        old_value=site.card,
        new_value=None,
        test_id=TEST_CARD_CLEAR,
        evidence={
            "group": Group.P5.value,
            "clear": "the held card carries a Phase-3 reviewer-cleared defect",
            "phase3_findings": [dict(finding) for finding in findings],
            "holds": _holds_json(batch.holds.get(site.site_id, ())),
        },
    )


def _card_row(batch: BatchInputs, site: M.PlanSite, assembly: M.Assembly) -> Row4 | W.Refusal:
    card, provenance = assembly.card, assembly.provenance
    if card is None or provenance.card is None:
        raise PlanInputError(f"{site.site_id}: card_to_write returned an assembly without a card")
    if card == site.card:
        return W.Refusal(site.site_id, "card_description", RULE_NOT_A_CHANGE, "the card is stored")
    if len(card) > CARD_MAX_CHARS:
        return W.Refusal(
            site.site_id,
            "card_description",
            RULE_CARD_TOO_LONG,
            f"{len(card)} characters; card_stats.card_description holds {CARD_MAX_CHARS}",
        )
    _, texts = source_files(batch.evidence, site.site_id, [s.id for s in provenance.sources])
    cut = [provenance.sentences[item.sentence] for item in provenance.card.items]
    return make_row(
        group=Group.P5,
        site=site,
        column="card_description",
        old_value=site.card,
        new_value=card,
        test_id=TEST_CARD,
        evidence={
            "group": Group.P5.value,
            "lane": provenance.lane.value,
            "run": provenance.run,
            "card_text_sha256": M.text_sha256(card),
            "card": provenance.card.to_dict(),
            "quotes": [texts[s.src][s.start : s.end] for s in cut],
            "desc_sha256": provenance.desc_sha256,
        },
    )


def plan_writes(batch: BatchInputs, *, group: Group, **inputs: Any) -> WritePlan4:
    """The write plan of one row group for one plan batch (`docs/procedures/PHASE4_CONTRACTS.md`
    section 5): `plan_p4`, `plan_legacy` or `plan_cards`, called with that planner's own keyword
    inputs - a missing or foreign input is a `TypeError`, never a default. P4 and P5 take the
    owner's defect `scope` (`phase4/scope4.py`); L takes none (owner decision 2026-09-24), and
    neither does WC (`plan_wc`: the checked outcomes and production's live pair)."""
    planners: Mapping[Group, Callable[..., WritePlan4]] = {
        Group.P4: plan_p4,
        Group.L: plan_legacy,
        Group.P5: plan_cards,
        Group.WC: plan_wc,
    }
    return planners[group](batch, **inputs)


# ------------------------------------------------------------------------------------------------
# Chunks
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk4:
    """One write batch as one chunk: its rows, their digest, and the stamp that names them."""

    group: Group
    batch_id: str
    write_round: int  #: 1-based: the write round of this batch (a batch is one chunk)
    rows: tuple[Row4, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.write_round, int)
            or isinstance(self.write_round, bool)
            or self.write_round < 1
        ):
            raise W.WriteRefused(f"round {self.write_round!r} is not a 1-based write round")
        prefix = f"{GROUP_PREFIX[self.group]}-"
        if not self.batch_id.startswith(prefix) or not self.batch_id[len(prefix) :].isdigit():
            raise W.WriteRefused(f"{self.batch_id!r} is not a {self.group.value} write batch id")
        if len(self.site_ids) > CHUNK_SITES:
            raise W.WriteRefused(f"{len(self.site_ids)} sites in one chunk; the step is 100")
        if len(self.rows) > MAX_CHUNK_ROWS[self.group]:
            raise W.WriteRefused(
                f"{len(self.rows)} rows in one {self.group.value} chunk; at most "
                f"{MAX_CHUNK_ROWS[self.group]}"
            )

    @property
    def label(self) -> str:
        return f"chunk-{self.write_round:04d}"

    @property
    def stamp(self) -> str:
        """`phase4:p4-NNNN:chunk-NNNN`, `phase4l:p4l-...`, `phase5:p5-...` (production_write)."""
        return f"{GROUP_FAMILY[self.group]}:{self.batch_id}:{self.label}"

    @property
    def rollback_stamp(self) -> str:
        return self.stamp + W.ROLLBACK_KEY_SUFFIX

    @property
    def digest(self) -> str:
        return W.plan_digest(self.rows)  # type: ignore[arg-type]  # duck-typed: to_json_line

    @property
    def site_ids(self) -> tuple[str, ...]:
        return tuple(sorted({row.site_id for row in self.rows}))


def chunk_for(plan: WritePlan4, *, write_round: int = 1) -> Chunk4 | None:
    """The plan as its one chunk, or `None` for a plan with no rows (nothing to write is never a
    chunk that wrote nothing)."""
    if not plan.rows:
        return None
    return Chunk4(
        group=plan.group, batch_id=plan.batch_id, write_round=write_round, rows=tuple(plan.rows)
    )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------

_JOINS = (
    f"      FROM {PLAN_TABLE} p",
    "      LEFT JOIN unified_sites u ON u.id = p.site_id",
    "      LEFT JOIN card_stats c ON c.site_id = p.site_id",
)


def only_for(condition: str, test: str) -> str:
    """`test`, evaluated only where `condition` holds (`false` elsewhere).

    A `CASE`, not `condition AND test`: PostgreSQL does not promise to evaluate the operands of
    AND/OR in order, and `p.old_value::jsonb` on a description row's text would abort the whole
    statement. `CASE` is the evaluation order the manual guarantees.
    """
    return f"CASE WHEN {condition} THEN {test} ELSE false END"


def _value_comparisons(planned: str) -> list[str]:
    """One `OR ...` per target, comparing the stored value against `planned` in its own type.

    One helper for guard 4 (`p.old_value`) and the first invariant (`p.new_value`), so the two can
    never ask the question differently.
    """
    return [
        "        OR "
        + only_for(
            f"p.table_name = {W._sql_text(target.table)} AND p.column_name = "
            f"{W._sql_text(target.column)}",
            target.compare.format(planned=planned),
        )
        for target in TARGETS.values()
    ]


def _plan_table_ddl() -> list[str]:
    return [
        f"CREATE TEMP TABLE {PLAN_TABLE} (",
        "    site_id     UUID NOT NULL,",
        "    table_name  TEXT NOT NULL,",
        "    column_name TEXT NOT NULL,",
        "    pk_column   TEXT NOT NULL,",
        "    pk          TEXT NOT NULL,",
        "    old_value   TEXT,",
        "    new_value   TEXT,",
        "    change_key  TEXT NOT NULL,",
        "    test_id     TEXT NOT NULL,",
        "    evidence    JSONB NOT NULL,",
        "    -- one row per (table, column, site): two would be two writes of one transition",
        "    PRIMARY KEY (table_name, column_name, site_id)",
        ") ON COMMIT DROP;",
    ]


def _insert_values(rows: Sequence[Row4], *, reversal: bool) -> list[str]:
    """The plan's rows as one INSERT, in plan order. `reversal` swaps the values and suffixes the
    change key: the undo of a transition is another transition, with its own identity."""
    lines = [
        f"INSERT INTO {PLAN_TABLE} (site_id, table_name, column_name, pk_column, pk, old_value,",
        "                          new_value, change_key, test_id, evidence) VALUES",
    ]
    body = []
    for row in rows:
        key = row.change_key + (W.ROLLBACK_KEY_SUFFIX if reversal else "")
        old, new = (row.new_value, row.old_value) if reversal else (row.old_value, row.new_value)
        body.append(
            "    ("
            + ", ".join(
                [
                    f"{W._sql_text(row.site_id)}::uuid",
                    W._sql_text(row.table),
                    W._sql_text(row.column),
                    W._sql_text(row.pk_column),
                    W._sql_text(row.pk),
                    W._sql_text(old),
                    W._sql_text(new),
                    W._sql_text(key),
                    W._sql_text(row.test_id),
                    f"{W._sql_text(json.dumps(row.evidence, ensure_ascii=False, sort_keys=True))}::jsonb",
                ]
            )
            + ")"
        )
    lines.append(",\n".join(body) + ";")
    return lines


def _header(chunk: Chunk4, *, what: str) -> list[str]:
    return [
        f"-- Generated by {GENERATOR} - do not edit by hand.",
        f"{W.DIGEST_HEADER}{chunk.digest}",
        f"-- {chunk.group.value} write batch {chunk.batch_id}, {chunk.label}: the {what} of "
        f"{len(chunk.rows)} row(s) over {len(chunk.site_ids)} site(s); scope source_id = "
        f"'{W.CURATED_SOURCE}'.",
        f"-- run stamp '{chunk.stamp}'; every row's old value is in its own conditional WHERE.",
        "-- Each row goes through apply_remediation_change(table, column, pk_col, pk, old, new,",
        "-- test_id, run_stamp, change_key, confidence, evidence, site_id): migrations 0018/0022.",
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
    ]


def _raise_if(message: str, *args: str) -> list[str]:
    extra = "".join(f", {arg}" for arg in args)
    return [
        "    IF bad > 0 THEN",
        f"        RAISE EXCEPTION '{message}', bad{extra};",
        "    END IF;",
    ]


def _allowed_tuples(group: Group) -> str:
    tuples = []
    for column, test_id in sorted(GROUP_ROWS[group]):
        target = TARGETS[column]
        tuples.append(
            "("
            + ", ".join(
                W._sql_text(value)
                for value in (target.table, target.column, target.pk_column, test_id)
            )
            + ")"
        )
    return ", ".join(tuples)


def _null_tests_sql(group: Group) -> str:
    """Guard 3's test of a NULL new value: true for a row whose test id may not write NULL. One test
    id is `p.test_id <> '...'` - the text P4, L and P5 have always rendered - and WC's two clear
    tests are a `NOT IN` list."""
    tests = sorted(NULL_TESTS[group])
    if len(tests) == 1:
        return f"p.test_id <> {W._sql_text(tests[0])}"
    return f"p.test_id NOT IN ({', '.join(W._sql_text(test) for test in tests)})"


def _wc_invariants(label: str) -> list[str]:
    """WC's in-database invariants, in place of invariant 3 (a checked text that was unmarked
    carries no provenance, so invariant 3's premise does not hold for it): the check record hashes
    the description it describes, and lane L's provenance, where present, is lane L's and hashes it
    too; a cleared description (NULL) leaves none of the three WC keys in raw_data. NULL on both
    sides of `IS DISTINCT FROM` is a cleared site's, and not distinct."""
    keys = ", ".join(W._sql_text(key) for key in sorted(wc4.WC_KEYS))
    digest = "encode(sha256(convert_to(u.description, 'UTF8')), 'hex')"
    return [
        "    -- invariant 5 (WC): the check record's desc_sha256 is the sha256 of the description",
        "    SELECT count(*) INTO bad",
        f"      FROM {PLAN_TABLE} p JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE p.column_name = 'raw_data'",
        f"       AND (u.raw_data -> {W._sql_text(wc4.CHECK_KEY)} ->> 'desc_sha256')",
        f"           IS DISTINCT FROM {digest};",
        *_raise_if(f"{label}: % site(s) break the check record sha256 invariant"),
        "",
        "    -- invariant 6 (WC): a provenance beside a checked text is lane L's and hashes it; a",
        "    -- cleared description leaves none of the WC keys in raw_data.",
        "    SELECT count(*) INTO bad",
        f"      FROM {PLAN_TABLE} p JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE p.column_name = 'raw_data' AND (",
        "           (u.raw_data ? '_description_provenance' AND (",
        "               (u.raw_data -> '_description_provenance' ->> 'lane') IS DISTINCT FROM 'L'",
        "               OR (u.raw_data -> '_description_provenance' ->> 'desc_sha256')",
        f"                  IS DISTINCT FROM {digest}))",
        f"        OR (u.description IS NULL AND u.raw_data ?| ARRAY[{keys}]));",
        *_raise_if(f"{label}: % site(s) break the provenance or clear invariant"),
    ]


def render_apply(chunk: Chunk4, *, rehearse: bool = False) -> str:
    """One transaction that writes the chunk and journals every row, or writes nothing.

    `rehearse=True` renders the same statement ending in `ROLLBACK`: the rehearsal is proven against
    the live rows with the very guards, loop and invariants the write will run.
    """
    if not chunk.rows:
        raise W.WriteRefused("refusing to render a transaction with no rows")
    validate_rows(chunk.group, chunk.rows)
    label = f"{chunk.group.value.lower()} write"
    out = _header(chunk, what="rehearsal (ends in ROLLBACK)" if rehearse else "write")
    add = out.append
    add("")
    out.extend(_plan_table_ddl())
    add("")
    out.extend(_insert_values(chunk.rows, reversal=False))
    add("")
    add("DO $$")
    add("DECLARE")
    add("    bad        INTEGER;")
    add("    moved      INTEGER := 0;")
    add(f"    expected   INTEGER := {len(chunk.rows)};")
    add("    journalled INTEGER;")
    add("    r          RECORD;")
    add("BEGIN")
    add("    -- guard 1: every planned site is an existing curated site, and a card row has its")
    add("    -- card_stats row (apply_remediation_change only UPDATEs; a missing row matches 0).")
    add("    SELECT count(*) INTO bad")
    out.extend(_JOINS)
    add(f"     WHERE u.id IS NULL OR u.source_id <> {W._sql_text(W.CURATED_SOURCE)}")
    add("        OR (p.table_name = 'card_stats' AND c.site_id IS NULL);")
    out.extend(
        _raise_if(
            f"{label}: % planned row(s) are not rows of % sites", W._sql_text(W.CURATED_SOURCE)
        )
    )
    add("")
    add(
        "    -- guard 2: table, column, key column and test_id are this group's allow-list, and the"
    )
    add("    -- key is the site itself.")
    add(f"    SELECT count(*) INTO bad FROM {PLAN_TABLE} p")
    add(
        "     WHERE (p.table_name, p.column_name, p.pk_column, p.test_id) NOT IN "
        f"(VALUES {_allowed_tuples(chunk.group)})"
    )
    add("        OR p.pk <> p.site_id::text;")
    out.extend(_raise_if(f"{label}: % planned row(s) are outside the allow-list"))
    add("")
    add(
        "    -- guard 3: every row is a real change, in the column's own type: raw_data compares as"
    )
    add("    -- jsonb, so a re-serialisation of the same object is refused as the no-op it is.")
    add(f"    SELECT count(*) INTO bad FROM {PLAN_TABLE} p")
    add("     WHERE p.new_value IS NOT DISTINCT FROM p.old_value OR p.new_value = ''")
    add(f"        OR (p.new_value IS NULL AND {_null_tests_sql(chunk.group)})")
    add(
        "        OR "
        + only_for(
            "p.column_name = 'raw_data'",
            "p.new_value::jsonb IS NOT DISTINCT FROM p.old_value::jsonb",
        )
        + ";"
    )
    out.extend(_raise_if(f"{label}: % planned row(s) are not real changes"))
    add("")
    add(
        "    -- guard 4: every row still holds the old value the plan names (IS DISTINCT FROM in the"
    )
    add("    -- column's type; unlike `=`, it is true for a NULL old value).")
    add("    SELECT count(*) INTO bad")
    out.extend(_JOINS)
    add("     WHERE 1 = 0")
    out.extend(_value_comparisons("p.old_value"))
    add("       ;")
    out.extend(_raise_if(f"{label}: % planned row(s) no longer hold the planned old value"))
    add("")
    add("    -- the only writer: the conditional UPDATE and its journal row commit together")
    add(f"    FOR r IN SELECT * FROM {PLAN_TABLE} ORDER BY site_id, table_name, column_name LOOP")
    add("        moved := moved + apply_remediation_change(")
    add("            r.table_name, r.column_name, r.pk_column, r.pk, r.old_value, r.new_value,")
    add(f"            r.test_id, {W._sql_text(chunk.stamp)}, r.change_key,")
    add(f"            {W._sql_text(W.CONFIDENCE)}, r.evidence, r.site_id);")
    add("    END LOOP;")
    add("    IF moved <> expected THEN")
    add(f"        RAISE EXCEPTION '{label}: % row(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    add("    -- invariant 1: every planned row now holds the new value")
    add("    SELECT count(*) INTO bad")
    out.extend(_JOINS)
    add("     WHERE 1 = 0")
    out.extend(_value_comparisons("p.new_value"))
    add("       ;")
    out.extend(_raise_if(f"{label}: % planned row(s) do not hold the new value"))
    add("")
    add("    -- invariant 2: the journal and the plan agree row for row, in both directions")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {PLAN_TABLE} p LEFT JOIN remediation_change_log l")
    add(f"        ON l.change_key = p.change_key AND l.run_stamp = {W._sql_text(chunk.stamp)}")
    add("     WHERE l.id IS NULL")
    add("        OR l.table_name IS DISTINCT FROM p.table_name")
    add("        OR l.column_name IS DISTINCT FROM p.column_name")
    add("        OR l.row_pk IS DISTINCT FROM p.pk")
    add("        OR l.old_value IS DISTINCT FROM p.old_value")
    add("        OR l.new_value IS DISTINCT FROM p.new_value")
    add("        OR l.test_id IS DISTINCT FROM p.test_id")
    add("        OR l.site_id_ref IS DISTINCT FROM p.site_id;")
    out.extend(_raise_if(f"{label}: % planned row(s) have no matching journal row"))
    add("    SELECT count(*) INTO journalled FROM remediation_change_log l")
    add(f"     WHERE l.run_stamp = {W._sql_text(chunk.stamp)};")
    add("    IF journalled <> expected THEN")
    add(
        f"        RAISE EXCEPTION '{label}: this run stamp journals % row(s), the plan has %', "
        "journalled, expected;"
    )
    add("    END IF;")
    add("")
    if chunk.group is Group.WC:
        out.extend(_wc_invariants(label))
    else:
        add(
            "    -- invariant 3 (P4, L): the provenance's desc_sha256 is the sha256 of the description"
        )
        add("    SELECT count(*) INTO bad")
        add(f"      FROM {PLAN_TABLE} p JOIN unified_sites u ON u.id = p.site_id")
        add("     WHERE p.column_name = 'raw_data'")
        add("       AND (u.raw_data -> '_description_provenance' ->> 'desc_sha256')")
        add("           IS DISTINCT FROM encode(sha256(convert_to(u.description, 'UTF8')), 'hex');")
        out.extend(_raise_if(f"{label}: % site(s) break the description sha256 invariant"))
    add("")
    add("    -- invariant 4 (P5): a written card's sha256 is its provenance's card.text_sha256")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {PLAN_TABLE} p JOIN unified_sites u ON u.id = p.site_id")
    add("      JOIN card_stats c ON c.site_id = p.site_id")
    add("     WHERE p.column_name = 'card_description' AND p.new_value IS NOT NULL")
    add("       AND encode(sha256(convert_to(c.card_description, 'UTF8')), 'hex')")
    add(
        "           IS DISTINCT FROM (u.raw_data -> '_description_provenance' -> 'card' ->> 'text_sha256');"
    )
    out.extend(_raise_if(f"{label}: % card(s) break the card sha256 invariant"))
    add("")
    add(f"    RAISE NOTICE '{label}: % row(s) changed and journalled, % planned', moved, expected;")
    add("END $$;")
    add("")
    add("ROLLBACK;" if rehearse else "COMMIT;")
    add("")
    add(_post_reads(chunk, after="the rehearsal (every count must be 0)" if rehearse else "commit"))
    return "\n".join(out)


def _post_reads(chunk: Chunk4, *, after: str) -> str:
    return (
        f"-- Read after {after}: the numbers the report quotes, from the database.\n"
        "SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value\n"
        f"  FROM remediation_change_log WHERE run_stamp = {W._sql_text(chunk.stamp)}\n"
        "UNION ALL\n"
        "SELECT 'journal rows for the rollback stamp', count(*)::text\n"
        f"  FROM remediation_change_log WHERE run_stamp = {W._sql_text(chunk.rollback_stamp)}\n"
        "UNION ALL\n"
        f"SELECT 'temp table {PLAN_TABLE} left behind',\n"
        f"       (to_regclass('pg_temp.{PLAN_TABLE}') IS NOT NULL)::int::text\n"
    )


def render_rollback(chunk: Chunk4) -> str:
    """The chunk's inverse, proven inside a transaction that is rolled back (Phase 3's shape):
    guards, loop and journal run for real on the written rows, and none of it is kept."""
    if not chunk.rows:
        raise W.WriteRefused("refusing to render the reversal of a chunk with no rows")
    label = f"{chunk.group.value.lower()} rollback"
    out = _header(chunk, what="reversal")
    add = out.append
    add(f"-- this file reverses run stamp '{chunk.stamp}' and is itself rolled back: it proves")
    add("-- the inverse on the real rows and keeps none of it.")
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
    add("    -- guard: every row still holds the value the write left (the reversal's old value)")
    add("    SELECT count(*) INTO bad")
    out.extend(_JOINS)
    add("     WHERE 1 = 0")
    out.extend(_value_comparisons("p.old_value"))
    add("       ;")
    out.extend(_raise_if(f"{label}: % planned row(s) do not hold the written value"))
    add("")
    add(f"    FOR r IN SELECT * FROM {PLAN_TABLE} ORDER BY site_id, table_name, column_name LOOP")
    add("        moved := moved + apply_remediation_change(")
    add("            r.table_name, r.column_name, r.pk_column, r.pk, r.old_value, r.new_value,")
    add(f"            r.test_id, {W._sql_text(chunk.rollback_stamp)}, r.change_key,")
    add(f"            {W._sql_text(W.CONFIDENCE)}, r.evidence, r.site_id);")
    add("    END LOOP;")
    add("    IF moved <> expected THEN")
    add(f"        RAISE EXCEPTION '{label}: % row(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    add("    -- the inverse, asserted inside the transaction: every row is back at the old value")
    add("    SELECT count(*) INTO bad")
    out.extend(_JOINS)
    add("     WHERE 1 = 0")
    out.extend(_value_comparisons("p.new_value"))
    add("       ;")
    out.extend(_raise_if(f"{label}: % row(s) are not back at the old value"))
    add("")
    add("    -- the reversal is journalled row for row, under the rollback stamp")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {PLAN_TABLE} p LEFT JOIN remediation_change_log l")
    add(
        f"        ON l.change_key = p.change_key AND l.run_stamp = {W._sql_text(chunk.rollback_stamp)}"
    )
    add("     WHERE l.id IS NULL")
    add("        OR l.old_value IS DISTINCT FROM p.old_value")
    add("        OR l.new_value IS DISTINCT FROM p.new_value;")
    out.extend(_raise_if(f"{label}: % planned row(s) have no matching journal row"))
    add("")
    add(
        f"    RAISE NOTICE '{label}: % row(s) reversed inside a transaction about to be rolled back',"
    )
    add("        moved;")
    add("END $$;")
    add("")
    add("ROLLBACK;")
    add("")
    add(_post_reads(chunk, after="the ROLLBACK (the rollback stamp must count 0)"))
    return "\n".join(out)


def chunk_dir(out: Path, chunk: Chunk4) -> Path:
    return out / CHUNKS_DIR / chunk.label


def write_plan_files(out: Path, plan: WritePlan4, chunk: Chunk4 | None) -> None:
    """The plan, its refusals, the unclaimed list and the chunk's three statements (the reversal
    first, so a chunk that cannot be undone is visible before anything is written)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / PLAN_FILE).write_text(
        "".join(row.to_json_line() + "\n" for row in plan.rows), encoding="utf-8", newline="\n"
    )
    (out / REFUSED_FILE).write_text(
        "".join(refusal.to_json_line() + "\n" for refusal in plan.refusals),
        encoding="utf-8",
        newline="\n",
    )
    (out / UNCLAIMED_FILE).write_text(
        "".join(
            json.dumps(
                {"site_id": u.site_id, "name": u.name, "reason": u.reason.value},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for u in plan.unclaimed
        ),
        encoding="utf-8",
        newline="\n",
    )
    if chunk is None:
        return
    directory = chunk_dir(out, chunk)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ROLLBACK_FILE).write_text(render_rollback(chunk), encoding="utf-8", newline="\n")
    (directory / REHEARSE_FILE).write_text(
        render_apply(chunk, rehearse=True), encoding="utf-8", newline="\n"
    )
    (directory / APPLY_FILE).write_text(render_apply(chunk), encoding="utf-8", newline="\n")


def read_plan(out: Path, *, group: Group) -> list[Row4]:
    """The rows a write batch was rendered from (`PLAN.jsonl`), validated as its group's."""
    rows = [Row4.from_dict(row) for row in read_jsonl(out / PLAN_FILE)]
    validate_rows(group, rows)
    return rows


#: psql did not answer: whether a COMMIT landed is unknown until the journal is read. The same code
#: as `mechanical.apply.EXIT_UNKNOWN`, so every writer's exit line says it the same way.
EXIT_UNKNOWN = 5


def exit_line(tag: str, run: Callable[[], int]) -> int:
    """Run one tool body and print its own `<TAG>_EXIT=` line - the line that is read, never a
    wrapper's status (design, DRIVER). The streams are UTF-8 first: a console that cannot encode a
    site name once killed a write wave before its first row (`write_stage.utf8_streams`). A
    refusal is printed, not swallowed: the code is the refusal's. A psql timeout is neither a
    success nor a refusal: it is `EXIT_UNKNOWN` (audit 2026-09-25 M3 - it used to escape as a
    traceback with no exit line at all)."""
    W.utf8_streams()
    try:
        code = run()
    except SystemExit as exc:
        if exc.code is None or isinstance(exc.code, int):
            code = exc.code or 0
        else:
            print(exc.code, file=sys.stderr)
            code = 1
    except W.WriteRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        code = 1
    except W.OutcomeUnknown as exc:
        print(f"OUTCOME UNKNOWN: {exc}", file=sys.stderr)
        code = EXIT_UNKNOWN
    print(f"{tag}_EXIT={code}", flush=True)
    return code


# ------------------------------------------------------------------------------------------------
# Reads and the per-chunk run
# ------------------------------------------------------------------------------------------------

STORED_READ = "-- the values each named site holds now"


def stored_values_sql(site_ids: Sequence[str]) -> str:
    """Description, raw_data and card of each named site, one JSON object per site."""
    ids = ", ".join(f"{W._sql_text(site_id)}::uuid" for site_id in site_ids)
    return (
        f"{STORED_READ}, one JSON object per site\n"
        "\\pset footer off\n"
        "SELECT to_jsonb(t)::text FROM (\n"
        "  SELECT u.id::text AS id, u.source_id, u.description, u.raw_data,\n"
        "         c.site_id IS NOT NULL AS card_row, c.card_description\n"
        "    FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id\n"
        f"   WHERE u.id IN ({ids})\n"
        ") t ORDER BY 1"
    )


def holds_value(stored: Mapping[str, Any], row: Row4, planned: str | None) -> bool:
    """Does the stored row hold `planned` in the column's own sense? raw_data compares as JSON
    values (jsonb equality: numbers as exact decimals, like guard 4 - audit 2026-09-25 m20), text
    columns byte for byte; `None` is a value of its own."""
    observed = stored.get(row.column)
    if row.column == "raw_data":
        return observed == (None if planned is None else M.parse_json(planned, exact=True))
    return observed == planned


def invariant_problems(stored: Mapping[str, Any], rows: Sequence[Row4]) -> list[str]:
    """The two in-database sha256 invariants, re-checked on what the read returned (a WC site:
    lane WC's own, `wc4.wc_problems`)."""
    problems: list[str] = []
    columns = {row.column for row in rows}
    raw = stored.get("raw_data")
    provenance = raw.get(M.PROVENANCE_KEY) if isinstance(raw, dict) else None
    site = stored.get("id")
    if rows and rows[0].group is Group.WC:
        return [f"{site}: {problem}" for problem in wc4.wc_problems(stored.get("description"), raw)]
    if "raw_data" in columns:
        description = stored.get("description")
        if (
            provenance is None
            or description is None
            or provenance.get("desc_sha256") != M.text_sha256(description)
        ):
            problems.append(f"{site}: desc_sha256 is not the sha256 of the stored description")
    for row in rows:
        if row.column == "card_description" and row.new_value is not None:
            card = stored.get("card_description")
            wanted = (
                None if provenance is None else (provenance.get("card") or {}).get("text_sha256")
            )
            if card is None or wanted != M.text_sha256(card):
                problems.append(f"{site}: the card's sha256 is not provenance card.text_sha256")
    return problems


def _stored(chunk: Chunk4, runner: W.SqlRunner | None, host: str) -> dict[str, dict[str, Any]]:
    """The stored rows by site id, numbers read exactly (`holds_value` compares as jsonb does)."""
    text = W._exec(runner, stored_values_sql(chunk.site_ids), host=host)
    rows = [M.parse_json(line, exact=True) for line in W.jsonl_lines(text) if line.strip()]
    return {str(entry["id"]): entry for entry in rows}


def preflight(
    chunk: Chunk4, *, runner: W.SqlRunner | None = None, host: str = W.SSH_HOST
) -> list[str]:
    """What stands in the way of this chunk, read before anything is sent: a row that no longer
    holds its old value, a site that is not a curated site or has no card row, and a stamp that
    already journals rows (written before, or a round number used twice). Empty = go."""
    stored = _stored(chunk, runner, host)
    problems: list[str] = []
    for row in chunk.rows:
        found = stored.get(row.site_id)
        where = f"{row.site_id}/{row.column}"
        if found is None:
            problems.append(f"{where}: no unified_sites row")
            continue
        if found.get("source_id") != W.CURATED_SOURCE:
            problems.append(f"{where}: source_id is {found.get('source_id')!r}")
            continue
        if row.table == "card_stats" and found.get("card_row") is not True:
            problems.append(f"{where}: no card_stats row")
            continue
        if not holds_value(found, row, row.old_value):
            problems.append(f"{where}: the row no longer holds the planned old value")
    already = W.journal_rows_for_stamp(chunk.stamp, run_sql_runner=runner, host=host)
    if already:
        problems.append(
            f"run stamp {chunk.stamp} already journals {already} row(s): this round of the batch "
            "was written, or its number is used twice"
        )
    return problems


def read_back(
    chunk: Chunk4,
    *,
    expect_new: bool,
    runner: W.SqlRunner | None = None,
    host: str = W.SSH_HOST,
) -> W.ReadBack:
    """Every row compared with its planned value, the journal row for row (this chunk's stamp
    only: a later write round journals the same change keys), the stamp's count, and (after a
    write) the two sha256 invariants. `expect_new=False` is the rehearsal's check: every row still
    old and the stamp without a single journal row."""
    stored = _stored(chunk, runner, host)
    mismatches: list[str] = []
    held = 0
    for row in chunk.rows:
        found = stored.get(row.site_id)
        planned = row.new_value if expect_new else row.old_value
        if found is None or not holds_value(found, row, planned):
            mismatches.append(f"{row.site_id}/{row.column}: does not hold the planned value")
            continue
        held += 1
    total = W.journal_rows_for_stamp(chunk.stamp, run_sql_runner=runner, host=host)
    if not expect_new:
        if total:
            mismatches.append(f"the rehearsal left {total} journal row(s) for {chunk.stamp}")
        return W.ReadBack(
            checked=len(chunk.rows), held=held, journal_rows=total, mismatches=tuple(mismatches)
        )
    mismatches.extend(
        W.journal_mismatches(
            chunk.rows,  # type: ignore[arg-type]  # duck-typed: the WriteRow fields it reads
            run_stamp=chunk.stamp,
            run_sql_runner=runner,
            host=host,
        )
    )
    if total != len(chunk.rows):
        mismatches.append(
            f"run stamp {chunk.stamp} has {total} journal row(s), the plan {len(chunk.rows)}"
        )
    by_site: dict[str, list[Row4]] = {}
    for row in chunk.rows:
        by_site.setdefault(row.site_id, []).append(row)
    for site_id, rows in by_site.items():
        if site_id in stored:
            mismatches.extend(invariant_problems(stored[site_id], rows))
    return W.ReadBack(
        checked=len(chunk.rows), held=held, journal_rows=total, mismatches=tuple(mismatches)
    )


@dataclass
class ChunkOutcome4:
    chunk: Chunk4
    rehearsed: bool
    written: int
    blocked: tuple[str, ...] = ()
    read_back: W.ReadBack | None = None
    inverse: W.ReadBack | None = None
    rollback_rows: int | None = None

    @property
    def ok(self) -> bool:
        return not self.blocked

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.chunk.group.value,
            "batch_id": self.chunk.batch_id,
            "chunk": self.chunk.label,
            "write_round": self.chunk.write_round,
            "run_stamp": self.chunk.stamp,
            "digest": self.chunk.digest,
            "rows_planned": len(self.chunk.rows),
            "sites": len(self.chunk.site_ids),
            "rehearsed": self.rehearsed,
            "rows_written": self.written,
            "blocked": list(self.blocked),
            "read_back": None if self.read_back is None else self.read_back.describe(),
            "inverse": None if self.inverse is None else self.inverse.describe(),
            "rollback_rows_left": self.rollback_rows,
        }


def apply_chunk(
    chunk: Chunk4,
    *,
    out: Path,
    rehearse: bool,
    runner: W.SqlRunner | None = None,
    host: str = W.SSH_HOST,
) -> ChunkOutcome4:
    """Preflight, then the rehearsal or the write with its read-back and inverse proof.

    The three statements are read from `chunks/<label>/` and each must be pinned to exactly these
    rows. Nothing is sent when the preflight finds anything: the statement was generated from the
    chunk as a whole. A read-back or inverse that disagrees raises, and the caller stops the run.
    """
    directory = chunk_dir(out, chunk)
    statements = {}
    for name in (APPLY_FILE, REHEARSE_FILE, ROLLBACK_FILE):
        path = directory / name
        if not path.exists():
            raise W.WriteRefused(f"{path} does not exist: render the plan before running it")
        statements[name] = path.read_text(encoding="utf-8")
        W.assert_pinned(statements[name], chunk.rows, what=str(path))  # type: ignore[arg-type]
    blocked = preflight(chunk, runner=runner, host=host)
    if blocked:
        return ChunkOutcome4(chunk=chunk, rehearsed=rehearse, written=0, blocked=tuple(blocked))
    if rehearse:
        W._exec(runner, statements[REHEARSE_FILE], host=host)
        back = read_back(chunk, expect_new=False, runner=runner, host=host)
        if not back.ok:
            raise W.ReadBackFailed(f"{chunk.stamp}: the rehearsal left a trace - {back.describe()}")
        return ChunkOutcome4(chunk=chunk, rehearsed=True, written=0, read_back=back)
    W._exec(runner, statements[APPLY_FILE], host=host)
    back = read_back(chunk, expect_new=True, runner=runner, host=host)
    if not back.ok:
        raise W.ReadBackFailed(f"{chunk.stamp}: the read-back disagrees - {back.describe()}")
    W._exec(runner, statements[ROLLBACK_FILE], host=host)
    inverse = read_back(chunk, expect_new=True, runner=runner, host=host)
    if not inverse.ok:
        raise W.InverseFailed(
            f"{chunk.stamp}: the reversal did not leave the write as it was - {inverse.describe()}"
        )
    left = W.journal_rows_for_stamp(chunk.rollback_stamp, run_sql_runner=runner, host=host)
    if left:
        raise W.InverseFailed(f"{chunk.stamp}: {left} reversal journal row(s) survived")
    return ChunkOutcome4(
        chunk=chunk,
        rehearsed=False,
        written=len(chunk.rows),
        read_back=back,
        inverse=inverse,
        rollback_rows=left,
    )
