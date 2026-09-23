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

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
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
        {"batchcomplete": True, "query": {"pages": [page]}}, ensure_ascii=False, separators=(",", ":")
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
