"""Lane E, the enrichment (owner decisions D3, D4 and D21 of 2026-10-08, orchestrator decision X1):
the records and the pure core - lane E's provenance, the append composition, the enrichment record, the
invariants of an enriched pair and of its journal evidence, the enrich answer's parser and the frozen
texts. Nothing here calls a model, opens a socket or touches a database. The mutation cases are
`ENRICH_MUTATIONS`.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from wc import answers as A  # noqa: E402 - scripts/remediation is on sys.path by wc_fixtures
from wc import enrich as E  # noqa: E402
from wc import prompts_enrich as PE  # noqa: E402

from tests.remediation import enrich_fixtures as EF
from tests.remediation import wc_fixtures as FX
from tests.remediation import wn_fixtures as WX
from tests.remediation.wc_fixtures import WC4, M

CITATIONS = WX.p4_site_raw()[M.CITATIONS_KEY]
EXISTING = WC4.checked_sentences(WX.P4_TEXT)


def _base() -> WC4.Base:
    return WC4.Base(text=WX.P4_TEXT, citations=tuple(copy.deepcopy(CITATIONS)))


def _kept(*texts: str) -> list[WC4.Decision]:
    return [
        WC4.Decision(n, text, WC4.Verdict.KEEP, None, None) for n, text in enumerate(texts, start=1)
    ]


def _quote(url: str, text: str = "x" * 30) -> WC4.Quote:
    return WC4.Quote(url=url, title="A title", quote=text)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict[str, Any]:
    """The standard four-site scenario, run end to end once."""
    return EF.built(tmp_path_factory.mktemp("enrich"))


# ------------------------------------------------------------------------------ the append
def test_the_base_stays_byte_for_byte_and_the_new_pages_are_numbered_from_n_plus_one() -> None:
    """`compose(..., base=)` is the whole of the enrichment's text: the stored text and its markers
    stay, the citation list keeps the stored entries verbatim (whatever keys they carry) and a new page
    is number N+1, the next N+2, by first appearance."""
    decisions = _kept(EF.FACT, EF.HOOK)
    quotes = {1: [_quote(EF.RESEARCH)], 2: [_quote(EF.POSITIONS), _quote(EF.RESEARCH)]}
    composed = WC4.compose(decisions, quotes, base=_base())
    assert composed.description == (
        f"{WX.P4_TEXT} Spiral reliefs decorate limestone slabs inside the temples [2]. "
        "Whether the south temple's alignment served as a calendar remains undecided [2] [3]."
    )
    assert composed.cites == ((2,), (2, 3))
    assert [c["n"] for c in composed.citations] == [1, 2, 3]
    assert composed.citations[0] == CITATIONS[0]  # verbatim, `license` key and all
    assert set(composed.citations[1]) == {"n", "url", "title", "domain"}
    assert composed.citations[2]["domain"] == "example.edu"  # the host without www


def test_compose_append_is_compose_with_a_base() -> None:
    decisions = _kept(EF.FACT, EF.HOOK)
    quotes = {1: [_quote(EF.RESEARCH)], 2: [_quote(EF.POSITIONS), _quote(EF.RESEARCH)]}
    assert WC4.compose_append(_base(), decisions, quotes) == WC4.compose(
        decisions, quotes, base=_base()
    )


def test_a_page_the_base_already_cites_keeps_its_number() -> None:
    quotes = {1: [_quote(CITATIONS[0]["url"])]}
    composed = WC4.compose(_kept(EF.FACT_PERMALINK), quotes, base=_base())
    assert composed.cites == ((1,),) and len(composed.citations) == 1
    assert composed.description.endswith(
        "Four main structures of the complex stand side by side [1]."
    )


def test_nothing_kept_is_no_description_whatever_the_base_holds() -> None:
    dropped = [WC4.Decision(1, EF.FACT, WC4.Verdict.DROP, None, WC4.DropReason.UNSUPPORTED)]
    composed = WC4.compose(dropped, {}, base=_base())
    assert composed.description is None and composed.cites == ((),)
    assert [c["n"] for c in composed.citations] == [1]


def test_a_plain_compose_is_what_it_was() -> None:
    composed = WC4.compose(_kept(EF.FACT), {1: [_quote(EF.RESEARCH)]})
    assert composed.description == "Spiral reliefs decorate limestone slabs inside the temples [1]."
    assert [c["n"] for c in composed.citations] == [1]


@pytest.mark.parametrize(
    ("text", "citations", "message"),
    [
        (" " + WX.P4_TEXT, CITATIONS, "leading or trailing whitespace"),
        (WX.P4_TEXT[:-1] + " and", CITATIONS, "does not end with"),
        ("The site is old [2]. It is big [1].", [{"n": 1, "url": "u"}, {"n": 2, "url": "v"}],
         "not numbered 1..N by first use"),
        (WX.P4_TEXT, [], "disagree"),
        (WX.P4_TEXT, [{**CITATIONS[0]}, {**CITATIONS[0], "n": 2}], "share one"),
        ("A text without a marker at all in it.", CITATIONS, "disagree"),
    ],
)  # fmt: skip
def test_a_base_whose_markers_and_citations_disagree_is_not_enriched(
    text: str, citations: list, message: str
) -> None:
    problems = WC4.base_problems(text, citations)
    assert any(message in problem for problem in problems), problems
    with pytest.raises(WC4.WcError, match="cannot be enriched"):
        WC4.Base(text=text, citations=tuple(citations))


def test_a_text_without_markers_and_without_citations_is_a_base_numbered_from_one() -> None:
    plain = "The Tarxien Temples are an archaeological complex in Tarxien, Malta."
    base = WC4.Base(text=plain, citations=())
    composed = WC4.compose(_kept(EF.FACT), {1: [_quote(EF.RESEARCH)]}, base=base)
    assert (
        composed.description
        == f"{plain} Spiral reliefs decorate limestone slabs inside the temples [1]."
    )
    assert base.sentences == 1


# ------------------------------------------------------------------------------ lane E's record
def _enriched_raw() -> tuple[dict[str, Any], WC4.Composed]:
    composed = WC4.compose(
        _kept(EF.FACT_PERMALINK, EF.HOOK),
        {1: [_quote(CITATIONS[0]["url"])], 2: [_quote(EF.RESEARCH)]},
        base=_base(),
    )
    return WX.p4_site_raw(), composed


def test_lane_e_keeps_the_phase_4_provenance_and_lists_what_was_added() -> None:
    raw, composed = _enriched_raw()
    provenance = WC4.enriched_provenance(
        raw, composed, base=_base(), ai_system=M.AI_SYSTEM_CLAUDE, marking=WC4.Marking.PHASE4
    )
    data = provenance.to_dict()
    old = raw[M.PROVENANCE_KEY]
    assert data["lane"] == "E" and data["base_lane"] == "W" and data["ai"] == "generated"
    assert data["card"] is None and data["desc_sha256"] == M.text_sha256(composed.description)
    assert (data["sources"], data["sentences"], data["run"]) == (
        old["sources"], old["sentences"], old["run"]
    )  # fmt: skip
    assert data["attribution"] == {
        **old["attribution"],
        "changes": M.Changes.SELECTED_AND_EXTENDED.value,
    }
    # sentence 4 is the first appended (the text had three), cited as the pinned source W; sentence 5
    # cites a page of the web, E<n> for citation n
    assert data["added"] == [
        {"sentence": 4, "n": 1, "src": "W"},
        {"sentence": 5, "n": 2, "src": "E2"},
    ]
    assert M.provenance_from_dict(data) == provenance
    assert M.EnrichedProvenance.from_dict(data).to_json() == provenance.to_json()


def _valid_dict() -> dict[str, Any]:
    raw, composed = _enriched_raw()
    return WC4.enriched_provenance(
        raw, composed, base=_base(), ai_system=M.AI_SYSTEM_CLAUDE, marking=WC4.Marking.PHASE4
    ).to_dict()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"lane": "W"}, "not E|lane"),
        ({"ai": "selected"}, "is not generated"),
        ({"base_lane": "T"}, "not enrichable"),
        ({"base_lane": "E"}, "not enrichable"),
        ({"ai_system": "someone else"}, "ai_system"),
        ({"licence": "restricted"}, "licence"),
        ({"added": []}, "adds at least one"),
        ({"added": [{"sentence": 3, "n": 1, "src": "W"}]}, "one of the 3 sentences"),
        ({"added": [{"sentence": 5, "n": 2, "src": "E2"}, {"sentence": 4, "n": 1, "src": "W"}]},
         "not in sentence order"),
        ({"added": [{"sentence": 4, "n": 1, "src": "D"}]}, "not pinned"),
        ({"added": [{"sentence": 4, "n": 2, "src": "E3"}]}, "must be E2"),
        ({"added": [{"sentence": 4, "n": 1, "src": "R1"}]}, "not pinned"),
        ({"card": {"items": [], "text_sha256": "a" * 64}}, "card"),
        ({"v": 2}, "version"),
        ({"desc_sha256": "x"}, "desc_sha256"),
    ],
)  # fmt: skip
def test_every_field_of_lane_e_s_record_is_held(change: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        M.EnrichedProvenance.from_dict({**_valid_dict(), **change})


def test_the_attribution_changes_note_must_name_the_extension() -> None:
    data = _valid_dict()
    data["attribution"] = {**data["attribution"], "changes": "sentences selected and shortened"}
    with pytest.raises(ValueError, match="changes"):
        M.EnrichedProvenance.from_dict(data)


def test_a_missing_or_foreign_key_is_refused() -> None:
    data = _valid_dict()
    for broken in ({k: v for k, v in data.items() if k != "added"}, {**data, "extra": 1}):
        with pytest.raises(ValueError, match="keys|carries"):
            M.EnrichedProvenance.from_dict(broken)


def test_the_provenance_of_each_marking_is_the_one_its_lane_calls_for() -> None:
    raw, composed = _enriched_raw()
    digest = M.text_sha256(composed.description)
    legacy_raw = {M.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256="a" * 64).to_dict()}
    assert WC4.enriched_provenance(
        legacy_raw, composed, base=_base(), ai_system=M.AI_SYSTEM_CLAUDE, marking=WC4.Marking.L
    ) == M.LegacyProvenance(
        desc_sha256=digest, ai_system=M.legacy_enriched_ai_system(M.AI_SYSTEM_CLAUDE)
    )
    web_raw = {
        M.PROVENANCE_KEY: M.WebProvenance(desc_sha256="a" * 64, ai_system=M.AI_SYSTEM).to_dict()
    }
    web = WC4.enriched_provenance(
        web_raw, composed, base=_base(), ai_system=M.AI_SYSTEM_CLAUDE, marking=WC4.Marking.WEB
    )
    assert isinstance(web, M.WebProvenance) and web.desc_sha256 == digest
    assert (
        web.ai_system == M.AI_SYSTEM
    )  # a MiniMax agent wrote part of the text: the combined string stays
    for marking in (WC4.Marking.UNCLAIMED, WC4.Marking.MARCH, WC4.Marking.NONE):
        with pytest.raises(WC4.WcError, match="not enriched"):
            WC4.enriched_provenance(
                legacy_raw, composed, base=_base(), ai_system=M.AI_SYSTEM_CLAUDE, marking=marking
            )
    with pytest.raises(WC4.WcError, match="carries lane L's provenance"):
        WC4.enriched_provenance(
            raw, composed, base=_base(), ai_system=M.AI_SYSTEM_CLAUDE, marking=WC4.Marking.L
        )


def test_a_march_text_that_was_enriched_names_the_write_that_appended_to_it() -> None:
    plain = M.LegacyProvenance(desc_sha256="a" * 64)
    assert plain.ai_system == M.LEGACY_AI_SYSTEM  # a text nothing was appended to is unchanged
    for system in M.AI_SYSTEMS:
        named = M.legacy_enriched_ai_system(system)
        assert named.startswith(M.LEGACY_AI_SYSTEM) and system in named
        assert (
            M.LegacyProvenance.from_dict({**plain.to_dict(), "ai_system": named}).ai_system == named
        )
    with pytest.raises(ValueError, match="no disclosure"):
        M.legacy_enriched_ai_system("some model")
    with pytest.raises(ValueError, match="legacy_provenance.ai_system"):
        M.LegacyProvenance(desc_sha256="a" * 64, ai_system=M.AI_SYSTEM_CLAUDE)  # no chain named
    with pytest.raises(ValueError, match="legacy_provenance.ai_system"):
        M.LegacyProvenance(
            desc_sha256="a" * 64, ai_system=M.LEGACY_AI_SYSTEM + "; sentences appended by x"
        )


def test_only_a_w_or_s_text_with_aligned_sentences_becomes_lane_e() -> None:
    raw, composed = _enriched_raw()
    short = copy.deepcopy(raw)
    short[M.PROVENANCE_KEY]["sentences"] = short[M.PROVENANCE_KEY]["sentences"][:2]
    with pytest.raises(WC4.WcError, match="cannot be matched one for one"):
        WC4.enriched_provenance(
            short, composed, base=_base(), ai_system=M.AI_SYSTEM_CLAUDE, marking=WC4.Marking.PHASE4
        )
    with pytest.raises(ValueError, match="not enrichable"):
        M.EnrichedProvenance.from_dict({**_valid_dict(), "base_lane": "T"})


def test_the_disclosure_of_two_writes_names_every_model_that_took_part() -> None:
    assert WC4.union_ai_system(M.AI_SYSTEM_OPUS, M.AI_SYSTEM_CLAUDE) == M.AI_SYSTEM_CLAUDE
    assert WC4.union_ai_system(M.AI_SYSTEM, M.AI_SYSTEM_CLAUDE) == M.AI_SYSTEM
    assert (
        WC4.union_ai_system(M.AI_SYSTEM_CLAUDE, M.AI_SYSTEM_CLAUDE_HAIKU)
        == M.AI_SYSTEM_CLAUDE_HAIKU
    )
    with pytest.raises(WC4.WcError, match="no disclosure"):
        WC4.union_ai_system("someone", M.AI_SYSTEM_CLAUDE)


# ------------------------------------------------------------------------------ the record
def _record(**change: Any) -> WC4.DescriptionEnrichment:
    sentences = (
        WC4.EnrichedSentence(1, WC4.FACT, WC4.Verdict.KEEP, None, (2,), ("a" * 64,)),
        WC4.EnrichedSentence(2, WC4.OPEN_QUESTION, WC4.Verdict.KEEP, None, (2, 3), ("b" * 64,)),
    )
    fields: dict[str, Any] = {
        "run": "enrich-test", "writer": M.AI_SYSTEM_CLAUDE, "base_sha256": "c" * 64,
        "base_sentences": 3, "base_citations": 1, "base_check": None, "sentences": sentences,
        "desc_sha256": "d" * 64, "verifiers": ("web_verifier:sonnet-1",),
        "verified_sha256": "d" * 64,
    }  # fmt: skip
    return WC4.DescriptionEnrichment(**{**fields, **change})


def test_the_enrichment_record_round_trips_and_is_strict() -> None:
    record = _record()
    assert WC4.DescriptionEnrichment.from_dict(record.to_dict()) == record
    assert set(record.to_dict()) == WC4._ENRICH_KEYS
    assert record.to_dict()["sentences"][1]["class"] == "open_question"
    with pytest.raises(ValueError, match="keys|carries"):
        WC4.DescriptionEnrichment.from_dict({**record.to_dict(), "extra": 1})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"desc_sha256": "c" * 64, "verified_sha256": "c" * 64}, "nothing was appended"),
        ({"writer": "someone else"}, "writer"),
        ({"verifiers": ("a", "a")}, "distinct agent"),
        ({"verifiers": ()}, "distinct agent"),
        ({"base_sentences": 0}, "base_sentences"),
        ({"base_citations": 0}, "without a gap"),  # the new numbers 2, 3 do not follow 0
        ({"base_check": {"v": 2}}, "keys|carries|check"),
    ],
)
def test_every_field_of_the_enrichment_record_is_held(change: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _record(**change)


def test_the_classes_are_read_in_their_order_and_one_must_stay() -> None:
    hook = WC4.EnrichedSentence(1, WC4.OPEN_QUESTION, WC4.Verdict.KEEP, None, (2,), ("a" * 64,))
    fact = WC4.EnrichedSentence(2, WC4.FACT, WC4.Verdict.KEEP, None, (2,), ("b" * 64,))
    with pytest.raises(ValueError, match="out of order"):
        _record(sentences=(hook, fact))
    gone = WC4.EnrichedSentence(
        1, WC4.FACT, WC4.Verdict.DROP, WC4.DropReason.VERIFY_UNSUPPORTED, (), ()
    )
    with pytest.raises(ValueError, match="none kept"):
        _record(sentences=(gone,))


# ------------------------------------------------------------------------------ built outcomes
def test_the_built_pair_of_every_base_holds_the_lane_s_invariants(built: dict[str, Any]) -> None:
    outcomes = built["outcomes"]
    assert set(outcomes) == {EF.SITE_W, EF.SITE_L, EF.SITE_N}  # the none-found site is not planned
    for site_id, outcome in outcomes.items():
        marking = outcome.evidence["marking"]["old"]
        assert WC4.wc_problems(outcome.description, outcome.raw_data, marking=marking) == []
        assert WC4.evidence_problems(outcome.evidence, outcome.description, outcome.raw_data) == []
        assert WC4.verification_problems(outcome.evidence, outcome.description) == []
        record = outcome.raw_data[WC4.ENRICH_KEY]
        digest = M.text_sha256(outcome.description)
        assert record["desc_sha256"] == record["verified_sha256"] == digest, site_id
        assert WC4.CHECK_KEY not in outcome.raw_data  # the old record moved into the new one
        assert outcome.evidence["decision"] == WC4.EVIDENCE_DECISION_ENRICH


def test_a_checked_march_text_keeps_lane_l_and_its_old_check_record_moves_into_the_new_one(
    built: dict[str, Any],
) -> None:
    outcome = built["outcomes"][EF.SITE_L]
    old = next(r for r in built["rows"] if r["id"] == EF.SITE_L)
    # the public AI system names the March chain that wrote the base and the write that appended
    assert (
        outcome.raw_data[M.PROVENANCE_KEY]
        == M.LegacyProvenance(
            desc_sha256=M.text_sha256(outcome.description),
            ai_system=M.legacy_enriched_ai_system(outcome.evidence["checker"]),
        ).to_dict()
    )
    assert outcome.evidence["checker"] in outcome.raw_data[M.PROVENANCE_KEY]["ai_system"]
    assert outcome.raw_data[WC4.ENRICH_KEY]["base_check"] == old["raw_data"][WC4.CHECK_KEY]
    assert outcome.description.startswith(old["description"] + " ")
    assert outcome.raw_data[M.CITATIONS_KEY][:2] == old["raw_data"][M.CITATIONS_KEY]


def test_a_phase_4_text_becomes_lane_e_and_a_lane_n_text_stays_n(built: dict[str, Any]) -> None:
    w = built["outcomes"][EF.SITE_W].raw_data[M.PROVENANCE_KEY]
    n = built["outcomes"][EF.SITE_N].raw_data[M.PROVENANCE_KEY]
    assert (w["lane"], w["base_lane"], w["ai"]) == ("E", "W", "generated")
    assert (n["lane"], n["ai"]) == ("N", "generated")
    assert n["desc_sha256"] == M.text_sha256(built["outcomes"][EF.SITE_N].description)
    assert w["desc_sha256"] == M.text_sha256(built["outcomes"][EF.SITE_W].description)


def _pair(built: dict[str, Any], site: str = EF.SITE_W) -> tuple[str, dict[str, Any], str]:
    outcome = built["outcomes"][site]
    return (
        outcome.description,
        copy.deepcopy(outcome.raw_data),
        outcome.evidence["marking"]["old"],
    )


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d, r: r[WC4.ENRICH_KEY].update(desc_sha256="e" * 64), "desc_sha256 is not"),
        (lambda d, r: r[WC4.ENRICH_KEY].update(verified_sha256="e" * 64), "verified_sha256"),
        (lambda d, r: r.update({WC4.CHECK_KEY: {}}), "check record beside"),
        (lambda d, r: r.pop(M.PROVENANCE_KEY), "carries its provenance"),
        (lambda d, r: r[M.PROVENANCE_KEY].update(desc_sha256="e" * 64), "provenance's desc_sha256"),
        (lambda d, r: r.update({M.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256=M.text_sha256(d)).to_dict()}),
         "lane-L provenance"),
        (lambda d, r: r[M.CITATIONS_KEY][-1].pop("domain"), "carries"),
        (lambda d, r: r[M.CITATIONS_KEY][-1].update(domain="elsewhere.example"), "is not its host"),
        (lambda d, r: r[M.CITATIONS_KEY].pop(), "disagree"),
        (lambda d, r: r.pop(WC4.ENRICH_KEY), "does not read|check record"),
    ],
)  # fmt: skip
def test_an_enriched_pair_breaks_the_invariants_it_names(
    built: dict[str, Any], edit, message
) -> None:
    description, raw, marking = _pair(built)
    edit(description, raw)
    description_after = description
    problems = WC4.wc_problems(description_after, raw, marking=marking)
    assert any(re.search(message, p) for p in problems), problems


def test_the_markers_of_the_whole_text_are_numbered_by_first_use_and_every_new_one_is_cited(
    built: dict[str, Any],
) -> None:
    description, raw, marking = _pair(built)
    problems = WC4.wc_problems(description.replace("[2]", "[7]"), raw, marking=marking)
    assert any("not numbered 1..N" in p or "disagree" in p for p in problems)
    raw[WC4.ENRICH_KEY]["sentences"][0]["cites"] = [1]
    raw[WC4.ENRICH_KEY]["sentences"][1]["cites"] = [1]
    problems = WC4.wc_problems(description, raw, marking=marking)
    assert any("markers beyond the base's" in p for p in problems), problems


def test_the_journal_evidence_composes_the_text_and_every_edit_of_it_is_found(
    built: dict[str, Any],
) -> None:
    outcome = built["outcomes"][EF.SITE_W]
    evidence, description, raw = outcome.evidence, outcome.description, outcome.raw_data
    assert WC4.evidence_problems(evidence, description, raw) == []
    problems = WC4.evidence_problems(evidence, description + " Another sentence.", raw)
    assert any("not what the journal evidence composes" in p for p in problems)
    edited = copy.deepcopy(raw)
    edited[M.PROVENANCE_KEY]["added"] = edited[M.PROVENANCE_KEY]["added"][:1]
    assert any("added list" in p for p in WC4.evidence_problems(evidence, description, edited))
    other = copy.deepcopy(raw)
    other[M.CITATIONS_KEY][0]["url"] = "https://example.org/other"
    assert any("citations" in p for p in WC4.evidence_problems(evidence, description, other))
    forged = copy.deepcopy(raw)
    forged[WC4.ENRICH_KEY]["sentences"][0]["class"] = "open_question"
    assert any(
        "enrichment record" in p for p in WC4.evidence_problems(evidence, description, forged)
    )


def test_the_acceptance_holds_the_base_the_writer_and_the_disclosure_to_the_evidence(
    built: dict[str, Any],
) -> None:
    for site in (EF.SITE_W, EF.SITE_L, EF.SITE_N):
        outcome = built["outcomes"][site]
        evidence, description = outcome.evidence, outcome.description

        def problems(raw=None, ev=None):
            return WC4.evidence_problems(ev or evidence, description, raw or outcome.raw_data)

        assert problems() == []
        # a record whose writer is not the models that answered (D6: the stamp names the real model)
        forged = copy.deepcopy(outcome.raw_data)
        forged[WC4.ENRICH_KEY]["writer"] = M.AI_SYSTEM
        assert any("enrichment record" in p for p in problems(forged)), site
        # a public AI system that does not name the write that appended (Opus alone does not name
        # the Sonnet agent that wrote the sentences; the bare March chain names no write at all)
        other = copy.deepcopy(outcome.raw_data)
        other[M.PROVENANCE_KEY]["ai_system"] = (
            M.LEGACY_AI_SYSTEM if site == EF.SITE_L else M.AI_SYSTEM_OPUS
        )
        assert any("ai_system" in p for p in problems(other)), site
        # a base that is not the text the question asked
        edited = copy.deepcopy(evidence)
        edited[WC4.ENRICH_EVIDENCE_KEY]["base"]["text"] += " Extra words."
        assert any("base text is not the stored text" in p for p in problems(ev=edited)), site


def test_the_evidence_of_an_enrichment_carries_the_enrichment_block_and_no_other_does(
    built: dict[str, Any],
) -> None:
    outcome = built["outcomes"][EF.SITE_W]
    evidence = outcome.evidence
    assert set(evidence) == WC4.ENRICH_EVIDENCE_KEYS
    assert set(evidence[WC4.ENRICH_EVIDENCE_KEY]) == WC4._ENRICH_DETAIL_KEYS
    assert evidence["marking"]["enriched"] is True
    short = {k: v for k, v in evidence.items() if k != WC4.ENRICH_EVIDENCE_KEY}
    with pytest.raises(ValueError, match="evidence carries"):
        WC4.WcOutcome(outcome.site_id, outcome.description, outcome.raw_data, short)
    assert WC4.evidence_keys({"decision": WC4.EVIDENCE_DECISION}) == WC4.EVIDENCE_KEYS


def test_the_verifier_was_shown_the_whole_text_so_its_round_records_the_new_texts_hash(
    built: dict[str, Any],
) -> None:
    outcome = built["outcomes"][EF.SITE_W]
    rounds = outcome.evidence[WC4.VERIFICATION_KEY]["rounds"]
    assert rounds[-1]["text_sha256"] == M.text_sha256(outcome.description)
    decisions, quotes = WC4.decisions_of(outcome.evidence)
    base = WC4.base_of(outcome.evidence)
    assert WC4.compose(decisions, quotes, base=base).description == outcome.description
    # without the base the same rounds are not a verification of what they showed
    given = [{key: r[key] for key in WC4.ROUND_KEYS} for r in rounds]
    with pytest.raises(WC4.WcError, match="verified the text of sha256"):
        WC4.run_verification(decisions, quotes, given)
    assert WC4.run_verification(decisions, quotes, given, base=base)[2] is WC4.VerifyStatus.VERIFIED


@pytest.mark.parametrize("site", [EF.SITE_W, EF.SITE_L, EF.SITE_N])
@pytest.mark.parametrize("listed", [False, True])
def test_an_enriched_text_is_never_asked_again_by_a_check_or_a_list_run(
    built: dict[str, Any], site: str, listed: bool
) -> None:
    outcome = built["outcomes"][site]
    stored = FX.plan_site(FX.row(site, outcome.description, raw_data=outcome.raw_data))
    with pytest.raises(WC4.WcError, match="neither a check nor a list run"):
        WC4.old_marking(stored, listed=listed)


# ------------------------------------------------------------------------------ the answer
def _parse(
    text: str, *, existing: Sequence[str] = EXISTING, max_facts: int = 3, dispute: bool = False
):
    return A.parse_enrich(
        text, site_id=EF.SITE_W, existing=existing, max_facts=max_facts, dispute=dispute
    )


def test_a_good_answer_is_a_fact_and_the_hook_in_that_order() -> None:
    parsed = _parse(EF.good(EF.SITE_W))
    assert [s.kind for s in parsed.sentences] == ["fact", "open_question"]
    assert [a.n for a in parsed.as_check()] == [1, 2]
    assert all(a.verdict is WC4.Verdict.KEEP for a in parsed.as_check())


def test_no_sentence_at_all_is_an_answer_and_leaves_the_site_as_it_is() -> None:
    assert _parse(EF.nothing(EF.SITE_W)).sentences == ()


def _fact(text: str = EF.FACT) -> dict:
    return EF.sentence("fact", text, EF.Q_FACT)


def _hook(text: str = EF.HOOK) -> dict:
    return EF.sentence("open_question", text, EF.Q_HOOK)


def _answer(*sentences: dict) -> str:
    return EF.answer(EF.SITE_W, *sentences)


@pytest.mark.parametrize(
    ("sentences", "kwargs", "message"),
    [
        ([_hook(), _fact()], {}, "not in the order"),
        ([_fact()], {"max_facts": 0}, "may take 0"),
        ([_hook(), _hook("Whether the temples served a calendar is still debated by scholars.")],
         {}, "open questions|not in the order"),
        ([{**_fact(), "class": "story"}], {}, "class 'story'"),
        ([EF.sentence("dispute_a", EF.POSITION_A, EF.Q_A)], {"dispute": True}, "both positions"),
        ([EF.sentence("dispute_a", EF.POSITION_A, EF.Q_A),
          EF.sentence("dispute_b", EF.POSITION_B, EF.Q_B)], {}, "no dispute brief"),
        ([_fact()], {"dispute": True}, "has a dispute brief"),
        ([_fact(EXISTING[0])], {}, "repeats a sentence the description has"),
        ([_fact(EXISTING[1].upper())], {}, "repeats a sentence the description has"),
        ([_fact(), _fact()], {}, "written twice|repeats"),
    ],
)  # fmt: skip
def test_an_enrich_answer_the_rules_refuse(sentences: list, kwargs: dict, message: str) -> None:
    with pytest.raises(A.AnswerError, match=message):
        _parse(_answer(*sentences), **kwargs)


def test_the_dispute_pair_is_accepted_for_a_site_with_a_brief_and_in_its_order() -> None:
    pair = [
        EF.sentence("dispute_a", EF.POSITION_A, EF.Q_A),
        EF.sentence("dispute_b", EF.POSITION_B, EF.Q_B),
    ]
    parsed = _parse(_answer(_fact(), *pair, _hook()), dispute=True)
    assert [s.kind for s in parsed.sentences] == ["fact", "dispute_a", "dispute_b", "open_question"]
    with pytest.raises(A.AnswerError, match="not in the order"):
        _parse(_answer(pair[1], pair[0]), dispute=True)


def test_the_added_text_and_the_hook_have_their_lengths() -> None:
    long_fact = (
        "Archaeologists recorded " + "weathered carved spiral reliefs " * 4 + "on the slabs."
    )
    assert 150 < len(long_fact) <= A.MAX_SENTENCE_CHARS
    three = [
        _fact(long_fact.replace("recorded", word))
        for word in ("recorded", "documented", "measured")
    ]
    assert sum(len(s["text"]) for s in three) > A.MAX_ADDED_CHARS
    with pytest.raises(A.AnswerError, match="characters added; at most 450"):
        _parse(_answer(*three))
    long_hook = (
        "Whether the alignment of the south temple, built and rebuilt by generations of "
        "unknown builders whose names and methods were never written down and whose tools and "
        "quarries have only in part been found, served as a calendar or a ritual guide, remains "
        "undecided today."
    )
    assert A.MAX_HOOK_CHARS < len(long_hook) <= A.MAX_SENTENCE_CHARS
    with pytest.raises(A.AnswerError, match="open question is .* characters, at most 220"):
        _parse(_answer(_hook(long_hook)))


def test_every_sentence_is_a_write_answers_sentence() -> None:
    copied = _hook(
        "Scholars have not settled whether the alignment of the south temple served as a "
        "calendar, apparently."
    )
    with pytest.raises(A.AnswerError, match="shares a run of 12 words"):
        _parse(_answer(copied))
    with pytest.raises(A.AnswerError, match="citation marker"):
        _parse(_answer(_fact(EF.FACT[:-1] + " [1].")))
    with pytest.raises(A.AnswerError, match="pronoun"):
        _parse(_answer(_fact("They decorate limestone slabs inside the temples of Tarxien.")))
    with pytest.raises(A.AnswerError, match="names site"):
        A.parse_enrich(EF.good(EF.SITE_W), site_id=EF.SITE_L, existing=EXISTING, max_facts=3,
                       dispute=False)  # fmt: skip
    payload = json.loads(EF.good(EF.SITE_W))
    del payload["sentences"][0]["class"]
    with pytest.raises(A.AnswerError, match="carries"):
        _parse(json.dumps(payload))


def test_a_sentence_that_shares_a_run_of_twelve_words_with_a_sentence_the_text_has_is_a_repeat() -> (
    None
):
    long_existing = (
        "The ancient temple complex stands on a low hill above the small town of Tarxien in Malta.",
    )
    near_copy = _fact(
        "The ancient temple complex stands on a low hill above the small town, and spiral reliefs "
        "decorate its limestone slabs."
    )
    with pytest.raises(A.AnswerError, match="repeats a sentence the description has"):
        _parse(_answer(near_copy), existing=long_existing)
    _parse(_answer(_fact()), existing=long_existing)  # a different fact is fine


def test_the_judge_may_find_only_an_open_question_invented() -> None:
    answer = {
        "site_id": "s",
        "kept": [
            {"k": 1, "verdict": "SUPPORTED", "quotes": [], "note": "ok"},
            {"k": 2, "verdict": "INVENTED", "quotes": [], "note": "no source calls it open"},
        ],
        "dropped": [],
        "coherent": True,
        "note": "ok",
    }
    parsed = A.parse_judge(json.dumps(answer), site_id="s", kept=2, dropped=0, hooks=[2])
    assert parsed.kept[1].verdict == "INVENTED"
    with pytest.raises(A.AnswerError, match="INVENTED is a verdict of an open question only"):
        A.parse_judge(json.dumps(answer), site_id="s", kept=2, dropped=0, hooks=[1])
    with pytest.raises(A.AnswerError, match="not one of"):
        A.parse_judge(json.dumps(answer), site_id="s", kept=2, dropped=0)


# ------------------------------------------------------------------------------ the texts
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: The frozen texts of lane E, pinned by their bytes: a changed question makes every exported answer
#: stale (`opus_handoff.validate`), so a change is a new pin and a new export, never an edit under a
#: running round.
TEXT_PINS = {
    "ENRICH_QUESTION": "6348b5f135ff309d8ba1cbf4ce47e41bad7079f8fbbd620879cf6e9b3e4fc867",
    "VERIFY_QUESTION_ENRICH": "512e29bbae04577fa34c6082cd02d395c7902e455bb3029c9e0c9d100854c85f",
    "JUDGE_QUESTION_ENRICH": "56283b5ceee543722d8450e1721d6d456e98e79b01ca9d05606cfeb95cc7ad09",
    "DISPUTE_BLOCK": "8510fdf6d1eb88b07e22b45ddd62d6d2fed2c085810a17eeefaa3b9f0d4e1ef8",
    "CLASS_FACT_THIN": "dabf3273f7efcf01a00d1a5ef25885bb8cb399f8188906b9309d11c8b1c8e145",
    "CLASS_FACT_NONE": "f423ed664f530038a6765915340fabbc76f37e11ca846dd743bad7a431d43452",
    "CLASS_HOOK": "358c8778b3fe03a01d13f19352ddc7fcc42fd804f8ce905da7629ec7eec6564e",
    "ENRICH_BRIEF": "01925056f30d0f9202557b9d5ae01b4d5569d01932d4c807d1fcadf62be48196",
    "VERIFY_BRIEF_ENRICH": "140cfab9b60f7e278613bbbcd8e376c31f6620f31a4f144fb1825b1e39a535f5",
    "JUDGE_BRIEF_ENRICH": "6d511931c8724c603137828c3fb503e4550d098d6c04b564bc202967158217d0",
}


def test_the_frozen_texts_of_lane_e_are_pinned() -> None:
    assert {name: _sha(getattr(PE, name)) for name in TEXT_PINS} == TEXT_PINS


def test_the_earlier_questions_are_not_touched() -> None:
    """`prompts.py` and `prompts_sonnet.py` are the pinned texts of the runs in flight; lane E derives
    from them by exact replacement or adds its own file."""
    from wc import prompts as P
    from wc import prompts_sonnet as P2

    assert PE.VERIFY_BRIEF_ENRICH != P.VERIFY_BRIEF and PE.JUDGE_BRIEF_ENRICH != P.JUDGE_BRIEF
    assert "lane E" not in P2.WRITE_BRIEF and "lane E" in PE.ENRICH_BRIEF


def test_each_brief_records_its_answer_in_the_role_d6_registers() -> None:
    import roles

    for text, role in (
        (PE.ENRICH_BRIEF, PE.WRITER_ROLE),
        (PE.VERIFY_BRIEF_ENRICH, PE.VERIFIER_ROLE),
        (PE.JUDGE_BRIEF_ENRICH, PE.JUDGE_ROLE),
    ):
        assert f"--role {role} --model {roles.role(role).model}" in text
        assert (
            "<the model id you run as" not in text
        )  # the brief names the model, the agent chooses none


def _entry(**change: Any) -> dict[str, Any]:
    site = FX.plan_site(FX.row(EF.SITE_W, WX.P4_TEXT, raw_data=WX.p4_site_raw()))
    entry = {
        "site_id": EF.SITE_W, "name": site.name, "marking": "phase4", "plan_site": site.to_dict(),
        **E.entry_extras(site, EXISTING),
    }  # fmt: skip
    return {**entry, **change}


def test_the_question_names_the_classes_a_site_may_take() -> None:
    thin = E.enrich_prompt(_entry(), site="THE SITE BLOCK")
    assert "up to 3 sentences" in thin and "open_question: at most one sentence" in thin
    assert "S1: The Tarxien Temples are an archaeological complex in Tarxien, Malta." in thin
    assert "THE SITE BLOCK" in thin and "THIS SITE IS DISPUTED" not in thin
    long = E.enrich_prompt(_entry(thin=False), site="s")
    assert "fact: none. This description is long enough" in long and "up to 3 sentences" not in long


def test_a_dispute_brief_puts_both_positions_and_their_sources_in_the_question() -> None:
    record = {
        "site_id": EF.SITE_W, "name": "Tarxien", "desc_sha256": "a" * 64, "verdict": "dispute",
        "position_a": {"claim": "The first phase is near 3600 BC", "holders": "the excavators",
                       "sources": [{"url": EF.POSITIONS, "title": "Dating Tarxien",
                                    "quote": "Excavators place the first phase near 3600 BC."}]},
        "position_b": {"claim": "The first phase is near 3150 BC", "holders": "radiocarbon specialists",
                       "sources": [{"url": EF.POSITIONS, "title": "Dating Tarxien",
                                    "quote": "Radiocarbon specialists argue that the first phase belongs near 3150 BC."}]},
        "asserting": [], "note": "a documented controversy", "researched_by": "r", "adjudicated_by": "a",
    }  # fmt: skip
    assert E.dispute_record_problems(record) == []
    prompt = E.enrich_prompt(_entry(dispute=record), site="s")
    assert (
        "THIS SITE IS DISPUTED" in prompt
        and "POSITION A: The first phase is near 3600 BC" in prompt
    )
    assert "held by: radiocarbon specialists" in prompt and EF.POSITIONS in prompt
    for broken, message in (
        ({**record, "verdict": "settled"}, "verdict"),
        ({**record, "position_a": {**record["position_a"], "sources": []}}, "names no source"),
        ({**record, "position_b": {"claim": "x"}}, "position_b"),
        (
            {**record, "asserting": [{"sentence": 0, "asserts": "a", "text": "x"}]},
            "asserting entry",
        ),
        ({k: v for k, v in record.items() if k != "note"}, "carries"),
    ):
        assert any(message in p for p in E.dispute_record_problems(broken)), message


def test_the_classification_lists_a_text_under_the_reason_it_is_not_asked(
    built: dict[str, Any], tmp_path
) -> None:
    def classify(description, raw, **kwargs):
        site = FX.plan_site(FX.row(EF.SITE_W, description, raw_data=raw))
        return E.classify(
            site, excluded=kwargs.get("excluded", set()), earlier=kwargs.get("earlier", set())
        )

    raw = WX.p4_site_raw()
    assert classify(WX.P4_TEXT, raw)[0:2] == (None, "phase4")
    assert classify("", None)[0] == "no-description"
    assert classify(WX.P4_TEXT, None)[0] == "no-provenance"
    assert classify(WX.P4_TEXT + " Edited.", raw)[0] == "provenance-hash-differs"
    assert (
        classify(WX.P4_TEXT, {**raw, M.PROVENANCE_KEY: {"lane": "W"}})[0] == "provenance-unreadable"
    )
    old = M.Provenance.from_dict(raw[M.PROVENANCE_KEY])
    translated = dataclasses.replace(
        old,
        lane=M.Lane.T,
        ai=M.AiMark.GENERATED,
        attribution=dataclasses.replace(old.attribution, changes=M.Changes.TRANSLATED),
        desc_sha256=M.text_sha256(WX.P4_TEXT),
    )
    assert classify(WX.P4_TEXT, {**raw, M.PROVENANCE_KEY: translated.to_dict()})[0] == (
        "phase4-lane-not-enrichable"
    )
    assert classify(WX.P4_TEXT, raw, excluded={EF.SITE_W})[0] == "excluded"
    assert classify(WX.P4_TEXT, raw, earlier={EF.SITE_W})[0] == "earlier-run"
    broken = copy.deepcopy(raw)
    broken[M.CITATIONS_KEY] = []
    assert classify(WX.P4_TEXT, broken)[0] == "base-not-enrichable"
    # an unchecked March text is no basis: its sentences would sit beside the new ones unverified
    march = FX.legacy_raw(FX.TEXT_A)
    assert (
        classify(FX.TEXT_A, march)[0] == "base-not-enrichable"
        or classify(FX.TEXT_A, march)[0] == "unchecked-text"
    )
    done = built["outcomes"][EF.SITE_W]
    assert classify(done.description, done.raw_data)[0] == "enriched-before"


def test_a_checked_march_text_and_a_lane_n_text_are_asked_under_their_marking(
    built: dict[str, Any],
) -> None:
    rows = {r["id"]: r for r in built["rows"]}
    for site_id, marking in ((EF.SITE_L, "L"), (EF.SITE_N, "web")):
        row = rows[site_id]
        site = FX.plan_site(row)
        assert E.classify(site, excluded=set(), earlier=set())[0:2] == (None, marking)
    unchecked = copy.deepcopy(rows[EF.SITE_L]["raw_data"])
    del unchecked[WC4.CHECK_KEY]
    site = FX.plan_site(FX.row(EF.SITE_L, rows[EF.SITE_L]["description"], raw_data=unchecked))
    assert E.classify(site, excluded=set(), earlier=set())[0] == "unchecked-text"
    stale = copy.deepcopy(rows[EF.SITE_L]["raw_data"])
    stale[WC4.CHECK_KEY]["verified_sha256"] = "f" * 64
    site = FX.plan_site(FX.row(EF.SITE_L, rows[EF.SITE_L]["description"], raw_data=stale))
    assert E.classify(site, excluded=set(), earlier=set())[0] == "unchecked-text"
