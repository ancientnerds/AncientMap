"""T07 - does the URL a reference link points at still answer?

`site_content_links` holds 16,029 web-discovery reference links across 3,575 curated sites
(1,429 sites have none, so the test does not apply to them). The plan's Phase 1 item 7
records the gap this module closes: these links were **never checked for HTTP status**.

Two halves, in the order run.py allows them.

collect() - the only network half
    15,230 distinct `content_url` values, one polite request each, through the shared
    Fetcher (`head()` falls back to GET when a server refuses HEAD). The Fetcher's own
    worker count is kept - this sweep talks to 4,939 third-party hosts, and the plan's
    "24 parallel" is a wall-clock estimate, not a licence to hammer them. `fetch.map()`
    gives deterministic, order-preserving results; every completed probe is persisted
    immediately, so an interrupted sweep resumes instead of starting over.

    Why a store of its own next to the Fetcher cache: the client caches only responses
    below 400, so exactly the statuses this test exists to classify (404, 403, 5xx) would
    be re-requested on every run and a second run would not be offline. A URL whose record
    carries an HTTP status is never requested again; records written for a *transport*
    failure carry no status and are deliberately re-probed, because "my laptop was offline"
    must not harden into "this link is unreachable" (see the two guards in collect()).

run() - pure: the verified snapshot plus those records, no socket.

    2xx/3xx        reachable - nothing to report
    404            gone
    410            gone permanently
    401, 403, 429  refused - the host will not answer this client. **Not** a dead link:
    400, 405, 406, a WAF turns HEAD *and* the GET fallback away routinely while serving a
    501            browser normally (www.megalithic.co.uk: 577 links, 403), so the only
                   honest verdict is "could not verify"
    5xx            the server is failing now - retry later, nothing is proven
    no status      transport failure (DNS, connect, timeout) - unreachable
    anything else  unclassified, quoted as it came

    The four "we do not know" verdicts are reported, never swallowed, and never called
    dead. They stay at Severity.COSMETIC: no defect is known, only an open question. Not
    reporting them would mark a site whose links sit behind a bot wall as `pass`, i.e. turn
    "could not check" into "checked and clean" - the inversion this census exists to prevent.

A link that really is gone, and severity
    T08 owns marker/array integrity (`raw_data->description_citations`). The marker format
    is `[N]` - plan section 1.3, line 57: "the description carries `[N]` markers, and every
    marker has an entry in `raw_data->description_citations`" - and `CitationText.tsx`
    resolves marker N through that array. This module reads that array for one purpose:
    tells apart a dead URL that is the published evidence of a claim from a dead favicon
    button.

      * not cited     -> Severity.COSMETIC, Proposal.CLEAR on the link row's `content_url`.
        Every reader of the table filters `content_url IS NOT NULL`
        (`pipeline/static_exporter.py:423`, `api/routes/sites.py:419` and `:1248`), so a
        cleared row simply stops rendering the dead button, and `remediation_change_log`
        keeps the old URL, so the change is reversible. Confidence.AUTHORITATIVE: a 404/410
        is the host's own answer about its own URL, not a third party's opinion.
      * cited         -> Severity.MODERATE, Proposal.REVIEW. Clearing the link row would
        not touch the footnote: the marker resolves through `description_citations`, and
        the source of that claim has to be *replaced*, which is a judgement call. The row
        stays untouched until someone decides.

    A refused, failing or unreachable link never becomes CLEAR, whatever else it looks like.

`field` is the table-qualified column `site_content_links.content_url`. One row per
finding is identified by (site_id, current_value = the URL) - verified unique on
2026-09-20 - and the row's own id is in the note for the applier.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from census.fetch import FetchError
from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

log = logging.getLogger("census.tests.t07")

TEST_ID = "T07"
NAME = "reference links reachable"
DIMENSION = "D8-URL / content_url"

#: the finding target: a row of site_content_links, pinned by site_id + current_value
FIELD = "site_content_links.content_url"

#: probe records live here under the run cache; the Fetcher cache is not enough (see module doc)
PROBE_NS = "t07_links"

#: Below this many probes in one sweep, a transport failure is treated as information about
#: the individual host (and is recorded); at or above it, a near-total failure is treated as
#: information about our own network and the sweep is abandoned. See collect().
MIN_SWEEP = 50

GONE = "gone"
GONE_PERMANENT = "gone-permanent"
REFUSED = "refused"
SERVER_ERROR = "server-error"
UNREACHABLE = "unreachable"
UNCLASSIFIED = "unclassified"
REACHABLE = "reachable"

#: statuses that mean "a non-browser client is not welcome here", not "this page is gone".
#: 400/405/406/501 are the Fetcher's own HEAD-refused set: `head()` already retried with
#: GET, so seeing them here means the GET was refused too.
REFUSED_STATUSES = frozenset({400, 401, 403, 405, 406, 429, 501})

#: `[N]` in the description; N indexes raw_data->description_citations (see module doc).
#: Measured 2026-09-20: the only numeric marker shape in the 2,141 marked descriptions,
#: 6,614 occurrences, no grouped (`[1, 2]`) or ranged (`[2-4]`) form.
MARKER_RE = re.compile(r"\[(\d+)\]")


# --------------------------------------------------------------------- probe store
def _probe_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _probe_path(ctx: Context, url: str) -> Path:
    key = _probe_key(url)
    return Path(ctx.cache) / PROBE_NS / key[:2] / f"{key}.json"


def read_probe(ctx: Context, url: str) -> dict[str, Any] | None:
    """The stored probe for `url`, or None.

    An unreadable or mis-keyed record returns None rather than deciding a link's fate:
    collect() then re-probes it and run() refuses to run without a record.
    """
    p = _probe_path(ctx, url)
    if not p.exists():
        return None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("T07: unreadable probe record, will re-probe: %s", p)
        return None
    if not isinstance(rec, dict) or rec.get("url") != url:
        log.warning("T07: probe record does not describe %s, will re-probe: %s", url, p)
        return None
    return rec


def _write_probe(ctx: Context, rec: dict[str, Any]) -> None:
    p = _probe_path(ctx, rec["url"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(p)  # atomic, like the Fetcher's own store: no half record can be read


def _is_final(rec: dict[str, Any] | None) -> bool:
    """True when a re-run must not request this URL again.

    A record with an HTTP status is an answer from the host and stays. A record without
    one is a transport failure - about the route, not the link - and is re-probed, so a
    sweep that ran while the connection was down heals instead of hardening.
    """
    return rec is not None and rec.get("status") is not None


# --------------------------------------------------------------------- inputs
def _content_url(link: dict[str, Any]) -> str | None:
    """The URL to probe for one link row; None when the column holds nothing.

    collect() and run() both go through here, so a stray whitespace cannot make the two
    halves disagree about the cache key. An empty `content_url` is not a link - the
    readers filter it out - and T06 owns the shape of the wide range of URLs it may be.
    """
    value = (link.get("content_url") or "").strip()
    return value or None


def _distinct_urls(ctx: Context) -> list[str]:
    urls = {u for row in ctx.snap.rows("site_content_links") if (u := _content_url(row))}
    return sorted(urls)


def _cited_markers(site: dict[str, Any]) -> dict[str, int]:
    """`url -> marker number` for the citations the description's `[N]` markers resolve to.

    Keyed by URL, not by the link row: a reference link carries no marker number of its
    own - the marker belongs to `raw_data->description_citations`, and a link is "cited"
    exactly when the text points at the URL the link points at. A citation entry whose
    marker is missing from the text is not counted: nothing on the page points at it
    (T08 reports that defect itself).
    """
    raw = site.get("raw_data")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        # The snapshot contract says JSON object. A string here means the export changed
        # shape, and guessing would silently drop every citation.
        raise ValueError(
            f"site {site.get('id')}: raw_data is {type(raw).__name__}, expected object "
            "or null - the snapshot shape changed, T07 cannot tell cited from uncited"
        )
    citations = raw.get("description_citations") or []
    if not isinstance(citations, list):
        raise ValueError(
            f"site {site.get('id')}: description_citations is "
            f"{type(citations).__name__}, expected list"
        )
    markers = {int(m) for m in MARKER_RE.findall(site.get("description") or "")}
    return {
        c["url"]: c["n"]
        for c in citations
        if isinstance(c, dict) and c.get("n") in markers and c.get("url")
    }


def classify(rec: dict[str, Any]) -> str:
    """The verdict for one probe record. Never "dead" without the host saying so."""
    status = rec.get("status")
    if status is None:
        return UNREACHABLE
    if 200 <= status < 400:
        return REACHABLE
    if status == 404:
        return GONE
    if status == 410:
        return GONE_PERMANENT
    if status in REFUSED_STATUSES:
        return REFUSED
    if 500 <= status < 600:
        return SERVER_ERROR
    return UNCLASSIFIED


# --------------------------------------------------------------------- collect
def collect(ctx: Context) -> None:
    net = ctx.net()
    urls = _distinct_urls(ctx)
    pending = [u for u in urls if not _is_final(read_probe(ctx, u))]
    log.info("T07: %d distinct reference URLs, %d to probe, %d already cached",
             len(urls), len(pending), len(urls) - len(pending))
    if not pending:
        return

    def probe(url: str) -> dict[str, Any]:
        """One polite request, persisted before it is returned."""
        try:
            payload = net.head(url)
        except FetchError as exc:
            # Transport failure after the client's own retries: recorded, never hidden -
            # run() calls it 'unreachable', and the missing status sends the next run back
            # here. The client's message names the method, the URL and the last underlying
            # reason (DNS, refused, timeout), which is what the evidence has to carry.
            rec: dict[str, Any] = {
                "url": url, "final_url": None, "status": None, "method": None,
                "error": str(exc), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
        else:
            rec = {
                "url": url,
                "final_url": payload.get("url"),
                "status": payload["status"],
                "method": payload.get("method"),
                "error": payload.get("error"),
                "fetched_at": payload.get("fetched_at"),
            }
        _write_probe(ctx, rec)
        return rec

    results = net.map(probe, pending, desc="T07 head sweep")
    broken = [r for r in results if not isinstance(r, dict)]
    if broken:
        # The worker raised something the collector does not know how to record. Aborting
        # is the only option that cannot be mistaken for a finished sweep.
        raise RuntimeError(
            f"T07: {len(broken)} of {len(pending)} probes failed in a way the collector "
            f"does not record: {broken[0]!r}"
        )

    no_status = sum(1 for r in results if r["status"] is None)
    # Both guards only apply to a real sweep, and protect the same thing: at this scale a
    # silent local network problem must not be written down as thousands of unreachable
    # links, because a cached wrong answer outlives the outage. Below MIN_SWEEP probes the
    # individual failure is recorded and the operator sees the count in the log line.
    if len(results) >= MIN_SWEEP and no_status == len(results):
        raise FetchError(
            f"T07: not one of the {len(results)} probes produced an HTTP status - refusing "
            "to record the whole reference-link corpus as unreachable"
        )
    if len(results) >= MIN_SWEEP and no_status * 2 > len(results):
        raise FetchError(
            f"T07: {no_status} of {len(results)} probes produced no HTTP status - more than "
            "half; this is our side of the wire, not 4,939 hosts"
        )

    tally: dict[str, int] = {}
    for r in results:
        verdict = classify(r)
        tally[verdict] = tally.get(verdict, 0) + 1
    log.info("T07: sweep done - %s", ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    log.info("T07: %d probed, %d left for the next run (no HTTP status), %d redirected",
             len(results), no_status, sum(1 for r in results if _is_redirect(r)))


def _is_redirect(rec: dict[str, Any]) -> bool:
    final = rec.get("final_url")
    return bool(final) and final != rec["url"]


# --------------------------------------------------------------------- run
def applies_to(site: dict[str, Any], ctx: Context) -> bool:
    """Only sites with a reference link that actually carries a URL are checked."""
    rows = ctx.snap.by("site_content_links", "site_id").get(str(site["id"]), [])
    return any(_content_url(row) for row in rows)


def run(ctx: Context) -> list[Finding]:
    links = ctx.snap.by("site_content_links", "site_id")
    findings: list[Finding] = []
    dead_sites: set[str] = set()
    unverified_sites: set[str] = set()
    n_dead = n_unverified = 0

    for site in ctx.sites:
        sid = str(site["id"])
        rows = links.get(sid, [])
        if not rows:
            continue
        cited = _cited_markers(site)
        for row in rows:
            url = _content_url(row)
            if url is None:
                continue  # no URL, nothing to probe (and no reader would show it)
            rec = read_probe(ctx, url)
            if rec is None:
                raise RuntimeError(
                    f"T07: no probe record for {url} (site {sid}) - the collector did not "
                    "run for this URL; run --tests T07 --collect-only first"
                )
            verdict = classify(rec)
            if verdict is REACHABLE:
                continue
            marker = cited.get(url)
            if verdict in (GONE, GONE_PERMANENT):
                n_dead += 1
                dead_sites.add(sid)
                findings.append(_dead_finding(sid, row, url, rec, marker, verdict))
            else:
                n_unverified += 1
                unverified_sites.add(sid)
                findings.append(_unverified_finding(sid, row, url, rec, marker, verdict))

    log.info(
        "T07: %d dead links on %d sites (%d permanent, %d cited), %d links unverified on "
        "%d sites",
        n_dead, len(dead_sites),
        sum(1 for f in findings if f.test_id.endswith("gone-permanent")),
        sum(1 for f in findings if f.severity is Severity.MODERATE),
        n_unverified, len(unverified_sites),
    )
    return findings


def _probe_quote(rec: dict[str, Any]) -> str:
    """What the host answered, in one line, including where a redirect chain ended."""
    if rec["status"] is None:
        return f"no HTTP status: {rec.get('error')}"
    where = ""
    if _is_redirect(rec):
        where = f" (after redirect to {rec['final_url']})"
    return f"HTTP {rec['status']} on {rec['url']}{where}"


def _probe_evidence(rec: dict[str, Any]) -> Evidence:
    return Evidence(
        source=f"HTTP probe ({rec.get('method') or 'HEAD'}, GET fallback)",
        url=rec["url"],
        quote=_probe_quote(rec),
        retrieved_at=rec.get("fetched_at"),
    )


def _citation_evidence(url: str, marker: int) -> Evidence:
    return Evidence(
        source="unified_sites.raw_data:description_citations",
        quote=f"the description's [{marker}] marker resolves to {url}",
    )


def _row_ref(row: dict[str, Any]) -> str:
    return f"site_content_links.id={row.get('id')}"


def _dead_finding(sid: str, row: dict[str, Any], url: str, rec: dict[str, Any],
                  marker: int | None, verdict: str) -> Finding:
    permanent = verdict is GONE_PERMANENT
    test_id = f"{TEST_ID}/gone-permanent" if permanent else f"{TEST_ID}/gone"
    quote = _probe_quote(rec)
    if marker is not None:
        # Clearing the link row would leave the visible footnote exactly as dead as it is
        # now: the marker resolves through description_citations, not through this row.
        return Finding(
            site_id=sid, test_id=test_id, field=FIELD,
            severity=Severity.MODERATE, dimension=DIMENSION,
            current_value=url, proposal=Proposal.REVIEW,
            confidence=Confidence.AUTHORITATIVE,
            note=f"{quote}. The description's [{marker}] marker cites this URL, so the "
                 f"published evidence of a claim cannot be reached; replacing the source "
                 f"is a decision, not a mechanical fix ({_row_ref(row)})",
            evidence=[_probe_evidence(rec), _citation_evidence(url, marker)],
        )
    return Finding(
        site_id=sid, test_id=test_id, field=FIELD,
        severity=Severity.COSMETIC, dimension=DIMENSION,
        current_value=url, proposal=Proposal.CLEAR,
        confidence=Confidence.AUTHORITATIVE,
        note=f"{quote}. No [N] marker in the description cites it, so this row only powers "
             f"a favicon button; every reader of site_content_links filters "
             f"content_url IS NOT NULL, so clearing it drops the dead button ({_row_ref(row)})",
        evidence=[_probe_evidence(rec)],
    )


def _unverified_finding(sid: str, row: dict[str, Any], url: str, rec: dict[str, Any],
                        marker: int | None, verdict: str) -> Finding:
    host = url.split("//", 1)[-1].split("/", 1)[0]
    if verdict is REFUSED:
        note = (f"HTTP {rec['status']} from {host} - the host refuses this client. A WAF or "
                "bot wall answers 403 to a non-browser routinely, so this says nothing "
                "about whether the page works in a browser: not a dead link.")
    elif verdict is SERVER_ERROR:
        note = (f"HTTP {rec['status']} from {host} - the server is failing right now. "
                "Nothing is proven; retry later.")
    elif verdict is UNREACHABLE:
        note = (f"{_probe_quote(rec)} - DNS, connect or timeout. Unreachable from here is "
                "not evidence that the link is dead.")
    else:
        note = (f"HTTP {rec['status']} from {host} - neither reachable nor a status that "
                "identifies a dead link. Quoted as it came.")
    if marker is not None:
        note += (f" The description's [{marker}] marker cites this URL, so a citation is "
                 "unverified, not disproven.")
    note += f" ({_row_ref(row)})"

    evidence = [_probe_evidence(rec)]
    if marker is not None:
        evidence.append(_citation_evidence(url, marker))
    return Finding(
        site_id=sid, test_id=f"{TEST_ID}/{verdict}", field=FIELD,
        severity=Severity.COSMETIC, dimension=DIMENSION,
        current_value=url, proposal=Proposal.REVIEW,
        confidence=Confidence.UNVERIFIABLE, note=note, evidence=evidence,
    )
