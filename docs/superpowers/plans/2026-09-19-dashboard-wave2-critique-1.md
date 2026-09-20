I ran every SQL statement in the contract against the live `umami` and `ancient_map` databases on the VPS, plus EXPLAIN (ANALYZE, BUFFERS) and synthetic 10×/100× workloads. Findings by severity.

---

# BLOCKERS — things that will not work as written

### 1. `ttl_cached`'s stated key does not exist for `fetch_app` (§2.1 vs §4.4)
§2.1 defines one decorator with `key = (sql, since, until, sorted(params))`. §4.4.5 defines `fetch_app(db, sql, **params)` — first positional is a **per-request SQLAlchemy `Session`** (`pipeline/database.py:59`, pool 20+30 at `:42-47`), and there is no `since`/`until` at all. The stated key cannot be computed. If the decorator falls back to keying on `*args`, the `Session`'s identity differs on every request → the 300 s memo **never hits**, and the memo dict holds a strong reference to every request's `Session`, i.e. a connection/memory leak on a 20+30 pool. Either exclude `fetch_app` or give it its own key.

### 2. `sorted(params)` throws away parameter *values*
Measured: `sorted({'live':1,'min_sessions':3})` → `['live','min_sessions']`. Two calls with identical `(sql, since, until)` but different values collide. Not live today (`/overview`'s two `SQL_OVERVIEW` blocks differ in `since`/`until`), but `SQL_GLOBE` takes `:path` and `SQL_CLUSTERS` takes `:min_sessions`/`:unknown_country` — a second `path` would silently return the first one's rows. Must be `sorted(params.items())`.

### 3. No eviction is specified — the memo is an unbounded leak
The key changes every minute by construction. ~20 distinct keys/min × 1,440 min = **~28,800 entries/day per container**, each holding a whole result list (measured: the 30-day session list is 373 KB of Python objects today; ~56 MB at 10×). `pipeline/lyra/analytics_alerts.py:27-36` also imports `fetch`, so the long-lived Lyra worker inherits it. A 25-line sketch with no prune and no `maxsize` is the single most dangerous under-specified item in the document.

### 4. `:param::type` silently truncates the bind name — and §3.5 walks straight into it
SQLAlchemy 2.0.45, `TextClause._bind_params_regex = (?<![:\w\x5c]):(\w+)(?!:)`. Measured:
```
'roles @> :founder_role::jsonb'      -> binds ['founder_rol']     # WRONG
'CAST(:founder_role AS jsonb)'       -> binds ['founder_role']    # correct
'b = :until::timestamptz'            -> binds ['unti']            # WRONG
```
§3.5 mandates `:founder_role` as a bound jsonb parameter and mandates `AT TIME ZONE 'UTC'` casts, but warns about neither. The natural Postgres spelling raises `A value is required for bind parameter 'founder_rol'` at runtime.

### 5. §3.3's array-slice prohibition is false as written
Measured: `text('SELECT (array_agg(p))[1:40] … WHERE a=:since')` → binds `['since']` **only**. `[1:40]` is safe — the lookbehind rejects a `:` preceded by `1`. Only the open-ended form binds: `[:40]` → `['40','since']`. The contract forbids a cheap construct on a wrong premise and mandates a `row_number() + FILTER` workaround that costs more.

### 6. The Scrapers panel returns **zero rows** if "page loads" is read as page views
Spec 2's proof reproduces *exactly* — but only over **all** events:
```
 screen    | browser | os         | shared_loads | max_ids     (all events)
 1366x1366 | chrome  | Mac OS     |           11 |       7     <- contract: 11 loads, max 7
 1280x1200 | chrome  | Windows 10 |            4 |       6     <- contract: 4 loads, max 6
                                                               (0 other rows)
```
With `event_type = 1` added: **0 rows**. Sessions 34+18 = 52 ✓. The contract calls them "Split page loads … 11 loads" and rules the panel to slot #2 under Pulse; the obvious implementation empties it.

---

# WRONG NUMBERS in the §0 baseline

| Contract | Measured today | |
|---|---|---|
| "**182** human 200-status Google page arrivals" | **166** over the whole log; **153** inside the tracker window | 13 predate Umami's first event (log starts 08:19 UTC, tracker 10:03 UTC) — the contract compares the whole log against a 7-day tracker window. No filter combination reproduces 182 (200-only 166, 200+301 186, any status 212). The finding survives at 153 vs 61 ≈ 2.5×; the number does not. |
| "**70** dead answers to real referred visitors" | 71 raw, but **29 are not page requests** and **47 of the 50 404s carry an unparseable referer** | The human page-request truth is 21×404 + 21×410 = **42**, and the 404 half is `/wp-admin/css/`, `/.well-known/`, `/images/images/cache.php`, `/uploads/` scanner probes with fake referers — exactly what `scripts/referral_report.py:141-144` filters out with `pages_only=True`. §4.5's `coverage_report(visits, since, until)` has **no `pages_only` switch**, so the panel prints scanner noise as founder-facing truth. |
| status list "200×264, 404×50, 301×26, 410×20, 307×14, 403×4, 499×4" | 200×266, 404×50, 301×27, 410×21, 307×14, 403×4, 499×4, **302×13, 405×2, 500×1, 206×1** | The list is incomplete; 302 is the third-largest non-200. |

---

# A LIVE BUG THE CONTRACT MISSES — 9× bigger than the one it does name

**Scheme-less referers are silently dropped.** `scripts/referral_report.py:99` does `urlsplit(ref).hostname`, which returns `None` for a referer logged without a scheme. nginx logs both forms:

```
raw ref values:  'https://www.google.com/' ×210   'www.google.com' ×27   'binance.com' ×28
lines whose ref has NO parseable host:  55 / 403  (13.6 %)
plus 19 utm-only lines  ->  74 of 403 (18 %) have no attributable host
```

**27 of those are genuine `www.google.com` arrivals** — and they are precisely the error responses (404/403/301) the panel exists to surface. §4.5 fixes the "utm without a dot" case (3 lines) and calls it "live bug #1"; this one is 9× larger and unmentioned. Consequence for the panel: `statuses[]` counts all 403 visits while `families[]` can only attribute ~356 — two lists side by side in one box disagreeing by 18 %.

**Second contamination:** `http://localhost:5199/globe.html?demo=1` appears **47 times (11.7 % of the log)** — all `GET /api/...`, all 200, all one desktop UA. That is the founder's own Vite dev server hitting production. `family_of("localhost")` = `"other"`. Unless `coverage_report` filters like `aggregate(pages_only=True)` does, **"other" becomes the #2 family on the panel and it is the founder looking at himself.** Measured families over the whole log: `search 227, DROPPED 74, other 68, social 30, ai 4`.

---

# COST — what each endpoint really costs, and what breaks at 10×

Measured warm inside `ancient_nerds_api` (`docker exec … python`):

```
SQL_SESSION_EVENTS 7d   13.6 ms  767 rows  2,334 buffers   (30d identical - tracker is 2 days old)
SQL_VITALS 4.6   SQL_ERRORS 4.1   SQL_CONTENT 3.9   SQL_MAP 3.3   SQL_NOT_FOUND 2.5
SQL_FEEDBACK 2.1   SQL_OVERVIEW 1.8   SQL_SOURCES 1.7   SQL_HOUR_BUCKETS 1.4   SQL_GLOBE 0.96
sessions_from_rows 7d  1.7 ms
```

### C1 — Every route is `async def` and every `fetch()` is blocking psycopg2
`api/routes/founders_stats.py:45,60,…` + `pipeline/umami_db.py:283-287`; `Dockerfile:93` = `uvicorn api.main:app`, one worker. **All dashboard SQL is event-loop time the container cannot serve the public site with.** §6 tallies DB milliseconds and never names this. ~65 ms per refresh today; **~0.6–1 s per refresh per container at 10×**, every 60 s, in both `api` and `api2`.

### C2 — "~14 distinct queries/min total" undercounts by ~40 %
Enumerating distinct `(sql, since, until)` tuples after the wave at `days=7`: `SQL_OVERVIEW`×2 (today/yesterday windows differ), `SESSION_EVENTS`×3 (7 d / 48 h / 30 d), MAP, CONTENT, FEEDBACK, SOURCES, NOT_FOUND, VITALS, ERRORS, GLOBE, CLUSTERS, WEBGL_LOST, DEVICES, LIVE, OUTBOUND, MEMBERS, MEMBER_ACTS = **20** (18 umami + 2 app-DB). The memo dedups only 4 (the 7-day session scan across `/overview`, `/journeys`, `/problems`; `SQL_CONTENT` across `/content` and `/problems`). The "before" figure is 15 by count of the current code, not 14.

### C3 — "for all open tabs combined, not per tab" is wrong by the container count
`docker-compose.yml:86` `api: &api-service`, `:152` `api2: <<: *api-service`, comment at `:149` "nginx balances an upstream of 8000+8001". **Two processes, two memos → 2 scans/min, not 1.** The contract states this correctly one section later for the referral log and forgets it here.

### C4 — 55 s TTL under a 60 s key lifetime
`_now()` floors to the minute, so the key lives 60 s and the entry dies at 55 s. Every minute there is a 5 s hole where an identical query re-runs. Set TTL ≥ the floor.

### C5 — `/clusters` is the first thing that breaks at 10×
`count(DISTINCT session_id)` grouped by `(screen, browser, os, url_path, minute)` forces a **sort of every event in the window**; it cannot hash-aggregate. Prod plan sorts 767 rows into **118 kB = 154 B/row**; `work_mem` is **4 MB** → the spill point is ~27,000 events = **exactly 10× today's traffic over a full 7-day window**. Synthetic confirmation:
```
 27,000 rows ->  70 ms, quicksort in memory
270,000 rows -> 791 ms, Sort Method: external merge  Disk: 11544kB, temp read=1905 written=1910
```
§6's "Bounded: 40 groups × 40 paths" bounds the **output**. The sort is unbounded. This is a once-a-minute query that writes to disk.

### C6 — the 30-day `SQL_SESSION_EVENTS` is the other one
Its correlated `event_data` subquery runs once per event (`SubPlan 1 … loops=765`, **2,101 of the query's 2,334 buffers**). At a synthetic 10× row count (7,670 rows): **64 ms, 21,400 shared buffer hits = 167 MB of buffer traffic**, and JIT switches on (15.7 ms). `shared_buffers` is **128 MB**, shared with `ancient_map` in the same container — one call already touches more pages than the whole cache holds. A genuinely full 30-day window at 10× (~115,000 events) extrapolates to ~316,000 buffers ≈ 2.5 GB of traffic and ~1 s, once a minute, per container. Separately: `JOIN session s` in `pipeline/umami_db.py:82` carries **no `website_id` and no time predicate** — today it is a `Seq Scan on session` + `Sort` of the whole table on every call, and that table has no retention policy.

### C7 — `/sources`' log cache inverts at 10×
`read_visits()` is keyed on `(mtime_ns, size)`. Measured growth: 403 lines / 2 days = **202 lines/day** → mtime changes about every 7 min today (the contract's "about every 9 minutes" is right). At 10× that is ~2,015 lines/day = **one new line every ~43 s, shorter than the 60 s refresh — so every refresh re-parses.** Measured parse cost: 403 lines 1.7 ms · 8,060 lines 39 ms · 58,435 lines (15 MB) **311 ms**. Capped at `MAX_TAIL_BYTES = 8 MB` that is ~160 ms of synchronous JSON parsing on the event loop, per refresh, per container. §6's own sentence — *"A refresh that re-parsed the file would be … ~58 000 in a year; that is the shape this rule exists to prevent"* — describes exactly what the rule produces at 10×. (Also: 8 MB ≈ 147 days at today's rate but ≈ **15 days** at 10×; "~half a year of log" is a today-only claim.)

### C8 — `/globe`'s "small (33 rows)" is the result, not the scan
Measured plan: `Seq Scan on event_data` (all 2,052 rows) + `Seq Scan on website_event` (767, 632 removed by filter), 0.955 ms. The `LEFT JOIN event_data` carries no `d.created_at`/`d.website_id` predicate; only the planner choosing `event_data_website_event_id_idx` keeps it off a full scan at volume. Same shape as `SQL_CONTENT`/`VITALS`/`ERRORS`, so it is consistent — but the cost line should say so.

---

# DOES ANY JOIN DOUBLE-COUNT SESSIONS? (asked explicitly)

**Yes — one, and the contract touches that exact query.** `SQL_SOURCES` groups per *event*, so a session whose first view has `referrer_domain='google.com'` and whose second has none appears under **both** `google.com` and `direct`:

```
session_source_pairs 135 | distinct_pageview_sessions 127 | overcount 8   (6.3 %)
  3 × google.com+direct, 3 × chatgpt.com+direct, bing.com+direct, discord.com+direct
```
Pre-existing, but §3.1 adds `views` to this query and §5.2 promotes the panel to `wide` with the sessions column sitting next to an nginx number. The column does not sum to the session total and nothing says so.

**Everything else is clean, verified row-by-row:**
- `SQL_SESSION_EVENTS`' `JOIN session` is on `session_pkey` — measured `rows=765` = exactly the `website_event` count. No fan-out.
- `SQL_GLOBE`'s `ev` CTE groups by `e.event_id` (PK) *before* the outer aggregate, so the `event_data` LEFT JOIN cannot fan out: 398 joined rows → 133 `ev` rows → 19 session rows, and `views` summed to **exactly 33** = the true `/globe.html` pageview count.
- `SQL_CONTENT`, `SQL_VITALS`, `SQL_ERRORS`, `SQL_NOT_FOUND` all use the same group-by-`event_id` shape.

---

# PARAMETERISATION & WINDOW SCOPING (asked explicitly)

- `SQL_GLOBE` run through `sqlalchemy.text()` extracts exactly `['path','since','until','website_id']`. It passes `test_queries_are_parameterised_and_scoped_to_the_website` (has `:website_id`/`:since`/`:until`; no `'%`, `%s`, `{`) and `test_queries_only_read` (starts with `WITH`, no DML verb). §3.2's `'{}'` gotcha is real and its `ARRAY[]::float8[]` fix works — the `::` survives the bind regex because the preceding `]` falls outside the lookbehind class.
- Every existing `SQL_*` is parameterised and scoped to `[:since, :until)` and `:website_id`. None interpolates.
- `/members`' two queries are the only ones with no window and no `:website_id`; they are on another DB with their own test module, so the gate is not weakened — but §7 step 13 lists `test_members_db_queries.py` without saying what it must assert. It needs its own `test_queries_only_read` equivalent.

---

# VERIFIED SOUND (what I checked and found correct)

- **Every §0 Umami number.** Sessions/views 161/211 (contract 160/210, grew since). Tracker first event 2026-09-17 10:03:33 UTC. Event census: vital **401** (contract 400), scroll_depth 55, site_open 39, js_error 26, media_play 12, globe_ready 8, outbound_click 6, filter_toggle 4, feedback 2, globe_idle 2 — all exact. All nine "never fired" events absent. `site_open` context: site 36 / globe 2 / radar 1. `/globe.html` 33 views / 19 sessions; globe_ready 8 events / 6 sessions.
- **Spec 2's fingerprint proof** reproduces exactly (table above), 52 sessions.
- **All of `SQL_GLOBE`'s premises.** Exactly one `url_path` contains "globe"; all 8 `globe_ready` and both `globe_idle` fired there; `url_path` never carries a query string (59 events have non-empty `url_query`, **0** have `?` in `url_path`), so `=` is exact; `ms` is `data_type 2` with both `number_value` and `string_value` populated, so `max(d.number_value)` is right.
- **The percentiles are exact.** 8 samples `{9450, 10023, 11059, 12488, 19917, 20110, 38703, 80383}` → p50 **16 202.5 ms**, p75 **24 758.25 ms**. The contract's "median of 16 s" and "p75 is 24 758 ms" are correct, and p75 > 10 000 with samples ≥ 5 means the `globe_start` problem row does fire today.
- **Every §3.5 application-DB claim.** `research_requests.user_id` is `varchar(255)`; `JOIN … ON u.discord_id = r.user_id` → **59 rows**, `ON u.id::text` → **0 rows** (the warning is exactly right); all timestamps are `timestamp without time zone`; `discord_users.roles` is jsonb; `user_contributions` has no user column, 932 rows, all `source='lyra'`.
- **Every §9 number.** 5 members, 2 founders (`roles @> '["933105341292486707"]'`, matching `api/services/jwt_auth.py:22`), 2 likes, 2 bookmarks, 47 cards, 126 `token_usage_logs`, 59 `research_requests`, newest signup `2026-08-28 01:33:22`, **0 acts in the last 7 days** (founder *and* non-founder; 18 + 22 in 30 days).
- **`SQL_HOUR_BUCKETS` consumers** are exactly `api/routes/founders_stats.py:23,68` and the string tuple at `tests/pipeline/test_umami_db_queries.py:23`. `pipeline/lyra/analytics_alerts.py:27-36` imports CONTENT/ERRORS/FEEDBACK/NOT_FOUND/OVERVIEW/SESSION_EVENTS/VITALS/fetch and **not** HOUR_BUCKETS.
- **The axis bug is real:** `SQL_HOUR_BUCKETS` returns **45 rows** for both a 7-day and a 48-hour window.
- **Counts:** 8 `@router.get` today, docstring says "seven"; 8 + 6 new = **14**. Correct.
- **`a5a1307`** is an ancestor of HEAD and the VPS checkout is `572a46f` — §9.3's rebuttal is right.
- **`.pages =`**: the only writer is `pipeline/stats_analysis.py:191`; readers are `:395` and `tests/pipeline/test_stats_analysis.py:151`. The property refactor is safe.
- **§9.1's `source_family` ruling is right.** `/sources` passes the coalesced value into the *referrer* position (`api/routes/founders_stats.py:179`), so `chatgpt.com` already buckets as `ai`; only the bare `perplexity` (1 session) falls to Other. Measured AI split: chatgpt utm-only 9 sessions + chatgpt utm&referer 2 + perplexity utm 1 = **12 sessions, 10 utm-only** — §9.2 confirmed.
- **pyproject:** both proposed `api.** ->` allowances match the existing style at `pyproject.toml:92,95`; `pipeline.stats_cache` genuinely needs none.
- **The log mount:** `./logs:/app/logs:ro` on the `api` anchor at `docker-compose.yml:125`, inherited by `api2` at `:153`; file is 403 lines, 109 KB, `-rw-r--r-- www-data:root`. `datetime.fromisoformat` handled **403/403** lines with `+02:00` offsets, 0 failures.

---

# SMALLER

- **§7 step 2's diagnosis is wrong.** `QUERIES` is a module-level *string* tuple (`tests/pipeline/test_umami_db_queries.py:20-31`) and the `getattr` runs inside the test bodies (`:36`, `:43`). Deleting `SQL_HOUR_BUCKETS` without editing it gives **two failing tests, not an `AttributeError` at import**. The edit is still mandatory; the stated symptom sends an implementer to the wrong place.
- **`globe_funnel`'s `never_booted` mixes granularities.** `vitals` is a per-*session* count but the number is reported per *load* ("8 of 33 loads"). It is accidentally right today — every never-booted session has `vitals = 0` across all its views (`e23b0213` 2/0, `40644374` 2/0, `47b0f24b` 1/0, `3d8d7f53` 1/0). A session with 4 views where one load failed to boot would be counted as fully booted. `website_event.visit_id` exists and would give the per-load key.
- **§2 narrows `/feedback`** from `Query(30, ge=1, le=365)` (`api/routes/founders_stats.py:161`) to "30..365" with no stated reason — a breaking parameter change slipped into a table.
- **`useStats` polls forever in background tabs.** `ancient-nerds-map/src/components/dashboard/useStats.ts:22` is a bare `setInterval` with no `document.hidden` guard and no jitter; going from 8 to 14 panels means 14 simultaneous requests in the same tick every 60 s, per open tab, forever.
- **Everything is still self-identical until 2026-10-17.** Not just `days=30` (which the contract notes) — the 48-hour strip fetch also returns the *same 767 rows* as the 7-day fetch right now (0 sessions straddle the 48 h cut), so neither the strip's separate scan nor the 30-day scan can be cost-validated on live data yet. When they diverge, a session that started before the 48 h cut will be truncated in the strip's fetch and can be classed `unconfirmed` there while the 7-day fetch calls it `human` — two numbers on the same Pulse panel disagreeing.