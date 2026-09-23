"""The Phase-4/5 contracts: the records every stage reads and writes, and their exact JSON form.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json` ("Phases 4 and
5, final design"; sections pipeline, source_store, writer, verification, production_write and
card_texts). Work item WB-00. Which track produces and which consumes each record is in
`docs/procedures/PHASE4_CONTRACTS.md`.

Form, not truth
---------------
A record here refuses what is **malformed**: a missing or unknown key, a wrong type (a `bool` is
never an `int`), a value outside a closed vocabulary, an offset range that is empty, unsorted or
outside its sentence, a reference to a source or sentence that is not there, a lane paired with
the wrong AI mark or change note. It never checks a record against the world. Whether a hash
matches its text, a revision is the latest, a licence suits the lane, a dropped range is an offered
span, the citation numbers run 1..N, the text is long enough - all of that is a rule of the
verifier (V1-V15, `phase4/verify4.py`), which must be able to hold a well-formed record that breaks
it. A V-rule that restates a property this module also checks (V1: "it is an integer") is checked
by the verifier on the raw JSON, so its own mutation test can go red.

Offsets
-------
Every offset is a Python `str` index (a Unicode code point) into the pinned text of its source:
the bytes of `src.<id>.txt` decoded as UTF-8 (NFC, `\\n` line ends). Ranges are half-open
`[start, end)`. A drop range is in the same space as the sentence it cuts, never relative to it.

JSON
----
`to_dict()` is the exact shape: every key is always present, `None` is written as `null`, tuples
as lists, enums as their values. `from_dict()` is its strict inverse and raises `ValueError` on any
difference. `to_json()` is `json.dumps(..., ensure_ascii=False, sort_keys=True)`, the form the
writer uses for `raw_data`; `from_json()` also refuses `NaN` and `Infinity`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Self, TypeVar

from phase3.model import _coerce  # one enum coercion for both phases, not a second spelling
from phase3.model_stage import MODEL  # the model the disclosure names is the model that is called
from phase3.run import read_jsonl

# --------------------------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------------------------


class Lane(StrEnum):
    """Where a site's text comes from. Assigned once (S1b); L exists only in provenance."""

    W = "W"  #: its own English Wikipedia article
    S = "S"  #: a shared or parent English article: only name-bearing sentences
    T = "T"  #: its own article, only in another language (translated)
    R = "R"  #: only non-free pages (facts restated, wording never published)
    ZERO = "0"  #: nothing usable: held as `no-source`
    L = "L"  #: legacy disclosure of held March-LLM text; never an assignment


#: The lanes S1b can assign. L is written only by `phase4/legacy4.py`.
ASSIGNED_LANES = frozenset({Lane.W, Lane.S, Lane.T, Lane.R, Lane.ZERO})


class AiMark(StrEnum):
    """`_description_provenance.ai`, the render key of the disclosure (licensing_and_ai_act)."""

    SELECTED = "selected"  #: verbatim text; the AI chose sentences and deletable spans
    GENERATED = "generated"  #: the AI wrote the words


#: The AI mark is a function of the lane, not a choice per site.
LANE_AI: Mapping[Lane, AiMark] = MappingProxyType(
    {
        Lane.W: AiMark.SELECTED,
        Lane.S: AiMark.SELECTED,
        Lane.T: AiMark.GENERATED,
        Lane.R: AiMark.GENERATED,
        Lane.L: AiMark.GENERATED,
    }
)


class Changes(StrEnum):
    """`attribution.changes`: the CC BY-SA 4.0 section 3(a) change note."""

    SELECTED_AND_SHORTENED = "sentences selected and shortened"
    TRANSLATED = "translated"
    FACTS_RESTATED = "facts restated"


#: The change note is a function of the lane.
LANE_CHANGES: Mapping[Lane, Changes] = MappingProxyType(
    {
        Lane.W: Changes.SELECTED_AND_SHORTENED,
        Lane.S: Changes.SELECTED_AND_SHORTENED,
        Lane.T: Changes.TRANSLATED,
        Lane.R: Changes.FACTS_RESTATED,
    }
)


class Licence(StrEnum):
    """Licence labels. Which host carries which is `phase4/licences.py`'s registry."""

    CC_BY_SA_4 = "CC BY-SA 4.0"  #: every Wikipedia language edition
    CC0 = "CC0"  #: Wikidata; a witness only, never published
    RESTRICTED = "restricted"  #: a non-free page: facts may be restated, wording never published


#: Every published description is CC BY-SA 4.0: W/S/T adapt Wikipedia, and R's restated facts are
#: the curated layer's own text, which is declared CC BY-SA 4.0 (`pipeline/sources/configs.py`).
PUBLISHED_LICENCE = Licence.CC_BY_SA_4
PUBLISHED_LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

#: `_description_provenance.ai_system` for lanes W/S/T/R (production_write).
AI_SYSTEM = f"{MODEL} via Pi (an-sites-remediation-2026-09)"
#: Lane L's `ai_system` and `basis`, verbatim from production_write.
LEGACY_AI_SYSTEM = "2026-03 enrichment chain (LLM; model per site not recorded)"
LEGACY_BASIS = "description differs from pre-March snapshot d4526691 (plan section 15.3)"
PROVENANCE_VERSION = 1

#: The `raw_data` key. The leading underscore is what makes `sourceFields.ts` skip it.
PROVENANCE_KEY = "_description_provenance"
CITATIONS_KEY = "description_citations"


class SourceKind(StrEnum):
    """The four source kinds of the store (source_store LAYOUT)."""

    W = "W"  #: English Wikipedia, `src.W`
    D = "D"  #: Wikidata, `src.D`: a witness, never cited
    T = "T"  #: another-language Wikipedia, `src.T.<lang>`
    R = "R"  #: a non-free page, `src.R<k>`


_SOURCE_ID = re.compile(r"W|D|T\.[a-z]+(?:-[a-z]+)*|R[1-9][0-9]*")
#: The kinds whose text may be published (and therefore cited).
CITABLE_KINDS = frozenset({SourceKind.W, SourceKind.T, SourceKind.R})
#: The kinds the sentence splitter numbers (`W12`, `T.fr3`); R text is quoted, not selected.
SELECTABLE_KINDS = frozenset({SourceKind.W, SourceKind.T})


def source_kind(source_id: str) -> SourceKind:
    """The kind of a store id: `W`, `D`, `T.<lang>` or `R<k>`. Anything else raises."""
    if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
        raise ValueError(f"{source_id!r} is not a source id (W, D, T.<lang>, R<k>)")
    return SourceKind(source_id[0])


def source_feature(source_id: str, part: str) -> str:
    """The `EvidenceStore` feature of one part of a source: `src.W`, `src.W.txt`, `src.W.meta`.

    `part` is `raw` (the fetched bytes), `txt` (the pinned text offsets index into) or `meta` (a
    `SourceDoc`).
    """
    source_kind(source_id)
    suffix = {"raw": "", "txt": ".txt", "meta": ".meta"}
    if part not in suffix:
        raise ValueError(f"{part!r} is not a source part {sorted(suffix)}")
    return f"src.{source_id}{suffix[part]}"


class Route(StrEnum):
    """How a source was reached (S1, S1b), recorded in its meta."""

    ENWIKI_TITLE = "enwiki_title"  #: site_external_ids.enwiki_title
    SOURCE_URL = "source_url"  #: the title of a Wikipedia source_url
    LANGLINKS = "langlinks"  #: from another-language article to English
    GEOSEARCH = "geosearch"  #: list=geosearch within 2 km plus a name match
    MINIMAX = "minimax"  #: a search hit (phase3.search_stage.MiniMaxSearcher)
    PHASE3_EVIDENCE = "phase3-evidence"  #: a Phase-3 wikidata_entity file, reused
    WIKIDATA_NARROW = "wikidata-narrow"  #: refetched through the narrow Wikidata route
    #: refetched through the Phase-3 entity request at the 1 MiB wiki cap (WB-A2, 2026-09-23: the
    #: narrow route carries no P279 and no P625 precision, which the subject gate reads)
    WIKIDATA_ENTITY = "wikidata-entity"


class SubjectVerdict(StrEnum):
    """The subject gate's verdict (S1)."""

    OWN = "own"
    SHARED = "shared"
    WRONG = "wrong"
    NONE = "none"


class SpanKind(StrEnum):
    """The deletable spans S2 offers. A span id is its kind letter plus a number: `a1`."""

    P = "p"  #: a balanced parenthesis
    A = "a"  #: a paired-comma or paired-dash insertion
    L = "l"  #: a leading phrase of at most 6 tokens before the first comma
    T = "t"  #: the last comma segment


_SID = re.compile(r"(?P<src>W|T\.[a-z]+(?:-[a-z]+)*)(?P<index>[1-9][0-9]*)")
_SPAN_ID = re.compile(r"[plat][1-9][0-9]*")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class SiteFlag(StrEnum):
    """What S0 derives per site from data (not from the B block's temp files)."""

    SCOPE_PENDING = "scope-pending"  #: out of the date window or undated: held
    SHARED_QID = "shared-qid"  #: the stored QID is shared with another curated site
    SHARED_TITLE = "shared-title"  #: the stored enwiki title is shared
    DUPLICATE_PAIR = "duplicate-pair"  #: listed for the B duplicate lane; written like any site
    CLEARED_DESCRIPTION_DEFECT = "cleared-description-defect"  #: one of the 322 (waives V9's floor)
    CLEARED_CARD_DEFECT = "cleared-card-defect"  #: one of the 709 (allows P5/card-clear)
    T03 = "t03"  #: in run_t03/findings.jsonl (order only)
    T03_SEVERE = "t03-severe"  #: T03 flagged the stored text as severe (waives V9's floor)


class HoldScope(StrEnum):
    """What a hold keeps unwritten. A held site keeps its card too; a held card only the card."""

    SITE = "site"
    CARD = "card"


class HoldReason(StrEnum):
    """Why a site or card is not written. Closed: a new reason is a contract change (WB-00)."""

    # S0-S1b: plan, sources, subject gate and routes (Track A)
    SCOPE_PENDING = "scope-pending"
    REVISION_TOO_FRESH = "revision-too-fresh"  #: younger than 48 h: deferred to a later batch
    MOVED_DURING_FETCH = "moved-during-fetch"  #: revisions[0].revid != lastrevid
    FETCH_FAILED = "fetch-failed"  #: a recorded fetch failure, a body at the cap included
    SEARCH_STOPPED = "search-stopped"  #: a quota floor or a failed probe stopped its search
    NO_SOURCE = "no-source"  #: lane 0
    # S3, S3T, S3R: model calls (Track B). No retry: a rerun is a new ledgered call.
    MODEL_STREAM_UNREADABLE = "model-stream-unreadable"
    SELECTION_REFUSED = "selection-refused"  #: detail names the SelectionProblem
    ABSTAINED = "abstained"
    TRANSLATION_REFUSED = "translation-refused"
    RESTATEMENT_REFUSED = "restatement-refused"
    # S6: the drop-only review (Track B)
    REVIEW_UNPARSEABLE = "review-unparseable"
    REVIEW_TOO_FEW_SENTENCES = "review-too-few-sentences"
    CARD_TOO_SHORT_AFTER_REVIEW = "card-too-short-after-review"
    # S5: the verifier holds under the rule id (Track C)
    V1 = "V1"
    V2 = "V2"
    V3 = "V3"
    V4 = "V4"
    V5 = "V5"
    V6 = "V6"
    V7 = "V7"
    V8 = "V8"
    V9 = "V9"
    V10 = "V10"
    V11 = "V11"
    V12 = "V12"
    V13 = "V13"
    V14 = "V14"
    V15 = "V15"
    # S6b: the independent audit, and lanes closed by a pilot hit
    AUDIT_UNSUPPORTED = "audit-unsupported"
    AUDIT_WRONG_SITE = "audit-wrong-site"
    AUDIT_NOT_CONTAINED = "audit-not-contained"
    LANE_R_CLOSED = "lane-R-closed"
    LANE_T_CLOSED = "lane-T-closed"


#: Reasons that concern the card alone; they cannot hold the description.
CARD_ONLY_REASONS = frozenset(
    {HoldReason.CARD_TOO_SHORT_AFTER_REVIEW, HoldReason.AUDIT_NOT_CONTAINED}
)


class SelectionProblem(StrEnum):
    """The named refusals of a selector answer (writer, OUTPUT). A refusal HOLDs the site."""

    # raised by phase4/select_stage.parse_selection, which knows the candidate pool
    UNKNOWN_LINE = "unknown-line"
    UNKNOWN_SID = "unknown-sid"
    SPAN_NOT_OFFERED = "span-not-offered"
    # raised by `Selection` itself
    DUPLICATE = "duplicate"
    TOO_MANY_DESC = "too-many-desc"
    TOO_MANY_CARD = "too-many-card"
    CARD_NOT_IN_DESC = "card-not-in-desc"
    NO_DESC = "no-desc"
    NO_CARD = "no-card"
    ABSTAIN_WITH_OTHER_LINES = "abstain-with-other-lines"
    ABSTAIN_WITHOUT_REASON = "abstain-without-reason"


#: The selector contract's bounds: 1-8 DESC lines, 1-2 CARD lines.
MAX_DESC = 8
MAX_CARD = 2

# --------------------------------------------------------------------------------------------
# Shared word lists (data only; each consumer implements its own matcher)
# --------------------------------------------------------------------------------------------

#: V4's protected tokens as the design lists them (verification, V4, amended per judges 1 and 3),
#: by the design's own group names, verbatim. Consumers read `PROTECTED_TOKENS`, which extends it.
DESIGN_PROTECTED_TOKENS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "hedges": (
            "possibly", "probably", "perhaps", "may", "might", "could", "likely", "believed",
            "thought", "suggest*", "claimed", "alleged*", "legend*", "tradition*", "reportedly",
            "according", "circa", "c.", "ca.", "approximately", "about", "around", "estimated",
            "some", "several",
        ),
        "negations": ("not", "no", "never", "neither", "nor", "without"),
        "contrast": (
            "but", "although", "though", "however", "whereas", "while", "yet", "despite",
        ),
        "refutation": (
            "disputed", "debated", "uncertain", "unclear", "rejected", "refuted", "disproved",
            "discredited", "unlikely", "doubtful", "contested", "questioned", "hypothes*",
            "theor*", "speculat*", "attributed",
        ),
        "restriction": (
            "only", "except", "until", "partly", "partially", "formerly", "originally", "mainly",
            "mostly", "largely", "part of", "at least", "at most", "up to", "nearly", "almost",
        ),
    }
)  # fmt: skip

#: The `n't` forms, in both apostrophes the extracts carry (`'` and `’`): `don't` negates like
#: `not`, and `\bnot\b` never matches inside it (nor inside `cannot`).
_NOT_CONTRACTIONS = tuple(
    f"{stem}n{apostrophe}t"
    for stem in (
        "ca", "could", "did", "does", "do", "had", "has", "have", "is", "are", "was", "were",
        "wo", "would", "should", "must", "need", "might", "sha", "ai",
    )
    for apostrophe in ("'", "’")
)  # fmt: skip

#: What the review of WB-B2 added to the design's list (WB-00 contract change, 2026-09-23). The
#: design promises that hedges, negations and restrictions survive by construction (card_texts;
#: pilot T3 stops the run on one lost), and its list let the real pools offer `Presumably, `,
#: `, it seems,`, `, arguably,`, `cannot` and `don't` spans for deletion: 1,037 offered spans over
#: the 3,681 local extracts carried a word below. Every entry uses the entry rules above, so a
#: matcher that implements them (S2's and V4's) reads the additions without a code change.
PROTECTED_TOKEN_ADDITIONS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "hedges": (
            "presum*", "apparent*", "arguabl*", "seem*", "appear*", "suppos*", "reputed*",
            "purported*", "evidently", "assum*", "possible", "probable", "maybe",
        ),
        "negations": ("cannot", *_NOT_CONTRACTIONS),
        "refutation": ("unknown",),
    }
)  # fmt: skip

#: The protected tokens every consumer reads: the design's list, then the additions, per group. A
#: span containing one is never offered for deletion (S2) and a drop containing one fails V4.
#: Meaning of an entry: matched case-insensitively as whole words; a trailing `*` matches any word
#: that starts with the rest (`suggest*`: suggests, suggested, suggestion); an entry with a space
#: is a phrase of consecutive words; `c.` and `ca.` include their full stop.
PROTECTED_TOKENS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        group: entries + PROTECTED_TOKEN_ADDITIONS.get(group, ())
        for group, entries in DESIGN_PROTECTED_TOKENS.items()
    }
)

#: V6's closed pronoun list. A sentence opening with one (as its first word or words, exactly as
#: written here, followed by a non-letter) needs its source predecessor published right before
#: it; a card never opens with one.
PRONOUN_OPENERS: tuple[str, ...] = (
    "It", "Its", "This", "These", "They", "Their", "He", "She", "His", "Her", "The latter",
    "The former", "Here", "There",
)  # fmt: skip

# --------------------------------------------------------------------------------------------
# Run-directory files that cross a track boundary (one record per line, `to_json()`)
# --------------------------------------------------------------------------------------------

INPUT_FILE = "input.json"  #: phase3.run.Batch whose sites are PlanSite dicts (A3 -> all)
EVIDENCE_DIR = "evidence"  #: phase3 fetch_stage.EvidenceStore root (A -> B, C)
FETCH_FAILURES_FILE = "fetch.json"  #: model_stage.read_fetch_failures shape (A)
LANES_FILE = "lanes.jsonl"  #: LaneAssignment, one per site of the batch (A3 -> B)
ASSEMBLY_FILE = "assembly.jsonl"  #: Assembly after review (B3 -> C, D)
HOLDS_FILE = "holds.jsonl"  #: Hold, every stage's (all -> D)


# --------------------------------------------------------------------------------------------
# Form checks
# --------------------------------------------------------------------------------------------


def text_sha256(text: str) -> str:
    """sha256 of the UTF-8 bytes, lowercase hex: Postgres
    `encode(sha256(convert_to(text, 'UTF8')), 'hex')`, the in-database invariant's form."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _need_int(value: Any, what: str, *, minimum: int | None) -> None:
    """An `int` that is not a `bool`; `minimum=None` is unbounded (a year can be -1,400,000)."""
    if not _is_int(value) or (minimum is not None and value < minimum):
        raise ValueError(f"{what}: {value!r} is not an integer >= {minimum}")


def _need_opt_int(value: Any, what: str, *, minimum: int | None) -> None:
    if value is not None:
        _need_int(value, what, minimum=minimum)


def _need_number(value: Any, what: str, *, low: float, high: float) -> None:
    number = isinstance(value, int | float) and not isinstance(value, bool)
    if not number or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{what}: {value!r} is not a finite number in [{low}, {high}]")


def _need_opt_number(value: Any, what: str, *, low: float, high: float) -> None:
    if value is not None:
        _need_number(value, what, low=low, high=high)


def _need_text(value: Any, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what}: {value!r} is not a non-empty string")


def _need_opt_text(value: Any, what: str) -> None:
    if value is not None:
        _need_text(value, what)


def _need_bool(value: Any, what: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{what}: {value!r} is not a boolean")


def _need_opt_bool(value: Any, what: str) -> None:
    if value is not None:
        _need_bool(value, what)


def _need_hex(value: Any, what: str) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ValueError(f"{what}: {value!r} is not a lowercase sha256 hex digest")


def _need_opt_hex(value: Any, what: str) -> None:
    if value is not None:
        _need_hex(value, what)


def _need_member(value: Any, enum_cls: type[StrEnum], what: str) -> None:
    if not isinstance(value, enum_cls):
        raise ValueError(f"{what}: {value!r} is not a {enum_cls.__name__}")


def _need_tuple_of(value: Any, cls: type, what: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, cls) for item in value):
        raise ValueError(f"{what}: expected a tuple of {cls.__name__}, got {value!r}")


def _need_range(start: Any, end: Any, what: str) -> None:
    _need_int(start, f"{what}.start", minimum=0)
    _need_int(end, f"{what}.end", minimum=0)
    if not start < end:
        raise ValueError(f"{what}: [{start}, {end}) is empty or reversed")


def _need_drop_pairs(drop: Any, what: str) -> None:
    """Drop ranges: a tuple of `(a, b)` int pairs, each non-empty, sorted and disjoint."""
    if not isinstance(drop, tuple):
        raise ValueError(f"{what}.drop: expected a tuple of (a, b) pairs, got {drop!r}")
    previous_end = 0
    for pair in drop:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError(f"{what}.drop: {pair!r} is not an (a, b) pair")
        low, high = pair
        _need_range(low, high, f"{what}.drop")
        if low < previous_end:
            raise ValueError(f"{what}.drop: {pair!r} overlaps or precedes the range before it")
        previous_end = high


def _need_drops_within(drop: tuple[tuple[int, int], ...], start: int, end: int, what: str) -> None:
    """Every drop range lies inside the sentence range `[start, end)` it cuts."""
    for low, high in drop:
        if low < start or high > end:
            raise ValueError(f"{what}.drop: ({low}, {high}) leaves [{start}, {end})")


def _need_source_id(value: Any, what: str) -> SourceKind:
    try:
        return source_kind(value)
    except ValueError as exc:
        raise ValueError(f"{what}: {exc}") from exc


# --------------------------------------------------------------------------------------------
# JSON helpers
# --------------------------------------------------------------------------------------------


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def parse_json(text: str) -> Any:
    """`json.loads` that refuses `NaN`, `Infinity` and `-Infinity` (Python accepts them)."""
    return json.loads(text, parse_constant=_refuse_constant)


def _obj(data: Any, what: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{what}: expected a JSON object, got {type(data).__name__}")
    missing = sorted(keys - data.keys())
    unknown = sorted(data.keys() - keys)
    if missing or unknown:
        raise ValueError(f"{what}: missing keys {missing}, unknown keys {unknown}")
    return data


def _list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{what}: expected a JSON array, got {type(value).__name__}")
    return value


def _pairs(value: Any, what: str) -> tuple[tuple[Any, Any], ...]:
    pairs = _list(value, what)
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"{what}: {pair!r} is not an [a, b] pair")
    return tuple((pair[0], pair[1]) for pair in pairs)


def _pairs_json(drop: tuple[tuple[int, int], ...]) -> list[list[int]]:
    return [[low, high] for low, high in drop]


class _JsonRecord(ABC):
    """`to_dict` is the exact JSON shape; `from_dict` is its strict inverse."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """The record as its JSON object."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Any) -> Self:
        """The record from its JSON object; any difference in shape raises `ValueError`."""

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Self:
        return cls.from_dict(parse_json(text))


def dump_jsonl(records: Sequence[_JsonRecord]) -> str:
    """One `to_json()` line per record, LF-terminated: the body of a cross-track JSONL file."""
    return "".join(record.to_json() + "\n" for record in records)


_R = TypeVar("_R", bound=_JsonRecord)


def load_jsonl(path: Path, cls: type[_R]) -> list[_R]:
    """Every line of `path` as a `cls`, through `phase3.run.read_jsonl` (no line is skipped)."""
    return [cls.from_dict(row) for row in read_jsonl(path)]


# --------------------------------------------------------------------------------------------
# S0: the plan
# --------------------------------------------------------------------------------------------

_PLAN_SITE_KEYS = frozenset(
    {
        "site_id", "name", "aliases", "country", "site_type", "period_start", "period_end", "lat",
        "lon", "description", "description_sha256", "raw_data", "raw_data_sha256", "card",
        "card_sha256", "source_url", "wikidata_qid", "enwiki_title", "snapshot_description",
        "flags",
    }
)  # fmt: skip


@dataclass(frozen=True, kw_only=True)
class PlanSite(_JsonRecord):
    """One curated site as S0 read it from production: the old values every later stage uses.

    `raw_data_sha256` is the sha256 of Postgres' own `raw_data::text`, which Python cannot
    re-render, so it is carried, not checked. `raw_data` is the one mutable field (a JSON object);
    treat it as read-only.
    """

    site_id: str
    name: str
    aliases: tuple[str, ...]  #: unified_site_names
    country: str | None
    site_type: str | None
    period_start: int | None
    period_end: int | None
    lat: float
    lon: float
    description: str | None
    description_sha256: str | None
    raw_data: dict[str, Any] | None
    raw_data_sha256: str | None
    card: str | None  #: card_stats.card_description
    card_sha256: str | None
    source_url: str | None
    wikidata_qid: str | None
    enwiki_title: str | None
    snapshot_description: str | None  #: the description in pre-March snapshot d4526691
    flags: frozenset[SiteFlag]

    def __post_init__(self) -> None:
        _need_text(self.site_id, "plan_site.site_id")
        _need_text(self.name, f"{self.site_id}: name")
        _need_tuple_of(self.aliases, str, f"{self.site_id}: aliases")
        for alias in self.aliases:
            _need_text(alias, f"{self.site_id}: alias")
        for field_name in ("country", "site_type", "source_url", "wikidata_qid", "enwiki_title"):
            _need_opt_text(getattr(self, field_name), f"{self.site_id}: {field_name}")
        _need_opt_int(self.period_start, f"{self.site_id}: period_start", minimum=None)
        _need_opt_int(self.period_end, f"{self.site_id}: period_end", minimum=None)
        _need_number(self.lat, f"{self.site_id}: lat", low=-90.0, high=90.0)
        _need_number(self.lon, f"{self.site_id}: lon", low=-180.0, high=180.0)
        for text_field in ("description", "card", "snapshot_description"):
            value = getattr(self, text_field)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{self.site_id}: {text_field} is not a string or null")
        for value, digest, what in (
            (self.description, self.description_sha256, "description"),
            (self.card, self.card_sha256, "card"),
        ):
            _need_opt_hex(digest, f"{self.site_id}: {what}_sha256")
            if (value is None) != (digest is None):
                raise ValueError(f"{self.site_id}: {what} and {what}_sha256 disagree on null")
            if value is not None and text_sha256(value) != digest:
                raise ValueError(f"{self.site_id}: {what}_sha256 is not the sha256 of {what}")
        if self.raw_data is not None and not isinstance(self.raw_data, dict):
            raise ValueError(f"{self.site_id}: raw_data is not a JSON object or null")
        _need_opt_hex(self.raw_data_sha256, f"{self.site_id}: raw_data_sha256")
        if (self.raw_data is None) != (self.raw_data_sha256 is None):
            raise ValueError(f"{self.site_id}: raw_data and raw_data_sha256 disagree on null")
        if not isinstance(self.flags, frozenset) or not all(
            isinstance(flag, SiteFlag) for flag in self.flags
        ):
            raise ValueError(f"{self.site_id}: flags is not a frozenset of SiteFlag")

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "aliases": list(self.aliases),
            "country": self.country,
            "site_type": self.site_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "lat": self.lat,
            "lon": self.lon,
            "description": self.description,
            "description_sha256": self.description_sha256,
            "raw_data": self.raw_data,
            "raw_data_sha256": self.raw_data_sha256,
            "card": self.card,
            "card_sha256": self.card_sha256,
            "source_url": self.source_url,
            "wikidata_qid": self.wikidata_qid,
            "enwiki_title": self.enwiki_title,
            "snapshot_description": self.snapshot_description,
            "flags": sorted(flag.value for flag in self.flags),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "plan_site", _PLAN_SITE_KEYS)
        flags = _list(d["flags"], "plan_site.flags")
        if len(set(map(str, flags))) != len(flags):
            raise ValueError(f"plan_site.flags: a flag is listed twice: {flags!r}")
        return cls(
            site_id=d["site_id"],
            name=d["name"],
            aliases=tuple(_list(d["aliases"], "plan_site.aliases")),
            country=d["country"],
            site_type=d["site_type"],
            period_start=d["period_start"],
            period_end=d["period_end"],
            lat=d["lat"],
            lon=d["lon"],
            description=d["description"],
            description_sha256=d["description_sha256"],
            raw_data=d["raw_data"],
            raw_data_sha256=d["raw_data_sha256"],
            card=d["card"],
            card_sha256=d["card_sha256"],
            source_url=d["source_url"],
            wikidata_qid=d["wikidata_qid"],
            enwiki_title=d["enwiki_title"],
            snapshot_description=d["snapshot_description"],
            flags=frozenset(_coerce(SiteFlag, flag, "plan_site.flag") for flag in flags),
        )


# --------------------------------------------------------------------------------------------
# S1: the pinned sources
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SubjectGate(_JsonRecord):
    """The subject gate's recorded facts and verdict (S1), kept in the source's meta."""

    qid_match: bool
    shared: bool
    concept: bool
    place_item: bool
    km: float | None  #: article (or P625) coordinates to the stored point
    name_score: float | None  #: rapidfuzz token_sort_ratio of the directional name match
    verdict: SubjectVerdict

    def __post_init__(self) -> None:
        for field_name in ("qid_match", "shared", "concept", "place_item"):
            _need_bool(getattr(self, field_name), f"subject_gate.{field_name}")
        _need_opt_number(self.km, "subject_gate.km", low=0.0, high=math.inf)
        _need_opt_number(self.name_score, "subject_gate.name_score", low=0.0, high=100.0)
        _need_member(self.verdict, SubjectVerdict, "subject_gate.verdict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "qid_match": self.qid_match,
            "shared": self.shared,
            "concept": self.concept,
            "place_item": self.place_item,
            "km": self.km,
            "name_score": self.name_score,
            "verdict": self.verdict.value,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        keys = frozenset({"qid_match", "shared", "concept", "place_item", "km", "name_score"})
        d = _obj(data, "subject_gate", keys | {"verdict"})
        return cls(
            **{key: d[key] for key in keys},
            verdict=_coerce(SubjectVerdict, d["verdict"], "subject_gate.verdict"),
        )


@dataclass(frozen=True, kw_only=True)
class Tdm(_JsonRecord):
    """The TDM opt-out check of a non-free page (training_corpus), before it is stored."""

    checked: bool
    reserved: bool
    signal: str | None  #: what reserved it: robots, tdmrep or the HTML meta

    def __post_init__(self) -> None:
        _need_bool(self.checked, "tdm.checked")
        _need_bool(self.reserved, "tdm.reserved")
        _need_opt_text(self.signal, "tdm.signal")

    def to_dict(self) -> dict[str, Any]:
        return {"checked": self.checked, "reserved": self.reserved, "signal": self.signal}

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "tdm", frozenset({"checked", "reserved", "signal"}))
        return cls(checked=d["checked"], reserved=d["reserved"], signal=d["signal"])


_SOURCE_DOC_KEYS = frozenset(
    {
        "id", "url", "permalink", "title", "pageid", "revid", "lastrevid", "rev_timestamp",
        "retrieved_at", "sha256_raw", "sha256_text", "licence", "route", "subject_gate", "tdm",
        "final_url", "truncated",
    }
)  # fmt: skip


@dataclass(frozen=True, kw_only=True)
class SourceDoc(_JsonRecord):
    """`src.<id>.meta`: one pinned source (source_store LAYOUT). Every key is always written.

    W and T carry the Wikipedia pin (`permalink` `...index.php?title=<T>&oldid=<revid>`, `pageid`,
    `revid`, `lastrevid`, `rev_timestamp`) and `subject_gate`; R carries `tdm`, `final_url` and
    `truncated`; D (Wikidata) carries `lastrevid`. The rest are `None`. Which fields a kind needs,
    and whether the pin holds, is V1's to check (see the module docstring): here only the form.
    """

    id: str
    url: str
    permalink: str | None
    title: str | None
    pageid: int | None
    revid: int | None
    lastrevid: int | None
    rev_timestamp: str | None
    retrieved_at: str
    sha256_raw: str
    sha256_text: str | None  #: of the `.txt` bytes; D has no text
    licence: Licence
    route: Route
    subject_gate: SubjectGate | None
    tdm: Tdm | None
    final_url: str | None
    truncated: bool | None

    def __post_init__(self) -> None:
        _need_source_id(self.id, "source_doc.id")
        what = f"source {self.id}"
        _need_text(self.url, f"{what}: url")
        for field_name in ("permalink", "title", "rev_timestamp", "final_url"):
            _need_opt_text(getattr(self, field_name), f"{what}: {field_name}")
        for field_name in ("pageid", "revid", "lastrevid"):
            _need_opt_int(getattr(self, field_name), f"{what}: {field_name}", minimum=0)
        _need_text(self.retrieved_at, f"{what}: retrieved_at")
        _need_hex(self.sha256_raw, f"{what}: sha256_raw")
        _need_opt_hex(self.sha256_text, f"{what}: sha256_text")
        _need_member(self.licence, Licence, f"{what}: licence")
        _need_member(self.route, Route, f"{what}: route")
        if self.subject_gate is not None and not isinstance(self.subject_gate, SubjectGate):
            raise ValueError(f"{what}: subject_gate is not a SubjectGate or null")
        if self.tdm is not None and not isinstance(self.tdm, Tdm):
            raise ValueError(f"{what}: tdm is not a Tdm or null")
        _need_opt_bool(self.truncated, f"{what}: truncated")

    @property
    def kind(self) -> SourceKind:
        return source_kind(self.id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "permalink": self.permalink,
            "title": self.title,
            "pageid": self.pageid,
            "revid": self.revid,
            "lastrevid": self.lastrevid,
            "rev_timestamp": self.rev_timestamp,
            "retrieved_at": self.retrieved_at,
            "sha256_raw": self.sha256_raw,
            "sha256_text": self.sha256_text,
            "licence": self.licence.value,
            "route": self.route.value,
            "subject_gate": None if self.subject_gate is None else self.subject_gate.to_dict(),
            "tdm": None if self.tdm is None else self.tdm.to_dict(),
            "final_url": self.final_url,
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "source_doc", _SOURCE_DOC_KEYS)
        plain = _SOURCE_DOC_KEYS - {"licence", "route", "subject_gate", "tdm"}
        return cls(
            **{key: d[key] for key in plain},
            licence=_coerce(Licence, d["licence"], "source_doc.licence"),
            route=_coerce(Route, d["route"], "source_doc.route"),
            subject_gate=(
                None if d["subject_gate"] is None else SubjectGate.from_dict(d["subject_gate"])
            ),
            tdm=None if d["tdm"] is None else Tdm.from_dict(d["tdm"]),
        )


#: The text sources each lane uses (pipeline, "Lane assignment"): W and S one English article, T
#: one other-language article, 0 none. R uses one or more non-free pages.
_LANE_SOURCE_KINDS: Mapping[Lane, list[SourceKind]] = MappingProxyType(
    {
        Lane.W: [SourceKind.W],
        Lane.S: [SourceKind.W],
        Lane.T: [SourceKind.T],
        Lane.ZERO: [],
    }
)


@dataclass(frozen=True, kw_only=True)
class LaneAssignment(_JsonRecord):
    """S1b's one lane decision per site, from recorded facts. A site never changes lane."""

    site_id: str
    lane: Lane
    sources: tuple[str, ...]  #: the store ids whose text the lane uses; D is never one
    detail: str  #: the facts the decision was made from

    def __post_init__(self) -> None:
        _need_text(self.site_id, "lane_assignment.site_id")
        _need_member(self.lane, Lane, f"{self.site_id}: lane")
        if self.lane not in ASSIGNED_LANES:
            raise ValueError(f"{self.site_id}: lane {self.lane.value} is never assigned")
        _need_tuple_of(self.sources, str, f"{self.site_id}: sources")
        kinds = [_need_source_id(source, f"{self.site_id}: source") for source in self.sources]
        if len(set(self.sources)) != len(self.sources):
            raise ValueError(f"{self.site_id}: a source is listed twice: {self.sources!r}")
        if self.lane is Lane.R:
            fits = bool(kinds) and all(kind is SourceKind.R for kind in kinds)
        else:
            fits = kinds == _LANE_SOURCE_KINDS[self.lane]
        if not fits:
            raise ValueError(
                f"{self.site_id}: lane {self.lane.value} cannot use the sources {self.sources!r}"
            )
        _need_text(self.detail, f"{self.site_id}: detail")

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "lane": self.lane.value,
            "sources": list(self.sources),
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "lane_assignment", frozenset({"site_id", "lane", "sources", "detail"}))
        return cls(
            site_id=d["site_id"],
            lane=_coerce(Lane, d["lane"], "lane_assignment.lane"),
            sources=tuple(_list(d["sources"], "lane_assignment.sources")),
            detail=d["detail"],
        )


# --------------------------------------------------------------------------------------------
# S2: sentences and spans
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Span(_JsonRecord):
    """One deletable span a sentence offers the selector.

    `source_text[start:end]` is exactly what the prompt shows after `a1=`; a drop removes exactly
    that range (see `docs/procedures/PHASE4_CONTRACTS.md`, "Offsets and spans").
    """

    id: str
    kind: SpanKind
    start: int
    end: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _SPAN_ID.fullmatch(self.id):
            raise ValueError(f"span id {self.id!r} is not a kind letter and a number")
        _need_member(self.kind, SpanKind, f"span {self.id}: kind")
        if self.id[0] != self.kind.value:
            raise ValueError(f"span {self.id}: its id does not name its kind {self.kind.value}")
        _need_range(self.start, self.end, f"span {self.id}")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind.value, "start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "span", frozenset({"id", "kind", "start", "end"}))
        return cls(
            id=d["id"],
            kind=_coerce(SpanKind, d["kind"], "span.kind"),
            start=d["start"],
            end=d["end"],
        )


@dataclass(frozen=True, kw_only=True)
class Sentence(_JsonRecord):
    """One numbered source sentence (S2): `sid` is `W12` - the 12th sentence of `src.W`.

    `index` counts the whole split of the pinned text from 1, so an id does not move when the
    candidate pool is bounded. `section` is the heading it sits under; `None` is the lead.
    """

    src: str
    index: int
    section: str | None
    start: int
    end: int
    spans: tuple[Span, ...]

    def __post_init__(self) -> None:
        kind = _need_source_id(self.src, "sentence.src")
        if kind not in SELECTABLE_KINDS:
            raise ValueError(f"sentence.src: {self.src} is not a selectable source (W, T.<lang>)")
        _need_int(self.index, f"sentence {self.src}: index", minimum=1)
        what = f"sentence {self.sid}"
        _need_opt_text(self.section, f"{what}: section")
        _need_range(self.start, self.end, what)
        _need_tuple_of(self.spans, Span, f"{what}: spans")
        if len({span.id for span in self.spans}) != len(self.spans):
            raise ValueError(f"{what}: a span id is offered twice")
        for span in self.spans:
            if span.start < self.start or span.end > self.end:
                raise ValueError(f"{what}: span {span.id} leaves the sentence")

    @property
    def sid(self) -> str:
        return f"{self.src}{self.index}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "src": self.src,
            "index": self.index,
            "section": self.section,
            "start": self.start,
            "end": self.end,
            "spans": [span.to_dict() for span in self.spans],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "sentence", frozenset({"src", "index", "section", "start", "end", "spans"}))
        return cls(
            src=d["src"],
            index=d["index"],
            section=d["section"],
            start=d["start"],
            end=d["end"],
            spans=tuple(Span.from_dict(span) for span in _list(d["spans"], "sentence.spans")),
        )


# --------------------------------------------------------------------------------------------
# S3: the selector's answer
# --------------------------------------------------------------------------------------------


class SelectionRefused(ValueError):
    """A selector answer the contract refuses, with its named problem (HOLD, no retry)."""

    def __init__(self, problem: SelectionProblem, detail: str) -> None:
        super().__init__(f"{problem.value}: {detail}")
        self.problem = problem
        self.detail = detail


@dataclass(frozen=True, kw_only=True)
class Pick(_JsonRecord):
    """One `DESC:` or `CARD:` line: a sentence id and the span ids to drop from it."""

    sid: str
    drop: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sid, str) or not _SID.fullmatch(self.sid):
            raise ValueError(f"pick: {self.sid!r} is not a sentence id")
        _need_tuple_of(self.drop, str, f"pick {self.sid}: drop")
        for span_id in self.drop:
            if not _SPAN_ID.fullmatch(span_id):
                raise ValueError(f"pick {self.sid}: {span_id!r} is not a span id")
        if len(set(self.drop)) != len(self.drop):
            raise SelectionRefused(
                SelectionProblem.DUPLICATE, f"{self.sid} drops a span twice: {self.drop!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"sid": self.sid, "drop": list(self.drop)}

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "pick", frozenset({"sid", "drop"}))
        return cls(sid=d["sid"], drop=tuple(_list(d["drop"], "pick.drop")))


@dataclass(frozen=True, kw_only=True)
class Selection(_JsonRecord):
    """A parsed selector answer: 1-8 DESC picks and 1-2 CARD picks, or an ABSTAIN reason.

    The picks are in answer order; the assembler puts sentences in source order. A CARD pick's
    spans are removed on top of its DESC pick's spans. Whether a sid is in the pool and a span is
    offered is `select_stage.parse_selection`'s check (it knows the pool); the rest is here.
    """

    site_id: str
    desc: tuple[Pick, ...]
    card: tuple[Pick, ...]
    abstain: str | None

    def __post_init__(self) -> None:
        _need_text(self.site_id, "selection.site_id")
        _need_tuple_of(self.desc, Pick, f"{self.site_id}: desc")
        _need_tuple_of(self.card, Pick, f"{self.site_id}: card")
        if self.abstain is not None:
            if not isinstance(self.abstain, str):
                raise ValueError(f"{self.site_id}: abstain is not a string or null")
            if self.desc or self.card:
                raise SelectionRefused(
                    SelectionProblem.ABSTAIN_WITH_OTHER_LINES, f"{self.site_id}: ABSTAIN and picks"
                )
            if not self.abstain.strip():
                raise SelectionRefused(
                    SelectionProblem.ABSTAIN_WITHOUT_REASON,
                    f"{self.site_id}: ABSTAIN names no reason",
                )
            return
        if not self.desc:
            raise SelectionRefused(SelectionProblem.NO_DESC, f"{self.site_id}: no DESC line")
        if len(self.desc) > MAX_DESC:
            raise SelectionRefused(
                SelectionProblem.TOO_MANY_DESC, f"{self.site_id}: {len(self.desc)} DESC lines"
            )
        if not self.card:
            raise SelectionRefused(SelectionProblem.NO_CARD, f"{self.site_id}: no CARD line")
        if len(self.card) > MAX_CARD:
            raise SelectionRefused(
                SelectionProblem.TOO_MANY_CARD, f"{self.site_id}: {len(self.card)} CARD lines"
            )
        for label, picks in (("DESC", self.desc), ("CARD", self.card)):
            sids = [pick.sid for pick in picks]
            if len(set(sids)) != len(sids):
                raise SelectionRefused(
                    SelectionProblem.DUPLICATE, f"{self.site_id}: a {label} sid repeats: {sids}"
                )
        outside = sorted({pick.sid for pick in self.card} - {pick.sid for pick in self.desc})
        if outside:
            raise SelectionRefused(
                SelectionProblem.CARD_NOT_IN_DESC, f"{self.site_id}: CARD {outside} not in DESC"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "desc": [pick.to_dict() for pick in self.desc],
            "card": [pick.to_dict() for pick in self.card],
            "abstain": self.abstain,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "selection", frozenset({"site_id", "desc", "card", "abstain"}))
        return cls(
            site_id=d["site_id"],
            desc=tuple(Pick.from_dict(pick) for pick in _list(d["desc"], "selection.desc")),
            card=tuple(Pick.from_dict(pick) for pick in _list(d["card"], "selection.card")),
            abstain=d["abstain"],
        )


# --------------------------------------------------------------------------------------------
# S4: provenance v1 (production_write, "_description_provenance v1") and the assembly
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Attribution(_JsonRecord):
    """CC BY-SA 4.0 section 3(a): title, the revision permalink, the licence link, the change."""

    title: str
    url: str
    licence_url: str
    changes: Changes

    def __post_init__(self) -> None:
        _need_text(self.title, "attribution.title")
        _need_text(self.url, "attribution.url")
        _need_text(self.licence_url, "attribution.licence_url")
        _need_member(self.changes, Changes, "attribution.changes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "licence_url": self.licence_url,
            "changes": self.changes.value,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "attribution", frozenset({"title", "url", "licence_url", "changes"}))
        return cls(
            title=d["title"],
            url=d["url"],
            licence_url=d["licence_url"],
            changes=_coerce(Changes, d["changes"], "attribution.changes"),
        )


@dataclass(frozen=True, kw_only=True)
class SourceRef(_JsonRecord):
    """`provenance.sources[i]`: a cited source's pin. R pages have no revision (`None`)."""

    id: str
    url: str  #: the oldid permalink (W, T) or the page's final URL (R)
    revid: int | None
    rev_timestamp: str | None
    text_sha256: str
    licence: Licence

    def __post_init__(self) -> None:
        kind = _need_source_id(self.id, "source_ref.id")
        if kind not in CITABLE_KINDS:
            raise ValueError(f"source_ref {self.id}: Wikidata is a witness and is never cited")
        _need_text(self.url, f"source_ref {self.id}: url")
        _need_opt_int(self.revid, f"source_ref {self.id}: revid", minimum=0)
        _need_opt_text(self.rev_timestamp, f"source_ref {self.id}: rev_timestamp")
        _need_hex(self.text_sha256, f"source_ref {self.id}: text_sha256")
        _need_member(self.licence, Licence, f"source_ref {self.id}: licence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "revid": self.revid,
            "rev_timestamp": self.rev_timestamp,
            "text_sha256": self.text_sha256,
            "licence": self.licence.value,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        keys = frozenset({"id", "url", "revid", "rev_timestamp", "text_sha256"})
        d = _obj(data, "source_ref", keys | {"licence"})
        return cls(
            **{key: d[key] for key in keys},
            licence=_coerce(Licence, d["licence"], "source_ref.licence"),
        )


@dataclass(frozen=True, kw_only=True)
class PublishedSentence(_JsonRecord):
    """`provenance.sentences[i]`: citation number, source, range and dropped ranges.

    The invariant the verifier re-derives (V3): published sentence i ==
    apply_drops(source_text[start:end], drop) + ' [n]' + final punctuation. Offsets only; the
    quote text lives in the journal evidence and the store, never in public `raw_data`.
    """

    n: int
    src: str
    start: int
    end: int
    drop: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        _need_int(self.n, "published_sentence.n", minimum=1)
        _need_source_id(self.src, "published_sentence.src")
        what = f"published_sentence {self.src}[{self.start}:{self.end}]"
        _need_range(self.start, self.end, what)
        _need_drop_pairs(self.drop, what)
        _need_drops_within(self.drop, self.start, self.end, what)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "src": self.src,
            "start": self.start,
            "end": self.end,
            "drop": _pairs_json(self.drop),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "published_sentence", frozenset({"n", "src", "start", "end", "drop"}))
        return cls(
            n=d["n"],
            src=d["src"],
            start=d["start"],
            end=d["end"],
            drop=_pairs(d["drop"], "published_sentence.drop"),
        )


@dataclass(frozen=True, kw_only=True)
class CardItem(_JsonRecord):
    """`provenance.card.items[i]`: a published sentence (its 0-based index in `sentences`) and
    the full list of ranges dropped from its source slice for the card (its DESC drops included).
    The only other edit is the closed spoken form 'c.'/'ca.' -> 'circa' (V10)."""

    sentence: int
    drop: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        _need_int(self.sentence, "card_item.sentence", minimum=0)
        _need_drop_pairs(self.drop, f"card_item {self.sentence}")

    def to_dict(self) -> dict[str, Any]:
        return {"sentence": self.sentence, "drop": _pairs_json(self.drop)}

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "card_item", frozenset({"sentence", "drop"}))
        return cls(sentence=d["sentence"], drop=_pairs(d["drop"], "card_item.drop"))


@dataclass(frozen=True, kw_only=True)
class Card(_JsonRecord):
    """`provenance.card`: 1-2 items in source order, and the sha256 of the card text (V13)."""

    items: tuple[CardItem, ...]
    text_sha256: str

    def __post_init__(self) -> None:
        _need_tuple_of(self.items, CardItem, "card.items")
        if not 1 <= len(self.items) <= MAX_CARD:
            raise ValueError(f"card.items: {len(self.items)} items, the contract allows 1-2")
        indices = [item.sentence for item in self.items]
        if indices != sorted(set(indices)):
            raise ValueError(f"card.items: {indices} is not strictly ascending (source order)")
        _need_hex(self.text_sha256, "card.text_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items], "text_sha256": self.text_sha256}

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "card", frozenset({"items", "text_sha256"}))
        return cls(
            items=tuple(CardItem.from_dict(item) for item in _list(d["items"], "card.items")),
            text_sha256=d["text_sha256"],
        )


_PROVENANCE_KEYS = frozenset(
    {
        "v", "run", "lane", "ai", "ai_system", "licence", "attribution", "sources", "sentences",
        "card", "desc_sha256",
    }
)  # fmt: skip
_LEGACY_KEYS = frozenset({"v", "lane", "ai", "ai_system", "basis", "desc_sha256"})


def _need_version(value: Any, what: str) -> None:
    if not _is_int(value) or value != PROVENANCE_VERSION:
        raise ValueError(f"{what}.v: {value!r} is not version {PROVENANCE_VERSION}")


@dataclass(frozen=True, kw_only=True)
class Provenance(_JsonRecord):
    """`raw_data._description_provenance` v1 for lanes W, S, T and R (production_write)."""

    run: str
    lane: Lane
    ai: AiMark
    ai_system: str
    licence: Licence
    attribution: Attribution
    sources: tuple[SourceRef, ...]
    sentences: tuple[PublishedSentence, ...]
    card: Card | None
    desc_sha256: str
    v: int = PROVENANCE_VERSION

    def __post_init__(self) -> None:
        _need_version(self.v, "provenance")
        _need_text(self.run, "provenance.run")
        _need_member(self.lane, Lane, "provenance.lane")
        if self.lane not in LANE_CHANGES:
            raise ValueError(f"provenance.lane: {self.lane.value} has no full provenance")
        _need_member(self.ai, AiMark, "provenance.ai")
        if self.ai is not LANE_AI[self.lane]:
            raise ValueError(f"provenance.ai: lane {self.lane.value} is {LANE_AI[self.lane]}")
        if self.ai_system != AI_SYSTEM:
            raise ValueError(f"provenance.ai_system: {self.ai_system!r} is not {AI_SYSTEM!r}")
        _need_member(self.licence, Licence, "provenance.licence")
        if self.licence is not PUBLISHED_LICENCE:
            raise ValueError(f"provenance.licence: published text is {PUBLISHED_LICENCE}")
        if not isinstance(self.attribution, Attribution):
            raise ValueError("provenance.attribution is not an Attribution")
        if self.attribution.changes is not LANE_CHANGES[self.lane]:
            raise ValueError(
                f"attribution.changes: lane {self.lane.value} is {LANE_CHANGES[self.lane]!r}"
            )
        if self.attribution.licence_url != PUBLISHED_LICENCE_URL:
            raise ValueError(f"attribution.licence_url is not {PUBLISHED_LICENCE_URL}")
        _need_tuple_of(self.sources, SourceRef, "provenance.sources")
        source_ids = [source.id for source in self.sources]
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise ValueError(f"provenance.sources: empty or an id repeats: {source_ids}")
        if self.attribution.url not in {source.url for source in self.sources}:
            raise ValueError("attribution.url is not the url of a cited source")
        _need_tuple_of(self.sentences, PublishedSentence, "provenance.sentences")
        if not self.sentences:
            raise ValueError("provenance.sentences: no sentence")
        unknown = sorted({s.src for s in self.sentences} - set(source_ids))
        if unknown:
            raise ValueError(f"provenance.sentences: sources {unknown} are not in sources")
        uncited = sorted(set(source_ids) - {s.src for s in self.sentences})
        if uncited:
            raise ValueError(f"provenance.sources: {uncited} are cited by no sentence")
        last_end: dict[str, int] = {}
        for sentence in self.sentences:
            if sentence.start < last_end.get(sentence.src, 0):
                raise ValueError(
                    f"provenance.sentences: {sentence.src}[{sentence.start}:] is out of source "
                    "order or overlaps the sentence before it"
                )
            last_end[sentence.src] = sentence.end
        if self.card is not None:
            if not isinstance(self.card, Card):
                raise ValueError("provenance.card is not a Card or null")
            for item in self.card.items:
                if item.sentence >= len(self.sentences):
                    raise ValueError(
                        f"card item names sentence {item.sentence}, which is not there"
                    )
                cut = self.sentences[item.sentence]
                _need_drops_within(item.drop, cut.start, cut.end, f"card item {item.sentence}")
        _need_hex(self.desc_sha256, "provenance.desc_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "run": self.run,
            "lane": self.lane.value,
            "ai": self.ai.value,
            "ai_system": self.ai_system,
            "licence": self.licence.value,
            "attribution": self.attribution.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
            "sentences": [sentence.to_dict() for sentence in self.sentences],
            "card": None if self.card is None else self.card.to_dict(),
            "desc_sha256": self.desc_sha256,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "provenance", _PROVENANCE_KEYS)
        return cls(
            v=d["v"],
            run=d["run"],
            lane=_coerce(Lane, d["lane"], "provenance.lane"),
            ai=_coerce(AiMark, d["ai"], "provenance.ai"),
            ai_system=d["ai_system"],
            licence=_coerce(Licence, d["licence"], "provenance.licence"),
            attribution=Attribution.from_dict(d["attribution"]),
            sources=tuple(
                SourceRef.from_dict(source) for source in _list(d["sources"], "provenance.sources")
            ),
            sentences=tuple(
                PublishedSentence.from_dict(sentence)
                for sentence in _list(d["sentences"], "provenance.sentences")
            ),
            card=None if d["card"] is None else Card.from_dict(d["card"]),
            desc_sha256=d["desc_sha256"],
        )


@dataclass(frozen=True, kw_only=True)
class LegacyProvenance(_JsonRecord):
    """Lane L: truthful 'generated' provenance for a held site whose text the March LLM chain
    changed (it differs from snapshot d4526691). No sources, no sentences, no card."""

    desc_sha256: str
    v: int = PROVENANCE_VERSION
    lane: Lane = Lane.L
    ai: AiMark = AiMark.GENERATED
    ai_system: str = LEGACY_AI_SYSTEM
    basis: str = LEGACY_BASIS

    def __post_init__(self) -> None:
        _need_version(self.v, "legacy_provenance")
        if self.lane is not Lane.L:
            raise ValueError(f"legacy_provenance.lane: {self.lane!r} is not L")
        if self.ai is not AiMark.GENERATED:
            raise ValueError(f"legacy_provenance.ai: {self.ai!r} is not generated")
        if self.ai_system != LEGACY_AI_SYSTEM:
            raise ValueError(f"legacy_provenance.ai_system: {self.ai_system!r}")
        if self.basis != LEGACY_BASIS:
            raise ValueError(f"legacy_provenance.basis: {self.basis!r}")
        _need_hex(self.desc_sha256, "legacy_provenance.desc_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "lane": self.lane.value,
            "ai": self.ai.value,
            "ai_system": self.ai_system,
            "basis": self.basis,
            "desc_sha256": self.desc_sha256,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "legacy_provenance", _LEGACY_KEYS)
        return cls(
            v=d["v"],
            lane=_coerce(Lane, d["lane"], "legacy_provenance.lane"),
            ai=_coerce(AiMark, d["ai"], "legacy_provenance.ai"),
            ai_system=d["ai_system"],
            basis=d["basis"],
            desc_sha256=d["desc_sha256"],
        )


def provenance_from_dict(data: Any) -> Provenance | LegacyProvenance:
    """Read `raw_data._description_provenance` of either shape; the lane decides which."""
    if not isinstance(data, dict):
        raise ValueError(f"provenance: expected a JSON object, got {type(data).__name__}")
    if data.get("lane") == Lane.L.value:
        return LegacyProvenance.from_dict(data)
    return Provenance.from_dict(data)


@dataclass(frozen=True, kw_only=True)
class Citation(_JsonRecord):
    """One `raw_data.description_citations` entry: the existing `DescriptionCitation` shape
    (`anRoute.ts`) plus `license`; the old `claim` key is dropped (writer, ASSEMBLY)."""

    n: int
    url: str  #: the pinned permalink (W, T) or final URL (R)
    title: str  #: 'Wikipedia: <title>' for Wikipedia sources
    domain: str
    license: Licence

    def __post_init__(self) -> None:
        _need_int(self.n, "citation.n", minimum=1)
        _need_text(self.url, f"citation {self.n}: url")
        _need_text(self.title, f"citation {self.n}: title")
        _need_text(self.domain, f"citation {self.n}: domain")
        _need_member(self.license, Licence, f"citation {self.n}: license")

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "url": self.url,
            "title": self.title,
            "domain": self.domain,
            "license": self.license.value,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        keys = frozenset({"n", "url", "title", "domain"})
        d = _obj(data, "citation", keys | {"license"})
        return cls(
            **{key: d[key] for key in keys},
            license=_coerce(Licence, d["license"], "citation.license"),
        )


@dataclass(frozen=True, kw_only=True)
class Assembly(_JsonRecord):
    """S4's output for one site: the description, its citations, the card and the provenance.

    Whether these agree with each other (hashes, markers, the card inside the description) is the
    verifier's to check; the assembler builds them, the verifier re-derives them.
    """

    site_id: str
    description: str
    citations: tuple[Citation, ...]
    card: str | None
    provenance: Provenance

    def __post_init__(self) -> None:
        _need_text(self.site_id, "assembly.site_id")
        _need_text(self.description, f"{self.site_id}: description")
        _need_tuple_of(self.citations, Citation, f"{self.site_id}: citations")
        _need_opt_text(self.card, f"{self.site_id}: card")
        if not isinstance(self.provenance, Provenance):
            raise ValueError(f"{self.site_id}: provenance is not a (full) Provenance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "description": self.description,
            "citations": [citation.to_dict() for citation in self.citations],
            "card": self.card,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        keys = frozenset({"site_id", "description", "citations", "card", "provenance"})
        d = _obj(data, "assembly", keys)
        return cls(
            site_id=d["site_id"],
            description=d["description"],
            citations=tuple(
                Citation.from_dict(citation)
                for citation in _list(d["citations"], "assembly.citations")
            ),
            card=d["card"],
            provenance=Provenance.from_dict(d["provenance"]),
        )


# --------------------------------------------------------------------------------------------
# Holds
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Hold(_JsonRecord):
    """One reason a site (or only its card) is not written: a line of `holds.jsonl`/HOLDS4."""

    site_id: str
    scope: HoldScope
    reason: HoldReason
    detail: str

    def __post_init__(self) -> None:
        _need_text(self.site_id, "hold.site_id")
        _need_member(self.scope, HoldScope, f"hold {self.site_id}: scope")
        _need_member(self.reason, HoldReason, f"hold {self.site_id}: reason")
        if self.reason in CARD_ONLY_REASONS and self.scope is not HoldScope.CARD:
            raise ValueError(f"hold {self.site_id}: {self.reason.value} holds only a card")
        _need_text(self.detail, f"hold {self.site_id}: detail")

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "scope": self.scope.value,
            "reason": self.reason.value,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        d = _obj(data, "hold", frozenset({"site_id", "scope", "reason", "detail"}))
        return cls(
            site_id=d["site_id"],
            scope=_coerce(HoldScope, d["scope"], "hold.scope"),
            reason=_coerce(HoldReason, d["reason"], "hold.reason"),
            detail=d["detail"],
        )
