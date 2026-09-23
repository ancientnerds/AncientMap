# SPDX-License-Identifier: AGPL-3.0-only
"""Founder-level answers computed from Umami rows — the analysis half of the
pair with pipeline/umami_db.py (which fetches them).

Under pipeline/, not api/services/, for two reasons: it is pure functions
over rows with no FastAPI in sight, and the orchestrator's weekly digest
runs inside the Lyra image, which contains no `api` tree at all.

Sessions, human filter, session types, journeys. Pure functions — the routes
feed them the rows from pipeline.umami_db (SQL_SESSION_EVENTS); the tests
feed them fixtures.

The rules are the ones locked in the plan (2026-09-17):

* human = at least one page view, plus either an interaction event or a
  second page view; everything else is "unconfirmed" (a stealth scraper or a
  bouncing human — cookieless data cannot tell them apart, so both counts are
  shown). An interaction has to be the visitor's own act: ``site_open`` fires
  by itself on a server-rendered site page and does not count there
  (2026-09-19, it made thirteen of sixty-six "human" sessions human by page
  load alone). The page view became a condition on 2026-09-19: eight sessions
  fired one ``scroll_depth`` and never loaded a page at all, and all eight sit
  inside the two fingerprints ``/clusters`` proves are a single machine.
* session type = the first match in the order researcher → explorer →
  searcher → reader → other, which are the five values Session.kind returns.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

#: Events only a visitor can raise. A session with one of them and a page view
#: is a person. `outbound_click` and `discord_click` are in here because
#: boot.ts fires both from a click handler and from nowhere else: leaving them
#: out made a visitor who opened a story and followed a link off the site count
#: as "unconfirmed, may be a bot" (2026-09-19, one live session of 49).
INTERACTIONS = {
    "site_open",
    "search",
    "filter_toggle",
    "story_open",
    "paper_open",
    "media_play",
    "lyra_chat",
    "share",
    "feedback",
    "scroll_depth",
    "outbound_click",
    "discord_click",
}
#: The subset of INTERACTIONS that proves a visitor did something other than
#: scroll. A bounce is measured by scroll depth alone, so a session that played
#: the embedded video or clicked out to YouTube is not one - all five live
#: "bounces" on 2026-09-19 fired media_play and four of them outbound_click.
ENGAGEMENTS = ("media_play", "outbound_click", "share", "feedback", "lyra_chat", "discord_click")
#: The `context` a `site_open` carries when the page opened the site by itself
#: instead of a visitor picking it — SitePopup's effect sends the page type,
#: and on the server-rendered detail page that is "site" (SitePopup.tsx).
AUTO_SITE_OPEN_CONTEXT = "site"
#: Custom events that appear as steps in a journey (page types fill the rest).
JOURNEY_EVENTS = {
    "site_open",
    "search",
    "paper_open",
    "story_open",
    "lyra_chat",
    "share",
    "feedback",
}
SEARCH_HOSTS = (
    "google.",
    "bing.com",
    "duckduckgo.com",
    "yandex.",
    "ecosia.org",
    "qwant.com",
    "brave.com",
)
AI_HOSTS = (
    "chatgpt.com",
    "openai.com",
    "perplexity.ai",
    "copilot.microsoft.com",
    "gemini.google.com",
    "claude.ai",
)
#: utm_source values that name an assistant without naming a host. ChatGPT
#: tags its outbound links "utm_source=chatgpt.com", which is a host and is
#: already in AI_HOSTS; Perplexity tags them "utm_source=perplexity", which is
#: not. Measured 2026-09-19: thirteen AI sessions, eleven of them tagged
#: chatgpt.com, one perplexity, one referred by gemini.google.com - and ten of
#: the thirteen carry no referer at all.
AI_LABELS = ("chatgpt", "perplexity", "copilot", "gemini", "claude", "openai")
#: What source_family() calls a session that arrived from an assistant.
AI_ENTRY = "ai"

# Same shape as the regex in src/analytics/index.ts pageType(): only a
# top-level, lowercase name.html is a page type of its own.
_HTML_PAGE = re.compile(r"/([a-z0-9-]+)\.html")
_HUBS = (
    ("/news-archive/", "stories", "story"),
    ("/research/", "papers", "paper"),
    ("/articles/", "journals", "journal"),
)


def page_type(path: str) -> str:
    """Mirrors pageType() in src/analytics/index.ts — keep the two in step."""
    if path in ("/", "/index.html"):
        return "home"
    m = _HTML_PAGE.fullmatch(path)
    if m:
        return m.group(1)
    if path in ("/sites", "/sites/"):
        return "sites"
    if path.startswith("/sites/"):
        return "site" if len([p for p in path.split("/") if p]) >= 3 else "country"
    for prefix, hub, leaf in _HUBS:
        if path.startswith(prefix):
            return hub if path == prefix else leaf
    return "other"


def is_ai_entry(referrer: str | None, utm_source: str | None = None) -> bool:
    """True when either column names an AI assistant.

    Two columns, two vocabularies, and neither contains the other: the
    referrer carries a host ("perplexity.ai"), the utm carries a host *or* a
    bare label ("perplexity"). A rule written against the referrer alone finds
    two of the thirteen live AI sessions; one written against AI_LABELS alone
    finds one.
    """
    for value in (referrer, utm_source):
        if not value:
            continue
        v = value.lower()
        if any(h in v for h in AI_HOSTS) or v in AI_LABELS:
            return True
    return False


def source_family(referrer: str | None, utm_source: str | None = None) -> str:
    """Where a session came from, in founder words: "ai", else a utm_source
    verbatim, else "google" / "search" / the bare referrer host / "direct".

    The AI test runs first and over both columns, so /sources - which passes
    its coalesced value into the referrer slot - buckets a bare "perplexity"
    correctly without a second rule of its own.
    """
    if is_ai_entry(referrer, utm_source):
        return AI_ENTRY
    if utm_source:
        return utm_source
    if not referrer:
        return "direct"
    r = referrer.lower()
    if any(h in r for h in SEARCH_HOSTS):
        return "google" if "google." in r else "search"
    return r.removeprefix("www.")


@dataclass
class Session:
    id: str
    started: datetime
    country: str | None
    device: str | None
    browser: str | None = None
    entry: str | None = None
    #: True when the referrer or the utm_source named an AI assistant. `entry`
    #: cannot answer it on its own: ten of thirteen AI arrivals send no referer.
    from_ai: bool = False
    steps: list[str] = field(default_factory=list)  # page types and event names, in order
    #: Page types in order, without the event names `steps` interleaves. The
    #: two ends of a session cannot be filtered back out of `steps`, because
    #: "search" is both an event name and the type of /search.html.
    page_steps: list[str] = field(default_factory=list)
    events: Counter[str] = field(default_factory=Counter)
    depth: int = 0  # deepest scroll_depth seen, percent
    #: Time of the session's last event. The flag row slices one fetch into
    #: four windows with it — "in the last five minutes" is about the last
    #: sign of life, not about when the visitor arrived.
    last_seen: datetime | None = None
    #: site_open events the page fired on its own; they stay in `events` (the
    #: session type and the journey want them) but prove nothing about a human.
    auto_opens: int = 0

    @property
    def pages(self) -> int:
        """Page views, which is the length of `page_steps`. Read-only: one
        source of truth, and an assignment now raises AttributeError."""
        return len(self.page_steps)

    @property
    def human(self) -> bool:
        # A session without a single page view is not a person. Umami sends a
        # page view on every load, so an interaction without one is a forged
        # event burst - measured 2026-09-19: eight such sessions, one
        # scroll_depth each, and every one of them inside the two fingerprints
        # /clusters proves are a single machine.
        if not self.page_steps:
            return False
        if self.pages >= 2:
            return True
        return sum(self.events[n] for n in INTERACTIONS) > self.auto_opens

    @property
    def kind(self) -> str:
        pages = {
            s
            for s in self.steps
            if s in {"story", "paper", "journal", "site", "globe", "search", "papers", "stories"}
        }
        if (
            self.events["paper_open"]
            or self.events["lyra_chat"]
            or "paper" in pages
            or "papers" in pages
        ):
            return "researcher"
        if self.events["site_open"] or ("globe" in pages and self.events["filter_toggle"]):
            return "explorer"
        if self.events["search"]:
            return "searcher"
        if pages & {"story", "journal"}:
            return "reader"
        return "other"


def sessions_from_rows(rows: list[dict[str, Any]]) -> list[Session]:
    """Fold SQL_SESSION_EVENTS rows (ordered by session, time) into sessions."""
    by_id: dict[str, Session] = {}
    for r in rows:
        s = by_id.get(r["session_id"])
        if s is None:
            s = by_id[r["session_id"]] = Session(
                r["session_id"],
                r["created_at"],
                r.get("country"),
                r.get("device"),
                r.get("browser"),
            )
        # The rows arrive ordered by session and time, but a max() costs
        # nothing and does not depend on that order holding.
        if s.last_seen is None or r["created_at"] > s.last_seen:
            s.last_seen = r["created_at"]
        data = r.get("data") or {}
        if r["event_type"] == 1:
            if s.entry is None:
                s.entry = source_family(r.get("referrer_domain"), r.get("utm_source"))
                s.from_ai = is_ai_entry(r.get("referrer_domain"), r.get("utm_source"))
            page = page_type(r["url_path"] or "/")
            s.page_steps.append(page)
            s.steps.append(page)
        else:
            name = r["event_name"] or "event"
            s.events[name] += 1
            if name == "site_open" and data.get("context") == AUTO_SITE_OPEN_CONTEXT:
                s.auto_opens += 1
            if name == "scroll_depth":
                s.depth = max(s.depth, int(float(data.get("depth", 0) or 0)))
            if name in JOURNEY_EVENTS:
                s.steps.append(name)
    return sorted(by_id.values(), key=lambda s: s.started)


def journeys(sessions: list[Session], limit: int = 10) -> list[tuple[str, int]]:
    """The most common chains "entry → step → step…" over human sessions,
    six links at most."""
    c: Counter[str] = Counter()
    for s in sessions:
        if not s.human:
            continue
        chain = [s.entry or "direct", *s.steps][:6]
        c[" → ".join(chain)] += 1
    return c.most_common(limit)


def session_type_shares(sessions: list[Session]) -> dict[str, int]:
    return dict(Counter(s.kind for s in sessions if s.human))


#: Stands in for a session Umami could not place — the flag row shows a globe.
UNKNOWN_COUNTRY = "??"


def countries(
    sessions: list[Session],
    since: datetime | None = None,
    human_only: bool = True,
) -> list[dict[str, Any]]:
    """Sessions per country, biggest first — the flag row of the pulse panel.

    `since` keeps the sessions still alive after that moment, so one fetch
    serves every window the panel shows. `human_only` is off for the live
    tile: a visitor who arrived thirty seconds ago has one page view and no
    act to their name yet, and leaving them out would make "now" read zero.
    """
    c: Counter[str] = Counter()
    for s in sessions:
        if since is not None and (s.last_seen is None or s.last_seen < since):
            continue
        if human_only and not s.human:
            continue
        c[s.country or UNKNOWN_COUNTRY] += 1
    # Alphabetical inside a tie, so a refresh does not shuffle equal counts.
    return [
        {"country": code, "sessions": n}
        for code, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


#: Google's "good" thresholds in milliseconds — above them a page is slow for
#: three quarters of its visitors. CLS has no entry: it is a share, not a time.
VITAL_LIMITS = {"LCP": 2500, "INP": 200}
#: A 75th percentile out of three measurements is one visitor's phone, not a
#: percentile. Below this many samples a page stays out of the list (radar
#: showed "p75 4717 ms" from three loads on 2026-09-19).
VITAL_MIN_SAMPLES = 10
#: One dead hit is a typed typo; two are a link somebody published.
BROKEN_LINK_MIN = 2
#: Below a quarter of the page the visitor read the headline and left.
SHALLOW_DEPTH = 25
#: The page types a bounce is worth reporting for. Neither string is an event
#: name, so a step carrying one is always the page view, never an action.
SHALLOW_PAGES = {"story", "site"}
#: What a lost WebGL context means for the visitor, by the phase the globe was
#: in when it happened. src/components/Globe.tsx sends exactly these two.
WEBGL_PHASES = {
    "loading": "globe never started",
    "live": "globe froze after it had started",
}


def _visitors(n: int) -> str:
    """ "1 visitor" / "4 visitors" — the panel prints these details verbatim."""
    return f"{n} visitor" if n == 1 else f"{n} visitors"


#: How much of a session id the panel shows. Cookieless analytics has no user;
#: Umami's id recognises the same browser for one calendar month, and eight
#: characters are enough to see that two rows are the same visitor.
SESSION_ID_CHARS = 8


def _last_visitor(row: dict[str, Any]) -> dict[str, Any] | None:
    """Who a problem row last hit, from the `last_*` columns the problem
    queries select. None when the row carries no session."""
    session = row.get("last_session")
    if not session:
        return None
    return {
        "session": str(session)[:SESSION_ID_CHARS],
        "country": row.get("last_country"),
        "device": row.get("last_device"),
        "browser": row.get("last_browser"),
    }


def _session_visitor(s: Session) -> dict[str, Any]:
    """The same shape for the problems folded out of the sessions themselves."""
    return {
        "session": str(s.id)[:SESSION_ID_CHARS],
        "country": s.country,
        "device": s.device,
        "browser": s.browser,
    }


def problems(
    sessions: list[Session],
    not_found: list[dict[str, Any]],
    vitals: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    searches: list[dict[str, Any]] | None = None,
    webgl: list[dict[str, Any]] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Where the platform fails its visitors, worst first.

    Eight rows at most: below that the tail is one visitor each, and a list
    past eight rows on a phone is not read. `limit` was fifteen until
    2026-09-19; the digest slices three off the top either way.

    Six kinds, each with a score that makes them comparable: a JavaScript
    error counts triple per *visitor it reached* (it breaks the page for
    everyone who hits it), a dead link double, a bounce and an empty search
    once.

    Everything counts people, not events. Scoring a JavaScript error by its
    event count made one visitor who reloads a broken page three times look
    like nine incidents and outweigh everything else on the panel
    (2026-09-19); boot.ts sends up to three errors per page view, so the
    inflation is built in.

    A slow page is the one kind whose score is not a plain visitor count: it
    is how many visitors it was measured over, times how far past its budget
    it is. Counting the measurements alone ranked traffic instead of damage -
    on 2026-09-19 story · LCP at 2 524 ms (0.96 % over the 2 500 ms budget,
    35 samples) took the top row of the panel and of the weekly digest, while
    the globe's INP at 4.6× its budget came second and a WebGL shader failure
    that ended the visit for somebody came seventh.

    `not_found`, `vitals`, `errors` and `webgl` are the rows of SQL_NOT_FOUND,
    SQL_VITALS, SQL_ERRORS and SQL_WEBGL_LOST; the bounces and empty searches
    come from the sessions, so no query has to be repeated.

    A lost WebGL context weighs the same as a JavaScript error, because that
    is what it is: the globe stops and the page is over for that visitor. The
    globe's *slowness* is deliberately not a kind here - eight globe_ready
    samples from six browsers cannot carry a percentile, and the globe panel
    prints the times it has, with their count, instead.

    Every `label` names the thing that is broken and nothing else — the panel
    puts the kind in front of it, so "story loads slowly" would say it twice.

    Every entry also carries `at`, the last time it happened, and `last`, the
    visitor it happened to (owner, 2026-09-19: "date, time and user"). There
    is no user in cookieless analytics — `last` is the session Umami
    recognises for one calendar month, with its country, device and browser.
    """
    found: list[dict[str, Any]] = []
    for row in errors:
        hit = row["sessions"]
        found.append(
            {
                "kind": "js_error",
                "label": row["message"],
                "score": hit * 3,
                "detail": f"{_visitors(hit)}, {row['n']}× on {row['page']}",
                "at": row.get("last_at"),
                "last": _last_visitor(row),
            }
        )
    for row in webgl or []:
        hit = row["sessions"]
        found.append(
            {
                "kind": "webgl_lost",
                "label": WEBGL_PHASES[row["phase"]],
                "score": hit * 3,
                "detail": f"{_visitors(hit)}, {row['n']}× — {row['reason']}",
                "at": row.get("last_at"),
                "last": _last_visitor(row),
            }
        )
    for row in vitals:
        limit_ms = VITAL_LIMITS.get(row["name"])
        if limit_ms is None or row["p75"] <= limit_ms:
            continue
        if row["samples"] < VITAL_MIN_SAMPLES:
            continue
        found.append(
            {
                "kind": "slow_page",
                # The metric belongs in the label: a page type can be slow twice.
                "label": f"{row['page']} · {row['name']}",
                # Visitors reached, times the overshoot. `sessions` and not
                # `samples`, for the same reason js_error counts sessions.
                "score": round(row["sessions"] * row["p75"] / limit_ms),
                "detail": (
                    f"p75 {round(row['p75'])} ms against a {limit_ms} ms budget, {row['samples']} samples"
                ),
                "at": row.get("last_at"),
                "last": _last_visitor(row),
            }
        )
    for row in not_found:
        if row["n"] < BROKEN_LINK_MIN:
            continue
        found.append(
            {
                "kind": "broken_link",
                "label": row["path"],
                # Visitors, not views: BROKEN_LINK_MIN already reads the views,
                # and one person reloading a dead link is one broken link.
                "score": row["sessions"] * 2,
                "detail": f"{row['n']} views into nothing, from {row['referrer']}",
                "at": row.get("last_at"),
                "last": _last_visitor(row),
            }
        )
    bounces: Counter[str] = Counter()
    #: The most recent bouncing session per page type — the panel names one.
    last_bounce: dict[str, Session] = {}
    empty_searches = 0
    for s in sessions:
        empty_searches += s.events["search_empty"]
        # Only sessions we can tell from a crawler. A one-page visit without a
        # scroll and without an act of its own is exactly the "unconfirmed"
        # bucket the pulse already shows — listing it here as well turned
        # twenty-two headless story fetches into the second-worst problem on
        # the panel (2026-09-19). What is left is a visitor who did something
        # and still left the page after the headline.
        if not s.human:
            continue
        # A bounce is measured by scroll depth alone, and scrolling is not the
        # only way to use a page: all five sessions this test caught on
        # 2026-09-19 had played the embedded video and four of them had clicked
        # through to YouTube, so the panel reported the week's most engaged
        # visitors as a failure - and the Paths panel counted the same clicks
        # two panels below as "links out of the site".
        if any(s.events[name] for name in ENGAGEMENTS):
            continue
        page = next((p for p in s.steps if p in SHALLOW_PAGES), None)
        if page and s.pages == 1 and s.depth < SHALLOW_DEPTH:
            bounces[page] += 1
            seen = last_bounce.get(page)
            if seen is None or (s.last_seen or s.started) > (seen.last_seen or seen.started):
                last_bounce[page] = s
    for page, n in bounces.most_common():
        found.append(
            {
                "kind": "shallow_exit",
                "label": page,
                "score": n,
                "detail": f"{_visitors(n)} read one page, under {SHALLOW_DEPTH} % scrolled",
                "at": last_bounce[page].last_seen,
                "last": _session_visitor(last_bounce[page]),
            }
        )
    # The term, not just the count: "atlantis finds nothing" is a content
    # decision, "12 searches found nothing" is only a number. The per-term rows
    # come from SQL_CONTENT; without them the session counter is all we have.
    dead_terms = [r for r in (searches or []) if not (r.get("results") or 0) and r.get("label")]
    if dead_terms:
        for row in sorted(dead_terms, key=lambda r: int(r["n"] or 0), reverse=True):
            n = int(row["n"] or 0)
            found.append(
                {
                    "kind": "empty_search",
                    "label": str(row["label"]),
                    "score": n,
                    "detail": f"searched {n}×, found nothing",
                    "at": row.get("last_at"),
                    "last": _last_visitor(row),
                }
            )
    elif empty_searches:
        found.append(
            {
                "kind": "empty_search",
                "label": "search",
                "score": empty_searches,
                "detail": f"{empty_searches} searches found nothing",
                # Only the session counter got here, so there is no row to
                # name a moment or a visitor with.
                "at": None,
                "last": None,
            }
        )
    return sorted(found, key=lambda p: p["score"], reverse=True)[:limit]


#: How many hours the pulse strip draws. Two days is readable at 390 px.
HOURLY_STRIP_HOURS = 48


def hourly_sessions(
    rows: list[dict[str, Any]],
    sessions: list[Session],
    until: datetime,
    hours: int = HOURLY_STRIP_HOURS,
) -> list[dict[str, Any]]:
    """One bucket per hour, `hours` of them, newest last - a fixed axis.

    Folded from the rows /overview already fetched, so it costs no query. The
    query it replaces returned one row per hour that *had* events - 45 for a
    48-hour window on 2026-09-19 - and the strip drew one bar per row across a
    48-hour label, so every empty hour shifted the bars left of it.

    `sessions` is what the same rows fold to, and it is the only thing that
    knows which ids are human; re-deriving that here would be a second
    definition of "human". `human` and `ai` are both subsets of `sessions` and
    they overlap each other - the strip stacks `human` against the rest, and
    prints `ai` as a number.
    """
    human = {s.id for s in sessions if s.human}
    from_ai = {s.id for s in sessions if s.from_ai}
    end = until.replace(minute=0, second=0, microsecond=0)
    buckets: dict[datetime, set[str]] = {end - timedelta(hours=i): set() for i in range(hours)}
    for r in rows:
        seen = buckets.get(r["created_at"].replace(minute=0, second=0, microsecond=0))
        if seen is None:
            continue
        seen.add(r["session_id"])
    return [
        {
            "hour": hour,
            "sessions": len(ids),
            "human": len(ids & human),
            "ai": len(ids & from_ai),
        }
        for hour, ids in sorted(buckets.items())
    ]


#: Below this many globe_ready samples the panel prints the times it has and
#: no middle value. Five is where a median stops being one visitor's phone;
#: it is deliberately not a percentile, because eight live samples come from
#: six browsers and two of those contributed two loads each.
GLOBE_MIN_SAMPLES = 5

#: How a load that never fired globe_ready ended, in the order a load meets
#: them: phone gate -> capability check -> start -> the visitor leaving. Each
#: bucket names the SQL_GLOBE columns that count it. The frontend sends one of
#: these per load; the order only decides who wins when a session carries more
#: of them than it has unreached loads.
GLOBE_ENDINGS = (
    ("gate", ("gate_left", "gate_quit")),
    ("unsupported", ("unsupported",)),
    ("error", ("failed", "context_lost")),
    ("abandoned", ("abandoned",)),
)


def _spread(times: list[float]) -> dict[str, Any]:
    """min / median / max / samples - the median (the upper-middle element)
    only from GLOBE_MIN_SAMPLES on."""
    times = sorted(times)
    enough = len(times) >= GLOBE_MIN_SAMPLES
    return {
        "min": times[0] if times else None,
        "median": times[len(times) // 2] if enough else None,
        "max": times[-1] if times else None,
        "samples": len(times),
    }


def globe_funnel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """How many globe loads reached an interactive globe, how long the ones
    that did took, and how the others ended. Rows are SQL_GLOBE's, one per
    session.

    Measured 2026-09-19: 33 loads, 8 of them reached - about three quarters of
    the people who open the globe never see one. The denominator is page
    loads, not sessions, and the panel says so.

    `min(ready, views)` per session, because a globe_ready can arrive eighty
    seconds after its page view and straddle the window edge.

    `ready_ms.samples` is the number of globe_ready events the window holds
    and is deliberately NOT capped to `reached`: the cap above exists to keep
    the funnel from reading more successes than loads, and applying it to the
    timings would throw away real measurements. The two can differ, so
    GlobeReach's sentence names the events, not the visitors.

    `not_reached` splits `gave_up`; the invariant is
    ``sum(not_reached.values()) == gave_up``, always. Umami ties an event to a
    session, never to a page load, so the split is per session: the session's
    unreached loads (`views - min(ready, views)`) are handed to the endings in
    GLOBE_ENDINGS order, each capped by what is left. Background failures
    (`globe_error{phase:'bg:…'}`) are not endings - SQL_GLOBE excludes them,
    they belong to loads that reached the globe. `webgl_lost` while loading
    is an error: it is a start failure, and uncounted it would read as a
    crash. What no ending claims is `no_signal` - the page loaded and nothing
    else arrived (a crashed tab, or a visitor gone before the tracker loaded) -
    unless the session began before the first ending event was ever recorded
    (SQL_GLOBE's `endings_since`, None while there is none). Such a load could
    not have sent one, so it is `unmeasured`: otherwise every load from before
    the instrumentation would read as a crash for as long as the window
    reaches back. Its endings, if it has any, still count first.

    `abandon_ms` is capped where `ready_ms` is not: only the abandons that the
    split actually counted feed it, the latest ones of the session. A
    globe_abandon sent on visibilitychange->hidden can be followed by the same
    load's globe_ready (a tab switched away and back); that one is no "left
    while loading" measurement.
    """
    loads = 0
    reached = 0
    reached_sessions = 0
    times: list[float] = []
    split = {name: 0 for name, _cols in GLOBE_ENDINGS}
    no_signal = 0
    unmeasured = 0
    left_times: list[float] = []
    for r in rows:
        views = int(r["views"] or 0)
        if not views:
            continue
        got = min(int(r["ready"] or 0), views)
        loads += views
        reached += got
        reached_sessions += 1 if got else 0
        times.extend(float(ms) for ms in (r["ready_ms"] or []))
        left = views - got
        for name, cols in GLOBE_ENDINGS:
            take = min(sum(int(r[c] or 0) for c in cols), left)
            split[name] += take
            left -= take
            # `and take` is load-bearing: xs[-0:] is the whole list.
            if name == "abandoned" and take:
                left_times.extend(float(ms) for ms in (r["abandon_ms"] or [])[-take:])
        since = r["endings_since"]
        if since is None or r["first_view"] < since:
            unmeasured += left
        else:
            no_signal += left
    return {
        "loads": loads,
        "reached": reached,
        "gave_up": loads - reached,
        "sessions": {"all": sum(1 for r in rows if r["views"]), "reached": reached_sessions},
        "ready_ms": _spread(times),
        "not_reached": {**split, "no_signal": no_signal, "unmeasured": unmeasured},
        "abandon_ms": _spread(left_times),
    }


def clusters(rows: list[dict[str, Any]], min_ids: int) -> dict[str, Any]:
    """Which browser fingerprints are one machine rather than several people.

    Rows are SQL_CLUSTERS', already grouped. This adds nothing but the total,
    because the rule is one rule: a path several session ids touched inside
    one minute. Seven heuristics and a "suspected" verdict were specified and
    are deliberately not built - none of them survived measurement, and a
    suspicion on a founders dashboard is a number somebody will act on.

    There is no session total here on purpose: the panel divides by
    /overview's `sessions.all`, which the page already holds. The two numbers
    therefore always cover the same `days` span - but not the same instant:
    /clusters polls every 300 s and /overview every 60 s, so the share on
    screen can be up to five minutes out of step. Scrapers.tsx says so.
    """
    return {
        "min_ids": min_ids,
        "flagged": sum(int(r["sessions"] or 0) for r in rows),
        "clusters": [
            {
                "screen": r["screen"],
                "browser": r["browser"],
                "os": r["os"],
                "sessions": int(r["sessions"] or 0),
            }
            for r in rows
        ],
    }


def entry_exit_pages(sessions: list[Session]) -> dict[str, Any]:
    """Where confirmed-human sessions land and where they stop.

    Counts only, never a rate: at 46 human sessions, a share would be built
    from single figures. Measured 2026-09-19: story takes 20 of 46 entries and
    12 of those go no further; every country hub landing is a dead end.

    There is deliberately no "sessions that loaded no page" count here. Since
    9d, `human` is False without a page view, so over `people` that number is
    structurally zero and a panel printing "0 of 46" forever is worse than no
    sentence. The real figure - 34 of 163 sessions have no page view at all,
    every one of them inside the two /clusters fingerprints - belongs to the
    scraper story, and the LiveNow panel already states its own half of it.
    """
    people = [s for s in sessions if s.human]
    entries: Counter[str] = Counter()
    stopped: Counter[str] = Counter()
    exits: Counter[str] = Counter()
    views: Counter[str] = Counter()
    one_page = 0
    for s in people:
        entries[s.page_steps[0]] += 1
        exits[s.page_steps[-1]] += 1
        for page in s.page_steps:
            views[page] += 1
        if len(s.page_steps) == 1:
            one_page += 1
            stopped[s.page_steps[0]] += 1
    return {
        "sessions": len(people),
        "one_page": one_page,
        "moving": len(people) - one_page,
        "entries": [
            {"page": page, "sessions": n, "stopped": stopped.get(page, 0)}
            for page, n in sorted(entries.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "exits": [
            {"page": page, "sessions": n, "views": views.get(page, 0)}
            for page, n in sorted(exits.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def outbound_links(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Where a visitor went on purpose, from the same SQL_SESSION_EVENTS rows
    /journeys already fetched.

    src/analytics/boot.ts sends `outbound_click` with the link's host, so this
    needs no query and cannot disagree with the chains above it. The host is
    indexed, not probed: boot.ts only fires the event once outboundHost()
    returned a host, so a row without one is SQL drift and must fail loudly.

    There is no Discord list here. `discord_click` has never fired - the
    landing page, which carries ten of the twenty-three human clicks the
    server counted, loads no analytics module at all.
    """
    clicks: Counter[str] = Counter()
    visitors: defaultdict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r.get("event_name") != "outbound_click":
            continue
        host = r["data"]["host"]
        clicks[host] += 1
        visitors[host].add(r["session_id"])
    return [
        {"host": host, "clicks": n, "visitors": len(visitors[host])}
        for host, n in sorted(clicks.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


#: A page title ends in this plus the brand on every page but two.
TITLE_BRAND = " | "


def without_brand(title: str) -> str:
    """ "Göbekli Tepe | Ancient Nerds" -> "Göbekli Tepe". Keeps inner pipes, and
    keeps a title that carries no brand at all ("Database - Ancient Nerds",
    one of two live titles that do not end in the brand).

    The space after the opening quotes is what ruff format emits when a
    docstring starts with a quote character - do not close it up."""
    head, sep, _tail = title.rpartition(TITLE_BRAND)
    return head if sep else title


def live_row(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    """One visitor of SQL_LIVE, as the live panel prints them.

    The first four keys are exactly _last_visitor()'s shape and the id is cut
    with the same SESSION_ID_CHARS - there is no second visitor shape and no
    second id rule.
    """
    return {
        "session": str(row["session"])[:SESSION_ID_CHARS],
        "country": row.get("country"),
        "device": row.get("device"),
        "browser": row.get("browser"),
        "page": page_type(row["url_path"] or "/"),
        "title": without_brand(row["title"] or row["url_path"] or "/"),
        # The path is what the row links to, so it travels next to the title:
        # the dashboard is served from its own host and cannot resolve it.
        "path": row["url_path"] or "/",
        "here": int((now - row["page_since"]).total_seconds()),
        "last_seen": row["last_seen"].isoformat(),
    }


#: Umami's `device` is ua-parser's device type with one local rule of its own:
#: a desktop operating system on a screen narrower than 1920 px is written as
#: "laptop". That is a screen-size split inside one kind of machine, so the
#: panel folds the two back together and answers the only question a founder
#: asks here - phone or not. Measured 2026-09-19 over seven days: laptop 117,
#: mobile 45, desktop 6, tablet 0 in 168 sessions, i.e. about 27 % phones.
#: Reading "laptop" as its own class turned that into "88 % mobile" once, in a
#: draft of this panel; it is the reason the fold is a named table and not an
#: inline replace.
DEVICE_GROUPS = {
    "laptop": "desktop",
    "desktop": "desktop",
    "mobile": "mobile",
    "tablet": "tablet",
}
#: A session whose client sent no screen size: Umami writes NULL and cannot
#: place it. Shown as its own row rather than dropped, because the counts next
#: to the shares have to add up to the sessions the page claims.
UNKNOWN_DEVICE = "unknown"


def _device_bucket(device: str | None) -> str:
    """One of DEVICE_GROUPS' values, `unknown` for NULL - and anything Umami
    invents later as itself, because folding an unknown word into `desktop`
    would hide the change instead of showing it."""
    if not device:
        return UNKNOWN_DEVICE
    return DEVICE_GROUPS.get(device, device)


def devices_and_languages(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What the visitors browse with and what language they asked for.

    Rows are SQL_DEVICES', one per (device, language) pair. Counts, never a
    share on their own: at 168 sessions every cell is small enough that the
    panel has to print the number next to any percentage it draws, and
    `sessions` is the denominator it divides by.

    Languages travel twice because they are read twice: `languages` keeps the
    full tag the browser sent, which is what a row is titled with (en-US 93,
    en-GB 21, zh-CN 11, de-DE 7, tr-TR 4 on 2026-09-19), and
    `language_groups` folds them onto the primary subtag, which is the only
    headline this sample size carries - en-US and en-GB are one audience, and
    "en 114 of 168" says that where five separate rows do not.
    """
    devices: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    groups: Counter[str] = Counter()
    total = 0
    for r in rows:
        n = int(r["sessions"] or 0)
        total += n
        devices[_device_bucket(r["device"])] += n
        tag = (r["language"] or "").strip()
        if not tag:
            continue
        languages[tag] += n
        groups[tag.split("-", 1)[0].lower()] += n
    return {
        "sessions": total,
        "devices": [
            {"device": d, "sessions": n}
            for d, n in sorted(devices.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "languages": [
            {"language": tag, "sessions": n}
            for tag, n in sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "language_groups": [
            {"language": tag, "sessions": n}
            for tag, n in sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


#: The depth marks src/analytics/boot.ts fires, in its own order. One event
#: per mark per page load. newDepthSteps() queues every mark the visitor has
#: crossed and not yet sent, so reaching 75 is meant to send 25 and 50 with it
#: - but the marks are four separate fire-and-forget requests from one frame,
#: and the live table shows they do not all arrive: on 2026-09-19 six of the
#: seventeen story sessions carry one deep mark and no shallower one ({50},
#: {75} and {100} twice each). Hence `depth >= step` below rather than an
#: equality: a session that reported 100 passed 25, whether or not the 25 ever
#: reached us.
SCROLL_STEPS = (25, 50, 75, 100)


def reading_funnel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """How far visitors read, per page type, in whole visitors.

    Folded from the same SQL_SESSION_EVENTS rows /journeys already fetched -
    `scroll_depth` carries its own `page` (the page type) and `depth`, so this
    needs no query and no url_path.

    Counts only, and never a percentage. Run against the live seven-day rows
    on 2026-09-19 this returns story 17 / 15 / 13 / 10, country 2 / 2 / 2 / 2,
    site 1 / 1 / 1 / 1, over 20 readers. Twenty reads cannot carry a rate, and
    a rate is what would be read as one - so the panel prints the numbers and
    names its sample size.

    The story row is 17 and not the 11 the raw events suggest, because 11 is
    only how many sessions sent a mark carrying literally 25; six more sent a
    deeper mark and nothing below it (see SCROLL_STEPS). Counting those at 25
    as well is the whole reason the loop compares with `>=`: without it the
    top of the funnel would read smaller than the 13 sessions that provably
    passed 75.

    `readers` is the denominator and it is sessions that scrolled, never page
    views: boot.ts only arms the listener on a content page and only fires on
    a real scroll event, which is exactly why the numbers are this small and
    why they mean something.
    """
    reached: defaultdict[str, defaultdict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    readers: set[str] = set()
    for r in rows:
        if r.get("event_name") != "scroll_depth":
            continue
        # Both keys are boot.ts's own (installScrollDepth sends depth and
        # page together): a scroll_depth carrying neither is drift and has to
        # fail loudly, exactly like outbound_links' host above.
        data = r["data"]
        page = data["page"]
        readers.add(r["session_id"])
        depth = int(float(data["depth"]))
        for step in SCROLL_STEPS:
            if depth >= step:
                reached[page][step].add(r["session_id"])
    counted = {
        page: [len(steps.get(step, set())) for step in SCROLL_STEPS]
        for page, steps in reached.items()
    }
    return {
        "steps": list(SCROLL_STEPS),
        "readers": len(readers),
        "pages": [
            {"page": page, "sessions": counts}
            for page, counts in sorted(counted.items(), key=lambda kv: (-kv[1][0], kv[0]))
        ],
    }
