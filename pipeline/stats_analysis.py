# SPDX-License-Identifier: AGPL-3.0-only
"""Founder-level answers computed from Umami rows — the analysis half of the
pair with pipeline/umami_db.py (which fetches them).

Under pipeline/, not api/services/, for two reasons: it is pure functions
over rows with no FastAPI in sight, and the orchestrator's weekly digest
runs inside the Lyra image, which contains no `api` tree at all.

Original docstring follows.

Founder-level answers computed from Umami rows: sessions, human filter,
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


#: Google's "good" thresholds in milliseconds — above them a page is slow for
#: three quarters of its visitors. CLS has no entry: it is a share, not a time.
VITAL_LIMITS = {"LCP": 2500, "INP": 200}
#: One dead hit is a typed typo; two are a link somebody published.
BROKEN_LINK_MIN = 2
#: Below a quarter of the page the visitor read the headline and left.
SHALLOW_DEPTH = 25
#: The page types a bounce is worth reporting for. Neither string is an event
#: name, so a step carrying one is always the page view, never an action.
SHALLOW_PAGES = {"story", "site"}


def problems(
    sessions: list[Session],
    not_found: list[dict[str, Any]],
    vitals: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    searches: list[dict[str, Any]] | None = None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Where the platform fails its visitors, worst first.

    Five kinds, each with a score that makes them comparable: a JavaScript
    error counts triple (it breaks the page for everyone who hits it), a dead
    link double (someone is sending people into the void), a slow page as
    often as it was measured, a bounce and an empty search once.

    `not_found`, `vitals` and `errors` are the rows of SQL_NOT_FOUND,
    SQL_VITALS and SQL_ERRORS; the bounces and empty searches come from the
    sessions, so no query has to be repeated.

    Every `label` names the thing that is broken and nothing else — the panel
    puts the kind in front of it, so "story lädt langsam" would say it twice.
    """
    found: list[dict[str, Any]] = []
    for row in errors:
        found.append(
            {
                "kind": "js_error",
                "label": row["message"],
                "score": row["n"] * 3,
                "detail": f"{row['n']}× auf {row['page']}",
            }
        )
    for row in vitals:
        limit_ms = VITAL_LIMITS.get(row["name"])
        if limit_ms is None or row["p75"] <= limit_ms:
            continue
        found.append(
            {
                "kind": "slow_page",
                # The metric belongs in the label: a page type can be slow twice.
                "label": f"{row['page']} · {row['name']}",
                "score": row["samples"],
                "detail": (
                    f"p75 {round(row['p75'])} ms statt {limit_ms} ms, {row['samples']} Messungen"
                ),
            }
        )
    for row in not_found:
        if row["n"] < BROKEN_LINK_MIN:
            continue
        found.append(
            {
                "kind": "broken_link",
                "label": row["path"],
                "score": row["n"] * 2,
                "detail": f"{row['n']} Aufrufe ins Leere, Herkunft {row['referrer']}",
            }
        )
    bounces: Counter[str] = Counter()
    empty_searches = 0
    for s in sessions:
        empty_searches += s.events["search_empty"]
        page = next((p for p in s.steps if p in SHALLOW_PAGES), None)
        if page and s.pages == 1 and s.depth < SHALLOW_DEPTH:
            bounces[page] += 1
    for page, n in bounces.most_common():
        found.append(
            {
                "kind": "shallow_exit",
                "label": page,
                "score": n,
                "detail": f"{n} Sitzungen mit einer Seite und unter {SHALLOW_DEPTH} % Scrolltiefe",
            }
        )
    # The term, not just the count: "atlantis findet nichts" is a content
    # decision, "12 Suchen fanden nichts" is only a number. The per-term rows
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
                    "detail": f"{n}x gesucht, nichts gefunden",
                }
            )
    elif empty_searches:
        found.append(
            {
                "kind": "empty_search",
                "label": "search",
                "score": empty_searches,
                "detail": f"{empty_searches} Suchanfragen fanden nichts",
            }
        )
    return sorted(found, key=lambda p: p["score"], reverse=True)[:limit]
