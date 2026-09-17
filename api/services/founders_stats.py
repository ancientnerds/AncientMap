# SPDX-License-Identifier: AGPL-3.0-only
"""Founder-level answers computed from Umami rows: sessions, human filter,
session types, journeys. Pure functions — the routes feed them the rows from
pipeline.umami_db (SQL_SESSION_EVENTS); the tests feed them fixtures.

The rules are the ones locked in the plan (2026-09-17):

* human = at least one interaction event or at least two page views;
  everything else is "unconfirmed" (a stealth scraper or a bouncing human —
  cookieless data cannot tell them apart, so both counts are shown).
* session type = the first match in the order Forscher → Entdecker → Sucher →
  Leser → Sonstige.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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
}
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


def source_family(referrer: str | None, utm_source: str | None = None) -> str:
    """Where a session came from, in founder words: a utm_source verbatim,
    else "google" / "search" / "ai" / the bare referrer host / "direct"."""
    if utm_source:
        return utm_source
    if not referrer:
        return "direct"
    r = referrer.lower()
    if any(h in r for h in AI_HOSTS):
        return "ai"
    if any(h in r for h in SEARCH_HOSTS):
        return "google" if "google." in r else "search"
    return r.removeprefix("www.")


@dataclass
class Session:
    id: str
    started: datetime
    country: str | None
    device: str | None
    entry: str | None = None
    steps: list[str] = field(default_factory=list)  # page types and event names, in order
    pages: int = 0
    events: Counter[str] = field(default_factory=Counter)
    depth: int = 0  # deepest scroll_depth seen, percent

    @property
    def human(self) -> bool:
        return self.pages >= 2 or any(self.events[n] for n in INTERACTIONS)

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
            return "forscher"
        if self.events["site_open"] or ("globe" in pages and self.events["filter_toggle"]):
            return "entdecker"
        if self.events["search"]:
            return "sucher"
        if pages & {"story", "journal"}:
            return "leser"
        return "sonstige"


def sessions_from_rows(rows: list[dict[str, Any]]) -> list[Session]:
    """Fold SQL_SESSION_EVENTS rows (ordered by session, time) into sessions."""
    by_id: dict[str, Session] = {}
    for r in rows:
        s = by_id.get(r["session_id"])
        if s is None:
            s = by_id[r["session_id"]] = Session(
                r["session_id"], r["created_at"], r.get("country"), r.get("device")
            )
        data = r.get("data") or {}
        if r["event_type"] == 1:
            if s.entry is None:
                s.entry = source_family(r.get("referrer_domain"), r.get("utm_source"))
            s.pages += 1
            s.steps.append(page_type(r["url_path"] or "/"))
        else:
            name = r["event_name"] or "event"
            s.events[name] += 1
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
