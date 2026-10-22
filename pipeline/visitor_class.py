# SPDX-License-Identifier: AGPL-3.0-only
"""Who is visiting: the one definition of every visitor class, threshold and
rule the founders dashboard and the Lyra digest use.

Two populations, two sources, never joined per visitor (joining them would
mean recomputing Umami's salted hash, which de-anonymises visitors):

* **Sessions** - Umami's, so only clients that ran our JavaScript.
  session_class() puts each into one of SESSION_CLASSES. Session.human
  (pipeline/stats_analysis.py) decides first; a burst or volume mark never
  overrides it. The lockstep mark is the one exception, see LOCKSTEP_MIN.
* **Requests** - nginx's request log (pipeline/request_log.py), so every
  client with its IP. request_class() puts each page request into one of
  REQUEST_CLASSES.

Stdlib only and no import of stats_analysis (which imports this module):
the functions work on duck-typed sessions, so the digest inside the Lyra
image gets the same rules.

A session's **fingerprint** is (browser, os, screen, language). It leaves the
country out on purpose: the 800x600 zh-CN scraper of 2026-10-15/16 rotated
through 101 countries. Its **start** is Umami's ``session.created_at``,
which does not move with the window a fold reads.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

#: Burst: a session whose start lies in some BURST_WINDOW holding at least
#: BURST_MIN starts of its fingerprint. Measured over the 30 days to
#: 2026-10-22: 3,382 sessions marked, none of them human; it catches the SG
#: burst of 2026-10-22 (1,427 sessions, chrome/Windows 10/1280x1200/en-US)
#: within a minute and the 800x600 zh-CN rotation (1,893 sessions). Lower
#: thresholds reach humans: 6 touches 3, 5 touches 8.
BURST_WINDOW = timedelta(minutes=10)
BURST_MIN = 8
#: Volume: at least this many starts of the fingerprint on the session's UTC
#: day - the slow drips a burst misses (SG 1280x1200 at 53-105 a day). The
#: boundary group holds one rule-human (chrome/Windows 10/1920x1080/zh-CN on
#: 2026-10-16, exactly 50 starts), who stays human because the human check
#: comes first.
VOLUME_MIN = 50
#: Lockstep (owner, 2026-10-22): at least LOCKSTEP_MIN crawl-shaped sessions
#: of one fingerprint starting within LOCKSTEP_WINDOW of each other, and every
#: crawl-shaped session of that fingerprint within LOCKSTEP_REACH of such a
#: start. Crawl-shaped = direct entry, at least LOCKSTEP_URLS distinct URLs,
#: not one act of its own. It is the CN chrome/Windows 10/1600x1600/zh-CN crawl
#: of 2026-10-01..11: 54 crawl-shaped sessions of 8-34 URLs each, every
#: site_open fired by the page itself, three to five of them starting in the
#: same minute. Measured over the 30 days to 2026-10-22 (61,251 production
#: SQL_SESSION_EVENTS rows): the rule marks 49 of them, and 48 of those were
#: human under Session.human (10-01: 12, 10-02: 17, 10-03: 10, 10-04: 3,
#: 10-05: 2, 10-06: 3, 10-08: 1), because before CAPTURE_FIX a second URL
#: proved a person; it touches no session of any other fingerprint. The other
#: five (2026-10-10 and -11, 17-22 URLs) start more than LOCKSTEP_REACH after
#: the last lockstep start and stay unclear (multi_direct): they come after
#: CAPTURE_FIX and were never human. This is the one machine rule that
#: overrides Session.human: those 48 are human only by that pre-CAPTURE_FIX
#: allowance, and three crawls started in one minute are no person reading.
#: Over the 36 days to 2026-10-22 it is the only fingerprint with three
#: crawl-shaped starts in one minute; the nearest other is a chrome/Mac
#: OS/1920x1080/en-US pair (two starts, two countries), which a minimum of
#: three leaves alone.
LOCKSTEP_MIN = 3
LOCKSTEP_WINDOW = timedelta(seconds=60)
LOCKSTEP_REACH = timedelta(days=7)
LOCKSTEP_URLS = 5
#: A session that has not been decided yet: its latest visit began less than
#: this long ago. founders_stats.HERE_WINDOW is this same object.
UNDECIDED_WINDOW = timedelta(minutes=30)
#: A browser page counts as having run our JavaScript when the same client
#: sent a beacon within this long of it, either side.
BEACON_WINDOW = timedelta(seconds=120)
#: Disallowed in robots.txt and linked only by a hidden anchor in the app
#: shell: whoever fetches it ignores robots.txt.
HONEYPOT_PATH = "/index-all/"
#: A path + clock-minute group with this many session ids is a fetcher that
#: keeps no state (pipeline/umami_db.py SQL_CLUSTERS, which says why three).
CLUSTER_MIN_IDS = 3

SESSION_CLASSES = ("human", "human_ai", "scraper_js", "undecided", "unclear")
#: The classes Session.human puts a session in.
HUMAN_CLASSES = frozenset({"human", "human_ai"})
SESSION_REASONS = (
    "burst",
    "volume",
    "lockstep",
    "no_pageview",
    "one_page",
    "cluster",
    "multi_direct",
)
REQUEST_CLASSES = (
    "browser_js",
    "scraper_nojs",
    "robots_ignorer",
    "self_declared_bot",
    "impostor",
    "search",
    "ai_training",
    "ai_live",
    "bot_other",
    "prefetch",
    "unclear",
)
LABELS = {
    "human": "Humans",
    "human_ai": "Humans from AI answers",
    "scraper_js": "JS scrapers",
    "undecided": "Just arrived, not decided yet",
    "burst": "8+ starts of one fingerprint in 10 minutes",
    "volume": "50+ starts of one fingerprint in a UTC day",
    "lockstep": "Crawls of a fingerprint seen starting 3+ crawls in one minute (within 7 days)",
    "no_pageview": "Events without a page view",
    "one_page": "One page, no act of its own",
    "cluster": "Shares a page and minute with 2+ other sessions",
    "multi_direct": "Direct entry, several pages, no act of its own",
    "browser_js": "Browsers that ran our JavaScript",
    "scraper_nojs": "Browser-like clients without JavaScript",
    "robots_ignorer": "Clients that ignore robots.txt",
    "self_declared_bot": "Other self-declared bots and tools",
    "impostor": "Impostors (claimed bot outside its operator's ranges)",
    "search": "Search engines",
    "ai_training": "AI training crawlers",
    "ai_live": "AI assistants and AI search",
    "bot_other": "Other known crawlers",
    "prefetch": "Browser prefetches",
    "unclear": "Unclear",
}

Fingerprint = tuple[str | None, str | None, str | None, str | None]


def fingerprint(s: Any) -> Fingerprint:
    return (s.browser, s.os, s.screen, s.language)


def crawl_shaped(s: Any) -> bool:
    """Direct entry, LOCKSTEP_URLS or more distinct URLs, no act of its own."""
    return s.entry == "direct" and len(s.urls) >= LOCKSTEP_URLS and not s.acted


def _starts(sessions: Iterable[Any]) -> dict[Fingerprint, list[Any]]:
    """Sessions per fingerprint, by start."""
    by: defaultdict[Fingerprint, list[Any]] = defaultdict(list)
    for s in sessions:
        by[fingerprint(s)].append(s)
    for group in by.values():
        group.sort(key=lambda s: s.created)
    return by


def _windows(group: list[Any], width: timedelta, minimum: int) -> set[str]:
    """The ids whose start lies in some half-open window of `width` holding at
    least `minimum` starts: one two-pointer pass over a start-sorted group."""
    marked: set[str] = set()
    done = 0  # every index below this one is already marked
    end = 0
    for first in range(len(group)):
        end = max(end, first)
        while end + 1 < len(group) and group[end + 1].created - group[first].created < width:
            end += 1
        if end - first + 1 >= minimum:
            for s in group[max(first, done) : end + 1]:
                marked.add(s.id)
            done = end + 1
    return marked


def _volume(group: list[Any]) -> set[str]:
    days: defaultdict[date, list[str]] = defaultdict(list)
    for s in group:
        days[s.created.astimezone(UTC).date()].append(s.id)
    return {i for ids in days.values() if len(ids) >= VOLUME_MIN for i in ids}


def _lockstep(group: list[Any]) -> set[str]:
    crawls = [s for s in group if crawl_shaped(s)]
    lockstep = _windows(crawls, LOCKSTEP_WINDOW, LOCKSTEP_MIN)
    anchors = [s.created for s in crawls if s.id in lockstep]
    return {s.id for s in crawls if any(abs(s.created - a) <= LOCKSTEP_REACH for a in anchors)}


def machine_groups(sessions: Iterable[Any]) -> dict[str, str]:
    """Every session (human or not) whose start crossed a burst or volume
    threshold of its fingerprint, mapped to that reason - burst before volume."""
    out: dict[str, str] = {}
    for group in _starts(sessions).values():
        for i in _volume(group):
            out[i] = "volume"
        for i in _windows(group, BURST_WINDOW, BURST_MIN):
            out[i] = "burst"
    return out


def machine_marks(sessions: Iterable[Any]) -> dict[str, str]:
    """Session id -> "lockstep", "burst" or "volume". A lockstep mark goes on
    any crawl-shaped session (it overrides Session.human, see LOCKSTEP_MIN);
    burst and volume go only on sessions that are not human."""
    sessions = list(sessions)
    marks = {i: "lockstep" for group in _starts(sessions).values() for i in _lockstep(group)}
    human = {s.id for s in sessions if s.id not in marks and s.human}
    for i, reason in machine_groups(sessions).items():
        if i not in human:
            marks.setdefault(i, reason)
    return marks


def humans_in_machine_groups(sessions: Iterable[Any]) -> int:
    """Rule-humans whose fingerprint crossed a burst or volume threshold: the
    early warning that a spike is pushing human fingerprints over them."""
    sessions = list(sessions)
    groups = machine_groups(sessions)
    return sum(1 for s in sessions if s.human and s.id in groups)


def cluster_ids(rows: Iterable[dict[str, Any]]) -> set[str]:
    """SQL_CLUSTERS in Python over SQL_SESSION_EVENTS rows: the ids that share
    a path and a clock minute with CLUSTER_MIN_IDS - 1 others, over every
    event, not only page views (umami_db says why)."""
    groups: defaultdict[tuple[str | None, datetime], set[str]] = defaultdict(set)
    for r in rows:
        groups[(r["url_path"], r["created_at"].replace(second=0, microsecond=0))].add(
            r["session_id"]
        )
    return {i for ids in groups.values() if len(ids) >= CLUSTER_MIN_IDS for i in ids}


def session_class(s: Any, now: datetime) -> tuple[str, str | None]:
    """(class, reason). The first rule that matches wins: a lockstep mark,
    human (from an AI answer first), a burst or volume mark, undecided while
    the latest visit is young, then the reasons it stays unclear."""
    if s.machine == "lockstep":
        return "scraper_js", "lockstep"
    if s.human:
        return ("human_ai" if s.from_ai else "human"), None
    if s.machine is not None:
        return "scraper_js", s.machine
    if not s.page_steps:
        return "unclear", "no_pageview"
    if now - s.visit_start < UNDECIDED_WINDOW:
        return "undecided", None
    if s.cluster:
        return "unclear", "cluster"
    if s.entry == "direct" and len(s.urls) >= 2:
        return "unclear", "multi_direct"
    return "unclear", "one_page"


def session_counts(sessions: list[Any], now: datetime) -> dict[str, Any]:
    """The fold's totals: sessions per class and per reason, and the
    rule-humans inside machine groups."""
    classes: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for s in sessions:
        cls, reason = session_class(s, now)
        classes[cls] += 1
        if reason is not None:
            reasons[reason] += 1
    return {
        "total": len(sessions),
        "classes": {c: classes[c] for c in SESSION_CLASSES},
        "reasons": {r: reasons[r] for r in SESSION_REASONS},
        "humans_in_machine_groups": humans_in_machine_groups(sessions),
    }


def bursts(sessions: Iterable[Any]) -> list[dict[str, Any]]:
    """Maximal runs of burst-marked sessions of one fingerprint whose starts
    lie under BURST_WINDOW apart, newest first."""
    marked = [s for s in sessions if s.machine == "burst"]
    out: list[dict[str, Any]] = []
    for (browser, os_, screen, language), group in _starts(marked).items():
        run: list[Any] = []
        for s in [*group, None]:
            if run and (s is None or s.created - run[-1].created >= BURST_WINDOW):
                out.append(
                    {
                        "start": run[0].created,
                        "end": run[-1].created,
                        "sessions": len(run),
                        "browser": browser,
                        "os": os_,
                        "screen": screen,
                        "language": language,
                        "country": Counter(x.country for x in run).most_common(1)[0][0],
                    }
                )
                run = []
            if s is not None:
                run.append(s)
    return sorted(out, key=lambda b: b["start"], reverse=True)


# ---- requests (nginx requests.log) ---------------------------------------

#: crawler_log.KINDS -> request class.
BOT_CLASSES = {
    "search": "search",
    "training": "ai_training",
    "ai_search": "ai_live",
    "ai_user": "ai_live",
    "other": "bot_other",
}
#: robots.txt-only tokens. No real crawler sends them in its user agent, so a
#: UA that names one is an impostor whatever its address.
EXTENDED_TOKENS = re.compile(r"google-extended|applebot-extended", re.IGNORECASE)
#: The three requests only our JavaScript sends.
BEACONS = (("POST", "/api/pulse"), ("GET", "/pulse.js"), ("GET", "/api/app/interactive"))
PAGE_STATUSES = (200, 410)


def _path(uri: str) -> str:
    return uri.split("?", 1)[0]


def is_beacon(method: str, uri: str) -> bool:
    return (method, _path(uri)) in BEACONS


def is_page(method: str, uri: str, status: int) -> bool:
    """A GET answered 200 or 410 that is no beacon, no .xml or .txt file and
    nothing under /feeds/."""
    path = _path(uri)
    return (
        method == "GET"
        and status in PAGE_STATUSES
        and not is_beacon(method, uri)
        and not path.endswith((".xml", ".txt"))
        and not path.startswith("/feeds/")
    )


def is_honeypot(uri: str) -> bool:
    return _path(uri).startswith(HONEYPOT_PATH)


def is_prefetch(purpose: str) -> bool:
    return "prefetch" in purpose.lower()


def beacon_near(at: datetime, beacons: list[datetime]) -> bool:
    """True when the start-sorted `beacons` of a client hold one within
    BEACON_WINDOW of `at`, either side."""
    i = bisect_left(beacons, at - BEACON_WINDOW)
    return i < len(beacons) and beacons[i] <= at + BEACON_WINDOW


def request_class(
    *,
    purpose: str,
    ua: str,
    bot_kind: str | None,
    verified: bool | None,
    self_declared: bool,
    honeypot: bool,
    beacon: bool,
    dnt: str,
    gpc: str,
) -> tuple[str, bool]:
    """(class, unverified) of one request, the first rule that matches.

    `bot_kind` is the crawler_log.BOTS kind of the UA's token (None for no
    token) and `verified` that bot's crawler_log.verified(); `self_declared`
    is referral_log.BOT_UA_RE on the UA; `honeypot` says the client fetched
    HONEYPOT_PATH other than as a prefetch; `beacon` says it sent one within
    BEACON_WINDOW of this request. A browser UA's request is classed as a
    page (is_page); `unverified` is True only for a known bot whose operator
    publishes no ranges.
    """
    if is_prefetch(purpose):
        return "prefetch", False
    if EXTENDED_TOKENS.search(ua):
        return "impostor", False
    if bot_kind is not None:
        if verified is False:
            return "impostor", False
        return BOT_CLASSES[bot_kind], verified is None
    if self_declared:
        return "self_declared_bot", False
    if honeypot:
        return "robots_ignorer", False
    if beacon:
        return "browser_js", False
    # The tracker honours Do Not Track (data-do-not-track), so such a person
    # sends no beacon: not a scraper on that evidence.
    if dnt == "1" or gpc == "1":
        return "unclear", False
    return "scraper_nojs", False
