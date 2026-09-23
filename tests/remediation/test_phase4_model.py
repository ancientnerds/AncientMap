"""Do the Phase-4/5 contracts (WB-00) spell the design's records exactly and refuse malformed ones?

`scripts/remediation/phase4/model4.py` is what the four tracks code against: sources (A),
selection (B), checking (C) and write (D). The mistakes worth a test are the silent ones - a key the
writer adds that the design never named, a lane published under the wrong AI mark, a drop range
that leaves its sentence, a `True` read as citation number 1, a selector answer with a card the
description does not carry. Each guard in `model4` has a test here that fails when the guard is
removed; the mutation cases are in `scripts/remediation/phase3/mutation_sweep.py`
(`PHASE4_MODEL_MUTATIONS`).

The schema literals below are copied from the design (entry [6] of
`output/remediation/logs/design_texts_images_2026-09-22.json`, section production_write), not
from `model4`, so a change to the module cannot move the expectation with it. Nothing here opens a
socket, calls a model or touches a database.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

from phase3 import model_stage as MS  # noqa: E402
from phase4 import model4 as M  # noqa: E402

DESIGN = REPO / "output" / "remediation" / "logs" / "design_texts_images_2026-09-22.json"

PERMALINK = "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567"
HEX_TEXT = M.text_sha256("the pinned text")
HEX_DESC = M.text_sha256("the description")
HEX_CARD = M.text_sha256("the card")

#: production_write, "_description_provenance v1" - the keys, verbatim.
PROVENANCE_KEYS = {
    "v",
    "run",
    "lane",
    "ai",
    "ai_system",
    "licence",
    "attribution",
    "sources",
    "sentences",
    "card",
    "desc_sha256",
}
ATTRIBUTION_KEYS = {"title", "url", "licence_url", "changes"}
SOURCE_KEYS = {"id", "url", "revid", "rev_timestamp", "text_sha256", "licence"}
SENTENCE_KEYS = {"n", "src", "start", "end", "drop"}
CARD_KEYS = {"items", "text_sha256"}
CARD_ITEM_KEYS = {"sentence", "drop"}
#: production_write, row group L.
LEGACY_KEYS = {"v", "lane", "ai", "ai_system", "basis", "desc_sha256"}
#: writer, ASSEMBLY: the existing DescriptionCitation shape plus `license`, without `claim`.
CITATION_KEYS = {"n", "url", "title", "domain", "license"}


# ------------------------------------------------------------------------------------------------
# Samples (fresh dicts per call, so a test can break one without touching the next)
# ------------------------------------------------------------------------------------------------


def _provenance_dict() -> dict[str, Any]:
    return {
        "v": 1,
        "run": "pilot-20260922",
        "lane": "W",
        "ai": "selected",
        "ai_system": "opencode-go/deepseek-v4.1-flash via Pi (an-sites-remediation-2026-09)",
        "licence": "CC BY-SA 4.0",
        "attribution": {
            "title": "Tarxien Temples",
            "url": PERMALINK,
            "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "changes": "sentences selected and shortened",
        },
        "sources": [
            {
                "id": "W",
                "url": PERMALINK,
                "revid": 1234567,
                "rev_timestamp": "2026-09-01T10:00:00Z",
                "text_sha256": HEX_TEXT,
                "licence": "CC BY-SA 4.0",
            }
        ],
        "sentences": [
            {"n": 1, "src": "W", "start": 0, "end": 80, "drop": [[50, 79]]},
            {"n": 1, "src": "W", "start": 81, "end": 160, "drop": []},
        ],
        "card": {"items": [{"sentence": 0, "drop": [[20, 30], [50, 79]]}], "text_sha256": HEX_CARD},
        "desc_sha256": HEX_DESC,
    }


def _r_provenance_dict() -> dict[str, Any]:
    """Lane R: two restricted pages, cited as [1] and [2]; no revision, no card."""
    return {
        "v": 1,
        "run": "pilot-20260922",
        "lane": "R",
        "ai": "generated",
        "ai_system": M.AI_SYSTEM,
        "licence": "CC BY-SA 4.0",
        "attribution": {
            "title": "Hatunmarka - site page",
            "url": "https://example.org/hatunmarka",
            "licence_url": M.PUBLISHED_LICENCE_URL,
            "changes": "facts restated",
        },
        "sources": [
            {
                "id": "R1",
                "url": "https://example.org/hatunmarka",
                "revid": None,
                "rev_timestamp": None,
                "text_sha256": HEX_TEXT,
                "licence": "restricted",
            },
            {
                "id": "R2",
                "url": "https://example.net/andes",
                "revid": None,
                "rev_timestamp": None,
                "text_sha256": HEX_TEXT,
                "licence": "restricted",
            },
        ],
        "sentences": [
            {"n": 1, "src": "R1", "start": 10, "end": 90, "drop": []},
            {"n": 2, "src": "R2", "start": 5, "end": 70, "drop": []},
            {"n": 1, "src": "R1", "start": 200, "end": 260, "drop": []},
        ],
        "card": None,
        "desc_sha256": HEX_DESC,
    }


def _legacy_dict() -> dict[str, Any]:
    return {
        "v": 1,
        "lane": "L",
        "ai": "generated",
        "ai_system": "2026-03 enrichment chain (LLM; model per site not recorded)",
        "basis": "description differs from pre-March snapshot d4526691 (plan section 15.3)",
        "desc_sha256": HEX_DESC,
    }


def _plan_site_dict() -> dict[str, Any]:
    return {
        "site_id": "4a5a324f-0000-4000-8000-000000000001",
        "name": "Tarxien Temples",
        "aliases": ["Templos de Tarxien"],
        "country": "Malta",
        "site_type": "Temple",
        "period_start": -3150,
        "period_end": None,
        "lat": 35.8692,
        "lon": 14.5122,
        "description": "The description.",
        "description_sha256": M.text_sha256("The description."),
        "raw_data": {"description_citations": [{"n": 1, "url": PERMALINK}]},
        "raw_data_sha256": HEX_TEXT,
        "card": "A card.",
        "card_sha256": M.text_sha256("A card."),
        "source_url": "https://en.wikipedia.org/wiki/Tarxien_Temples",
        "wikidata_qid": "Q1195938",
        "enwiki_title": "Tarxien Temples",
        "in_snapshot": True,
        "snapshot_description": None,
        "flags": ["cleared-card-defect", "shared-title"],
    }


def _source_doc_dict() -> dict[str, Any]:
    return {
        "id": "W",
        "url": "https://en.wikipedia.org/w/api.php?action=query&titles=Tarxien%20Temples",
        "permalink": PERMALINK,
        "title": "Tarxien Temples",
        "pageid": 1843961,
        "revid": 1234567,
        "lastrevid": 1234567,
        "rev_timestamp": "2026-09-01T10:00:00Z",
        "retrieved_at": "2026-09-23T08:00:00Z",
        "sha256_raw": HEX_TEXT,
        "sha256_text": HEX_TEXT,
        "licence": "CC BY-SA 4.0",
        "route": "enwiki_title",
        "subject_gate": {
            "qid_match": True,
            "shared": False,
            "concept": False,
            "place_item": False,
            "km": 0.12,
            "name_score": 100.0,
            "verdict": "own",
        },
        "tdm": None,
        "final_url": None,
        "truncated": None,
    }


def _r_source_doc_dict() -> dict[str, Any]:
    return {
        **_source_doc_dict(),
        "id": "R1",
        "url": "https://example.org/hatunmarka",
        "permalink": None,
        "pageid": None,
        "revid": None,
        "lastrevid": None,
        "rev_timestamp": None,
        "licence": "restricted",
        "route": "minimax",
        "subject_gate": None,
        "tdm": {"checked": True, "reserved": False, "signal": None},
        "final_url": "https://example.org/hatunmarka/",
        "truncated": False,
    }


def _sentence_dict() -> dict[str, Any]:
    return {
        "src": "W",
        "index": 12,
        "section": "History",
        "start": 100,
        "end": 170,
        "spans": [
            {"id": "a1", "kind": "a", "start": 145, "end": 169},
            {"id": "p1", "kind": "p", "start": 120, "end": 131},
        ],
    }


def _selection_dict() -> dict[str, Any]:
    return {
        "site_id": "4a5a324f",
        "desc": [{"sid": "W3", "drop": []}, {"sid": "W12", "drop": ["a1"]}],
        "card": [{"sid": "W12", "drop": ["p1"]}],
        "abstain": None,
    }


def _assembly_dict() -> dict[str, Any]:
    return {
        "site_id": "4a5a324f",
        "description": "The Tarxien Temples are a megalithic complex [1]. They date to 3150 BC [1].",
        "citations": [
            {
                "n": 1,
                "url": PERMALINK,
                "title": "Wikipedia: Tarxien Temples",
                "domain": "en.wikipedia.org",
                "license": "CC BY-SA 4.0",
            }
        ],
        "card": "The Tarxien Temples are a megalithic complex.",
        "provenance": _provenance_dict(),
    }


def _refused(build: Any, data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        build(data)


# ------------------------------------------------------------------------------------------------
# The exact shape of provenance v1
# ------------------------------------------------------------------------------------------------


def test_provenance_json_is_the_production_write_schema_exactly() -> None:
    record = M.Provenance.from_dict(_provenance_dict())
    written = json.loads(record.to_json())

    assert set(written) == PROVENANCE_KEYS
    assert set(written["attribution"]) == ATTRIBUTION_KEYS
    assert all(set(source) == SOURCE_KEYS for source in written["sources"])
    assert all(set(sentence) == SENTENCE_KEYS for sentence in written["sentences"])
    assert set(written["card"]) == CARD_KEYS
    assert all(set(item) == CARD_ITEM_KEYS for item in written["card"]["items"])
    # The whole object, value for value, in the writer's serialisation (sorted keys, no escapes).
    assert written == _provenance_dict()
    assert record.to_json() == json.dumps(_provenance_dict(), ensure_ascii=False, sort_keys=True)


def test_legacy_provenance_is_the_production_write_shape_exactly() -> None:
    record = M.LegacyProvenance(desc_sha256=HEX_DESC)
    assert set(record.to_dict()) == LEGACY_KEYS
    assert record.to_dict() == _legacy_dict()
    assert M.LegacyProvenance.from_dict(_legacy_dict()) == record


def test_a_citation_is_the_description_citation_shape_plus_license_without_claim() -> None:
    citation = M.Citation.from_dict(_assembly_dict()["citations"][0])
    assert set(citation.to_dict()) == CITATION_KEYS
    stale = {**_assembly_dict()["citations"][0], "claim": "a claim"}
    _refused(M.Citation.from_dict, stale, "unknown keys \\['claim'\\]")


def test_the_raw_data_keys_are_the_ones_the_frontend_reads_and_skips() -> None:
    # sourceFields.ts skips an object key with a leading underscore; the citations key is the
    # existing one that CitationText, the exporter's `dc` and library_aggregator read.
    assert M.PROVENANCE_KEY == "_description_provenance"
    assert M.CITATIONS_KEY == "description_citations"


def test_every_record_round_trips_through_its_json(tmp_path: Path) -> None:
    samples: list[M._JsonRecord] = [
        M.PlanSite.from_dict(_plan_site_dict()),
        M.SourceDoc.from_dict(_source_doc_dict()),
        M.SourceDoc.from_dict(_r_source_doc_dict()),
        M.LaneAssignment(site_id="s", lane=M.Lane.W, sources=("W",), detail="own article"),
        M.Sentence.from_dict(_sentence_dict()),
        M.Selection.from_dict(_selection_dict()),
        M.Selection(site_id="s", desc=(), card=(), abstain="no sentence is about this site"),
        M.Provenance.from_dict(_provenance_dict()),
        M.Provenance.from_dict(_r_provenance_dict()),
        M.LegacyProvenance.from_dict(_legacy_dict()),
        M.Assembly.from_dict(_assembly_dict()),
        M.Hold(site_id="s", scope=M.HoldScope.SITE, reason=M.HoldReason.V9, detail="180 < 200"),
    ]
    for record in samples:
        again = type(record).from_json(record.to_json())
        assert again == record
        assert again.to_json() == record.to_json()

    holds = [
        M.Hold(site_id=f"s{i}", scope=M.HoldScope.CARD, reason=M.HoldReason.V10, detail="country")
        for i in range(3)
    ]
    path = tmp_path / M.HOLDS_FILE
    path.write_text(M.dump_jsonl(holds), encoding="utf-8", newline="\n")
    assert M.load_jsonl(path, M.Hold) == holds


def test_an_unknown_key_is_refused_not_dropped() -> None:
    data = {**_provenance_dict(), "quote": "the verbatim sentence"}
    _refused(M.Provenance.from_dict, data, "unknown keys \\['quote'\\]")


def test_a_missing_key_is_refused_even_when_its_value_would_be_null() -> None:
    data = _provenance_dict()
    del data["card"]
    _refused(M.Provenance.from_dict, data, "missing keys \\['card'\\]")


def test_nan_and_infinity_are_not_json() -> None:
    text = json.dumps(_plan_site_dict()).replace("35.8692", "NaN")
    with pytest.raises(ValueError, match="NaN is not JSON"):
        M.PlanSite.from_json(text)


def test_a_bool_is_never_an_int() -> None:
    data = _provenance_dict()
    data["sentences"][0]["n"] = True
    _refused(M.Provenance.from_dict, data, "True is not an integer")
    data = _provenance_dict()
    data["v"] = True
    _refused(M.Provenance.from_dict, data, "is not version 1")


@pytest.mark.parametrize(
    ("build", "data", "key", "value"),
    [
        (M.Provenance.from_dict, _provenance_dict, "lane", "X"),
        (M.Provenance.from_dict, _provenance_dict, "licence", "CC BY 4.0"),
        (M.SourceDoc.from_dict, _source_doc_dict, "route", "google"),
        (M.PlanSite.from_dict, _plan_site_dict, "flags", ["pilot"]),
    ],
)
def test_a_value_outside_a_closed_vocabulary_is_refused(
    build: Any, data: Any, key: str, value: Any
) -> None:
    broken = data()
    broken[key] = value
    _refused(build, broken, "is not one of")


def test_a_constructed_record_takes_enum_members_not_their_strings() -> None:
    with pytest.raises(ValueError, match="is not a HoldReason"):
        M.Hold(site_id="s", scope=M.HoldScope.SITE, reason="V9", detail="d")  # type: ignore[arg-type]


def test_records_are_frozen() -> None:
    hold = M.Hold(site_id="s", scope=M.HoldScope.SITE, reason=M.HoldReason.V1, detail="pin")
    with pytest.raises(dataclasses.FrozenInstanceError):
        hold.detail = "other"  # type: ignore[misc]


# ------------------------------------------------------------------------------------------------
# Provenance: the fixed pairings and the references
# ------------------------------------------------------------------------------------------------


def test_the_ai_mark_follows_the_lane() -> None:
    assert dict(M.LANE_AI) == {
        M.Lane.W: M.AiMark.SELECTED,
        M.Lane.S: M.AiMark.SELECTED,
        M.Lane.T: M.AiMark.GENERATED,
        M.Lane.R: M.AiMark.GENERATED,
        M.Lane.L: M.AiMark.GENERATED,
    }
    data = _provenance_dict()
    data["ai"] = "generated"
    _refused(M.Provenance.from_dict, data, "lane W is selected")
    data = _r_provenance_dict()
    data["ai"] = "selected"
    _refused(M.Provenance.from_dict, data, "lane R is generated")


def test_the_change_note_follows_the_lane() -> None:
    data = _provenance_dict()
    data["attribution"]["changes"] = "translated"
    _refused(M.Provenance.from_dict, data, "attribution.changes: lane W")
    data = _provenance_dict()
    data["lane"] = "T"
    data["ai"] = "generated"
    _refused(M.Provenance.from_dict, data, "attribution.changes: lane T")


def test_the_disclosed_ai_system_is_the_model_that_is_called() -> None:
    assert M.AI_SYSTEM == f"{MS.MODEL} via Pi (an-sites-remediation-2026-09)"
    data = _provenance_dict()
    data["ai_system"] = "some other model"
    _refused(M.Provenance.from_dict, data, "provenance.ai_system")


def test_published_text_is_cc_by_sa_4_and_links_that_licence() -> None:
    data = _provenance_dict()
    data["licence"] = "restricted"
    _refused(M.Provenance.from_dict, data, "published text is CC BY-SA 4.0")
    data = _provenance_dict()
    data["attribution"]["licence_url"] = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
    _refused(M.Provenance.from_dict, data, "licence_url")


def test_the_attribution_points_at_a_cited_source() -> None:
    data = _provenance_dict()
    data["attribution"]["url"] = "https://en.wikipedia.org/wiki/Tarxien_Temples"
    _refused(M.Provenance.from_dict, data, "not the url of a cited source")


def test_lane_0_and_lane_l_have_no_full_provenance() -> None:
    for lane in ("0", "L"):
        data = _provenance_dict()
        data["lane"] = lane
        _refused(M.Provenance.from_dict, data, "has no full provenance")


def test_every_sentence_names_a_listed_source() -> None:
    data = _provenance_dict()
    data["sentences"][1]["src"] = "T.fr"
    _refused(M.Provenance.from_dict, data, "are not in sources")


def test_every_listed_source_is_cited() -> None:
    data = _r_provenance_dict()
    data["sentences"][1].update(src="R1", start=100, end=170)
    _refused(M.Provenance.from_dict, data, "cited by no sentence")


def test_a_source_is_listed_once() -> None:
    data = _r_provenance_dict()
    data["sources"][1]["id"] = "R1"
    _refused(M.Provenance.from_dict, data, "an id repeats")


def test_wikidata_is_a_witness_and_never_cited() -> None:
    data = _provenance_dict()
    data["sources"][0]["id"] = "D"
    _refused(M.Provenance.from_dict, data, "Wikidata is a witness")


def test_sentences_of_one_source_keep_source_order_and_do_not_overlap() -> None:
    reordered = _provenance_dict()
    reordered["sentences"].reverse()
    _refused(M.Provenance.from_dict, reordered, "out of source order")
    overlapping = _provenance_dict()
    overlapping["sentences"][1]["start"] = 70
    _refused(M.Provenance.from_dict, overlapping, "out of source order")
    # Two sources interleave freely (lane R): order is kept per source, not across sources.
    assert M.Provenance.from_dict(_r_provenance_dict()).sentences[1].src == "R2"


def test_a_drop_range_outside_its_sentence_is_refused() -> None:
    data = _provenance_dict()
    data["sentences"][0]["drop"] = [[70, 90]]
    _refused(M.Provenance.from_dict, data, "leaves \\[0, 80\\)")


def test_overlapping_or_unsorted_drops_are_refused() -> None:
    for drop in ([[40, 60], [50, 70]], [[50, 70], [10, 20]]):
        data = _provenance_dict()
        data["sentences"][0]["drop"] = drop
        _refused(M.Provenance.from_dict, data, "overlaps or precedes")


def test_an_empty_or_reversed_range_is_refused() -> None:
    data = _provenance_dict()
    data["sentences"][0]["drop"] = [[50, 50]]
    _refused(M.Provenance.from_dict, data, "is empty or reversed")
    data = _provenance_dict()
    data["sentences"][0]["end"] = 0
    _refused(M.Provenance.from_dict, data, "is empty or reversed")


def test_a_drop_is_a_pair() -> None:
    data = _provenance_dict()
    data["sentences"][0]["drop"] = [[50, 60, 70]]
    _refused(M.Provenance.from_dict, data, "is not an \\[a, b\\] pair")


def test_a_constructed_drop_is_a_pair_too() -> None:
    with pytest.raises(ValueError, match="is not an \\(a, b\\) pair"):
        M.PublishedSentence(n=1, src="W", start=0, end=80, drop=((50, 60, 70),))  # type: ignore[arg-type]


def test_a_card_names_published_sentences_in_source_order() -> None:
    missing = _provenance_dict()
    missing["card"]["items"][0]["sentence"] = 2
    _refused(M.Provenance.from_dict, missing, "which is not there")
    for indices in ([1, 0], [0, 0]):
        data = _provenance_dict()
        data["card"]["items"] = [{"sentence": index, "drop": []} for index in indices]
        _refused(M.Provenance.from_dict, data, "not strictly ascending")


def test_a_card_has_one_or_two_items() -> None:
    for count in (0, 3):
        data = _provenance_dict()
        data["card"]["items"] = [{"sentence": index, "drop": []} for index in range(count)]
        _refused(M.Provenance.from_dict, data, "the contract allows 1-2")


def test_a_card_drop_stays_inside_its_sentence() -> None:
    data = _provenance_dict()
    data["card"]["items"][0]["drop"] = [[79, 85]]
    _refused(M.Provenance.from_dict, data, "card item 0.drop")


def test_digests_are_lowercase_sha256_hex() -> None:
    for digest in (HEX_DESC.upper(), HEX_DESC[:-1], "sha256:" + HEX_DESC):
        data = _provenance_dict()
        data["desc_sha256"] = digest
        _refused(M.Provenance.from_dict, data, "lowercase sha256 hex")


def test_text_sha256_is_the_in_database_form() -> None:
    # encode(sha256(convert_to('abc', 'UTF8')), 'hex') - the FIPS 180-2 test vector.
    assert M.text_sha256("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    # UTF-8 bytes, not code points: 'à' is two bytes.
    assert M.text_sha256("Arc de Berà") != M.text_sha256("Arc de Bera")


def test_legacy_provenance_refuses_any_other_wording() -> None:
    for key, value in (
        ("lane", "W"),
        ("ai", "selected"),
        ("ai_system", "an LLM"),
        ("basis", "differs"),
        ("v", 2),
    ):
        data = _legacy_dict()
        data[key] = value
        _refused(M.LegacyProvenance.from_dict, data, "legacy_provenance")


def test_provenance_from_dict_reads_both_shapes_by_lane() -> None:
    assert isinstance(M.provenance_from_dict(_legacy_dict()), M.LegacyProvenance)
    assert isinstance(M.provenance_from_dict(_provenance_dict()), M.Provenance)
    # A lane-L object in the full shape is not quietly read as the full shape.
    _refused(M.provenance_from_dict, {**_provenance_dict(), "lane": "L"}, "unknown keys")


def test_an_assembly_carries_a_full_provenance() -> None:
    with pytest.raises(ValueError, match="is not a \\(full\\) Provenance"):
        M.Assembly(
            site_id="s",
            description="Text [1].",
            citations=(),
            card=None,
            provenance=M.LegacyProvenance(desc_sha256=HEX_DESC),  # type: ignore[arg-type]
        )


# ------------------------------------------------------------------------------------------------
# The selector's answer
# ------------------------------------------------------------------------------------------------


def _picks(*sids: str) -> list[dict[str, Any]]:
    return [{"sid": sid, "drop": []} for sid in sids]


@pytest.mark.parametrize(
    ("desc", "card", "abstain", "problem"),
    [
        ([], _picks("W1"), None, M.SelectionProblem.NO_DESC),
        (_picks(*(f"W{i}" for i in range(1, 10))), _picks("W1"), None, "too-many-desc"),
        (_picks("W1", "W2", "W3"), [], None, M.SelectionProblem.NO_CARD),
        (_picks("W1", "W2", "W3"), _picks("W1", "W2", "W3"), None, "too-many-card"),
        (_picks("W1", "W1"), _picks("W1"), None, M.SelectionProblem.DUPLICATE),
        (_picks("W1", "W2"), _picks("W2", "W2"), None, M.SelectionProblem.DUPLICATE),
        (_picks("W1", "W2"), _picks("W3"), None, M.SelectionProblem.CARD_NOT_IN_DESC),
        (_picks("W1"), [], "about a namesake", M.SelectionProblem.ABSTAIN_WITH_OTHER_LINES),
        ([], _picks("W1"), "about a namesake", M.SelectionProblem.ABSTAIN_WITH_OTHER_LINES),
        ([], [], "  ", M.SelectionProblem.ABSTAIN_WITHOUT_REASON),
    ],
)
def test_a_selection_refusal_is_named(
    desc: list[dict[str, Any]], card: list[dict[str, Any]], abstain: str | None, problem: str
) -> None:
    data = {"site_id": "s", "desc": desc, "card": card, "abstain": abstain}
    with pytest.raises(M.SelectionRefused) as caught:
        M.Selection.from_dict(data)
    assert caught.value.problem == problem


def test_the_selector_bounds_are_the_contracts() -> None:
    assert (M.MAX_DESC, M.MAX_CARD) == (8, 2)
    eight = {"site_id": "s", "desc": _picks(*(f"W{i}" for i in range(1, 9))), "abstain": None}
    assert len(M.Selection.from_dict({**eight, "card": _picks("W1", "W8")}).desc) == 8


def test_a_span_dropped_twice_in_one_line_is_a_duplicate() -> None:
    with pytest.raises(M.SelectionRefused) as caught:
        M.Pick.from_dict({"sid": "W12", "drop": ["a1", "a1"]})
    assert caught.value.problem is M.SelectionProblem.DUPLICATE


def test_a_pick_names_a_numbered_wikipedia_sentence() -> None:
    for sid in ("R1", "D1", "W0", "W", "w3", "T.fr"):
        _refused(M.Pick.from_dict, {"sid": sid, "drop": []}, "is not a sentence id")
    assert M.Pick.from_dict({"sid": "T.fr3", "drop": ["l1"]}).sid == "T.fr3"
    _refused(M.Pick.from_dict, {"sid": "W3", "drop": ["x1"]}, "is not a span id")


# ------------------------------------------------------------------------------------------------
# Sentences and spans
# ------------------------------------------------------------------------------------------------


def test_a_sentence_id_is_its_source_and_its_number() -> None:
    assert M.Sentence.from_dict(_sentence_dict()).sid == "W12"
    assert M.Sentence.from_dict({**_sentence_dict(), "src": "T.fr", "spans": []}).sid == "T.fr12"


def test_only_wikipedia_text_is_numbered_into_sentences() -> None:
    for src in ("R1", "D"):
        _refused(M.Sentence.from_dict, {**_sentence_dict(), "src": src}, "not a selectable")


def test_a_span_id_names_its_kind() -> None:
    _refused(M.Span.from_dict, {"id": "p1", "kind": "a", "start": 1, "end": 2}, "does not name")


def test_a_span_outside_its_sentence_is_refused() -> None:
    data = _sentence_dict()
    data["spans"][0]["end"] = 171
    _refused(M.Sentence.from_dict, data, "span a1 leaves the sentence")


def test_a_span_id_is_offered_once_per_sentence() -> None:
    data = _sentence_dict()
    data["spans"][1] = {**data["spans"][0], "start": 101, "end": 110}
    _refused(M.Sentence.from_dict, data, "offered twice")


# ------------------------------------------------------------------------------------------------
# Sources, lanes, the plan, holds
# ------------------------------------------------------------------------------------------------


def test_source_ids_follow_the_store_layout() -> None:
    assert [M.source_kind(s) for s in ("W", "D", "T.fr", "T.zh-yue", "R1", "R12")] == [
        M.SourceKind.W,
        M.SourceKind.D,
        M.SourceKind.T,
        M.SourceKind.T,
        M.SourceKind.R,
        M.SourceKind.R,
    ]
    for bad in ("T", "R", "R0", "W1", "T.", "T.FR", "D2", "src.W", ""):
        with pytest.raises(ValueError, match="is not a source id"):
            M.source_kind(bad)
    assert [M.source_feature("T.fr", part) for part in ("raw", "txt", "meta")] == [
        "src.T.fr",
        "src.T.fr.txt",
        "src.T.fr.meta",
    ]
    with pytest.raises(ValueError, match="is not a source part"):
        M.source_feature("W", "json")


def test_a_source_doc_keeps_every_key_even_when_null() -> None:
    written = M.SourceDoc.from_dict(_r_source_doc_dict()).to_dict()
    assert written == _r_source_doc_dict()
    assert written["subject_gate"] is None and "subject_gate" in written


@pytest.mark.parametrize(
    ("lane", "sources"),
    [
        ("W", ["T.fr"]),
        ("S", ["W", "R1"]),
        ("T", ["W"]),
        ("R", []),
        ("R", ["R1", "W"]),
        ("0", ["W"]),
        ("W", ["W", "D"]),
    ],
)
def test_each_lane_uses_its_own_kind_of_source(lane: str, sources: list[str]) -> None:
    data = {"site_id": "s", "lane": lane, "sources": sources, "detail": "facts"}
    _refused(M.LaneAssignment.from_dict, data, "cannot use the sources")


def test_the_lanes_that_can_be_assigned() -> None:
    for lane, sources in (("W", ["W"]), ("S", ["W"]), ("T", ["T.it"]), ("R", ["R1", "R2"])):
        data = {"site_id": "s", "lane": lane, "sources": sources, "detail": "facts"}
        assert M.LaneAssignment.from_dict(data).lane == lane
    assert M.LaneAssignment(site_id="s", lane=M.Lane.ZERO, sources=(), detail="none").sources == ()
    data = {"site_id": "s", "lane": "L", "sources": [], "detail": "facts"}
    _refused(M.LaneAssignment.from_dict, data, "is never assigned")


def test_a_plan_site_digest_is_the_sha256_of_its_text() -> None:
    for text_key in ("description", "card"):
        data = _plan_site_dict()
        data[text_key] = data[text_key] + " "
        _refused(M.PlanSite.from_dict, data, f"{text_key}_sha256 is not the sha256")
    data = _plan_site_dict()
    data["card"] = None
    _refused(M.PlanSite.from_dict, data, "card and card_sha256 disagree on null")
    data = _plan_site_dict()
    data["raw_data"] = None
    _refused(M.PlanSite.from_dict, data, "raw_data and raw_data_sha256 disagree on null")


def test_a_plan_site_says_whether_the_snapshot_has_it() -> None:
    """`in_snapshot` is a boolean, and a site the snapshot does not have carries no snapshot text
    (accepted by the orchestrator 2026-09-23, decision D4)."""
    _refused(M.PlanSite.from_dict, {**_plan_site_dict(), "in_snapshot": 1}, "not a boolean")
    _refused(
        M.PlanSite.from_dict,
        {**_plan_site_dict(), "in_snapshot": False, "snapshot_description": "old"},
        "a snapshot description for a site not in the snapshot",
    )
    absent = M.PlanSite.from_dict({**_plan_site_dict(), "in_snapshot": False})
    assert M.PlanSite.from_json(absent.to_json()) == absent


def test_a_plan_site_accepts_the_oldest_period_in_production() -> None:
    # Measured 2026-09-23 (read-only): min(period_start) over the curated rows is -1,400,000.
    data = {**_plan_site_dict(), "period_start": -1_400_000}
    assert M.PlanSite.from_dict(data).period_start == -1_400_000


def test_a_plan_site_flag_listed_twice_is_refused() -> None:
    data = {**_plan_site_dict(), "flags": ["t03", "t03"]}
    _refused(M.PlanSite.from_dict, data, "listed twice")


def test_a_hold_names_its_reason() -> None:
    _refused(
        M.Hold.from_dict,
        {"site_id": "s", "scope": "site", "reason": "V5", "detail": " "},
        "detail",
    )


def test_card_only_reasons_cannot_hold_a_site() -> None:
    for reason in ("card-too-short-after-review", "audit-not-contained"):
        data = {"site_id": "s", "scope": "site", "reason": reason, "detail": "d"}
        _refused(M.Hold.from_dict, data, "holds only a card")
        assert M.Hold.from_dict({**data, "scope": "card"}).scope is M.HoldScope.CARD


def test_the_verifier_can_hold_under_every_rule_id() -> None:
    rule_ids = {reason.value for reason in M.HoldReason if re.fullmatch(r"V\d+", reason.value)}
    assert rule_ids == {f"V{i}" for i in range(1, 16)}
    assert M.HoldReason("lane-R-closed") is M.HoldReason.LANE_R_CLOSED


# ------------------------------------------------------------------------------------------------
# The shared word lists
# ------------------------------------------------------------------------------------------------

#: verification, V4, verbatim.
DESIGN_PROTECTED = {
    "hedges": (
        "possibly probably perhaps may might could likely believed thought suggest* claimed "
        "alleged* legend* tradition* reportedly according circa c. ca. approximately about "
        "around estimated some several"
    ).split(),
    "negations": "not no never neither nor without".split(),
    "contrast": "but although though however whereas while yet despite".split(),
    "refutation": (
        "disputed debated uncertain unclear rejected refuted disproved discredited unlikely "
        "doubtful contested questioned hypothes* theor* speculat* attributed"
    ).split(),
    "restriction": [
        *"only except until partly partially formerly originally mainly mostly largely".split(),
        "part of",
        "at least",
        "at most",
        "up to",
        "nearly",
        "almost",
    ],
}
#: verification, V6, verbatim.
DESIGN_PRONOUNS = [
    *"It Its This These They Their He She His Her".split(),
    "The latter",
    "The former",
    "Here",
    "There",
]


#: The review of WB-B2's additions (2026-09-23), verbatim: the design's list let hedged and
#: contracted-negation spans be offered for deletion.
ADDED_PROTECTED = {
    "hedges": (
        "presum* apparent* arguabl* seem* appear* suppos* reputed* purported* evidently assum* "
        "possible probable maybe"
    ).split(),
    "negations": ["cannot", "*n't", "*n’t"],
    "refutation": ["unknown"],
}


def test_the_protected_tokens_are_the_design_list_verbatim() -> None:
    assert {group: list(tokens) for group, tokens in M.DESIGN_PROTECTED_TOKENS.items()} == (
        DESIGN_PROTECTED
    )


def test_the_protected_tokens_every_consumer_reads_are_the_design_list_then_the_additions() -> None:
    assert {group: list(tokens) for group, tokens in M.PROTECTED_TOKEN_ADDITIONS.items()} == (
        ADDED_PROTECTED
    )
    assert {group: list(tokens) for group, tokens in M.PROTECTED_TOKENS.items()} == {
        group: [*design, *ADDED_PROTECTED.get(group, [])]
        for group, design in DESIGN_PROTECTED.items()
    }


def test_the_pronoun_openers_are_the_design_list_verbatim() -> None:
    assert list(M.PRONOUN_OPENERS) == DESIGN_PRONOUNS


@pytest.mark.parametrize(
    ("text", "circa"),
    [
        ("built c. 2500 BC", "c. "),
        ("built ca.300 AD", "ca."),
        # {{circa}} renders `c.` and a thin space (U+2009); an NBSP is whitespace too
        ("grew c.\u20091770 BC", "c.\u2009"),
        ("settled c.\u00a012,500 years ago", "c.\u00a0"),
        # era-first dates
        ("built c. AD 79 on the shore", "c. "),
        ("built ca. BC 500 on the hill", "ca. "),
        ("built c. BCE 500 on the hill", "c. "),
        # a capital C, at the start of a sentence
        ("C. 1200 BC the city was burnt", "C. "),
        ("Ca. 1200 BC the city was burnt", "Ca. "),
    ],
)
def test_the_circa_pattern_reads_every_circa_form(text: str, circa: str) -> None:
    (match,) = M.CIRCA_PATTERN.finditer(text)
    assert match.group() == circa


@pytest.mark.parametrize(
    "text",
    [
        "It dates to the 5th c. BCE and later.",  # c. is a century: no number follows
        "It dates to the 5th c. and the 4th c.",
        "It was dug by B.c. 1990 surveyors.",  # an initial after a full stop
        "Tools from Africa. 1990 was the year.",  # the end of a word, not an abbreviation
        "Tools, pots etc. 5 of them.",
        "It was built c. ad 79.",  # an era word is upper case
    ],
)
def test_the_circa_pattern_reads_no_century_and_no_word_end(text: str) -> None:
    assert M.CIRCA_PATTERN.search(text) is None


def test_the_word_lists_match_the_design_file() -> None:
    """The same lists, parsed out of the design itself: the literal above cannot drift from it."""
    if not DESIGN.exists():
        pytest.skip(f"needs the gitignored design file {DESIGN.relative_to(REPO)}")
    entry = json.loads(DESIGN.read_text(encoding="utf-8"))[6]
    assert entry["title"].startswith("Phases 4 and 5, final design")
    text = entry["verification"]
    v4 = text[text.index("V4 drop legality") : text.index("V5 well-formed")]
    groups = dict(re.findall(r"^- (\w+): (.+?)[;.]$", v4, flags=re.MULTILINE))
    parsed = {
        group: [token.strip("'") for token in body.split(", ")] for group, body in groups.items()
    }
    assert parsed == {group: list(tokens) for group, tokens in M.DESIGN_PROTECTED_TOKENS.items()}
    v6 = text[text.index("V6 anaphora") : text.index("V7 subject")]
    pronouns = re.search(r"closed pronoun list \(([^)]*)\)", v6)
    assert pronouns is not None
    assert pronouns.group(1).split(", ") == list(M.PRONOUN_OPENERS)


# ------------------------------------------------------------------------------------------------
# The import shim
# ------------------------------------------------------------------------------------------------


def test_importing_phase4_puts_the_repository_root_on_the_path(tmp_path: Path) -> None:
    """A phase-4 stage imports `pipeline.*`. Importing the package must make that resolve from
    any working directory, as `phase3/search_evidence.py` does for `phase3`. `-I` keeps the
    working directory and PYTHONPATH off `sys.path`, so only the shim can put the root there."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import phase4; "
        "import pipeline.lyra.text_sentences; print(phase4.REPO)"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code, str(PHASE4_PARENT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert Path(proc.stdout.strip()) == REPO
