# Founders Dashboard & Feedback Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the two founders one mobile-first NERV page at `https://stats.ancientnerds.com/` that answers three questions from the Umami data — what most visitors do, how they navigate, where the platform fails them — plus the missing feedback hooks (site pages, Lyra answers, globe idle), UTM on the video links, and a Discord alert/digest so the answers reach the founders without opening anything.

**Architecture:** Umami keeps collecting (tracker + events already live). A read-only query layer in `pipeline/umami_db.py` (shared by API and orchestrator) turns Umami's `website_event` / `event_data` / `session` tables into founder-level answers; `api/routes/founders_stats.py` exposes them under `/api/stats/*`, gated by the existing `an_stats` cookie (`api/routes/stats_access.py`). A new Vite entry `dashboard.html` renders the page; nginx serves it as the root of the stats host, keeps `/api/stats/*` and our `/assets/` for it, and proxies everything else to Umami as today. Alerts and the weekly digest are orchestrator steps reusing the same query layer and the existing Discord webhook sender.

**Tech Stack:** FastAPI + SQLAlchemy (raw SQL against the `umami` database, same Postgres), React 18 + Vite (existing multi-page setup), inline SVG map from Natural Earth 110m land + country centroids, vitest + pytest, nginx.

**Scope guard (owner, 2026-09-17):** nothing in this plan changes what is collected or how long it is kept. Every new event carries feature usage only. The one privacy-text edit (Task A5) documents feedback texts that are already being stored.

---

## Decisions locked in

| Question | Decision | Why |
|---|---|---|
| Where does the dashboard live? | `https://stats.ancientnerds.com/` (root). Umami stays behind it at `/websites/…`; "Open Umami" links there. | One address for the founders; the Discord gate already protects the host; Umami's UI cannot be re-rooted without a custom image. |
| Data access | Read-only SQL on the `umami` database through a second SQLAlchemy engine (`UMAMI_DB_PASSWORD` is already in the VPS `.env`, both api and lyra containers read it). | No Umami API tokens to manage, joins with our own tables possible, same Postgres. |
| Map | SVG, equirectangular, Natural Earth 110m land outline (~150 KB, public domain) + country centroids (≈5 KB JSON generated once). Dots per country sized by visits, 24-hour scrubber. | Umami stores country/region/city names, no coordinates; country level is honest and light. The Three.js globe can come later. |
| "Human" filter | A session counts as human when it has ≥ 1 interaction event (`site_open`, `search`, `filter_toggle`, `story_open`, `paper_open`, `media_play`, `lyra_chat`, `share`, `feedback`, `scroll_depth`) **or** ≥ 2 page views. Everything else is "unconfirmed". Both counts are shown; the headline numbers use human. | Cookieless data cannot tell a stealth scraper from a bouncing human; showing both is the honest version. |
| Session types | Leser: ≥ 1 story/paper/journal page view, no `site_open`, no search. Entdecker: ≥ 1 `site_open` or globe page with `filter_toggle`. Forscher: `paper_open` or `lyra_chat` or `/research/` pages. Sucher: `search` without `site_open`. Sonstige: the rest. A session gets the first matching type in the order Forscher → Entdecker → Sucher → Leser → Sonstige. | Simple, explainable rules; tunable in one table. |
| Alerts / digest | Orchestrator steps (`pipeline/lyra/analytics_alerts.py`), hourly check + Monday 06:00 UTC digest, posted with `api.services.notify.send_discord_webhook`. Active only when `DISCORD_WEBHOOK_URL` is set (owner creates the webhook). | Runs where the other periodic work runs; no second scheduler. |
| Retention | Unchanged (Umami keeps raw events). | Owner's call; revisit at 13 months. |

**Needs from the owner:** a Discord webhook URL for the alerts channel (Part D only). Nothing else.

---

## File structure

**Part A — quick wins**
- Modify `ancient-nerds-map/src/analytics/index.ts` — `EventName` gains `globe_idle`; `FeedbackPromptKind` gains `site_page`, `lyra_answer`.
- Modify `ancient-nerds-map/src/analytics/feedback.ts` — new prompt kinds.
- Modify `ancient-nerds-map/src/pages/SitePage.tsx` — `FeedbackPrompt` before `CommunityCta`.
- Create `ancient-nerds-map/src/components/lyra/AnswerFeedback.tsx` — thumbs under a finished Lyra answer.
- Modify `ancient-nerds-map/src/components/LyraChatModal.tsx` — render `AnswerFeedback` after each finished assistant message.
- Modify `ancient-nerds-map/src/App.tsx` — `globe_idle` after 30 s without interaction.
- Modify `pipeline/video/shorts_export.py` — `?utm_source=youtube&utm_medium=short` on the page link (only if the file is clean in the working tree; the video session edits this area).
- Modify `ancient-nerds-map/privacy.html`, `PRIVACY.md` — one clause: feedback texts.
- Tests: `ancient-nerds-map/src/analytics/__tests__/feedback.test.ts`, `tests/pipeline/video/test_shorts_export_utm.py`.

**Part B — dashboard V1**
- Create `pipeline/umami_db.py` — engine factory + the read queries (pure SQL, parameterised, one function per panel). Shared by API and orchestrator.
- Create `api/services/founders_stats.py` — session typing, human filter, journeys, problem ranking (pure Python over query rows; unit-testable without a DB).
- Create `api/routes/founders_stats.py` — `/api/stats/overview`, `/api/stats/map`, `/api/stats/content`, `/api/stats/feedback`, `/api/stats/sources`, each `Depends(require_stats_session)`.
- Modify `api/routes/stats_access.py` — export `require_stats_session` (401 dependency built on `stats_session`).
- Modify `api/main.py` — mount the router under `/api/stats`.
- Modify `pyproject.toml` — import-linter: `api.** -> pipeline.umami_db`.
- Create `ancient-nerds-map/dashboard.html`, `ancient-nerds-map/src/dashboardMain.tsx`.
- Create `ancient-nerds-map/src/pages/DashboardPage.tsx` — layout + data loading.
- Create `ancient-nerds-map/src/components/dashboard/{Pulse,VisitorMap,SessionTypes,TopContent,FeedbackInbox,Sources}.tsx`, `ancient-nerds-map/src/components/dashboard/useStats.ts` (fetch + refresh), `ancient-nerds-map/src/styles/dashboard.css`.
- Create `public/data/layers/ne_110m_land.geojson` (downloaded, public domain) and `ancient-nerds-map/src/data/country_centroids.json` (generated by `scripts/build_country_centroids.py`).
- Modify `ancient-nerds-map/vite.config.ts` — add the `dashboard` entry; `analyticsTag` skips `dashboard.html`.
- Modify `ancientnerds-nginx-config` (stats server) — `/` → `dashboard.html`, `/assets/`, `/fonts/`, `/data/layers/ne_110m_land.geojson` from dist/public, `/api/stats/` → API; rest → Umami.
- Tests: `tests/pipeline/test_umami_db_queries.py` (SQL text sanity, no DB), `tests/api/test_founders_stats.py` (typing/filter/journeys with fixture rows), `ancient-nerds-map/src/components/dashboard/__tests__/*.test.ts` (pure helpers: map projection, hour buckets).

**Part C — dashboard V2**
- Extend `pipeline/umami_db.py`, `api/services/founders_stats.py`, `api/routes/founders_stats.py` with `/api/stats/journeys`, `/api/stats/problems`.
- Create `ancient-nerds-map/src/components/dashboard/{Journeys,Problems}.tsx`.

**Part D — alerts & digest**
- Create `pipeline/lyra/analytics_alerts.py` — `check_hourly()` (error spike, 5xx-like signals from `js_error`, empty-search spike) and `weekly_digest()`.
- Modify `pipeline/lyra/orchestrator.py` — steps `alerts` (every cycle) and `digest` (every cycle, sends only Monday 06:xx UTC once).
- Modify `pyproject.toml` — import-linter exception `pipeline.lyra.analytics_alerts -> api.services.notify` (same pattern as `pipeline.lyra.curator`).
- Tests: `tests/pipeline/test_analytics_alerts.py`.

---

## Part A — Quick wins (≈ 3 h)

### Task A1: Feedback on site pages

**Files:**
- Modify: `ancient-nerds-map/src/analytics/feedback.ts`
- Modify: `ancient-nerds-map/src/pages/SitePage.tsx`
- Test: `ancient-nerds-map/src/analytics/__tests__/feedback.test.ts`

- [ ] **Step 1: Extend the prompt kinds (failing test first)**

Append to `feedback.test.ts`:
```ts
it('knows the site page and lyra answer prompts', () => {
  expect(feedbackPayload('site_page', 'no', 'coordinates are off', '/sites/peru/x-1234abcd').page).toBe('site')
  expect(feedbackPayload('lyra_answer', 'yes', '', '/lyra.html').prompt).toBe('lyra_answer')
})
```
Run: `cd ancient-nerds-map && npx vitest run src/analytics` — Expected: type error / FAIL (kinds unknown).

- [ ] **Step 2: Add the kinds**

In `feedback.ts`:
```ts
export type FeedbackPromptKind = 'search_empty' | 'story_end' | 'not_found' | 'site_page' | 'lyra_answer'
```
Run the tests — Expected: PASS.

- [ ] **Step 3: Render the prompt on the site page**

In `SitePage.tsx`, add `import FeedbackPrompt from '../components/FeedbackPrompt'` and, directly above `<CommunityCta globeHref=…`:
```tsx
      <FeedbackPrompt
        prompt="site_page"
        question="Missing or wrong on this site?"
        yesNo
        placeholder="What should we fix or add?"
      />
```
(The `yesNo` pair reads "Yes / No" to "Is this page useful?" — keep the question as above; the pair answers "found what you needed?".)

- [ ] **Step 4: Verify and commit**

Run: `npm run -s type-check && npx vitest run src/analytics && npm run -s build:ssr` — Expected: all green (SSR build proves the component renders server-side).
```bash
git add ancient-nerds-map/src/analytics/feedback.ts ancient-nerds-map/src/pages/SitePage.tsx ancient-nerds-map/src/analytics/__tests__/feedback.test.ts
git commit -m "feat(analytics): feedback prompt on site pages (site_page)"
```

### Task A2: Thumbs under Lyra answers

**Files:**
- Create: `ancient-nerds-map/src/components/lyra/AnswerFeedback.tsx`
- Modify: `ancient-nerds-map/src/components/LyraChatModal.tsx` (assistant message block near line 1227–1240)
- Test: `ancient-nerds-map/src/components/lyra/__tests__/answerFeedback.test.ts`

- [ ] **Step 1: Failing test for the payload helper**

```ts
import { describe, expect, it } from 'vitest'
import { answerFeedbackProps } from '../AnswerFeedback'

describe('answerFeedbackProps', () => {
  it('sends the verdict, the question length and the page — never the question', () => {
    expect(answerFeedbackProps('no', 'where is göbekli tepe', '/lyra.html')).toEqual({
      prompt: 'lyra_answer', answer: 'no', chars: 21, page: 'lyra',
    })
  })
})
```
Run: `npx vitest run src/components/lyra` — Expected: FAIL (module missing).

- [ ] **Step 2: The component**

```tsx
import { useState } from 'react'
import { track, pageType, type EventProps } from '../../analytics'
import type { FeedbackAnswer } from '../../analytics/feedback'

/** Props of the lyra_answer feedback event: verdict + question length only. */
export function answerFeedbackProps(answer: FeedbackAnswer, question: string, pathname: string): EventProps {
  return { prompt: 'lyra_answer', answer, chars: question.trim().length, page: pageType(pathname) }
}

interface Props { question: string }

/** Two small buttons under a finished answer; one tap, then "Thanks". */
export default function AnswerFeedback({ question }: Props) {
  const [done, setDone] = useState<FeedbackAnswer | null>(null)
  if (done) return <span className="lyra-answer-feedback lyra-answer-feedback--done">Thanks</span>
  const vote = (answer: FeedbackAnswer) => {
    track('feedback', answerFeedbackProps(answer, question, window.location.pathname))
    setDone(answer)
  }
  return (
    <span className="lyra-answer-feedback" role="group" aria-label="Was this answer helpful?">
      <button type="button" onClick={() => vote('yes')} aria-label="Helpful">👍</button>
      <button type="button" onClick={() => vote('no')} aria-label="Not helpful">👎</button>
    </span>
  )
}
```
Styles: append to `ancient-nerds-map/src/styles/feedback-prompt.css`:
```css
.lyra-answer-feedback { display: inline-flex; gap: 6px; margin-top: 6px; }
.lyra-answer-feedback button { background: #000; border: 1px solid #bb0a0a; color: #ff2a2a; border-radius: 3px; min-width: 36px; min-height: 32px; cursor: pointer; }
.lyra-answer-feedback button:hover { background: #bb0a0a; color: #000; }
.lyra-answer-feedback--done { font-family: 'JetBrains Mono', monospace; font-size: .7rem; letter-spacing: .08em; text-transform: uppercase; color: #00cc66; }
```
Run the test — Expected: PASS.

- [ ] **Step 3: Mount it under finished assistant messages**

In `LyraChatModal.tsx`, inside the assistant branch of the message list (after the `lyra-chat-msg-content` div closes, ~line 1240): 
```tsx
{msg.role === 'assistant' && !msg.isStreaming && msg.content && (
  <AnswerFeedback question={lastUserMsgRef.current ?? ''} />
)}
```
Import: `import AnswerFeedback from './lyra/AnswerFeedback'`. `lastUserMsgRef` already exists (set in `sendMessage`).

- [ ] **Step 4: Verify and commit**

Run: `npm run -s type-check && npm run -s test` — Expected: green.
```bash
git add ancient-nerds-map/src/components/lyra ancient-nerds-map/src/components/LyraChatModal.tsx ancient-nerds-map/src/styles/feedback-prompt.css
git commit -m "feat(analytics): thumbs under Lyra answers (feedback lyra_answer, no question text)"
```

### Task A3: Globe idle signal

**Files:**
- Modify: `ancient-nerds-map/src/analytics/index.ts` (`EventName`)
- Modify: `ancient-nerds-map/src/App.tsx` (near `setLayersReady(true)` ≈ line 1799 and `openSitePopup` ≈ line 506)

- [ ] **Step 1: Add the event name**

`| 'globe_idle' // globe ready, no site/search/filter within 30 s — ms`

- [ ] **Step 2: The timer**

In `App.tsx`, next to the other refs:
```ts
const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
const markGlobeActivity = useCallback(() => {
  if (idleTimerRef.current) { clearTimeout(idleTimerRef.current); idleTimerRef.current = null }
}, [])
```
In `onLayersReady` after `track('globe_ready', …)`:
```ts
idleTimerRef.current = setTimeout(() => track('globe_idle', { ms: 30000 }), 30000)
```
Call `markGlobeActivity()` at the top of `openSitePopup`, in the search `setSearchQuery` wrapper passed to the filter panel (wrap: `q => { markGlobeActivity(); setSearchQuery(q) }`), and in `FilterPanel`'s `onSourceChange` handler in App.tsx.

- [ ] **Step 3: Verify and commit**

Run: `npm run -s type-check && npm run -s build` — Expected: green. Manual: load `/globe.html` in Playwright with intercepted beacons, wait 35 s → `globe_idle` appears; click a dot → no `globe_idle`.
```bash
git add ancient-nerds-map/src/analytics/index.ts ancient-nerds-map/src/App.tsx
git commit -m "feat(analytics): globe_idle after 30 s without interaction"
```

### Task A4: UTM on the YouTube page links

**Files:**
- Modify: `pipeline/video/shorts_export.py:229` (`"page_path": site_path(...)`)
- Test: `tests/pipeline/video/test_shorts_export_utm.py`

Precondition: `git status --porcelain pipeline/video/shorts_export.py` is empty (the video session owns this area). If not empty, skip the task and note it in the report.

- [ ] **Step 1: Failing test**

```python
from pipeline.video.shorts_export import page_url

def test_page_url_is_canonical_and_tagged_for_youtube():
    assert page_url("Türkiye", "Göbekli Tepe", "9c8b7a65-4321-4cba-8000-111122223333") == (
        "https://ancientnerds.com/sites/t%C3%BCrkiye/g%C3%B6bekli-tepe-9c8b7a65"
        "?utm_source=youtube&utm_medium=short"
    )
```
Run: `python -m pytest tests/pipeline/video/test_shorts_export_utm.py -q` — Expected: FAIL (no `page_url`).

- [ ] **Step 2: Implement**

In `shorts_export.py`, next to the imports (`from pipeline.sites_html_renderer import encode_path, site_path`; `from pipeline.utils.slugs import BASE_URL`):
```python
YOUTUBE_UTM = "utm_source=youtube&utm_medium=short"


def page_url(country: str, name: str, site_id: str) -> str:
    """Absolute site URL for a video description, tagged so Umami's UTM report
    can attribute the visit (YouTube strips the referer on app clicks)."""
    return f"{BASE_URL}{encode_path(site_path(country, name, site_id))}?{YOUTUBE_UTM}"
```
and use `page_url(row["country"] or "", row["name"], row["id"])` wherever the description is assembled (search for `page_path` consumers; keep `page_path` for the file layout if it is used elsewhere).

- [ ] **Step 3: Verify and commit**

Run: `python -m pytest tests/pipeline/video -q && ruff check pipeline/video` — Expected: green.
```bash
git add pipeline/video/shorts_export.py tests/pipeline/video/test_shorts_export_utm.py
git commit -m "feat(video): UTM on the YouTube page links"
```

### Task A5: Privacy text names the feedback texts (correction)

**Files:**
- Modify: `ancient-nerds-map/privacy.html` (§2a list), `PRIVACY.md` (§2)

- [ ] **Step 1: Add the clause**

privacy.html list item (after the feature-usage item):
`<li>Answers you type into the short feedback boxes (empty search, end of a story, site pages, missing pages, Lyra answers); free text is limited to 100 characters</li>`
PRIVACY.md: `- Short feedback answers you choose to type (≤ 100 characters)`

- [ ] **Step 2: Commit**
```bash
git add ancient-nerds-map/privacy.html PRIVACY.md
git commit -m "docs(privacy): feedback texts named in §2a"
```

**Part A deploy:** push once after A1–A5; verify on production with the intercepted-beacon script (`verify_feedback.py` pattern): site page prompt present, Lyra thumbs present after an answer (manual), `globe_idle` after 35 s.

---

## Part B — Dashboard V1 (≈ 8 h)

### Task B1: Umami read layer

**Files:**
- Create: `pipeline/umami_db.py`
- Test: `tests/pipeline/test_umami_db_queries.py`

- [ ] **Step 1: Failing test (SQL shape, no database)**

```python
from pipeline import umami_db as u

def test_queries_are_parameterised_and_scoped_to_the_website():
    for name in ("overview", "map", "hour_buckets", "session_events", "content", "feedback", "sources"):
        sql = getattr(u, f"SQL_{name.upper()}")
        assert ":website_id" in sql and ":since" in sql, name
        assert "'%" not in sql  # no string interpolation anywhere
```
Run: `python -m pytest tests/pipeline/test_umami_db_queries.py -q` — Expected: FAIL (module missing).

- [ ] **Step 2: The module**

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only access to Umami's tables for the founders dashboard and the
alerts. Same Postgres as everything else, its own database `umami`, its own
role (UMAMI_DB_PASSWORD from the VPS .env). Every query is parameterised
and scoped to one website and a time window; nothing here writes."""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

WEBSITE_ID = os.getenv("VITE_UMAMI_WEBSITE_ID", "")


@lru_cache(maxsize=1)
def engine() -> Engine:
    password = os.environ["UMAMI_DB_PASSWORD"]  # missing = misconfigured deploy, fail loudly
    host = os.getenv("POSTGRES_HOST", "db")
    return create_engine(f"postgresql://umami:{password}@{host}:5432/umami", pool_pre_ping=True, pool_size=2)


SQL_OVERVIEW = """
SELECT
  count(*) FILTER (WHERE event_type = 1)                       AS views,
  count(DISTINCT session_id)                                   AS sessions,
  count(DISTINCT session_id) FILTER (WHERE created_at >= :live) AS live_sessions
FROM website_event
WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
"""

SQL_MAP = """
SELECT s.country, s.city, date_part('hour', e.created_at AT TIME ZONE 'UTC')::int AS hour,
       count(DISTINCT e.session_id) AS sessions
FROM website_event e JOIN session s ON s.session_id = e.session_id
WHERE e.website_id = :website_id AND e.event_type = 1 AND e.created_at >= :since AND e.created_at < :until
GROUP BY 1, 2, 3
"""

SQL_HOUR_BUCKETS = """
SELECT date_trunc('hour', created_at) AS hour, count(*) FILTER (WHERE event_type = 1) AS views,
       count(DISTINCT session_id) AS sessions
FROM website_event
WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
GROUP BY 1 ORDER BY 1
"""

SQL_SESSION_EVENTS = """
SELECT e.session_id, e.created_at, e.event_type, e.event_name, e.url_path, e.referrer_domain,
       s.country, s.device,
       (SELECT jsonb_object_agg(d.data_key, coalesce(d.string_value, d.number_value::text))
          FROM event_data d WHERE d.website_event_id = e.event_id) AS data
FROM website_event e JOIN session s ON s.session_id = e.session_id
WHERE e.website_id = :website_id AND e.created_at >= :since AND e.created_at < :until
ORDER BY e.session_id, e.created_at
"""

SQL_CONTENT = """
SELECT e.event_name, d.data_key, d.string_value, count(*) AS n
FROM website_event e JOIN event_data d ON d.website_event_id = e.event_id
WHERE e.website_id = :website_id AND e.event_type = 2 AND e.created_at >= :since AND e.created_at < :until
  AND e.event_name IN ('site_open', 'story_open', 'paper_open', 'search') AND d.data_key IN ('name', 'story', 'paper', 'q')
GROUP BY 1, 2, 3 ORDER BY n DESC LIMIT 200
"""

SQL_FEEDBACK = """
SELECT e.created_at, e.url_path,
       max(d.string_value) FILTER (WHERE d.data_key = 'prompt') AS prompt,
       max(d.string_value) FILTER (WHERE d.data_key = 'answer') AS answer,
       max(d.string_value) FILTER (WHERE d.data_key = 'text')   AS text
FROM website_event e JOIN event_data d ON d.website_event_id = e.event_id
WHERE e.website_id = :website_id AND e.event_name = 'feedback' AND e.created_at >= :since AND e.created_at < :until
GROUP BY e.event_id, e.created_at, e.url_path ORDER BY e.created_at DESC LIMIT 200
"""

SQL_SOURCES = """
SELECT coalesce(nullif(utm_source, ''), nullif(referrer_domain, ''), 'direct') AS source,
       count(DISTINCT session_id) AS sessions
FROM website_event
WHERE website_id = :website_id AND event_type = 1 AND created_at >= :since AND created_at < :until
GROUP BY 1 ORDER BY 2 DESC LIMIT 40
"""


def fetch(sql: str, since: datetime, until: datetime, **params) -> list[dict]:
    with engine().connect() as conn:
        rows = conn.execute(text(sql), {"website_id": WEBSITE_ID, "since": since, "until": until, **params})
        return [dict(r._mapping) for r in rows]
```
Run the test — Expected: PASS. Also `python -c "import pipeline.umami_db"` with `UMAMI_DB_PASSWORD` unset must not fail at import (engine is lazy).

- [ ] **Step 3: Commit**
```bash
git add pipeline/umami_db.py tests/pipeline/test_umami_db_queries.py
git commit -m "feat(stats): read-only query layer on the Umami database"
```

### Task B2: Founder-level answers (pure Python)

**Files:**
- Create: `api/services/founders_stats.py`
- Test: `tests/api/test_founders_stats.py`

- [ ] **Step 1: Failing tests**

```python
from datetime import UTC, datetime
from api.services import founders_stats as fs

T = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)

def ev(session, name=None, path="/", event_type=1, data=None, referrer=None, minute=0):
    return {"session_id": session, "created_at": T.replace(minute=minute), "event_type": event_type,
            "event_name": name, "url_path": path, "referrer_domain": referrer, "country": "DE", "device": "mobile", "data": data or {}}

def test_human_filter_needs_an_interaction_or_a_second_page():
    rows = [ev("a", path="/news-archive/x-1"), ev("b", path="/globe.html"), ev("b", "site_open", event_type=2, data={"site": "1"}), ev("c", path="/"), ev("c", path="/sites/", minute=1)]
    sessions = fs.sessions_from_rows(rows)
    assert {s.id: s.human for s in sessions} == {"a": False, "b": True, "c": True}

def test_session_types():
    rows = [ev("r", path="/news-archive/x-1"), ev("r", "scroll_depth", event_type=2, data={"depth": "100"}),
            ev("e", path="/globe.html"), ev("e", "site_open", event_type=2, data={"site": "1"}),
            ev("f", path="/research/"), ev("f", "paper_open", event_type=2, data={"paper": "/research/p"}),
            ev("s", path="/search.html"), ev("s", "search", event_type=2, data={"q": "giza", "results": "0"})]
    types = {s.id: s.kind for s in fs.sessions_from_rows(rows)}
    assert types == {"r": "leser", "e": "entdecker", "f": "forscher", "s": "sucher"}

def test_top_journeys_are_page_types_and_actions_not_urls():
    rows = [ev("a", path="/news-archive/x-1", referrer="google.com"), ev("a", "site_open", event_type=2, data={"site": "1"}, minute=1), ev("a", path="/sites/peru/x-1", minute=2)]
    assert fs.journeys(fs.sessions_from_rows(rows))[0] == ("google → story → site_open → site", 1)
```
Run: `python -m pytest tests/api/test_founders_stats.py -q` — Expected: FAIL.

- [ ] **Step 2: Implement**

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Founder-level answers computed from Umami rows: sessions, human filter,
session types, journeys. Pure functions — the routes feed them the rows from
pipeline.umami_db; the tests feed them fixtures."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.utils.slugs import story_id_from_slug  # noqa: F401  (journeys use page types only; kept for the content join)

INTERACTIONS = {"site_open", "search", "filter_toggle", "story_open", "paper_open", "media_play", "lyra_chat", "share", "feedback", "scroll_depth"}
SEARCH_HOSTS = ("google.", "bing.com", "duckduckgo.com", "yandex.", "ecosia.org", "qwant.com", "brave.com")
AI_HOSTS = ("chatgpt.com", "openai.com", "perplexity.ai", "copilot.microsoft.com", "gemini.google.com", "claude.ai")


def page_type(path: str) -> str:  # mirrors src/analytics/index.ts pageType
    if path in ("/", "/index.html"):
        return "home"
    if path.endswith(".html"):
        return path.rsplit("/", 1)[-1][:-5]
    if path in ("/sites", "/sites/"):
        return "sites"
    if path.startswith("/sites/"):
        return "site" if len([p for p in path.split("/") if p]) >= 3 else "country"
    for prefix, hub, leaf in (("/news-archive/", "stories", "story"), ("/research/", "papers", "paper"), ("/articles/", "journals", "journal")):
        if path.startswith(prefix):
            return hub if path == prefix else leaf
    return "other"


def source_family(referrer: str | None, utm_source: str | None = None) -> str:
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
    events: Counter = field(default_factory=Counter)
    depth: int = 0

    @property
    def human(self) -> bool:
        return self.pages >= 2 or any(self.events[n] for n in INTERACTIONS)

    @property
    def kind(self) -> str:
        pages = {s for s in self.steps if s in {"story", "paper", "journal", "site", "globe", "search", "papers", "stories"}}
        if self.events["paper_open"] or self.events["lyra_chat"] or "paper" in pages or "papers" in pages:
            return "forscher"
        if self.events["site_open"] or ("globe" in pages and self.events["filter_toggle"]):
            return "entdecker"
        if self.events["search"]:
            return "sucher"
        if pages & {"story", "journal"}:
            return "leser"
        return "sonstige"


def sessions_from_rows(rows: list[dict]) -> list[Session]:
    by_id: dict[str, Session] = {}
    for r in rows:
        s = by_id.get(r["session_id"])
        if s is None:
            s = by_id[r["session_id"]] = Session(r["session_id"], r["created_at"], r.get("country"), r.get("device"))
        if r["event_type"] == 1:
            pt = page_type(r["url_path"] or "/")
            if s.entry is None:
                s.entry = source_family(r.get("referrer_domain"), (r.get("data") or {}).get("utm_source"))
            s.pages += 1
            s.steps.append(pt)
        else:
            name = r["event_name"] or "event"
            s.events[name] += 1
            if name == "scroll_depth":
                s.depth = max(s.depth, int(float((r.get("data") or {}).get("depth", 0) or 0)))
            if name in {"site_open", "search", "paper_open", "story_open", "lyra_chat", "share", "feedback"}:
                s.steps.append(name)
    return sorted(by_id.values(), key=lambda s: s.started)


def journeys(sessions: list[Session], limit: int = 10) -> list[tuple[str, int]]:
    c: Counter = Counter()
    for s in sessions:
        if not s.human:
            continue
        chain = [s.entry or "direct", *s.steps][:6]
        c[" → ".join(chain)] += 1
    return c.most_common(limit)


def session_type_shares(sessions: list[Session]) -> dict[str, int]:
    return dict(Counter(s.kind for s in sessions if s.human))
```
Run the tests — Expected: PASS. (Adjust the test for journeys if the entry family for `google.com` must read "google": `source_family` returns "google" for any google host — the test expects that.)

- [ ] **Step 3: Commit**
```bash
git add api/services/founders_stats.py tests/api/test_founders_stats.py
git commit -m "feat(stats): sessions, human filter, session types and journeys from Umami rows"
```

### Task B3: The `/api/stats/*` routes

**Files:**
- Modify: `api/routes/stats_access.py` — add `require_stats_session`
- Create: `api/routes/founders_stats.py`
- Modify: `api/main.py` (import + `app.include_router(founders_stats.router, prefix="/api/stats", tags=["stats"])`)
- Modify: `pyproject.toml` (`"api.** -> pipeline.umami_db"` in the import-linter ignore list)
- Test: `tests/api/test_founders_stats_routes.py`

- [ ] **Step 1: Failing test**

```python
import asyncio
from datetime import UTC, datetime
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from api.routes import founders_stats as fr
from api.routes import stats_access as sa
from api.services import jwt_auth

def _req(cookie=None):
    headers = [(b"cookie", f"{sa.COOKIE_NAME}={cookie}".encode())] if cookie else []
    return Request({"type": "http", "method": "GET", "path": "/api/stats/overview", "query_string": b"", "headers": headers})

def test_routes_require_the_stats_cookie(monkeypatch):
    monkeypatch.setattr(jwt_auth, "SECRET_KEY", "k" * 40)
    with pytest.raises(HTTPException) as e:
        sa.require_stats_session(_req())
    assert e.value.status_code == 401
    assert sa.require_stats_session(_req(sa.mint_stats_token("1", "m")))["scope"] == "stats"

def test_overview_shapes_the_rows(monkeypatch):
    monkeypatch.setattr(fr, "fetch", lambda sql, since, until, **p: [{"views": 10, "sessions": 4, "live_sessions": 1}] if "live_sessions" in sql else [])
    out = asyncio.run(fr.overview(days=7, session={"scope": "stats"}))
    assert out["today"]["views"] == 10 and out["today"]["live"] == 1
```
Run — Expected: FAIL.

- [ ] **Step 2: The dependency and the routes**

In `stats_access.py`:
```python
from fastapi import Depends, HTTPException

def require_stats_session(request: Request) -> dict:
    """FastAPI dependency for /api/stats/*: the an_stats cookie or 401."""
    payload = stats_session(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Founder session required")
    return payload
```
`founders_stats.py`:
```python
# SPDX-License-Identifier: AGPL-3.0-only
"""The founders dashboard's data: five endpoints, all behind the an_stats cookie."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from api.routes.stats_access import require_stats_session
from api.services import founders_stats as fs
from pipeline.umami_db import SQL_CONTENT, SQL_FEEDBACK, SQL_HOUR_BUCKETS, SQL_MAP, SQL_OVERVIEW, SQL_SESSION_EVENTS, SQL_SOURCES, fetch

router = APIRouter()


def _window(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    return until - timedelta(days=days), until


@router.get("/overview")
async def overview(days: int = Query(7, ge=1, le=90), session: dict = Depends(require_stats_session)):
    now = datetime.now(UTC)
    def block(since, until):
        row = fetch(SQL_OVERVIEW, since, until, live=now - timedelta(minutes=5))[0]
        return {"views": row["views"], "sessions": row["sessions"], "live": row["live_sessions"]}
    today = block(now.replace(hour=0, minute=0, second=0, microsecond=0), now)
    yesterday = block(now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1), now - timedelta(days=1))
    since, until = _window(days)
    sessions = fs.sessions_from_rows(fetch(SQL_SESSION_EVENTS, since, until))
    human = [s for s in sessions if s.human]
    return {
        "today": today, "yesterday": yesterday, "days": days,
        "sessions": {"all": len(sessions), "human": len(human)},
        "types": fs.session_type_shares(sessions),
        "hours": fetch(SQL_HOUR_BUCKETS, since, until),
    }


@router.get("/map")
async def visitor_map(days: int = Query(1, ge=1, le=30), session: dict = Depends(require_stats_session)):
    since, until = _window(days)
    return {"points": fetch(SQL_MAP, since, until)}


@router.get("/content")
async def content(days: int = Query(7, ge=1, le=90), session: dict = Depends(require_stats_session)):
    since, until = _window(days)
    rows = fetch(SQL_CONTENT, since, until)
    return {"sites": [r for r in rows if r["event_name"] == "site_open"][:15],
            "stories": [r for r in rows if r["event_name"] == "story_open"][:15],
            "papers": [r for r in rows if r["event_name"] == "paper_open"][:15],
            "searches": [r for r in rows if r["event_name"] == "search"][:30]}


@router.get("/feedback")
async def feedback(days: int = Query(30, ge=1, le=365), session: dict = Depends(require_stats_session)):
    since, until = _window(days)
    return {"items": fetch(SQL_FEEDBACK, since, until)}


@router.get("/sources")
async def sources(days: int = Query(7, ge=1, le=90), session: dict = Depends(require_stats_session)):
    since, until = _window(days)
    rows = fetch(SQL_SOURCES, since, until)
    return {"sources": [{"source": r["source"], "family": fs.source_family(r["source"]), "sessions": r["sessions"]} for r in rows]}
```
Run the tests — Expected: PASS. `lint-imports` must stay green (add the ignore line).

- [ ] **Step 3: Commit**
```bash
git add api/routes/stats_access.py api/routes/founders_stats.py api/main.py pyproject.toml tests/api/test_founders_stats_routes.py
git commit -m "feat(stats): /api/stats endpoints behind the founder cookie"
```

### Task B4: Map data

**Files:**
- Create: `scripts/build_country_centroids.py`
- Create: `public/data/layers/ne_110m_land.geojson` (download), `ancient-nerds-map/src/data/country_centroids.json` (generated)
- Test: `ancient-nerds-map/src/components/dashboard/__tests__/mapMath.test.ts` (Task B5 uses the file)

- [ ] **Step 1: Script**

```python
"""One-off: Natural Earth 110m (public domain) → land outline for the dashboard
map and ISO-2 country centroids (bbox centre) for the visitor dots."""
import json, httpx
from pathlib import Path
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
land = httpx.get(NE + "ne_110m_land.geojson", timeout=60).json()
Path("public/data/layers/ne_110m_land.geojson").write_text(json.dumps(land, separators=(",", ":")))
countries = httpx.get(NE + "ne_110m_admin_0_countries.geojson", timeout=60).json()
def bbox_center(geom):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)): xs.append(c[0]); ys.append(c[1])
        else: [walk(x) for x in c]
    walk(geom["coordinates"]); return [round((min(xs)+max(xs))/2, 2), round((min(ys)+max(ys))/2, 2)]
out = {f["properties"]["ISO_A2_EH"] or f["properties"]["ISO_A2"]: bbox_center(f["geometry"]) for f in countries["features"]}
out = {k: v for k, v in out.items() if k and k != "-99"}
Path("ancient-nerds-map/src/data/country_centroids.json").write_text(json.dumps(out, sort_keys=True))
print(len(out), "countries")
```
Run: `python scripts/build_country_centroids.py` — Expected: `~175 countries`, land file ≈ 150 KB.

- [ ] **Step 2: Commit the data**
```bash
git add scripts/build_country_centroids.py public/data/layers/ne_110m_land.geojson ancient-nerds-map/src/data/country_centroids.json
git commit -m "feat(stats): map data (Natural Earth 110m land, country centroids)"
```

### Task B5: The page

**Files:**
- Create: `ancient-nerds-map/dashboard.html`, `src/dashboardMain.tsx`, `src/pages/DashboardPage.tsx`, `src/components/dashboard/useStats.ts`, `Pulse.tsx`, `VisitorMap.tsx`, `SessionTypes.tsx`, `TopContent.tsx`, `FeedbackInbox.tsx`, `Sources.tsx`, `mapMath.ts`, `src/styles/dashboard.css`
- Modify: `vite.config.ts` (entry + tracker exclusion)
- Test: `src/components/dashboard/__tests__/mapMath.test.ts`

- [ ] **Step 1: Failing test for the map math**

```ts
import { describe, expect, it } from 'vitest'
import { project, hourWeights } from '../mapMath'

describe('map math', () => {
  it('projects lon/lat onto a 1000×500 equirectangular canvas', () => {
    expect(project([0, 0])).toEqual([500, 250])
    expect(project([-180, 90])).toEqual([0, 0])
    expect(project([180, -90])).toEqual([1000, 500])
  })
  it('sums sessions per country for one hour, or all hours', () => {
    const pts = [{ country: 'DE', city: 'x', hour: 8, sessions: 2 }, { country: 'DE', city: 'y', hour: 9, sessions: 1 }, { country: 'US', city: 'z', hour: 8, sessions: 5 }]
    expect(hourWeights(pts, 8)).toEqual({ DE: 2, US: 5 })
    expect(hourWeights(pts, null)).toEqual({ DE: 3, US: 5 })
  })
})
```
Run: `npx vitest run src/components/dashboard` — Expected: FAIL.

- [ ] **Step 2: mapMath.ts**

```ts
export type MapPoint = { country: string; city: string | null; hour: number; sessions: number }
export const MAP_W = 1000
export const MAP_H = 500
export function project([lon, lat]: [number, number]): [number, number] {
  return [Math.round(((lon + 180) / 360) * MAP_W), Math.round(((90 - lat) / 180) * MAP_H)]
}
export function hourWeights(points: MapPoint[], hour: number | null): Record<string, number> {
  const out: Record<string, number> = {}
  for (const p of points) {
    if (hour !== null && p.hour !== hour) continue
    out[p.country] = (out[p.country] ?? 0) + p.sessions
  }
  return out
}
```
Run — Expected: PASS.

- [ ] **Step 3: Data hook**

`useStats.ts`:
```ts
import { useEffect, useState } from 'react'
export type Loaded<T> = { data: T | null; error: 'unauthorized' | 'failed' | null }
export function useStats<T>(path: string, refreshMs = 60_000): Loaded<T> {
  const [state, set] = useState<Loaded<T>>({ data: null, error: null })
  useEffect(() => {
    let alive = true
    const load = async () => {
      const r = await fetch(`/api/stats/${path}`, { credentials: 'same-origin' })
      if (!alive) return
      if (r.status === 401) return set({ data: null, error: 'unauthorized' })
      if (!r.ok) return set({ data: null, error: 'failed' })
      set({ data: (await r.json()) as T, error: null })
    }
    load()
    const t = setInterval(load, refreshMs)
    return () => { alive = false; clearInterval(t) }
  }, [path, refreshMs])
  return state
}
```

- [ ] **Step 4: Components (one responsibility each, mobile first)**

`Pulse.tsx` — three tiles (Jetzt, Heute vs Gestern, 7 Tage), each a number with a delta arrow; props from `/overview`.
`VisitorMap.tsx` — `<svg viewBox="0 0 1000 500">` with the land outline (fetched once from `/data/layers/ne_110m_land.geojson`, drawn as `<path>` per polygon via `project`), country dots from `hourWeights` with radius `4 + 3·√sessions`, an `<input type="range" min=0 max=23>` plus an "all hours" toggle; the current hour label in JetBrains Mono. Touch-friendly (44 px thumb).
`SessionTypes.tsx` — horizontal bars for leser/entdecker/forscher/sucher/sonstige with counts and share; below, "bestätigt menschlich: n von m".
`TopContent.tsx` — three lists (Sites with country, Stories, Papers) and the search terms with result counts, empty ones marked red.
`FeedbackInbox.tsx` — list: time, prompt label, answer icon, text, page link.
`Sources.tsx` — grouped bars: search / ai / discord / youtube / direct / other.
`DashboardPage.tsx` — header (wordmark, "Open Umami" → `/websites/<id>` on the same host, "Sign out" → `/logout`), the six panels in order, and a `unauthorized` state that renders the same entry markup as the stats login (link to `https://ancientnerds.com/api/auth/discord?return_to=%2Fapi%2Fauth%2Fstats-handoff`).
`dashboard.css` — NERV: black, green labels (#00cc66), red accents (#bb0a0a/#ff2a2a), JetBrains Mono for numbers, Saira Extra Condensed for the big numbers, single column under 720 px, two columns above, panels with the green left border used by the feedback prompt.

- [ ] **Step 5: Entry, Vite, tracker exclusion**

`dashboard.html` (copy the head of `search.html`, title "Founders · Ancient Nerds", `<meta name="robots" content="noindex, nofollow">`, `<script type="module" src="/src/dashboardMain.tsx">`). `dashboardMain.tsx`: `createRoot(...).render(<DashboardPage />)` — no `analytics/boot` import (the founders' own visits stay out of the data). In `vite.config.ts`: add `dashboard: resolve(__dirname, 'dashboard.html')` to `rollupOptions.input`, and in `analyticsTag` return `html` unchanged when `ctx.filename.endsWith('dashboard.html')` (handler signature gains `ctx`).

- [ ] **Step 6: Verify and commit**

Run: `npm run -s type-check && npm run -s test && npx knip --no-progress --include files,dependencies,devDependencies && npm run -s build && npx size-limit` — Expected: green; `dist/dashboard.html` exists and contains no `pulse.js`.
```bash
git add ancient-nerds-map/dashboard.html ancient-nerds-map/src/dashboardMain.tsx ancient-nerds-map/src/pages/DashboardPage.tsx ancient-nerds-map/src/components/dashboard ancient-nerds-map/src/styles/dashboard.css ancient-nerds-map/vite.config.ts
git commit -m "feat(stats): founders dashboard V1 (pulse, map, session types, top content, feedback inbox, sources)"
```

### Task B6: nginx — the dashboard at the root of the stats host

**Files:**
- Modify: `ancientnerds-nginx-config` (stats 443 server)

- [ ] **Step 1: Add, above `location / {` of the stats server**

```nginx
    # The founders dashboard (dashboard.html from the frontend build) is the
    # root; its assets and the map data come from the same build. Umami keeps
    # every other path, including its own /api/. /api/stats/ is ours.
    root /var/www/ancientnerds/ancient-nerds-map/dist;
    location = / {
        auth_request /_gate;
        error_page 401 = @entry;
        add_header Cache-Control "no-cache" always;
        try_files /dashboard.html =404;
    }
    location ^~ /assets/ {
        auth_request /_gate;
        error_page 401 = @entry;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
    location ^~ /fonts/ { auth_request /_gate; error_page 401 = @entry; }
    location = /data/layers/ne_110m_land.geojson {
        auth_request /_gate;
        error_page 401 = @entry;
        root /var/www/ancientnerds/public;
    }
    location ^~ /api/stats/ {
        auth_request /_gate;
        error_page 401 = @entry;
        proxy_pass http://an_api;
        proxy_set_header Host $host;
        proxy_set_header Cookie $http_cookie;
    }
```
And change the SSO page's final `location.replace('/')` — it already lands on `/`, which is now the dashboard.

- [ ] **Step 2: Verify and commit**

Push; the deploy runs `nginx -t`. Then: `curl -sS https://stats.ancientnerds.com/ | grep -c "Continue with Discord"` → 1 without a cookie; with a browser session: the dashboard renders, `/websites/` opens Umami. Screenshots at 390 px and 1280 px go into the report.
```bash
git add ancientnerds-nginx-config
git commit -m "feat(stats): dashboard served at the root of stats.ancientnerds.com"
```

---

## Part C — Dashboard V2: journeys and problems (≈ 4 h)

### Task C1: Journeys and problems endpoints

**Files:**
- Modify: `pipeline/umami_db.py` (`SQL_NOT_FOUND`, `SQL_VITALS`, `SQL_ERRORS`)
- Modify: `api/services/founders_stats.py` (`problems()`)
- Modify: `api/routes/founders_stats.py` (`/journeys`, `/problems`)
- Test: extend `tests/api/test_founders_stats.py`

- [ ] **Step 1: Failing test**

```python
def test_problems_rank_exits_errors_and_empty_searches():
    rows = [ev("a", path="/news-archive/x-1"), ev("b", path="/news-archive/x-1"), ev("c", path="/news-archive/x-1"), ev("c", "scroll_depth", event_type=2, data={"depth": "25"})]
    sessions = fs.sessions_from_rows(rows)
    problems = fs.problems(sessions, not_found=[{"url_path": "/old", "referrer_domain": "example.org", "n": 3}], vitals=[{"page": "story", "name": "LCP", "p75": 4100}], errors=[{"message": "x is not a function", "page": "globe", "n": 12}])
    kinds = [p["kind"] for p in problems]
    assert kinds[0] == "js_error"          # 12 hits outrank everything
    assert {"slow_page", "broken_link", "shallow_exit"} <= set(kinds)
```

- [ ] **Step 2: SQL + ranking**

```python
SQL_NOT_FOUND = """
SELECT e.url_path, e.referrer_domain, count(*) AS n
FROM website_event e
WHERE e.website_id = :website_id AND e.event_type = 1 AND e.created_at >= :since AND e.created_at < :until
  AND EXISTS (SELECT 1 FROM event_data d WHERE d.website_event_id = e.event_id AND d.data_key = 'page' AND d.string_value = 'other')
GROUP BY 1, 2 ORDER BY n DESC LIMIT 50
"""
SQL_VITALS = """
SELECT max(p.string_value) AS page, max(n.string_value) AS name,
       percentile_cont(0.75) WITHIN GROUP (ORDER BY v.number_value) AS p75, count(*) AS samples
FROM website_event e
JOIN event_data p ON p.website_event_id = e.event_id AND p.data_key = 'page'
JOIN event_data n ON n.website_event_id = e.event_id AND n.data_key = 'name'
JOIN event_data v ON v.website_event_id = e.event_id AND v.data_key = 'value'
WHERE e.website_id = :website_id AND e.event_name = 'vital' AND e.created_at >= :since AND e.created_at < :until
GROUP BY e.event_id % 1 = 0, p.string_value, n.string_value
"""
SQL_ERRORS = """
SELECT max(m.string_value) AS message, max(p.string_value) AS page, count(*) AS n
FROM website_event e
JOIN event_data m ON m.website_event_id = e.event_id AND m.data_key = 'message'
JOIN event_data p ON p.website_event_id = e.event_id AND p.data_key = 'page'
WHERE e.website_id = :website_id AND e.event_name = 'js_error' AND e.created_at >= :since AND e.created_at < :until
GROUP BY m.string_value, p.string_value ORDER BY n DESC LIMIT 30
"""
```
(The 404 page carries `page: other` in its feedback only; use `url_path` of pageviews whose status we cannot see — so instead detect not-found pages by the `/api/auth`… **Correction:** the 404 page is a normal pageview with the missing path; mark it server-side by adding `data-umami-event-page="not_found"`? Simpler and exact: in `render_error_html` add `<script>window.umami && umami.track('not_found', {path: location.pathname, referrer: document.referrer})</script>` — one event per 404 view (Task C1 step 2b), then `SQL_NOT_FOUND` groups `not_found` events by path/referrer.)

`problems()` in `founders_stats.py` scores: js_error → `n * 3`; slow_page (LCP p75 > 2500 or INP p75 > 200) → `samples`; broken_link (not_found n ≥ 2) → `n * 2`; shallow_exit (story/site sessions with 1 page and depth < 25) → count per page type; empty_search → count. Returns a list of `{"kind", "label", "score", "detail"}` sorted by score.

- [ ] **Step 3: Routes + components**

`/api/stats/journeys?days=7` → `fs.journeys(...)`; `/api/stats/problems?days=7` → `fs.problems(...)`. Components `Journeys.tsx` (chains as chips: entry → steps, count on the right) and `Problems.tsx` (ranked list with a coloured severity dot). Add both to `DashboardPage` after Sources.

- [ ] **Step 4: Verify and commit** — same gate list as B5/B3.

---

## Part D — Alerts and weekly digest (≈ 3 h, needs `DISCORD_WEBHOOK_URL`)

### Task D1: Orchestrator steps

**Files:**
- Create: `pipeline/lyra/analytics_alerts.py`
- Modify: `pipeline/lyra/orchestrator.py` (STEPS `alerts`, `digest`; STEP_ORDER after `indexnow`)
- Modify: `pyproject.toml` (import-linter exception `pipeline.lyra.analytics_alerts -> api.services.notify`)
- Test: `tests/pipeline/test_analytics_alerts.py`

- [ ] **Step 1: Failing tests**

```python
from datetime import UTC, datetime
from pipeline.lyra import analytics_alerts as aa

def test_error_spike_message_names_page_and_count():
    msg = aa.error_spike_message([{"message": "x is not a function", "page": "globe", "n": 14}], threshold=10)
    assert "14" in msg and "globe" in msg and "x is not a function" in msg

def test_no_message_below_threshold():
    assert aa.error_spike_message([{"message": "m", "page": "p", "n": 3}], threshold=10) is None

def test_digest_is_due_only_once_on_monday_morning():
    monday_6 = datetime(2026, 9, 21, 6, 10, tzinfo=UTC)
    assert aa.digest_due(monday_6, last_sent=None)
    assert not aa.digest_due(monday_6, last_sent=monday_6.replace(hour=6, minute=5))
    assert not aa.digest_due(datetime(2026, 9, 22, 6, 10, tzinfo=UTC), last_sent=None)
```

- [ ] **Step 2: Implement**

`error_spike_message(rows, threshold)` → string or None; `check_hourly()` → fetches `SQL_ERRORS` for the last hour, posts via `send_discord_webhook({"content": msg})`, returns 1 if posted else 0. `digest_due(now, last_sent)` → Monday and 06:00–06:59 UTC and (last_sent is None or last_sent.date() < now.date()). `weekly_digest()` → builds: pulse (7 d vs previous 7 d), top 3 sites/stories, top 3 problems, all feedback texts of the week, posts as one message (≤ 1,900 chars, split like `discord_bot._split_response`), persists `last_sent` in `/app/logs/lyra_step_state.json` under key `digest_sent`. Both return 0 without `DISCORD_WEBHOOK_URL` and log once.

- [ ] **Step 3: Register the steps**

```python
    "alerts": ("pipeline.lyra.analytics_alerts", "check_hourly", False, "Alerts: {n} posted"),
    "digest": ("pipeline.lyra.analytics_alerts", "weekly_digest", False, "Digest: {n} posted"),
```
Append `"alerts", "digest"` to `STEP_ORDER` (after `indexnow`). No STEP_INTERVALS entry: every cycle, cheap.

- [ ] **Step 4: Verify and commit** — `python -m pytest tests/pipeline/test_analytics_alerts.py tests/pipeline/test_orchestrator_intervals.py -q`, the markdown-free import simulation (`sys.modules['markdown']=None; import pipeline.lyra.orchestrator`), `lint-imports`, then commit.

---

## Verification after each deploy

- Backend gates: `ruff check api/ pipeline/`, `ruff format --check api/ pipeline/`, `lint-imports`, `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80`, `semgrep scan --config .semgrep`, `python -m pytest -q -m "not integration and not live_llm and not slow" --timeout 90`.
- Frontend gates: `npm run -s type-check`, `npm run -s test`, `npx knip …`, `npm run -s build`, `npx size-limit`, `npm run -s build:ssr`.
- Production: Playwright with intercepted `/api/pulse` for the new events; screenshots of the dashboard at 390 px and 1280 px; `curl` of `/api/stats/overview` with and without the cookie (401 / 200).

## Self-review notes

- Spec coverage: three founder questions → B (what, where from), C (how they navigate, where it fails), A (feedback hooks), D (reaching the founders). Map with hours → B4/B5. Human filter → B2. UTM YouTube → A4. Search terms → already live (8ef236f).
- Types: `Session.kind` values (`leser|entdecker|forscher|sucher|sonstige`) are the same strings the `SessionTypes` component labels; `MapPoint` matches `SQL_MAP` columns (`country, city, hour, sessions`).
- Known limits, stated on the page: cookieless visitors are recognised within a calendar month only; "unconfirmed" sessions may be bots or bouncing humans.
