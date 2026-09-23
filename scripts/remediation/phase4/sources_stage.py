"""S1 SOURCES: pin each site's English article and its Wikidata item, and judge the article's subject.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, sections
pipeline ("S1 SOURCES", "SUBJECT GATE") and source_store. Work item WB-A2. No model is called.

What one batch does (`sources_batch`), in order:

1. **scope-pending.** A site plan4 flagged out of the date window (or undated) is held and nothing
   is fetched for it: E4 hides it, so a text for it would be written for nobody.
2. **Wikidata, a witness.** The Phase-3 `wikidata_entity` file of the site is reused byte for byte
   when it parses and answers for the stored QID (`retrieved_at`: the file's mtime, when Phase 3
   stored it). Otherwise - missing, cut, unparseable, or for another QID (a QID repaired since
   Phase 3) - the same request (`fetch_stage.wikidata_entity_url`, plus `curtimestamp=1`:
   `entity_url`) is made again through the 1 MiB wiki cap (`retrieved_at`: the answer's own server
   clock). Measured 2026-09-23: 115 of the 4,618 Phase-3 files stopped at exactly 61,440 bytes;
   five of those entities re-measured at 64-146 KB. **Deviation from the design, named:** the design
   says "the tools-gap narrow route". That route (WDQS truthy values plus date claims) carries
   neither P279 - the gate's concept test - nor the precision of P625, so for the refetched items the
   gate could not decide; the entity request at the 1 MiB cap carries both, in the same shape as the
   reused files, and is recorded as `Route.WIKIDATA_ENTITY`. Neither the Phase-3 answer nor its
   refetch carries `lastrevid` (`props=claims|labels|descriptions` has no `info`), so
   `src.D.meta.lastrevid` is `null`: D is pinned by `sha256_raw`, and it is a witness that is never
   cited.
3. **English Wikipedia by `site_external_ids.enwiki_title`**, one request per site (`article_url`):
   the design's query plus `curtimestamp=1`, so the answer carries the server's own clock and the
   48 h rule is a function of the stored bytes (a resumed run judges exactly what the first run
   saw, never a revision that aged on disk). A title Wikipedia calls `invalid` is an answer, not a
   failure: the site is routed (`invalid-title`) like a title Wikipedia does not have.
4. **The page's own item**, when the article names another item than the stored QID (a wrong
   subject, a parent page, or the article of a site that stores no QID): the same entity request
   at the wiki cap (`s1.wikidata.<item>`). The gate judges a page on its own item - the stored
   item's P279, P31 and P625 say nothing about what a mismatched page is about.
5. **The P31 class labels**: one `wbgetentities props=labels` pass over the distinct P31 classes of
   the batch's items (stored and page items), 50 ids a request, stored under the batch id.
6. **The gate** (`subject_gate.subject_gate`) on every article. `own` and `shared` pin the article
   as `src.W` (raw copy, `src.W.txt` - the extract, NFC, `\\n` line ends - and `src.W.meta`);
   before that, the two rules on the response hold it: `revisions[0].revid != lastrevid` is
   `moved-during-fetch`, a revision younger than 48 h is `revision-too-fresh`. Both are checked
   only on an article the gate would use: a wrong-subject article is rejected whatever its age,
   so its site still reaches the routes. `wrong`, `none`, a disambiguation page, a 'List of' title
   and a title Wikipedia does not have are recorded and not pinned: `src.W` stays free for the
   article S1b may find. For a site that stores no QID the page's item is its witness and is
   pinned as `src.D` before the article.

A `revision-too-fresh` hold is final for its batch directory: `sources.json` is the completion mark
and the stored answer is write-once, so a re-run judges the same answer again. The design's
"deferred to a later batch" is the driver's to do (PHASE4_CONTRACTS.md, Track A): it re-queues such
sites into a new batch directory once 48 h have passed.

Every request is one `FETCH` ledger line through `fetch_stage.one_attempt`, each host is probed once
per batch (`fetch_stage.probe_host`), and the failures go to `fetch.json` in the shape
`model_stage.read_fetch_failures` reads. A target that failed holds its site `fetch-failed`; a wiki
host that did not answer its probe stops the batch (`phase3.run.STOP_RUN_EXIT`, no report, so a
re-run retries) - holding every site of the run over one outage would be the wrong outcome.

A cut wiki answer (at `WIKI_MAX_BYTES`) is a failure and is never parsed. `one_attempt` stores it
with Phase 3's `TRUNCATION_MARKER`, whose text names the 60 KB cap; the hold's detail names the cap
that applied.

`sources.json` is the stage's report and its completion mark: when it exists, the stage is done and
a re-run changes nothing. It carries what S1b reads - each site's status, resolved title, verdict
and the class labels. Holds go to `holds.jsonl`, each detail tagged `S1: ` so a re-run replaces its
own holds and never another stage's.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3.model import Stage  # noqa: E402

from phase4 import licences as LIC  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402

#: The cap of the wiki client (design S1, WB-A1): `*.wikipedia.org` and `wikidata.org` only.
WIKI_MAX_BYTES = 1024 * 1024
#: A revision younger than this is deferred (design S1; failure_modes: vandalism).
FRESH = timedelta(hours=48)
#: Every Phase-4 fetch line is written under the finder stage: the ledger's `Stage` has two members
#: (finder, reviewer), and these fetches buy the evidence the selector - the finder of Phase 4 -
#: reads. The line's `kind` is `fetch`, which is what tells it from a model call.
STAGE = Stage.FINDER
#: wbgetentities takes at most 50 ids per request.
LABELS_PER_REQUEST = 50

SOURCES_REPORT = "sources.json"
#: The prefix of every hold detail this stage writes (`write_holds`).
TAG = "S1"

FEATURE_ENWIKI = "s1.enwiki"
FEATURE_CLASS_LABELS = "s1.p31_labels."
#: The item an enwiki answer names when it is not the stored QID (`s1.wikidata.Q309`).
FEATURE_PAGE_ITEM = "s1.wikidata."

#: The site's S1 outcome, as `sources.json` records it for S1b.
STATUS_SCOPE_PENDING = "scope-pending"
STATUS_HELD = "held"
STATUS_PINNED = "pinned"
STATUS_REJECTED = "rejected"
STATUS_MISSING = "missing"
#: Wikipedia answered that the stored title cannot be a title at all (`invalid`): one production
#: row, Petra's, stores its title with a newline and a second URL (2026-09-23).
STATUS_INVALID_TITLE = "invalid-title"
STATUS_NO_TITLE = "no-title"
#: The statuses that send a site to S1b.
ROUTED_STATUSES = frozenset(
    {STATUS_REJECTED, STATUS_MISSING, STATUS_INVALID_TITLE, STATUS_NO_TITLE}
)


class ArticleUnreadable(ValueError):
    """A 2xx MediaWiki answer that is not the shape `article_url` asks for."""


class TitleInvalid(ValueError):
    """Wikipedia's answer that the asked title cannot be a page title (`invalid`, its reason).

    An answer, not a failure: the request succeeded and asking again gets the same answer. S1 routes
    such a site like a title Wikipedia does not have, so its `source_url` still gets its chance;
    S1b records such a candidate and moves on.
    """


# ------------------------------------------------------------------------------------ the client


class HostCappedFetcher:
    """The 1 MiB client for the wiki hosts, the 60 KB client for every other host (design S1).

    The rule sits on the `Fetcher` seam, so no call site can send a web page through the wide cap.
    """

    def __init__(self, *, wiki: F.Fetcher, web: F.Fetcher) -> None:
        self._wiki = wiki
        self._web = web

    def get(self, url: str) -> F.FetchedPage:
        client = self._wiki if LIC.is_wiki_host(F.host_of(url)) else self._web
        return client.get(url)


@contextmanager
def open_fetcher(*, pacing_dir: Path, timeout: float = 40.0) -> Iterator[F.Fetcher]:
    """The live fetcher of S1 and S1b: host-capped, and paced per host across processes."""
    wiki = F.HttpFetcher(timeout=timeout, max_bytes=WIKI_MAX_BYTES)
    web = F.HttpFetcher(timeout=timeout)
    try:
        yield F.PacedFetcher(HostCappedFetcher(wiki=wiki, web=web), F.HostPacer(pacing_dir))
    finally:
        wiki.close()
        web.close()


# ------------------------------------------------------------------------------------ the batch


def read_batch(batch_dir: Path) -> tuple[str, list[M.PlanSite]]:
    """The batch id (its directory name) and its sites, from `input.json`."""
    batch_id = batch_dir.name
    batch = R._single_batch(batch_dir / M.INPUT_FILE, batch_id)
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise R.InputError(f"{batch_dir}: the batch carries no sites")
    return batch_id, [M.PlanSite.from_dict(site) for site in sites]


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Sorted keys, LF, swapped in whole: a reader sees the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def write_holds(batch_dir: Path, holds: Sequence[M.Hold], *, tag: str) -> None:
    """Replace this stage's holds in `holds.jsonl` and keep every other stage's.

    A hold belongs to the stage whose tag opens its detail (`S1: `, `S1b: `). A re-run of a stage
    therefore replaces its own lines instead of appending a second copy - or keeping a hold whose
    reason a re-run no longer finds.
    """
    prefix = f"{tag}: "
    foreign = [hold for hold in holds if not hold.detail.startswith(prefix)]
    if foreign:
        raise ValueError(f"holds without the {prefix!r} tag: {[h.site_id for h in foreign]}")
    path = batch_dir / M.HOLDS_FILE
    kept = []
    if path.exists():
        kept = [h for h in M.load_jsonl(path, M.Hold) if not h.detail.startswith(prefix)]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(M.dump_jsonl([*kept, *holds]), encoding="utf-8", newline="\n")
    tmp.replace(path)


def hold(site_id: str, reason: M.HoldReason, detail: str, *, tag: str = TAG) -> M.Hold:
    return M.Hold(site_id=site_id, scope=M.HoldScope.SITE, reason=reason, detail=f"{tag}: {detail}")


# -------------------------------------------------------------------------------- the requests


@dataclass(frozen=True)
class Stored:
    """What one target left in the store: its bytes, or why there are none.

    `http_status` is the last status of a target that bought no page (`None` when no response
    arrived, or when the page is on disk): a policy file that answers 404 says something different
    from one that never answered.
    """

    body: bytes | None
    failure: str | None
    truncated: bool = False
    http_status: int | None = None

    @property
    def ok(self) -> bool:
        return self.body is not None and not self.truncated


class _FinalUrls:
    """A `Fetcher` decorator that remembers where each request ended after redirects."""

    def __init__(self, inner: F.Fetcher) -> None:
        self._inner = inner
        self.final: dict[str, str] = {}

    def get(self, url: str) -> F.FetchedPage:
        page = self._inner.get(url)
        self.final[url] = page.final_url
        return page


@dataclass
class Fetches:
    """One stage's requests for one batch: every host probed once, every target through
    `fetch_stage.one_attempt`, every outcome in a `fetch_stage.BatchFetchReport`.

    A target already on disk is read, not fetched: existence is the record, as in Phase 3.
    """

    batch_id: str
    fetcher: F.Fetcher
    store: F.EvidenceStore
    ledger: L.Ledger
    sleep: Callable[[float], None]
    report: F.BatchFetchReport = field(init=False)
    probes: dict[str, F.HostProbe] = field(default_factory=dict)
    _sites: dict[str, F.SiteEvidence] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.report = F.BatchFetchReport(batch_id=self.batch_id, stage=STAGE)
        self._recorder = _FinalUrls(self.fetcher)

    def final_url(self, url: str) -> str | None:
        """Where a request of this run ended, or `None` for a target read from disk."""
        return self._recorder.final.get(url)

    def _site(self, site_id: str) -> F.SiteEvidence:
        if site_id not in self._sites:
            self._sites[site_id] = F.SiteEvidence(site_id=site_id)
            self.report.sites.append(self._sites[site_id])
        return self._sites[site_id]

    def unreachable(self) -> list[str]:
        return [probe.host for probe in self.probes.values() if not probe.reachable]

    def get(self, target: F.Target) -> Stored:
        """The stored bytes of `target`, fetched first when they are not on disk."""
        evidence = self._site(target.site_id)
        evidence.targets.append(target)
        path = self.store.path_for(target.site_id, target.feature)
        if path.exists():
            evidence.skipped_existing += 1
            return _stored(path.read_bytes())
        host = F.host_of(target.request_url)
        if host not in self.probes:
            self.probes[host] = F.probe_host(
                host=host,
                url=F.host_probe_url(target.request_url),
                fetcher=self.fetcher,
                ledger=self.ledger,
                batch_id=self.batch_id,
                stage=STAGE,
            )
            self.report.probes = list(self.probes.values())
        probe = self.probes[host]
        if not probe.reachable:
            outcome = F.record_not_attempted(
                target=target, probe=probe, ledger=self.ledger, batch_id=self.batch_id, stage=STAGE
            )
            evidence.outcomes.append(outcome)
            return Stored(body=None, failure=outcome.failure)
        outcome = F.one_attempt(
            target=target,
            fetcher=self._recorder,
            store=self.store,
            ledger=self.ledger,
            batch_id=self.batch_id,
            stage=STAGE,
            sleep=self.sleep,
        )
        F.tally(evidence, target, outcome)
        if not outcome.stored:
            return Stored(body=None, failure=outcome.failure, http_status=outcome.final.http_status)
        return _stored(path.read_bytes())


def _stored(body: bytes) -> Stored:
    """A stored body; one that ends in Phase 3's truncation marker is a cut page."""
    marker = F.TRUNCATION_MARKER.encode("utf-8")
    if body.endswith(marker):
        return Stored(body=body, failure="the answer was cut at the fetch cap", truncated=True)
    return Stored(body=body, failure=None)


# ------------------------------------------------------------------------------------ the URLs


def article_url(lang: str, title: str) -> str:
    """The design's S1 query on `<lang>.wikipedia.org`, plus `curtimestamp=1` (module docstring)."""
    return f"https://{lang}.wikipedia.org/w/api.php?" + urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "prop": "extracts|revisions|coordinates|pageprops|info",
            "explaintext": "1",
            "rvprop": "ids|timestamp",
            "ppprop": "wikibase_item|disambiguation",
            "curtimestamp": "1",
            "titles": title,
        },
        quote_via=quote,
    )


#: What a permalink's title may keep unencoded besides letters, digits and `_.-~`.
_PERMALINK_SAFE = "/(),:'!*"


def permalink(lang: str, title: str, revid: int) -> str:
    """`https://<lang>.wikipedia.org/w/index.php?title=<T>&oldid=<revid>` (source_store)."""
    encoded = quote(title.replace(" ", "_"), safe=_PERMALINK_SAFE)
    return f"https://{lang}.wikipedia.org/w/index.php?title={encoded}&oldid={revid}"


def entity_url(qid: str) -> str:
    """Phase 3's entity request for one item, plus `curtimestamp=1`: the answer names its time."""
    return F.wikidata_entity_url(qid) + "&" + urlencode({"curtimestamp": "1"})


def class_labels_url(qids: Sequence[str]) -> str:
    """One label pass request: the English labels of up to 50 P31 classes."""
    if not 1 <= len(qids) <= LABELS_PER_REQUEST:
        raise R.InputError(f"{len(qids)} ids: wbgetentities takes 1 to 50 per request")
    for qid in qids:
        if not F.QID_PATTERN.fullmatch(qid):
            raise R.InputError(f"{qid!r} is not a Q-number")
    return (
        F.WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(qids),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
            quote_via=quote,
        )
    )


# ---------------------------------------------------------------------------------- the answers


@dataclass(frozen=True)
class Article:
    """One article as the query answer states it."""

    page: Mapping[str, Any]  #: the page object, for the gate
    title: str
    pageid: int
    revid: int
    lastrevid: int
    rev_timestamp: str
    retrieved_at: str  #: the answer's `curtimestamp`
    extract: str | None

    @property
    def item(self) -> str | None:
        """The Wikidata item the page names (`pageprops.wikibase_item`), or `None`."""
        return (self.page.get("pageprops") or {}).get("wikibase_item")


def _int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ArticleUnreadable(f"{what} is {value!r}, not an integer")
    return value


def _utc(stamp: str, what: str) -> datetime:
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ArticleUnreadable(f"{what} {stamp!r} is not an ISO timestamp") from exc
    if when.tzinfo is None:
        raise ArticleUnreadable(f"{what} {stamp!r} carries no zone")
    return when.astimezone(UTC)


def parse_article(body: bytes) -> Article | None:
    """The one page of an `article_url` answer, or `None` when Wikipedia has no such title.

    A title Wikipedia calls `invalid` raises `TitleInvalid`; any other shape `ArticleUnreadable`.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArticleUnreadable(f"the answer is not JSON: {exc}") from None
    pages = (payload.get("query") or {}).get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
        raise ArticleUnreadable(f"the answer carries no single page: {str(payload)[:200]}")
    page = pages[0]
    if page.get("missing") is True:
        return None
    if page.get("invalid") is True:
        raise TitleInvalid(str(page.get("invalidreason")))
    revisions = page.get("revisions")
    if not isinstance(revisions, list) or not revisions or not isinstance(revisions[0], dict):
        raise ArticleUnreadable("the page carries no revision")
    title = page.get("title")
    if not isinstance(title, str) or not title:
        raise ArticleUnreadable("the page carries no title")
    stamp = revisions[0].get("timestamp")
    retrieved = payload.get("curtimestamp")
    _utc(stamp, "revisions[0].timestamp")
    _utc(retrieved, "curtimestamp")
    extract = page.get("extract")
    if extract is not None and not isinstance(extract, str):
        raise ArticleUnreadable(f"extract is {type(extract).__name__}, not text")
    return Article(
        page=page,
        title=title,
        pageid=_int(page.get("pageid"), "pageid"),
        revid=_int(revisions[0].get("revid"), "revisions[0].revid"),
        lastrevid=_int(page.get("lastrevid"), "lastrevid"),
        rev_timestamp=stamp,
        retrieved_at=retrieved,
        extract=extract,
    )


def pinned_text(extract: str) -> str:
    """The text offsets index into: the extract, NFC, `\\n` line ends (source_store)."""
    return unicodedata.normalize("NFC", extract.replace("\r\n", "\n").replace("\r", "\n"))


def article_problem(article: Article) -> tuple[M.HoldReason, str] | None:
    """The two rules on a response the gate would use: moved during the fetch, or too fresh."""
    if article.revid != article.lastrevid:
        return (
            M.HoldReason.MOVED_DURING_FETCH,
            f"revisions[0].revid {article.revid} != lastrevid {article.lastrevid} in the one "
            f"answer for {article.title!r}",
        )
    age = _utc(article.retrieved_at, "curtimestamp") - _utc(article.rev_timestamp, "timestamp")
    if age < FRESH:
        hours = age.total_seconds() / 3600
        return (
            M.HoldReason.REVISION_TOO_FRESH,
            f"revision {article.revid} of {article.title!r} was {hours:.1f} h old at "
            f"{article.retrieved_at}; a revision younger than 48 h is not used, and the hold "
            "stands for this batch directory (the stored answer is judged again on a re-run)",
        )
    return None


def parse_entity(body: bytes, qid: str) -> Mapping[str, Any] | None:
    """The entity `qid` of a wbgetentities answer, or `None` when the answer is not usable."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    entities = payload.get("entities") if isinstance(payload, dict) else None
    entity = entities.get(qid) if isinstance(entities, dict) else None
    return entity if isinstance(entity, dict) else None


def answer_time(body: bytes) -> str:
    """The `curtimestamp` a MediaWiki answer carries: when the server answered."""
    payload = json.loads(body.decode("utf-8"))
    stamp = payload.get("curtimestamp") if isinstance(payload, dict) else None
    _utc(stamp, "curtimestamp")
    return str(stamp)


def parse_class_labels(body: bytes, qids: Sequence[str]) -> dict[str, str]:
    """`{class: its English label}` for every asked class; `""` for a class without one."""
    payload = json.loads(body.decode("utf-8"))
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        raise ArticleUnreadable(f"the label answer carries no entities: {str(payload)[:200]}")
    labels: dict[str, str] = {}
    for qid in qids:
        entity = entities.get(qid)
        if not isinstance(entity, dict):
            raise ArticleUnreadable(f"{qid}: asked for, and absent from the label answer")
        english = (entity.get("labels") or {}).get("en") or {}
        labels[qid] = str(english.get("value") or "")
    return labels


# --------------------------------------------------------------------------- store and records


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def write_source(
    store: F.EvidenceStore, site_id: str, meta: M.SourceDoc, raw: bytes, text: str | None
) -> None:
    """Pin one source: the raw bytes, the pinned text (not for D) and the meta, write-once."""
    if sha256_hex(raw) != meta.sha256_raw:
        raise ValueError(f"{site_id}/{meta.id}: sha256_raw is not the sha256 of the raw bytes")
    if (text is None) != (meta.sha256_text is None):
        raise ValueError(f"{site_id}/{meta.id}: a text and its sha256_text come together")
    if text is not None and M.text_sha256(text) != meta.sha256_text:
        raise ValueError(f"{site_id}/{meta.id}: sha256_text is not the sha256 of the text")
    store.write(site_id=site_id, feature=M.source_feature(meta.id, "raw"), body=raw)
    if text is not None:
        store.write(
            site_id=site_id, feature=M.source_feature(meta.id, "txt"), body=text.encode("utf-8")
        )
    store.write(
        site_id=site_id,
        feature=M.source_feature(meta.id, "meta"),
        body=(meta.to_json() + "\n").encode("utf-8"),
    )


def read_meta(store: F.EvidenceStore, site_id: str, source_id: str) -> M.SourceDoc | None:
    path = store.path_for(site_id, M.source_feature(source_id, "meta"))
    if not path.exists():
        return None
    return M.SourceDoc.from_json(path.read_text(encoding="utf-8"))


def wiki_source(
    *,
    source_id: str,
    lang: str,
    url: str,
    raw: bytes,
    article: Article,
    route: M.Route,
    gate: M.SubjectGate,
) -> tuple[M.SourceDoc, str]:
    """The meta and the pinned text of a Wikipedia article the gate accepted."""
    if article.extract is None:
        raise ValueError(f"{article.title!r}: an article without an extract cannot be pinned")
    text = pinned_text(article.extract)
    meta = M.SourceDoc(
        id=source_id,
        url=url,
        permalink=permalink(lang, article.title, article.revid),
        title=article.title,
        pageid=article.pageid,
        revid=article.revid,
        lastrevid=article.lastrevid,
        rev_timestamp=article.rev_timestamp,
        retrieved_at=article.retrieved_at,
        sha256_raw=sha256_hex(raw),
        sha256_text=M.text_sha256(text),
        licence=LIC.licence_of(url),
        route=route,
        subject_gate=gate,
        tdm=None,
        final_url=None,
        truncated=None,
    )
    return meta, text


def shared_sets(site: M.PlanSite) -> tuple[frozenset[str], frozenset[str]]:
    """The shared anchors plan4 derived for this site, as the gate's two sets."""
    qids = frozenset(
        {site.wikidata_qid} if M.SiteFlag.SHARED_QID in site.flags and site.wikidata_qid else ()
    )
    titles = frozenset(
        {site.enwiki_title} if M.SiteFlag.SHARED_TITLE in site.flags and site.enwiki_title else ()
    )
    return qids, titles


def gate_for(
    site: M.PlanSite,
    article: Article,
    *,
    entity: Mapping[str, Any] | None,
    class_labels: Mapping[str, str],
) -> M.SubjectGate:
    qids, titles = shared_sets(site)
    return SG.subject_gate(
        site,
        page=article.page,
        entity=entity,
        class_labels=class_labels,
        shared_qids=qids,
        shared_titles=titles,
    )


def usable_verdict(gate: M.SubjectGate) -> bool:
    return gate.verdict in (M.SubjectVerdict.OWN, M.SubjectVerdict.SHARED)


# ---------------------------------------------------------------------------------- Wikidata


def phase3_entity(phase3_run: Path, site_id: str) -> tuple[bytes, Path] | None:
    """The site's Phase-3 `wikidata_entity` file and its path, or `None` when the run holds none.

    A site that two Phase-3 batches fetched must have byte-identical files; two different answers
    for one site are a conflict nobody may pick from.
    """
    slug = F.EvidenceStore.slug(site_id, F.FEATURE_WIKIDATA_ENTITY)
    found = sorted(phase3_run.glob(f"*/{M.EVIDENCE_DIR}/{slug}.txt"))
    if not found:
        return None
    bodies = {path.read_bytes() for path in found}
    if len(bodies) > 1:
        raise R.InputError(f"{site_id}: {len(found)} Phase-3 entity files that differ: {found}")
    return bodies.pop(), found[0]


def iso_utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError(f"{moment!r} carries no zone")
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()


def _mtime_utc(path: Path) -> str:
    return iso_utc(datetime.fromtimestamp(os.stat(path).st_mtime, tz=UTC))


@dataclass
class Witness:
    """A site's Wikidata item as S1 pinned it, or why it could not."""

    entity: Mapping[str, Any] | None
    failure: str | None


def _pin_entity(*, site: M.PlanSite, fetches: Fetches, phase3_run: Path) -> Witness:
    """Reuse the Phase-3 file, or refetch the same request at the wiki cap (module docstring)."""
    qid = str(site.wikidata_qid)
    store = fetches.store
    url = F.wikidata_entity_url(qid)
    meta = read_meta(store, site.site_id, "D")
    if meta is not None:
        raw = store.path_for(site.site_id, M.source_feature("D", "raw")).read_bytes()
        return Witness(entity=parse_entity(raw, qid), failure=None)
    reused = phase3_entity(phase3_run, site.site_id)
    if reused is not None:
        # A cut file does not parse, with Phase 3's marker or without it (the 115 cut before the
        # marker existed): `parse_entity` refuses both, and the item is asked again.
        body, source = reused
        entity = parse_entity(body, qid)
        if entity is not None:
            meta = _entity_meta(url, body, M.Route.PHASE3_EVIDENCE, _mtime_utc(source))
            write_source(store, site.site_id, meta, body, None)
            return Witness(entity=entity, failure=None)
    target = F.Target(
        site_id=site.site_id,
        feature=M.source_feature("D", "raw"),
        url=entity_url(qid),
        reason="S1 wikidata entity (Phase-3 file missing, cut, unparseable or for another QID)",
    )
    return pin_witness(site.site_id, qid, fetches.get(target), target.url, store)


def pin_witness(
    site_id: str, qid: str, stored: Stored, url: str, store: F.EvidenceStore
) -> Witness:
    """Pin a fetched entity as the site's `src.D`, or say why it cannot be."""
    if not stored.ok:
        cut = f" (cap {WIKI_MAX_BYTES:,} bytes)" if stored.truncated else ""
        return Witness(entity=None, failure=f"Wikidata {qid}: {stored.failure}{cut}")
    body = stored.body or b""
    entity = parse_entity(body, qid)
    if entity is None:
        return Witness(entity=None, failure=f"Wikidata {qid}: the answer carries no entity {qid}")
    try:
        retrieved_at = answer_time(body)
    except ArticleUnreadable as exc:
        return Witness(entity=None, failure=f"Wikidata {qid}: {exc}")
    meta = _entity_meta(url, body, M.Route.WIKIDATA_ENTITY, retrieved_at)
    write_source(store, site_id, meta, body, None)
    return Witness(entity=entity, failure=None)


def _entity_meta(url: str, raw: bytes, route: M.Route, retrieved_at: str) -> M.SourceDoc:
    return M.SourceDoc(
        id="D",
        url=url,
        permalink=None,
        title=None,
        pageid=None,
        revid=None,
        lastrevid=None,
        rev_timestamp=None,
        retrieved_at=retrieved_at,
        sha256_raw=sha256_hex(raw),
        sha256_text=None,
        licence=LIC.licence_of(url),
        route=route,
        subject_gate=None,
        tdm=None,
        final_url=None,
        truncated=None,
    )


@dataclass(frozen=True)
class PageItem:
    """The item an article names when it is not the stored QID, fetched to judge the article on it.

    `subject_gate` reads a page's class, place level and fallback coordinate off the page's own item,
    never off the site's (module docstring there). For a site that stores no QID this item is also
    the witness pinned as `src.D` when its article is chosen (the gate's rule 7), so the answer is
    kept whole.
    """

    qid: str
    url: str
    stored: Stored
    entity: Mapping[str, Any] | None
    failure: str | None


def fetch_page_item(
    site_id: str, qid: str, *, fetches: Fetches, feature: str, reason: str
) -> PageItem:
    """The page's own item through Phase 3's entity request at the wiki cap, or why it cannot be read."""
    url = entity_url(qid)
    stored = fetches.get(F.Target(site_id=site_id, feature=feature, url=url, reason=reason))
    if not stored.ok:
        cut = f" (cap {WIKI_MAX_BYTES:,} bytes)" if stored.truncated else ""
        return PageItem(qid, url, stored, None, f"Wikidata {qid}: {stored.failure}{cut}")
    entity = parse_entity(stored.body or b"", qid)
    if entity is None:
        return PageItem(
            qid, url, stored, None, f"Wikidata {qid}: the answer carries no entity {qid}"
        )
    return PageItem(qid, url, stored, entity, None)


def class_labels_for(
    entities: Sequence[Mapping[str, Any]], *, fetches: Fetches
) -> tuple[dict[str, str], dict[str, str]]:
    """`({class: English label}, {class: why its label could not be read})` for every P31 class."""
    classes = sorted({cls for entity in entities for cls in SG.p31_classes(entity)})
    labels: dict[str, str] = {}
    failed: dict[str, str] = {}
    for start in range(0, len(classes), LABELS_PER_REQUEST):
        chunk = classes[start : start + LABELS_PER_REQUEST]
        digest = hashlib.sha256("|".join(chunk).encode("ascii")).hexdigest()[:12]
        target = F.Target(
            site_id=fetches.batch_id,
            feature=f"{FEATURE_CLASS_LABELS}{digest}",
            url=class_labels_url(chunk),
            reason="S1 P31 class labels",
        )
        stored = fetches.get(target)
        problem = stored.failure
        if stored.ok:
            try:
                labels.update(parse_class_labels(stored.body or b"", chunk))
            except (ArticleUnreadable, UnicodeDecodeError, json.JSONDecodeError) as exc:
                problem = f"the label answer is unreadable: {exc}"
        if problem is not None:
            failed.update(dict.fromkeys(chunk, problem))
    return labels, failed


# ---------------------------------------------------------------------------------------- S1


@dataclass
class SiteFacts:
    """One site's S1 outcome, as `sources.json` records it."""

    site_id: str
    status: str
    detail: str
    title: str | None = None
    verdict: M.SubjectVerdict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "status": self.status,
            "detail": self.detail,
            "title": self.title,
            "verdict": None if self.verdict is None else self.verdict.value,
        }


@dataclass(frozen=True)
class Outcome:
    """One site's S1 outcome and, when it is held, its hold."""

    facts: SiteFacts
    hold: M.Hold | None = None


def _held(site_id: str, reason: M.HoldReason, detail: str, **facts: Any) -> Outcome:
    return Outcome(SiteFacts(site_id, STATUS_HELD, detail, **facts), hold(site_id, reason, detail))


@dataclass(frozen=True)
class Answer:
    """One site's enwiki answer as read: the article, or the site's outcome when there is none."""

    target: F.Target
    raw: bytes
    result: Article | Outcome

    @property
    def article(self) -> Article | None:
        return self.result if isinstance(self.result, Article) else None


def read_answer(site: M.PlanSite, target: F.Target, stored: Stored) -> Answer:
    """Read the answer for the stored title once: an article, or why the site has none."""
    site_id = site.site_id
    if not stored.ok:
        cut = f" (cap {WIKI_MAX_BYTES:,} bytes)" if stored.truncated else ""
        detail = f"enwiki {site.enwiki_title!r}: {stored.failure}{cut}"
        return Answer(target, b"", _held(site_id, M.HoldReason.FETCH_FAILED, detail))
    raw = stored.body or b""
    try:
        article = parse_article(raw)
    except TitleInvalid as exc:
        detail = f"English Wikipedia calls the stored title {site.enwiki_title!r} invalid: {exc}"
        return Answer(target, raw, Outcome(SiteFacts(site_id, STATUS_INVALID_TITLE, detail)))
    except ArticleUnreadable as exc:
        detail = f"enwiki {site.enwiki_title!r}: an unreadable answer: {exc}"
        return Answer(target, raw, _held(site_id, M.HoldReason.FETCH_FAILED, detail))
    if article is None:
        detail = f"English Wikipedia has no article {site.enwiki_title!r}"
        return Answer(target, raw, Outcome(SiteFacts(site_id, STATUS_MISSING, detail)))
    return Answer(target, raw, article)


def sources_batch(
    batch_dir: Path,
    *,
    ledger: Path,
    fetcher: F.Fetcher,
    now: datetime,
    phase3_run: Path,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """S1 over one batch. 0 when every site reached an outcome; `STOP_RUN_EXIT` when a wiki host
    did not answer (nothing is final then: no holds, no report, and a re-run retries).

    `now` is when the stage ran, recorded in the report; every source's own time comes from its
    answer (`curtimestamp`) or, for a reused Phase-3 file, from the file.
    """
    batch_id, sites = read_batch(batch_dir)
    report_path = batch_dir / SOURCES_REPORT
    if report_path.exists():
        return 0
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    fetches = Fetches(
        batch_id=batch_id, fetcher=fetcher, store=store, ledger=L.Ledger(ledger), sleep=sleep
    )
    facts: dict[str, SiteFacts] = {}
    holds: list[M.Hold] = []
    active = []
    for site in sites:
        if M.SiteFlag.SCOPE_PENDING in site.flags:
            detail = (
                f"out of the date window or undated (period_start={site.period_start}, "
                f"period_end={site.period_end}, lon={site.lon}); E4 hides it"
            )
            facts[site.site_id] = SiteFacts(site.site_id, STATUS_SCOPE_PENDING, detail)
            holds.append(hold(site.site_id, M.HoldReason.SCOPE_PENDING, detail))
        else:
            active.append(site)

    witnesses: dict[str, Witness] = {}
    for site in active:
        if site.wikidata_qid is not None:
            witnesses[site.site_id] = _pin_entity(site=site, fetches=fetches, phase3_run=phase3_run)
    answers: dict[str, Answer] = {}
    for site in active:
        if site.enwiki_title is not None:
            target = F.Target(
                site_id=site.site_id,
                feature=FEATURE_ENWIKI,
                url=article_url("en", site.enwiki_title),
                reason="S1 enwiki_title",
            )
            answers[site.site_id] = read_answer(site, target, fetches.get(target))
    # A page is judged on its own item (subject_gate): an article that names another item than the
    # stored QID - a wrong subject, a parent page, or the article of a site without a QID - has its
    # item fetched, and the label pass covers that item's classes too.
    page_items: dict[str, PageItem] = {}
    for site in active:
        witness = witnesses.get(site.site_id)
        if witness is not None and witness.failure is not None:
            continue  # held for its witness whatever its article names
        answer = answers.get(site.site_id)
        item = None if answer is None or answer.article is None else answer.article.item
        if item is not None and item != site.wikidata_qid:
            page_items[site.site_id] = fetch_page_item(
                site.site_id,
                item,
                fetches=fetches,
                feature=f"{FEATURE_PAGE_ITEM}{item}",
                reason=f"S1 the item of enwiki {site.enwiki_title!r}",
            )
    entities = [
        w.entity for w in (*witnesses.values(), *page_items.values()) if w.entity is not None
    ]
    labels, label_failures = class_labels_for(entities, fetches=fetches)

    if any(LIC.is_wiki_host(host) for host in fetches.unreachable()):
        F.write_report(batch_dir / M.FETCH_FAILURES_FILE, fetches.report)
        return R.STOP_RUN_EXIT

    for site in active:
        outcome = _site_outcome(
            site,
            witness=witnesses.get(site.site_id),
            answer=answers.get(site.site_id),
            page_item=page_items.get(site.site_id),
            labels=labels,
            label_failures=label_failures,
            store=store,
        )
        facts[site.site_id] = outcome.facts
        if outcome.hold is not None:
            holds.append(outcome.hold)

    F.write_report(batch_dir / M.FETCH_FAILURES_FILE, fetches.report)
    write_holds(batch_dir, holds, tag=TAG)
    write_json(
        report_path,
        {
            "batch_id": batch_id,
            "class_labels": labels,
            "licences_version": LIC.LICENCES_VERSION,
            "ran_at": iso_utc(now),
            "sites": [facts[site.site_id].to_dict() for site in sites],
        },
    )
    return 0


def _uncovered(entity: Mapping[str, Any] | None, label_failures: Mapping[str, str]) -> str | None:
    """Why the gate could not read an item's P31 classes, or `None` when the labels cover them."""
    classes = () if entity is None else SG.p31_classes(entity)
    uncovered = [cls for cls in classes if cls in label_failures]
    if not uncovered:
        return None
    return f"P31 class labels {uncovered} could not be read: {label_failures[uncovered[0]]}"


def _site_outcome(
    site: M.PlanSite,
    *,
    witness: Witness | None,
    answer: Answer | None,
    page_item: PageItem | None,
    labels: Mapping[str, str],
    label_failures: Mapping[str, str],
    store: F.EvidenceStore,
) -> Outcome:
    """One site's S1 outcome, from its witness, its enwiki answer and the item that answer names."""
    site_id = site.site_id
    if witness is not None and witness.failure is not None:
        return _held(site_id, M.HoldReason.FETCH_FAILED, witness.failure)
    stored_entity = None if witness is None else witness.entity
    # The stored item's classes must be covered for every site, titled or not: S1b judges every
    # candidate that names the stored item on these labels.
    problem = _uncovered(stored_entity, label_failures)
    if problem is not None:
        return _held(site_id, M.HoldReason.FETCH_FAILED, problem)
    if answer is None:
        return Outcome(SiteFacts(site_id, STATUS_NO_TITLE, "the site stores no enwiki_title"))
    if isinstance(answer.result, Outcome):
        return answer.result
    article = answer.result
    entity = stored_entity if article.item == site.wikidata_qid else None
    if page_item is not None:
        if page_item.failure is not None:
            detail = f"enwiki {article.title!r} names another item: {page_item.failure}"
            return _held(site_id, M.HoldReason.FETCH_FAILED, detail, title=article.title)
        problem = _uncovered(page_item.entity, label_failures)
        if problem is not None:
            return _held(site_id, M.HoldReason.FETCH_FAILED, problem, title=article.title)
        entity = page_item.entity
    return _judge_article(
        site,
        answer.target,
        answer.raw,
        article,
        entity=entity,
        witness=page_item if site.wikidata_qid is None else None,
        labels=labels,
        store=store,
    )


def _judge_article(
    site: M.PlanSite,
    target: F.Target,
    raw: bytes,
    article: Article,
    *,
    entity: Mapping[str, Any] | None,
    witness: PageItem | None,
    labels: Mapping[str, str],
    store: F.EvidenceStore,
) -> Outcome:
    """One site's English article, judged on its own item: pin it, reject it, or hold the site.

    `witness` is the page's item of a site that stores no QID. It is pinned as the site's `src.D`
    before the article (the gate's rule 7), so an article is never pinned without its witness.
    """
    site_id = site.site_id
    gate = gate_for(site, article, entity=entity, class_labels=labels)
    if not usable_verdict(gate):
        detail = f"{article.title!r}: verdict {gate.verdict.value} ({_facts(gate)})"
        return Outcome(SiteFacts(site_id, STATUS_REJECTED, detail, article.title, gate.verdict))
    if not (article.extract or "").strip():
        detail = f"{article.title!r}: verdict {gate.verdict.value}, but the answer has no text"
        return Outcome(SiteFacts(site_id, STATUS_REJECTED, detail, article.title, gate.verdict))
    problem = article_problem(article)
    if problem is not None:
        reason, detail = problem
        return _held(site_id, reason, detail, title=article.title, verdict=gate.verdict)
    if witness is not None:
        pinned = pin_witness(site_id, witness.qid, witness.stored, witness.url, store)
        if pinned.failure is not None:
            return _held(
                site_id,
                M.HoldReason.FETCH_FAILED,
                pinned.failure,
                title=article.title,
                verdict=gate.verdict,
            )
    meta, text = wiki_source(
        source_id="W",
        lang="en",
        url=target.url,
        raw=raw,
        article=article,
        route=M.Route.ENWIKI_TITLE,
        gate=gate,
    )
    write_source(store, site_id, meta, raw, text)
    detail = f"{article.title!r} revision {article.revid}: verdict {gate.verdict.value}"
    return Outcome(SiteFacts(site_id, STATUS_PINNED, detail, article.title, gate.verdict))


def _facts(gate: M.SubjectGate) -> str:
    return (
        f"qid_match={gate.qid_match}, shared={gate.shared}, concept={gate.concept}, "
        f"place_item={gate.place_item}, km={gate.km}, name_score={gate.name_score}"
    )


def read_sources_report(batch_dir: Path) -> dict[str, Any]:
    """`sources.json`, which S1b needs: a batch without it has not been through S1."""
    path = batch_dir / SOURCES_REPORT
    if not path.exists():
        raise R.InputError(f"{batch_dir}: no {SOURCES_REPORT}; run the sources stage first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sites"), list):
        raise R.InputError(f"{path}: not a sources report")
    return payload


LANG_CODE = re.compile(r"[a-z]+(?:-[a-z]+)*")


def check_lang(lang: str) -> str:
    """A Wikipedia language code as a source id may carry it (`T.<lang>`)."""
    if not LANG_CODE.fullmatch(lang):
        raise R.InputError(f"{lang!r} is not a Wikipedia language code")
    return lang
