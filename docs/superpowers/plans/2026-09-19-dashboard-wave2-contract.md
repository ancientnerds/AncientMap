# AncientMap Founders Dashboard — Authoritative Merge Contract
**Date:** 2026-09-19 · **Base commit:** `572a46f` (HEAD == origin/main) · **All live numbers re-verified by me against `ancient_nerds_db` (`umami` + `ancient_map`) and `logs/referrals.log` today.**

Implementers follow this literally. Where a spec disagrees with this document, this document wins. Where this document disagrees with the live data, the live data wins and you stop and report.

---

## 0. The measurement baseline every ruling rests on

7-day window, run today:

| Fact | Value | Consequence |
|---|---|---|
| Sessions / pageviews | **160 / 210** | Everything is a direction, not a KPI |
| Tracker age | since 2026-09-17 10:03 | `days=30` returns the same rows as `days=7` until 2026-10-17 |
| Custom events | vital 400, scroll_depth 55, site_open 39, js_error 26, media_play 12, globe_ready 8, outbound_click 6, filter_toggle 4, feedback 2, globe_idle 2 | — |
| Events that have **never fired** | `search`, `search_empty`, `story_open`, `paper_open`, `not_found`, `share`, `lyra_chat`, `discord_click`, `hub_click` | Kills spec 6; blinds `broken_link` and `empty_search`; empties 3 of TopContent's 4 lists |
| `site_open` context | `site` 36, `globe` 2, `radar` 1 | 92 % of site opens are the SSR page firing itself |
| `/globe.html` | 33 views / 19 sessions; `globe_ready` 8 events / 6 sessions, all on `/globe.html`, carrying `ms` | Spec 1 confirmed exactly |
| Split page loads | **exactly 2 fingerprints**: `1366x1366 chrome Mac OS` (11 loads, max 7 ids), `1280x1200 chrome Windows 10` (4 loads, max 6 ids). Every other fingerprint peaked at 1 | Spec 2's proof holds; 52 of 160 sessions are provably fewer clients than sessions |
| AI arrivals | 12 sessions (chatgpt 11, perplexity 1); **10 of 12 carry only `utm_source`, no referer** | Brief's "2" is wrong by 6× |
| nginx referral log (399 lines) vs Umami, same window | **182 human 200-status Google page arrivals** vs **60 Umami google.com pageviews / 49 sessions** | The tracker misses ~2/3 of search arrivals. Largest single finding in the wave |
| nginx statuses served to *referred* visitors | 200 ×264, **404 ×50, 301 ×26, 410 ×20, 307 ×14, 403 ×4, 499 ×4** | 70 dead answers to real referred visitors that the dashboard cannot see, because `not_found` has 0 rows |
| Application DB | discord_users **5** (2 founders), likes 2, bookmarks 2, cards 47, token_usage_logs 126, research_requests 59 | Spec 9 confirmed |
| `a5a1307` ("scroll_depth only on real scroll") | **is an ancestor of HEAD and is deployed** | Spec 2's "not on the VPS" is wrong |

---

## 1. VERDICTS

| # | Spec | Ruling | Reason |
|---|---|---|---|
| 1 | Globe abandonment | **ACCEPT — merged with wave one's globe-start-time into ONE panel + ONE endpoint + ONE query** | 8 of 33 loads reach an interactive globe. Product-health headline. Two panels reading the same event from opposite ends is the duplication CLAUDE.md forbids |
| 2 | Scraper clusters | **ACCEPT — promoted to panel #2, directly under Pulse** | Verified today with zero false positives. It is the footnote to every other number on the page and must be adjacent to the number it corrects |
| 3 | Returning visitors (calendar month) | **DROP. Trigger: build when a calendar month holds ≥ 200 confirmed-human visitors AND ≥ 10 returners** | 2 returners, one of which is a founder's own browser (`text=this is just a test from MrSchneebly`). On 2026-10-01 00:00 UTC the salt rotates and it reads 0 for days. Retention is answered better by `/members`, which has durable consented identity. Do **not** build `Session.days`, `month_window()`, `/returning`, `.dash-compare`, `.dash-returner*`, `fmtDay` |
| 4 | Entry / exit pages | **ACCEPT — merged into `/journeys`, no new endpoint, no new SQL** | Story is 20 of 45 human entries and 12 of those die on it; every country-hub landing is a dead end. The `Session.pages` → property refactor is accepted because it removes a real second source of truth |
| 5 | AI-assistant referral log | **ACCEPT the module and the fixes; REFRAME the panel and FOLD it into `/sources`** | The AI question (19 log vs 17 tracked) is 19 rows. The same one file answers the far bigger one: 182 vs 60 on Google, plus 70 error responses to referred visitors. Panel becomes "Where do they come from, and how many do we miss?". No `/assistants` endpoint, no `SQL_ASSISTANT_VIEWS` |
| 6 | Search follow-through | **DROP. Trigger: build when a 7-day window holds ≥ 50 `search` events.** Prerequisite bug ticket filed now | Zero `search` events have ever been recorded. The spec's own finding — `useSiteSearch.ts:360` bails out of the tracking timer via `searchingRef`, so a cross-source search that genuinely finds nothing never reports — must be fixed first or the trigger can never fire honestly. That fix ships as its own commit, not as part of any panel |
| 7 | Heritage (visitor × site country) | **SHRINK. Drop the panel, the endpoint, `SQL_HERITAGE`, the tiles and `.dash-tiles--pair`. Keep ONE list: "Countries read about", folded in the frontend from `content.sites[].country`** | 26 pairings, 25 of them a single session; and 92 % of `site_open`s are the SSR page firing itself, so the "diagonal" measures what Google ranks, not what visitors choose. The durable finding is the UK block at 25 % — visible only once England+Scotland+Wales fold to GB, which `getCountryCode()` already does. Trigger for the full matrix: ≥ 300 site-open sessions in 7 days |
| 8 | Stacked 48-hour strip | **ACCEPT in full, including deleting `SQL_HOUR_BUCKETS`** | It fixes a live axis bug (45 rows drawn across a 48-hour axis) and its `is_ai_entry` correction is the one that makes AI honest everywhere. `SQL_HOUR_BUCKETS` has exactly one consumer — verified repo-wide |
| 9 | Members (application DB) | **ACCEPT — narrow panel, fixed windows, 300 s refresh, aggregate only** | 5 members, 2 founders, **0 non-founder activity in 7 days**, newest signup 22 days old. That is the end of the funnel and nothing else on the page can see it. The numbers being bad is the argument for it, not against |
| 10 | WebGL context loss | **ACCEPT both halves unconditionally** | I re-read the code: all three defects are real (see §8). The dashboard half is one more `ProblemKind`, never a panel |

**Net:** 8 accepted (4 of them merged into existing endpoints/panels), 2 dropped with named triggers.

---

## 2. ENDPOINTS — final list after BOTH waves

Every route is `async def`, behind `Depends(require_stats_session)`, under `/api/stats`. `days` is always `Query(7, ge=1, le=90)` unless stated.

| Route fn | Path | Response keys | Owner |
|---|---|---|---|
| `overview` | `/overview?days=N` | `today`, `yesterday`, `last_week`¹, `days`, `sessions{all,human,ai}`, `types`, `hours[48]{hour,ai,human,unconfirmed,sessions}` | #8 + wave1 WoW |
| `visitor_countries` | `/countries` | `now`, `today`, `d7`, `d30` — **unchanged** (one 30-day fetch, sliced four ways) | existing |
| `visitor_map` | `/map?days=N` *(1..30, default 1)* | `points` — unchanged | existing |
| `content` | `/content?days=N` | `sites`, `stories`, `papers`, `searches` — **unchanged shape** | existing (+#7 folded frontend-side) |
| `journeys` | `/journeys?days=N` | `chains`, `pages{sessions,no_page,one_page,moving,entries[],exits[]}`, `scroll`¹ | #4 + wave1 funnel |
| `problems` | `/problems?days=N` | `problems[]` — 7 kinds: `js_error`, `webgl_lost`, `broken_link`, `slow_page`, `globe_start`¹, `shallow_exit`, `empty_search` | existing + #10 + wave1 |
| `feedback` | `/feedback?days=N` *(30..365)* | `items` — unchanged | existing |
| `sources` | `/sources?days=N` | `sources[]{source,family,sessions,views}`, `log{available,reason?,covered_from,covered_days,families[],pages[],statuses[],ai[]}` | existing + #5 |
| `globe` | `/globe?days=N` | `loads`, `reached`, `gave_up`, `never_booted`, `sessions{all,reached}`, `ready_ms{p50,p75,max,samples}` | #1 + wave1 |
| `clusters` | `/clusters?days=N` | `sessions`, `checked`, `flagged`, `proven`, `min_sessions`, `clusters[]`, `proven_fingerprints[]{screen,browser,os}` | #2 |
| `members` | `/members` *(no params)* | `members`, `founders`, `new{d7,d30}`, `active{d7,d30}`, `active_others{d7,d30}`, `returned`, `last_signup`, `lifespans[]`, `acts[]` | #9 |
| `devices`¹ | `/devices?days=N` | wave one owns the shape. **Must accept and honour `exclude` = the `proven_fingerprints` from `/clusters`** | wave1 |
| `live`¹ | `/live` *(no params)* | wave one owns the shape | wave1 |
| `outbound`¹ | `/outbound?days=N` | wave one owns the shape | wave1 |

¹ wave one.

**14 endpoints.** The module docstring currently says "seven"; there are eight today. Whoever lands last writes **fourteen** and nobody writes a number they did not count.

**Endpoints that were proposed and are NOT built:** `/returning` (spec 3), `/assistants` (spec 5 — folded into `/sources`), `/heritage` (spec 7 — never existed as a route, folded into `/content`'s existing payload), `/pages` (spec 4 — folded into `/journeys`).

### 2.1 Fetch merging — the one structural change

`SQL_SESSION_EVENTS` is fetched by `/overview`, `/countries` (30 days), `/journeys`, `/problems` and, after the wave, by the strip and wave one's funnel — **six full scans per minute per open tab**, growing.

**Ruling: quantise the window and memoise `fetch()`.** Two pieces, ~30 lines total:

1. **`pipeline/stats_cache.py`** (new, stdlib only, ~25 lines) — one TTL memo used by both DB layers, so there is exactly one such helper in the repo:
   ```python
   def ttl_cached(ttl: float): ...   # decorator; key = (sql, since, until, sorted(params)) hashed
   ```
2. **`api/routes/founders_stats.py`** — one `_now()`, floored to the minute, feeding `_window()`, `/countries`, `/members` and `SQL_OVERVIEW`'s `live=` parameter:
   ```python
   WINDOW_STEP = timedelta(minutes=1)
   def _now() -> datetime:
       n = datetime.now(UTC)
       return n - timedelta(microseconds=n.microsecond, seconds=n.second)
   def _window(days: int) -> tuple[datetime, datetime]:
       until = _now()
       return until - timedelta(days=days), until
   ```
   `umami_db.fetch` is wrapped with `@ttl_cached(55.0)`, `members_db.fetch_app` with `@ttl_cached(300.0)`.

Effect: within one minute every route asking for "7 days" asks for the **identical** `(since, until)` pair, so six scans collapse to one — **for all open tabs combined, not per tab.** Stated cost: the "Now, last 5 min" tile is now "last 5–6 min". That is written on the panel.

---

## 3. SQL — final constants in `pipeline/umami_db.py`

**Unchanged:** `SQL_OVERVIEW`, `SQL_MAP`, `SQL_SESSION_EVENTS`, `SQL_CONTENT`, `SQL_FEEDBACK`, `_LAST_VISITOR`, `SQL_NOT_FOUND`, `SQL_VITALS`, `SQL_ERRORS`.

**DELETED:** `SQL_HOUR_BUCKETS`. Verified repo-wide: its only consumers are `api/routes/founders_stats.py:23,68` and the `QUERIES` tuple in `tests/pipeline/test_umami_db_queries.py:23`. `pipeline/lyra/analytics_alerts.py` does **not** import it. All three edits land in the same commit or the test module raises `AttributeError` at import.

**NOT CREATED:** `SQL_HERITAGE`, `SQL_ASSISTANT_VIEWS` (spec 5's comparison is served by one extra column on `SQL_SOURCES`), any retention query.

### 3.1 `SQL_SOURCES` — one column added

```sql
SQL_SOURCES = """
SELECT coalesce(nullif(utm_source, ''), nullif(referrer_domain, ''), 'direct') AS source,
       count(DISTINCT session_id) AS sessions,
       -- Page views, so the panel can put Umami's number next to nginx's,
       -- which counts requests. On 2026-09-19 nginx logged 182 human Google
       -- page arrivals and Umami 60: the gap is the panel's whole point.
       count(*) AS views
FROM website_event
WHERE website_id = :website_id AND event_type = 1
  AND created_at >= :since AND created_at < :until
GROUP BY 1 ORDER BY 2 DESC LIMIT 40
"""
```

### 3.2 `SQL_GLOBE` — new, after `SQL_ERRORS`

One query serves both halves of the merged globe panel: the funnel counts **and** the `globe_ready` timings, so wave one adds no second globe query.

```python
#: The one path that hosts the globe. Verified 2026-09-19: exactly one
#: url_path contains "globe", all eight globe_ready events ever recorded fired
#: there, and the utm string lives in url_query — so equality is exact.
GLOBE_PATH = "/globe.html"

#: How often the globe actually comes up, and how long it took when it did.
#: One row per session:
#:   views  — page views, one per document load. App.tsx never calls pushState
#:            (only AccountPage and ArticlesPage do), so Umami cannot
#:            manufacture a virtual view here; views and globe_ready are the
#:            same granularity and therefore divide.
#:   ready  — globe_ready, fired once per load from the map's onLayersReady.
#:   vitals — boot.ts arms onTTFB from every *Main.tsx entry, so a load with no
#:            Core Web Vital never executed our module bundle at all. That is
#:            not the globe losing a visitor.
#:   ready_ms — the milliseconds each globe_ready carried, so the percentile
#:            and the funnel come from ONE scan.
#: The LEFT JOIN is load-bearing: a page view has no event_data row.
#: globe_idle is deliberately not read. markGlobeActivity() (App.tsx:207) is
#: called from exactly three sites — openSitePopup, handleFilterSearchChange,
#: handleSourceChange — so a country toggle, a category toggle and every
#: camera drag leave the timer armed. Both globe_idle events on production
#: carry a constant ms=30000 and both fired for a visitor who was toggling a
#: country filter at that moment. Precision 0/2.
SQL_GLOBE = """
WITH ev AS (
    SELECT e.event_id, e.session_id, e.created_at, e.event_type, e.event_name,
           (max(d.number_value) FILTER (WHERE d.data_key = 'ms'))::float8 AS ms
    FROM website_event e
    LEFT JOIN event_data d ON d.website_event_id = e.event_id
    WHERE e.website_id = :website_id AND e.url_path = :path
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, e.event_type, e.event_name
)
SELECT session_id,
       count(*) FILTER (WHERE event_type = 1)             AS views,
       count(*) FILTER (WHERE event_name = 'globe_ready') AS ready,
       count(*) FILTER (WHERE event_name = 'vital')       AS vitals,
       coalesce(
           array_remove(
               array_agg(ms ORDER BY created_at) FILTER (WHERE event_name = 'globe_ready'),
               NULL),
           ARRAY[]::float8[]) AS ready_ms
FROM ev
GROUP BY session_id
"""
```
*Gotcha, do not "simplify" it away:* `'{}'` as the empty-array literal would break `test_queries_are_parameterised_and_scoped_to_the_website`, which asserts `"{" not in sql`. Use `ARRAY[]::float8[]`.

### 3.3 `SQL_CLUSTERS` — new, spec 2's text taken verbatim

Accepted unchanged, with its two bound parameters `:min_sessions` and `:unknown_country`. Two notes from spec 2 that are **not** optional:
* Do **not** use PostgreSQL array-slice syntax (`[1:40]`) — SQLAlchemy `text()` reads `40` as a bind parameter. The 40-path sample is cut with `row_number()` + `FILTER`, as written.
* The group key is `(screen, browser, os)`. **Country stays out** (one fingerprint arrived from 7 countries; keying on country leaves six unreachable singletons). **Browser stays in** (without it one real Mac visitor collides with himself as `safari` and `ios-webview`).

Add one aggregate to the analysis output, not the SQL: `proven_fingerprints`.

### 3.4 `SQL_WEBGL_LOST` — new, spec 10's text taken verbatim

Reuses `_LAST_VISITOR`. Groups by `(phase, reason)`, returns `n` **and** `count(DISTINCT session_id) AS sessions`. Starts with `WITH`, passes both shape gates.

### 3.5 `pipeline/members_db.py` — new module, application DB

`SQL_MEMBERS` and `SQL_MEMBER_ACTS` exactly as spec 9 wrote them. Non-negotiable details, each verified:
* `research_requests.user_id` is the **Discord id as text**, not the uuid — `JOIN discord_users u ON u.discord_id = r.user_id`. Joining on `u.id` silently returns nothing.
* Both `AT TIME ZONE 'UTC'` casts stay: the columns are naive UTC, the container is `Etc/UTC`, and the output cast is what stops the browser reading `2026-08-28T01:33:22` as local time.
* `:founder_role` is a **bound jsonb parameter**, never a literal — `pipeline` may not import `api`, so the route passes `json.dumps([jwt_auth.FOUNDER_ROLE_ID])` down.
* No query selects `username`, `discord_id`, `avatar_hash`, `submitter_ip` or `credits`.
* `user_contributions` is out for good: the model has no user column, only `submitter_ip`, and all 932 rows are `source='lyra'`.

### 3.6 Wave-one SQL slots (reserved, so nobody collides)

`SQL_DEVICES` (screen/browser/os/`session.language`), `SQL_OUTBOUND` (`outbound_click` → `host` + `page`; 6 events live), `SQL_LIVE`. Scroll funnel needs **no** new SQL — `scroll_depth` is already in `SQL_SESSION_EVENTS` and already folded into `Session.depth`.

---

## 4. PYTHON — `pipeline/stats_analysis.py`

### 4.1 Changes to what already exists

| Existing | Change | Why |
|---|---|---|
| `AI_HOSTS` | **keep**, add sibling `AI_UTM_SOURCES = ("chatgpt","perplexity","copilot","gemini","claude","openai")` and `AI_ENTRY = "ai"` | Two columns, two vocabularies: `perplexity.ai` is a host, `perplexity` is a label, neither contains the other |
| `source_family(referrer, utm_source=None)` | **rewrite the first branch**: `if utm_source: return AI_ENTRY if is_ai_entry(None, utm_source) else utm_source` | It returns the utm verbatim today, so 11 ChatGPT + 1 Perplexity sessions get `entry="chatgpt.com"`. Everything else unchanged |
| `Session.pages` | **field → read-only property** `len(self.page_steps)`; new field `page_steps: list[str]` | One source of truth. Only writer was `s.pages += 1`. **Grep `\.pages\s*=` before landing — an assignment now raises AttributeError** |
| `Session` | new field `from_ai: bool = False` (after `entry`, defaulted, so the five positional args in `sessions_from_rows` are untouched) | `source_family` cannot answer it; 10 of 12 AI arrivals send no referer |
| `sessions_from_rows` | in the `event_type == 1` branch: set `from_ai` beside `entry`; `page = page_type(...)` appended to **both** `steps` and `page_steps`; delete `s.pages += 1` | Order-independent, one extra `page_type()` call per page view |
| `problems(...)` | signature gains `webgl: list[...] | None = None` **between `searches` and `limit`**; docstring "Five kinds" → "Seven kinds"; one new loop after the `errors` loop | Wave one's `globe_start` parameter goes **after** `webgl`. Both optional, both default `None`, so all six existing call sites and every existing test keep passing |
| `_visitors`, `_last_visitor`, `_session_visitor`, `page_type`, `countries`, `journeys`, `session_type_shares`, `UNKNOWN_COUNTRY`, `SESSION_ID_CHARS`, `AUTO_SITE_OPEN_CONTEXT` | **untouched and reused** | Spec 6's `_visitor()` refactor is dropped with spec 6; do not extract it for two callers |

**Rejected changes to existing code:** `Session.days` (spec 3), `Session.human` rewrite (spec 3 — verify-don't-assume was the right instinct, but the panel is gone), any change to `Session.human`'s rule (spec 2's own argument, upheld: a split load proves *one client*, not *not a person*; making `human` depend on a session's neighbours breaks `countries()`, which slices one session list into four windows).

### 4.2 New constants

```python
AI_ENTRY = "ai"
AI_UTM_SOURCES = ("chatgpt", "perplexity", "copilot", "gemini", "claude", "openai")

SESSION_CLASSES = ("ai", "human", "unconfirmed")
HOURLY_STRIP_HOURS = 48

EXIT_RATE_MIN_VIEWS = 10

CLUSTER_MIN_SESSIONS = 3
CLUSTER_SHARED_IDS = 3
CLUSTER_SHARED_LOADS = 2
CLUSTER_NO_CITY = 5
CLUSTER_NO_CITY_SHARE = 0.6
CLUSTER_DIRECT_ONE_PAGE = 5
CLUSTER_PAGE_TYPES = 3

WEBGL_PHASES = {"loading": "globe never started", "live": "globe froze after it had started"}

LIFESPAN_BUCKETS = (("Same day only", 0), ("1-7 days", 7), ("8-30 days", 30), ("Over 30 days", 10**9))
```
Plus `from datetime import datetime, timedelta` and `from collections import Counter, defaultdict` on the existing import lines.

### 4.3 New functions

```python
def is_ai_entry(referrer: str | None, utm_source: str | None = None) -> bool
def session_class(s: Session) -> str
def hourly_classes(sessions: list[Session], until: datetime,
                   hours: int = HOURLY_STRIP_HOURS) -> list[dict[str, Any]]
def globe_funnel(rows: list[dict[str, Any]]) -> dict[str, Any]
def scraper_clusters(rows: list[dict[str, Any]]) -> dict[str, Any]
def entry_exit_pages(sessions: list[Session]) -> dict[str, Any]
def members(rows: list[dict[str, Any]], acts: list[dict[str, Any]],
            now: datetime) -> dict[str, Any]
```

Bodies are spec 8's, spec 1's, spec 2's, spec 4's and spec 9's respectively, with these amendments:

* **`globe_funnel`** additionally folds `ready_ms`: flatten every row's array, and return `"ready_ms": {"p50":…, "p75":…, "max":…, "samples": n}` (`None` values below 5 samples — 8 live samples clear it, 5 is the floor at which a median is not one phone). This is the merge point with wave one: **wave one does not add a second globe query, a second endpoint or a second panel.** Its "globe start time" becomes (a) these percentiles on the face of the globe panel and (b) a `globe_start` problem row when `p75 > 10_000` ms with `samples >= 5` — live p75 is 24 758 ms, so it fires today.
* **`globe_funnel`** keeps `min(ready, views)` per session (a `globe_ready` can arrive 80 s after its page view and straddle the window) and drops rows with `views == 0`.
* **`scraper_clusters`** additionally returns `"proven_fingerprints": [{"screen","browser","os"}…]` for every cluster whose verdict is `proven`. Wave one's `/devices` **must** subtract those and print "excl. N machine sessions", or its OS and country split is wrong by roughly a third.
* **`members`** returns no per-member field. That is the privacy boundary and it is tested twice (fold-level and route-level) by feeding `username`/`discord_id` through and asserting they do not appear in the serialised output.

### 4.4 Where the application-DB query lives (the explicit answer)

**`pipeline/members_db.py`.** Reasons, in order:
1. `pipeline` must not import `api` (import-linter, hard CI gate) — so this cannot live in `api/services/`… and it must not, because
2. `Dockerfile.lyra` copies `pipeline/` only. `stats_analysis.py` and `umami_db.py` live there for exactly this reason; the weekly digest will want members too.
3. The card-game tables are declared in `api/cardgame/models.py`, which `pipeline` may not import — hence **raw SQL**, not models. The table names are strings; they are listed in the module docstring and a live smoke call of `GET /api/stats/members` after deploy is the only check that catches a rename.
4. **No engine of its own.** Every function takes the caller's `Session`; the route gets it from `pipeline.database.get_db` (already sanctioned), so the dashboard shares the existing pool instead of opening a second connection.
5. `fetch_app(db, sql, **params)` is named differently from `fetch` so the route module can hold both as replaceable attributes.

**`pyproject.toml` — REQUIRED, or `lint-imports` fails the deploy:**
```toml
    # Read-only query layer on our own database for the founders dashboard's
    # members panel; under pipeline/ like umami_db, because the Lyra image
    # ships no api/ tree (2026-09-19).
    "api.** -> pipeline.members_db",
    # nginx's referral log: the /sources coverage block and the Discord funnel
    # redirect share BOT_UA_RE. Stdlib only (2026-09-19).
    "api.** -> pipeline.referral_log",
```
`pipeline.stats_cache` needs **no** entry — no `api` module imports it directly.

### 4.5 `pipeline/referral_log.py` — new module

Spec 5's file, accepted, **minus** `assistant_report`/`AssistantReport` and **plus** a broader report:

```python
LOG_PATH = Path(os.getenv("REFERRAL_LOG_PATH", "/app/logs/referrals.log"))
BOT_UA_RE          # moved here from api/routes/goto.py — one definition
ASSISTANT_HOSTS, UTM_ALIASES, FAMILIES, MAX_TAIL_BYTES = 8 * 1024 * 1024
@dataclass(frozen=True, slots=True) class Visit: at, source, path, status, bot, page
def parse_lines(lines) -> list[Visit]
def read_visits() -> list[Visit] | None            # cached on (mtime_ns, size)
def unavailable_reason() -> str
def aggregate(visits, since, pages_only=True)      # the CLI report, unchanged
def coverage_report(visits, since, until) -> CoverageReport
```

`coverage_report` returns `covered_from`, `covered_days`, `families[]{family,visits,bots}`, `ai[]{host,visits,bots}`, `pages[]{path,visits}` (top 8), `statuses[]{status,n}` for `status >= 300`. That last list is the one nothing else on the dashboard can produce: **50 × 404, 20 × 410, 26 × 301 served to referred visitors in two days, while Umami's `not_found` event has fired zero times ever.**

Verified mechanics that must not be "simplified":
* The mount exists and is readable: `docker-compose.yml` binds `./logs:/app/logs:ro` on the `api` service (and `api2` inherits it through the `&api-service` anchor); the file is `-rw-r--r-- www-data:root`, 110 KB, 399 lines. **Read-only — never write into `/app/logs` from the api container.**
* `$time_iso8601` is **VPS local time** (`+02:00` now, `+01:00` after October). `datetime.fromisoformat` handles it; `strptime("%Y-%m-%dT%H:%M:%S")` or string slicing is a silent two-hour window shift.
* A `utm_source` **must not** require a dot. Perplexity tags `utm_source=perplexity`; today's `source_host()` throws every such visit away. This is live bug #1 and this module is its fix.
* The tail is read in **binary** (text-mode `seek` only accepts offsets `tell` produced); a half-line at the seek point is skipped like any other unparsable line.

**Follow-on edits that come with the module:**
* `api/routes/goto.py` — delete the local `BOT_UA_RE` and its comment, `from pipeline.referral_log import BOT_UA_RE`, drop the now-unused `import re` (ruff and vulture both flag it).
* `scripts/referral_report.py` — becomes a thin CLI: delete `FAMILIES`, `family_of`, `source_host`, `is_page`, `parse_since`, `aggregate` and `from api.routes.goto import BOT_UA_RE`; import them from `pipeline.referral_log`; `aggregate()` now takes `Visit`s, so its five call sites in `tests/scripts/test_referral_report.py` become `rr.aggregate(rr.parse_lines(lines), SINCE)`.

---

## 5. TYPESCRIPT, COMPONENTS, CSS, PANEL ORDER

### 5.1 `types.ts` — final additions

```ts
export type SessionClass = 'ai' | 'human' | 'unconfirmed'

export interface HourBucket {          // REPLACES the existing one
  hour: string; ai: number; human: number; unconfirmed: number; sessions: number
}
export interface Overview {            // sessions gains `ai`; hours is always 48 long
  today: DayBlock; yesterday: DayBlock; last_week: DayBlock   // last_week = wave one
  days: number
  sessions: { all: number; human: number; ai: number }        // human and ai OVERLAP — never add them
  types: Partial<Record<SessionKind, number>>
  hours: HourBucket[]
}

export interface GlobeData {
  loads: number; reached: number; gave_up: number; never_booted: number
  sessions: { all: number; reached: number }
  ready_ms: { p50: number | null; p75: number | null; max: number | null; samples: number }
}

export type ClusterVerdict = 'proven' | 'suspected'
export interface Cluster {
  screen: string; browser: string; os: string; device: string | null
  sessions: number; verdict: ClusterVerdict; reasons: string[]; pages: string[]
  countries: CountryCount[]                    // reuses the existing CountryCount
  first_at: string; last_at: string
}
export interface ClustersData {
  sessions: number; checked: number; flagged: number; proven: number
  min_sessions: number; clusters: Cluster[]
  proven_fingerprints: Array<{ screen: string; browser: string; os: string }>
}

export interface EntryPage { page: string; sessions: number; stopped: number }
export interface ExitPage  { page: string; sessions: number; views: number; share: number | null }
export interface PageEnds  {
  sessions: number; no_page: number; one_page: number; moving: number
  entries: EntryPage[]; exits: ExitPage[]
}
export interface JourneysData { chains: JourneyChain[]; pages: PageEnds /* ; scroll: … wave one */ }

export interface LogFamily { family: string; visits: number; bots: number }
export interface LogStatus { status: number; n: number }
export interface LogCoverage {
  covered_from: string; covered_days: number
  families: LogFamily[]; ai: LogFamily[]
  pages: Array<{ path: string; visits: number }>
  statuses: LogStatus[]
}
export interface SourcesData {
  sources: Array<{ source: string; family: string; sessions: number; views: number }>
  /** null when /app/logs/referrals.log is not mounted (any dev box). */
  log: LogCoverage | null
  /** English sentence naming the path and the bind, when `log` is null. */
  log_reason: string | null
}

export type MemberActKind = 'like' | 'bookmark' | 'card' | 'lyra_chat' | 'paper'
export interface MemberAct { act: MemberActKind; n: number; n_d30: number; members: number }
export interface LifespanBucket { bucket: string; members: number }
export interface MembersData { /* exactly the §2 key list */ }

export type ProblemKind =
  | 'js_error' | 'slow_page' | 'broken_link' | 'shallow_exit'
  | 'empty_search' | 'webgl_lost' | 'globe_start'
```

**Near-duplicate interfaces killed:** `ReturnCohort`/`Returner`/`ReturningData` (spec 3, dropped), `AssistantRow`/`AssistantPage`/`AssistantsData` (spec 5 → `LogFamily`/`LogCoverage` inside `SourcesData`), `HeritagePair` (spec 7, dropped — the fold reads `ContentRow.country`), `ContentRow.searches_with_results`/`followed` (spec 6, dropped).

### 5.2 Components

**NEW shared file `components/dashboard/Tile.tsx`** — `Tile` and `Flags` move out of `Pulse.tsx` verbatim, `Tile` gains an optional `value?: number` so a panel with no `CountryWindow` can use it. Pulse and Members import it. This kills spec 9's copy-pasted 12-line `Tile` and spec 7's "export `Tile` from `Pulse.tsx`" hack in one move, and it is the file wave one edits for the week-over-week sub-line — **so it must land before wave one touches Pulse.**

**NEW panels:** `Scrapers.tsx` (spec 2 verbatim), `GlobeReach.tsx` (spec 1 + a `ready_ms` line: *"the 8 that made it waited a median of 16 s, three quarters of them 25 s"*), `Members.tsx` (spec 9 minus its private `Tile`), `Band.tsx`.

**CHANGED panels:**
* `Pulse.tsx` — `Spark` → `Strip` (stacked, legend, zero tick, 48 fixed buckets). Exports `stackHour` for the unit test.
* `Sources.tsx` — gains a second column: `.dash-lists` with "Umami sessions by bucket" | "nginx arrivals by family", the coverage sentence as `.dash-note`, and a `LogStatus` list when any `status >= 300` row exists. Panel becomes `wide`. Question becomes **"Where do they come from, and how many do we miss?"**
* `Journeys.tsx` — absorbs entry/exit as two `BarList`s above the chains (see §5.4 merge ruling). Exports `entryItem`/`exitItem`.
* `Problems.tsx` — two `Record<ProblemKind, …>` entries per new kind: `webgl_lost: 'high' / 'WebGL lost'`, `globe_start: 'mid' / 'Globe start'`. `Record` makes a missed entry a compile error; that is the whole conflict-safety mechanism for the two waves.
* `TopContent.tsx` — a fifth list, **"Countries read about"**, folded in the component from `c.sites` via `getCountryCode()` (imported, never re-implemented — `countryFlags.ts` already folds England/Scotland/Wales→GB and Türkiye→TR). Zero new SQL, zero new endpoint.

**NOT built:** `Returning.tsx`, `Assistants.tsx`, `Heritage.tsx`, `EntryExit.tsx` (its two lists live in `Journeys.tsx`).

### 5.3 CSS — `styles/dashboard.css`

Added, all at the end of the file except the `:root` block:
```
:root  --dash-seg-ai / --dash-seg-human / --dash-seg-unconfirmed   (spec 8's measured ramp)
.dash-spark-legend, .dash-spark-key, .dash-spark-key--{ai,human}, .dash-spark-key b
.dash-spark (height 110px; 140px from 720px), .dash-spark-{ai,human,unconfirmed,zero}
.dash-spark rect:hover { stroke; vector-effect: non-scaling-stroke }
.dash-tiles + .dash-lists { margin-top: 14px }          ← spec 7 and spec 9 both wrote this; land it ONCE
.dash-band, .dash-band-head, .dash-band-body, .dash-band-toggle
```
**Rejected:** `.dash-compare*`, `.dash-returner*` (spec 3), `.dash-tiles--pair` (spec 7). `.loading-retry` and `.webgl-lost-bar` live in `src/styles/index.css` (the globe app's sheet) — different file, no collision.

Colour ruling: spec 8's ramp is the only one backed by measurement (Viénot dichromat simulation + CIE Lab; worst pair 38 ΔE; L\* 92/66/40 monotonic). **`--dash-amber` and `--dash-red-bright` are forbidden as data colours in the strip** — 24 ΔE and 30 ΔE against the green under protanopia. Red stays what it already is: an action and a hover cue, never data.

### 5.4 FINAL PANEL ORDER — three bands, 14 panels

The page cannot carry 17 panels on a 390 px phone. Ruling: one `<div className="dash">` holding three `Band`s; each band is a heading, a toggle button and a `.dash-band-body` that is the existing `.dash-grid`.

**Collapse mechanism (hydration-safe, no `matchMedia` in the render path):** `useState(false)` — identical on server and client — renders `<div className="dash-band-body" hidden={!open}>` for bands B and C. CSS re-opens them on desktop without touching state:
```css
@media (min-width: 720px) {
  .dash-band-body[hidden] { display: grid; }   /* class beats the UA [hidden] rule */
  .dash-band-toggle { display: none; }
}
```
Band A never renders `hidden`. This is the same class of bug as React 418 in `reference-ssr-hydration-storage.md`; it is avoided by construction, and `render.test.tsx`'s storage guard is joined by an assertion that the dashboard calls no `matchMedia` during render.

| Band | Panel | Width | Endpoint | Why here |
|---|---|---|---|---|
| **A — "Is it working?"** *(always open)* | 1. **Pulse** | wide | `/overview` + `/countries` | Is anyone here at all |
| | 2. **Scrapers** | wide | `/clusters` | **Must be adjacent to Pulse.** 67 of 160 sessions are machines, 52 provably. Read one panel apart and "160 sessions" is a lie the founders will act on |
| | 3. **GlobeReach** | wide | `/globe` | The globe is the product and 76 % of loads never see it. Worst product number on the page |
| | 4. **Problems** | wide | `/problems` | What is broken, ranked, with the date and the visitor |
| **B — "Who they are"** *(collapsed on phone)* | 5. VisitorMap | wide | `/map` | |
| | 6. **Sources + coverage** | wide | `/sources` | Where they come from, and that we only see a third of the search arrivals |
| | 7. Devices & language *(wave 1)* | narrow | `/devices` | Pairs with 8 in one desktop row |
| | 8. SessionTypes | narrow | `/overview` | |
| | 9. **Members** | wide | `/members` | The funnel's end: 5 members, 0 non-founder activity in 7 days |
| **C — "What they do"** *(collapsed on phone)* | 10. Live reading *(wave 1)* | wide | `/live` | |
| | 11. **Paths** (entries + exits + chains + scroll funnel) | wide | `/journeys` | One panel, one fetch, one story: where they land, how far they scroll, where they stop, the whole chain |
| | 12. TopContent (+ countries read about) | wide | `/content` | |
| | 13. Outbound & Discord *(wave 1)* | narrow | `/outbound` | 6 events live |
| | 14. FeedbackInbox | wide | `/feedback` | 2 items, one of them a founder's own test |

**390 px justification.** Band A expanded is ≈ 1 760 px ≈ 2.1 screens: Pulse ~520 (four stacked tiles + a 110 px strip + legend + note), Scrapers ~300 (3 rows), GlobeReach ~340, Problems ~600 (15 rows). Bands B and C are two 44 px tap targets below it. On desktop all three bands are open and the grid is unchanged from today, so nothing regresses for the founders' actual screen.

**Merges that made this fit, and their justification:**
* **Entry/exit + journeys + scroll funnel → one "Paths" panel.** All three are "how far did they get", all three ride on `SQL_SESSION_EVENTS`, and `/journeys` already fetches it. Three panels answering one question in three places is the page-space equivalent of a duplicated helper.
* **Coverage → Sources.** Two contradicting numbers (Umami 60, nginx 182) belong in one box with room to say which is which. Spec 5 argued the opposite on 390 px grounds; `.dash-lists` at `wide` gives it two columns from 720 px and a clean stack below, so the argument does not hold.
* **Heritage → TopContent.** One list, not a panel.
* **Globe start → GlobeReach.** One sentence: *"8 of 33 loads made it, and even those waited a median of 16 s."*

---

## 6. COST — per 60 s refresh

| Endpoint | Queries | Heaviest | Ruling |
|---|---|---|---|
| `/overview` | 2 × `SQL_OVERVIEW`, 2 × `SQL_SESSION_EVENTS` (range + 48 h) | session scan | **Cached.** Net `SQL_HOUR_BUCKETS` deleted, so query count is unchanged from today |
| `/countries` | 1 × `SQL_SESSION_EVENTS` **30 days** | the single heaviest query on the page | **Cached — 1/min for all tabs.** Already slices four windows from one fetch; keep it that way. Do not add a fifth caller that re-fetches |
| `/map` | 1 × `SQL_MAP` | small | — |
| `/content` | 1 × `SQL_CONTENT` | medium | Cached; `/problems` reuses the same cached row set |
| `/journeys` | 1 × `SQL_SESSION_EVENTS` | cached | Entries, exits, chains and the scroll funnel all fold from **one** fetch |
| `/problems` | 5 × (session, not_found, vitals, errors, content) + `SQL_WEBGL_LOST` | session + content both cached | 2 real queries after the cache |
| `/feedback` | 1 | tiny | — |
| `/sources` | 1 × `SQL_SOURCES` + **one `os.stat()`** | — | The log is parsed **only when `(mtime_ns, size)` changed** — about every 9 minutes at 160 lines/day — and never beyond `MAX_TAIL_BYTES = 8 MB` (~half a year of log). **A refresh that re-parsed the file would be ~400 lines today and ~58 000 in a year; that is the shape this rule exists to prevent.** `api` and `api2` each hold their own cache: two parses per file change, not one |
| `/globe` | 1 × `SQL_GLOBE` | small (33 rows) | Funnel **and** percentile from one scan |
| `/clusters` | 1 × `SQL_CLUSTERS` | `EXPLAIN ANALYZE` 5.0 ms / 2.5 ms planning | Bounded: 40 groups × 40 paths. **If anyone removes that cap the once-a-minute refresh becomes expensive** |
| `/members` | 2 on the **application** DB | CTE full-scans `token_usage_logs` (126 rows) and `card_collections` (47) | `useStats('members', 300_000)` + `@ttl_cached(300.0)`. If `token_usage_logs` ever reaches millions, materialise a per-user `last_act`; do not widen the CTE |

**Before:** ~14 queries/min/tab, 4 full session scans (one at 30 days).
**After, without the cache:** ~22 queries/min/tab, 6 session scans.
**After, with the minute-quantised 55 s cache:** ~14 distinct queries/min **total, for every open tab combined**, 3 session scans (7 d, 30 d, 48 h).

**Explicitly called out as forbidden shapes:** re-reading a month of events per panel (spec 3's `/returning` would have added a fourth month-scale scan — dropped); re-parsing the referral log per request (cached on file identity); a second `/globe.html` query for wave one's start time (folded); a second query to compare Umami against the log (one column on `SQL_SOURCES` instead).

---

## 7. IMPLEMENTATION ORDER

Strictly dependency-ordered. Each numbered step is one commit; a step cannot compile before its predecessors.

| # | File(s) | Blocks |
|---|---|---|
| 1 | **`pipeline/stats_cache.py`** (new) | the two DB layers |
| 2 | **`pipeline/umami_db.py`** — delete `SQL_HOUR_BUCKETS`, `+views` on `SQL_SOURCES`, add `GLOBE_PATH`/`SQL_GLOBE`/`SQL_CLUSTERS`/`SQL_WEBGL_LOST`, wrap `fetch` **+ in the same commit** `tests/pipeline/test_umami_db_queries.py` `QUERIES` tuple (drop `hour_buckets`, add `globe`, `clusters`, `webgl_lost`) | everything backend. **The test tuple edit is not optional — it is a module-level `getattr` loop and raises `AttributeError` at import** |
| 3 | **`pipeline/referral_log.py`** (new) + `api/routes/goto.py` + `scripts/referral_report.py` + `tests/scripts/test_referral_report.py` + **`pyproject.toml`** | `/sources` |
| 4 | **`pipeline/members_db.py`** (new) + `pyproject.toml` | `/members` |
| 5 | **`pipeline/stats_analysis.py`** — §4 in full. **Grep `\.pages\s*=` first.** Run the existing `test_stats_analysis.py` suite before touching anything else | every route |
| 6 | **`api/routes/founders_stats.py`** — `_now`/`_window`, new + changed routes, docstring count | all frontend fetches |
| 7 | **`components/dashboard/types.ts`** | **every component below** |
| 8 | **`components/dashboard/Tile.tsx`** (extract `Tile`+`Flags` from `Pulse.tsx`) | Pulse, Members, and wave one's WoW work |
| 9 | Components, any order: `Pulse`, `Scrapers`, `GlobeReach`, `Sources`, `Members`, `Journeys`, `Problems`, `TopContent` | — |
| 10 | **`components/dashboard/Band.tsx`** + `styles/dashboard.css` | the page |
| 11 | **`pages/DashboardPage.tsx`** — imports everything; **land last of the source files** | — |
| 12 | **`scripts/dashboard_screenshots.py`** — fixtures for `globe`, `clusters`, `members`, `sources.log`, `journeys.pages`, the 48-bucket `hours`, the `webgl_lost` problem row; add `page.wait_for_selector(".dash-spark-ai")` and `".dash-band-body"` | the 390 px gate is the acceptance test |
| 13 | Tests: `test_stats_analysis.py`, `test_umami_db_queries.py` (beyond step 2), **new** `test_referral_log.py`, **new** `test_members_db_queries.py`, `test_founders_stats_routes.py`, `__tests__/{pulse,problems,journeys,sources,members,scrapers}.test.ts` | — |
| 14 | **WebGL fix** (§8) — independent of 1–13 except that `types.ts` must already carry `'webgl_lost'` | — |
| 15 | **Separate ticket, separate commit:** `App.tsx` route `FilterPanel.toggleCountry`, `toggleCategory` and the camera-move handler through `markGlobeActivity()`; `useSiteSearch.ts:360` `searchingRef` bail-out | unblocks the spec-3 and spec-6 triggers |

**Files both waves touch — resolve by keeping both entries, never by picking one:**
`pipeline/stats_analysis.py` (`problems()` signature + `Session`), `api/routes/founders_stats.py` (import block + route list + docstring count), `types.ts` (`ProblemKind`, `Overview`), `Problems.tsx` (two `Record` maps), `Tile.tsx`, `DashboardPage.tsx` (imports, `panels` array, band JSX), `dashboard.css`, `scripts/dashboard_screenshots.py` (`FIXTURES`), `tests/pipeline/test_umami_db_queries.py` (`QUERIES`). **Land this wave's step 5–7 before wave one opens `stats_analysis.py` or `Pulse.tsx`.**

---

## 8. THE WEBGL FIX — file by file

Three independent defects, all re-confirmed in the tree today. Not one of them is fixed with a try/catch.

**`src/components/Globe/rendering/animationLoop.ts` (line 206)** — `requestAnimationFrame(animate)` is the **first** statement, before the context guard. three.js compiles programs lazily inside `renderer.render()`; on a dead context `gl.createShader()` returns `null` and `shaderSource` throws a `TypeError` straight out of the rAF callback, and the next frame is already booked. The 2026-09-18 burst is exactly three errors **because `MAX_ERRORS_PER_PAGE = 3`, not because it happened three times.**
→ Move `requestAnimationFrame` **below** two checks: `if (ctx.webglContextLostRef.current) { ctx.onContextLost('context_lost'); return }` and `if (renderer.getContext().isContextLost()) { ctx.webglContextLostRef.current = true; ctx.onContextLost('no_shader'); return }`. The hidden-tab early-return stays *after* the reschedule, so a backgrounded tab still resumes. New `AnimationLoopContext` field: `onContextLost(reason)`.

**`src/components/Globe/rendering/sceneInit.ts` (lines 103–112, 128)** — `webglcontextrestored` sets `needsLabelReloadRef.current = true` and **never dispatches `webgl-labels-need-reload`**. The only dispatcher is `handleVisibilityChange` (line 132), which runs on hidden→visible. A context restored while the tab is in front leaves every label texture dead for the rest of the visit. Second defect: `handleVisibilityChange` calls `renderer.render()` unguarded.
→ Dispatch the event from the `webglcontextrestored` handler; add `if (refs.webglContextLostRef.current) return` before the visibility-change render; new `SceneInitOptions`: `onContextLost(reason)`, `onContextRestored()`.

**`src/components/Globe.tsx`** — new props `onWebglLost?`, `onWebglRestored?`; `webglLostReportedRef` (one report per page view); `animationCtxRef` stored before `runAnimationLoop` so restore can restart the stopped loop. `handleContextLost` sends `track('webgl_lost', { reason, phase: layersReadyCalledRef.current ? 'live' : 'loading', ms })`.

**`src/App.tsx`** — `const [webglLost, setWebglLost] = useState(false)`; two props on the existing `<Globe>`; inside the loading overlay the stamp becomes `GPU LOST`, the text `GRAPHICS CONTEXT LOST`, and `.loading-hint` is replaced **in place** by a red "Reload the globe" button (same height, no layout shift). A `webgl-lost-bar` `role="alert"` renders instead when the overlay is already gone.

**`src/analytics/index.ts`** — one line in the event taxonomy: `| 'webgl_lost' // globe's WebGL context died — reason, phase, ms`.

**`src/styles/index.css`** — `.loading-retry` and `.webgl-lost-bar` (+ its button), next to the existing `.loading-hint`.

**Do NOT also patch `src/hooks/globe/useGlobeAnimation.ts`.** It is a dead second copy of the loop with the same guard; `Globe.tsx` uses `rendering/animationLoop.ts`. Patching both is the duplication CLAUDE.md forbids. Raise its deletion as a separate cleanup.

**Accepted behaviour change, state it in the commit:** the loop now *stops* on a lost context instead of spinning. If a browser ever restores a context without dispatching `webglcontextrestored` (Safari frequently does not), the globe stays frozen where it might previously have resumed — but the visitor is now told and given a button, instead of watching a progress bar stuck at 90 % for 38 seconds, which is what the one real visitor did.

**Acceptance gate — no unit test can cover an 80-field context in jsdom, so this is the gate.** On desktop `/globe.html`:
```js
const ext = document.querySelector('canvas').getContext('webgl2').getExtension('WEBGL_lose_context')
ext.loseContext()   // before: unbounded TypeError burst, overlay frozen at LOADING, no globe_ready
                    // after:  ZERO TypeErrors, stamp GPU LOST, one webgl_lost event, reload button
ext.restoreContext()// before: labels stay dead until you switch tabs and back
                    // after:  notice clears, loop restarts, labels come back
```
Run it twice — once while the overlay still reads `LOADING` (`phase: 'loading'`, the 2026-09-18 case) and once after `ALL SYSTEMS NOMINAL` (`phase: 'live'`, which shows the bar instead).

---

## 9. DISAGREEMENTS — every one ruled

1. **"The Sources panel files ChatGPT under Other" (spec 5) vs spec 7.** **Spec 7 is right; spec 5 is wrong.** `/sources` passes `coalesce(utm_source, referrer_domain, 'direct')` into `source_family()`'s **referrer** position, so `"chatgpt.com"` matches `AI_HOSTS` and buckets as `ai` correctly. Only `"perplexity"` (1 session) falls to Other. The bug is real but one-twelfth the size claimed. **Ruling:** fix it once, in `source_family` via `is_ai_entry`, which repairs the session-level path (`Session.entry`, journeys, the strip's AI segment) at the same time. Do not touch `Sources.tsx`.
2. **"Umami sees 2 AI referrals" (the brief) vs 12 (specs 5 and 7).** **12 confirmed**: chatgpt 9 + 2, perplexity 1. Ten of twelve carry only `utm_source`. **Ruling:** any rule written as "entry referrer in `AI_HOSTS`" finds 2 of 12 and `s.entry == "ai"` finds 0. `is_ai_entry(referrer, utm_source)` is mandatory.
3. **Spec 2: "`a5a1307` is a local commit not on the VPS."** **False** — it is an ancestor of HEAD, HEAD == `origin/main`, and the VPS deploys `main`. **Ruling:** scroll-depth already fires only on a real scroll; wave one's funnel is *not* contaminated going forward; and cluster thresholds must **not** be re-tuned in anticipation of a drop that has already happened. Re-measure `max_ids` after 2026-09-24 out of curiosity only — the structural rule (three session ids on one path in one minute is impossible for humans) scales at any volume.
4. **Spec 1 vs wave one, both reading `globe_ready`.** **Ruling:** one `SQL_GLOBE`, one `/globe`, one `GlobeReach` panel carrying both the funnel and the percentile. Neither side ships a second query scanning `/globe.html`.
5. **Three specs mutate `Session`:** `pages`→property (4), `days` (3), `from_ai` (7/8). **Ruling:** 4 and 8 land, 3 does not. `page_steps` exists because `steps` interleaves event names and `"search"` is both an event name and the type of `/search.html` — the two ends of a session genuinely cannot be filtered back out of `steps`. Grep `\.pages\s*=` before landing.
6. **Spec 6 vs live data.** Zero `search` events, ever. **Dropped**, trigger named, and its genuinely valuable finding — the `searchingRef` bail-out that suppresses exactly the "searched everything, found nothing" case — is promoted to its own bug ticket in step 15.
7. **Spec 7's heritage panel vs the `site_open` context distribution.** 36 of 39 site opens carry `context='site'`, i.e. the SSR page firing itself. Spec 7 chose not to filter and said so honestly in its risks; but that makes the panel a measure of what Google ranks, sold under a title about what visitors choose. **Ruling:** the panel is dropped and only the site-country ranking survives, inside TopContent, where "what got served and read" is the honest frame. The `Tile` export from `Pulse.tsx` that spec 7 needed is dropped with it.
8. **Spec 9's private `Tile` vs spec 7's `export function Tile`.** **Ruling:** neither. Extract `Tile` and `Flags` into `components/dashboard/Tile.tsx`. Spec 9's own risk 12 called its duplication "deliberate"; it was avoidable, and the memory file is explicit that copy-pasted helpers are not acceptable.
9. **Spec 2 refuses to change `Session.human`.** **Upheld, in full, with its reasoning:** a shared page load proves those sessions are *one client*, not that they are *not a person*; `human` is read from a session's own events and making it depend on its neighbours would silently change a session's answer depending on which of `countries()`'s four windows you look at. The correction is carried as an explicit number on the Scrapers panel and by `proven_fingerprints`, which wave one's `/devices` must subtract.
10. **Spec 5's standalone `/assistants`.** **Folded into `/sources`.** Its own risk 5 predicted the panel would stay thin ("~8 rows a day") and its risk 11 named the bigger panel it declined to build. The bigger panel is the one that ships, because 182 vs 60 on Google — and 70 error responses served to referred visitors while Umami's `not_found` has never fired once — change how a founder reads every other number on the page.
11. **Spec 3's salt-rotation research.** Sound and worth keeping in the handover; the panel is still dropped. The footer already tells the founders that a visitor is only recognised within one calendar month, which is the honest version of the same sentence at 2 returners.
12. **Spec 10 vs spec 1 on who owns the globe's failures.** No conflict: `webgl_lost` is a `ProblemKind` (a smoke detector that should get *rarer*), the funnel is a panel (a rate). Both ship.
13. **`founders_stats.py`'s docstring says "seven endpoints"; there are eight.** Ruled: whoever lands last writes **fourteen**, after counting `router.routes`.

**One caveat that survives every ruling and belongs on the handover, not in a panel note:** Umami drops declared crawlers before the insert — GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot and Applebot appear **zero times** in the events table *and* zero times in the referral log (they send neither a referer nor a utm). "42 % of sessions are automated" must never be read as "and the rest are people". The honest crawlers are structurally invisible to this dashboard, and the only way to see them is a second nginx `log_format` keyed on crawler user agents — which the deploy user cannot currently read `/var/log/nginx/access.log` to verify. That is its own piece of work.