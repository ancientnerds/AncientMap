"""Phase 6 acceptance, sections 6-7: the strict answer parsers and the quote check.

`scripts/remediation/acceptance/answers.py` reads what an Opus judge wrote. A verdict counts only in
exactly its shape - one JSON object with exactly its keys - and only when every quote it rests on is
found verbatim (NFC and whitespace runs only) in the page it cites, fetched and stored by the run:
the Opus re-verification's check, `scripts/remediation/opus_audit/quotes.py`, reused unchanged.
Offline: pages are stored by the test, nothing is fetched. The mutation cases are
`acceptance judge: ...` in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from acceptance import answers as A  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

WIKI = "https://en.wikipedia.org/wiki/Temple_of_Nowhere"
UNESCO = "https://whc.unesco.org/en/list/1"
TEXT = "The temple stands on a hill.[1] It was built c. 400 BC by the Inca.[1]"


def q(url: str = WIKI, quote: str = "a temple on a hill", claim: str | None = None) -> dict:
    return {"url": url, "quote": quote, "claim": claim}


def s1(**over: Any) -> str:
    body: dict[str, Any] = {
        "verdict": "CORRECT",
        "quotes": [q(), q(UNESCO)],
        "right_value": None,
        "severity": None,
        "reasoning": "Both sources name it so.",
    }
    body.update(over)
    return json.dumps(body)


def wrong(**over: Any) -> str:
    return s1(verdict="WRONG", quotes=[q()], right_value="Bolivia", severity="severe", **over)


# ------------------------------------------------------------------------------ the JSON object
def test_an_answer_is_one_json_object_with_exactly_its_keys() -> None:
    assert A.parse_stage1(s1(), "country", "Peru").verdict == "CORRECT"
    fenced = "```json\n" + s1() + "\n```"
    body = json.loads(s1())
    for bad, why in (
        (fenced, "one JSON object"),
        (s1() + "\nThat is my answer.", "one JSON object"),
        (json.dumps({**body, "confidence": "high"}), "keys"),
        (json.dumps({k: v for k, v in body.items() if k != "reasoning"}), "keys"),
        (s1()[:-1] + ', "verdict": "WRONG"}', "twice"),
        (json.dumps([body]), "object"),
        (s1(verdict="correct"), "verdict"),
        (s1(reasoning="  "), "reasoning"),
        (s1(quotes=[{"url": WIKI, "quote": "x"}, q(UNESCO)]), "quote"),
        (s1(quotes=[q(url="en.wikipedia.org/wiki/X"), q(UNESCO)]), "http"),
        (s1(quotes=[q(quote=" \n "), q(UNESCO)]), "empty"),
    ):
        with pytest.raises(A.AnswerError, match=why):
            A.parse_stage1(bad, "country", "Peru")


def test_nan_is_not_json() -> None:
    with pytest.raises(A.AnswerError, match="NaN is not JSON"):
        A.parse_stage1(s1().replace('"severity": null', '"severity": NaN'), "country", "Peru")


# ------------------------------------------------------------------------------ source families
def test_one_wikipedia_article_and_its_wikidata_item_are_one_source_family() -> None:
    family = A.source_family
    assert family(WIKI) == family("https://de.wikipedia.org/wiki/Tempel") == "wikimedia"
    assert family("https://www.wikidata.org/wiki/Q1") == "wikimedia"
    assert family("https://commons.wikimedia.org/wiki/File:X.jpg") == "wikimedia"
    assert family(UNESCO) == family("https://unesco.org/x") == "unesco.org"
    assert family("https://historicengland.org.uk/listing/1") == "historicengland.org.uk"
    assert family("https://www.english-heritage.org.uk/visit") == "english-heritage.org.uk"
    archived = "https://web.archive.org/web/20200101000000/https://www.persee.fr/doc/x"
    assert family(archived) == "persee.fr"
    assert family("https://web.archive.org/web/") == "archive.org"


def test_correct_needs_two_quotes_from_two_source_families() -> None:
    wikidata = "https://www.wikidata.org/wiki/Q1"
    with pytest.raises(A.AnswerError, match="two"):
        A.parse_stage1(s1(quotes=[q()]), "country", "Peru")
    with pytest.raises(A.AnswerError, match="source famil"):
        A.parse_stage1(s1(quotes=[q(), q(wikidata)]), "country", "Peru")
    with pytest.raises(A.AnswerError, match="null"):
        A.parse_stage1(s1(right_value="Peru"), "country", "Peru")
    with pytest.raises(A.AnswerError, match="null"):
        A.parse_stage1(s1(severity="severe"), "country", "Peru")
    answer = A.parse_stage1(s1(), "country", "Peru")
    assert [x.url for x in answer.quotes] == [WIKI, UNESCO]


# ---------------------------------------------------------------------------------- WRONG
def test_wrong_needs_a_quote_a_right_value_and_a_severity_its_row_allows() -> None:
    answer = A.parse_stage1(wrong(), "country", "Peru")
    assert (answer.verdict, answer.right_value, answer.severity) == ("WRONG", "Bolivia", "severe")
    with pytest.raises(A.AnswerError, match="quote"):
        A.parse_stage1(wrong().replace(json.dumps([q()]), "[]"), "country", "Peru")
    with pytest.raises(A.AnswerError, match="severity"):
        A.parse_stage1(s1(verdict="WRONG", quotes=[q()], right_value="Bolivia",
                          severity="moderate"), "country", "Peru")  # fmt: skip
    with pytest.raises(A.AnswerError, match="right_value"):
        A.parse_stage1(s1(verdict="WRONG", quotes=[q()], right_value=None,
                          severity="severe"), "country", "Peru")  # fmt: skip
    with pytest.raises(A.AnswerError, match="served value"):
        A.parse_stage1(s1(verdict="WRONG", quotes=[q()], right_value=" Peru ",
                          severity="severe"), "country", "Peru")  # fmt: skip


def test_unverifiable_rests_on_no_quote_and_proposes_nothing() -> None:
    answer = A.parse_stage1(s1(verdict="UNVERIFIABLE", quotes=[]), "country", "Peru")
    assert answer.verdict == "UNVERIFIABLE" and answer.quotes == ()
    with pytest.raises(A.AnswerError, match="UNVERIFIABLE"):
        A.parse_stage1(s1(verdict="UNVERIFIABLE", quotes=[q()]), "country", "Peru")
    with pytest.raises(A.AnswerError, match="null"):
        A.parse_stage1(
            s1(verdict="UNVERIFIABLE", quotes=[], right_value="Chile"), "country", "Peru"
        )


# ---------------------------------------------------------------------------- the text fields
def _text_quotes(*claims: str) -> list[dict]:
    return [q(WIKI, "hill", claims[0]), *(q(UNESCO, "Inca", c) for c in claims[1:])]


def test_a_text_field_quote_names_the_claim_it_bears_on_from_the_served_text() -> None:
    claims = ("The temple stands on a hill.", "built c. 400 BC by the Inca")
    answer = A.parse_stage1(s1(quotes=_text_quotes(*claims)), "description", TEXT)
    assert [x.claim for x in answer.quotes] == list(claims)
    with pytest.raises(A.AnswerError, match="not in the served text"):
        A.parse_stage1(s1(quotes=_text_quotes(claims[0], "built by the Maya")), "description", TEXT)
    with pytest.raises(A.AnswerError, match="claim"):
        A.parse_stage1(s1(quotes=[q(), q(UNESCO, "Inca", claims[1])]), "description", TEXT)
    with pytest.raises(A.AnswerError, match="claim"):
        A.parse_stage1(s1(quotes=[q(claim="Peru"), q(UNESCO)]), "country", "Peru")


def test_a_correct_text_field_quotes_a_claim_in_every_sentence() -> None:
    with pytest.raises(A.AnswerError, match="It was built c. 400 BC by the Inca"):
        A.parse_stage1(
            s1(quotes=_text_quotes("stands on a hill", "The temple")), "card_description", TEXT
        )
    assert A.uncovered_sentences(TEXT, ["on a hill.[1] It was"]) == []
    assert A.uncovered_sentences("One. Two.", ["One."]) == ["Two."]
    assert A.uncovered_sentences("Built c. 400 BC. Two.", ["Built c. 400 BC.", "Two"]) == []


def test_a_wrong_text_field_names_the_contradicted_claim() -> None:
    body = wrong().replace(json.dumps([q()]), json.dumps([q(claim="by the Inca")]))
    answer = A.parse_stage1(body, "description", TEXT)
    assert answer.quotes[0].claim == "by the Inca"


# ---------------------------------------------------------------------------- typed right values
def _wrong(field: str, value: str, right: str, severity: str) -> A.Answer1:
    body = s1(verdict="WRONG", quotes=[q()], right_value=right, severity=severity)
    return A.parse_stage1(body, field, value)


def test_a_right_point_is_a_point_and_its_distance_decides_the_class() -> None:
    served = "51.178882, -1.826215"
    assert _wrong("coordinates", served, "51.3, -1.826215", "severe").right_value
    assert _wrong("coordinates", served, "51.2, -1.826215", "moderate").severity == "moderate"
    with pytest.raises(A.AnswerError, match="1 km"):
        _wrong("coordinates", served, "51.1789, -1.8262", "moderate")
    with pytest.raises(A.AnswerError, match="5 km"):
        _wrong("coordinates", served, "51.3, -1.826215", "moderate")
    with pytest.raises(A.AnswerError, match="lat, lon"):
        _wrong("coordinates", served, "north of Salisbury", "severe")
    with pytest.raises(A.AnswerError, match="lat, lon"):
        _wrong("coordinates", served, "95.0, 10.0", "severe")


def test_a_right_type_is_a_canonical_type() -> None:
    assert _wrong("site_type", "Temple", "Fortress/citadel", "moderate").right_value
    with pytest.raises(A.AnswerError, match="canonical"):
        _wrong("site_type", "Temple", "hill fort", "moderate")


def test_a_right_start_is_another_bucket_and_the_distance_decides_the_class() -> None:
    assert _wrong("period_start", "-500", "-1500", "moderate").severity == "moderate"
    assert _wrong("period_start", "-500", "-3000", "severe").severity == "severe"
    with pytest.raises(A.AnswerError, match="bucket"):
        _wrong("period_start", "-500", "-200", "moderate")
    with pytest.raises(A.AnswerError, match="severe"):
        _wrong("period_start", "-500", "-3000", "moderate")
    with pytest.raises(A.AnswerError, match="moderate"):
        _wrong("period_start", "-500", "-1500", "severe")
    with pytest.raises(A.AnswerError, match="integer"):
        _wrong("period_start", "-500", "5th century BC", "moderate")


def test_a_right_bucket_is_a_bucket() -> None:
    assert _wrong("period_name", "1 - 500 AD", "500 BC - 1 AD", "moderate").right_value
    with pytest.raises(A.AnswerError, match="bucket"):
        _wrong("period_name", "1 - 500 AD", "Roman", "moderate")


# ------------------------------------------------------------------------------- stage 2
def s2(**over: Any) -> str:
    body: dict[str, Any] = {
        "verdict": "CONFIRMED",
        "quotes": [{"url": UNESCO, "quote": "in Bolivia"}],
        "severity": None,
        "severity_reason": None,
        "pattern": None,
        "reasoning": "The site lies in Bolivia.",
    }
    body.update(over)
    return json.dumps(body)


def test_a_confirmation_needs_a_quote_and_may_only_lower_the_class_with_a_reason() -> None:
    assert A.parse_stage2(s2(), "coordinates", "severe").verdict == "CONFIRMED"
    lowered = A.parse_stage2(
        s2(severity="moderate", severity_reason="3 km off, not another place"),
        "coordinates",
        "severe",
    )
    assert lowered.severity == "moderate"
    for bad, why in (
        (s2(quotes=[]), "quote"),
        (s2(severity="moderate"), "severity_reason"),
        (s2(severity="severe", severity_reason="same"), "lower"),
        (s2(severity="cosmetic", severity_reason="x"), "severity"),
        (s2(pattern=2), "pattern"),
        (s2(quotes=[{"url": UNESCO, "quote": "x", "claim": None}]), "quote"),
    ):
        with pytest.raises(A.AnswerError, match=why):
            A.parse_stage2(bad, "coordinates", "severe")


def test_a_refutation_may_name_a_pattern_and_an_undecided_rests_on_nothing() -> None:
    refuted = A.parse_stage2(s2(verdict="REFUTED", quotes=[], pattern=2), "country", "severe")
    assert refuted.pattern == 2
    assert A.parse_stage2(s2(verdict="UNDECIDED", quotes=[]), "country", "severe").quotes == ()
    for bad, why in (
        (s2(verdict="REFUTED", pattern=12), "pattern"),
        (s2(verdict="REFUTED", pattern=True), "pattern"),
        (s2(verdict="REFUTED", severity="severe"), "null"),
        (s2(verdict="UNDECIDED"), "UNDECIDED"),
        (s2(verdict="WRONG"), "verdict"),
    ):
        with pytest.raises(A.AnswerError, match=why):
            A.parse_stage2(bad, "country", "severe")


def test_the_third_judge_decides_confirmed_or_refuted_and_a_confirmation_is_quoted() -> None:
    body = {"verdict": "CONFIRMED", "quotes": [{"url": UNESCO, "quote": "x"}], "reasoning": "r"}
    assert A.parse_stage3(json.dumps(body)).verdict == "CONFIRMED"
    assert A.parse_stage3(json.dumps({**body, "verdict": "REFUTED", "quotes": []})).quotes == ()
    with pytest.raises(A.AnswerError, match="verdict"):
        A.parse_stage3(json.dumps({**body, "verdict": "UNDECIDED"}))
    with pytest.raises(A.AnswerError, match="quote"):
        A.parse_stage3(json.dumps({**body, "quotes": []}))


# ------------------------------------------------------------------------------ the quote check
def _library(tmp_path: Path) -> Q.Library:
    pages = tmp_path / "pages"
    html = b"<html><body><p>The temple\n stands   on a <b>hill</b>.</p></body></html>"
    Q.store_page(pages, WIKI, status=200, final_url=WIKI, content_type="text/html; charset=utf-8",
                 body=html, error="", fetched_at="t")  # fmt: skip
    Q.store_page(pages, UNESCO, status=403, final_url=UNESCO, content_type="text/html",
                 body=b"denied", error="", fetched_at="t")  # fmt: skip
    return Q.Library(REPO, pages)


def test_a_quote_counts_only_when_found_verbatim_whitespace_forgiven(tmp_path: Path) -> None:
    library = _library(tmp_path)
    found = A.check_quotes("q1", (A.Quote(WIKI, "temple stands on a hill.", None),), library)
    assert found.counted and found.reason == ""
    assert found.results[0]["outcome"] == Q.FOUND
    case = A.check_quotes("q1", (A.Quote(WIKI, "Temple stands on a hill.", None),), library)
    assert not case.counted and case.reason == Q.NOT_FOUND
    blocked = A.check_quotes(
        "q1", (A.Quote(WIKI, "hill", None), A.Quote(UNESCO, "denied", None)), library
    )
    assert not blocked.counted and blocked.reason == Q.FETCH_FAILED
    production = A.check_quotes(
        "q1", (A.Quote("https://ancientnerds.com/sites/x", "x", None),), library
    )
    assert not production.counted and production.reason == Q.NOT_FETCHED


def test_a_verdict_without_quotes_has_nothing_to_fail(tmp_path: Path) -> None:
    check = A.check_quotes("q1", (), _library(tmp_path))
    assert check.counted and check.results == ()
