"""Does S1 pin the right article, judge its subject, and refuse the rest? (WB-A2, WB-A1 wiring)

Three modules of Track A: `phase4/licences.py` (the licence registry, the deny list, the mirror
detector), `phase4/subject_gate.py` (the own/shared/wrong/none verdict) and
`phase4/sources_stage.py` (the enwiki query, the Wikidata witness, the P31 label pass, the holds).
Nothing here opens a socket: the network is `httpx.MockTransport` behind the real
`fetch_stage.HttpFetcher`, so the real cap, the real retry loop and the real ledger lines run, and a
URL the test did not script is a test failure, not an empty answer. Each guard has a test that goes
red without it; the mutation cases are `PHASE4_SOURCES_MUTATIONS` in
`scripts/remediation/phase3/mutation_sweep.py`.

The expected values are copied from the design (entry [6] of
`output/remediation/logs/design_texts_images_2026-09-22.json`), not from the modules.
"""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase4 import licences as LIC  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import sources_stage as S1  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402

from pipeline.lyra.blocked_domains import BLOCKED_DOMAINS  # noqa: E402

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
CUR = "2026-09-22T12:00:00Z"
OLD = "2026-07-19T17:30:40Z"
SITE_ID = "4a5a324f-1111-4000-8000-000000000001"
OTHER_ID = "4a5a324f-2222-4000-8000-000000000002"
QID = "Q1064331"
POINT = (35.8686, 14.5117)
EXTRACT = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta. They date to "
    "approximately 3150 BC.\n\n\n== Description ==\nThe complex consists of four structures."
)
#: The design's permalink form (source_store): `...index.php?title=<T>&oldid=<revid>`.
PERMALINK = "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=100"


# ------------------------------------------------------------------------------------ builders


def plan_site(**over: Any) -> M.PlanSite:
    base: dict[str, Any] = {
        "site_id": SITE_ID,
        "name": "Tarxien Temples",
        "aliases": (),
        "country": "Malta",
        "site_type": "Temple complex",
        "period_start": -3150,
        "period_end": -2500,
        "lat": POINT[0],
        "lon": POINT[1],
        "description": "old text",
        "description_sha256": M.text_sha256("old text"),
        "raw_data": None,
        "raw_data_sha256": None,
        "card": None,
        "card_sha256": None,
        "source_url": "https://en.wikipedia.org/wiki/Tarxien_Temples",
        "wikidata_qid": QID,
        "enwiki_title": "Tarxien Temples",
        "snapshot_description": None,
        "flags": frozenset(),
    }
    base.update(over)
    return M.PlanSite(**base)


def page_dict(
    title: str = "Tarxien Temples",
    *,
    pageid: int = 12129747,
    revid: int = 100,
    lastrevid: int | None = None,
    timestamp: str = OLD,
    extract: str | None = EXTRACT,
    qid: str | None = QID,
    coords: tuple[float, float] | None = POINT,
    disambiguation: bool = False,
    ns: int = 0,
) -> dict[str, Any]:
    """One page object of the S1 query answer, in the shape measured on 2026-09-23."""
    page: dict[str, Any] = {
        "pageid": pageid,
        "ns": ns,
        "title": title,
        "revisions": [{"revid": revid, "parentid": revid - 1, "timestamp": timestamp}],
        "contentmodel": "wikitext",
        "lastrevid": revid if lastrevid is None else lastrevid,
        "length": 10304,
    }
    props: dict[str, str] = {}
    if qid is not None:
        props["wikibase_item"] = qid
    if disambiguation:
        props["disambiguation"] = ""
    if props:
        page["pageprops"] = props
    if coords is not None:
        page["coordinates"] = [
            {"lat": coords[0], "lon": coords[1], "primary": True, "globe": "earth"}
        ]
    if extract is not None:
        page["extract"] = extract
    return page


def article_answer(*, cur: str = CUR, missing_title: str | None = None, **page: Any) -> bytes:
    if missing_title is not None:
        pages = [{"ns": 0, "title": missing_title, "missing": True}]
    else:
        pages = [page_dict(**page)]
    return json.dumps(
        {"batchcomplete": True, "curtimestamp": cur, "query": {"pages": pages}}
    ).encode("utf-8")


def _snak(pid: str, value: Any, kind: str) -> dict[str, Any]:
    return {"snaktype": "value", "property": pid, "datavalue": {"value": value, "type": kind}}


def entity_dict(
    qid: str = QID,
    *,
    p31: Iterable[str] = ("Q839954",),
    p279: str | None = None,
    p279_rank: str = "normal",
    p625: tuple[float, float, float | None] | None = None,
    labels: Mapping[str, str] | None = None,
    aliases: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "P31": [
            {
                "mainsnak": _snak("P31", {"entity-type": "item", "id": cls}, "wikibase-entityid"),
                "rank": "normal",
            }
            for cls in p31
        ]
    }
    if p279 is not None:
        claims["P279"] = [
            {
                "mainsnak": _snak("P279", {"entity-type": "item", "id": p279}, "wikibase-entityid"),
                "rank": p279_rank,
            }
        ]
    if p625 is not None:
        lat, lon, precision = p625
        value = {"latitude": lat, "longitude": lon, "precision": precision, "globe": "Q2"}
        claims["P625"] = [{"mainsnak": _snak("P625", value, "globecoordinate"), "rank": "normal"}]
    entity: dict[str, Any] = {
        "type": "item",
        "id": qid,
        "labels": {
            lang: {"language": lang, "value": value}
            for lang, value in (labels or {"en": "Tarxien Temples"}).items()
        },
        "claims": claims,
    }
    if aliases is not None:
        entity["aliases"] = {
            lang: [{"language": lang, "value": value} for value in values]
            for lang, values in aliases.items()
        }
    return entity


def entity_answer(qid: str = QID, *, cur: str | None = None, **entity: Any) -> bytes:
    """A wbgetentities answer; `cur` adds the server clock `curtimestamp=1` asks for."""
    payload: dict[str, Any] = {"entities": {qid: entity_dict(qid, **entity)}}
    if cur is not None:
        payload["curtimestamp"] = cur
    return json.dumps(payload).encode("utf-8")


def labels_answer(labels: Mapping[str, str]) -> bytes:
    return json.dumps(
        {
            "entities": {
                qid: {
                    "type": "item",
                    "id": qid,
                    "labels": {"en": {"language": "en", "value": label}} if label else {},
                }
                for qid, label in labels.items()
            },
            "success": 1,
        }
    ).encode("utf-8")


# ---------------------------------------------------------------------------------- the network


def _key(url: str) -> str:
    return str(httpx.URL(url))


class Web:
    """The network, scripted: an exact URL gets its answer; a host root answers the probe.

    A URL nobody scripted raises inside the transport, which `HttpFetcher` does not catch - the test
    fails instead of reading a silent empty answer. `down` hosts fail at the transport, like a reset.
    """

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, bytes, str | None]] = {}
        self.calls: list[str] = []
        self.down: set[str] = set()
        self.dead: set[str] = set()

    def add(self, url: str, body: bytes = b"", *, status: int = 200, redirect: str | None = None):
        self.routes[_key(url)] = (status, body, redirect)
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if request.url.host in self.down or url in self.dead:
            raise httpx.ConnectError("connection reset", request=request)
        if request.url.path == "/" and not request.url.query:
            return httpx.Response(200, content=b"root")
        if url not in self.routes:
            raise AssertionError(f"an unscripted request: {url}")
        status, body, redirect = self.routes[url]
        if redirect is not None:
            return httpx.Response(302, headers={"location": redirect})
        return httpx.Response(status, content=body)

    def fetcher(self) -> S1.HostCappedFetcher:
        transport = httpx.MockTransport(self.handler)
        return S1.HostCappedFetcher(
            wiki=F.HttpFetcher(transport=transport, max_bytes=S1.WIKI_MAX_BYTES),
            web=F.HttpFetcher(transport=transport),
        )

    def asked(self, fragment: str) -> list[str]:
        return [call for call in self.calls if fragment in call]


def make_batch(root: Path, sites: list[M.PlanSite], *, batch_id: str = "p4-0001") -> Path:
    batch_dir = root / "run" / batch_id
    batch_dir.mkdir(parents=True)
    batch = R.Batch(batch_id=batch_id, ordinal=1, sites=tuple(s.to_dict() for s in sites))
    (batch_dir / M.INPUT_FILE).write_text(batch.to_json() + "\n", encoding="utf-8")
    return batch_dir


def phase3_file(root: Path, site_id: str, body: bytes, *, batch: str = "batch-0007") -> Path:
    evidence = root / "phase3" / batch / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    path = evidence / f"{F.EvidenceStore.slug(site_id, F.FEATURE_WIKIDATA_ENTITY)}.txt"
    path.write_bytes(body)
    os.utime(path, (1_790_000_000, 1_790_000_000))
    return path


def run_sources(tmp_path: Path, batch_dir: Path, web: Web, *, now: datetime = NOW) -> int:
    pauses: list[float] = []
    return S1.sources_batch(
        batch_dir,
        ledger=tmp_path / "LEDGER.jsonl",
        fetcher=web.fetcher(),
        now=now,
        phase3_run=tmp_path / "phase3",
        sleep=pauses.append,
    )


def standard_web(
    *,
    site: M.PlanSite | None = None,
    article: bytes | None = None,
    labels: Mapping[str, str] | None = None,
) -> Web:
    site = site or plan_site()
    web = Web()
    web.add(S1.article_url("en", str(site.enwiki_title)), article or article_answer())
    web.add(
        S1.class_labels_url(sorted(labels or {"Q839954": "archaeological site"})),
        labels_answer(labels or {"Q839954": "archaeological site"}),
    )
    return web


def store_of(batch_dir: Path) -> F.EvidenceStore:
    return F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)


def report_of(batch_dir: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads((batch_dir / S1.SOURCES_REPORT).read_text(encoding="utf-8"))
    return {row["site_id"]: row for row in payload["sites"]}


def holds_of(batch_dir: Path) -> list[M.Hold]:
    return M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold)


# ================================================================================== licences.py


@pytest.mark.parametrize(
    ("url", "licence"),
    [
        ("https://en.wikipedia.org/wiki/Stonehenge", M.Licence.CC_BY_SA_4),
        ("https://fr.wikipedia.org/wiki/Stonehenge", M.Licence.CC_BY_SA_4),
        ("https://en.m.wikipedia.org/wiki/Stonehenge", M.Licence.CC_BY_SA_4),
        ("https://www.wikidata.org/wiki/Q39671", M.Licence.CC0),
        ("https://query.wikidata.org/sparql", M.Licence.CC0),
        ("https://www.english-heritage.org.uk/visit/places/stonehenge/", M.Licence.RESTRICTED),
        ("https://wikipedia.org.example.com/x", M.Licence.RESTRICTED),
    ],
)
def test_the_licence_of_a_page_follows_its_host(url: str, licence: M.Licence) -> None:
    assert LIC.licence_of(url) is licence


def test_a_url_without_an_http_host_has_no_licence() -> None:
    for url in ("ftp://en.wikipedia.org/x", "wikipedia.org/wiki/X", "https:///x"):
        with pytest.raises(ValueError, match="not an http"):
            LIC.licence_of(url)


def test_only_wikipedia_and_wikidata_are_wiki_hosts() -> None:
    assert LIC.is_wiki_host("en.wikipedia.org")
    assert LIC.is_wiki_host("zh-min-nan.wikipedia.org")
    assert LIC.is_wiki_host("www.wikidata.org")
    assert not LIC.is_wiki_host("wikipedia.org.example.com")
    assert not LIC.is_wiki_host("notwikipedia.org")
    assert not LIC.is_wiki_host("commons.wikimedia.org")


@pytest.mark.parametrize(
    "url",
    [
        "https://grokipedia.com/page/Stonehenge",
        "https://www.aroundus.com/p/stonehenge",
        "https://mindtrip.ai/attraction/stonehenge",
        "https://evendo.com/x",
        "https://wanderlog.com/place/details/1",
    ],
)
def test_the_ai_aggregators_the_design_names_are_denied(url: str) -> None:
    assert LIC.deny_family(url) == LIC.FAMILY_AI_AGGREGATOR


@pytest.mark.parametrize(
    "url",
    [
        "https://kids.kiddle.co/Stonehenge",
        "https://www.wikiwand.com/en/Stonehenge",
        "https://dbpedia.org/page/Stonehenge",
        "https://alchetron.com/Stonehenge",
        "https://wiki2.org/en/Stonehenge",
        "https://en.everybodywiki.com/Stonehenge",
        "https://infogalactic.com/info/Stonehenge",
        "https://www.wikishire.co.uk/wiki/Stonehenge",
    ],
)
def test_the_wikipedia_mirrors_are_counted_as_the_wikimedia_family(url: str) -> None:
    assert LIC.deny_family(url) == LIC.FAMILY_WIKIMEDIA


def test_a_blocked_domain_and_our_own_site_are_denied() -> None:
    blocked = sorted(BLOCKED_DOMAINS)[0]
    assert LIC.deny_family(f"https://www.{blocked}/x") == LIC.FAMILY_BLOCKED
    assert LIC.deny_family("https://ancientnerds.com/sites/mt/tarxien") == LIC.FAMILY_OWN_SITE


def test_hosts_are_matched_by_label_never_by_substring() -> None:
    for url in (
        "https://notgrokipedia.com/x",
        "https://grokipedia.com.example.org/x",
        "https://en.wikipedia.org/wiki/Kiddle",
        "https://www.english-heritage.org.uk/x",
    ):
        assert LIC.deny_family(url) is None, url


def test_the_deny_list_is_versioned() -> None:
    assert isinstance(LIC.LICENCES_VERSION, str) and LIC.LICENCES_VERSION.strip()


def _words(count: int, start: int = 0) -> str:
    return " ".join(f"w{index}" for index in range(start, start + count))


def test_a_shared_run_of_25_words_is_a_mirror_and_24_is_not() -> None:
    wiki = "Intro. " + _words(40) + " end."
    assert LIC.is_mirror("Copied: " + _words(25, start=5) + " (mirror)", wiki)
    assert not LIC.is_mirror("Copied: " + _words(24, start=5) + " (mirror)", wiki)


def test_case_punctuation_and_line_breaks_do_not_hide_a_copy() -> None:
    """The detector reads the page's extracted text (lane R stores it through
    `extract_text_from_html`), so what may differ is case, punctuation and line breaks."""
    wiki = _words(30).upper()
    page = "(" + _words(30).replace(" w10 ", ",\n w10 - ") + ")."
    assert LIC.is_mirror(page, wiki)
    assert LIC.is_mirror(wiki, page)


def test_an_empty_wikipedia_text_mirrors_nothing() -> None:
    assert not LIC.is_mirror(_words(40), "")


# ================================================================================ subject_gate.py


def gate(
    site: M.PlanSite | None = None,
    *,
    page: dict[str, Any] | None = None,
    entity: dict[str, Any] | None | bool = True,
    labels: Mapping[str, str] | None = None,
    shared_qids: frozenset[str] = frozenset(),
    shared_titles: frozenset[str] = frozenset(),
) -> M.SubjectGate:
    return SG.subject_gate(
        site or plan_site(),
        page=page if page is not None else page_dict(),
        entity=entity_dict() if entity is True else (entity or None),
        class_labels=labels if labels is not None else {"Q839954": "archaeological site"},
        shared_qids=shared_qids,
        shared_titles=shared_titles,
    )


def test_an_own_article_matches_the_qid_the_place_and_is_no_class() -> None:
    result = gate()

    assert result.verdict is M.SubjectVerdict.OWN
    assert (result.qid_match, result.shared, result.concept, result.place_item) == (
        True,
        False,
        False,
        False,
    )
    assert result.km == 0.0
    assert result.name_score == 100.0


def test_a_qid_that_is_not_the_articles_item_is_no_own_article() -> None:
    far = page_dict(qid="Q999", coords=None)
    assert gate(page=far).verdict is M.SubjectVerdict.NONE
    assert gate(page=far).qid_match is False


def test_a_shared_qid_or_title_makes_the_article_shared() -> None:
    assert gate(shared_qids=frozenset({QID})).verdict is M.SubjectVerdict.SHARED
    assert gate(shared_titles=frozenset({"Tarxien Temples"})).verdict is M.SubjectVerdict.SHARED
    resolved = page_dict(title="Tarxien (temples)")
    assert (
        gate(page=resolved, shared_titles=frozenset({"Tarxien (temples)"})).verdict
        is M.SubjectVerdict.SHARED
    )


def test_a_class_item_is_wrong_even_when_everything_else_matches() -> None:
    history = entity_dict(p279="Q1190554")
    result = gate(entity=history)
    assert (result.concept, result.verdict) == (True, M.SubjectVerdict.WRONG)


def test_a_deprecated_subclass_statement_does_not_make_a_class() -> None:
    assert (
        gate(entity=entity_dict(p279="Q5", p279_rank="deprecated")).verdict is M.SubjectVerdict.OWN
    )


def test_a_place_level_item_is_shared_unless_the_site_is_a_settlement() -> None:
    labels = {"Q15661340": "ancient city"}
    town = entity_dict(p31=("Q15661340",))
    temple = gate(entity=town, labels=labels)
    city = gate(plan_site(site_type="City/town/settlement"), entity=town, labels=labels)
    assert (temple.place_item, temple.verdict) == (True, M.SubjectVerdict.SHARED)
    assert (city.place_item, city.verdict) == (True, M.SubjectVerdict.OWN)


@pytest.mark.parametrize(
    "label", ["commune of France", "human settlement", "municipality of Spain", "neighborhood"]
)
def test_the_place_level_words_are_matched_as_whole_words(label: str) -> None:
    assert gate(entity=entity_dict(p31=("Q1",)), labels={"Q1": label}).place_item is True


def test_a_place_level_word_inside_another_word_is_not_one() -> None:
    assert gate(entity=entity_dict(p31=("Q1",)), labels={"Q1": "townland"}).place_item is False


def test_the_settlement_types_are_the_catalogues_own() -> None:
    assert SG.is_settlement_type("City/town/settlement")
    assert SG.is_settlement_type("Settlement")
    assert SG.is_settlement_type("City")
    assert not SG.is_settlement_type("Temple complex")
    assert not SG.is_settlement_type(None)


def test_an_article_more_than_25_km_away_is_wrong() -> None:
    far = page_dict(coords=(POINT[0] + 0.3, POINT[1]))  # about 33 km north
    result = gate(page=far)
    assert result.km is not None and 30 < result.km < 36
    assert result.verdict is M.SubjectVerdict.WRONG


def test_a_road_wall_or_aqueduct_is_wrong_only_beyond_50_km() -> None:
    far = page_dict(coords=(POINT[0] + 0.3, POINT[1]))
    farther = page_dict(coords=(POINT[0] + 0.5, POINT[1]))  # about 56 km
    for site_type in ("Road/avenue/trackway", "Wall", "Reservoir/aqueduct/canal"):
        site = plan_site(site_type=site_type)
        assert gate(site, page=far).verdict is M.SubjectVerdict.NONE
        assert gate(site, page=farther).verdict is M.SubjectVerdict.WRONG
    assert SG.wrong_km("Megalithic walls") == SG.WRONG_KM


def test_between_5_and_25_km_an_article_is_neither_own_nor_wrong() -> None:
    near = page_dict(coords=(POINT[0] + 0.09, POINT[1]))  # about 10 km
    assert gate(page=near).verdict is M.SubjectVerdict.NONE


def test_the_item_coordinates_stand_in_when_the_article_has_none() -> None:
    far_item = entity_dict(p625=(POINT[0] + 0.3, POINT[1], 0.0001))
    near_item = entity_dict(p625=(POINT[0] + 0.01, POINT[1], 0.0001))
    no_coords = page_dict(coords=None)
    assert gate(page=no_coords, entity=far_item).verdict is M.SubjectVerdict.WRONG
    assert gate(page=no_coords, entity=near_item).verdict is M.SubjectVerdict.OWN


def test_the_article_coordinates_come_before_the_items() -> None:
    far_item = entity_dict(p625=(POINT[0] + 0.3, POINT[1], 0.0001))
    assert gate(entity=far_item).verdict is M.SubjectVerdict.OWN


def test_a_coarse_p625_precision_widens_the_own_radius() -> None:
    eight_km = page_dict(coords=(POINT[0] + 0.072, POINT[1]))
    coarse = entity_dict(p625=(POINT[0], POINT[1], 0.1))  # 0.1 degree, about 11 km
    fine = entity_dict(p625=(POINT[0], POINT[1], 0.0001))
    assert gate(page=eight_km, entity=coarse).verdict is M.SubjectVerdict.OWN
    assert gate(page=eight_km, entity=fine).verdict is M.SubjectVerdict.NONE


def test_without_coordinates_a_directional_name_match_stands_in() -> None:
    no_coords = page_dict(coords=None)
    named = entity_dict(labels={"en": "Tarxien Temples"})
    other = entity_dict(labels={"en": "Ggantija"})
    assert gate(page=no_coords, entity=named).verdict is M.SubjectVerdict.OWN
    assert gate(page=no_coords, entity=other).verdict is M.SubjectVerdict.NONE


def test_a_name_that_is_only_a_subset_of_the_label_does_not_match() -> None:
    """The directional trap: token_set_ratio says 100 for 'Kilmartin' in the longer label."""
    site = plan_site(name="Kilmartin")
    label = entity_dict(labels={"en": "Kilmartin Glen standing stones"})
    result = gate(site, page=page_dict(coords=None), entity=label)
    assert result.name_score is not None and result.name_score < SG.NAME_MATCH_MIN
    assert result.verdict is M.SubjectVerdict.NONE


def test_names_are_compared_without_accents_and_aliases_count() -> None:
    assert SG.name_score(["Catalhoyuk"], ["Çatalhöyük"]) == 100.0
    site = plan_site(name="Templos de Tarxien", aliases=("Tarxien Temples",))
    no_coords = page_dict(coords=None)
    assert gate(site, page=no_coords).verdict is M.SubjectVerdict.OWN
    alias_only = entity_dict(labels={"en": "X"}, aliases={"es": ["Templos de Tarxien"]})
    assert gate(
        plan_site(name="Templos de Tarxien"), page=no_coords, entity=alias_only
    ).verdict is (M.SubjectVerdict.OWN)


def test_a_disambiguation_page_or_a_list_is_refused() -> None:
    assert gate(page=page_dict(disambiguation=True)).verdict is M.SubjectVerdict.NONE
    assert gate(page=page_dict(title="List of megalithic sites")).verdict is M.SubjectVerdict.NONE


def test_a_parent_page_within_reach_is_shared_and_a_distant_stranger_is_not() -> None:
    parent = page_dict(title="Stonehenge", qid="Q39671", coords=(POINT[0] + 0.02, POINT[1]))
    stranger = page_dict(title="Mercury", qid="Q308", coords=None)
    assert gate(page=parent).verdict is M.SubjectVerdict.SHARED
    assert gate(page=stranger).verdict is M.SubjectVerdict.NONE


def test_a_site_without_a_qid_and_without_its_pages_item_is_never_own() -> None:
    site = plan_site(wikidata_qid=None)
    assert gate(site, entity=None).verdict is M.SubjectVerdict.NONE


def test_a_site_without_a_qid_is_own_only_by_place_and_name_together() -> None:
    site = plan_site(wikidata_qid=None, name="Tarxien Temples")
    item = entity_dict(QID, labels={"en": "Something else"})
    own = gate(site, entity=item)
    assert (own.verdict, own.qid_match, own.name_score) == (M.SubjectVerdict.OWN, False, 100.0)
    other_name = gate(plan_site(wikidata_qid=None, name="Hagar Qim"), entity=item)
    assert other_name.verdict is M.SubjectVerdict.NONE
    eight_km = page_dict(coords=(POINT[0] + 0.072, POINT[1]))
    assert gate(site, page=eight_km, entity=item).verdict is M.SubjectVerdict.NONE
    no_coords = page_dict(coords=None)
    assert gate(site, page=no_coords, entity=item).verdict is M.SubjectVerdict.NONE


def test_a_qid_less_site_is_judged_on_its_pages_own_item_and_no_other() -> None:
    with pytest.raises(ValueError, match="judged on its page's item"):
        gate(plan_site(wikidata_qid=None), entity=entity_dict("Q42"))


def test_the_page_title_counts_as_a_name_only_for_a_qid_less_site() -> None:
    no_coords = page_dict(coords=None)
    item = entity_dict(QID, labels={"en": "Something else"})
    assert gate(page=no_coords, entity=item).verdict is M.SubjectVerdict.NONE


def test_a_class_the_label_pass_did_not_cover_raises() -> None:
    with pytest.raises(ValueError, match="no class label"):
        gate(entity=entity_dict(p31=("Q1", "Q2")), labels={"Q1": "temple"})


def test_a_missing_page_has_no_subject_to_judge() -> None:
    with pytest.raises(ValueError, match="missing page"):
        gate(page={"ns": 0, "title": "X", "missing": True})


# =============================================================================== the client (A1)


def test_the_wiki_hosts_get_the_1_mib_client_and_every_other_host_the_60_kb_one() -> None:
    body = b"x" * (200 * 1024)
    web = Web()
    web.add("https://en.wikipedia.org/w/api.php?x=1", body)
    web.add("https://www.wikidata.org/w/api.php?x=1", body)
    web.add("https://example.org/page", body)
    fetcher = web.fetcher()

    wiki = fetcher.get("https://en.wikipedia.org/w/api.php?x=1")
    data = fetcher.get("https://www.wikidata.org/w/api.php?x=1")
    page = fetcher.get("https://example.org/page")

    assert (len(wiki.body), wiki.truncated) == (len(body), False)
    assert (len(data.body), data.truncated) == (len(body), False)
    assert (len(page.body), page.truncated) == (F.MAX_PAGE_BYTES, True)


def test_the_live_fetcher_builds_one_client_per_cap_and_paces_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[dict[str, Any]] = []

    class Recording:
        def __init__(self, **kwargs: Any) -> None:
            built.append(kwargs)

        def close(self) -> None:
            built.append({"closed": True})

    monkeypatch.setattr(F, "HttpFetcher", Recording)
    with S1.open_fetcher(pacing_dir=tmp_path / "pacing") as fetcher:
        assert isinstance(fetcher, F.PacedFetcher)
    caps = [kwargs.get("max_bytes", F.MAX_PAGE_BYTES) for kwargs in built if "closed" not in kwargs]
    assert sorted(caps) == [F.MAX_PAGE_BYTES, S1.WIKI_MAX_BYTES]
    assert S1.WIKI_MAX_BYTES == 1024 * 1024
    assert sum("closed" in kwargs for kwargs in built) == 2


# ===================================================================================== the URLs


def test_the_article_query_is_the_designs_plus_the_server_clock() -> None:
    url = S1.article_url("en", "Tarxien Temples")
    parts = urlsplit(url)
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert (parts.scheme, parts.netloc, parts.path) == ("https", "en.wikipedia.org", "/w/api.php")
    assert query == {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
        "prop": "extracts|revisions|coordinates|pageprops|info",
        "explaintext": "1",
        "rvprop": "ids|timestamp",
        "ppprop": "wikibase_item|disambiguation",
        "curtimestamp": "1",
        "titles": "Tarxien Temples",
    }


def test_the_permalink_is_the_oldid_form_of_the_design() -> None:
    assert S1.permalink("en", "Tarxien Temples", 100) == PERMALINK
    assert S1.permalink("fr", "Temples de Tarxien", 7) == (
        "https://fr.wikipedia.org/w/index.php?title=Temples_de_Tarxien&oldid=7"
    )
    assert S1.permalink("en", "AT&T Building (Troy)", 3) == (
        "https://en.wikipedia.org/w/index.php?title=AT%26T_Building_(Troy)&oldid=3"
    )


def test_the_pinned_text_is_nfc_with_lf_line_ends() -> None:
    decomposed = unicodedata.normalize("NFD", "Ħal Saflieni\r\nČatalhöyük\rend")
    text = S1.pinned_text(decomposed)
    assert text == unicodedata.normalize("NFC", "Ħal Saflieni\nČatalhöyük\nend")
    assert "\r" not in text


# ====================================================================================== S1 stage


def _setup(tmp_path: Path, sites: list[M.PlanSite], **web: Any) -> tuple[Path, Web]:
    batch_dir = make_batch(tmp_path, sites)
    for site in sites:
        if site.wikidata_qid is not None:
            phase3_file(tmp_path, site.site_id, entity_answer(site.wikidata_qid))
    return batch_dir, standard_web(**web)


def test_an_own_article_is_pinned_as_src_w_with_its_meta_text_and_raw_bytes(tmp_path: Path) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])

    assert run_sources(tmp_path, batch_dir, web) == 0

    store = store_of(batch_dir)
    raw = store.path_for(SITE_ID, "src.W").read_bytes()
    text = store.path_for(SITE_ID, "src.W.txt").read_bytes().decode("utf-8")
    meta = S1.read_meta(store, SITE_ID, "W")
    assert raw == article_answer()
    assert text == EXTRACT
    assert meta is not None
    assert meta.permalink == PERMALINK
    assert (meta.revid, meta.lastrevid, meta.pageid) == (100, 100, 12129747)
    assert (meta.rev_timestamp, meta.retrieved_at) == (OLD, CUR)
    assert meta.sha256_text == M.text_sha256(text)
    assert meta.licence is M.Licence.CC_BY_SA_4
    assert meta.route is M.Route.ENWIKI_TITLE
    assert meta.subject_gate is not None and meta.subject_gate.verdict is M.SubjectVerdict.OWN
    assert meta.url == S1.article_url("en", "Tarxien Temples")
    assert report_of(batch_dir)[SITE_ID]["status"] == S1.STATUS_PINNED
    assert holds_of(batch_dir) == []


def test_every_request_writes_one_fetch_line_and_the_failures_go_to_fetch_json(
    tmp_path: Path,
) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])
    run_sources(tmp_path, batch_dir, web)

    lines = [json.loads(line) for line in (tmp_path / "LEDGER.jsonl").read_text().splitlines()]
    assert len(lines) == len(web.calls)
    assert {line["kind"] for line in lines} == {"fetch"}
    report = json.loads((batch_dir / M.FETCH_FAILURES_FILE).read_text(encoding="utf-8"))
    assert report["batch_id"] == "p4-0001" and "sites" in report


def test_the_phase3_entity_is_reused_byte_for_byte_and_not_fetched(tmp_path: Path) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])
    run_sources(tmp_path, batch_dir, web)

    store = store_of(batch_dir)
    meta = S1.read_meta(store, SITE_ID, "D")
    assert store.path_for(SITE_ID, "src.D").read_bytes() == entity_answer(QID)
    assert meta is not None
    assert meta.route is M.Route.PHASE3_EVIDENCE
    assert meta.licence is M.Licence.CC0
    assert (meta.lastrevid, meta.sha256_text, meta.subject_gate) == (None, None, None)
    assert meta.retrieved_at == "2026-09-21T14:13:20+00:00"  # the Phase-3 file's mtime
    assert web.asked("wbgetentities&ids=Q1064331&props=claims") == []


@pytest.mark.parametrize(
    "phase3_body",
    [
        entity_answer(QID)[: F.MAX_PAGE_BYTES // 1000],  # cut without a marker, as 115 were
        entity_answer(QID) + F.TRUNCATION_MARKER.encode("utf-8"),
        entity_answer("Q309"),  # a QID repaired since Phase 3
        None,
    ],
    ids=["cut", "marked", "other-qid", "absent"],
)
def test_a_phase3_entity_that_cannot_serve_is_refetched_at_the_wiki_cap(
    tmp_path: Path, phase3_body: bytes | None
) -> None:
    batch_dir = make_batch(tmp_path, [plan_site()])
    if phase3_body is not None:
        phase3_file(tmp_path, SITE_ID, phase3_body)
    web = standard_web()
    big = entity_answer(QID, cur=CUR, labels={"en": "Tarxien Temples", "mt": "x" * (200 * 1024)})
    web.add(S1.entity_url(QID), big)

    assert run_sources(tmp_path, batch_dir, web) == 0

    store = store_of(batch_dir)
    meta = S1.read_meta(store, SITE_ID, "D")
    assert meta is not None and meta.route is M.Route.WIKIDATA_ENTITY
    assert store.path_for(SITE_ID, "src.D").read_bytes() == big  # 200 KB: whole at the wiki cap
    assert meta.retrieved_at == CUR  # the answer's own clock
    assert meta.url == S1.entity_url(QID)
    assert report_of(batch_dir)[SITE_ID]["status"] == S1.STATUS_PINNED


def test_two_phase3_files_that_differ_for_one_site_are_a_conflict(tmp_path: Path) -> None:
    phase3_file(tmp_path, SITE_ID, entity_answer(QID), batch="batch-0001")
    phase3_file(tmp_path, SITE_ID, entity_answer(QID, p31=("Q5",)), batch="batch-0002")
    with pytest.raises(R.InputError, match="differ"):
        S1.phase3_entity(tmp_path / "phase3", SITE_ID)


def test_the_entity_request_is_phase3s_plus_the_server_clock() -> None:
    assert S1.entity_url(QID) == F.wikidata_entity_url(QID) + "&curtimestamp=1"


def test_a_refetched_entity_without_its_server_clock_is_not_pinned(tmp_path: Path) -> None:
    batch_dir = make_batch(tmp_path, [plan_site()])
    web = standard_web()
    web.add(S1.entity_url(QID), entity_answer(QID))

    run_sources(tmp_path, batch_dir, web)

    (only,) = holds_of(batch_dir)
    assert (only.reason, "curtimestamp" in only.detail) == (M.HoldReason.FETCH_FAILED, True)
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "D") is None


def test_a_wikidata_item_that_cannot_be_read_holds_the_site(tmp_path: Path) -> None:
    batch_dir = make_batch(tmp_path, [plan_site()])
    web = standard_web()
    web.add(S1.entity_url(QID), b"not found", status=404)

    assert run_sources(tmp_path, batch_dir, web) == 0

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.FETCH_FAILED
    assert only.detail.startswith("S1: Wikidata Q1064331")
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "W") is None


def test_revid_and_lastrevid_that_differ_hold_the_site_moved_during_fetch(tmp_path: Path) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()], article=article_answer(lastrevid=101))

    run_sources(tmp_path, batch_dir, web)

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.MOVED_DURING_FETCH
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "W") is None


@pytest.mark.parametrize(
    ("age_stamp", "held"), [("2026-09-20T13:00:00Z", True), ("2026-09-20T11:00:00Z", False)]
)
def test_a_revision_younger_than_48_hours_is_deferred(
    tmp_path: Path, age_stamp: str, held: bool
) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()], article=article_answer(timestamp=age_stamp))

    run_sources(tmp_path, batch_dir, web)

    holds = holds_of(batch_dir)
    assert bool(holds) is held
    if held:
        assert holds[0].reason is M.HoldReason.REVISION_TOO_FRESH
    assert (S1.read_meta(store_of(batch_dir), SITE_ID, "W") is None) is held


def test_a_wrong_subject_article_is_rejected_whatever_its_age(tmp_path: Path) -> None:
    fresh_and_far = article_answer(
        timestamp="2026-09-22T11:00:00Z", coords=(POINT[0] + 1, POINT[1])
    )
    batch_dir, web = _setup(tmp_path, [plan_site()], article=fresh_and_far)

    run_sources(tmp_path, batch_dir, web)

    assert holds_of(batch_dir) == []
    row = report_of(batch_dir)[SITE_ID]
    assert (row["status"], row["verdict"]) == (S1.STATUS_REJECTED, "wrong")
    assert not store_of(batch_dir).path_for(SITE_ID, "src.W").exists()


def test_a_disambiguation_page_is_recorded_and_leaves_src_w_free(tmp_path: Path) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()], article=article_answer(disambiguation=True))

    run_sources(tmp_path, batch_dir, web)

    row = report_of(batch_dir)[SITE_ID]
    assert (row["status"], row["verdict"]) == (S1.STATUS_REJECTED, "none")
    assert not store_of(batch_dir).path_for(SITE_ID, "src.W").exists()
    assert store_of(batch_dir).path_for(SITE_ID, S1.FEATURE_ENWIKI).exists()


def test_a_title_wikipedia_does_not_have_is_missing_not_failed(tmp_path: Path) -> None:
    missing = article_answer(missing_title="Tarxien Temples")
    batch_dir, web = _setup(tmp_path, [plan_site()], article=missing)

    run_sources(tmp_path, batch_dir, web)

    assert report_of(batch_dir)[SITE_ID]["status"] == S1.STATUS_MISSING
    assert holds_of(batch_dir) == []


@pytest.mark.parametrize(("status", "retries"), [(500, 3), (404, 1)])
def test_a_failed_article_request_holds_the_site_fetch_failed(
    tmp_path: Path, status: int, retries: int
) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])
    web.add(S1.article_url("en", "Tarxien Temples"), b"error", status=status)

    assert run_sources(tmp_path, batch_dir, web) == 0

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.FETCH_FAILED
    assert f"HTTP {status}" in only.detail
    assert len(web.asked("titles=Tarxien%20Temples")) == retries


def test_an_article_at_the_1_mib_cap_is_a_failure_and_never_parsed(tmp_path: Path) -> None:
    huge = article_answer(extract="x" * (S1.WIKI_MAX_BYTES + 10))
    batch_dir, web = _setup(tmp_path, [plan_site()], article=huge)

    run_sources(tmp_path, batch_dir, web)

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.FETCH_FAILED
    assert "1,048,576" in only.detail
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "W") is None


def test_an_answer_of_another_shape_holds_the_site(tmp_path: Path) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()], article=b'{"query": {"pages": []}}')

    run_sources(tmp_path, batch_dir, web)

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.FETCH_FAILED
    assert "unreadable" in only.detail


def test_a_scope_pending_site_is_held_and_nothing_is_fetched_for_it(tmp_path: Path) -> None:
    site = plan_site(flags=frozenset({M.SiteFlag.SCOPE_PENDING}), period_start=900)
    batch_dir = make_batch(tmp_path, [site])
    web = Web()

    assert run_sources(tmp_path, batch_dir, web) == 0

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.SCOPE_PENDING
    assert web.calls == []


def test_the_label_pass_asks_every_p31_class_and_a_place_level_class_makes_it_shared(
    tmp_path: Path,
) -> None:
    batch_dir = make_batch(tmp_path, [plan_site()])
    phase3_file(tmp_path, SITE_ID, entity_answer(QID, p31=("Q515", "Q839954")))
    labels = {"Q515": "city", "Q839954": "archaeological site"}
    web = standard_web(labels=labels)

    run_sources(tmp_path, batch_dir, web)

    meta = S1.read_meta(store_of(batch_dir), SITE_ID, "W")
    assert meta is not None and meta.subject_gate is not None
    assert meta.subject_gate.place_item is True
    assert meta.subject_gate.verdict is M.SubjectVerdict.SHARED
    assert len(web.asked("props=labels")) == 1
    assert json.loads((batch_dir / S1.SOURCES_REPORT).read_text())["class_labels"] == labels


def test_a_label_pass_that_failed_holds_the_sites_that_need_it(tmp_path: Path) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])
    web.add(S1.class_labels_url(["Q839954"]), b"", status=503)

    run_sources(tmp_path, batch_dir, web)

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.FETCH_FAILED
    assert "P31 class labels" in only.detail


def test_a_shared_anchor_from_the_plan_flags_reaches_the_gate(tmp_path: Path) -> None:
    site = plan_site(flags=frozenset({M.SiteFlag.SHARED_TITLE}))
    batch_dir, web = _setup(tmp_path, [site])

    run_sources(tmp_path, batch_dir, web)

    meta = S1.read_meta(store_of(batch_dir), SITE_ID, "W")
    assert meta is not None and meta.subject_gate is not None
    assert meta.subject_gate.verdict is M.SubjectVerdict.SHARED
    assert S1.shared_sets(plan_site()) == (frozenset(), frozenset())


def test_a_site_without_a_title_waits_for_the_routes(tmp_path: Path) -> None:
    site = plan_site(enwiki_title=None)
    batch_dir = make_batch(tmp_path, [site])
    phase3_file(tmp_path, SITE_ID, entity_answer(QID))
    web = Web().add(S1.class_labels_url(["Q839954"]), labels_answer({"Q839954": "x"}))

    run_sources(tmp_path, batch_dir, web)

    assert report_of(batch_dir)[SITE_ID]["status"] == S1.STATUS_NO_TITLE
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "D") is not None


def test_a_wiki_host_that_does_not_answer_stops_the_batch_and_nothing_is_final(
    tmp_path: Path,
) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])
    web.down.add("en.wikipedia.org")

    assert run_sources(tmp_path, batch_dir, web) == R.STOP_RUN_EXIT

    assert not (batch_dir / S1.SOURCES_REPORT).exists()
    assert not (batch_dir / M.HOLDS_FILE).exists()
    assert (batch_dir / M.FETCH_FAILURES_FILE).exists()


def test_a_finished_batch_is_not_asked_again_and_its_report_stands(tmp_path: Path) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])
    run_sources(tmp_path, batch_dir, web)
    asked = len(web.calls)
    report = (batch_dir / S1.SOURCES_REPORT).read_bytes()

    later = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)
    assert run_sources(tmp_path, batch_dir, web, now=later) == 0
    assert len(web.calls) == asked
    assert (batch_dir / S1.SOURCES_REPORT).read_bytes() == report


def test_a_rerun_after_a_stop_reads_what_is_on_disk_and_asks_only_what_is_missing(
    tmp_path: Path,
) -> None:
    batch_dir, web = _setup(tmp_path, [plan_site()])
    web.dead.add(_key(S1.class_labels_url(["Q839954"])))
    web.down.add("www.wikidata.org")
    assert run_sources(tmp_path, batch_dir, web) == R.STOP_RUN_EXIT
    web.down.clear()
    web.dead.clear()
    web.calls.clear()

    assert run_sources(tmp_path, batch_dir, web) == 0

    assert web.asked("titles=") == []
    assert len(web.asked("props=labels")) == 1


def test_holds_are_tagged_and_a_rerun_replaces_only_its_own(tmp_path: Path) -> None:
    batch_dir = make_batch(tmp_path, [plan_site()])
    theirs = M.Hold(
        site_id=SITE_ID, scope=M.HoldScope.SITE, reason=M.HoldReason.V9, detail="V9: 180 < 200"
    )
    old = S1.hold(SITE_ID, M.HoldReason.FETCH_FAILED, "an old failure")
    (batch_dir / M.HOLDS_FILE).write_text(M.dump_jsonl([theirs, old]), encoding="utf-8")
    new = S1.hold(OTHER_ID, M.HoldReason.SCOPE_PENDING, "out of window")

    S1.write_holds(batch_dir, [new], tag=S1.TAG)

    assert holds_of(batch_dir) == [theirs, new]
    with pytest.raises(ValueError, match="without the"):
        S1.write_holds(batch_dir, [theirs], tag=S1.TAG)


def test_the_report_carries_every_site_of_the_batch_in_batch_order(tmp_path: Path) -> None:
    other = plan_site(
        site_id=OTHER_ID, wikidata_qid=None, enwiki_title=None, name="Hagar Qim", source_url=None
    )
    batch_dir, web = _setup(tmp_path, [plan_site(), other])

    run_sources(tmp_path, batch_dir, web)

    payload = json.loads((batch_dir / S1.SOURCES_REPORT).read_text(encoding="utf-8"))
    assert [row["site_id"] for row in payload["sites"]] == [SITE_ID, OTHER_ID]
    assert payload["licences_version"] == LIC.LICENCES_VERSION
    assert payload["ran_at"] == "2026-09-22T12:00:00+00:00"


def test_write_source_refuses_a_meta_whose_hashes_are_not_its_bytes(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    article = S1.parse_article(article_answer())
    assert article is not None
    meta, text = S1.wiki_source(
        source_id="W",
        lang="en",
        url=S1.article_url("en", "Tarxien Temples"),
        raw=article_answer(),
        article=article,
        route=M.Route.ENWIKI_TITLE,
        gate=gate(),
    )
    with pytest.raises(ValueError, match="sha256_raw"):
        S1.write_source(store, SITE_ID, meta, b"other bytes", text)
    with pytest.raises(ValueError, match="sha256_text"):
        S1.write_source(store, SITE_ID, meta, article_answer(), text + " ")
    assert not store.path_for(SITE_ID, "src.W").exists()
