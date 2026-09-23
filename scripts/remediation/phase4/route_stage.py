"""S1b ROUTES: find a source for the sites S1 could not anchor, then assign every site its lane.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, section
pipeline ("S1b ROUTES", "Lane assignment"), source_store (DENY LIST) and licensing_and_ai_act (TDM).
Work item WB-A3. No model is called; MiniMax is asked for search hits only.

Scope: the sites without an `enwiki_title`, the titles English Wikipedia does not have, and the
articles the subject gate called `wrong` or `none` (`sources.json`). A site S1 pinned goes straight
to its lane; a site S1 held gets lane 0 and keeps S1's hold. For every routed site, in order:

1. **The free routes**, each resolved and recorded: the title of an English Wikipedia `source_url`
   (every URL of it: some rows store several, one per line); for another-language `source_url`,
   its English langlink (and the article itself as a lane-T candidate); `list=geosearch` within
   2 km of the stored point, kept only at a directional name match >= 90
   (`subject_gate.name_score`). Every English candidate goes back through S1's query and S1's gate
   (`sources_stage.gate_for`); the first `own` wins lane W. All 385 sites without an
   `enwiki_title` store no QID either (production, 2026-09-23), so for them the page's own item is
   fetched as the witness and the gate's rule 7 (place **and** name) decides.
2. **MiniMax**, only while no candidate is `own`: at most `MAX_QUERIES_PER_SITE` queries, built from
   name + site_type + country (`route_queries`), through `search_stage.search_slot` behind
   `quota_stop_reason` (floors 25 % weekly, 20 % 5 h, Theo's window refused; a failed probe stops) and
   the run's `--max-searches` budget. Hits are URLs only - a snippet is never evidence. A Wikipedia
   hit goes back through S1 and its gate; any other hit must pass, in order, the deny list
   (`licences.deny_family`), the TDM opt-out check (`training_corpus.parse_robots`,
   `parse_tdmrep`, `reservation_for` on the host's policy, then `html_reserves_tdm` on the page - a
   check that could not be made counts as a reservation), the mirror detector against every
   Wikipedia text the site's routes read, and web identity (the folded name in the text, and the
   stored country or a coordinate within 25 km). Only then is it pinned, with the 60 KB cap, as a
   lane-R candidate `src.R<k>`: its text through `content_fetch.extract_text_from_html`.
3. **The lane**, exactly once, from those facts: W (an own English article), S (a shared or parent
   article), T (an own article only in another language), R (only non-free pages), 0 (nothing: held
   `no-source`). A search that the quota gate, a stop-class error or the budget stopped holds the site
   `search-stopped` with lane 0: its lane is decided when it can be searched, never from half the
   facts. A site whose routes could not be asked at all (a failed request, not an empty answer) is
   held `fetch-failed`, because "could not look" is not "found nothing".

A page whose own HTML reserves text and data mining is deleted from the store right after the check
- the fetch that learned of the reservation is the one copy the law tolerates, and keeping it would
be a reproduction the reservation forbids; the ledger line and `routes.json` keep the fact. A page
that redirected to another host passes that host's policy too.

Outputs: `lanes.jsonl` (one `LaneAssignment` per site, in batch order), holds tagged `S1b: `, the
fetch report `routes.fetch.json` and the search report `search.json` (the shapes
`model_stage.read_fetch_failures` reads; `fetch.json` stays S1's), and `routes.json`, the stage's
report and completion mark. Exit: 0 when every site has its lane or its hold; `STOP_RUN_EXIT` when
the quota gate refused or a stop-class search error arrived - the sites are held, and the run stops.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlencode, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import search_stage as SS  # noqa: E402
from phase3.model_stage import SEARCH_REPORT_NAME  # noqa: E402

from phase4 import licences as LIC  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import sources_stage as S1  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402
from pipeline.lyra.handlers.content_fetch import extract_text_from_html  # noqa: E402
from pipeline.lyra.training_corpus import (  # noqa: E402
    DomainPolicy,
    html_reserves_tdm,
    parse_robots,
    parse_tdmrep,
    reservation_for,
)
from pipeline.utils.country_lookup import country_name_variants  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402
from pipeline.utils.text import normalize_name  # noqa: E402

ROUTES_REPORT = "routes.json"
ROUTES_FETCH_REPORT = "routes.fetch.json"
TAG = "S1b"

#: The geosearch radius and the page count asked for (design: within 2 km).
GEOSEARCH_RADIUS_M = 2000
GEOSEARCH_LIMIT = 20
#: The design's bound: at most 2 MiniMax queries per site.
MAX_QUERIES_PER_SITE = 2
#: How many web pages one site may pin as lane-R candidates, and how many web hits it may fetch to
#: find them. **Chosen bounds, not measurements**: the restricted call restates 2-4 quotes, and the
#: design budgets about 750 lane-R pages for about 250 sites.
MAX_R_PAGES_PER_SITE = 3
MAX_WEB_FETCHES_PER_SITE = 6
#: Web identity: a coordinate in the page within this distance of the stored point (design).
IDENTITY_KM = 25.0
#: The query of each search: name + site_type + country (design), phrased first, then loose.
QUERY_TEMPLATES: tuple[str, ...] = ('"{name}" {rest}', "{name} {rest}")

#: How a TDM refusal - a reservation, or a check that could not be made - opens its reason. A page
#: fetched before the refusal was known is deleted (module docstring).
TDM_REFUSED = "TDM refused"

#: A decimal coordinate pair as pages write it: `35.8696, 14.5068`.
_COORDINATE = re.compile(r"(-?\d{1,2}\.\d{3,})\s*[,;/ ]\s*(-?\d{1,3}\.\d{3,})")
_NON_WORD = re.compile(r"\W+")
#: `<lang>.wikipedia.org` and its mobile twin `<lang>.m.wikipedia.org`.
_WIKIPEDIA_HOST = re.compile(r"(?P<lang>[a-z]+(?:-[a-z]+)*)(?:\.m)?\.wikipedia\.org")


# ------------------------------------------------------------------------------------ the URLs


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def wikipedia_title(url: str) -> tuple[str, str] | None:
    """`(lang, title)` of a Wikipedia article URL (`/wiki/<title>`), or `None` for anything else.

    The mobile host (`en.m.wikipedia.org`) is the same edition; `simple` is English, not another
    language, and is not a route.
    """
    try:
        host = LIC.host_of(url)
    except ValueError:
        return None
    match = _WIKIPEDIA_HOST.fullmatch(host)
    path = urlsplit(url).path
    if match is None or match.group("lang") in ("www", "simple") or not path.startswith("/wiki/"):
        return None
    title = unquote(path[len("/wiki/") :]).replace("_", " ").strip()
    return (match.group("lang"), title) if title else None


def langlinks_url(lang: str, title: str) -> str:
    """The English langlink of an article on `<lang>.wikipedia.org`."""
    return f"https://{S1.check_lang(lang)}.wikipedia.org/w/api.php?" + urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "prop": "langlinks",
            "lllang": "en",
            "titles": title,
        },
        quote_via=quote,
    )


def geosearch_url(lat: float, lon: float) -> str:
    """English articles within `GEOSEARCH_RADIUS_M` of the stored point, nearest first."""
    return (
        F.WIKIPEDIA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "list": "geosearch",
                "gscoord": f"{lat!r}|{lon!r}",
                "gsradius": str(GEOSEARCH_RADIUS_M),
                "gslimit": str(GEOSEARCH_LIMIT),
            },
            quote_via=quote,
        )
    )


def route_queries(site: M.PlanSite) -> tuple[str, ...]:
    """The site's MiniMax queries: the stored name (phrased, then loose), site_type and country.

    A `"` inside a name is removed, because a phrase cannot contain its own delimiter.
    """
    name = " ".join(site.name.replace('"', " ").split())
    rest = " ".join(part for part in (site.site_type, site.country) if part)
    return tuple(" ".join(t.format(name=name, rest=rest).split()) for t in QUERY_TEMPLATES)


def policy_urls(url: str) -> tuple[str, str]:
    """The host's robots.txt and `/.well-known/tdmrep.json`, on the page's own scheme and host."""
    parts = urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    return f"{root}/robots.txt", f"{root}/.well-known/tdmrep.json"


# ---------------------------------------------------------------------------------- the answers


def parse_langlink(body: bytes) -> str | None:
    """The English title a langlinks answer names, or `None` when the article has none."""
    payload = json.loads(body.decode("utf-8"))
    pages = (payload.get("query") or {}).get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list) or len(pages) != 1:
        raise S1.ArticleUnreadable(f"the langlinks answer carries no single page: {payload!r}")
    links = pages[0].get("langlinks") or []
    for link in links:
        if link.get("lang") == "en" and isinstance(link.get("title"), str) and link["title"]:
            return link["title"]
    return None


def parse_geosearch(body: bytes) -> list[str]:
    """The article titles of a geosearch answer, nearest first."""
    payload = json.loads(body.decode("utf-8"))
    rows = (payload.get("query") or {}).get("geosearch") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise S1.ArticleUnreadable(f"the geosearch answer carries no list: {str(payload)[:200]}")
    titles = []
    for row in rows:
        if row.get("ns") == 0 and isinstance(row.get("title"), str):
            titles.append(row["title"])
    return titles


def _fold_text(text: str) -> str:
    """Accents stripped, lowercased, every run of non-word characters one space, padded."""
    folded = normalize_name(text, remove_parentheses=False, remove_brackets=False)
    return " " + " ".join(_NON_WORD.sub(" ", folded).split()) + " "


def web_identity(site: M.PlanSite, text: str) -> str | None:
    """Why the page is not about this site, or `None` when it is (design: web identity).

    The folded name (or an alias) must occur in the folded text as whole words, and so must the
    stored country (any of `country_name_variants`) or a coordinate within `IDENTITY_KM`.
    """
    page = _fold_text(text)
    names = [n for n in (site.name, *site.aliases) if _fold_text(n).strip()]
    if not any(_fold_text(name) in page for name in names):
        return "the stored name occurs nowhere in the page"
    countries = country_name_variants(site.country) if site.country else []
    if any(_fold_text(variant) in page for variant in countries if _fold_text(variant).strip()):
        return None
    for match in _COORDINATE.finditer(text):
        lat, lon = float(match.group(1)), float(match.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            if haversine_distance(site.lat, site.lon, lat, lon) <= IDENTITY_KM:
                return None
    return "the page names neither the stored country nor a point within 25 km"


def _same_host(one: str, other: str) -> bool:
    return one.removeprefix("www.") == other.removeprefix("www.")


# ------------------------------------------------------------------------------------ one site


@dataclass(frozen=True)
class WikiCandidate:
    """An article one of the routes named: its edition, its title, how it was reached."""

    lang: str
    title: str
    route: M.Route
    via: str


@dataclass(frozen=True)
class WebPage:
    """A non-free page that passed every check: what `src.R<k>` pins."""

    url: str
    body: bytes
    final_url: str
    retrieved_at: str
    text: str
    truncated: bool


@dataclass(frozen=True)
class Kept:
    """An article the gate accepted, with what it was judged on.

    `item` and `witness` are set for a site that stores no QID: the page's own item, fetched to
    judge it (`subject_gate`, rule 7), and pinned as the site's `src.D` when the article is chosen.
    """

    candidate: WikiCandidate
    article: S1.Article
    raw: bytes
    gate: M.SubjectGate
    item: str | None = None
    witness: S1.Stored | None = None
    witness_url: str | None = None


@dataclass
class Found:
    """What the routes of one site found, as they found it."""

    notes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    own: Kept | None = None
    shared: Kept | None = None
    other: Kept | None = None
    pages: list[WebPage] = field(default_factory=list)
    wiki_texts: list[str] = field(default_factory=list)
    seen: set[tuple[str, str]] = field(default_factory=set)
    #: The web hits already considered for this site: two queries often return the same page.
    urls: set[str] = field(default_factory=set)
    web_fetches: int = 0
    searched: bool = False
    stopped: str | None = None


@dataclass
class Routing:
    """The batch-wide state of S1b: the requests, the searches and the policies of every host."""

    batch_id: str
    fetches: S1.Fetches
    searcher: SS.Searcher
    probe: Callable[[], Mapping[str, Any]]
    wait: Callable[[], None]
    sleep: Callable[[float], None]
    now: datetime
    budget: int
    entities: Mapping[str, Mapping[str, Any] | None]
    #: S1's class labels, and those of the page items S1b fetches for QID-less sites.
    class_labels: dict[str, str]
    search: SS.SearchReport = field(init=False)
    stopped: str | None = None
    queries: int = 0
    policies: dict[str, tuple[DomainPolicy, str | None]] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.search = SS.SearchReport(batch_id=self.batch_id, endpoint=self.searcher.endpoint)

    @property
    def store(self) -> F.EvidenceStore:
        return self.fetches.store

    def outage(self) -> bool:
        """A wiki host did not answer its probe: nothing this batch decides can be final."""
        return any(LIC.is_wiki_host(host) for host in self.fetches.unreachable())


def _judge_wiki(site: M.PlanSite, candidate: WikiCandidate, found: Found, routing: Routing) -> None:
    """Fetch one candidate article, record it, and keep it when the gate says own or shared."""
    key = (candidate.lang, candidate.title)
    if key in found.seen:
        return
    found.seen.add(key)
    target = F.Target(
        site_id=site.site_id,
        feature=f"s1b.{candidate.lang}wiki.{_digest(candidate.title)}",
        url=S1.article_url(S1.check_lang(candidate.lang), candidate.title),
        reason=f"S1b {candidate.route.value} {candidate.via}",
    )
    stored = routing.fetches.get(target)
    label = f"{candidate.lang}:{candidate.title!r} ({candidate.route.value})"
    if not stored.ok:
        found.failures.append(f"{label}: {stored.failure}")
        return
    raw = stored.body or b""
    try:
        article = S1.parse_article(raw)
    except S1.ArticleUnreadable as exc:
        found.failures.append(f"{label}: an unreadable answer: {exc}")
        return
    if article is None:
        found.notes.append(f"{label}: no such article")
        return
    found.seen.add((candidate.lang, article.title))
    if article.extract:
        found.wiki_texts.append(article.extract)
    if article.page.get("ns") != 0:
        found.notes.append(f"{label}: not an article (namespace {article.page.get('ns')})")
        return
    entity = routing.entities.get(site.site_id)
    item = (article.page.get("pageprops") or {}).get("wikibase_item")
    witness: S1.Stored | None = None
    witness_url: str | None = None
    if site.wikidata_qid is None and item is not None:
        witness_url = S1.entity_url(item)
        witness = routing.fetches.get(
            F.Target(
                site_id=site.site_id,
                feature=f"s1b.wikidata.{item}",
                url=witness_url,
                reason=f"S1b the item of {label}",
            )
        )
        entity = S1.parse_entity(witness.body or b"", item) if witness.ok else None
        if entity is None:
            why = witness.failure or "the answer carries no entity"
            found.failures.append(f"{label}: its item {item}: {why}")
            return
        problem = _labels_for(entity, routing)
        if problem is not None:
            found.failures.append(f"{label}: its item {item}: {problem}")
            return
    gate = S1.gate_for(site, article, entity=entity, class_labels=routing.class_labels)
    found.notes.append(f"{label} -> {article.title!r}: {gate.verdict.value}")
    if not S1.usable_verdict(gate) or not (article.extract or "").strip():
        return
    kept = Kept(candidate, article, raw, gate, item, witness, witness_url)
    if candidate.lang != "en":
        if gate.verdict is M.SubjectVerdict.OWN and found.other is None:
            found.other = kept
    elif gate.verdict is M.SubjectVerdict.OWN and found.own is None:
        found.own = kept
    elif gate.verdict is M.SubjectVerdict.SHARED and found.shared is None:
        found.shared = kept


def _labels_for(entity: Mapping[str, Any], routing: Routing) -> str | None:
    """Make sure the class labels cover the entity's P31 classes; why they cannot, or `None`."""
    if all(cls in routing.class_labels for cls in SG.p31_classes(entity)):
        return None
    labels, failed = S1.class_labels_for([entity], fetches=routing.fetches)
    routing.class_labels.update(labels)
    if failed:
        return f"P31 class labels could not be read: {next(iter(failed.values()))}"
    return None


def _langlink(
    site: M.PlanSite, lang: str, title: str, route: M.Route, found: Found, routing: Routing
) -> None:
    """An article in another language: its English langlink is a W candidate, itself a T one."""
    target = F.Target(
        site_id=site.site_id,
        feature=f"s1b.langlinks.{lang}.{_digest(title)}",
        url=langlinks_url(lang, title),
        reason=f"S1b langlinks of {lang}:{title}",
    )
    stored = routing.fetches.get(target)
    if not stored.ok:
        found.failures.append(f"langlinks of {lang}:{title!r}: {stored.failure}")
    else:
        try:
            english = parse_langlink(stored.body or b"")
        except (S1.ArticleUnreadable, UnicodeDecodeError, json.JSONDecodeError) as exc:
            found.failures.append(f"langlinks of {lang}:{title!r}: unreadable: {exc}")
            english = None
        if english is not None:
            candidate = WikiCandidate("en", english, M.Route.LANGLINKS, f"{lang}:{title}")
            _judge_wiki(site, candidate, found, routing)
        else:
            found.notes.append(f"{lang}:{title!r} has no English langlink")
    if found.own is None:
        _judge_wiki(site, WikiCandidate(lang, title, route, f"{lang}:{title}"), found, routing)


def source_urls(site: M.PlanSite) -> list[str]:
    """Every URL the stored `source_url` names. Measured 2026-09-23: 20 curated rows store several,
    one per line (`https://www.megalithic.co.uk/...` then `https://en.wikipedia.org/wiki/...`), and
    18 of the 385 sites without an `enwiki_title` carry their English article only that way."""
    return (site.source_url or "").split()


def _free_routes(site: M.PlanSite, found: Found, routing: Routing) -> None:
    """source_url, its langlinks, and geosearch - every one resolved and recorded."""
    for url in source_urls(site):
        wiki = wikipedia_title(url)
        if wiki is None:
            found.notes.append(f"source_url {url!r} is no Wikipedia article")
        elif wiki[0] == "en":
            candidate = WikiCandidate("en", wiki[1], M.Route.SOURCE_URL, url)
            _judge_wiki(site, candidate, found, routing)
        else:
            _langlink(site, wiki[0], wiki[1], M.Route.SOURCE_URL, found, routing)
    target = F.Target(
        site_id=site.site_id,
        feature="s1b.geosearch",
        url=geosearch_url(site.lat, site.lon),
        reason="S1b geosearch within 2 km",
    )
    stored = routing.fetches.get(target)
    if not stored.ok:
        found.failures.append(f"geosearch: {stored.failure}")
        return
    try:
        titles = parse_geosearch(stored.body or b"")
    except (S1.ArticleUnreadable, UnicodeDecodeError, json.JSONDecodeError) as exc:
        found.failures.append(f"geosearch: unreadable: {exc}")
        return
    names = (site.name, *site.aliases)
    matched = [t for t in titles if (SG.name_score(names, [t]) or 0.0) >= SG.NAME_MATCH_MIN]
    found.notes.append(f"geosearch: {len(titles)} articles within 2 km, {len(matched)} named")
    for title in matched:
        _judge_wiki(
            site, WikiCandidate("en", title, M.Route.GEOSEARCH, "geosearch"), found, routing
        )


def _host_policy(url: str, routing: Routing) -> tuple[DomainPolicy, str | None]:
    """The host's reservation policy, fetched once per batch, and why it could not be read."""
    host = LIC.host_of(url)
    if host in routing.policies:
        return routing.policies[host]
    robots_url, tdmrep_url = policy_urls(url)
    robots = routing.fetches.get(
        F.Target(
            site_id=routing.batch_id,
            feature=f"s1b.robots.{host}",
            url=robots_url,
            reason="S1b TDM check",
        )
    )
    tdmrep = routing.fetches.get(
        F.Target(
            site_id=routing.batch_id,
            feature=f"s1b.tdmrep.{host}",
            url=tdmrep_url,
            reason="S1b TDM check",
        )
    )
    problem = _policy_problem(robots, "robots.txt") or _policy_problem(tdmrep, "tdmrep.json")
    if problem is not None:
        result = (DomainPolicy(check_error=problem), problem)
    else:
        rules = None
        if robots.body is not None:
            rules = parse_robots(robots.body.decode("utf-8"))
        paths: tuple[str, ...] = ()
        if tdmrep.body is not None:
            paths = parse_tdmrep(tdmrep.body.decode("utf-8"))
        result = (DomainPolicy(robots=rules, reserved_paths=paths), None)
    routing.policies[host] = result
    return result


def _policy_problem(stored: S1.Stored, what: str) -> str | None:
    """Why a policy file could not be read, or `None` (read, or absent by a 4xx answer).

    RFC 9309: a 4xx robots.txt means no rules; a 5xx, no answer, or a rate limit means the rules are
    unknown - and an unknown reservation counts as one (design: "A failed check counts as
    unusable"). A tdmrep.json that answers 200 must be JSON: `parse_tdmrep` reads anything else as
    "no reservation", which a page served for every path would turn into a silent pass.
    """
    if stored.body is not None:
        if stored.truncated:
            return f"{what} was cut at the page cap"
        try:
            text = stored.body.decode("utf-8")
        except UnicodeDecodeError:
            return f"{what} is not UTF-8 text"
        if what == "tdmrep.json":
            try:
                json.loads(text)
            except json.JSONDecodeError:
                return f"{what} answered 2xx with a body that is not JSON"
        return None
    status = stored.http_status
    if status is not None and 400 <= status < 500 and status not in (408, 429):
        return None
    return f"{what}: {stored.failure}"


def _tdm_problem(url: str, routing: Routing) -> str | None:
    """Why `url` may not be stored: a reservation, or a check that could not be made."""
    policy, problem = _host_policy(url, routing)
    verdict = reservation_for(url, policy)
    if problem is not None or verdict.signal == "check_failed":
        return f"{TDM_REFUSED}: the check could not be made for {LIC.host_of(url)}: {problem}"
    if verdict.opt_out:
        return f"{TDM_REFUSED}: reserved ({verdict.signal})"
    return None


def _fetch_record(site_id: str, feature: str, url: str, routing: Routing) -> tuple[str, str]:
    """Where the page's request ended and when, kept beside the page (`<feature>.fetched`) so a
    resumed run pins exactly the meta the first run would have pinned."""
    sidecar = f"{feature}.fetched"
    path = routing.store.path_for(site_id, sidecar)
    known = routing.fetches.final_url(url)
    if known is not None:
        record = {"final_url": known, "retrieved_at": S1.iso_utc(routing.now)}
        if not path.exists():
            body = json.dumps(record, sort_keys=True).encode("utf-8")
            routing.store.write(site_id=site_id, feature=sidecar, body=body)
    if not path.exists():
        page = routing.store.path_for(site_id, feature)
        raise R.InputError(
            f"{page} was fetched by an earlier run that did not record where it ended; delete it "
            "to fetch it again"
        )
    record = json.loads(path.read_text(encoding="utf-8"))
    return str(record["final_url"]), str(record["retrieved_at"])


def _web_page(site: M.PlanSite, url: str, found: Found, routing: Routing) -> None:
    """One non-Wikipedia hit: deny list, TDM, fetch, TDM again, mirror, identity - then pin."""
    if url in found.urls:
        return
    found.urls.add(url)
    family = LIC.deny_family(url)
    if family is not None:
        found.notes.append(f"{url}: denied ({family})")
        return
    if found.web_fetches >= MAX_WEB_FETCHES_PER_SITE:
        return
    problem = _tdm_problem(url, routing)
    if problem is not None:
        found.notes.append(f"{url}: {problem}")
        return
    found.web_fetches += 1
    feature = f"s1b.web.{_digest(url)}"
    stored = routing.fetches.get(
        F.Target(site_id=site.site_id, feature=feature, url=url, reason="S1b lane-R candidate")
    )
    if stored.body is None:
        found.failures.append(f"{url}: {stored.failure}")
        return
    final, retrieved_at = _fetch_record(site.site_id, feature, url, routing)
    reason = _page_problem(site, url, final, stored, found, routing)
    if reason is not None and reason.startswith(TDM_REFUSED):
        routing.store.path_for(site.site_id, feature).unlink()
        routing.deleted.append(f"{site.site_id}/{feature}")
    if reason is not None:
        found.notes.append(f"{url}: {reason}")
        return
    body = stored.body or b""
    found.pages.append(
        WebPage(
            url=url,
            body=body,
            final_url=final,
            retrieved_at=retrieved_at,
            text=_page_text(body),
            truncated=stored.truncated,
        )
    )


def _page_text(body: bytes) -> str:
    marker = F.TRUNCATION_MARKER.encode("utf-8")
    html = body[: -len(marker)] if body.endswith(marker) else body
    return S1.pinned_text(extract_text_from_html(html.decode("utf-8")))


def _page_problem(
    site: M.PlanSite, url: str, final: str, stored: S1.Stored, found: Found, routing: Routing
) -> str | None:
    """Why a fetched web page cannot be a lane-R candidate, or `None`."""
    family = LIC.deny_family(final)
    if family is not None:
        return f"redirected to {final}: denied ({family})"
    if not _same_host(LIC.host_of(final), LIC.host_of(url)):
        problem = _tdm_problem(final, routing)
        if problem is not None:
            return problem
    marker = F.TRUNCATION_MARKER.encode("utf-8")
    body = stored.body or b""
    html_bytes = body[: -len(marker)] if body.endswith(marker) else body
    try:
        html = html_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "the page is not UTF-8 text"
    if html_reserves_tdm(html):
        return f"{TDM_REFUSED}: reserved (meta_tag)"
    text = _page_text(body)
    if not text.strip():
        return "the page carries no text"
    for wiki_text in found.wiki_texts:
        if LIC.is_mirror(text, wiki_text):
            return f"a mirror of a Wikipedia text of this site ({LIC.FAMILY_WIKIMEDIA})"
    return web_identity(site, text)


def _hits(site: M.PlanSite, record: SE.SearchRecord, found: Found, routing: Routing) -> None:
    """A search's hits: Wikipedia ones back through S1's gate, the others as lane-R candidates."""
    web: list[str] = []
    for hit in record.hits:
        wiki = wikipedia_title(hit.url)
        if wiki is None:
            web.append(hit.url)
        elif wiki[0] == "en":
            candidate = WikiCandidate("en", wiki[1], M.Route.MINIMAX, record.query)
            _judge_wiki(site, candidate, found, routing)
        else:
            _langlink(site, wiki[0], wiki[1], M.Route.MINIMAX, found, routing)
        if found.own is not None:
            return
    if found.shared is not None or found.other is not None:
        return
    for url in web:
        if len(found.pages) >= MAX_R_PAGES_PER_SITE:
            return
        try:
            LIC.host_of(url)
        except ValueError:
            found.notes.append(f"{url}: not an http(s) URL")
            continue
        _web_page(site, url, found, routing)


def _search(site: M.PlanSite, found: Found, routing: Routing) -> None:
    """Up to `MAX_QUERIES_PER_SITE` searches, while no candidate is `own`."""
    site_search = SS.SiteSearch(site_id=site.site_id)
    routing.search.sites.append(site_search)
    for number, query in enumerate(route_queries(site), start=1):
        if found.own is not None:
            return
        slot = SE.SearchSlot(
            key=f"route{number}",
            feature=SE.search_feature(f"route{number}"),
            fields=("description", "card_description"),
        )
        url = SS.search_ledger_url(routing.searcher.endpoint, query)
        path = routing.store.path_for(site.site_id, slot.feature)
        if path.exists():
            record = SE.read_record(path)
            if record.query != query:
                raise R.InputError(
                    f"{site.site_id}/{slot.feature}: the stored search asked {record.query!r}, this "
                    f"stage builds {query!r}; a changed query needs a new run directory"
                )
            site_search.outcomes.append(
                SS.SlotOutcome(
                    feature=slot.feature,
                    fields=slot.fields,
                    query=query,
                    url=url,
                    existing=True,
                    hits=len(record.hits),
                    linkless=record.linkless,
                )
            )
        else:
            stop = _search_stop(routing)
            if stop is not None:
                found.stopped = stop
                site_search.outcomes.append(
                    SS.SlotOutcome(
                        feature=slot.feature,
                        fields=slot.fields,
                        query=query,
                        url=url,
                        failure=f"not searched: {stop}; 0 requests",
                    )
                )
                return
            routing.queries += 1
            outcome = SS.search_slot(
                batch_id=routing.batch_id,
                site_id=site.site_id,
                slot=slot,
                query=query,
                searcher=routing.searcher,
                store=routing.store,
                ledger=routing.fetches.ledger,
                wait=routing.wait,
                sleep=routing.sleep,
                stage=S1.STAGE,
            )
            site_search.outcomes.append(outcome)
            if outcome.stops:
                routing.stopped = f"{site.site_id}/{slot.feature}: {outcome.failure}"
                found.stopped = routing.stopped
                return
            if outcome.failure is not None:
                found.failures.append(f"search {query!r}: {outcome.failure}")
                continue
            record = SE.read_record(path)
        found.searched = True
        found.notes.append(f"search {query!r}: {len(record.hits)} hits")
        _hits(site, record, found, routing)


def _search_stop(routing: Routing) -> str | None:
    """Why no further query may be sent: the run's budget, a stop-class error earlier in the batch,
    or the gate (probed once, before the first query the budget allows)."""
    if routing.queries >= routing.budget:
        return f"the run's search budget is spent ({routing.budget} queries for this batch)"
    if routing.search.quota_before is None and routing.stopped is None:
        reading = routing.probe()
        routing.search.quota_before = SS.quota_reading(reading)
        refusal = SS.quota_stop_reason(reading, now_utc=routing.now)
        if refusal is not None:
            routing.stopped = f"the quota gate refused: {refusal}"
            routing.search.stopped = routing.stopped
    return routing.stopped


# --------------------------------------------------------------------------------------- pins


def _pin_wiki(site: M.PlanSite, kept: Kept, source_id: str, store: F.EvidenceStore) -> None:
    """Pin the chosen article (and, for a QID-less site, the page's item as its `src.D`)."""
    problem = S1.article_problem(kept.article)
    if problem is not None:
        raise _Held(problem[0], problem[1])
    if kept.witness is not None and S1.read_meta(store, site.site_id, "D") is None:
        witness = S1.pin_witness(
            site.site_id, str(kept.item), kept.witness, str(kept.witness_url), store
        )
        if witness.failure is not None:
            raise _Held(M.HoldReason.FETCH_FAILED, witness.failure)
    meta, text = S1.wiki_source(
        source_id=source_id,
        lang=kept.candidate.lang,
        url=S1.article_url(kept.candidate.lang, kept.candidate.title),
        raw=kept.raw,
        article=kept.article,
        route=kept.candidate.route,
        gate=kept.gate,
    )
    S1.write_source(store, site.site_id, meta, kept.raw, text)


def _pin_pages(site: M.PlanSite, found: Found, routing: Routing) -> tuple[str, ...]:
    ids = []
    for number, page in enumerate(found.pages, start=1):
        source_id = f"R{number}"
        meta = M.SourceDoc(
            id=source_id,
            url=page.url,
            permalink=None,
            title=None,
            pageid=None,
            revid=None,
            lastrevid=None,
            rev_timestamp=None,
            retrieved_at=page.retrieved_at,
            sha256_raw=S1.sha256_hex(page.body),
            sha256_text=M.text_sha256(page.text),
            licence=LIC.licence_of(page.url),
            route=M.Route.MINIMAX,
            subject_gate=None,
            tdm=M.Tdm(checked=True, reserved=False, signal=None),
            final_url=page.final_url,
            truncated=page.truncated,
        )
        S1.write_source(routing.store, site.site_id, meta, page.body, page.text)
        ids.append(source_id)
    return tuple(ids)


class _Held(Exception):
    """A pinned candidate that the rules on a response hold (moved, too fresh)."""

    def __init__(self, reason: M.HoldReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


# ------------------------------------------------------------------------------------- S1b


def _existing_meta(store: F.EvidenceStore, site_id: str, source_id: str) -> M.SourceDoc | None:
    return S1.read_meta(store, site_id, source_id)


def _route(
    site: M.PlanSite, fact: Mapping[str, Any], routing: Routing
) -> tuple[M.LaneAssignment, M.Hold | None] | None:
    """One site's lane, from S1's outcome and, for a routed site, the routes' facts. `None` when
    a wiki host stopped answering: then nothing about the site is decided, and nothing is pinned."""
    site_id = site.site_id
    status = fact["status"]
    if status in (S1.STATUS_SCOPE_PENDING, S1.STATUS_HELD):
        lane = M.LaneAssignment(
            site_id=site_id, lane=M.Lane.ZERO, sources=(), detail=f"held in S1: {fact['detail']}"
        )
        return lane, None
    if status == S1.STATUS_PINNED:
        meta = _existing_meta(routing.store, site_id, "W")
        if meta is None or meta.subject_gate is None:
            raise R.InputError(f"{site_id}: S1 says pinned, and src.W.meta is not there")
        lane_of = {M.SubjectVerdict.OWN: M.Lane.W, M.SubjectVerdict.SHARED: M.Lane.S}
        lane = M.LaneAssignment(
            site_id=site_id,
            lane=lane_of[meta.subject_gate.verdict],
            sources=("W",),
            detail=f"S1: {fact['detail']}",
        )
        return lane, None
    if status not in S1.ROUTED_STATUSES:
        raise R.InputError(f"{site_id}: S1 status {status!r} is not one this stage knows")
    found = Found()
    if fact.get("title"):
        found.seen.add(("en", fact["title"]))
    s1_text = _s1_extract(site_id, routing.store)
    if s1_text:
        found.wiki_texts.append(s1_text)
    _free_routes(site, found, routing)
    if routing.outage():
        return None  # the batch stops before a search is bought for a site it cannot judge
    if found.own is None:
        _search(site, found, routing)
    if routing.outage():
        return None
    return _assign(site, fact, found, routing)


def _s1_extract(site_id: str, store: F.EvidenceStore) -> str | None:
    """The text of the article S1 fetched and rejected, for the mirror detector."""
    path = store.path_for(site_id, S1.FEATURE_ENWIKI)
    if not path.exists():
        return None
    try:
        article = S1.parse_article(path.read_bytes())
    except S1.ArticleUnreadable:
        return None
    return None if article is None else article.extract


def _assign(
    site: M.PlanSite, fact: Mapping[str, Any], found: Found, routing: Routing
) -> tuple[M.LaneAssignment, M.Hold | None]:
    site_id = site.site_id
    facts = "; ".join([f"S1: {fact['detail']}", *found.notes, *found.failures])

    def zero(reason: M.HoldReason, why: str) -> tuple[M.LaneAssignment, M.Hold]:
        detail = f"{why}. {facts}"
        lane = M.LaneAssignment(site_id=site_id, lane=M.Lane.ZERO, sources=(), detail=detail)
        return lane, S1.hold(site_id, reason, detail, tag=TAG)

    try:
        if found.own is not None:
            _pin_wiki(site, found.own, "W", routing.store)
            return _lane(site_id, M.Lane.W, ("W",), facts), None
        if found.stopped is not None:
            return zero(M.HoldReason.SEARCH_STOPPED, f"its search was stopped: {found.stopped}")
        if found.shared is not None:
            _pin_wiki(site, found.shared, "W", routing.store)
            return _lane(site_id, M.Lane.S, ("W",), facts), None
        if found.other is not None:
            source_id = f"T.{found.other.candidate.lang}"
            _pin_wiki(site, found.other, source_id, routing.store)
            return _lane(site_id, M.Lane.T, (source_id,), facts), None
    except _Held as held:
        detail = f"{held.detail}. {facts}"
        lane = M.LaneAssignment(site_id=site_id, lane=M.Lane.ZERO, sources=(), detail=detail)
        return lane, S1.hold(site_id, held.reason, detail, tag=TAG)
    if found.pages:
        return _lane(site_id, M.Lane.R, _pin_pages(site, found, routing), facts), None
    if found.failures and not found.searched:
        return zero(M.HoldReason.FETCH_FAILED, "its routes could not be asked")
    return zero(M.HoldReason.NO_SOURCE, "no route found a usable source")


def _lane(site_id: str, lane: M.Lane, sources: tuple[str, ...], facts: str) -> M.LaneAssignment:
    return M.LaneAssignment(site_id=site_id, lane=lane, sources=sources, detail=facts)


@contextmanager
def open_search(
    *, pacing_dir: Path
) -> Iterator[tuple[SS.Searcher, Callable[[], Mapping[str, Any]], Callable[[], None]]]:
    """The three live seams of the search lane, wired the way `phase3/run.py search` wires them:
    `search_stage.MiniMaxSearcher` from the pipeline's settings, `probe_minimax_quota(force=True)`
    (a cached reading would let the gate pass on an old figure), and the MiniMax host's pace
    (`search_stage.SEARCH_MIN_INTERVAL_SECONDS`, across processes). The searcher is closed on exit.
    """
    from pipeline.lyra.minimax_shared import probe_minimax_quota

    searcher = SS.MiniMaxSearcher.from_settings()
    pacer = F.HostPacer(pacing_dir, min_interval=SS.SEARCH_MIN_INTERVAL_SECONDS)
    host = F.host_of(searcher.endpoint)
    try:
        yield searcher, (lambda: probe_minimax_quota(force=True)), (lambda: pacer.wait(host))
    finally:
        searcher.close()


def routes_batch(
    batch_dir: Path,
    *,
    ledger: Path,
    fetcher: F.Fetcher,
    searcher: SS.Searcher,
    max_searches: int,
    now: datetime,
    probe: Callable[[], Mapping[str, Any]],
    wait: Callable[[], None],
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """S1b over one batch (module docstring). `max_searches` is how many MiniMax queries this batch
    may still send; `probe` is `probe_minimax_quota(force=True)`; `wait` paces the MiniMax host."""
    if not isinstance(max_searches, int) or isinstance(max_searches, bool) or max_searches < 0:
        raise R.InputError(f"max_searches={max_searches!r} is not a count")
    batch_id, sites = S1.read_batch(batch_dir)
    if (batch_dir / ROUTES_REPORT).exists():
        return 0
    report = S1.read_sources_report(batch_dir)
    facts = {str(row["site_id"]): row for row in report["sites"]}
    missing = [site.site_id for site in sites if site.site_id not in facts]
    if missing:
        raise R.InputError(f"{batch_dir}: {S1.SOURCES_REPORT} has no outcome for {missing}")
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    fetches = S1.Fetches(
        batch_id=batch_id, fetcher=fetcher, store=store, ledger=L.Ledger(ledger), sleep=sleep
    )
    entities: dict[str, Mapping[str, Any] | None] = {}
    for site in sites:
        entities[site.site_id] = None
        if site.wikidata_qid is not None and S1.read_meta(store, site.site_id, "D") is not None:
            raw = store.path_for(site.site_id, M.source_feature("D", "raw")).read_bytes()
            entities[site.site_id] = S1.parse_entity(raw, site.wikidata_qid)
    routing = Routing(
        batch_id=batch_id,
        fetches=fetches,
        searcher=searcher,
        probe=probe,
        wait=wait,
        sleep=sleep,
        now=now,
        budget=max_searches,
        entities=entities,
        class_labels=dict(report["class_labels"]),
    )
    lanes: list[M.LaneAssignment] = []
    holds: list[M.Hold] = []
    for site in sites:
        routed = _route(site, facts[site.site_id], routing)
        if routed is None:
            break
        lane, site_hold = routed
        lanes.append(lane)
        if site_hold is not None:
            holds.append(site_hold)
    if routing.search.quota_before is not None:
        routing.search.quota_after = SS.quota_reading(probe())
    routing.search.stopped = routing.stopped
    F.write_report(batch_dir / ROUTES_FETCH_REPORT, fetches.report)
    if routing.search.sites:
        SS.write_report(batch_dir / SEARCH_REPORT_NAME, routing.search)
    if routing.outage():
        # An outage is not a fact about the sites: nothing is final, and a re-run asks again (the
        # searches already bought are on disk and are read, not bought twice).
        return R.STOP_RUN_EXIT
    (batch_dir / M.LANES_FILE).write_text(M.dump_jsonl(lanes), encoding="utf-8", newline="\n")
    S1.write_holds(batch_dir, holds, tag=TAG)
    S1.write_json(
        batch_dir / ROUTES_REPORT,
        {
            "batch_id": batch_id,
            "deleted_for_tdm": routing.deleted,
            "licences_version": LIC.LICENCES_VERSION,
            "queries": routing.queries,
            "search_requests": sum(len(o.attempts) for o in routing.search.outcomes),
            "stopped": routing.stopped,
            "sites": [lane.to_dict() for lane in lanes],
        },
    )
    return R.STOP_RUN_EXIT if routing.stopped is not None else 0
