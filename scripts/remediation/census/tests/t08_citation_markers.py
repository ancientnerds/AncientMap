"""T08 - citation integrity: the `[N]` markers in the description vs the evidence array.

WHICH PAIR THIS CHECK IS ABOUT - established 2026-09-20 against the code and the exported
snapshot, because a check built on the wrong pair measures nothing:

* The text is `unified_sites.description`. 2,141 of the 5,004 curated rows carry at least
  one `[N]` marker. Its reader-facing consumer is
  `ancient-nerds-map/src/components/CitationText.tsx::citationNodes`, which matches
  `/\\[(\\d+)\\]/g` and turns marker N into a link when the entry `n == N` exists - and into
  a bare `<sup>[N]</sup>` when it does not. That last branch is the visible defect this
  check exists for.
* The array is `unified_sites.raw_data -> 'description_citations'`: 2,217 rows, each entry
  `{n, url, title, domain, claim}`. It is the ONLY key in `raw_data` on every row that has
  it (the remaining 2,787 rows carry `raw_data` NULL), so the array never shares a row with
  another `raw_data` feature. `scripts/remediation/census/snapshot.py` exports `raw_data`
  whole, so the array is in the snapshot.
* The plan text names `card_stats.card_description` as a candidate text. It is not: zero of
  the 5,004 `card_description` values contains a marker (measured), and `card_stats` has no
  evidence array - `evidence` lives only in `raw_data`. The candidate pair in the plan is
  therefore not the pair in the data; the pair the frontend actually resolves is
  (description, raw_data.description_citations), because both travel in the same site row
  payload (`api/routes/sites.py:1237`, `pipeline/static_exporter.py:388`).

Who writes the pair: `api/routes/sites.py::batch_upload_sites` (description and
`description_citations` from one upload payload - `edited_by='MrSchneebly'` on 2,133 rows
with markers and 75 without, 2,202 of them dated 2026-03-14) and
`scripts/audit_enrich.py::merge_verified_citations` (`verify-citations-merge`, the "10
sites" recorded as an `api/main.py` startup fix, which only back-fills rows where the key is
absent). Nothing rewrites either field on container restart, so - unlike T04 - there is no
restart invariant to assert here; the producer that could undo a fix is another upload, not
a boot.

THE FOUR FAILURE MODES and their measured size in this snapshot (the plan's Phase 1 item 8
states 76 / 11 / 8; this module reproduces them exactly, plus 4 sites whose numbering is
not 1..N, which the plan did not count):

    no-markers          76   array present, description cites nothing at all
    marker-without-entry 11  the text cites a number the array has no entry for
    entry-never-cited     8  the array holds an entry no marker reaches
    numbering-gap         4  the cited numbers are not 1..N

EVERY FINDING IS `Proposal.REVIEW` + `Confidence.UNVERIFIABLE`. Not one of the four modes
has a mechanically decidable correct value:

* A dangling marker can be cured by adding the missing evidence entry (which needs a
  source nobody has fetched) or by dropping the claim or just the marker from the text -
  and the pipeline's own answer in the verification stage is to drop the whole sentence
  (`docs/procedures/ENRICHMENT_AUDIT.md`, Phase 3), not the marker
  (`pipeline/lyra/theo_citations.py::strip_orphan_citation_markers`). Two opposite
  remedies from the project's own code: that is a decision, not a computation.
* The three no-marker rows inspected by hand (Lindos, Kuntur Amaya, Quispiguanca) carry
  array claims that paraphrase a sentence of their own description - the markers were lost
  while the array survived, so re-attaching them is plausible; dropping the array is equally
  defensible. Which one is right is not in the data.
* An unreached entry and a skipped number are invariant violations, not wrong values.

Writing a value here would mean rewriting published description text from a guess, which
is the one thing the audit forbids (an empty field beats a wrong one). The check
therefore stops at evidence: every finding carries the description excerpt and the
array's number list. Because both quotes come from the SAME row, they are a record of
what was observed and not two independent sources - hence UNVERIFIABLE, never TWO_SOURCE.

Deliberately NOT used: `theo_citations._collect_non_numeric_markers` /
`strip_debug_tokens`. They flag the bracketed tokens in a scholarly transcription of a
damaged inscription as pipeline artifacts - `CVNORIX MACVSMA QVICO[L]I[N]E` (Wroxeter
Stone, `dae9bc10-f90d-45d4-9ab6-1408912b461e`) is reconstructed-letter notation, and
stripping it would corrupt the description. Measured on all 5,004 rows: exactly one such
site, and it is not a defect. A check that reports it would send a fixer to break it.

`current_value` is a literal readout of the offending side, never a proposed replacement:
the marker numbers in first-use order (text side) or the array's `n` values in stored
order (array side). `proposed_value` is always None.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T08"
NAME = "citation markers match the evidence array"
DIMENSION = "content / citation integrity"

REPO = Path(__file__).resolve().parents[4]

#: the reader-facing text, and the array, as they are named in the snapshot
TEXT_FIELD = "description"
ARRAY_FIELD = "raw_data.description_citations"

SRC_TEXT = f"snapshot:unified_sites.{TEXT_FIELD}"
SRC_ARRAY = f"snapshot:unified_sites.{ARRAY_FIELD}"
SRC_CONSUMER = "ancient-nerds-map/src/components/CitationText.tsx:citationNodes"

#: A marker, exactly as `audit_citations` (`re.findall(r"\[(\d+)\]", prose_only)`) and the
#: frontend (`/\[(\d+)\]/g` in CitationText.tsx, `/[^\S\n]*\[\d+\]/g` in seo/text.ts) define
#: one. The module exports no such symbol - only the private `_ANY_CITATION_RE`, which also
#: accepts the journal's `[V2]` video markers that a site description never carries and the
#: frontend never resolves. Four identical copies of this shape exist in the project; this
#: is the fifth, and it is the only one the census can import. Grouped and range forms are
#: NOT handled here - they go through the pipeline's own expander first (see below).
_MARKER_RE = re.compile(r"\[(\d+)\]")


def _grouped_expander() -> Callable[[str], tuple[str, int]]:
    """The pipeline's own grouped-marker / range expander, imported from the real module.

    `normalize_grouped_markers` splits `[9, 7, 1]` into `[9] [7] [1]` and `[1-3]` into
    `[1] [2] [3]`, leaves `[3,000]` (a numeral) and `[1990-1995]` (a year span) intact, and
    is the definition the writer pipeline renumbers against. A second, subtly different
    parser is how a check like this starts reporting markers that are not there.
    """
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from pipeline.lyra.theo_citations import normalize_grouped_markers

    return normalize_grouped_markers


def _description(site: dict[str, Any]) -> str:
    return site.get("description") or ""


def _citations(site: dict[str, Any]) -> Any:
    """The raw `description_citations` value as stored; None when the row has none."""
    raw = site.get("raw_data")
    if not isinstance(raw, dict):
        return None
    return raw.get("description_citations")


def marker_sequence(text: str) -> list[int]:
    """Every cited number, in reading order, grouped and range forms expanded first.

    Public since 2026-09-23: the Phase-4 verifier (`phase4/verify4.py`, V8) and its acceptance
    read markers with this function, so the census and the writer's checks cannot disagree.
    """
    expanded, _ = _grouped_expander()(text)
    return [int(n) for n in _MARKER_RE.findall(expanded)]


def _distinct_in_order(numbers: list[int]) -> list[int]:
    seen: dict[int, None] = {}
    for n in numbers:
        seen[n] = None
    return list(seen)


def entries(citations: Any, site_id: str) -> list[dict[str, Any]]:
    """The evidence array, validated. Absent or null means "no array" - a normal state.

    Public since 2026-09-23, like `marker_sequence`, for the Phase-4 verifier (V8).

    A value that is not a list of objects carrying an integer `n` is a hole rather than a
    clean site: the marker relation cannot be evaluated, so this raises and the run records
    T08 as errored instead of reporting those sites as passing. Silence here would turn
    "could not check" into "checked and clean".
    """
    if citations is None:
        return []
    if not isinstance(citations, list):
        raise ValueError(
            f"T08: {site_id}: raw_data.description_citations is {type(citations).__name__}, "
            "not a list - cannot evaluate the marker relation"
        )
    checked: list[dict[str, Any]] = []
    for entry in citations:
        n = entry.get("n") if isinstance(entry, dict) else None
        if isinstance(n, bool) or not isinstance(n, int):
            raise ValueError(f"T08: {site_id}: evidence entry without an integer n: {entry!r}")
        checked.append(entry)
    return checked


def _excerpt(text: str, number: int, span: int = 48) -> str:
    """A window of `text` around the first `[number]`, for the evidence quote."""
    needle = f"[{number}]"
    at = text.find(needle)
    if at < 0:
        # The number came out of an expanded group like `[1,2]`, so the literal `[2]` is not
        # in the text. Quoting the whole marker instead of inventing a position.
        return f"marker [{number}] is only present in a grouped/range form"
    lo, hi = max(0, at - span), min(len(text), at + len(needle) + span)
    head = "…" if lo else ""
    tail = "…" if hi < len(text) else ""
    return f"{head}{' '.join(text[lo:hi].split())}{tail}"


def applies_to(site: dict[str, Any], ctx: Context) -> bool:
    """Sites that carry either side of the relation: a marker, or an evidence array.

    Shape is not judged here - `run` does that. This answers only "is there anything to
    look at on this row", so a malformed array still reaches `run` and fails loudly there
    instead of being filed as not-applicable.
    """
    return bool(_citations(site)) or bool(marker_sequence(_description(site)))


def run(ctx: Context) -> list[Finding]:
    findings: list[Finding] = []

    for site in ctx.sites:
        # Kept in step with `applies_to` by construction: `run.py::_aggregate` discards any
        # finding from a site it considers not-applicable, so a finding emitted here for
        # such a site would vanish and leave the site looking clean.
        if not applies_to(site, ctx):
            continue

        sid = str(site["id"])
        text = _description(site)
        array = entries(_citations(site), sid)
        sequence = marker_sequence(text)
        cited = set(sequence)
        declared = [e["n"] for e in array]

        if not cited:
            # Array without markers. Modes 2-4 are all moot here (there is no numbering to
            # check and no entry that a marker could reach), and reporting each of the
            # array's entries as "never cited" on top of this would count the same rows
            # twice under a second label. The plan counts this mode once, as its 76.
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/no-markers",
                    field=ARRAY_FIELD,
                    severity=Severity.MODERATE,
                    dimension=DIMENSION,
                    current_value=declared,
                    proposal=Proposal.REVIEW,
                    confidence=Confidence.UNVERIFIABLE,
                    note=f"the array documents {len(declared)} source(s) but the description "
                    f"cites nothing - the array is stranded. Remedy is a human choice: "
                    f"re-attach the markers, or drop the array",
                    evidence=[
                        Evidence(source=SRC_ARRAY, quote=f"description_citations n={declared}"),
                        Evidence(
                            source=SRC_TEXT,
                            quote=f"{len(text)} chars, no match for "
                            f"r'\\[(\\d+)\\]' after normalize_grouped_markers()",
                        ),
                    ],
                )
            )
            continue

        orphans = sorted(cited - set(declared))
        unreached = sorted(set(declared) - cited)

        if orphans:
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/marker-without-entry",
                    field=TEXT_FIELD,
                    severity=Severity.MODERATE,
                    dimension=DIMENSION,
                    current_value=_distinct_in_order(sequence),
                    proposal=Proposal.REVIEW,
                    confidence=Confidence.UNVERIFIABLE,
                    note=f"the description cites {orphans} with no entry in the array "
                    f"(n={declared}); the reader gets a bare superscript number. Remedy is "
                    f"a human choice: add the missing evidence entry, or drop the claim",
                    evidence=[
                        Evidence(source=SRC_TEXT, quote=_excerpt(text, orphans[0])),
                        Evidence(source=SRC_ARRAY, quote=f"description_citations n={declared}"),
                        Evidence(
                            source=SRC_CONSUMER,
                            quote="cite ? <a href={cite.url}> : <sup>{label}</sup>",
                        ),
                    ],
                )
            )

        if unreached:
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/entry-never-cited",
                    field=ARRAY_FIELD,
                    severity=Severity.COSMETIC,
                    dimension=DIMENSION,
                    current_value=declared,
                    proposal=Proposal.REVIEW,
                    confidence=Confidence.UNVERIFIABLE,
                    note=f"array entries n={unreached} are cited by no marker "
                    f"(cited: {_distinct_in_order(sequence)}); they render nowhere. Remedy "
                    f"is a human choice: cite them, or remove them",
                    evidence=[
                        Evidence(
                            source=SRC_ARRAY,
                            quote=f"description_citations n={declared}; uncited {unreached}",
                        ),
                        Evidence(source=SRC_TEXT, quote=f"markers {_distinct_in_order(sequence)}"),
                    ],
                )
            )

        if cited and cited != set(range(1, len(cited) + 1)):
            expected = set(range(1, len(cited) + 1))
            first_gap = next(n for n in sequence if n not in expected)
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/numbering-gap",
                    field=TEXT_FIELD,
                    severity=Severity.COSMETIC,
                    dimension=DIMENSION,
                    current_value=_distinct_in_order(sequence),
                    proposal=Proposal.REVIEW,
                    confidence=Confidence.UNVERIFIABLE,
                    note=f"the cited numbers are {sorted(cited)}, not 1..{len(cited)}; every "
                    f"marker resolves, but the numbering a reader sees skips. Remedy is a "
                    f"human choice: renumber text and array together",
                    evidence=[
                        Evidence(source=SRC_TEXT, quote=_excerpt(text, first_gap)),
                        Evidence(source=SRC_ARRAY, quote=f"description_citations n={declared}"),
                    ],
                )
            )

    return findings
