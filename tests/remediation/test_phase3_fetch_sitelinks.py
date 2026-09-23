"""The fetch stage's sitelink route (2026-09-23): the item's other-language Wikipedia articles, each
pinned to a revision, read as plain text through the extracts API and refused when the answer is no
longer the pinned revision of the item's own article.

No test here opens a socket: every answer is a fixture in the shape the live answer had on
2026-09-23 (`runs/sitelink-gold-dry`, the pilot's dry fetch: de.wikipedia.org `Areni-1`, Q1007510).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError  # noqa: E402

SITE = "1ef25b31-0000-4000-8000-000000000001"
QID = "Q1007510"
REVID = 268759019
DE = {"wiki": "dewiki", "lang": "de", "title": "Areni-1", "revid": REVID}
ES = {"wiki": "eswiki", "lang": "es", "title": "Cueva Areni-1", "revid": 170000001}
TEXT = "Areni-1 ist eine Karsthöhle in der Nähe der Stadt Jeghegnadsor."


def _record(**extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "site_id": SITE,
        "name": "Areni-1 cave complex",
        "findings": [SP.finding_row(field, "a value") for field in SP.DISCOVER_FIELDS],
        "wikidata_qid": QID,
        F.WIKI_SITELINKS_KEY: [dict(DE)],
    }
    record.update(extra)
    return record


def _page(**changes: Any) -> dict[str, Any]:
    """The live answer's one page (`formatversion=2`), metadata first and the extract last."""
    page: dict[str, Any] = {
        "pageid": 10133575,
        "ns": 0,
        "title": "Areni-1",
        "contentmodel": "wikitext",
        "pagelanguage": "de",
        "touched": "2026-09-11T14:38:04Z",
        "lastrevid": REVID,
        "length": 5719,
        "revisions": [{"revid": REVID, "parentid": 268150967}],
        "pageprops": {"wikibase_item": QID},
        "extract": TEXT,
    }
    page.update(changes)
    return {key: value for key, value in page.items() if value is not None}


def _body(page: dict[str, Any]) -> bytes:
    return json.dumps(
        {"batchcomplete": True, "query": {"pages": [page]}},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _target(record: dict[str, Any] | None = None) -> F.Target:
    targets = F.targets_for_site(record or _record())
    return next(t for t in targets if t.sitelink is not None)


class _Answers:
    """A `Fetcher` that answers every request with the next body of a list, and counts."""

    def __init__(self, *bodies: bytes, status: int = 200, truncated: bool = False) -> None:
        self.bodies = list(bodies)
        self.status = status
        self.truncated = truncated
        self.asked: list[str] = []

    def get(self, url: str) -> F.FetchedPage:
        self.asked.append(url)
        return F.FetchedPage(
            status=self.status, final_url=url, body=self.bodies.pop(0), truncated=self.truncated
        )


def _attempt(tmp_path: Path, fetcher: Any, target: F.Target | None = None) -> F.TargetOutcome:
    return F.one_attempt(
        target=target or _target(),
        fetcher=fetcher,
        store=F.EvidenceStore(tmp_path / "evidence"),
        ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
        batch_id="slkg-0001",
        stage=Stage.FINDER,
        sleep=lambda _seconds: None,
    )


def _lines(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "LEDGER.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ── the ledger's rule: every request has its line ─────────────────────────────────────────────


def test_an_unreadable_2xx_sitelink_answer_stops_the_run_after_its_ledger_line(
    tmp_path: Path,
) -> None:
    """MediaWiki sends an error with HTTP 200 (`{"error": {...}}`): the answer is a contract break and
    stops the run - but the request left the machine, so its line is already down (piece 2's rule)."""
    error = json.dumps({"error": {"code": "badvalue", "info": "Unrecognized value"}}).encode()
    with pytest.raises(F.EvidenceUnrenderable, match="no single page"):
        _attempt(tmp_path, _Answers(error))
    lines = _lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["outcome"] == "ok" and lines[0]["http_status"] == 200
    assert lines[0]["given_up"] is False and lines[0]["label"].endswith("sitelink.dewiki")
    assert not (tmp_path / "evidence").exists() or not any((tmp_path / "evidence").iterdir())


def test_a_refused_answer_is_not_stored_not_asked_again_and_its_line_says_given_up(
    tmp_path: Path,
) -> None:
    edited = _body(_page(lastrevid=REVID + 5, revisions=[{"revid": REVID + 5}]))
    fetcher = _Answers(edited, edited)
    outcome = _attempt(tmp_path, fetcher)
    assert len(fetcher.asked) == 1
    assert outcome.stored is False and outcome.succeeded is False
    assert "edited after the plan was built" in str(outcome.answer_refused)
    assert str(outcome.failure).startswith("HTTP 200, answer refused: the article is at revision")
    lines = _lines(tmp_path)
    assert [line["given_up"] for line in lines] == [True]
    assert not F.EvidenceStore(tmp_path / "evidence").exists(SITE, "sitelink.dewiki")


def test_the_pinned_answer_is_stored_as_its_source_line_and_its_text(tmp_path: Path) -> None:
    outcome = _attempt(tmp_path, _Answers(_body(_page())))
    assert outcome.stored is True and outcome.succeeded is True and outcome.answer_refused is None
    store = F.EvidenceStore(tmp_path / "evidence")
    text = store.path_for(SITE, "sitelink.dewiki").read_text(encoding="utf-8")
    permalink = f"https://de.wikipedia.org/w/index.php?title=Areni-1&oldid={REVID}"
    assert text == (
        f'Wikipedia (dewiki) article "Areni-1", revision {REVID} ({permalink}), as plain text '
        f"through the MediaWiki extracts API:\n\n{TEXT}\n"
    )
    raw = tmp_path / "evidence_raw"
    assert json.loads(next(raw.iterdir()).read_bytes())["query"]["pages"][0]["extract"] == TEXT
    assert [line["given_up"] for line in _lines(tmp_path)] == [False]


# ── the record names the articles, and every one of them is bought ────────────────────────────


def test_every_named_article_becomes_a_target_after_the_name_route() -> None:
    targets = F.targets_for_site(_record(**{F.WIKI_SITELINKS_KEY: [dict(DE), dict(ES)]}))
    assert [t.feature for t in targets] == [
        F.FEATURE_ENWIKI,
        "sitelink.dewiki",
        "sitelink.eswiki",
        F.FEATURE_WIKIDATA_ENTITY,
    ]
    de = targets[1]
    assert de.url == f"https://de.wikipedia.org/w/index.php?title=Areni-1&oldid={REVID}"
    assert de.qid == QID and de.sitelink == F.WikiSitelink("dewiki", "de", "Areni-1", REVID)
    assert de.request_url == F.wikipedia_article_url("de", "Areni-1")


def test_a_record_whose_findings_buy_no_article_route_refuses_its_named_articles() -> None:
    """The articles ride on the `enwiki` slot; a record whose findings never reach that slot (only a
    T02 finding, which buys nothing) would drop them without a word - and the transport count reads
    the same targets, so nobody would notice."""
    record = _record(findings=[{**SP.finding_row("country", "Armenia"), "test_id": "T02"}])
    with pytest.raises(InputError, match="names articles no finding buys"):
        F.targets_for_site(record)


def test_a_record_without_articles_buys_exactly_the_targets_it_always_bought() -> None:
    record = _record()
    del record[F.WIKI_SITELINKS_KEY]
    targets = F.targets_for_site(record)
    assert [t.feature for t in targets] == [F.FEATURE_ENWIKI, F.FEATURE_WIKIDATA_ENTITY]
    assert all(t.sitelink is None for t in targets)


def test_the_articles_come_after_the_english_sitelink_and_before_the_narrowed_claims() -> None:
    record = _record(enwiki_sitelink={"qid": QID, "title": "Areni-1 cave"}, wikidata_route="narrow")
    features = [t.feature for t in F.targets_for_site(record)]
    assert features[:3] == [F.FEATURE_ENWIKI, F.FEATURE_ENWIKI_SITELINK, "sitelink.dewiki"]
    assert features[3] == F.FEATURE_WIKIDATA_TRUTHY


# ── the record's list of articles is read strictly ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "not a list of 1 to 3 articles"),
        (
            [dict(DE), dict(ES), {**DE, "wiki": "frwiki", "lang": "fr"}, {**DE, "wiki": "itwiki"}],
            "not a list of 1 to 3",
        ),
        (dict(DE), "not a list of 1 to 3"),
        ([{**DE, "badges": []}], "not \\{wiki, lang, title, revid\\}"),
        ([{k: v for k, v in DE.items() if k != "revid"}], "not \\{wiki, lang, title, revid\\}"),
        (["dewiki"], "not \\{wiki, lang, title, revid\\}"),
        ([{**DE, "wiki": "de"}], "is not a Wikipedia site id"),
        ([{**DE, "wiki": "enwiki", "lang": "en"}], "is English"),
        ([{**DE, "wiki": "simplewiki", "lang": "simple"}], "is English"),
        ([{**DE, "wiki": "cebwiki", "lang": "ceb"}], "bot-generated"),
        ([{**DE, "wiki": "warwiki", "lang": "war"}], "bot-generated"),
        ([{**DE, "wiki": "arzwiki", "lang": "arz"}], "bot-generated"),
        ([{**DE, "wiki": "cewiki", "lang": "ce"}], "bot-generated"),
        ([{**DE, "wiki": "lldwiki", "lang": "lld"}], "bot-generated"),
        ([{**DE, "wiki": "zh_min_nanwiki", "lang": "zh-min-nan"}], "bot-generated"),
        ([{**DE, "wiki": "cowiki", "lang": "co"}], "bot-generated"),
        ([{**DE, "lang": "de.example.org"}], "not a Wikipedia language subdomain"),
        ([{**DE, "lang": "DE"}], "not a Wikipedia language subdomain"),
        ([{**DE, "title": "  "}], "carries no title"),
        ([{**DE, "title": None}], "carries no title"),
        ([{**DE, "revid": 0}], "pins revision 0"),
        ([{**DE, "revid": True}], "pins revision True"),
        ([{**DE, "revid": "268759019"}], "pins revision '268759019'"),
        ([dict(DE), {**DE, "title": "Areni"}], "dewiki is named twice"),
    ],
)
def test_a_damaged_list_of_articles_is_refused_not_read(value: Any, message: str) -> None:
    """The reader refuses on its own, before any address is built from the entry (a permalink would
    refuse a bad subdomain too, later, and hide a reader that let it through)."""
    record = _record(**{F.WIKI_SITELINKS_KEY: value})
    with pytest.raises(InputError, match=message):
        F.read_wiki_sitelinks(record, SITE)
    with pytest.raises(InputError, match=message):
        F.targets_for_site(record)


def test_articles_on_a_record_without_an_item_are_refused() -> None:
    record = _record()
    del record["wikidata_qid"]
    with pytest.raises(InputError, match="without a wikidata_qid"):
        F.targets_for_site(record)


def test_the_bot_generated_and_english_wikis_are_the_named_ones() -> None:
    assert F.BOT_GENERATED_WIKIS == {
        "cebwiki",
        "warwiki",
        "arzwiki",
        "cewiki",
        "lldwiki",
        "zh_min_nanwiki",
        "cowiki",
    }
    assert F.ENGLISH_WIKIS == {"enwiki", "simplewiki"}
    assert F.MAX_WIKI_SITELINKS == 3


# ── the addresses ─────────────────────────────────────────────────────────────────────────────


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def test_the_article_request_asks_for_plain_text_last_and_follows_no_redirect() -> None:
    url = F.wikipedia_article_url("de", "Areni-1")
    assert url.startswith("https://de.wikipedia.org/w/api.php?")
    query = _query(url)
    assert query["action"] == ["query"] and query["formatversion"] == ["2"]
    assert query["prop"] == ["info|revisions|pageprops|extracts"]
    assert query["explaintext"] == ["1"] and query["rvprop"] == ["ids"]
    assert query["ppprop"] == ["wikibase_item|disambiguation"]
    assert query["titles"] == ["Areni-1"]
    assert "redirects" not in query


def test_the_pin_request_takes_one_to_fifty_titles_and_no_text() -> None:
    url = F.wikipedia_pages_url("zh-min-nan", ["A", "B"])
    assert url.startswith("https://zh-min-nan.wikipedia.org/w/api.php?")
    query = _query(url)
    assert query["titles"] == ["A|B"] and query["prop"] == ["info|revisions|pageprops"]
    assert "redirects" not in query and "explaintext" not in query
    F.wikipedia_pages_url("de", [f"T{n}" for n in range(50)])
    for count in (0, 51):
        with pytest.raises(InputError, match="1 to 50 per request"):
            F.wikipedia_pages_url("de", [f"T{n}" for n in range(count)])


def test_a_host_nobody_named_is_never_built() -> None:
    for lang in ("de.example.org", "de/", "", "-de", "de-"):
        for build in (
            lambda: F.wikipedia_api_url(lang),
            lambda: F.wikipedia_permalink(lang, "Areni-1", REVID),
        ):
            with pytest.raises(InputError, match="not a Wikipedia language subdomain"):
                build()


def test_the_permalink_names_one_revision_in_the_one_spelling_of_the_project() -> None:
    assert F.wikipedia_permalink("de", "Höhle von Areni (Armenien)", 5) == (
        "https://de.wikipedia.org/w/index.php?title=H%C3%B6hle_von_Areni_(Armenien)&oldid=5"
    )
    assert F.WikiSitelink("dewiki", "de", "Areni-1", REVID).permalink == (
        f"https://de.wikipedia.org/w/index.php?title=Areni-1&oldid={REVID}"
    )


def test_every_sitelink_of_an_item_is_asked_with_its_url_for_the_lane() -> None:
    lane = _query(F.wikidata_sitelinks_url(["Q1", "Q2"], all_wikis=True))
    assert lane["props"] == ["sitelinks/urls"] and "sitefilter" not in lane
    english = _query(F.wikidata_sitelinks_url(["Q1"]))
    assert english["props"] == ["sitelinks"] and english["sitefilter"] == ["enwiki"]


# ── the item's sitelinks, read ───────────────────────────────────────────────────────────────


def _entities(**items: Any) -> bytes:
    return json.dumps({"entities": items}).encode("utf-8")


def _link(title: str, url: str | None = None, *badges: str) -> dict[str, Any]:
    link: dict[str, Any] = {"title": title, "badges": list(badges)}
    if url is not None:
        link["url"] = url
    return link


def test_every_sitelink_of_every_item_is_read_with_its_url_and_badges() -> None:
    answer = F.item_sitelinks_from_answer(
        _entities(
            Q1={
                "sitelinks": {
                    "dewiki": _link("Areni-1", "https://de.wikipedia.org/wiki/Areni-1"),
                    "enwiki": _link("Areni-1 cave", None, "Q70893996"),
                }
            },
            Q2={"sitelinks": {}},
        )
    )
    assert answer["Q1"]["dewiki"] == F.Sitelink(
        "Areni-1", (), "https://de.wikipedia.org/wiki/Areni-1"
    )
    assert answer["Q1"]["enwiki"].url is None
    assert answer["Q1"]["enwiki"].redirect_badges() == ["Q70893996 sitelink to redirect"]
    assert answer["Q2"] == {}
    assert F.enwiki_sitelinks_from_answer(
        _entities(Q1={"sitelinks": {"enwiki": _link("Areni-1 cave")}}, Q2={"sitelinks": {}})
    ) == {"Q1": F.Sitelink("Areni-1 cave", ()), "Q2": None}


def test_a_sitelink_url_that_is_not_text_is_refused() -> None:
    for url in ("", 5, ["https://de.wikipedia.org/wiki/A"]):
        body = _entities(Q1={"sitelinks": {"dewiki": {"title": "A", "badges": [], "url": url}}})
        with pytest.raises(F.EvidenceUnrenderable, match="url is"):
            F.item_sitelinks_from_answer(body)


def test_an_item_wikidata_says_does_not_exist_is_refused() -> None:
    with pytest.raises(F.EvidenceUnrenderable, match="does not exist"):
        F.item_sitelinks_from_answer(_entities(Q1={"id": "Q1", "missing": ""}))


# ── the answer, read whole or cut ─────────────────────────────────────────────────────────────


def test_a_whole_answer_is_its_page_and_its_extract() -> None:
    answer = F.read_wiki_article(_body(_page()), truncated=False, what="t")
    assert answer.extract == TEXT and answer.cut is False
    assert "extract" not in answer.page and answer.page["lastrevid"] == REVID


def test_an_answer_that_is_not_one_page_is_refused() -> None:
    for payload in (
        {"query": {"pages": []}},
        {"query": {"pages": [_page(), _page(title="B")]}},
        {"query": "pages"},
        {"query": {"pages": ["Areni-1"]}},
        ["query"],
    ):
        with pytest.raises(F.EvidenceUnrenderable, match="no single page"):
            F.read_wiki_article(json.dumps(payload).encode(), truncated=False, what="t")


def _cut(body: bytes, keep: int) -> bytes:
    return body[:keep]


def test_a_cut_answer_is_read_as_its_whole_metadata_and_the_extract_up_to_the_cut() -> None:
    long_text = "Höhle " * 20_000
    body = _body(_page(extract=long_text))
    cut = _cut(body, F.MAX_PAGE_BYTES)
    answer = F.read_wiki_article(cut, truncated=True, what="t")
    assert answer.cut is True and answer.page["lastrevid"] == REVID
    assert long_text.startswith(answer.extract) and len(answer.extract) > 10_000


def test_a_cut_that_splits_an_escape_or_a_character_drops_only_the_split_part() -> None:
    page = _page(extract="abécd")
    ascii_body = json.dumps({"query": {"pages": [page]}}, separators=(",", ":")).encode()
    start = ascii_body.index(b"\\u00e9")
    for keep in range(start + 1, start + 6):  # inside the six characters of the escape
        assert F.read_wiki_article(ascii_body[:keep], truncated=True, what="t").extract == "ab"
    utf8_body = _body(page)
    at = utf8_body.index("é".encode())
    assert F.read_wiki_article(utf8_body[: at + 1], truncated=True, what="t").extract == "ab"
    escaped = json.dumps(
        {"query": {"pages": [_page(extract='say "x"')]}}, separators=(",", ":")
    ).encode()
    quote_at = escaped.index(b'\\"x')
    assert F.read_wiki_article(escaped[: quote_at + 1], truncated=True, what="t").extract == "say "


def test_a_cut_that_falls_in_the_closing_brackets_keeps_the_whole_extract() -> None:
    body = _body(_page())
    answer = F.read_wiki_article(body[:-2], truncated=True, what="t")
    assert answer.extract == TEXT and answer.cut is True


def test_a_cut_answer_that_is_not_the_requested_shape_is_refused() -> None:
    body = _body(_page())
    cases = [
        (body[: body.index(b'"extract"')], "cut before its extract began"),
        (b'{"extract":"' + TEXT.encode(), "cut before its extract began"),
        (b'{"query":{"pages":[{"title":' + b',"extract":"abc', "metadata is not JSON"),
        (body[: body.index(b'"extract"') + 11] + b"\xff\xfe" + b"a" * 10, "not UTF-8"),
        (body[: body.index(b'"extract"') + 11] + b"ab\\xcdefghij", "is not a JSON string"),
    ]
    for cut, message in cases:
        with pytest.raises(F.EvidenceUnrenderable, match=message):
            F.read_wiki_article(cut, truncated=True, what="t")


# ── is it the pinned article? ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"missing": True, "revisions": None, "lastrevid": None}, "has no article 'Areni-1'"),
        ({"title": "Areni 1"}, "the answer is for 'Areni 1', not 'Areni-1'"),
        ({"redirect": True}, "'Areni-1' is a redirect, not an article"),
        (
            {"pageprops": {"wikibase_item": QID, "disambiguation": ""}},
            "'Areni-1' is a disambiguation page",
        ),
        ({"pageprops": {"wikibase_item": "Q5"}}, "names the Wikidata item 'Q5', not 'Q1007510'"),
        ({"pageprops": None}, "names the Wikidata item None"),
        ({"lastrevid": REVID + 1}, f"at revision {REVID} \\(latest {REVID + 1}\\)"),
        ({"revisions": [{"revid": REVID - 1}]}, f"at revision {REVID - 1} \\(latest {REVID}\\)"),
        ({"extract": "  "}, "'Areni-1' carries no text"),
        ({"extract": None}, "'Areni-1' carries no text"),
    ],
)
def test_an_answer_that_is_not_the_pinned_article_is_refused_with_the_reason(
    changes: dict[str, Any], reason: str
) -> None:
    answer = F.read_wiki_article(_body(_page(**changes)), truncated=False, what="t")
    refused = F.wiki_article_refusal(_target(), answer)
    assert refused is not None
    assert __import__("re").search(reason, refused), refused


def test_the_pinned_article_is_not_refused() -> None:
    answer = F.read_wiki_article(_body(_page()), truncated=False, what="t")
    assert F.wiki_article_refusal(_target(), answer) is None


def test_a_page_the_answer_cannot_describe_is_a_contract_break() -> None:
    target = _target()
    for changes, message in (
        ({"invalid": True, "invalidreason": "bad title"}, "calls 'Areni-1' invalid"),
        ({"revisions": None}, "carries no revision"),
        ({"revisions": []}, "carries no revision"),
        ({"lastrevid": None}, "lastrevid None"),
        ({"lastrevid": True}, "lastrevid True"),
        ({"revisions": [{"revid": "1"}]}, "revision '1'"),
        ({"pageprops": ["wikibase_item"]}, "pageprops"),
    ):
        answer = F.read_wiki_article(_body(_page(**changes)), truncated=False, what="t")
        with pytest.raises(F.EvidenceUnrenderable, match=message):
            F.wiki_article_refusal(target, answer)


def test_only_a_sitelink_target_is_checked_and_rendered_as_an_article() -> None:
    record = _record()
    english = next(t for t in F.targets_for_site(record) if t.feature == F.FEATURE_ENWIKI)
    answer = F.read_wiki_article(_body(_page()), truncated=False, what="t")
    with pytest.raises(InputError, match="not a sitelink target"):
        F.wiki_article_refusal(english, answer)
    page = F.FetchedPage(status=200, final_url="u", body=b"not json at all", truncated=False)
    assert F.answer_refusal(english, page) is None
    refused = F.read_wiki_article(_body(_page(redirect=True)), truncated=False, what="t")
    with pytest.raises(InputError, match="only the pinned article's own answer is rendered"):
        F.render_wiki_article(_target(), refused)


# ── stored as plain text, a cut one marked ────────────────────────────────────────────────────


def test_a_cut_article_is_stored_as_far_as_it_was_read_with_the_truncation_marker(
    tmp_path: Path,
) -> None:
    long_text = "Höhle " * 20_000
    cut = _body(_page(extract=long_text))[: F.MAX_PAGE_BYTES]
    outcome = _attempt(tmp_path, _Answers(cut, truncated=True))
    assert outcome.stored is True and outcome.truncated is True
    text = F.EvidenceStore(tmp_path / "evidence").path_for(SITE, "sitelink.dewiki")
    stored = text.read_text(encoding="utf-8")
    assert stored.endswith(F.TRUNCATION_MARKER)
    body = stored[: -len(F.TRUNCATION_MARKER)]
    assert body.startswith('Wikipedia (dewiki) article "Areni-1"')
    assert long_text.startswith(body.split("\n\n", 1)[1].rstrip("\n"))
    raw = next((tmp_path / "evidence_raw").iterdir()).read_bytes()
    assert raw == cut


def test_a_failed_answer_is_retried_and_never_read_as_an_article(tmp_path: Path) -> None:
    fetcher = _Answers(b"busy", b"busy", _body(_page()), status=503)
    outcome = _attempt(tmp_path, fetcher)
    assert len(fetcher.asked) == F.MAX_ATTEMPTS
    assert outcome.answer_refused is None and outcome.stored is False
    assert [line["given_up"] for line in _lines(tmp_path)][-1] is True


def test_the_judge_reads_a_refused_article_as_that_targets_failure(tmp_path: Path) -> None:
    """collect_batch records the refusal in `fetch.json`; the finder's prompt then names the article
    as failed instead of raising on a missing file (`model_stage.read_fetch_failures`)."""
    record = _record(**{F.WIKI_SITELINKS_KEY: [dict(DE), dict(ES)]})

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if urlsplit(url).path == "/":
            return httpx.Response(200, content=b"root")
        host = urlsplit(url).netloc
        if host == "de.wikipedia.org":
            return httpx.Response(200, content=_body(_page()))
        if host == "es.wikipedia.org":
            edited = _page(title="Cueva Areni-1", lastrevid=9, revisions=[{"revid": 9}])
            return httpx.Response(200, content=_body(edited))
        if host == "en.wikipedia.org":
            return httpx.Response(200, content=b"English article")
        return httpx.Response(200, content=b'{"entities": {}}')

    store = F.EvidenceStore(tmp_path / "evidence")
    with F.HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        report = F.collect_batch(
            batch={"batch_id": "slkg-0001", "sites": [record]},
            fetcher=fetcher,
            store=store,
            ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
            stage=Stage.FINDER,
            sleep=lambda _seconds: None,
        )
    (tmp_path / "fetch.json").write_text(report.to_json(), encoding="utf-8")
    failures = MS.read_fetch_failures(tmp_path / "fetch.json")
    assert list(failures[SITE]) == ["sitelink.eswiki"]
    assert "answer refused" in failures[SITE]["sitelink.eswiki"]
    excerpts = MS.evidence_excerpts(
        site_id=SITE, site=record, store=store, hit_pages=False, failures=failures[SITE]
    )
    by_feature = {e.feature: e for e in excerpts}
    assert by_feature["sitelink.dewiki"].text is not None
    assert by_feature["sitelink.eswiki"].text is None and by_feature["sitelink.eswiki"].failure
