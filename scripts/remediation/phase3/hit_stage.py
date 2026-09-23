"""Stage "verify-hits" of the search lane: the page behind every search hit a finder answer cites.

The search pilot (`output/remediation/phase3_runner/SEARCH_PILOT_RESULT_1.txt`, 2026-09-23) failed
partly because a snippet is not a page. Las Labradas' `1000 B.C. - 300 A.D.` came from a travel page
about another site (Toro Muerto), and the Font dels Coms quote was not in the Zenodo snippet at all:
the finder is shown a search engine's title and snippet, and the snippet decides nothing about what
the page says or whom it is about. So after the finder has answered, and before the reviewer is asked,
this stage fetches the page behind every hit a finder answer cites, and from then on

* the reviewer is shown the page next to the snippet (`model_stage.evidence_excerpts`, bounded);
* a citation of the hit counts only when its quote occurs in the page's text
  (`discover_stage.pages_from_excerpts`), and a hit whose page could not be fetched or read leaves the
  citation unverified - the writer refuses the row (`write_stage.RULE_HIT_UNVERIFIED`) and never
  accepts it on the snippet.

What one batch does (`verify_batch`):

1. **Which hits.** Per site, the urls every finder answer on disk cites (`discover_stage.parse_answer`,
   its `SOURCE:` lines, in the field order the run asked, then in citation order) that are search hits
   of the site - the urls `model_stage.search_hit_urls` finds among the site's evidence. A cited
   fetched target or a url in no evidence at all is not a hit and is left to the citation check.
2. **A cap.** At most `MAX_HIT_PAGES_PER_SITE` pages per site are fetched; a cited hit beyond it is
   recorded as not fetched, with the count, so its citation stays unverified rather than silent.
3. **One page per hit, write-once.** The fetch stage's own attempt (`fetch_stage.one_attempt`):
   the project User-Agent, the 60 KB page cap and its truncation marker, the retries and their
   `Retry-After` rule, **one ledger line per attempt** (`kind="fetch"`, label
   `<site>/hitpage.<sha1(url)[:12]>`, stage `reviewer`), and the store that never overwrites a page
   with other bytes (`fetch_stage.EvidenceStore`). The pace is `fetch_stage.PacedFetcher` over the
   shared pacing directory, so a `--jobs N` run asks each host one request at a time across processes.
   A page already on disk is not fetched again; a re-run asks only for the pages that are not. A
   hit that asks for raw geometry, or names a host that is not a public http(s) address (loopback,
   private, link-local: `fetch_stage.assert_public_address`, Lyra's own check), is recorded as not
   fetched with 0 requests; a redirect hop into such a host is refused inside the client and
   recorded on the attempt that met it.
4. **The report**, `hitpages.json`, in `fetch.json`'s own `sites[].outcomes[].failure` shape, so
   `model_stage.read_fetch_failures` reads a hit that could not be fetched exactly like a failed
   target. A page that was stored but is not text a quote can be found in (a PDF: both PDFs the
   pilot's finder cited) carries `unreadable`; the evidence reads the same fact from the stored bytes.

Measured 2026-09-23 on a copy of the first pilot's run (`runs/search-gold`), this stage run live with
the project User-Agent: its finder answers cite 20 distinct hits in 25 citations. 20 requests: 13
answered HTML, 2 answered a PDF (both cut at the page cap, both `unreadable`), 5 answered 403 (four
Cloudflare challenge pages, one CloudFront block). 8 of the 25 quoted sentences occur in the fetched
page's text; 24 occur in the snippet the finder was shown, 17 of them in the snippet only.

**The page cap decides most of it** (re-measured 2026-09-23 on the same copy by the fixer's review):
14 of the 15 stored pages were cut at the 60 KB cap (`fetch_stage.MAX_PAGE_BYTES`; only
comusantjulia.ad came back whole), and every citation whose readable page does not carry its quote
is on a cut page - 9 of them: pathere.org twice, nilecruisetrips.com, travelshelper.com twice,
andbeyond.com and the three Wikipedia articles (Lake Mungo, the Odeon, Ahu Tongariki, each 2,400 to
4,100 characters of text, mostly navigation). The rest of such a page was never read, so its row is
refused as unverified and the refusal names the cut (`write_stage._hit_page_refusal`), never as a
fabricated citation. The cap binds and is not raised here.

Nothing here judges, and nothing writes a database.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Dual use, same shim as the other phase-3 modules.
if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import discover_stage as DS  # noqa: E402  - the finder's answers and their citations
from phase3 import fetch_stage as F  # noqa: E402  - the attempt, the store, the pace, the cap
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402  - which urls are search hits of a site
from phase3 import search_evidence as SE  # noqa: E402  - the hit page's feature and its text
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second

#: How many cited hit pages one site may fetch. **A chosen bound**: one site's answers can cite at most
#: 15 (`discover_stage.MAX_SOURCES` per answer, five fields), and the first pilot's most-cited site
#: (Font dels Coms) cited 6 distinct hits. A cited hit past the cap is recorded as not fetched, so the
#: cap costs rows, never silence.
MAX_HIT_PAGES_PER_SITE = 8

#: The audit stage the pages are fetched for: the reviewer reads them, and so does the writer's check.
STAGE = Stage.REVIEWER


@dataclass(frozen=True)
class CitedHit:
    """One search hit a finder answer cites, and the fields whose answers cite it."""

    site_id: str
    url: str
    feature: str
    fields: tuple[str, ...]


def cited_hits(
    *,
    site: Mapping[str, Any],
    store: F.EvidenceStore,
    answers: F.EvidenceStore,
    failures: Mapping[str, str] | None,
) -> list[CitedHit]:
    """The search hits this site's finder answers cite, in field order and then citation order.

    Which urls are hits is read off the site's own evidence (`model_stage.evidence_excerpts`, which
    raises when a search is missing with nothing recorded - this stage runs after the search, and a
    hole there is not this stage's to paper over). Two cited urls whose features collide raise: one
    feature is one stored page, and a second url under it would be checked against the first's text.
    """
    site_id = str(site.get("site_id") or "")
    # Which urls are hits is a fact of the search, not of the pages this stage stores from them.
    excerpts = MS.evidence_excerpts(
        site_id=site_id, site=site, store=store, hit_pages=False, failures=failures
    )
    hits = MS.search_hit_urls(excerpts)
    fields_of: dict[str, list[str]] = {}
    for name in SE.rerun_fields(site) or DS.DISCOVER_FIELDS:
        path = answers.path_for(site_id, name)
        if not path.exists():
            continue
        for claim in DS.parse_answer(path.read_text(encoding="utf-8")).sources:
            if claim.url not in hits:
                continue
            fields = fields_of.setdefault(claim.url, [])
            if name not in fields:
                fields.append(name)
    cited: list[CitedHit] = []
    by_feature: dict[str, str] = {}
    for url, fields in fields_of.items():
        feature = SE.hit_page_feature(url)
        other = by_feature.setdefault(feature, url)
        if other != url:
            raise InputError(
                f"{site_id}: the cited hits {other} and {url} share the feature {feature}; one "
                "feature is one stored page"
            )
        cited.append(CitedHit(site_id=site_id, url=url, feature=feature, fields=tuple(fields)))
    return cited


@dataclass
class HitOutcome:
    """What one cited hit ended with: on disk already, stored now, or recorded as not fetched."""

    feature: str
    url: str
    fields: tuple[str, ...]
    attempts: list[F.FetchAttempt] = field(default_factory=list)
    existing: bool = False
    stored: bool = False
    truncated: bool = False
    #: Why this hit has no page on disk, or `None` when it has one. What `read_fetch_failures` reads.
    failure: str | None = None
    #: Why a page that **is** on disk holds no text a quote can be found in, or `None`.
    unreadable: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": [a.to_dict() for a in self.attempts],
            "existing": self.existing,
            "failure": self.failure,
            "feature": self.feature,
            "fields": list(self.fields),
            "requests": len(self.attempts),
            "stored": self.stored,
            "truncated": self.truncated,
            "unreadable": self.unreadable,
            "url": self.url,
        }


@dataclass
class SiteHits:
    site_id: str
    outcomes: list[HitOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"site_id": self.site_id, "outcomes": [o.to_dict() for o in self.outcomes]}


@dataclass
class HitReport:
    """One batch's hit-page stage. Deterministic: no timestamp (the ledger carries the clock)."""

    batch_id: str
    sites: list[SiteHits] = field(default_factory=list)

    @property
    def outcomes(self) -> list[HitOutcome]:
        return [o for s in self.sites for o in s.outcomes]

    def to_json(self) -> str:
        outcomes = self.outcomes
        payload = {
            "batch_id": self.batch_id,
            "sites": [s.to_dict() for s in self.sites],
            "totals": {
                "cited": len(outcomes),
                "existing": sum(o.existing for o in outcomes),
                "failed": sum(o.failure is not None for o in outcomes),
                "requests": sum(len(o.attempts) for o in outcomes),
                "stored": sum(o.stored for o in outcomes),
                "truncated": sum(o.truncated for o in outcomes),
                "unreadable": sum(o.unreadable is not None for o in outcomes),
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def write_report(path: Path, report: HitReport) -> None:
    """`hitpages.json`, written to a temp file and swapped in: a reader sees a whole report or none."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def _unreadable(store: F.EvidenceStore, hit: CitedHit) -> str | None:
    """Why the stored page holds no text a quote can be found in, or `None` when it does."""
    try:
        SE.hit_page_text(store.path_for(hit.site_id, hit.feature).read_bytes())
    except SE.UnreadablePage as exc:
        return str(exc)
    return None


def verify_site(
    *,
    batch_id: str,
    site: Mapping[str, Any],
    fetcher: F.Fetcher,
    store: F.EvidenceStore,
    answers: F.EvidenceStore,
    ledger: L.Ledger,
    failures: Mapping[str, str] | None,
    sleep: Callable[[float], None],
) -> SiteHits:
    """Fetch the pages of one site's cited hits, up to the cap. Never raises for a failed page."""
    site_id = str(site.get("site_id") or "")
    cited = cited_hits(site=site, store=store, answers=answers, failures=failures)
    result = SiteHits(site_id=site_id)
    for index, hit in enumerate(cited):
        outcome = HitOutcome(feature=hit.feature, url=hit.url, fields=hit.fields)
        result.outcomes.append(outcome)
        if store.exists(site_id, hit.feature):
            outcome.existing = True
        elif index >= MAX_HIT_PAGES_PER_SITE:
            outcome.failure = (
                f"not fetched: the finder's answers cite {len(cited)} search hits at this site and "
                f"this stage fetches the first {MAX_HIT_PAGES_PER_SITE} "
                "(hit_stage.MAX_HIT_PAGES_PER_SITE); 0 requests"
            )
            continue
        else:
            try:
                F.assert_named_feature(hit.url)
                F.assert_public_address(hit.url)
            except (F.RawGeometryRefused, F.NonPublicAddressRefused) as exc:
                outcome.failure = f"not fetched: {exc}; 0 requests"
                continue
            fetched = F.one_attempt(
                target=F.Target(
                    site_id=site_id,
                    feature=hit.feature,
                    url=hit.url,
                    reason=f"search hit cited for {', '.join(hit.fields)}",
                ),
                fetcher=fetcher,
                store=store,
                ledger=ledger,
                batch_id=batch_id,
                stage=STAGE,
                sleep=sleep,
            )
            outcome.attempts = fetched.attempts
            outcome.stored = fetched.stored
            outcome.truncated = fetched.truncated
            outcome.failure = fetched.failure
        if outcome.failure is None:
            outcome.unreadable = _unreadable(store, hit)
    return result


def verify_batch(
    *,
    batch: Mapping[str, Any],
    fetcher: F.Fetcher,
    store: F.EvidenceStore,
    answers: F.EvidenceStore,
    ledger: L.Ledger,
    failures: Mapping[str, Mapping[str, str]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> HitReport:
    """Fetch the pages behind the search hits every finder answer of the batch cites.

    A batch whose sites buy no search is refused: nothing was searched, so no hit can be cited, and a
    report for it would read like a verified batch. `failures` is `read_fetch_failures`'s whole result.
    """
    batch_id = str(batch.get("batch_id") or "")
    sites = batch.get("sites")
    if not batch_id or not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id or 'a batch'}: a hit-page batch needs a batch_id and sites")
    recorded = failures or {}
    report = HitReport(batch_id=batch_id)
    for site in sites:
        site_id = str(site.get("site_id") or "")
        if not SE.search_slots(site):
            raise InputError(
                f"{batch_id}: site {site_id or '?'} carries no {SE.SEARCH_FIELDS_KEY}; only a search "
                "batch has hits a finder could cite"
            )
        report.sites.append(
            verify_site(
                batch_id=batch_id,
                site=site,
                fetcher=fetcher,
                store=store,
                answers=answers,
                ledger=ledger,
                failures=recorded.get(site_id),
                sleep=sleep,
            )
        )
    return report
