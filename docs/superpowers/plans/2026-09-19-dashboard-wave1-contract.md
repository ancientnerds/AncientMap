# Founders Dashboard — Merged Implementation Contract
**Date:** 2026-09-19 · **Scope:** six parallel panel specs merged into one authoritative plan · **All live numbers re-verified against production Umami this session** (`ssh ancientnerds` → `ancient_nerds_db`, db `umami`, 761 events, 2026-09-17 10:03:33 → 2026-09-19 09:03:36 UTC).

---

## 0. What the six features become

| Spec | Verdict | Where it lands |
|---|---|---|
| `device-language` | Panel **Devices** — **narrow**, rides `/overview` | no new query |
| `globe-time-to-interactive` | **No panel.** New `problems[].kind = "slow_start"` | +1 query on `/problems` |
| `scroll-depth` | Panel **Reading** — wide, **rides `/overview`** | **no new query, no new SQL constant** (ruling §9.2) |
| `live-now` | Panel **LiveNow** — wide, new `/live` | +1 query, 30 s poll |
| `exits` | Panel **Exits** — **narrow**, new `/exits` | +1 query |
| `pulse-period-delta` | **No panel.** `CountryWindow.change`; `/overview` loses `today`/`yesterday` | **−2 queries** |

Net: 4 new panels (12 total), 3 new SQL constants, +1 endpoint pair (`/live`, `/exits`), **net query delta per 60 s refresh: +1** (16 vs 15), plus `/live` polling twice a minute.

---

## 1. ENDPOINTS — final list of `/api/stats/*`

All eleven behind `Depends(require_stats_session)`. Route function names are binding.

### 1.1 `GET /api/stats/overview?days=N` → `async def overview(days=Query(7, ge=1, le=90))`
**The session-fold endpoint.** One `SQL_SESSION_EVENTS` fetch feeds four panels (Pulse spark, SessionTypes, Devices, Reading).

```python
{
  "days": int,
  "sessions": {"all": int, "human": int},
  "types": {"<SessionKind>": int},                       # existing
  "devices": {"<umami device word>": int},               # NEW, human only
  "languages": [{"language": str|None, "sessions": int}],# NEW, human only, biggest first, ties alphabetical, null last
  "reading": {                                           # NEW, folded from the same rows
     "funnels": [{"page": str, "opened": int, "scrolled": int,
                  "steps": [{"depth": 25|50|75|100, "reads": int}], "rated": bool}],
     "ignored": int,
     "min_reads": int
  },
  "hours": [{"hour": ISO, "views": int, "sessions": int}]
}
```
**REMOVED:** `today`, `yesterday` (both `DayBlock`). Both `fetch(SQL_OVERVIEW, …)` calls go. `SQL_OVERVIEW` itself stays in `umami_db.py` — `pipeline/lyra/analytics_alerts.weekly_digest()` still uses it (verified: lines with `fetch(SQL_OVERVIEW, week_start, now, live=now)`).

### 1.2 `GET /api/stats/countries` → `async def visitor_countries()`
No query params. Fixed windows; the page's 7/30 switch does not touch it.
```python
{"now"|"today"|"d7"|"d30": {
   "sessions": int, "all": int,
   "countries": [{"country": str, "sessions": int}],
   "change": {"previous": int, "pct": int|None} | None }}
```
`change` is **non-null only on `today`** (vs yesterday to the same time of day) **and `d7`** (vs the seven days before). `now` and `d30` are `null` — there is no previous five minutes, and a previous 30 days means a 60-day `SQL_SESSION_EVENTS` (measured: linear, per-row `event_data` probe, `loops=757`). **Declined.** Still **one** query.

### 1.3 `GET /api/stats/live` → `async def live()` — **NEW**
No query params (fixed 30 min window / 5 min quiet / 24 h lookback), like `/countries`.
```python
{"window_minutes": 30, "quiet_after_minutes": 5, "lookback_hours": 24,
 "total": int, "summary": str,
 "visitors": [{"session","country","device","browser","page","path","title","here","last_seen","quiet"}],
 "last": <same shape> | None}
```
Polled at **30 s** (`useStats(path, 30_000)` — the hook already takes `refreshMs`), because the rows print whole minutes.

### 1.4 `GET /api/stats/exits?days=N` → `async def exits(days=Query(7, ge=1, le=90))` — **NEW**
```python
{"outbound": ExitRow[], "discord": ExitRow[], "clicks": int, "at": ISO|None}
# ExitRow = {"target","clicks","visitors","pages":[{"page","clicks"}],"at"}
```

### 1.5 `GET /api/stats/problems?days=N` → `async def problems(...)`
Response key set unchanged. `problems[].kind` gains **`"slow_start"`**. Handler runs **six** fetches (adds `SQL_GLOBE_READY`).

### 1.6 Unchanged
`GET /map?days=N` → `visitor_map()` · `GET /content?days=N` → `content()` · `GET /journeys?days=N` → `journeys()` · `GET /feedback?days=N` → `feedback()` · `GET /sources?days=N` → `sources()`.

> **Explicit non-merge:** `/journeys` also fetches `SQL_SESSION_EVENTS` over the same `days` window as `/overview` and could be folded in. **Not done** — no feature in this batch touches it, and refactoring it would churn `Journeys.tsx`, `DashboardPage.tsx` and two test files for zero feature gain. Logged as a follow-up ticket: *"fold /journeys into /overview, third SESSION_EVENTS fetch per refresh"*.

---

## 2. SQL — final `SQL_*` constants in `pipeline/umami_db.py`

Final set: `SQL_OVERVIEW`, `SQL_MAP`, `SQL_HOUR_BUCKETS`, `SQL_SESSION_EVENTS`, `SQL_CONTENT`, `SQL_FEEDBACK`, `SQL_SOURCES`, `_LAST_VISITOR`, `SQL_NOT_FOUND`, `SQL_VITALS`, `SQL_ERRORS`, **`SQL_GLOBE_READY`**, **`SQL_LIVE`**, **`SQL_EXITS`**.
**`SQL_SCROLL_DEPTH` is not created** (§9.2).

### 2.1 `SQL_SESSION_EVENTS` — one column added
Only the `s.browser,` line changes:
```sql
SELECT e.session_id, e.created_at, e.event_type, e.event_name, e.url_path, e.referrer_domain,
       e.utm_source, s.country, s.device, s.browser, s.language,
       (SELECT jsonb_object_agg(d.data_key, coalesce(d.string_value, d.number_value::text))
          FROM event_data d WHERE d.website_event_id = e.event_id) AS data
FROM website_event e JOIN session s ON s.session_id = e.session_id
WHERE e.website_id = :website_id AND e.created_at >= :since AND e.created_at < :until
ORDER BY e.session_id, e.created_at
```
Module docstring column list extended:
> ``session`` (session_id, country, city, device, browser, language). … ``device`` is ua-parser's device type with a screen of 1920 px or less relabelled "laptop" (umami 3.4.0 bundle, read 2026-09-19); ``language`` is the raw browser tag, including locales Intl rejects ("en-US@posix" — one live session carries it). **Custom events carry `url_path` too** (verified: 55/55 `scroll_depth` events), which is why the reading funnel needs no query of its own.

### 2.2 `SQL_GLOBE_READY` — new, after `SQL_VITALS`
```python
#: The globe's time to interactive. src/App.tsx:1822 sends `globe_ready` from
#: onLayersReady with `ms` = performance.now() when the layers are usable;
#: useLayersReady's `layersReadyCalled` ref makes that once per page load, so a
#: sample is a load. Same percentile as the vitals plus two numbers they do not
#: need: `fastest`, because the best case is the honest headline (9 450 ms live
#: on 2026-09-19), and `sessions`, because one visitor reloading is one visitor.
#: Grouped by url_path: only /globe.html mounts App.tsx today (vite.config.ts has
#: one input), and a second mount point must show as its own row, not be averaged in.
SQL_GLOBE_READY = (
    """
WITH ev AS (
    SELECT
        e.event_id,
        e.session_id, e.created_at, s.country, s.device, s.browser,
        e.url_path,
        max(d.number_value) FILTER (WHERE d.data_key = 'ms') AS ms
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    JOIN session s ON s.session_id = e.session_id
    WHERE e.website_id = :website_id AND e.event_name = 'globe_ready'
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, s.country, s.device, s.browser, e.url_path
)
SELECT
    url_path,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY ms::float8) AS p75,
    min(ms)::float8 AS fastest,
    count(*) AS samples,
    count(DISTINCT session_id) AS sessions,
"""
    + _LAST_VISITOR
    + """
FROM ev
WHERE ms IS NOT NULL
GROUP BY url_path
ORDER BY samples DESC
LIMIT 10
"""
)
```
Re-verified live: one row, `/globe.html | 24758.25 | 9450 | 8 | 6`.

### 2.3 `SQL_LIVE` — new, after `SQL_SESSION_EVENTS`
```python
#: What each visitor who is still here has open. One row per session: last sign
#: of life, the last page view of that session, and that page's <title>.
#: `page_title` is a plain column on website_event, filled on 209 of 209 page
#: views (2026-09-19) — a headline beats a 139-character slug and costs no
#: event_data join. The LATERAL is INNER on purpose: 10 of 68 sessions in a day
#: fire only `vital`/`js_error` and never a page view. They have no page to name,
#: so they have no row — the panel says so rather than inventing one.
#: LIMIT 60 clips the oldest sessions of the lookback only; rows are ordered by
#: last sign of life, so neither the live window nor the most recent visitor is cut.
SQL_LIVE = """
WITH seen AS (
    SELECT session_id, max(created_at) AS last_seen
    FROM website_event
    WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
    GROUP BY session_id
)
SELECT seen.session_id::text AS session,
       seen.last_seen,
       page.created_at AS page_since,
       page.url_path,
       coalesce(nullif(page.page_title, ''), page.url_path) AS title,
       s.country, s.device, s.browser
FROM seen
JOIN session s ON s.session_id = seen.session_id
JOIN LATERAL (
    SELECT e.created_at, e.url_path, e.page_title
    FROM website_event e
    WHERE e.website_id = :website_id AND e.session_id = seen.session_id
      AND e.event_type = 1
      AND e.created_at >= :since AND e.created_at < :until
    ORDER BY e.created_at DESC
    LIMIT 1
) page ON true
ORDER BY seen.last_seen DESC
LIMIT 60
"""
```
Guard check: `"LATERAL"` does **not** contain the substring `"ALTER"` (needs A-L-T-E-R consecutively). Passes `test_queries_only_read`.

### 2.4 `SQL_EXITS` — new, after `SQL_SOURCES`
```python
#: Where a visitor goes on purpose. src/analytics/boot.ts installs one click
#: delegation per page: a link to another host sends `outbound_click` with host
#: and page, the Discord CTA sends `discord_click` with the surface (`src`).
#: One query for both — they differ only in that key name.
#: Two levels, like SQL_CONTENT: `ev` makes one row per event, `per_page` counts
#: the page types. The visitor count must come off `ev`: summing the per-page
#: rows would count one session twice when it clicked the same host from two
#: kinds of page.
SQL_EXITS = """
WITH ev AS (
    SELECT
        e.event_id,
        e.event_name,
        e.session_id,
        e.created_at,
        coalesce(
            nullif(max(d.string_value) FILTER (WHERE d.data_key = 'host'), ''),
            nullif(max(d.string_value) FILTER (WHERE d.data_key = 'src'), ''),
            'unknown'
        ) AS target,
        coalesce(nullif(max(d.string_value) FILTER (WHERE d.data_key = 'page'), ''), 'other') AS page
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    WHERE e.website_id = :website_id
      AND e.event_name IN ('outbound_click', 'discord_click')
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.event_name, e.session_id, e.created_at
),
per_page AS (
    SELECT event_name, target, page, count(*) AS n FROM ev GROUP BY 1, 2, 3
)
SELECT
    ev.event_name,
    ev.target,
    count(*) AS n,
    count(DISTINCT ev.session_id) AS sessions,
    max(ev.created_at) AS last_at,
    (SELECT jsonb_object_agg(p.page, p.n) FROM per_page p
      WHERE p.event_name = ev.event_name AND p.target = ev.target) AS pages
FROM ev
GROUP BY ev.event_name, ev.target
ORDER BY sessions DESC, n DESC, ev.target
LIMIT 40
"""
```
Re-verified live: 6 outbound clicks, **all six on `/news-archive/…` story pages**, hosts youtube.com ×5 / getty.edu ×1, 6 distinct sessions. `discord_click` = 0 rows.

### 2.5 `QUERIES` tuple in `tests/pipeline/test_umami_db_queries.py`
Final: `("overview","map","hour_buckets","session_events","content","feedback","sources","not_found","vitals","errors","globe_ready","live","exits")` — **no `"scroll_depth"`**.

### 2.6 `Fetch` markers (canonical, one per query — binding for all route tests)
| query | marker |
|---|---|
| `SQL_SESSION_EVENTS` | `"ORDER BY e.session_id"` |
| `SQL_HOUR_BUCKETS` | `"date_trunc('hour'"` |
| `SQL_GLOBE_READY` | `"'globe_ready'"` |
| `SQL_LIVE` | `"AS last_seen"` |
| `SQL_EXITS` | `"'outbound_click', 'discord_click'"` |
| `SQL_NOT_FOUND` / `SQL_VITALS` / `SQL_ERRORS` / `SQL_CONTENT` | `"'not_found'"` / `"'vital'"` / `"'js_error'"` / `"'site_open'"` |

Do **not** use `"referrer_domain"` (device-language's proposal) or `"live_sessions"` (gone with the `/overview` day blocks).

---

## 3. PYTHON — final additions to `pipeline/stats_analysis.py`

Placement is binding, so the six diffs do not fight over the same hunks.

### 3.1 Dataclass
```python
@dataclass
class Session:
    ...
    browser: str | None = None
    #: Browser language tag exactly as Umami stored it ("en-GB", "en-US@posix").
    #: Reduced to its primary subtag before anything displays it.
    language: str | None = None
    entry: str | None = None
    ...
```
`sessions_from_rows` constructor gains one positional arg `r.get("language")` after `r.get("browser")`. **Nothing else in that function changes** — its depth parse `int(float(data.get("depth", 0) or 0))` is reused verbatim by the reading fold (§3.5), not copied.

### 3.2 Comparison arithmetic — **kills three would-be implementations**
```python
def pct_change(current: int, previous: int) -> int | None:
```
Placed above `countries()`, under `UNKNOWN_COUNTRY`. **The only place this arithmetic lives.** `pipeline/lyra/analytics_alerts._delta()` loses its `round((c-p)/p*100)` and becomes pure Discord wording over `pct_change()`; `Pulse.tsx` loses `delta()` entirely and does no arithmetic. `None` when `previous == 0` — *not* "+400 %", because the tracker started 2026-09-17.

### 3.3 `countries()` gains an upper bound — **signature change**
```python
def countries(sessions, since: datetime|None = None, until: datetime|None = None,
              human_only: bool = True) -> list[dict[str, Any]]
```
Half-open `[since, until)` on `last_seen`. Every existing call site passes by keyword → no breakage. This is what makes the previous period free.

### 3.4 Device & language (rides `/overview`)
```python
UNKNOWN_DEVICE = "unknown"                      # Umami writes no device when no screen arrived
_PRIMARY_SUBTAG = re.compile(r"[a-z]{2,3}")
def primary_language(tag: str | None) -> str | None
def device_shares(sessions: list[Session]) -> dict[str, int]          # human only
def languages(sessions: list[Session]) -> list[dict[str, Any]]        # human only, countries()-shaped
```
Placed after `countries()`. `re`, `Counter`, `Any` already imported. **Both filter `s.human` internally**, mirroring `session_type_shares` — do *not* also hand them the pre-filtered list from the route.
Live justification (re-verified today): device all-sessions is laptop 110 / mobile 43 / desktop 6, but 34 of those laptops share one square `1366x1366` screen; human-only is laptop 31 / mobile 18 / desktop 4. `zh` drops 12 → 1.

### 3.5 Reading funnel (rides `/overview`, **no SQL**)
```python
SCROLL_PAGES = ("story", "site", "paper", "journal", "country")   # = CONTENT_PAGES in boot.ts
SCROLL_STEPS = (25, 50, 75, 100)                                  # = SCROLL_STEPS in boot.ts
SCROLL_MIN_READS = 10
def reading_funnels(rows: list[dict[str, Any]]) -> dict[str, Any]
```
`rows` are **`SQL_SESSION_EVENTS` rows**, not a dedicated query. Add `defaultdict` to the `from collections import` line. Body:
```python
    views: Counter[tuple[str, str]] = Counter()
    deepest: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r["session_id"], r["url_path"] or "/")
        if r["event_type"] == 1:
            views[key] += 1
        elif r["event_name"] == "scroll_depth":
            # Umami fills string_value for a number too ("25.0000") — the same
            # parse sessions_from_rows uses, not a second rule.
            depth = int(float((r.get("data") or {}).get("depth", 0) or 0))
            deepest[key] = max(deepest.get(key, 0), depth)
    opened, scrolled = Counter(), Counter()
    reached: dict[str, Counter[int]] = defaultdict(Counter)
    ignored = 0
    for key in views.keys() | deepest.keys():
        page = page_type(key[1])
        if page not in SCROLL_PAGES:
            continue
        depth = deepest.get(key)
        if not views.get(key):
            if depth is not None:
                ignored += 1       # scrolled without a page view: a scraper, or a page opened before the window
            continue
        opened[page] += 1
        if depth is None:
            continue
        scrolled[page] += 1
        for step in SCROLL_STEPS:
            if depth >= step:
                reached[page][step] += 1
    # …funnels sorted by (-scrolled, -opened, page); rated = scrolled >= SCROLL_MIN_READS
    return {"funnels": funnels, "ignored": ignored, "min_reads": SCROLL_MIN_READS}
```
**Do not merge `SCROLL_PAGES` with `SHALLOW_PAGES`** (bounce rule) or `deepest[key]` with `Session.depth` (per session, feeds `shallow_exit`). A session that read two stories has one `Session.depth` and two reads here. The comments must say so.

### 3.6 Globe time to interactive (rides `/problems`)
```python
GLOBE_READY_LIMIT = 3800          # Lighthouse's good/needs-improvement TTI line; MIN_SPLASH_DURATION in App.tsx is 3000, so a budget under it would flag an imperceptible globe
def _seconds(ms: float) -> str    # "24.8 s" — next to _visitors()
```
`VITAL_MIN_SAMPLES = 10` is **reused, not duplicated**; its comment gains "The globe's time to interactive is gated by the same number for the same reason."
`problems()` gains `globe_ready: list[dict]|None = None` **after `searches`, before `limit`**. The block goes **after the `vitals` loop, before `not_found`** (stable sort → on a tie the finer-grained slow page sorts above a slow start). Score `row["sessions"] * 2` (the dead-link weight: the visit is gone, not merely degraded; ×3 stays reserved for "broken for everyone who touches it"). Label `page_type(row["url_path"])` → `"globe"`.
**`globe_idle` gets no kind.** `track('globe_idle', { ms: 30000 })` is a literal constant — a flag, not a metric; both live `globe_idle` events belong to the one session whose two globe loads took 38.7 s and 19.9 s, so it would double-count the same root cause. Revisit only once `slow_start` clears.

### 3.7 Exits
```python
EXIT_LISTS = {"outbound_click": "outbound", "discord_click": "discord"}   # next to INTERACTIONS/JOURNEY_EVENTS
def exits(rows: list[dict[str, Any]]) -> dict[str, Any]
```
`row["pages"]` indexed directly and `EXIT_LISTS[...]` a direct lookup — the correlated `jsonb_object_agg` always matches its own group, and an unknown event name means the SQL drifted and must fail loudly (CLAUDE.md: no defensive wrapping).

### 3.8 Live panel
```python
TITLE_BRAND = " | "                                    # after page_type()
def without_brand(title: str) -> str                   # rpartition; keeps inner pipes and "Database - Ancient Nerds"
def _live_row(row, now, quiet_after) -> dict           # end of file
def live_now(rows, *, now, window, quiet_after, lookback, limit) -> dict
```
`_live_row`'s first four keys are exactly `_last_visitor`'s shape and it reuses `SESSION_ID_CHARS` — **do not add a second id-shortening rule**.

### 3.9 Duplication audit against existing logic
| New | Overlaps | Ruling |
|---|---|---|
| `reading_funnels` depth parse | `sessions_from_rows` | same expression, different granularity — documented, not extracted (extracting a 1-line parse would be worse) |
| `_live_row` visitor keys | `_last_visitor`, `_session_visitor` | third shape-builder over a third row type; **shares `SESSION_ID_CHARS`**. Acceptable; a generic builder would take 3 key-name maps |
| `_seconds` | nothing in Python | new |
| `device_shares`/`languages` human filter | `session_type_shares` | same pattern, deliberately mirrored |
| `pct_change` | `analytics_alerts._delta` | **`_delta` loses the maths** — the duplicate is removed, not added |
| `countries(until=…)` | — | extension, not a copy |
| `exits()` "1 visitor" plural | `_visitors()` | Python does **not** format it; the count travels and `fmtVisitors()` in `format.ts` is the single TS mirror (§4/§6) |

---

## 4. TYPESCRIPT — final `components/dashboard/types.ts`

**Delete:** `DayBlock` (nothing reads `today`/`yesterday`/`live` after §1.1 — grep: only `Pulse.tsx:95`).

```ts
/** A window measured against the one of the same length before it. `pct` is
 *  already rounded by pct_change() in pipeline/stats_analysis.py — the panel
 *  never does this arithmetic, so dashboard and Monday digest cannot disagree. */
export interface PeriodChange { previous: number; pct: number | null }

export interface CountryWindow {
  sessions: number      // human — every session on the live tile, where nobody has acted yet
  all: number
  countries: CountryCount[]
  /** null where there is nothing to compare: `now` and `d30`. */
  change: PeriodChange | null
}

/** Primary subtag of the browser language — "en" for both en-GB and en-US. */
export interface LanguageCount { language: string | null; sessions: number }

export interface FunnelStep { depth: number; reads: number }
export interface ReadingFunnel {
  page: string; opened: number
  /** The funnel's denominator, not `opened`: nothing is sent at load. */
  scrolled: number
  steps: FunnelStep[]   // shallowest first, cumulative
  rated: boolean        // scrolled >= min_reads
}
export interface ReadingReport { funnels: ReadingFunnel[]; ignored: number; min_reads: number }

/** GET /api/stats/overview?days=N */
export interface Overview {
  days: number
  sessions: { all: number; human: number }
  types: Partial<Record<SessionKind, number>>
  /** Confirmed-human sessions per Umami device word. NOT a closed set: Umami
   *  writes ua-parser's device type and calls a computer of <=1920 px a
   *  "laptop" (3.4.0 bundle, 2026-09-19), so the panel prints an unknown word
   *  verbatim rather than dropping its rows. Never Partial<Record<union,…>>. */
  devices: Record<string, number>
  languages: LanguageCount[]
  reading: ReadingReport
  hours: HourBucket[]
}

/** The six failures pipeline/stats_analysis.py problems() knows. */
export type ProblemKind =
  | 'js_error' | 'slow_page' | 'broken_link' | 'shallow_exit' | 'empty_search'
  /** The globe's own time to interactive — no Core Web Vital sees it: on
   *  2026-09-19 /globe.html reached LCP in 2.0 s and became usable at 24.8 s. */
  | 'slow_start'

/** A visitor who is here now, and what they have open. Extends Visitor. */
export interface LiveVisitor extends Visitor {
  page: string; path: string; title: string
  /** Seconds since this page view started. On `last` that is "opened N ago",
   *  not a dwell — which is why only live rows print it. */
  here: number
  last_seen: string
  quiet: boolean
}
/** GET /api/stats/live — fixed windows, not the page's range switch. */
export interface LiveData {
  window_minutes: number; quiet_after_minutes: number; lookback_hours: number
  total: number; summary: string
  visitors: LiveVisitor[]
  last: LiveVisitor | null
}

export interface ExitPage { page: string; clicks: number }
export interface ExitRow {
  /** Outbound: the link's host. Discord: the CTA surface ("seo", "app"). */
  target: string; clicks: number; visitors: number; pages: ExitPage[]; at: string
}
/** GET /api/stats/exits?days=N */
export interface ExitsData { outbound: ExitRow[]; discord: ExitRow[]; clicks: number; at: string | null }
```
`LiveVisitor` extends `Visitor` → it must be declared **after** the `Visitor` block. No `ReadingData` interface: reading rides `Overview`. The stray non-code line `url_path of the page they are on: see \`path\` below` in the live-now spec is a note, **not code** — it is dropped.

---

## 5. COMPONENTS & GRID

### 5.1 New files
| File | Panel question | Width | Grid slot | Data source |
|---|---|---|---|---|
| `LiveNow.tsx` | *What are they looking at right now?* | **wide** | 2 | `useStats<LiveData>('live', 30_000)` |
| `Exits.tsx` | *Where do they go next?* | **narrow** | 5 | `useStats<ExitsData>(\`exits?days=${days}\`)` |
| `Devices.tsx` | *What are they reading on?* | **narrow** | 7 | existing `overview` state |
| `Reading.tsx` | *Do they read to the end?* | **wide** | 11 | existing `overview` state |

Exports (claimed names, nothing in the repo uses them today): `LiveNow`+`rowDetail`; `Exits`+`exitItem`; `Devices`+`deviceRows`+`languageRows`; `Reading`+`steps`+`pageLabel`+`FINISH_WARN`.

### 5.2 Modified components
- **`Pulse.tsx`** — `delta()` **deleted**, replaced by exported `changeSub(change: PeriodChange|null, against: string): ChangeSub|null` (arrow/text/colour, **no arithmetic**) and a private `compare(w, against)` that falls back to `humanSub(w)` when `change` or `pct` is null. Tiles: `Now` (unchanged sub), `Today` vs `'yesterday'`, `7 days` vs `'previous 7 days'`, `30 days` keeps `humanSub`.
- **`Problems.tsx`** — `SEVERITY.slow_start = 'high'` (the page paints in 2.0 s and the product is not there — broken, not slow); `KIND_LABELS.slow_start = 'Slow start'`; closing note becomes "…a dead link **and a globe that never starts in time** double…". Both maps stay `Record<ProblemKind, …>` so widening the union is a compile error until they carry the key.

### 5.3 Devices is **narrow and stacked** (overrides the device-language spec)
Two `<h3>`+`<BarList>` sections stacked (the `Exits` pattern), **not** `.dash-lists` side by side. `DEVICE_ORDER = ['mobile','tablet','laptop','desktop']` with fixed order and real zeros, unknown Umami words appended biggest-first under their own word; `DEVICE_LABELS` = Phone/Tablet/Laptop/Desktop/Unknown; `LANGUAGE_ROWS = 6` then a tail line. Reason in §9.1.

### 5.4 Final panel order (source order = phone order)
```
 1  Pulse          wide   Who is here right now?
 2  LiveNow        wide   What are they looking at right now?
 3  VisitorMap     wide   Where are the visitors?
 4  Sources        narrow Where do they come from?
 5  Exits          narrow Where do they go next?
 6  SessionTypes   narrow What do visitors do?
 7  Devices        narrow What are they reading on?
 8  Journeys       wide   How do they move through the site?
 9  Problems       wide   Where does the platform fail them?
10  TopContent     wide   What gets opened, what gets searched?
11  Reading        wide   Do they read to the end?
12  FeedbackInbox  wide   What do visitors say?
```
**Desktop (≥720 px):** 8 wide panels each own a row; the 4 narrow ones form **exactly two complete pairs** (4+5, 6+7). **No half-empty cell anywhere** — which is why Devices had to become narrow and Exits could not be promoted to wide.
**Phone (<720 px):** one column, so the order is a reading order: *who is here now* (1-3) → *where from / where to* (4-5) → *who they are / on what* (6-7) → *how they move* (8) → *what fails* (9) → *what they open* (10) → *how far they read* (11) → *what they say* (12). LiveNow sits directly under Pulse because its note says "the same window as the Now tile above" — that must be literally true. Sources↔Exits and SessionTypes↔Devices are the two semantic pairs, so the desktop pairing and the phone narrative agree.

### 5.5 `DashboardPage.tsx`
```tsx
const overview = useStats<Overview>(`overview?days=${days}`)
const map = useStats<MapData>('map?days=1')
// Fixed windows (now / today / 7 / 30) — the range switch does not touch them.
const countries = useStats<CountriesData>('countries')
// Half an hour, refreshed twice a minute: the rows print whole minutes.
const live = useStats<LiveData>('live', 30_000)
const content = useStats<ContentData>(`content?days=${days}`)
const feedback = useStats<FeedbackData>('feedback?days=30')
const sources = useStats<SourcesData>(`sources?days=${days}`)
const exits = useStats<ExitsData>(`exits?days=${days}`)
const journeys = useStats<JourneysData>(`journeys?days=${days}`)
const problems = useStats<ProblemsData>(`problems?days=${days}`)
const panels = [overview, countries, live, map, content, feedback, sources, exits, journeys, problems]
```
Ten `useStats` calls for twelve panels — Devices and Reading ride `overview`. Docstring line 2: **"eight panels" → "twelve panels"** (one writer owns this line; four specs each tried to bump it).

---

## 6. CSS — final new class list

Checked against all 68 selectors currently in `dashboard.css`. **Nothing collides; nothing re-invents `.dash-bar*`, `.dash-lists`, `.dash-flag*`, `.dash-tile*`, `.dash-chip*`, `.dash-note`, `.dash-empty`, `.dash-dot`.**

| Class | Owner | Purpose |
|---|---|---|
| `.dash-live` | LiveNow | `list-style: none` |
| `.dash-live-row` | LiveNow | `grid-template-columns: 10px 18px auto minmax(0,1fr) auto`, top border (mirrors `.dash-problem`, which already passes 390 px) |
| `.dash-live-page` | LiveNow | 2-line clamp, `min-width:0`, `overflow-wrap:anywhere` |
| `.dash-live-here` | LiveNow | mono, right-aligned, nowrap, muted |
| `.dash-dot--live` | LiveNow | `background: var(--dash-green)` — sits with the existing `--high`/`--mid` modifiers |
| `.dash-empty b` | LiveNow | intentionally global: the noun in *any* panel's empty sentence gets `--dash-paper` + weight 500. Inert until now |
| `.dash-funnel-base` | Reading | the "N of M opens scrolled at all" line under each funnel heading |
| `.dash-exits` | Exits | scoping wrapper for the one override below |
| `.dash-exits .dash-bar-value` | Exits | `white-space: normal` — the hint names page types; `.dash-bar-value` is `nowrap` by default in an `auto` grid track and would push the 390 px layout sideways |
| `.dash-note--gap` | Exits | 2 px `var(--dash-amber)` left border + 8 px padding: a known blind spot, not a footnote |

**Killed from the specs:** `.dash-exits h3:first-child { margin-top: 0 }` — `.dash-panel h3:first-child` (line 181) already does exactly that and matches through the wrapper div. **Devices adds no CSS** (its two stacked sections are `.dash-panel h3` + `BarList`). **Problems adds no CSS** (`severity('slow_start') === 'high'` maps onto the existing `.dash-dot--high`). **Pulse adds no CSS** (`.dash-delta--up/--down` exist; `.dash-tile-sub` has no `nowrap` and `.dash-tile` is a flex column, so the longest new string `▼ 20 % vs previous 7 days (was 118)` wraps downward instead of overflowing).

### `format.ts` additions (three, all exported, all single-implementation)
```ts
const LANGUAGE_NAMES = new Intl.DisplayNames(['en'], { type: 'language' })
export function languageName(code: string | null): string     // guard /^[a-z]{2,3}$/ — .of('en-US@posix') throws RangeError and that tag is LIVE
export function fmtSpan(seconds: number): string              // "< 1 min" / "6 min" / "2 h 11 min" — formatDuration/formatDurationMs in utils/formatters.ts are clock style ("6:52"), timeAgo() needs a timestamp
export function fmtVisitors(n: number): string                // "1 visitor" / "4 visitors" — the single TS mirror of _visitors() in stats_analysis.py; Exits uses it, nobody re-inlines the ternary
```
`LANGUAGE_NAMES` is a second `Intl.DisplayNames` instance because the **type differs** from `countryName`'s `{type:'region'}` — not a duplicate. Do **not** use `'und'` as the unknown sentinel: `.of('und')` returns `"root"`.

---

## 7. SHARED FILES — one pass per file

### 7.1 `pipeline/umami_db.py`
1. Docstring: add `language` to the `session` column list + the two verified notes (§2.1).
2. `SQL_SESSION_EVENTS`: `s.browser,` → `s.browser, s.language,`.
3. New `SQL_LIVE` after `SQL_SESSION_EVENTS`.
4. New `SQL_EXITS` after `SQL_SOURCES`.
5. New `SQL_GLOBE_READY` after `SQL_VITALS`.
No other edit. `SQL_OVERVIEW` stays.

### 7.2 `pipeline/stats_analysis.py`
1. imports: `from collections import Counter, defaultdict`; `from datetime import datetime, timedelta`.
2. `TITLE_BRAND` + `without_brand()` after `page_type()`.
3. `EXIT_LISTS` next to `INTERACTIONS`/`JOURNEY_EVENTS`.
4. `Session.language` field + one constructor arg in `sessions_from_rows`.
5. `pct_change()` above `countries()`.
6. `countries()` gains `until`.
7. `UNKNOWN_DEVICE`, `_PRIMARY_SUBTAG`, `primary_language()`, `device_shares()`, `languages()` after `countries()`.
8. `SCROLL_PAGES`, `SCROLL_STEPS`, `SCROLL_MIN_READS` under `SHALLOW_PAGES`; `reading_funnels()` after `problems()`.
9. `GLOBE_READY_LIMIT` next to `VITAL_LIMITS`; `VITAL_MIN_SAMPLES` comment amended; `_seconds()` next to `_visitors()`.
10. `problems()` signature + docstring (five kinds → six) + the `slow_start` block between the vitals and not_found loops.
11. `exits()` at the end.
12. `_live_row()` + `live_now()` at the end.

### 7.3 `api/routes/founders_stats.py`
1. Module docstring: "seven endpoints" → **"eleven endpoints"**.
2. Import block: **remove** `SQL_OVERVIEW`; **add** `SQL_EXITS`, `SQL_GLOBE_READY`, `SQL_LIVE` (alphabetical).
3. Constants under `LIVE_WINDOW`: `HERE_WINDOW = timedelta(minutes=30)`, `LIVE_LOOKBACK = timedelta(hours=24)`, `LIVE_LIMIT = 12`. `LIVE_WINDOW` stays and is **load-bearing**: `/live` passes `quiet_after=LIVE_WINDOW`, so the tile and the panel read five minutes from one constant.
4. `overview()`: drop `block()`/`today`/`yesterday`; keep the rows in a local `rows` and return `days, sessions, types, devices, languages, reading, hours`.
5. `visitor_countries()`: `block(since, human_only=True, previous=None)`; `today` gets `previous=(midnight - day, now - day)`, `d7` gets `previous=(now - 2*week, now - week)`; still one fetch.
6. `live()` after `visitor_countries()`.
7. `problems()`: `globe_ready=fetch(SQL_GLOBE_READY, since, until)`.
8. `exits()` after `sources()`.

### 7.4 `pipeline/lyra/analytics_alerts.py` (shared, **not optional**)
1. `from pipeline.stats_analysis import pct_change, problems, sessions_from_rows`.
2. `from pipeline.umami_db import (…, SQL_GLOBE_READY, …)`.
3. `_delta()` keeps its German docstring and Discord wording, loses the maths → `pct_change()`.
4. `weekly_digest()`: `globe_ready=fetch(SQL_GLOBE_READY, week_start, now),` inside `problems(...)`; comment "Same four inputs" → "Same inputs the dashboard's Problems panel uses".
5. `problem_lines()` `labels` dict gains `"slow_start": "Slow start"` — it is a hand-kept mirror of `KIND_LABELS`; without it Monday's digest prints raw snake_case.

### 7.5 `ancient-nerds-map/src/components/dashboard/types.ts`
Exactly §4: delete `DayBlock`; add `PeriodChange`, `LanguageCount`, `FunnelStep`, `ReadingFunnel`, `ReadingReport`, `LiveVisitor`, `LiveData`, `ExitPage`, `ExitRow`, `ExitsData`; rewrite `CountryWindow` and `Overview`; widen `ProblemKind`.

### 7.6 `ancient-nerds-map/src/components/dashboard/format.ts`
Add `languageName` (under `countryName`), `fmtSpan` (under `fmtShare`), `fmtVisitors` (under `fmtShare`). Nothing else.

### 7.7 `ancient-nerds-map/src/pages/DashboardPage.tsx`
Docstring count; 4 component imports (`Devices`, `Exits`, `LiveNow`, `Reading`, alphabetical among the existing block); type imports `ExitsData`, `LiveData` (drop nothing — `Overview` still used); 3 new `useStats` lines + `panels` array; 4 JSX insertions at slots 2, 5, 7, 11 per §5.4.

### 7.8 `ancient-nerds-map/src/styles/dashboard.css`
Append two blocks at the end, in this order: `/* ── Live visitors ── */` (5 rules + `.dash-empty b`), `/* ── Reading funnel ── */` (`.dash-funnel-base`), `/* ── Exits ── */` (`.dash-exits .dash-bar-value`, `.dash-note--gap`). No edits above.

### 7.9 `scripts/dashboard_screenshots.py`
1. `country_window(divisor, change=None)` — `change` written out as a literal (a fixture is data; the arithmetic stays in `pct_change`).
2. `FIXTURES["countries"]`: `now.change = None`, `today = country_window(24, change={"previous": 9, "pct": 22})`, `d7 = country_window(4, change={"previous": 118, "pct": -20})`, `d30 = country_window(1)` — one green arrow and one red one in the same shot.
3. `FIXTURES["overview"]`: **drop** `today`/`yesterday`; **add** `devices` (mobile 604 / tablet 79 / laptop 392 / desktop 46 — sums to `sessions.human` 1121), `languages` (13 entries incl. `nb` in the visible six so **"Norwegian Bokmål"**, the longest label the live data can produce, is exercised at 390 px, and a `None` tail), and `reading` (`funnels` for story/country/journal/paper rated + `site` under `min_reads` so the thin line renders; `ignored: 26`, `min_reads: 10`).
4. New helper `funnel(page, opened, reads)` before `FIXTURES`.
5. `FIXTURES["problems"]["problems"]`: insert the `slow_start` row (`label "globe"`, score 34, detail *"p75 19.2 s to interactive against a 3.8 s budget, best 9.5 s, 41 loads by 17 visitors"*) between the 38 and the 24 entries — the list is rendered in receipt order, so it must stay descending: 57 / 42 / 38 / 34 / 24 / 17 / 11. The `PROBLEM_VISITORS` loop (mod 5) needs no change.
6. New helper `live_rows()` + `FIXTURES["live"]` after `"countries"`: six visitors, `total: 9`, `summary: "9 visitors in the last 30 minutes, 6 shown"`, `last: None`. Includes an 86-char story headline (clamp test), one `None` country (blank flag), one >1 h dwell.
7. New helper `exit_rows()` + `FIXTURES["exits"]` after `"content"` — 7 outbound rows incl. a stress row `journals.plos.org` with five page types, 6 discord rows, `clicks: 427`. **Write the comprehension plainly** — the exits spec's `[{"page": page, "n": n} and {"page": page, "clicks": n} for …]` is a typo and must not be copied.
8. No `FIXTURES["reading"]` key (it lives inside `overview`) and no change to `answer_stats()`.

Gate: after `npm run build`, `python scripts/dashboard_screenshots.py` must still print `horizontal overflow 0px` for `dashboard-mobile.png`.

---

## 8. IMPLEMENTATION ORDER

1. **`pipeline/umami_db.py`** — no dependencies. Then `pytest tests/pipeline/test_umami_db_queries.py` with the new `QUERIES` tuple + the three query-shape tests. Gate: parameterised/scoped/read-only guards pass for `globe_ready`, `live`, `exits`.
2. **`pipeline/stats_analysis.py`** — depends only on row shapes from (1). Then `tests/pipeline/test_stats_analysis.py`: `pct_change`, `countries(until=…)`, `primary_language`/`device_shares`/`languages`, `reading_funnels`, `problems(globe_ready=…)`, `exits`, `without_brand`/`live_now`. **All pure — no route, no TS yet.**
3. **`pipeline/lyra/analytics_alerts.py`** — depends on (1)+(2). `tests/pipeline/test_analytics_alerts.py`: `_delta` only *words* the shared percentage (monkeypatch `aa.pct_change`).
4. **`api/routes/founders_stats.py`** — depends on (1)+(2). `tests/api/test_founders_stats_routes.py`: `_FrozenNow` (mandatory — `visitor_countries` cuts at midnight), the canonical `Fetch` markers, `len(fetch.calls) == 6` for `/problems`, `== 1` for `/countries` / `/live` / `/exits`, and the rewritten `/overview` tests (`set(out) == {"days","sessions","types","devices","languages","reading","hours"}`). **The API contract is now frozen — TypeScript can be written against it.**
5. **`types.ts`** — transcribes (4). Compile-breaks `Pulse.tsx` (`o.today`) and `Problems.tsx` (`Record<ProblemKind,…>` missing `slow_start`) **on purpose**.
6. **`format.ts`** — no dependencies; needed by every new component.
7. **New components** `LiveNow.tsx`, `Exits.tsx`, `Devices.tsx`, `Reading.tsx` — depend on (5)+(6). Their class names are now fixed, so:
8. **`dashboard.css`** — depends on (7).
9. **`Pulse.tsx` + `Problems.tsx`** — depend on (5); fixes the two deliberate compile errors.
10. **`DashboardPage.tsx`** — **last TS file**, depends on (5)+(7). One writer owns the docstring count, the type-import list, the `panels` array and the JSX block.
11. **Vitest** — `__tests__/pulse.test.ts`, `liveNow.test.ts`, `exits.test.ts`, `devices.test.ts`, `reading.test.ts` + the extended `problems.test.ts`. `npx tsc --noEmit` and `npm run build` must be green before (12).
12. **`scripts/dashboard_screenshots.py`** — depends on the frozen shapes (4) and a built `dist/` (11). Run it; the 390 px overflow gate is the mobile proof.
13. **Full gate sweep before push:** `ruff format --check && ruff check`, `mypy`, `semgrep scan --config .semgrep`, `lint-imports`, `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80`, `npx knip`, `pytest -m "not integration and not live_llm"`, `npm run lint && npx vitest run`.

**Commit split (3 commits, so a rebase is cheap):**
`feat(stats): globe TTI, devices, languages, reading funnel, exits, live panel` → `feat(dashboard): period comparison on the pulse tiles` → `refactor(stats): /overview drops the SQL_OVERVIEW day blocks`. The third is separable: everything else works with `/overview` untouched, at the cost of two dead queries per refresh and a `DayBlock` nothing reads.

---

## 9. DISAGREEMENTS — rulings

**9.1 Devices: wide with side-by-side lists (spec) vs narrow and stacked.**
→ **Narrow, stacked.** With Exits narrow, the batch adds two narrow panels; `SessionTypes`+`Sources` already form the only complete narrow row. Wide-Devices + narrow-Exits leaves exactly one half-empty desktop cell (the exits spec flagged this itself as "a layout consequence the orchestrator has to settle"). Narrow-Devices makes it two clean pairs and zero holes. The spec's objection — `.dash-lists` gives ~160 px columns inside a half-width panel at 720 px — is real, which is why Devices does **not** use `.dash-lists`: it stacks two `h3`+`BarList` sections exactly like Exits. Cost: the panel is ~4 rows taller on desktop. Benefit: no hole, and on a phone nothing changes at all (one column either way).

**9.2 Reading: own endpoint + `SQL_SCROLL_DEPTH` (spec) vs folded into `/overview`.**
→ **Folded. `SQL_SCROLL_DEPTH` is never created.** Verified this session: all 55 `scroll_depth` events carry `url_path`, all 20 of their sessions have a `session` row (so `SQL_SESSION_EVENTS`' inner join loses nothing), and `depth` arrives as `"25.0000"` in `string_value`, which `int(float(…))` already handles in `sessions_from_rows`. The funnel is therefore a Python fold over rows `/overview` **already fetches** for the same `days` window — 0 queries instead of 1, one endpoint fewer, one SQL constant fewer, one `useStats` subscription fewer. The spec's own numbers confirm equivalence: my fold over the live 7-day window reproduces 167 opens / 12 scrolled reads / 8 ghosts exactly. The spec's warning against re-deriving page types in SQL is honoured — `page_type()` still does it, once.

**9.3 `/overview` losing `today`/`yesterday` (pulse spec) vs gaining `devices`/`languages` (device spec) — and `/overview` is also read by `SessionTypes`.**
→ **Both, in that file, in one pass.** They are disjoint keys. The removal is the last of the three commits so a conflict is a one-line rebase. `Overview.sessions.{human,all}` — which Devices needs as its denominator and its note — is untouched.

**9.4 The Today tile's percentage changes value on deploy.**
→ **Accept, and say so in the commit body.** Today `Pulse.tsx` prints `c.today.sessions` (human, from `/countries`) but feeds `delta()` with `o.today.sessions` (every session, from `SQL_OVERVIEW`). The tile shows **6** under "= same as yesterday" (28 vs 28). After this it reads "▲ 20 % vs yesterday (was 5)". That is a bug fix, not a regression — the number and the percentage finally describe the same population.

**9.5 The d7 comparison is dead on arrival.**
→ **Correct and intended.** Re-verified: `[now-14d, now-7d)` holds **0 events / 0 sessions**, and will until 2026-09-24 ~10:03 UTC. `pct_change` returns `None`, `changeSub` returns `null`, the tile keeps `humanSub`. Do **not** "fix" it by treating 0 → N as +∞ %.

**9.6 `slow_start` is invisible on merge day.**
→ **Do not lower `VITAL_MIN_SAMPLES`.** Re-verified: 8 `globe_ready` samples from 6 sessions, p75 24 758 ms, fastest 9 450 ms. 8 < 10, so `/problems` returns no `slow_start` row today. At 4.2 globe loads a day the gate is crossed on 19/20 Sep by itself. Post-deploy verification is the SQL in §2.2, not the panel. A reviewer seeing "nothing happened" is expected.

**9.7 Discord funnel: merge the server-side `/goto/discord` log into the Exits panel?**
→ **No.** Verified: `api/routes/goto.py` logs to container stdout only; `logs/referrals.log` (nginx foreign referers, 393 lines) contains **zero** `goto/discord` lines, so `scripts/referral_report.py` is not a second view — `scripts/funnel_report.py` is. Different store, different population (the server log counts and flags bots; the Umami tracker silently drops bot UAs), and the API has no read path into docker logs. One number built from both would be a lie. The panel names the blind spot in `.dash-note--gap` and points at `scripts/funnel_report.py`.

**9.8 Should we fix the landing page instead (it installs no `boot.ts`)?**
→ **Out of scope, confirmed as the root cause.** Verified: every `*Main.tsx` starts with `import './analytics/boot'` **except** `index.html`'s inline module (line 661), which imports only `./src/shared/disclaimerContent.ts` — and `dashboardMain.tsx`, deliberately. `landing` is the biggest `src` in the server funnel log (10 of 23 human clicks) and is structurally invisible to Umami. If someone later adds the import, the `.dash-note--gap` sentence becomes false and must be deleted in the same commit.

**9.9 `globe_idle` as a seventh problem kind.**
→ **No kind.** Verified: the only `event_data` key on any `globe*` event is `ms` (10 rows for 10 events), and `globe_idle`'s `ms` is the literal `30000` from `App.tsx:1823` — a flag with no threshold to cross. Both live `globe_idle` events belong to the single worst `globe_ready` session. Listing it double-counts the visitor `problems()` was just fixed to stop double-counting. Revisit only once `slow_start` clears.

**9.10 `/live` polls at 30 s while everything else polls at 60 s.**
→ **Keep 30 s.** `useStats(path, refreshMs = 60_000)` already takes the parameter, the query measured 0.675 ms with both required indexes present, and the panel prints whole minutes — a 60 s refresh could show a minute that is a minute stale. It roughly doubles this dashboard's request rate on its own; if that ever matters, change one number.

**9.11 `live` counts crawlers; `devices`/`languages`/`types` count only humans.**
→ **Both correct, and the notes must say which.** `Session.human` needs the full event stream; `SQL_LIVE` returns one aggregated row per session and cannot re-derive it. Re-deriving it there would create a second, different definition of "human". The tell on the live panel is the dwell column and the grey dot, not a filter. If the owner later wants it, widen the fetch — do not copy the rule.

**9.12 Live list can be shorter than the Pulse "Now" tile.**
→ **By design; one sentence in the note.** Re-verified: 10 of 68 sessions in the last 24 h fired only `vital`/`js_error` and have no page view at all. The inner `LATERAL` drops them because they have no page to name. Do **not** turn it into a `LEFT JOIN` and render a row with an empty page.

**9.13 `Intl.DisplayNames.of('en-US@posix')` throws — two guards or one?**
→ **Two, and neither may be "simplified" away.** Re-verified: exactly one live session carries `en-US@posix`. `primary_language()` in Python removes the whole class of input; the `/^[a-z]{2,3}$/` regex in `languageName()` stops a raw tag that ever slips through (a fixture, a hand-written test, a future caller). `session.language` and `session.device` are never NULL or empty (0 rows) — but `UNKNOWN_DEVICE`/`null` language stay, because "never so far" is not "never".

**9.14 `devices` is not a closed key set.**
→ **`Record<string, number>`, never `Partial<Record<union, number>>`.** Read out of the running Umami 3.4.0 bundle: `n = i?.type || "desktop"; return "desktop" === n && t && 1920 >= +r ? "laptop" : n` — ua-parser can also emit `tablet`, `smarttv`, `console`, `wearable`, `embedded`. A union type would silently drop those sessions. `deviceRows()` prints an unseen word verbatim after the four known ones.

**9.15 Spec arithmetic vs today's live numbers.**
Device spec quoted laptop 109 / zh 11; today the same query returns 110 / 12. **Drift, not a contradiction** — the tracker is live. All structural claims (the 1366×1366 headless cluster, `en-US@posix`, 209/209 `page_title`, 6 outbound clicks all on story pages, p75 24 758 / fastest 9 450 / 8 samples / 6 sessions, 8 ghost scrolls, prev-7d empty) reproduced exactly. **No spec contradicted the data.** The three literal-code bugs found in the specs (§4 stray prose line in `types.ts`, §7.9 `and`-typo in `exit_rows`, redundant `.dash-exits h3:first-child`) are corrected above.

**9.16 Score ties on the Problems panel.**
→ **Insertion order is the tiebreak and it is deliberate: vitals block before the globe block.** Python's sort is stable, so on equal scores a `slow_page` sorts above a `slow_start` (finer-grained finding first). Today both can name "globe" at once — `Slow | globe · INP | 14` is already live (p75 504 ms vs a 200 ms budget, 14 samples) and `Slow start | globe | 12` joins it. Two rows saying "globe" is correct: different defects, different fixes. The vitest test pins both label strings so nobody shortens one into the other. Test fixtures must avoid ties on purpose.

**9.17 Naming ownership (so no two features invent the same word).**
`pct_change` / `PeriodChange` / `changeSub` are the dashboard's **only** change formatters — a future panel imports them, it does not add `delta`/`trend`/`diff`. `fmtVisitors` is the only TS plural rule. `languageName` is the only `Intl.DisplayNames({type:'language'})`. `.dash-note--gap` has exactly one definition. `exits` (route/SQL/function) is unrelated to the `shallow_exit` problem kind — different namespaces, and the comments say so.

---

## 10. EMPTY STATES at today's volume (tracker 1.96 days old; a 7-day window *is* the whole history, and the 30-day switch shows identical numbers)

| Panel | What a founder sees on 2026-09-19 |
|---|---|
| **Pulse** | Four tiles with real numbers. **Today** compares (~6 human vs 5 yesterday → "▲ 20 % vs yesterday (was 5)"). **7 days**: previous window is **0 sessions** → `change.pct = null` → tile keeps `humanSub` ("human sessions, 34 % of 158"). **30 days**: never compares. Spark strip: ~47 hourly buckets, drawn. |
| **LiveNow** | Volatile. Right now 1 session in the last 30 min; a 30-min window was empty in 547 of 2 770 measured minutes (20 %), a 5-min one in 76 % — **treat the empty branch as the main branch**: "Nobody in the last 30 minutes. Last seen 🇮🇳 37m ago on *<headline>*." Biggest observed gap between two events is 117 min, so the 24 h lookback always names someone. Render the empty branch once by hand from the fixture before merging. |
| **VisitorMap** | Unchanged; dots present. |
| **Sources** | Unchanged. |
| **Exits** | **Outbound: two rows** — `youtube.com` 5 clicks / 5 visitors / story, `getty.edu` 1/1/story. **Discord: the empty state** — "No Discord click reached this panel." (`discord_click` = 0 events, ever) plus the amber blind-spot note. Headline: "6 clicks, last one 19 Sep 08:12." |
| **SessionTypes** | Unchanged (53 human sessions). |
| **Devices** | **Not empty.** Phone 18 / **Tablet 0 (a real zero row)** / Laptop 31 / Desktop 4 of 53 confirmed humans. Languages: English 39, German 6, French 2, Spanish 1, Italian 1, Portuguese 1, then the tail line "3 more sessions in 3 other languages." Note names the denominator (53 of 158) — a founder must not read "Italian 2 %" as a trend. Numbers **will not** match Umami's own device/language report (it counts every session: laptop 110 vs our 31, zh 12 vs our 1); the note says why, expect the question anyway. |
| **Journeys** | Unchanged. |
| **Problems** | **No `slow_start` row yet** — 8 globe loads vs the 10-sample gate. The panel shows the existing kinds (worst group today: `slow_page | globe · INP | 14`; `js_error` React #418, 2 sessions, score 6; `not_found` has 0 rows in 7 days so there is no `broken_link` at all). The globe row appears by itself on 19/20 Sep at score 12 and will then sit second. |
| **TopContent** | Unchanged. |
| **Reading** | **No rated funnel.** 12 scrolled reads total; story sits at 9 against `min_reads` 10. Renders: *"No page type reached 10 scrolled reads yet — counts only, no rates."* + the thin line *"too few to read as a rate: story 9 of 64 opens, country 2 of 15, site 1 of 25, paper 0 of 7, journal 0 of 1"* + *"8 scrolls arrived without a page view in this window and were dropped."* That is the honest output, not a stub. Structural caveat in the note: a page shorter than the viewport fires no scroll event at all, so site/country pages will always look worse than stories — **`scrolled/opened` must never become a KPI**. |
| **FeedbackInbox** | Two feedback events; otherwise unchanged. |

**Cross-cutting:** at this volume the 7-day and 30-day switch return identical numbers everywhere. Do not read them as two independent samples. The screenshot fixtures are deliberately rich so the layout is gated even while production is nearly empty — a reviewer comparing the screenshot against live will see two different things, and that is expected.