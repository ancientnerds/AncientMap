"""The shape helpers and the quote check every identity answer is made of (`identity/answers.py`)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from identity import answers as A  # noqa: E402
from identity.rounds import AnswerError  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation.identity_b_fixtures import html, store  # noqa: E402

PAGE = "https://example.org/page"
TEXT = "Kydonia was an ancient city on the north coast of Crete."


def q(url: str = PAGE, quote: str = TEXT) -> dict[str, str]:
    return {"url": url, "quote": quote}


class TestTheShape:
    def test_an_object_has_exactly_its_keys(self) -> None:
        assert A.load_object('{"a": 1, "b": 2}', {"a", "b"}) == {"a": 1, "b": 2}
        for text, match in (
            ("[1]", "carries list"),
            ('{"a": 1}', "carries"),
            ("nope", "not JSON"),
            ('{"a": 1, "b": 2, "c": 3}', "carries"),
        ):
            with pytest.raises(AnswerError, match=match):
                A.load_object(text, {"a", "b"})

    def test_a_text_is_trimmed_non_empty_clean_and_bounded(self) -> None:
        assert A.text_of("Menga Dolmen", "name") == "Menga Dolmen"
        for bad in ("", "  ", " x", "x ", None, 3):
            with pytest.raises(AnswerError, match="trimmed, non-empty"):
                A.text_of(bad, "name")
        with pytest.raises(AnswerError, match="control character"):
            A.text_of("a\x00b", "name")
        with pytest.raises(AnswerError, match="control character"):
            A.text_of("a\tb", "name")
        with pytest.raises(AnswerError, match="longer than 3 characters"):
            A.text_of("abcd", "name", max_chars=3)
        assert A.text_of("abc", "name", max_chars=3) == "abc"


class TestTheQuotes:
    def test_a_quote_is_a_url_and_a_text(self) -> None:
        assert A.quotes_of([q()], "quotes") == (q(),)
        assert A.quotes_of([], "quotes") == ()

    @pytest.mark.parametrize(
        ("value", "match"),
        [
            ("not a list", "quotes is not a list"),
            ({"url": PAGE, "quote": "x"}, "quotes is not a list"),
            ([["x"]], "is not {url, quote}"),
            ([{"url": PAGE}], "is not {url, quote}"),
            ([{"source": PAGE, "quote": "x"}], "is not {url, quote}"),
            ([{"url": PAGE, "quote": 3}], "needs a url and a text"),
            ([{"url": PAGE, "quote": "  "}], "needs a url and a text"),
            ([{"url": 3, "quote": "x"}], "needs a url and a text"),
            ([{"url": "ftp://x/y", "quote": "x"}], "must be the URL of the page"),
            ([{"url": "the Wikipedia article", "quote": "x"}], "must be the URL of the page"),
            ([{"url": "https://ancientnerds.com/x", "quote": "x"}], "never fetched here"),
            ([{"url": "http://localhost/x", "quote": "x"}], "never fetched here"),
        ],
    )
    def test_every_way_a_quote_can_be_malformed(self, value: Any, match: str) -> None:
        with pytest.raises(AnswerError, match=match):
            A.quotes_of(value, "quotes")

    def test_a_minimum_of_quotes_can_be_demanded(self) -> None:
        with pytest.raises(AnswerError, match="needs at least 2 quote"):
            A.quotes_of([q()], "quotes", minimum=2)
        assert len(A.quotes_of([q(), q(PAGE + "2")], "quotes", minimum=2)) == 2

    def test_cites_compares_canonical_urls(self) -> None:
        assert A.cites([q(PAGE + "?a=1&amp;b=2")], PAGE + "?a=1&b=2")
        assert not A.cites([q(PAGE)], PAGE + "x")
        assert A.urls_of([q()], [q(PAGE + "2")]) == {PAGE, PAGE + "2"}


class TestTheCheck:
    @pytest.fixture
    def library(self, tmp_path: Path) -> Q.Library:
        store(tmp_path / "pages", PAGE, html(TEXT))
        return Q.Library(REPO, tmp_path / "pages")

    def test_no_quote_is_all_quotes_found_and_a_found_quote_is_noted(
        self, library: Q.Library
    ) -> None:
        assert A.check_quotes([], "s", library) == (True, [], "")
        counted, noted, reason = A.check_quotes([q()], "s", library)
        assert counted and reason == "" and noted[0]["outcome"] == "found"

    def test_one_missing_quote_fails_the_cell_and_names_the_first_failure(
        self, library: Q.Library
    ) -> None:
        counted, noted, reason = A.check_quotes([q(), q(quote="nothing of the kind")], "s", library)
        assert not counted and reason == f"not found: {PAGE}"
        assert [n["outcome"] for n in noted] == ["found", "not found"]
        assert json.dumps(noted)
