# Founders Dashboard — BUILD PLAN (authoritative)

**Date:** 2026-09-19 · **Base commit:** `572a46f` · **Supersedes:** both wave contracts and all
eight critiques. Where this file disagrees with anything else, this file wins.

Every number below was re-measured by me today against `ancient_nerds_db` (`umami` and
`ancient_map`) and `/var/www/ancientnerds/logs/`. Where a contract and a critique disagreed, the
measurement decided, and the measurement is quoted next to the ruling.

## 0. Decisions

### 0.1 Measurement baseline (all re-run 2026-09-19, 7-day window)

| Fact | Measured | Source |
|---|---|---|
| Views / sessions | 212 / 162 | `website_event` |
| Tracker first event | 2026-09-17 10:03:33 UTC | `min(created_at)` |
| Custom events, all time | vital 401, scroll_depth 55, site_open 39, js_error 26, media_play 12, globe_ready 8, outbound_click 6, filter_toggle 4, feedback 2, globe_idle 2 | `event_type = 2` |
| Never fired, ever | `search`, `search_empty`, `story_open`, `paper_open`, `not_found`, `share`, `lyra_chat`, `discord_click`, `hub_click`, `globe_focus` | same |
| `/globe.html` | 33 views, 8 `globe_ready`, 19 sessions | `SQL_GLOBE` shape |
| Hour rows in the last 48 h | **45** — the axis bug is real | `date_trunc('hour')` |
| AI arrivals | 13 sessions: utm `chatgpt.com` 11, utm `perplexity` 1, referrer `gemini.google.com` 1 | `utm_source`/`referrer_domain` |
| Sessions in a page load shared by ≥ 3 ids | **38** (1366x1366 chrome Mac OS 22, 1280x1200 chrome Windows 10 16) | load-sharing query |
| Same, at ≥ 2 ids | **52 in six fingerprint rows** — the two machines (32 + 16) plus four rows that are two real visitors counted twice (one browser reporting itself as both `safari` and `ios-webview`, one Android phone under two OS strings) | same |
| Same, restricted to `event_type = 1` | **zero rows at any threshold ≥ 3** — the maximum number of ids on one *page view* in one minute is 2. The shared thing is events, not page views | same query + `AND event_type = 1` |
| Sessions with **zero** page views | **34** of 163, all inside the two fingerprints above | session fold |
| Sessions with an interaction but **zero** page views | **8**, all inside the two fingerprints above | session fold |
| `referrals.log` | 407 lines, 112 KB, `www-data:root` | `wc -l` |
| Log statuses | 200×267, 404×50, 301×27, 410×21, 307×14, 302×13, 403×4, 499×4, 405×2, 500×1, 206×1 | log parse |
| Google page arrivals nginx answered (200 or 410) | **189** — 168 with a 200, 21 with a 410. Umami, same window: **62 views from 51 sessions** | log parse, `website_event` |
| Real non-200 answers to referred humans | **21×410** (Google → retracted stories), **4×499**, **1×500**. The 27×301 are the legacy `/site.html` rule working as designed and are followed by their own 200 | log parse |
| The 50 404s | **none is a referral.** 27 forge `www.google.com` on `.php` / `//images/.../cache.php` paths, 20 forge `binance.com` on `/wp-admin/`, `/uploads/`, `/.well-known/`, 1 each `bing.com` / `facebook.com` / `t.co` on `/wp-login.php`. `BOT_UA_RE` catches **none** of them — the binance scanner sends a plain Chrome UA | log parse |
| Own dev server in the log | **47 of 407 lines (11.5 %)** — `http://localhost:5199/globe.html?demo=1` | log parse |
| Log parse cost | **8.6 ms for 408 lines / 110 KB** inside `ancient_nerds_api`, i.e. **21 µs per line, ~80 ms per megabyte** | `perf_counter`, best of 7 |
| `goto_discord` lines in `ancient_nerds_api.log` | 29 — and **not one carries a timestamp**; the file is **183 MB** | `grep`, `sed` |
| `goto/discord` lines in `referrals.log` | **0** | `grep -c` |
| Application DB | discord_users 5 (2 founders), likes 2 **by 1 member**, bookmarks 2 **by 1**, cards 47, token_usage_logs 126 **by 2**, research_requests 59 **by 2**, newest signup 2026-08-28 01:33:22, last login 2026-09-19 06:26:02 (all members **and** founders-only — the same row today) | `ancient_map` |
| Id spaces on the act tables | `site_likes.user_id`, `site_bookmarks.user_id`, `token_usage_logs.user_id` are UUID FKs to `discord_users.id`; `research_requests.user_id` is a `String(255)` Discord snowflake. **Two id spaces, never joined** | `pipeline/database.py` |
| Render tooling | `package.json` has vitest 4.0.18, **no jsdom, no @testing-library/react** | file |
| Dashboard mount | `dashboardMain.tsx` uses `createRoot`, **not** `hydrateRoot` | file |
| size-limit budget | `dist/assets/landing-*.js` ≤ 12 kB brotli | `.size-limit.json` |

### 0.2 The sixteen candidates

| # | Item | Ruling | Reason / trigger |
|---|---|---|---|
| 1 | W1 `device-language` panel | **DROP** | 45 confirmed humans split over 4 device words and 8 languages gives cells of 1–3. It also contradicts Umami's own device report (linked in our header) by 3.5× forever, and it needed `/devices?exclude=<proven fingerprints>` which `useStats(path)` cannot express. **Trigger: a 7-day window with ≥ 300 confirmed-human sessions.** |
| 2 | W2 globe time-to-interactive as a problem kind | **DROP the problem kind, MERGE the numbers into the globe panel** | 8 samples from 6 browsers, two of which contributed two loads each; p75 24 758 ms is pinned by one visitor's first load. `VITAL_MIN_SAMPLES = 10` suppresses `radar · LCP` at 3 samples in the same list — two floors in one list is incoherent. The globe panel prints min / median / max **with the sample count** instead. **This kills the `slow_start` (wave 1) vs `globe_start` (wave 2) name collision outright: `ProblemKind` gains exactly one member, `webgl_lost`.** |
| 3 | W3 `scroll-depth` Reading panel | **DROP** | 12 scrolled reads total, best page type 9 against its own 10-read gate, so it ships as the sentence "No page type reached 10 scrolled reads yet" — an empty box. Its own note declares its only ratio unusable. `scroll_depth` keeps feeding `Session.depth` → `shallow_exit`; no code is removed. **Trigger: ≥ 50 scrolled reads on one page type in a 7-day window.** |
| 4 | W4 `live-now` panel | **ACCEPT**, narrow-ish (wide, 6 rows max), polled at 60 s like everything else | The only panel in the present tense. Its empty branch names the last visitor and what they had open, so it is never a blank box. 30 s polling is rejected: one cadence for the whole page. |
| 5 | W5 `exits` panel + `/exits` + `SQL_EXITS` | **DROP the panel, the endpoint and the SQL. Fold outbound clicks into `/journeys`. Drop Discord entirely.** | See BLOCKER B1 and B2 below. `outbound_click` rows already travel inside `SQL_SESSION_EVENTS` with their `host`/`page` data, so the list costs **zero** new queries. |
| 6 | W6 pulse period delta | **DROP the comparison. KEEP the deletion it was bundled with.** | `[now-14d, now-7d)` holds 0 events and will until 2026-09-24, so every tile reads `null` on merge day; and the only cheap previous-window rule (`countries(until=…)` slicing on `last_seen`) is provably biased upward — measured yesterday: 26 vs the correct 29 all-sessions, 5 vs 7–8 human, and the three dropped sessions are the three most engaged. **Trigger: `[now-14d, now-7d)` holds ≥ 100 sessions.** The deletion stays: `Pulse.delta()`, `o.today`, `o.yesterday`, `DayBlock` and both `SQL_OVERVIEW` fetches in `/overview` go, because the Today tile currently divides a human count by an all-sessions count and prints a lie. **−3 queries per refresh.** |
| 7 | W7 globe abandonment | **ACCEPT** — one `SQL_GLOBE`, one `/globe`, one `GlobeReach` panel carrying both the funnel and the times | 8 of 33 loads reach an interactive globe. Worst product number on the page. |
| 8 | W8 scraper clusters | **ACCEPT, simplified to one rule and one verdict** | Measured: **38** sessions sit inside a page load seen by ≥ 3 session ids. At ≥ 2 two innocent fingerprints join (one real visitor whose browser reports itself as both `safari` and `ios-webview`); at ≥ 3 there are exactly two groups and no false positive. Dropped from the spec: `verdict`, `reasons[]`, `pages[]` (the 40-path sample — the expensive, unbounded part), `proven_fingerprints` (it only existed to feed the dropped `/devices`), and six of the seven thresholds. |
| 9 | W9 returning visitors | **DROP** | 2 returners, one of them a founder's own browser. Salt rotates 2026-10-01. **Trigger: a calendar month with ≥ 200 confirmed-human visitors and ≥ 10 returners.** |
| 10 | W10 entry / exit pages | **ACCEPT**, folded into `/journeys`; no new endpoint, no new SQL | `Session.pages` → read-only property over a new `page_steps` field. Verified repo-wide: the only writer is `stats_analysis.py:191`. |
| 11 | W11 nginx referral-log coverage | **ACCEPT the module, ACCEPT the fold into `/sources`, REWRITE the numbers AND the counting rule** | The finding survives re-measurement, the numbers do not: **189 vs 62** on Google (not 182 vs 60, and not 153 vs 61 either — 153 was a 200-only count that no panel renders), and the real error category is 21×410, not "70 dead answers". Five measured corrections are baked into §2: scheme-less referers, our own dev server, bot split, page-request filter, and — the one the drafts kept getting wrong — **a status filter, because `BOT_UA_RE` catches none of the forged-referer scanners and without it `binance.com` renders as the #2 referring host and 21 scanner 404s render as "answers we gave referred visitors"**. |
| 12 | W12 search follow-through | **DROP** | Zero `search` events, ever. **Trigger: ≥ 50 `search` events in a 7-day window.** The `useSiteSearch.ts:360` bail-out is a real bug and is ticketed in §5, not fixed here. |
| 13 | W13 heritage matrix / "countries read about" | **DROP both** | 36 of 39 `site_open`s carry `context='site'` — the SSR page firing itself — so it measures what Google ranks. `TopContent.tsx:17` already prints `Name · Country` on every Sites row; a fifth list would be the same column re-aggregated. **Instead: shrink TopContent** — `story_open`, `paper_open` and `search` have never fired, so three of its four lists are permanently empty boxes. |
| 14 | W14 stacked 48-hour strip | **ACCEPT the fixed 48-bucket axis. REDUCE the stack to two classes.** | The axis bug is real (45 rows across a 48-hour axis, measured). The three-class colour ramp is not implementable: its hex values exist in no document, `.dash-spark rect` at specificity (0,1,1) beats any appended `.dash-spark-ai` at (0,1,0) so it would render flat green, and at 390 px a bar is 4.9 px wide and one session at the 48-hour peak is 6.1 px tall — below the size at which any colour difference survives. **Two segments: confirmed-human and everything else, in the one green the file already has, at two strengths, edited in place.** AI travels as a count in the legend and in each bar's tooltip (13 AI sessions in 7 days = at most one per hour; it could never have been a visible segment). |
| 15 | W15 members panel | **ACCEPT, all-time counts only, ORM not raw SQL, `card_collections` dropped** | 0 acts in 7 days, 40 in 30, newest signup 22 days old — any window reads zero and says nothing. Five of the six tables (`discord_users`, `token_usage_logs`, `site_likes`, `site_bookmarks`, `research_requests`) are declared in `pipeline/database.py`, so the "must be raw SQL" premise is false for all but `card_collections`, which is under `api/cardgame/models.py` and is therefore **out**. Using the ORM also removes the `:founder_role::jsonb` bind-truncation blocker by construction. |
| 16 | W16 WebGL context loss | **ACCEPT, all three defects** | Re-confirmed at HEAD: `animationLoop.ts:207` books the next frame before the guard at `:211`; `sceneInit.ts:108-112` sets `needsLabelReloadRef` and never dispatches `webgl-labels-need-reload` (only `handleVisibilityChange` at `:123-136` does); `sceneInit.ts:128` renders unguarded. One new `ProblemKind`, never a panel. |

**Net: 9 accepted (4 of them folded into existing endpoints), 7 dropped with named triggers.**

### 0.3 Every BLOCKER any critique raised, ruled by name

**B1 — Owner ruling R1 ("the Exits panel reads the funnel log for Discord") is unimplementable. OVERRULED by measurement.**
R1 rests on two claims that are false on the live box:
* `scripts/funnel_report.py` does **not** parse `/var/www/ancientnerds/logs/ancient_nerds_api.log`. It parses `docker logs --since …` output, which the api container cannot run.
* The `goto_discord` lines in that file carry **no timestamp**. Measured, verbatim: `INFO | api.routes.goto | goto_discord src=seo bot=1`. A panel with a `days` switch cannot window them.
On top of that the file is **183 MB** and grows; reading it per refresh is forbidden by rule 9, and the mount is `:ro` so the route cannot write a smaller one either.
**Ruling: no Discord panel, no Discord list, no funnel-log reader.** The 29 clicks stay readable with `python scripts/funnel_report.py --since 24h`, which is what that script is for. **Trigger to build the panel: ≥ 20 `discord_click` events in a 7-day window** — reachable only after ticket T3 (§5).

**B2 — `discord_click` has never fired; root cause confirmed and deliberately not fixed here.**
`ancient-nerds-map/index.html` is static HTML whose inline module imports only `./src/shared/disclaimerContent.ts`; `src/analytics/boot.ts` — which installs the click delegation — never runs there, and the landing page owns 10 of the 23 human clicks. The fix is one import, but `.size-limit.json` caps `dist/assets/landing-*.js` at **12 kB brotli** and `boot.ts` pulls in `web-vitals`. Raising that budget is a deliberate landing-page performance decision and needs the owner. **Ticket T3.**

**B3 — `AI_UTM_SOURCES = ("chatgpt", …)` matches 1 of 13 AI sessions.** Confirmed (re-measured 2026-09-19: `utm=chatgpt.com` 9 + `utm=chatgpt.com, ref=chatgpt.com` 2 + `utm=perplexity` 1 + `ref=gemini.google.com` 1 = 13; today's `source_family` calls exactly **one** of them `ai`). The live utm value is literally `chatgpt.com`. Ruled: `is_ai_entry()` tests **both** columns against **both** `AI_HOSTS` (substring) and a new `AI_LABELS` tuple (exact), and `source_family()` calls it first. Verified side effect: `/sources` passes its coalesced value into the referrer slot, so the bare `perplexity` row that falls to "Other" today is fixed by the same three lines — `Sources.tsx` needs no change for it.

**B4 — `pipeline/stats_cache.py` / `ttl_cached`. DROPPED — but the number the drafts used to dismiss it was wrong.** Four independent blockers were found against the module (key cannot be computed for `fetch_app`; `sorted(params)` discards values; no eviction, ~20 000 retained result lists per day; 55 s TTL under a 60 s key). **Corrected measurement (2026-09-19, best-of-3, warm pool, inside `ancient_nerds_api`):** the four `SQL_SESSION_EVENTS` scans cost 11.8–13.8 ms each, i.e. **~50 ms of the ~75 ms** this page spends in the DB once a minute. De-duplicating the three redundant 7-day scans would remove **~37 ms of ~75 ms — half the page's DB time**, not the "~22 ms of ~55 ms" the first draft claimed.
Note the fourth blocker against that module — *a 55 s TTL under a 60 s poll key can never hit* — was then re-applied verbatim to `COUNTRY_TTL` in the same draft. `useStats`' default `refreshMs` is `60_000` (`useStats.ts:10`), so a 55-second entry is always expired when the next request arrives: 0 % hit rate for one open dashboard. `COUNTRY_TTL` is **90**, and step 10c carries the arithmetic.
The ruling still stands, for a reason the corrected number makes sharper: those three scans sit in **three separate HTTP requests** (`/overview`, `/journeys`, `/problems`), so there is no "fetch it once per request" fix — removing them *requires* exactly the cross-request cache this blocker rejects. `EXPLAIN (ANALYZE, BUFFERS)` says the cost is the `data` correlated subquery (786 loops, 2 123 of 2 350 buffers, `pipeline/umami_db.py:77-85`), so it grows with **events**, not sessions. **Ruling: no cache module.** `/countries` gets `@cached(...)` from the **existing** `api/cache.py` on a private async helper (§2 step 10e). **Trigger for more: when the 7-day `SQL_SESSION_EVENTS` exceeds 100 ms under `EXPLAIN ANALYZE`** (measured today: 11.8 ms / 2 350 buffers) — and then the fix is a `@cached` shared fold of that one query, not a new module.

**B5 — Three-band collapse. DROPPED.** Its hydration justification is void (`dashboardMain.tsx` uses `createRoot`; `render.test.tsx` renders `SeoRoute` only and cannot reach `DashboardPage`). Its CSS is self-defeating: if `.dash-band-body` also carries `.dash-grid`, the author-origin `display: grid` beats the UA `[hidden]` rule at every width and nothing ever collapses; if it does not, it is a verbatim duplicate of `.dash-grid`. It would also break the only layout gate we have — `scripts/dashboard_screenshots.py:352` waits for `.dash-map-dot` with the default `state="visible"`, and VisitorMap would be inside a hidden band — and it would hide 8 of 12 panels from that gate. **Ruling: one flat `.dash-grid`. The phone length problem is solved by shipping 7 fewer features, capping `problems()` at 8 rows and gating page height.**

**B6 — `.dash-spark rect` specificity. Fixed by editing line 334 in place**, not by appending. `feedback_slider_approach.md` requires exactly this.

**B7 — `SQL_EXITS`'s `coalesce(host, src, 'unknown')` is fallback code and its `'other'` arm lands drifted events in a legitimate bucket.** Moot: `SQL_EXITS` is not created (decision 5).

**B8 — `countries(until=…)` counts "last event in the window", not "active in the window".** Moot: the `until` parameter is not added (decision 6). `countries()` keeps its current two-argument signature.

**B9 — `never_booted` mixes per-session vitals with per-load views and removes the abandoners from the denominator.** Confirmed: `web-vitals`' `onTTFB` waits for `document.readyState === 'complete'`, so a visitor who bails during a 16-second loading overlay reports no vital. **Ruling: `SQL_GLOBE` selects no vitals column and `never_booted` does not exist.** The funnel is `loads`, `reached`, `gave_up = loads − reached`.

**B10 — The `QUERIES` tuple in `tests/pipeline/test_umami_db_queries.py` must change in the same commit as `SQL_HOUR_BUCKETS`' deletion.** Correct, though the stated symptom was wrong: `QUERIES` is a module-level *string* tuple and the `getattr` runs inside the test bodies, so the failure is two failing tests, not an import-time `AttributeError`. Step 2 and step 21 are the same commit.

**B11 — "52 provably" overstates by 14.** Confirmed: 52 is the total session count of the two fingerprints; only **38** appear inside a load shared by ≥ 3 ids. The panel prints 38.

**B12 — "182 human Google arrivals" and "70 dead answers" are both wrong.** Confirmed, and the replacement number in the first draft of this plan (153) was wrong too — it was a 200-only count while `coverage_report` counted every status, so no panel ever rendered a 153. **Final, measured against the live log with the counting rule this plan actually ships (step 3): nginx answered 189 Google page arrivals (168×200 + 21×410); Umami has 62 views from 51 sessions.** Real non-200 answers: 21×410, 4×499, 1×500. Those are the numbers in the shipped comments, in the `/sources` docstring and in §5.3 — one number, one rule, everywhere.

**B12b — `coverage_report()` did not implement its own docstring.** Found by all three adversarial checks and reproduced here by running the module verbatim over the live 407-line log: the old body filtered on `v.page` and `not v.bot` only, so it printed `families: search 230 · other 48 · ai 20 · social 2`, `hosts: google.com 214, binance.com 28, …` and `statuses: 301×27, 404×21, 410×21, 403×4, 499×4, 405×2, 500×1`. **`binance.com` was the #2 referring host and 21 scanner 404s were listed under "Answers other than 200"** — the exact error the docstring claims to correct. `BOT_UA_RE` flagged **1** of 360 kept lines; the scanner sends `Mozilla/5.0 … Chrome/90.0.4430.85`. **Ruling: `coverage_report` filters on status, not on UA.** With the rule in step 3 the same log yields `families: search 203 · ai 20 (1 bot) · other 17 · social 1`, `hosts: google.com 189, chatgpt.com 18, duckduckgo.com 7, bing.com 4, …` and `statuses: 410×21, 499×4, 500×1`. `binance.com` disappears completely.

**B13 — Scheme-less referers drop 55 of 407 log lines (13.5 %).** Accepted; `referrer_host()` parses both shapes. **The rest of B13's sentence was wrong and is corrected:** those 55 are 27 `www.google.com` and 28 `binance.com`, and **none of the 27 is a genuine arrival** — every one is a `.php` or `//images/.../cache.php` probe from a single forged `Mozlila/5.0 ... Moblie Safari` UA that `is_page()` drops on the extension. They must still be parsed, because `coverage_report`'s status filter is what rejects them and an unparsed line cannot be rejected. This is a bigger bug than the utm-without-a-dot one the wave-2 contract called "live bug #1", and it is fixed in the same function.

**B14 — `localhost:5199` is 11.5 % of the log and would become the #2 family.** Accepted; `OWN_HOSTS` is filtered out and the module docstring says why. **Corrected claim:** filtering `OWN_HOSTS` alone does *not* keep `other` out of second place — measured, it left `other` at 48 (21 of them the binance scanner, 2 our own Discord bot's `utm_source=discord`, the rest SEO link farms). It is B12b's status filter that fixes that: `other` drops to **17** and lands third, behind `search` 203 and `ai` 20. Both filters are required; neither is sufficient.

**B15 — a 410 emits no `not_found` event by design.** Confirmed at `pipeline/article_html_renderer.py`: `feedback = _NOT_FOUND_FEEDBACK if code == 404 else ""`, and the `not_found` track call lives inside that block. So `broken_link` is structurally blind to the only real error category we have (21×410). Not fixed here — it changes a public page's behaviour. **Ticket T1.**

**B16 — Components are untestable today (owner ruling R7). Ruling upheld, justification corrected.** The claim "components cannot be rendered in a test today" is **false**: `src/seo/__tests__/render.test.tsx` already renders ten page types with `renderToString` under plain Node, with no jsdom and no new dependency, and the same technique would reach every empty-state branch of the new panels at zero cost. **The ruling stands on the other half of the argument, which is the load-bearing half: `renderToString` produces a string, and the defect this page actually has is layout at 390 px — height, overflow, line clamps, flag boxes. No string renderer measures that, and jsdom does not either (no layout engine).** So: **do not add jsdom or @testing-library/react** — three dev dependencies plus a vitest environment change touching every existing test file, for a renderer that cannot see the failure mode. **Instead: every new component exports its pure shaping function (vitest), and every production state including all the empty ones gets a fixture in `scripts/dashboard_screenshots.py`, which grows a second, empty-state mobile pass with the same overflow and height assertions.** That script is **not** in CI today (see T9); it is a local gate the implementer must run, and calling it "the gate" without that sentence would be dishonest.

**B17 — `MembersData` was declared as an empty interface; `SourcesData` was specified two incompatible ways; `ExitPage` was declared twice with different shapes.** All three are written out once, in §2 step 13.

**B18 — `pipeline/lyra/analytics_alerts.py` is the second caller of `problems()` and was in neither contract's file list.** Included: step 11.

**B19 — `useStats` polls forever in background tabs with no jitter.** Real, out of scope, **ticket T4**.

**B20 — the aligned trailing comments in wave 1 §3 fail `ruff format --check`.** Accepted: every constant in this plan is documented with a `#:` block above it, which is the module's own convention. **Two places in this plan itself were not format-clean and are now written pre-formatted** (verified with the pinned ruff 0.15.11, `line-length = 100`): `hourly_sessions`' bucket dict comprehension fits on one line (94 chars) and must not be split, and `without_brand`'s docstring needs a space after the opening `"""` because its first character is a quote — the module already uses the spaced form at `pipeline/stats_analysis.py:268`. Everything else in §2 was run through `ruff format --check` and is clean.

**B21 — the wave plan shipped a crashing dashboard to production. Found by the scope check; confirmed at HEAD.** `ancient-nerds-map/src/components/dashboard/Pulse.tsx:95` is `const d = o ? delta(o.today.sessions, o.yesterday.sessions) : null`, and `src/dashboardMain.tsx` mounts with a bare `createRoot` and **no error boundary**. Step 10d removes `today`/`yesterday` from `/overview`. Every push to `main` deploys (CLAUDE.md). So a wave-0 commit on `main` would leave the deployed `Pulse` reading `undefined.sessions`, throwing during render and unmounting the whole root — a blank founders dashboard from the wave-0 deploy until wave 5. **Ruling: steps 1–38 land on ONE feature branch and reach `main` as ONE merge, i.e. one deploy.** §3.2 says so in the wave table now, and it is the single hardest constraint in this plan.

## 1. Final state

### 1.1 Endpoints — `/api/stats/*`, twelve of them

All `async def`, all behind `Depends(require_stats_session)`. `days` is `Query(7, ge=1, le=90)` unless stated.

| Route fn | Path | Response keys | Queries |
|---|---|---|---|
| `overview` | `/overview?days=N` | `days`, `sessions{all,human,ai}`, `types`, `hours[48]{hour,sessions,human,ai}` | 1 |
| `visitor_countries` | `/countries` | `now`, `today`, `d7`, `d30` — each `{sessions,all,countries[]}` | 1 (cached 90 s) |
| `visitor_map` | `/map?days=N` *(1..30, default 1)* | `points` | 1 |
| `live` | `/live` *(no params)* | `window_minutes`, `lookback_hours`, `total`, `shown`, `visitors[]`, `last` | 1 |
| `globe` | `/globe?days=N` | `loads`, `reached`, `gave_up`, `sessions{all,reached}`, `ready_ms{min,median,max,samples}` | 1 |
| `clusters` | `/clusters?days=N` | `min_ids`, `flagged`, `clusters[]{screen,browser,os,sessions}` | 1 |
| `content` | `/content?days=N` | `sites`, `stories`, `papers`, `searches` — unchanged | 1 |
| `journeys` | `/journeys?days=N` | `chains`, `pages{sessions,one_page,moving,entries[],exits[]}`, `outbound[]` | 1 |
| `problems` | `/problems?days=N` | `problems[]` — 6 kinds | 6 |
| `feedback` | `/feedback?days=N` *(1..365, default 30 — unchanged)* | `items` | 1 |
| `sources` | `/sources?days=N` | `sources[]{source,family,sessions,views}`, `log`, `log_reason` | 1 + one `os.stat()` |
| `members` | `/members` *(no params)* | `members`, `founders`, `newest_signup`, `last_login` *(founders only)*, `acts[]{act,n,by,at}` | 1 (application DB) |

Not built: `/returning`, `/assistants`, `/heritage`, `/pages`, `/exits`, `/outbound`, `/devices`.

### 1.2 Panels — mount order, which is also phone reading order

| # | Panel | Width | Endpoint(s) | Question |
|---|---|---|---|---|
| 1 | `Pulse` | wide | `/overview` + `/countries` | Who is here right now? |
| 2 | `LiveNow` | wide | `/live` | What are they looking at right now? |
| 3 | `GlobeReach` | narrow | `/globe` | Does the globe actually come up? |
| 4 | `Scrapers` | narrow | `/clusters` + `/overview` | How many of those sessions are one machine? |
| 5 | `Problems` | wide | `/problems` | Where does the platform fail them? |
| 6 | `VisitorMap` | wide | `/map` | Where are the visitors? |
| 7 | `Sources` | wide | `/sources` | Where do they come from, and how many do we miss? |
| 8 | `SessionTypes` | narrow | `/overview` | What do visitors do? |
| 9 | `Members` | narrow | `/members` | Who signed up, and did they come back? |
| 10 | `Paths` (was `Journeys`) | wide | `/journeys` | How do they move through the site, and where do they leave? |
| 11 | `TopContent` | wide | `/content` | What gets opened, what gets searched? |
| 12 | `FeedbackInbox` | wide | `/feedback` | What do visitors say? |

8 wide + two complete narrow pairs (3+4, 8+9) = **zero half-empty desktop cells**, and both pairs are
height-balanced (~240/~220 and ~336/~300 CSS px at 390 px).

### 1.3 Per-refresh cost

**17 queries in the set** (12 endpoints; `/problems` is 6, everything else 1 → 11 + 6 = 17). `/members`
and `/clusters` poll at 300 s, so the steady state is **15 per 60 s plus 2 per 300 s**. Today's code
also runs **15 per 60 s** (`/overview` alone is 4: two `SQL_OVERVIEW` blocks, `SQL_SESSION_EVENTS`,
`SQL_HOUR_BUCKETS`) — **this plan is not a query-count reduction, it is a query-count wash that buys
five more panels.** Say that in the commit body; do not sell it as a saving.

Measured 2026-09-19, best of 3, warm pool, from inside `ancient_nerds_api`:

| Query | ms | rows |
|---|---|---|
| `SQL_SESSION_EVENTS` 7 d (×4: overview, countries, journeys, problems) | 11.8–13.8 each | 794 |
| `SQL_VITALS` | 4.1 | 52 |
| `SQL_CLUSTERS` | 3.1 | 2 |
| `SQL_CONTENT` (×2: content, problems) | 2.8 each | 30 |
| `SQL_LIVE` | 2.3 | 60 |
| `SQL_GLOBE` | 1.7 | 20 |
| `SQL_MAP` | 1.7 | 130 |
| `SQL_NOT_FOUND` · `SQL_FEEDBACK` · `SQL_ERRORS` · `SQL_SOURCES` · `SQL_WEBGL_LOST` | 1.0–1.5 each | ≤ 9 |
| **16 Umami queries, total** | **≈ 75 ms** | |
| `/members` (application DB, every 300 s) | ≤ 26 ms first call, < 1 ms warm | 1 |

So **≈ 75 ms of DB time per refresh, ≈ 72 ms in the 60 s steady state** — and **~50 ms of it is the
four `SQL_SESSION_EVENTS` scans** (see B4). The 30-day `/countries` scan costs the *same* 10–13 ms as
the 7-day one today, because the tracker holds two days of data and both return 794 rows; the
"month-scale query" premise only becomes true around 2026-10-17.

**Two API containers behind the nginx upstream do NOT double the query count.**
`/etc/nginx/sites-available/ancientnerds.com` declares `upstream an_api { server 127.0.0.1:8000;
server 127.0.0.1:8001; }` — plain round-robin — so one dashboard tab's 12 requests a minute are split
across the two containers and the database still sees 15 queries per 60 s in total. What *is*
duplicated is per-process state: `referral_log._cache` is a module global, so each container parses
the log on its own; `/countries` is shared because `api/cache.py` reaches Redis.

Forbidden shapes, and how each is prevented: a month of events per panel — only `/countries` reaches
30 days, it slices four windows from one fetch, and it is cached; a log re-parse per refresh —
`read_visits()` parses only when `(mtime_ns, size)` changed **and** ≥ 55 s have passed, capped at
`MAX_TAIL_BYTES`; a second globe query — there is one; a second session scan for the strip — the
strip folds from `/overview`'s existing rows.

## 2. File-by-file instructions, in dependency order

Each step is one commit unless it says otherwise. Every file has exactly one OWNER.

---

### Step 1 — `pipeline/umami_db.py` · OWNER: BACKEND

**1a. Module docstring.** Replace the column list sentence:

before
```
``session``
(session_id, country, city, device, browser). event_type 1 = pageview,
```
after
```
``session``
(session_id, country, city, device, browser, screen, os). event_type 1 = pageview,
```

**1b. DELETE `SQL_HOUR_BUCKETS` entirely** (lines 69-75). Verified repo-wide: its only consumers
are `api/routes/founders_stats.py:23,68` and the `QUERIES` tuple in
`tests/pipeline/test_umami_db_queries.py:23`. `pipeline/lyra/analytics_alerts.py` does not import it.
Steps 1, 10 and 21 are **one commit**.

**1c. `SQL_SOURCES` — add the `views` column.** Replace the constant with:

```python
SQL_SOURCES = """
SELECT coalesce(nullif(utm_source, ''), nullif(referrer_domain, ''), 'direct') AS source,
       count(DISTINCT session_id) AS sessions,
       -- Page views as well as sessions, so the panel can put Umami's number
       -- next to nginx's, which counts requests. Measured 2026-09-19 over the
       -- same window: nginx answered 189 Google page arrivals (168 with a 200,
       -- 21 with a 410) while Umami recorded 62 views from 51 sessions. The
       -- gap is the panel's whole point.
       count(*) AS views
FROM website_event
WHERE website_id = :website_id AND event_type = 1
  AND created_at >= :since AND created_at < :until
GROUP BY 1 ORDER BY 2 DESC LIMIT 40
"""
```

**1d. Append after `SQL_ERRORS`** (before `def fetch`):

```python
#: The one path that hosts the globe. Verified 2026-09-19: exactly one
#: url_path contains "globe", all eight globe_ready events ever recorded fired
#: there, and no url_path carries a query string, so equality is exact.
GLOBE_PATH = "/globe.html"

#: How often the globe actually comes up, and how long it took when it did.
#: One row per session:
#:   views    - page views, one per document load. App.tsx never calls
#:              pushState (only AccountPage and ArticlesPage do), so Umami
#:              cannot manufacture a virtual view here and views and
#:              globe_ready are the same granularity.
#:   ready    - globe_ready, fired once per load from onLayersReady.
#:   ready_ms - the milliseconds each globe_ready carried, so the funnel and
#:              the times come from ONE scan.
#: The LEFT JOIN is load-bearing: a page view has no event_data row.
#: There is deliberately no "did the bundle boot" column. web-vitals' onTTFB
#: waits for document.readyState === 'complete', so a visitor who leaves
#: during a sixteen-second loading overlay reports no vital at all - counting
#: those loads out of the denominator would remove exactly the abandoners
#: this query exists to find (measured 2026-09-19: 6 of 33 loads).
#: globe_idle is not read either: markGlobeActivity() is called from three
#: places only, so a camera drag leaves the timer armed. Both live globe_idle
#: events carry the literal ms=30000 and both belong to a visitor who was
#: toggling a country filter at that moment. Precision 0/2.
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
       coalesce(
           array_remove(
               array_agg(ms ORDER BY created_at) FILTER (WHERE event_name = 'globe_ready'),
               NULL),
           ARRAY[]::float8[]) AS ready_ms
FROM ev
GROUP BY session_id
"""

#: How many session ids have to share one path-minute before it is a machine
#: rather than a coincidence. Verified on production 2026-09-19: at three
#: there are exactly two fingerprints and no false positive; at two the result
#: is six rows and 52 sessions, because one real visitor whose browser reports
#: itself as both "safari" and "ios-webview" and one Android phone counted
#: under two operating system strings each split into two rows.
CLUSTER_MIN_IDS = 3

#: Cookieless analytics gives every request a fresh session id when the
#: client keeps no state. A headless fetcher that touches one path with three
#: ids inside the same clock minute is therefore visible as exactly that: one
#: path, one minute, several ids. Measured 2026-09-19 over seven days: 38 of
#: 163 sessions sit inside such a group, in two fingerprints - 1366x1366
#: chrome Mac OS (22) and 1280x1200 chrome Windows 10 (16). Every other
#: fingerprint peaks at one id.
#: The grouping is over EVERY event, not over page views, and that is
#: load-bearing, not an oversight: these clients fire events without ever
#: sending a page view (34 of the 163 sessions have zero page views, all of
#: them inside these two fingerprints). Adding `AND event_type = 1` was
#: proposed and measured on 2026-09-19: the maximum number of ids on one page
#: view in one minute is 2, so the query then returns ZERO rows at this
#: threshold and the detection disappears entirely. Do not add it.
#: Deliberately no path sample and no per-cluster heuristics: the output is
#: bounded to twenty fingerprint rows, and the 40-path array the first draft
#: carried was the only unbounded part of the query.
SQL_CLUSTERS = """
WITH path_minutes AS (
    SELECT url_path, date_trunc('minute', created_at) AS minute,
           array_agg(DISTINCT session_id) AS ids
    FROM website_event
    WHERE website_id = :website_id
      AND created_at >= :since AND created_at < :until
    GROUP BY 1, 2
    HAVING count(DISTINCT session_id) >= :min_ids
),
shared AS (
    SELECT DISTINCT unnest(ids) AS session_id FROM path_minutes
)
SELECT s.screen, s.browser, s.os, count(*) AS sessions
FROM shared
JOIN session s ON s.session_id = shared.session_id
GROUP BY 1, 2, 3
ORDER BY sessions DESC
LIMIT 20
"""

#: A globe that lost its WebGL context. src/components/Globe.tsx sends this
#: once per page view with `reason` (why the loop stopped) and `phase`
#: ("loading" before onLayersReady, "live" after), so the panel can say
#: whether the visitor ever saw a globe at all.
SQL_WEBGL_LOST = (
    """
WITH ev AS (
    SELECT
        e.event_id,
        e.session_id, e.created_at, s.country, s.device, s.browser,
        max(d.string_value) FILTER (WHERE d.data_key = 'reason') AS reason,
        max(d.string_value) FILTER (WHERE d.data_key = 'phase')  AS phase
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    JOIN session s ON s.session_id = e.session_id
    WHERE e.website_id = :website_id AND e.event_name = 'webgl_lost'
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, s.country, s.device, s.browser
)
SELECT phase, reason, count(*) AS n, count(DISTINCT session_id) AS sessions,
"""
    + _LAST_VISITOR
    + """
FROM ev
WHERE phase IS NOT NULL AND reason IS NOT NULL
GROUP BY 1, 2
ORDER BY sessions DESC, n DESC
LIMIT 20
"""
)

#: What each visitor who is still here has open. One row per session: last
#: sign of life, the last page view of that session, and that page's <title>.
#: `page_title` is a plain column on website_event, filled on every page view
#: measured (2026-09-19) - a headline beats a 139-character slug and costs no
#: event_data join. The LATERAL is INNER on purpose: ten of sixty-nine
#: sessions in a day fire only `vital`/`js_error` and never a page view. They
#: have no page to name, so they have no row - the panel says so rather than
#: inventing one. The window is the 24-hour lookback; Python cuts the live
#: half out of it, so "who is here" and "who was here last" cost one query.
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

Three shape notes that must not be "simplified": `ARRAY[]::float8[]` (not `'{}'`, which trips
`assert "{" not in sql`); `LATERAL` contains no consecutive `A-L-T-E-R`, so `test_queries_only_read`
passes; `SQL_CLUSTERS` uses `[1:40]`-free syntax so nothing is mistaken for a bind parameter.

---

### Step 2 — `tests/pipeline/test_umami_db_queries.py` · OWNER: TESTS *(same commit as step 1)*

**2a.** `QUERIES` becomes:

```python
QUERIES = (
    "overview",
    "map",
    "session_events",
    "content",
    "feedback",
    "sources",
    "not_found",
    "vitals",
    "errors",
    "globe",
    "clusters",
    "webgl_lost",
    "live",
)
```

**2b.** In `test_problem_queries_read_the_events_the_frontend_actually_sends`, extend the
last-visitor loop and add the new assertions at the end of the function:

before
```python
    for name in ("SQL_ERRORS", "SQL_NOT_FOUND", "SQL_VITALS", "SQL_CONTENT"):
```
after
```python
    for name in ("SQL_ERRORS", "SQL_NOT_FOUND", "SQL_VITALS", "SQL_CONTENT", "SQL_WEBGL_LOST"):
```

append inside the same function
```python
    # The globe funnel and its times come from one scan, and it never asks
    # whether a Core Web Vital arrived (see the constant's own comment).
    assert "'globe_ready'" in u.SQL_GLOBE and ":path" in u.SQL_GLOBE
    assert "'vital'" not in u.SQL_GLOBE
    # The cluster rule is one rule: a page load several session ids share.
    assert ":min_ids" in u.SQL_CLUSTERS and "date_trunc('minute'" in u.SQL_CLUSTERS
    assert "'webgl_lost'" in u.SQL_WEBGL_LOST
    for key in ("'reason'", "'phase'"):
        assert key in u.SQL_WEBGL_LOST, key
    # The live list names the page, which is a plain column, not event_data.
    assert "page_title" in u.SQL_LIVE
```

**2c.** New test in the same file:

```python
def test_the_hour_bucket_query_is_gone():
    """The strip folds its 48 fixed buckets out of the session rows /overview
    already fetches. SQL_HOUR_BUCKETS returned one row per hour that had
    events - 45 for a 48-hour window on 2026-09-19 - and every gap shifted
    the bars left of it."""
    assert not hasattr(u, "SQL_HOUR_BUCKETS")
```

---

### Step 3 — `pipeline/referral_log.py` (new) · OWNER: BACKEND

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""nginx's referral log: who sends people here, and what we answered them.

nginx writes one JSON line per request that arrives with a referer from
another host or with a utm_source (log_format ``referral``) to
/var/www/ancientnerds/logs/referrals.log, which docker-compose binds into the
API containers read-only at /app/logs:

    {"t":"2026-09-17T12:00:00+02:00","ref":"https://chatgpt.com/",
     "req":"GET /sites/egypt","status":200,"ua":"Mozilla/5.0 ..."}

This is the only view we have of two things Umami cannot see: arrivals whose
tracker never ran, and the status code we served. Measured 2026-09-19 over
407 lines: nginx answered 189 Google page arrivals while Umami recorded 62
views from 51 sessions, and 21 of those 189 were a 410 for a retracted story
- an answer no event reports, because the 410 page raises none
(pipeline/article_html_renderer.py, render_error_html).

Five things the parser has to get right, each of them measured:

* ``$time_iso8601`` is VPS local time (+02:00 now, +01:00 after October).
  ``datetime.fromisoformat`` handles the offset; ``strptime`` without it or
  any string slicing is a silent two-hour window shift.
* Browsers do not all send a scheme. 55 of 407 lines carried a bare
  ``www.google.com`` or ``binance.com``, for which ``urlsplit(...).hostname``
  is None. Those lines have to be parsed to be *rejected* on their status:
  unparsed they are invisible, parsed and unfiltered they are the whole
  error list.
* A utm_source need not contain a dot: Perplexity tags its links
  ``utm_source=perplexity`` and our own Discord bot tags them
  ``utm_source=discord``. UTM_ALIASES maps every bare label we emit or
  receive onto a host, so family_of() can see it.
* 47 of 407 lines (11.5 %) come from ``http://localhost:5199/`` - a founder's
  own Vite dev server calling production. Left in, it is us looking at
  ourselves.
* A user agent cannot separate a scanner from a visitor here. BOT_UA_RE
  flagged 1 of 360 kept lines; the busiest scanner forges a plain
  ``Mozilla/5.0 ... Chrome/90.0.4430.85`` and probes /wp-admin/,
  /.well-known/ and /uploads/, none of which has a file extension, so
  is_page() says yes to all of them. The **status code** is what separates
  them: measured over the live log, every single 404 and 403 is a forged
  referer, and no scanner request was ever answered with a 200 or a 410.
  That is why coverage_report() counts arrivals by status and not by UA.

Read-only. Nothing here writes into /app/logs.

The CLI on top of this module is scripts/referral_report.py.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

#: Where the log is mounted inside the API container (docker-compose.yml binds
#: ./logs:/app/logs:ro on the api service anchor, which api2 inherits). The
#: environment variable exists so the CLI and the tests can point elsewhere.
LOG_PATH = Path(os.getenv("REFERRAL_LOG_PATH", "/app/logs/referrals.log"))

#: How much of the tail is ever read. Measured inside ancient_nerds_api on
#: 2026-09-19: 408 lines / 110 KB parse in 8.6 ms, i.e. 21 us per line and
#: ~80 ms per megabyte. The log grows ~56 KB a day at today's rate, so one
#: megabyte is about 19 days of history and costs about 80 ms to parse.
#: That parse blocks the event loop of whichever API container serves
#: /sources, once per CACHE_MIN_SECONDS, so the ceiling is a deliberate
#: trade and not a round number: 19 days comfortably covers the panel's
#: 7-day default, and the response carries covered_days so a founder asking
#: for 30 or 90 days can see how far back the log actually reaches. Ticket
#: T10 moves the parse onto asyncio.to_thread when this stops being enough.
MAX_TAIL_BYTES = 1024 * 1024

#: The parse is skipped unless the file changed AND this long has passed. The
#: file identity alone is not enough: at ten times today's traffic a new line
#: arrives every 43 seconds, which is shorter than the dashboard's refresh, so
#: every refresh would re-parse.
CACHE_MIN_SECONDS = 55.0

#: Our own machines. A localhost referer is the founder's dev server, not a
#: referral.
OWN_HOSTS = ("localhost", "127.0.0.1")

#: UA substrings that mark automated clients. Deliberately broad: the point is
#: separating "a person arrived" from "a crawler followed a link", not perfect
#: bot taxonomy. Misclassified stragglers land in the bot bucket, which only
#: makes the human count conservative. The Discord funnel redirect
#: (api/routes/goto.py) imports this - one definition in the repo.
BOT_UA_RE = re.compile(
    r"bot|crawl|spider|slurp|scrapy|curl|wget|python-requests|python-httpx|aiohttp"
    r"|headless|phantom|lighthouse|facebookexternalhit|whatsapp|telegram|preview"
    r"|go-http-client|okhttp|java/|libwww",
    re.IGNORECASE,
)

#: Referrer host families, first match wins. Hosts match as the host itself or
#: any subdomain of it.
FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ai",
        re.compile(
            r"(^|\.)(chatgpt\.com|openai\.com|perplexity\.ai|copilot\.microsoft\.com"
            r"|gemini\.google\.com|claude\.ai|you\.com|mistral\.ai|chat\.deepseek\.com"
            r"|phind\.com|grok\.com|meta\.ai)$"
        ),
    ),
    (
        "search",
        re.compile(
            r"(^|\.)(google\.[a-z.]+|bing\.com|duckduckgo\.com|yandex\.[a-z]+|ecosia\.org"
            r"|baidu\.com|search\.brave\.com|qwant\.com|startpage\.com|yahoo\.com|kagi\.com)$"
        ),
    ),
    (
        "social",
        re.compile(
            r"(^|\.)(discord\.com|discordapp\.com|reddit\.com|x\.com|twitter\.com|t\.co"
            r"|facebook\.com|instagram\.com|youtube\.com|linkedin\.com|threads\.net"
            r"|mastodon\.[a-z]+|bsky\.app|tiktok\.com|pinterest\.[a-z.]+)$"
        ),
    ),
)

#: A bare utm label that names a source without naming a host. Every value
#: live in the log on 2026-09-19 is covered: chatgpt.com (19 lines, already a
#: host), discord (2 - our own bot's links, which without the alias render as
#: a "host" literally called discord in the "other" family) and perplexity
#: (1). reddit and youtube are listed because the bot can post there too.
UTM_ALIASES = {
    "perplexity": "perplexity.ai",
    "chatgpt": "chatgpt.com",
    "openai": "openai.com",
    "discord": "discord.com",
    "reddit": "reddit.com",
    "youtube": "youtube.com",
}

#: Request paths that are not page views even with a foreign referer.
_NON_PAGE_PREFIX = ("/api/", "/assets/", "/data/", "/fonts/", "/landing/", "/goto/")
_NON_PAGE_SUFFIX = re.compile(r"\.(?!html$)[a-z0-9]{1,5}$", re.IGNORECASE)

#: A Referer header logged without a scheme: "www.google.com" or
#: "binance.com/x". Anchored, so a full URL never reaches this branch.
_BARE_HOST = re.compile(r"^[a-z0-9.-]+(?::\d+)?(?:/|$)", re.IGNORECASE)

#: How many host rows the coverage block hands to the panel. The families and
#: the statuses are never truncated - there are four of one and three of the
#: other.
REPORT_ROWS = 8

#: A status that means "nginx handed this visitor a page". 200 is the good
#: case; 410 is a story we withdrew on purpose, which is still an arrival and
#: is the single biggest thing Umami cannot see. Everything else is counted
#: out of `families` and `hosts`: a 3xx is a redirect on its way to its own
#: 200 (19 of the live 27 are the legacy /site.html rule) and counting both
#: would count one visitor twice, and a 4xx is a forged referer - measured
#: 2026-09-19, all 50 of the live 404s and all 4 of the 403s are, and a real
#: 404 raises a not_found event that the Problems panel already ranks.
ARRIVAL_STATUSES = frozenset({200, 410})


def is_bad_answer(status: int) -> bool:
    """An answer a founder has to know about, and that nothing else on the
    dashboard can see. 410 (a retracted story Google still links to, 21 live),
    499 (the visitor closed the tab before we finished, 4 live) and every 5xx
    (1 live). Deliberately not 404: see ARRIVAL_STATUSES."""
    return status in (410, 499) or status >= 500


def family_of(host: str) -> str:
    for name, pattern in FAMILIES:
        if pattern.search(host):
            return name
    return "other"


def referrer_host(ref: str, req: str) -> str:
    """The referring host: lower case, no scheme, no port, no ``www.``.

    Two legal shapes for one field, both live: a full URL and a bare host.
    When there is no referer at all, a utm_source on the request names the
    source instead - ChatGPT tags its outbound links and sends no referer.
    """
    host = urlsplit(ref).hostname or ""
    if not host and _BARE_HOST.match(ref):
        host = ref.split("/", 1)[0]
    if not host:
        query = urlsplit(req.split(" ", 1)[-1]).query
        utm = parse_qs(query).get("utm_source", [""])[0].lower()
        host = UTM_ALIASES.get(utm, utm)
    return host.lower().split(":", 1)[0].removeprefix("www.")


def is_page(req: str) -> bool:
    path = urlsplit(req.split(" ", 1)[-1]).path
    if path.startswith(_NON_PAGE_PREFIX):
        return False
    return not _NON_PAGE_SUFFIX.search(path)


@dataclass(frozen=True, slots=True)
class Visit:
    at: datetime
    host: str
    family: str
    status: int
    bot: bool
    page: bool


def parse_lines(lines: Iterable[str]) -> list[Visit]:
    """Every line the log can answer for. A line without a JSON object, with
    broken JSON or without an attributable host is skipped - the tail is read
    from a byte offset, so the first line is regularly half a line."""
    out: list[Visit] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        host = referrer_host(entry.get("ref", ""), entry["req"])
        if not host or host in OWN_HOSTS:
            continue
        out.append(
            Visit(
                at=datetime.fromisoformat(entry["t"]),
                host=host,
                family=family_of(host),
                status=int(entry["status"]),
                bot=bool(BOT_UA_RE.search(entry.get("ua", ""))),
                page=is_page(entry["req"]),
            )
        )
    return out


_cache: tuple[tuple[int, int], float, list[Visit]] | None = None


def read_visits() -> list[Visit] | None:
    """The log's tail, parsed. None when the file is not there - every dev box.

    Re-parsed only when the file changed and at least CACHE_MIN_SECONDS have
    passed since the last parse, so a busy log cannot turn the dashboard's
    once-a-minute refresh into a once-a-minute file read.
    """
    global _cache
    try:
        stat = LOG_PATH.stat()
    except OSError:
        return None
    identity = (stat.st_mtime_ns, stat.st_size)
    now = time.monotonic()
    if _cache is not None and (_cache[0] == identity or now - _cache[1] < CACHE_MIN_SECONDS):
        return _cache[2]
    with LOG_PATH.open("rb") as fh:
        if stat.st_size > MAX_TAIL_BYTES:
            fh.seek(stat.st_size - MAX_TAIL_BYTES)
        blob = fh.read()
    visits = parse_lines(blob.decode("utf-8", "replace").splitlines())
    _cache = (identity, now, visits)
    return visits


def unavailable_reason() -> str:
    """Why the coverage block is empty, in one English sentence for the panel."""
    return (
        f"nginx's referral log is not readable at {LOG_PATH}. "
        "It is bind-mounted read-only into the API containers on the VPS "
        "(docker-compose.yml, ./logs:/app/logs:ro); a development box has none."
    )


def aggregate(
    visits: Iterable[Visit], since: datetime, pages_only: bool = True
) -> dict[str, dict[str, Counter]]:
    """{family: {host: Counter(human=..., bot=...)}} - the CLI's table.

    Scanners send fake referers to paths that do not exist (/wp-admin/ from
    "binance.com"): a page view needs a page, so errors only count with --all.
    """
    result: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for v in visits:
        if v.at < since:
            continue
        if pages_only and (v.status >= 400 or not v.page):
            continue
        result[v.family][v.host]["bot" if v.bot else "human"] += 1
    return result


def coverage_report(visits: Iterable[Visit], since: datetime, until: datetime) -> dict[str, Any]:
    """What nginx saw in the same window the panel is showing.

    An arrival is a page request from a non-bot UA that we answered with an
    ARRIVAL_STATUS. Both halves of that rule are load-bearing and both were
    measured on 2026-09-19 by running this module over the live 407-line log:

    * Without the status filter, `binance.com` is the second-largest host
      (28 visits), "other" is the second-largest family (48), and the status
      list reads 301x27, 404x21, 410x21, 403x4, 499x4, 405x2, 500x1 - i.e.
      21 scanner probes printed as "answers we gave referred visitors" and a
      redirect that works as designed printed as the biggest problem. That
      was the single biggest error in the drafts this plan replaces.
    * With it: families search 203 / ai 20 / other 17 / social 1, hosts
      google.com 189, chatgpt.com 18, duckduckgo.com 7, bing.com 4, and
      statuses 410x21, 499x4, 500x1. binance.com disappears entirely.

    The UA test cannot do this job - it caught 1 of 360 kept lines - so it
    only ever moves a visit into `bots`, never out of the error list.
    """
    window = [v for v in visits if since <= v.at < until]
    pages = [v for v in window if v.page]
    families: Counter[str] = Counter()
    bots: Counter[str] = Counter()
    hosts: Counter[str] = Counter()
    statuses: Counter[int] = Counter()
    for v in pages:
        if v.bot:
            bots[v.family] += 1
            continue
        if v.status in ARRIVAL_STATUSES:
            families[v.family] += 1
            hosts[v.host] += 1
        if is_bad_answer(v.status):
            statuses[v.status] += 1
    first = min((v.at for v in window), default=until)
    return {
        "covered_from": first.astimezone(UTC).isoformat(),
        "covered_days": round((until - first) / timedelta(days=1), 2),
        "lines": len(window),
        "families": [
            {"family": f, "visits": n, "bots": bots.get(f, 0)}
            for f, n in sorted(families.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "hosts": [
            {"host": h, "visits": n}
            for h, n in sorted(hosts.items(), key=lambda kv: (-kv[1], kv[0]))[:REPORT_ROWS]
        ],
        "statuses": [
            {"status": s, "visits": n}
            for s, n in sorted(statuses.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }
```

---

### Step 4 — `api/routes/goto.py` · OWNER: BACKEND *(same commit as step 3)*

before
```python
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from pipeline.article_html_renderer import DISCORD_INVITE_URL
```
after
```python
import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from pipeline.article_html_renderer import DISCORD_INVITE_URL
from pipeline.referral_log import BOT_UA_RE
```

and **delete** the whole `BOT_UA_RE` block (its `#:` comment and the `re.compile(...)`, lines 36-45).
`import re` becomes unused and `ruff check` (F401 is ignored, but `vulture` and review will catch it)
— remove it, as shown above.

---

### Step 5 — `pyproject.toml` · OWNER: BACKEND *(same commit as step 3)*

Append inside the `api may only use sanctioned pipeline module families` `ignore_imports` list, after
the `pipeline.umami_db` entry:

```toml
    # nginx's referral log. The /sources coverage block and the Discord funnel
    # redirect share one BOT_UA_RE; stdlib only, under pipeline/ because the
    # Lyra image ships no api/ tree (2026-09-19).
    "api.** -> pipeline.referral_log",
    # All-time member counts off our own database for the dashboard's members
    # panel; under pipeline/ for the same reason (2026-09-19).
    "api.** -> pipeline.members_stats",
```

---

### Step 6 — `scripts/referral_report.py` · OWNER: BACKEND *(same commit as step 3)*

Becomes a thin CLI. **Delete** `FAMILIES`, `family_of`, `source_host`, `is_page`, `aggregate`,
`_NON_PAGE_PREFIX`, `_NON_PAGE_SUFFIX` and the `from api.routes.goto import BOT_UA_RE` import.
**Keep `LOG_PATH`** — `read_log()` passes it to `ssh … cat`, and it is the VPS path, not the
container mount, so it is deliberately not `referral_log.LOG_PATH`. Keep `parse_since`,
`print_report`, `read_log`, `main`.

**Also delete these five now-unused imports**, or `ruff check scripts/` (and review) fails:
`json`, `defaultdict`, `Iterable`, `urlsplit`, `parse_qs`. Keep `re` (`parse_since`), `Counter`
(`print_report`'s annotation), `argparse`, `subprocess`, `sys`, `Path`, `UTC`, `datetime`,
`timedelta`. The import block becomes:

```python
# Run from anywhere: the repo root must be importable for pipeline.referral_log.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.referral_log import aggregate, parse_lines  # noqa: E402

LOG_PATH = "/var/www/ancientnerds/logs/referrals.log"
SSH_HOST = "ancientnerds"
```

and `main`'s last line becomes:

```python
    print_report(aggregate(parse_lines(lines), since, pages_only=not args.all), since)
```

---

### Step 7 — `scripts/funnel_report.py` · OWNER: BACKEND *(same commit as step 3)*

One docstring line, so it does not point at a deleted symbol.

before
```
time (known bot substrings, see BOT_UA_RE in goto.py) — nothing else is
```
after
```
time (known bot substrings, see BOT_UA_RE in pipeline/referral_log.py) —
nothing else is
```

---

### Step 8 — `pipeline/members_stats.py` (new) · OWNER: BACKEND

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""The end of the funnel, read off our own database for the founders
dashboard: how many people signed up, how many of them are founders, and when
anybody last did something that needed an account.

Under pipeline/, not api/, for the reason stats_analysis.py is: the Lyra image
ships pipeline/ only, and the weekly digest will want these numbers too. The
models come from pipeline.database, so a renamed column is a type error here
rather than a 500 after the deploy. card_collections is deliberately absent -
it is declared in api/cardgame/models.py, which pipeline may not import.

All-time counts, never a window. Measured 2026-09-19: five members, two of
them founders, zero acts of any kind in the last seven days, forty in the last
thirty, newest signup twenty-two days old. Any window reads zero and says
nothing, so the panel counts the whole history and dates it instead.

Every act carries its own count of distinct actors, because at this size the
total alone is a lie: 126 Lyra answers come from 2 accounts and 59 research
requests from 2, 57 of them from one. "Research requests 59" without "by 2"
reads as member activity and is one person's week.

The two act id spaces are never joined and must not be: site_likes,
site_bookmarks and token_usage_logs carry a UUID foreign key into
discord_users.id, research_requests carries a String(255) Discord snowflake.
`by` is therefore "distinct actors on this table", never "distinct members".

Aggregates only. No query selects username, discord_id, avatar_hash or
credits: the founders get counts, never a list of their members.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from pipeline.database import (
    DiscordUser,
    ResearchRequest,
    SiteBookmark,
    SiteLike,
    TokenUsageLog,
)

#: What a member can do that leaves a row behind, in the order the panel
#: prints them. The label is what a founder reads; the model is what is
#: counted. Annotated `Any` on purpose: mypy joins four unrelated model
#: classes to `type[Base]`, and `model.created_at` is then an attribute error
#: on a base class that has no such column.
ACTS: tuple[tuple[str, Any], ...] = (
    ("Likes", SiteLike),
    ("Bookmarks", SiteBookmark),
    ("Lyra answers", TokenUsageLog),
    ("Research requests", ResearchRequest),
)


def members_query(founder_role: str) -> Select:
    """One statement, one round trip: two member counts, two member dates and
    a count, an actor count and a date per act.

    ``founder_role`` is the Discord role id and arrives from the caller -
    api.services.jwt_auth.FOUNDER_ROLE_ID - because pipeline may not import
    api. It is bound through SQLAlchemy Core, not a text() fragment: a
    hand-written ``:founder_role::jsonb`` would bind the name ``founder_rol``,
    because SQLAlchemy's bind regex stops at the first colon of the cast.

    `last_login` carries the same founder filter as `founders`, because the
    panel prints it under the "Founders" tile. Unfiltered it was the newest
    login of any member under a label that says founders - today the two
    happen to be the same row (2026-09-19 06:26:02), which is exactly the kind
    of coincidence that hides a wrong label until it stops being true.
    """
    founders_only = DiscordUser.roles.contains([founder_role])
    columns: list[Any] = [
        select(func.count()).select_from(DiscordUser).scalar_subquery().label("members"),
        select(func.count())
        .select_from(DiscordUser)
        .where(founders_only)
        .scalar_subquery()
        .label("founders"),
        select(func.max(DiscordUser.created_at)).scalar_subquery().label("newest_signup"),
        select(func.max(DiscordUser.last_login))
        .where(founders_only)
        .scalar_subquery()
        .label("last_login"),
    ]
    for i, (_label, model) in enumerate(ACTS):
        columns.append(select(func.count()).select_from(model).scalar_subquery().label(f"n{i}"))
        columns.append(
            select(func.count(func.distinct(model.user_id)))
            .select_from(model)
            .scalar_subquery()
            .label(f"by{i}")
        )
        columns.append(select(func.max(model.created_at)).scalar_subquery().label(f"at{i}"))
    return select(*columns)


def _stamp(value: Any) -> str | None:
    """Every timestamp on these tables is a naive DateTime written by a
    container running Etc/UTC. Without the tzinfo the browser reads
    "2026-08-28T01:33:22" as local time and the panel is two hours out."""
    return value.replace(tzinfo=UTC).isoformat() if value else None


def shape_members(row: Any) -> dict[str, Any]:
    """The one row of members_query() as the panel reads it."""
    return {
        "members": row.members,
        "founders": row.founders,
        "newest_signup": _stamp(row.newest_signup),
        "last_login": _stamp(row.last_login),
        "acts": [
            {
                "act": label,
                "n": getattr(row, f"n{i}"),
                #: Distinct actors on THIS table. Not comparable across acts -
                #: research_requests keys on a Discord snowflake, the other
                #: three on discord_users.id.
                "by": getattr(row, f"by{i}"),
                "at": _stamp(getattr(row, f"at{i}")),
            }
            for i, (label, _model) in enumerate(ACTS)
        ],
    }


def member_totals(db: Session, founder_role: str) -> dict[str, Any]:
    return shape_members(db.execute(members_query(founder_role)).one())
```

---

### Step 9 — `pipeline/stats_analysis.py` · OWNER: BACKEND

**9a. Imports.** Two lines change:

before
```python
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
```
after
```python
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
```

**9b. After the `AI_HOSTS` tuple, insert:**

```python
#: utm_source values that name an assistant without naming a host. ChatGPT
#: tags its outbound links "utm_source=chatgpt.com", which is a host and is
#: already in AI_HOSTS; Perplexity tags them "utm_source=perplexity", which is
#: not. Measured 2026-09-19: thirteen AI sessions, eleven of them tagged
#: chatgpt.com, one perplexity, one referred by gemini.google.com - and ten of
#: the thirteen carry no referer at all.
AI_LABELS = ("chatgpt", "perplexity", "copilot", "gemini", "claude", "openai")
#: What source_family() calls a session that arrived from an assistant.
AI_ENTRY = "ai"
```

**9c. Insert `is_ai_entry` above `source_family`, and rewrite `source_family`:**

```python
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
```

**9d. `Session` — three field changes and a tightened `human`.**

before
```python
    browser: str | None = None
    entry: str | None = None
    steps: list[str] = field(default_factory=list)  # page types and event names, in order
    pages: int = 0
    events: Counter[str] = field(default_factory=Counter)
```
after
```python
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
```

before
```python
    @property
    def human(self) -> bool:
        if self.pages >= 2:
            return True
        return sum(self.events[n] for n in INTERACTIONS) > self.auto_opens
```
after
```python
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
```

**9e. `sessions_from_rows` — the pageview branch.**

before
```python
        if r["event_type"] == 1:
            if s.entry is None:
                s.entry = source_family(r.get("referrer_domain"), r.get("utm_source"))
            s.pages += 1
            s.steps.append(page_type(r["url_path"] or "/"))
```
after
```python
        if r["event_type"] == 1:
            if s.entry is None:
                s.entry = source_family(r.get("referrer_domain"), r.get("utm_source"))
                s.from_ai = is_ai_entry(r.get("referrer_domain"), r.get("utm_source"))
            page = page_type(r["url_path"] or "/")
            s.page_steps.append(page)
            s.steps.append(page)
```

**9f. Append the five new pure functions at the end of the module** (after `problems`):

```python
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


def globe_funnel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """How many globe loads reached an interactive globe, and how long the
    ones that did took. Rows are SQL_GLOBE's, one per session.

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
    """
    loads = 0
    reached = 0
    reached_sessions = 0
    times: list[float] = []
    for r in rows:
        views = int(r["views"] or 0)
        if not views:
            continue
        got = min(int(r["ready"] or 0), views)
        loads += views
        reached += got
        reached_sessions += 1 if got else 0
        times.extend(float(ms) for ms in (r["ready_ms"] or []))
    times.sort()
    enough = len(times) >= GLOBE_MIN_SAMPLES
    return {
        "loads": loads,
        "reached": reached,
        "gave_up": loads - reached,
        "sessions": {"all": sum(1 for r in rows if r["views"]), "reached": reached_sessions},
        "ready_ms": {
            "min": times[0] if times else None,
            "median": times[len(times) // 2] if enough else None,
            "max": times[-1] if times else None,
            "samples": len(times),
        },
    }


def clusters(rows: list[dict[str, Any]], min_ids: int) -> dict[str, Any]:
    """Which browser fingerprints are one machine rather than several people.

    Rows are SQL_CLUSTERS', already grouped. This adds nothing but the total,
    because the rule is one rule: a page load several session ids share at the
    same minute. Seven heuristics and a "suspected" verdict were specified and
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
```

**9g. `problems()` — signature, docstring, default limit, one new loop.**

before
```python
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
```
after
```python
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
```

Also in the same docstring, replace

before
```
    `not_found`, `vitals` and `errors` are the rows of SQL_NOT_FOUND,
    SQL_VITALS and SQL_ERRORS; the bounces and empty searches come from the
    sessions, so no query has to be repeated.
```
after
```
    `not_found`, `vitals`, `errors` and `webgl` are the rows of SQL_NOT_FOUND,
    SQL_VITALS, SQL_ERRORS and SQL_WEBGL_LOST; the bounces and empty searches
    come from the sessions, so no query has to be repeated.

    A lost WebGL context weighs the same as a JavaScript error, because that
    is what it is: the globe stops and the page is over for that visitor. The
    globe's *slowness* is deliberately not a kind here - eight globe_ready
    samples from six browsers cannot carry a percentile, and the globe panel
    prints the times it has, with their count, instead.
```

Insert the new loop **immediately after the `errors` loop** and before the `vitals` loop, and add the
phase table next to `SHALLOW_PAGES`:

```python
#: What a lost WebGL context means for the visitor, by the phase the globe was
#: in when it happened. src/components/Globe.tsx sends exactly these two.
WEBGL_PHASES = {
    "loading": "globe never started",
    "live": "globe froze after it had started",
}
```

```python
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
```

---

### Step 10 — `api/routes/founders_stats.py` · OWNER: BACKEND *(same commit as steps 1, 2)*

**10a. Docstring.** Replace lines 2-4:

before
```python
"""The founders dashboard's data: seven endpoints under /api/stats, all behind
the ``an_stats`` cookie (stats_access.require_stats_session). Rows come from
pipeline.umami_db, the founder-level shaping from api.services.founders_stats.
```
after
```python
"""The founders dashboard's data: twelve endpoints under /api/stats, all behind
the ``an_stats`` cookie (stats_access.require_stats_session). Umami rows come
from pipeline.umami_db, the member counts from pipeline.members_stats, nginx's
referral log from pipeline.referral_log, and every founder-level shaping from
pipeline.stats_analysis.
```

**10b. Imports.** Replace the whole import block:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.cache import cached
from api.routes.stats_access import require_stats_session
from api.services import jwt_auth
from pipeline import members_stats, referral_log
from pipeline import stats_analysis as fs
from pipeline.database import get_db
from pipeline.umami_db import (
    CLUSTER_MIN_IDS,
    GLOBE_PATH,
    SQL_CLUSTERS,
    SQL_CONTENT,
    SQL_ERRORS,
    SQL_FEEDBACK,
    SQL_GLOBE,
    SQL_LIVE,
    SQL_MAP,
    SQL_NOT_FOUND,
    SQL_SESSION_EVENTS,
    SQL_SOURCES,
    SQL_VITALS,
    SQL_WEBGL_LOST,
    fetch,
)
```

`SQL_OVERVIEW` and `SQL_HOUR_BUCKETS` are **gone** from this module. `SQL_OVERVIEW` itself stays in
`umami_db.py` — `pipeline/lyra/analytics_alerts.weekly_digest()` still uses it.

**10c. Constants.** Replace the `LIVE_WINDOW` block:

```python
#: "Live" on the pulse tile: sessions with an event in the last five minutes.
LIVE_WINDOW = timedelta(minutes=5)
#: The live panel's own window, and how far back it looks for the last visitor
#: when nobody is here. Measured 2026-09-19: a thirty-minute window was empty
#: in 20 % of all minutes and the longest gap between two events was 117
#: minutes, so a 24-hour lookback always names somebody.
HERE_WINDOW = timedelta(minutes=30)
LIVE_LOOKBACK = timedelta(hours=24)
#: Rows the live panel prints. At one visitor an hour this is never reached;
#: it exists so a burst cannot make the panel the tallest thing on the phone.
LIVE_LIMIT = 6
#: The flag row's longest window. One fetch serves all four tiles.
COUNTRY_DAYS = 30
#: How long /countries' thirty-day fold is reused. It must be LONGER than the
#: dashboard's poll interval or it can never hit: useStats refreshes every
#: 60 000 ms (ancient-nerds-map/src/components/dashboard/useStats.ts:10), and
#: a 55-second entry is always expired by the time the next request arrives -
#: 0 % hit rate for a single open dashboard, which is what the first draft
#: shipped. At 90 s every second refresh is served from cache.
#: Redis holds it, so the two API containers share one copy; without Redis
#: api/cache.py falls back to a per-process dict and each container keeps its
#: own. Worth having even though the query costs 10 ms today: it is the only
#: one that will grow with the calendar rather than with the traffic.
COUNTRY_TTL = 90
```

(Delete the standalone `COUNTRY_DAYS` comment block further down — it moves here.)

**10d. `overview()` — replace the whole function.**

```python
@router.get("/overview")
async def overview(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """One fetch, three panels: the pulse strip, the session types and the
    scraper panel's denominator.

    `human` and `ai` both count sessions and they overlap - an assistant can
    send a person. They are never added together.
    """
    since, until = _window(days)
    rows = fetch(SQL_SESSION_EVENTS, since, until)
    sessions = fs.sessions_from_rows(rows)
    return {
        "days": days,
        "sessions": {
            "all": len(sessions),
            "human": sum(1 for s in sessions if s.human),
            "ai": sum(1 for s in sessions if s.from_ai),
        },
        "types": fs.session_type_shares(sessions),
        "hours": fs.hourly_sessions(rows, sessions, until),
    }
```

**10e. `visitor_countries()` — split the body into a cached helper.**

```python
@cached("stats:countries", ttl=COUNTRY_TTL)
async def _country_windows() -> dict[str, Any]:
    """The four flag tiles from one thirty-day fold.

    Cached rather than recomputed per request: this is the only query on the
    page that reaches back a month. The cache is api/cache.py's - Redis when
    it is up, and then both API containers share one copy; a bounded
    per-process dict when it is not, and then they do not. No argument, so the
    key is the prefix and no founder's session ever reaches it.

    Note the 30-day fold costs the same 10-13 ms as the 7-day one today
    (measured 2026-09-19: 794 rows either way) - the tracker has two days of
    history. The cache is here for October, not for now.
    """
    now = datetime.now(UTC)
    sessions = fs.sessions_from_rows(
        fetch(SQL_SESSION_EVENTS, now - timedelta(days=COUNTRY_DAYS), now)
    )

    def block(since: datetime | None, human_only: bool = True) -> dict[str, Any]:
        rows = fs.countries(sessions, since=since, human_only=human_only)
        everyone = fs.countries(sessions, since=since, human_only=False)
        return {
            "sessions": sum(r["sessions"] for r in rows),
            "all": sum(r["sessions"] for r in everyone),
            "countries": rows,
        }

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "now": block(now - LIVE_WINDOW, human_only=False),
        "today": block(midnight),
        "d7": block(now - timedelta(days=7)),
        "d30": block(None),
    }


@router.get("/countries")
async def visitor_countries(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is here — sessions per country for now, today, 7 and 30 days."""
    return await _country_windows()
```

**10f. `journeys()` — replace the return.**

before
```python
    sessions = fs.sessions_from_rows(fetch(SQL_SESSION_EVENTS, since, until))
    return {
        "chains": [{"chain": chain, "sessions": n} for chain, n in fs.journeys(sessions)],
    }
```
after
```python
    rows = fetch(SQL_SESSION_EVENTS, since, until)
    sessions = fs.sessions_from_rows(rows)
    return {
        "chains": [{"chain": chain, "sessions": n} for chain, n in fs.journeys(sessions)],
        "pages": fs.entry_exit_pages(sessions),
        "outbound": fs.outbound_links(rows),
    }
```

**10g. `problems()` — one more fetch.**

before
```python
            searches=[r for r in fetch(SQL_CONTENT, since, until) if r["event_name"] == "search"],
        )
```
after
```python
            searches=[r for r in fetch(SQL_CONTENT, since, until) if r["event_name"] == "search"],
            webgl=fetch(SQL_WEBGL_LOST, since, until),
        )
```

**10h. `sources()` — the coverage block.**

```python
@router.get("/sources")
async def sources(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Where the sessions came from, and how many arrivals the tracker missed.

    Two counts of one thing, deliberately side by side: Umami only sees a
    visitor whose browser ran our script, nginx sees every request. Measured
    2026-09-19 over the same window, with referral_log's own arrival rule:
    189 Google page arrivals in the log (168 answered 200, 21 answered 410)
    against 62 page views from 51 sessions in Umami.
    """
    since, until = _window(days)
    rows = fetch(SQL_SOURCES, since, until)
    visits = referral_log.read_visits()
    return {
        "sources": [
            {
                "source": r["source"],
                "family": fs.source_family(r["source"]),
                "sessions": r["sessions"],
                "views": r["views"],
            }
            for r in rows
        ],
        "log": referral_log.coverage_report(visits, since, until) if visits is not None else None,
        "log_reason": None if visits is not None else referral_log.unavailable_reason(),
    }
```

**10i. Three new routes, appended at the end of the module.**

```python
@router.get("/globe")
async def globe(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Does the globe come up, and how long does it take when it does."""
    since, until = _window(days)
    return fs.globe_funnel(fetch(SQL_GLOBE, since, until, path=GLOBE_PATH))


@router.get("/clusters")
async def clusters(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Browser fingerprints that are one machine, not several people. The
    denominator comes from /overview, which the page already has."""
    since, until = _window(days)
    rows = fetch(SQL_CLUSTERS, since, until, min_ids=CLUSTER_MIN_IDS)
    return fs.clusters(rows, min_ids=CLUSTER_MIN_IDS)


@router.get("/live")
async def live(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is here now and what they have open, and who was here last when
    nobody is. Fixed windows: the page's range switch does not touch this."""
    now = datetime.now(UTC)
    rows = fetch(SQL_LIVE, now - LIVE_LOOKBACK, now)
    here = [r for r in rows if r["last_seen"] >= now - HERE_WINDOW]
    return {
        "window_minutes": int(HERE_WINDOW.total_seconds() // 60),
        "lookback_hours": int(LIVE_LOOKBACK.total_seconds() // 3600),
        "total": len(here),
        "shown": min(len(here), LIVE_LIMIT),
        "visitors": [fs.live_row(r, now) for r in here[:LIVE_LIMIT]],
        "last": fs.live_row(rows[0], now) if rows and not here else None,
    }


@router.get("/members")
async def members(
    db: Session = Depends(get_db),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """The end of the funnel: signups and what members have ever done.
    Aggregates only — no name, no id, no credit balance leaves this route."""
    return members_stats.member_totals(db, jwt_auth.FOUNDER_ROLE_ID)
```

`/clusters` deliberately returns no session total: the route has no session count and must not run a
second query for one. The panel divides by `/overview`'s `sessions.all`, which it already holds.
Step 9f's `clusters(rows, min_ids)` is the only signature — there is no `sessions` parameter and no
`"sessions"` key in the fold. (An earlier draft of this file carried a "Correction" paragraph here
that told the implementer to *replace* the route body with a bare `return fs.clusters(rows, …)`;
`rows` was undefined in that scope and `ruff check api/` reported `F821`, which blocks the deploy.
The two-line body above is the whole of it.)

**10j. `live_row` — add to `pipeline/stats_analysis.py` in step 9f** (it belongs there, not in the
route):

```python
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
        "here": int((now - row["page_since"]).total_seconds()),
        "last_seen": row["last_seen"].isoformat(),
    }
```

---

### Step 11 — `pipeline/lyra/analytics_alerts.py` · OWNER: BACKEND

**11a.** Import `SQL_WEBGL_LOST`:

before
```python
from pipeline.umami_db import (
    SQL_CONTENT,
    SQL_ERRORS,
    SQL_FEEDBACK,
    SQL_NOT_FOUND,
    SQL_OVERVIEW,
    SQL_SESSION_EVENTS,
    SQL_VITALS,
    fetch,
)
```
after
```python
from pipeline.umami_db import (
    SQL_CONTENT,
    SQL_ERRORS,
    SQL_FEEDBACK,
    SQL_NOT_FOUND,
    SQL_OVERVIEW,
    SQL_SESSION_EVENTS,
    SQL_VITALS,
    SQL_WEBGL_LOST,
    fetch,
)
```

**11b.** `problem_lines()`'s label table gains the new kind:

before
```python
        "empty_search": "Empty search",
    }
```
after
```python
        "empty_search": "Empty search",
        "webgl_lost": "WebGL lost",
    }
```

**11c.** `weekly_digest()` passes the new rows:

before
```python
        # Same four inputs the dashboard's Problems panel uses.
        ranked = problems(
            sessions_from_rows(fetch(SQL_SESSION_EVENTS, week_start, now)),
            not_found=fetch(SQL_NOT_FOUND, week_start, now),
            vitals=fetch(SQL_VITALS, week_start, now),
            errors=fetch(SQL_ERRORS, week_start, now),
            searches=[r for r in content if r["event_name"] == "search"],
        )
```
after
```python
        # Dieselben Eingaben wie das Problems-Panel des Dashboards, damit
        # Digest und Panel nie zwei Wahrheiten erzählen.
        ranked = problems(
            sessions_from_rows(fetch(SQL_SESSION_EVENTS, week_start, now)),
            not_found=fetch(SQL_NOT_FOUND, week_start, now),
            vitals=fetch(SQL_VITALS, week_start, now),
            errors=fetch(SQL_ERRORS, week_start, now),
            searches=[r for r in content if r["event_name"] == "search"],
            webgl=fetch(SQL_WEBGL_LOST, week_start, now),
        )
```

---

### Step 12 — `ancient-nerds-map/src/components/dashboard/types.ts` · OWNER: TYPES

Exactly one writer for this file. **Delete** `DayBlock` (its only reader is `Pulse.tsx:95`, which
step 15 rewrites). **Replace** `HourBucket`, `Overview`, `JourneysData`, `SourceRow`, `SourcesData`
and `ProblemKind`. **Append** the rest at the end of the file.

Replace `HourBucket` and `Overview` (lines 10-32, `DayBlock` included):

```ts
export interface HourBucket {
  /** Start of the hour, UTC. Always 48 buckets, including the empty ones. */
  hour: string
  /** Sessions with any event in this hour. */
  sessions: number
  /** Of those, the confirmed-human ones — the strip's lower segment. */
  human: number
  /** Of those, the ones an AI assistant sent. Overlaps `human`; never added
   *  to it. Too rare to draw (13 in 7 days), so it lives in the legend. */
  ai: number
}

/** GET /api/stats/overview?days=N */
export interface Overview {
  days: number
  /** `human` and `ai` are both subsets of `all` and overlap each other. */
  sessions: { all: number; human: number; ai: number }
  types: Partial<Record<SessionKind, number>>
  hours: HourBucket[]
}
```

Replace `ProblemKind` (lines 112-113):

```ts
/** The six failures pipeline/stats_analysis.py problems() knows. */
export type ProblemKind =
  | 'js_error'
  | 'slow_page'
  | 'broken_link'
  | 'shallow_exit'
  | 'empty_search'
  /** The globe's WebGL context died — the page is over for that visitor. */
  | 'webgl_lost'
```

Replace `JourneysData` (lines 107-110):

```ts
export interface EntryPage {
  page: string
  sessions: number
  /** Of those, how many went no further. */
  stopped: number
}
export interface ExitPage {
  page: string
  sessions: number
  /** Views of this page type across all human sessions — the row prints
   *  "12 of 20", never a percentage: 46 human sessions is too few for one. */
  views: number
}
export interface PageEnds {
  sessions: number
  /** Human sessions with exactly one page view. There is no `no_page` key:
   *  a session without a page view is not `human` (stats_analysis.py 9d), so
   *  that number would be 0 forever. */
  one_page: number
  moving: number
  entries: EntryPage[]
  exits: ExitPage[]
}
export interface OutboundLink {
  host: string
  clicks: number
  visitors: number
}

/** GET /api/stats/journeys?days=N */
export interface JourneysData {
  chains: JourneyChain[]
  pages: PageEnds
  outbound: OutboundLink[]
}
```

Replace `SourceRow` / `SourcesData` (lines 145-154):

```ts
export interface SourceRow {
  source: string
  family: string
  sessions: number
  /** Page views, so the panel can put this next to nginx's request count. */
  views: number
}

export interface LogFamily {
  family: string
  visits: number
  bots: number
}
export interface LogHost {
  host: string
  visits: number
}
export interface LogStatus {
  status: number
  visits: number
}
/** What nginx saw in the same window — human page requests only. */
export interface LogCoverage {
  covered_from: string
  covered_days: number
  lines: number
  families: LogFamily[]
  hosts: LogHost[]
  statuses: LogStatus[]
}

/** GET /api/stats/sources?days=N */
export interface SourcesData {
  sources: SourceRow[]
  /** null when /app/logs/referrals.log is not mounted — every dev box. */
  log: LogCoverage | null
  /** An English sentence naming the path and the bind, when `log` is null. */
  log_reason: string | null
}
```

Append at the end of the file:

```ts
/** GET /api/stats/globe?days=N — the denominator is page loads, not sessions. */
export interface GlobeData {
  loads: number
  reached: number
  gave_up: number
  sessions: { all: number; reached: number }
  /** `median` is null below five samples; `min`/`max` are null with none. */
  ready_ms: { min: number | null; median: number | null; max: number | null; samples: number }
}

export interface Cluster {
  screen: string | null
  browser: string | null
  os: string | null
  sessions: number
}
/** GET /api/stats/clusters?days=N */
export interface ClustersData {
  /** How many session ids had to share one page load to count. */
  min_ids: number
  flagged: number
  clusters: Cluster[]
}

/** A visitor who is here now, and what they have open. Extends Visitor. */
export interface LiveVisitor extends Visitor {
  page: string
  title: string
  /** Seconds since this page view started. */
  here: number
  last_seen: string
}
/** GET /api/stats/live — fixed windows, not the page's range switch. */
export interface LiveData {
  window_minutes: number
  lookback_hours: number
  /** Visitors in the window. `shown` is how many of them the list prints. */
  total: number
  shown: number
  visitors: LiveVisitor[]
  /** Only when `total` is 0: the most recent visitor of the lookback. */
  last: LiveVisitor | null
}

export interface MemberAct {
  act: string
  n: number
  /** Distinct actors on this one table. Not comparable across acts: three of
   *  the four key on discord_users.id, research_requests on a snowflake. */
  by: number
  at: string | null
}
/** GET /api/stats/members — all-time counts, never a window. */
export interface MembersData {
  members: number
  founders: number
  newest_signup: string | null
  /** The newest login of a FOUNDER, matching the tile it sits under. */
  last_login: string | null
  acts: MemberAct[]
}
```

`LiveVisitor extends Visitor`, so it must be declared **after** the existing `Visitor` block — the
append position satisfies that.

**Interfaces deliberately not created:** `PeriodChange`, `CountryWindow.change`, `LanguageCount`,
`FunnelStep`, `ReadingFunnel`, `ReadingReport`, `ExitRow`, `ExitsData`, `ReturnCohort`, `Returner`,
`ReturningData`, `AssistantRow`, `AssistantsData`, `HeritagePair`, `ClusterVerdict`, `DayBlock`.

---

### Step 13 — `ancient-nerds-map/src/components/dashboard/Tile.tsx` (new) · OWNER: PANEL:Tile

`Tile` moves out of `Pulse.tsx`. `Flags` does **not** come here — it renders `Flag`s and belongs in
`Flag.tsx`, which already exists (step 14).

```tsx
import { Flags } from './Flag'
import { fmtInt } from './format'
import type { CountryCount } from './types'

interface TileProps {
  label: string
  /** The number, already counted by the backend. */
  value: number
  sub: string
  subCls?: string
  /** Flags filling the space beside the number. Omitted, the number is alone. */
  countries?: CountryCount[]
}

/**
 * One labelled number with its sub-line. The number keeps its size; anything
 * beside it gets whatever is left (owner, 2026-09-19).
 */
export function Tile({ label, value, sub, subCls, countries }: TileProps) {
  return (
    <div className="dash-tile">
      <span className="dash-tile-label">{label}</span>
      <div className="dash-tile-main">
        <span className="dash-tile-value">{fmtInt(value)}</span>
        {countries && <Flags rows={countries} />}
      </div>
      <span className={subCls ? `dash-tile-sub ${subCls}` : 'dash-tile-sub'}>{sub}</span>
    </div>
  )
}
```

---

### Step 14 — `ancient-nerds-map/src/components/dashboard/Flag.tsx` · OWNER: PANEL:Tile

Append `Flags`, moved verbatim from `Pulse.tsx:20-42` (the JSDoc block is lines 20-27, the function
28-42 — move both), and extend the import line to `import { countryName, fmtInt } from './format'`
plus `import type { CountryCount } from './types'`.

```tsx
/**
 * The countries behind a tile's number, biggest first, in a box that fills the
 * space to the right of it. The box is exactly as tall as the number (its
 * wrapper is a flex item with no content of its own, the list inside is
 * absolute), the flags wrap to use every line of it, and whatever no longer
 * fits is cut off instead of shrinking the number (owner, 2026-09-19). The
 * fade marks the cut.
 */
export function Flags({ rows }: { rows: CountryCount[] }) {
  if (rows.length === 0) return null
  return (
    <div className="dash-flags-box">
      <ul className="dash-flags">
        {rows.map(r => (
          <li className="dash-flag" key={r.country} title={`${countryName(r.country)}: ${fmtInt(r.sessions)}`}>
            <Flag country={r.country} />
            {fmtInt(r.sessions)}
          </li>
        ))}
      </ul>
    </div>
  )
}
```

---

### Step 15 — `ancient-nerds-map/src/components/dashboard/Pulse.tsx` · OWNER: PANEL:Pulse

Replace the whole file.

```tsx
import { fmtDayHour, fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { CountriesData, CountryWindow, HourBucket, Overview } from './types'
import type { Loaded } from './useStats'

/** Height of the strip's viewBox; the CSS scales it to the panel's width. */
const STRIP_HEIGHT = 20

export interface HourStack {
  humanY: number
  humanH: number
  restY: number
  restH: number
}

/**
 * One hour as two stacked rects: confirmed humans on the baseline, everything
 * else above them. Two segments, not three — at 390 px a bar is 4.9 px wide
 * and one session at the 48-hour peak is 6 px tall, below the size at which
 * any colour difference survives. The AI count is a number in the legend and
 * in the tooltip instead.
 */
export function stackHour(h: HourBucket, max: number, height = STRIP_HEIGHT): HourStack {
  const unit = height / Math.max(max, 1)
  const humanH = h.human * unit
  const restH = (h.sessions - h.human) * unit
  return { humanY: height - humanH, humanH, restY: height - humanH - restH, restH }
}

/** "human sessions, 34 % of 154" — the same sentence for every closed window. */
function humanSub(w: CountryWindow): string {
  return `human sessions, ${fmtShare(w.sessions, w.all)} of ${fmtInt(w.all)}`
}

function Strip({ o }: { o: Overview }) {
  const hours = o.hours
  if (hours.length < 2) return null
  const max = Math.max(...hours.map(h => h.sessions), 1)
  const first = new Date(hours[0].hour)
  const last = new Date(hours[hours.length - 1].hour)
  return (
    <>
      <svg
        className="dash-spark"
        viewBox={`0 0 ${hours.length} ${STRIP_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Sessions per hour, last ${hours.length} hours`}
      >
        {hours.map((h, i) => {
          const s = stackHour(h, max)
          const title = `${fmtDayHour(new Date(h.hour))} UTC: ${fmtInt(h.sessions)} sessions, ${fmtInt(h.human)} human, ${fmtInt(h.ai)} from AI`
          return (
            <g key={h.hour}>
              <rect x={i + 0.15} width={0.7} y={s.restY} height={s.restH}>
                <title>{title}</title>
              </rect>
              <rect className="dash-spark-human" x={i + 0.15} width={0.7} y={s.humanY} height={s.humanH}>
                <title>{title}</title>
              </rect>
            </g>
          )
        })}
      </svg>
      <div className="dash-spark-axis">
        <span>{fmtDayHour(first)}</span>
        <span>Sessions per hour, UTC</span>
        <span>{fmtDayHour(last)}</span>
      </div>
      <p className="dash-note">
        Bright green is a confirmed human — an interaction or a second page. The rest may be a bot, or a
        person who read the headline and left; cookieless data cannot tell them apart. AI assistants sent{' '}
        {fmtInt(o.sessions.ai)} of {fmtInt(o.sessions.all)} sessions in this window.
      </p>
    </>
  )
}

/**
 * Four windows of one question — who is here now, today, this week, this month
 * — each with its total and the countries behind it. The windows are fixed:
 * the page's range switch drives the other panels, not this one.
 */
export function Pulse({ state, countries }: { state: Loaded<Overview>; countries: Loaded<CountriesData> }) {
  const o = state.data
  const c = countries.data
  return (
    <Panel question="Who is here right now?" wide>
      <Status state={countries} />
      {c && (
        <div className="dash-tiles">
          <Tile label="Now" value={c.now.sessions} sub="sessions, last 5 min" countries={c.now.countries} />
          <Tile label="Today" value={c.today.sessions} sub={humanSub(c.today)} countries={c.today.countries} />
          <Tile label="7 days" value={c.d7.sessions} sub={humanSub(c.d7)} countries={c.d7.countries} />
          <Tile label="30 days" value={c.d30.sessions} sub={humanSub(c.d30)} countries={c.d30.countries} />
        </div>
      )}
      {o && <Strip o={o} />}
    </Panel>
  )
}
```

The Today tile now uses the same sentence as every other closed window. That is the fix for the live
defect where the tile printed a human count from `/countries` under a percentage computed from an
all-sessions count in `/overview` — "6" under "= same as yesterday (28 vs 28)".

---

### Step 16 — `ancient-nerds-map/src/components/dashboard/GlobeReach.tsx` (new) · OWNER: PANEL:GlobeReach

```tsx
import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { GlobeData } from './types'
import type { Loaded } from './useStats'

/** "9.5 s" / "80.4 s" — the globe's times are seconds, never milliseconds. */
export function secs(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

/**
 * The sentence under the two numbers. Counts, never a percentage on its own:
 * eight successes out of thirty-three loads is a direction, and the reader has
 * to see both numbers to know that. No p75 either — eight live samples come
 * from six browsers and two of those contributed two loads each.
 */
export function timesLine(g: GlobeData): string {
  const t = g.ready_ms
  if (t.samples === 0) return 'No globe reached its layers in this window.'
  const middle = t.median === null ? '' : `, ${secs(t.median)} in the middle`
  // "reports", not "visitors": samples counts globe_ready events and is not
  // capped to `reached`, which is capped to page views (globe_funnel's
  // docstring says why). The two agree today and need not tomorrow.
  return `The ${fmtInt(t.samples)} globe_ready reports we have waited ${secs(t.min ?? 0)} at best${middle}, ${secs(t.max ?? 0)} at worst.`
}

/** Does the globe come up at all — the product's own pass rate. */
export function GlobeReach({ state }: { state: Loaded<GlobeData> }) {
  const g = state.data
  return (
    <Panel question="Does the globe actually come up?">
      <Status state={state} />
      {g && (
        <>
          <div className="dash-tiles">
            <Tile label="Globe loads" value={g.loads} sub={`${fmtInt(g.sessions.all)} visitors opened it`} />
            <Tile
              label="Reached the globe"
              value={g.reached}
              sub={`${fmtInt(g.gave_up)} loads never got there`}
            />
          </div>
          <p className="dash-note">
            {timesLine(g)} The denominator is page loads of /globe.html, not visitors — one person
            reloading counts twice, on purpose.
          </p>
        </>
      )}
    </Panel>
  )
}
```

---

### Step 17 — `ancient-nerds-map/src/components/dashboard/Scrapers.tsx` (new) · OWNER: PANEL:Scrapers

```tsx
import { BarList, type BarItem } from './BarList'
import { fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import type { Cluster, ClustersData, Overview } from './types'
import type { Loaded } from './useStats'

/** One fingerprint as a bar row: screen, browser and operating system. */
export function clusterItem(c: Cluster): BarItem {
  const parts = [c.screen, c.browser, c.os].filter(Boolean)
  return {
    key: parts.join('|') || 'unknown',
    label: parts.length ? parts.join(' · ') : 'unknown machine',
    value: c.sessions,
    hint: 'sessions',
  }
}

/**
 * How much of the session count above is one machine. The rule is one rule: a
 * page load several session ids reached inside the same minute. Cookieless
 * analytics gives a stateless client a fresh id per request, so that is the
 * one thing a headless fetcher cannot hide.
 */
export function Scrapers({ state, overview }: { state: Loaded<ClustersData>; overview: Loaded<Overview> }) {
  const c = state.data
  // The denominator lives in another endpoint. When /overview has not answered
  // (or failed), print the count alone — never "38 of 0 sessions (0 %)".
  const all = overview.data?.sessions.all ?? null
  return (
    <Panel question="How many of those are one machine?">
      <Status state={state} />
      {c && (
        <>
          <BarList
            items={c.clusters.map(clusterItem)}
            empty="No path was touched by several session ids inside one minute in this window."
          />
          <p className="dash-note">
            {fmtInt(c.flagged)}
            {all === null ? '' : ` of ${fmtInt(all)} sessions (${fmtShare(c.flagged, all)})`} sat inside a
            group that {c.min_ids} or more session ids reached on the same path in the same minute. The
            two numbers cover the same window but are up to five minutes apart — this panel refreshes
            every five minutes, the session count every minute. Read every other number on this page with
            that subtracted. Declared crawlers never get this far: Umami drops GPTBot, ClaudeBot and
            PerplexityBot before the insert, so they are invisible here — "and the rest are people" does
            not follow.
          </p>
        </>
      )}
    </Panel>
  )
}
```

---

### Step 18 — `ancient-nerds-map/src/components/dashboard/LiveNow.tsx` (new) · OWNER: PANEL:LiveNow

```tsx
import { Flag } from './Flag'
import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { LiveData, LiveVisitor } from './types'
import type { Loaded } from './useStats'

/** "< 1 min" / "6 min" / "2 h 11 min" — how long they have had this page open.
 *  formatDuration() in utils/formatters.ts is clock style ("6:52") and
 *  timeAgo() needs a timestamp, so neither answers this question. */
export function fmtSpan(seconds: number): string {
  if (seconds < 60) return '< 1 min'
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} min`
  return `${Math.floor(mins / 60)} h ${mins % 60} min`
}

/** Seconds since an ISO stamp, for "last seen N ago". `here` cannot answer
 *  that: live_row() measures it from page_since, the start of that visitor's
 *  last page view, so it overstates by the whole time they spent on it —
 *  live rows show gaps of up to 4 min 40 s between the two today. */
export function secondsSince(iso: string, now = Date.now()): number {
  return Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
}

function Row({ v }: { v: LiveVisitor }) {
  return (
    <li className="dash-live-row">
      <span className="dash-dot dash-dot--live" aria-hidden="true" />
      <span className="dash-flag">
        <Flag country={v.country} />
      </span>
      <span className="dash-live-who">{[v.browser, v.device].filter(Boolean).join(' · ')}</span>
      <span className="dash-live-here">{fmtSpan(v.here)}</span>
      <span className="dash-live-page">{v.title}</span>
    </li>
  )
}

/** Who is here in the last half hour, and what they have open. */
export function LiveNow({ state }: { state: Loaded<LiveData> }) {
  const l = state.data
  return (
    <Panel question="What are they looking at right now?" wide>
      <Status state={state} />
      {l && (
        <>
          {l.total === 0 ? (
            <p className="dash-empty">
              Nobody in the last {l.window_minutes} minutes.
              {l.last && (
                <>
                  {' '}
                  Last seen {fmtSpan(secondsSince(l.last.last_seen))} ago on <b>{l.last.title}</b>.
                </>
              )}
            </p>
          ) : (
            <ul className="dash-live">
              {l.visitors.map(v => (
                <Row key={v.session} v={v} />
              ))}
            </ul>
          )}
          <p className="dash-note">
            {fmtInt(l.total)} in the last {l.window_minutes} minutes, {fmtInt(l.shown)} shown. The Now
            tile above counts five minutes, so this list is the longer window. A visitor who fired only a
            Core Web Vital has no page to name and no row — ten of sixty-nine sessions in a day
            (2026-09-19). The headline is the page's own title, so it is in the visitor's language, not
            ours. This is the one panel on the page that can point at a single person: at one visitor it
            names their country, device, browser and the page they have open right now. It is cookieless
            and no id here survives the daily salt rotation, but it is not anonymous in the moment — do
            not screenshot it into a public channel.
          </p>
        </>
      )}
    </Panel>
  )
}
```

---

### Step 19 — `ancient-nerds-map/src/components/dashboard/Members.tsx` (new) · OWNER: PANEL:Members

```tsx
import { BarList, type BarItem } from './BarList'
import { fmtInt, fmtStamp } from './format'
import { Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { MemberAct, MembersData } from './types'
import type { Loaded } from './useStats'

/**
 * One act as a bar row. The hint carries the denominator and the date,
 * because at this size the total alone is a lie: 126 Lyra answers come from
 * two accounts, 125 of them from one (measured 2026-09-19). "126" under a
 * panel headed "Who signed up, and did they come back?" reads as member
 * activity and is one person's week.
 */
export function actItem(a: MemberAct): BarItem {
  const by = `by ${fmtInt(a.by)} ${a.by === 1 ? 'account' : 'accounts'}`
  return {
    key: a.act,
    label: a.act,
    value: a.n,
    hint: a.at ? `${by}, last ${fmtStamp(a.at)}` : 'never',
  }
}

/**
 * The end of the funnel. All-time counts, never a window: at five members a
 * seven-day window reads zero everywhere and says nothing. Aggregates only —
 * the backend never sends a name, an id or a credit balance.
 */
export function Members({ state }: { state: Loaded<MembersData> }) {
  const m = state.data
  return (
    <Panel question="Who signed up, and did they come back?">
      <Status state={state} />
      {m && (
        <>
          <div className="dash-tiles">
            <Tile
              label="Members"
              value={m.members}
              sub={m.newest_signup ? `newest ${fmtStamp(m.newest_signup)}` : 'none yet'}
            />
            <Tile
              label="Founders"
              value={m.founders}
              sub={m.last_login ? `last login ${fmtStamp(m.last_login)}` : 'never'}
            />
          </div>
          <BarList items={m.acts.map(actItem)} empty="Nobody has done anything yet." />
          <p className="dash-note">
            Everything since the first signup, not the window above — {fmtInt(m.members)} members cannot
            fill a seven-day bucket. The login date is a founder's own; member recency is the date on each
            act row. The account counts are per table and do not add up across rows: three of the four
            key on a member id, research requests on a Discord id. The card game is not counted here: its
            table lives on the API side, which this query may not reach.
          </p>
        </>
      )}
    </Panel>
  )
}
```

---

### Step 20 — `Journeys.tsx` → `Paths.tsx` · OWNER: PANEL:Paths

`git mv ancient-nerds-map/src/components/dashboard/Journeys.tsx .../Paths.tsx` in the same commit, so
the file name matches its one export. Keep `ARROW`, `ACTION_STEPS`, `Chip`, `ChipTone` and
`chainChips` byte-for-byte. Replace the import block and the exported component.

```tsx
import { Fragment } from 'react'

import { BarList, type BarItem } from './BarList'
import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { EntryPage, ExitPage, JourneysData, OutboundLink } from './types'
import type { Loaded } from './useStats'
```

```tsx
/** "story · 248, 151 of them went no further" — counts, never a bounce rate. */
export function entryItem(e: EntryPage): BarItem {
  return {
    key: `entry:${e.page}`,
    label: e.page,
    value: e.sessions,
    hint: e.stopped ? `${fmtInt(e.stopped)} went no further` : undefined,
    tone: e.stopped && e.stopped === e.sessions ? 'warn' : undefined,
  }
}

/** The last page a session was on, against how often that type was seen. */
export function exitItem(x: ExitPage): BarItem {
  return {
    key: `exit:${x.page}`,
    label: x.page,
    value: x.sessions,
    hint: `of ${fmtInt(x.views)} views`,
  }
}

/** A link out of the site. There is no Discord row: see the panel's note. */
export function outboundItem(o: OutboundLink): BarItem {
  return {
    key: `out:${o.host}`,
    label: o.host,
    value: o.clicks,
    hint: `${fmtInt(o.visitors)} ${o.visitors === 1 ? 'visitor' : 'visitors'}`,
  }
}

/** Where they land, where they stop, the whole chain, and where they leave to. */
export function Paths({ state }: { state: Loaded<JourneysData> }) {
  const j = state.data
  return (
    <Panel question="How do they move through the site, and where do they leave?" wide>
      <Status state={state} />
      {j && (
        <>
          <div className="dash-lists">
            <div>
              <h3>They land on</h3>
              <BarList items={j.pages.entries.map(entryItem)} empty="No human session opened a page." />
            </div>
            <div>
              <h3>They stop on</h3>
              <BarList items={j.pages.exits.map(exitItem)} empty="No human session opened a page." />
            </div>
          </div>
          <h3>Most walked paths</h3>
          {j.chains.length === 0 ? (
            <p className="dash-empty">No journeys in this window.</p>
          ) : (
            <ol className="dash-journeys">
              {j.chains.map(c => (
                <li key={c.chain} className="dash-journey">
                  <span className="dash-journey-chain">
                    {chainChips(c.chain).map((chip, i) => (
                      <Fragment key={`${i}-${chip.label}`}>
                        {i > 0 && (
                          <span className="dash-journey-arrow" aria-hidden="true">
                            →
                          </span>
                        )}
                        <span className={`dash-chip dash-chip--${chip.tone}`}>{chip.label}</span>
                      </Fragment>
                    ))}
                  </span>
                  <span className="dash-journey-count">{fmtInt(c.sessions)}</span>
                </li>
              ))}
            </ol>
          )}
          <h3>Links out of the site</h3>
          <BarList items={j.outbound.map(outboundItem)} empty="No outbound click in this window." />
          <p className="dash-note">
            Confirmed human sessions only, at most six steps per chain; the first chip is the source. Of{' '}
            {fmtInt(j.pages.sessions)} human sessions, {fmtInt(j.pages.one_page)} loaded exactly one page
            and {fmtInt(j.pages.moving)} moved. A session with no page view at all is not counted as
            human and is not in here — the Scrapers panel above is where those go. Discord clicks are
            missing from the outbound list: the CTA on the landing page, which the server log says gets
            most of them, runs no analytics module — read those with scripts/funnel_report.py.
          </p>
        </>
      )}
    </Panel>
  )
}
```

---

### Step 21 — `ancient-nerds-map/src/components/dashboard/Sources.tsx` · OWNER: PANEL:Sources

Keep `SourceBucket`, `BUCKET_LABELS`, `RAW_ROWS`, `sourceBucket` and `bucketTotals` unchanged. Replace
the import block, add two pure functions and a sub-component, and rewrite the panel as `wide`.

```tsx
import { BarList, type BarItem } from './BarList'
import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { LogCoverage, LogFamily, LogHost, LogStatus, SourceRow, SourcesData } from './types'
import type { Loaded } from './useStats'
```

```tsx
/** What nginx counted per family, with the bots it saw on the side. */
export function familyItem(f: LogFamily): BarItem {
  return {
    key: `log:${f.family}`,
    label: f.family,
    value: f.visits,
    hint: f.bots ? `+ ${fmtInt(f.bots)} bots` : undefined,
  }
}

/** One referring host as nginx counted it — the row that makes the panel's
 *  claim checkable against the Umami list above it. */
export function hostItem(h: LogHost): BarItem {
  return { key: `loghost:${h.host}`, label: h.host, value: h.visits }
}

/** What each answer means. BarList only paints `tone` on a row that has a
 *  `hint`, so a warn without a hint is a no-op — every status needs one. */
const STATUS_MEANING: Record<number, string> = {
  410: 'story withdrawn on purpose',
  499: 'visitor left before we answered',
  500: 'our fault',
  502: 'our fault',
  503: 'our fault',
  504: 'our fault',
}

/** An answer to a referred human that nothing else on this page can see. */
export function statusItem(s: LogStatus): BarItem {
  return {
    key: `status:${s.status}`,
    label: String(s.status),
    value: s.visits,
    hint: STATUS_MEANING[s.status] ?? 'unexpected',
    tone: s.status === 410 || s.status >= 500 ? 'warn' : undefined,
  }
}

function Coverage({ log }: { log: LogCoverage }) {
  return (
    <>
      <div className="dash-lists">
        <div>
          <h3>Arrivals nginx saw</h3>
          <BarList items={log.families.map(familyItem)} empty="No referred arrival in this window." />
        </div>
        <div>
          <h3>Answers nothing else can see</h3>
          <BarList items={log.statuses.map(statusItem)} empty="Every referred visitor got a page." />
        </div>
      </div>
      <h3>Hosts nginx saw</h3>
      <BarList items={log.hosts.map(hostItem)} empty="No referred arrival in this window." />
      <p className="dash-note">
        The upper half of this panel is Umami: sessions whose browser ran our script. This half is nginx:
        every request that arrived with a foreign referer, over {log.covered_days} days of the log (
        {fmtInt(log.lines)} lines). Put one host against itself and the gap is the point — on 2026-09-19
        nginx answered 189 Google page arrivals and Umami recorded 62 views from 51 sessions. A visitor
        whose browser blocked the tracker, or who left before it loaded, exists only here. An arrival is
        a page request we answered 200 or 410: redirects are not counted, because each is followed by its
        own 200, and 4xx is not counted, because every 404 and 403 in this log is a forged referer
        probing /wp-admin/ — a real 404 raises an event the Problems panel already ranks. Bots and our
        own development server are out of every list. A 410 is a story we withdrew on purpose and Google
        still links to; it raises no event at all, which is why it is here and nowhere else.
      </p>
    </>
  )
}

/** Where the sessions came from, and how many arrivals the tracker missed. */
export function Sources({ state }: { state: Loaded<SourcesData> }) {
  const s = state.data
  return (
    <Panel question="Where do they come from, and how many do we miss?" wide>
      <Status state={state} />
      {s && (
        <>
          <div className="dash-lists">
            <div>
              <h3>Umami sessions by bucket</h3>
              <BarList
                items={bucketTotals(s.sources).map(([bucket, label, n]) => ({ key: bucket, label, value: n }))}
                empty="No sessions in this window."
              />
            </div>
            <div>
              <h3>Individual sources</h3>
              <BarList
                items={s.sources.slice(0, RAW_ROWS).map((r: SourceRow) => ({
                  key: r.source,
                  label: r.source,
                  value: r.sessions,
                  hint: `${fmtInt(r.views)} views`,
                }))}
                empty="No sources."
              />
            </div>
          </div>
          {s.log ? <Coverage log={s.log} /> : <p className="dash-note">{s.log_reason}</p>}
        </>
      )}
    </Panel>
  )
}
```

---

### Step 22 — `ancient-nerds-map/src/components/dashboard/Problems.tsx` · OWNER: PANEL:Problems

Two entries in the two `Record<ProblemKind, …>` maps and one sentence. `Record` makes a missing key a
compile error, which is the whole conflict-safety mechanism between parallel implementers.

before
```tsx
  js_error: 'high',
  broken_link: 'high',
  slow_page: 'mid',
```
after
```tsx
  js_error: 'high',
  broken_link: 'high',
  webgl_lost: 'high',
  slow_page: 'mid',
```

before
```tsx
  empty_search: 'Empty search',
}
```
after
```tsx
  empty_search: 'Empty search',
  webgl_lost: 'WebGL lost',
}
```

before
```tsx
            Everything counts people, not events. The score makes the kinds comparable: a JS error counts triple
            per visitor it reached, a dead link double, a slow page once per measurement.
```
after
```tsx
            Everything counts people, not events. The score makes the kinds comparable: a JS error and a lost
            WebGL context count triple per visitor they reached, a dead link double, a slow page once per
            measurement. The eight worst are listed. A story we withdrew on purpose answers 410 and raises no
            event, so retired links never appear here — the Sources panel counts those.
```

---

### Step 23 — `ancient-nerds-map/src/components/dashboard/TopContent.tsx` · OWNER: PANEL:TopContent

Three of the four lists are permanently empty — `story_open`, `paper_open` and `search` have never
fired, ever. Render only the lists that have rows, and say once why the others are absent. `item` and
`MAIN_ORIGIN` are unchanged.

```tsx
/** Why this panel is usually one list. Verified 2026-09-19: story_open,
 *  paper_open and search have never been recorded, not once. The search line
 *  names a bug on purpose — ticket T2 in the build plan. Describing a known
 *  defect as a design choice ("reports only once a visitor settles on a
 *  term") would be the worst sentence on the page. */
const NEVER_FIRED =
  'Only what the site actually reports is listed. story_open, paper_open and search have never fired, not once: the story and paper lists raise no open event yet, and search is swallowed by a bug in useSiteSearch (ticket T2) — so an empty search list here is our fault, not a finding.'

/** The most opened sites, and whatever else the site has actually reported. */
export function TopContent({ state }: { state: Loaded<ContentData> }) {
  const c = state.data
  const lists: Array<[string, ContentRow[], string]> = [
    ['Sites', c?.sites ?? [], 'No site opened.'],
    ['Search terms', c?.searches ?? [], 'No search.'],
    ['Stories', c?.stories ?? [], 'No story opened.'],
    ['Papers', c?.papers ?? [], 'No paper opened.'],
  ]
  const filled = lists.filter(([, rows]) => rows.length > 0)
  return (
    <Panel question="What gets opened, what gets searched?" wide>
      <Status state={state} />
      {c && (
        <>
          {filled.length === 0 ? (
            <p className="dash-empty">Nothing was opened in this window.</p>
          ) : (
            <div className="dash-lists">
              {filled.map(([title, rows, empty]) => (
                <div key={title}>
                  <h3>{title}</h3>
                  <BarList items={rows.map(item)} empty={empty} />
                </div>
              ))}
            </div>
          )}
          <p className="dash-note">{NEVER_FIRED}</p>
        </>
      )}
    </Panel>
  )
}
```

---

### Step 24 — `ancient-nerds-map/src/pages/DashboardPage.tsx` · OWNER: PAGE *(lands after every component)*

**24a. Docstring line 2:** `eight panels` → `twelve panels`.

**24b.** Replace the component import block and the type import block:

```tsx
import { FeedbackInbox } from '../components/dashboard/FeedbackInbox'
import { GlobeReach } from '../components/dashboard/GlobeReach'
import { LiveNow } from '../components/dashboard/LiveNow'
import { Members } from '../components/dashboard/Members'
import { Paths } from '../components/dashboard/Paths'
import { Problems } from '../components/dashboard/Problems'
import { Pulse } from '../components/dashboard/Pulse'
import { Scrapers } from '../components/dashboard/Scrapers'
import { SessionTypes } from '../components/dashboard/SessionTypes'
import { Sources } from '../components/dashboard/Sources'
import { TopContent } from '../components/dashboard/TopContent'
import type {
  ClustersData,
  ContentData,
  CountriesData,
  FeedbackData,
  GlobeData,
  JourneysData,
  LiveData,
  MapData,
  MembersData,
  Overview,
  ProblemsData,
  SourcesData,
} from '../components/dashboard/types'
import { useStats } from '../components/dashboard/useStats'
import { VisitorMap } from '../components/dashboard/VisitorMap'
```

**24c.** Replace the hook block and the panel array:

```tsx
  const [days, setDays] = useState<Days>(7)
  const overview = useStats<Overview>(`overview?days=${days}`)
  const map = useStats<MapData>('map?days=1')
  // Fixed windows (now / today / 7 / 30) — the range switch does not touch them.
  const countries = useStats<CountriesData>('countries')
  // Fixed 30-minute window, same 60 s cadence as everything else on the page.
  const live = useStats<LiveData>('live')
  const globe = useStats<GlobeData>(`globe?days=${days}`)
  // Five minutes: a scraper fingerprint does not change from minute to minute,
  // and this is the one query that has to sort every event in the window.
  const clusters = useStats<ClustersData>(`clusters?days=${days}`, 300_000)
  const content = useStats<ContentData>(`content?days=${days}`)
  const feedback = useStats<FeedbackData>('feedback?days=30')
  const sources = useStats<SourcesData>(`sources?days=${days}`)
  const journeys = useStats<JourneysData>(`journeys?days=${days}`)
  const problems = useStats<ProblemsData>(`problems?days=${days}`)
  // Five minutes, all-time counts: five members do not move in sixty seconds.
  const members = useStats<MembersData>('members', 300_000)
  // `members` is deliberately not in this array. It is the only route on a
  // different database behind a different dependency, and one hiccup there must
  // not replace the other eleven panels with "Session expired".
  const panels = [overview, countries, map, live, globe, clusters, content, feedback, sources, journeys, problems]
  const unauthorized = panels.some(s => s.error === 'unauthorized')
```

**24d.** Replace the grid:

```tsx
        <div className="dash-grid">
          <Pulse state={overview} countries={countries} />
          <LiveNow state={live} />
          <GlobeReach state={globe} />
          <Scrapers state={clusters} overview={overview} />
          <Problems state={problems} />
          <VisitorMap state={map} />
          <Sources state={sources} />
          <SessionTypes state={overview} />
          <Members state={members} />
          <Paths state={journeys} />
          <TopContent state={content} />
          <FeedbackInbox state={feedback} />
        </div>
```

**24e.** Under the 7 / 30 range switch, add one sentence — the switch is inert for four of the twelve
panels and, until 2026-10-17, returns identical numbers for the other eight. Without this line a
founder concludes the switch is broken, which is the correct conclusion from the evidence on screen:

```tsx
        <p className="dash-note">
          The range drives eight panels. Live now, Who is here, Members and Feedback have fixed windows
          of their own. Until 17 October both settings return the same numbers everywhere — the tracker's
          first event is 17 September.
        </p>
```

8 wide panels plus two complete narrow pairs (GlobeReach+Scrapers, SessionTypes+Members): zero
half-empty desktop cells, and both pairs are height-balanced. On a phone the source order is the
reading order and the five things that decide whether the product works come first.

---

### Step 25 — `ancient-nerds-map/src/styles/dashboard.css` · OWNER: CSS

**25a. Edit lines 327-341 IN PLACE.** Do not append a second `.dash-spark` block:
`.dash-spark rect` has specificity (0,1,1) and beats any appended class selector at (0,1,0), so an
appended ramp renders as flat green — and the project's own rule is to restyle in place, never to
rely on the cascade.

before
```css
.dash-spark {
  display: block;
  width: 100%;
  height: 56px;
  margin-top: 14px;
}

.dash-spark rect {
  fill: var(--dash-green);
  fill-opacity: 0.85;
}

.dash-spark rect:hover {
  fill-opacity: 1;
}
```
after
```css
/* The strip stacks two classes per hour: confirmed-human sessions on the
   baseline in the panel's green, everything else above them in the same green
   at the strength the low-severity dot already uses. Two segments, not three
   — at 390 px a bar is 4.9 px wide and one session at the 48-hour peak is
   6 px tall, below the size at which a colour difference survives. The AI
   count travels as a number in the legend and in each bar's tooltip. */
.dash-spark {
  display: block;
  width: 100%;
  height: 72px;
  margin-top: 14px;
}

.dash-spark rect {
  fill: var(--dash-dot-low);
}

.dash-spark rect.dash-spark-human {
  fill: var(--dash-green);
}

.dash-spark rect:hover {
  fill: var(--dash-paper);
}
```

**25b. Append at the end of the file, and nowhere else:**

```css
/* ── Live visitors ──────────────────────────────────────────────────── */

.dash-live {
  list-style: none;
}

/* Four tracks on the first line, the headline on a line of its own — exactly
   the mechanism that makes .dash-problem survive 390 px. A live page_title is
   72 characters on average and 138 at worst; on one line it would get under
   110 px of the 334 px content box, and 292 px at the 720 px breakpoint. */
.dash-live-row {
  display: grid;
  grid-template-columns: 10px 18px minmax(0, 1fr) auto;
  gap: 2px 8px;
  align-items: baseline;
  padding: 9px 0;
  border-top: 1px solid var(--dash-line-soft);
}

.dash-live-row:first-child {
  border-top: 0;
  padding-top: 0;
}

.dash-dot--live {
  background: var(--dash-green);
}

.dash-live-who {
  font-family: var(--dash-mono);
  font-size: 0.65rem;
  color: var(--dash-muted);
}

.dash-live-here {
  font-family: var(--dash-mono);
  font-size: 0.8rem;
  text-align: right;
  white-space: nowrap;
}

.dash-live-page {
  grid-column: 3 / -1;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  font-size: 0.9rem;
  overflow-wrap: anywhere;
}

/* The noun in an empty sentence: "Last seen 12 min ago on <headline>." */
.dash-empty b {
  color: var(--dash-paper);
  font-weight: 500;
}

/* A tile row followed by a list needs the air an h3 would have given it. */
.dash-tiles + .dash-bars {
  margin-top: 14px;
}
```

No other CSS is added. `GlobeReach`, `Scrapers` and `Members` are built from `.dash-tiles`,
`.dash-bars` and `.dash-note`, which exist and already pass 390 px. Nothing here introduces amber or
red as a data colour; red stays an action and a hover cue.

---

### Step 26 — `scripts/dashboard_screenshots.py` · OWNER: FIXTURES *(runs after `npm run build`)*

This is the acceptance test. Owner ruling R7 is answered here and only here: **no render tooling is
added; every production state, including every empty one, gets a fixture.**

**It is a local gate, not a CI gate.** `.github/workflows/ci.yml`'s `lint-frontend` job runs
`npm run type-check`, `npx knip`, `npm run test`, `npm run build`, `npx size-limit` and
`npm run build:ssr` — and never this script. So the 390 px overflow rule and the height budget are
enforced only when the implementer runs verification row 19. Wiring it into CI needs a playwright
chromium install in that job, which is CI configuration and therefore the owner's call: **ticket T9.**
Do not describe this step as blocking the deploy; it does not.

**26a.** Replace `hour_buckets()`:

```python
def hour_buckets(hours: int = 48) -> list[dict]:
    """Sessions per hour, newest last — always `hours` of them, including the
    empty ones, which is the bug the fixed axis fixes."""
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(hours):
        t = now - timedelta(hours=hours - 1 - i)
        sessions = int(6 + 11 * (1 + math.sin((t.hour - 8) / 24 * 2 * math.pi)) + (i % 7))
        if t.hour in (3, 4):
            sessions = 0  # an empty hour draws as an empty bar, never as a gap
        out.append(
            {
                "hour": t.isoformat(),
                "sessions": sessions,
                "human": sessions // 3,
                "ai": 1 if t.hour == 15 else 0,
            }
        )
    return out
```

**26b.** `FIXTURES["overview"]` — drop `today`/`yesterday`, add `ai`, new `hours`:

```python
    "overview": {
        "days": 7,
        "sessions": {"all": 1893, "human": 1121, "ai": 214},
        "types": {"reader": 402, "explorer": 388, "researcher": 97, "searcher": 143, "other": 91},
        "hours": hour_buckets(),
    },
```

**26c.** `FIXTURES["journeys"]` gains two keys after `chains`:

```python
        "pages": {
            "sessions": 612,
            "one_page": 291,
            "moving": 321,
            "entries": [
                {"page": "story", "sessions": 248, "stopped": 151},
                {"page": "site", "sessions": 137, "stopped": 44},
                {"page": "globe", "sessions": 96, "stopped": 11},
                {"page": "country", "sessions": 61, "stopped": 61},
                {"page": "home", "sessions": 42, "stopped": 8},
                {"page": "search", "sessions": 14, "stopped": 5},
            ],
            "exits": [
                {"page": "site", "sessions": 219, "views": 588},
                {"page": "story", "sessions": 186, "views": 401},
                {"page": "globe", "sessions": 92, "views": 173},
                {"page": "country", "sessions": 61, "views": 74},
                {"page": "paper", "sessions": 20, "views": 31},
            ],
        },
        "outbound": [
            {"host": "youtube.com", "clicks": 148, "visitors": 121},
            {"host": "journals.plos.org", "clicks": 39, "visitors": 37},
            {"host": "getty.edu", "clicks": 12, "visitors": 12},
            {"host": "en.wikipedia.org", "clicks": 7, "visitors": 1},
        ],
```

**26d.** New helper above `FIXTURES`, and four new fixture keys after `"countries"`:

```python
def live_rows() -> list[dict]:
    """Six visitors. One headline at the live maximum (138 characters), one
    visitor Umami could not place, one who has had the page open over an
    hour — the three cases the row layout has to survive at 390 px."""
    titles = [
        "Inca polygonal masonry in Cusco, Sacsayhuamán and the highland sites: massive irregular blocks fitted without any mortar",
        "Göbekli Tepe",
        "Database",
        "Nan Madol",
        "Bronze age shipwreck off Crete",
        "Puma Punku",
    ]
    countries = ["DE", "US", None, "IN", "BR", "GB"]
    heres = [42, 380, 4100, 95, 12, 1730]
    return [
        {
            "session": f"a1b2c3d{i}",
            "country": countries[i],
            "device": "mobile" if i % 2 else "laptop",
            "browser": "chrome" if i % 3 else "safari",
            "page": "site",
            "title": titles[i],
            "here": heres[i],
            "last_seen": (datetime.now(UTC) - timedelta(minutes=i * 3)).isoformat(),
        }
        for i in range(6)
    ]
```

```python
    "live": {
        "window_minutes": 30,
        "lookback_hours": 24,
        "total": 6,
        "shown": 6,
        "visitors": live_rows(),
        "last": None,
    },
    "globe": {
        "loads": 412,
        "reached": 297,
        "gave_up": 115,
        "sessions": {"all": 288, "reached": 214},
        "ready_ms": {"min": 3120.0, "median": 8940.0, "max": 41220.0, "samples": 297},
    },
    "clusters": {
        "min_ids": 3,
        "flagged": 418,
        "clusters": [
            {"screen": "1366x1366", "browser": "chrome", "os": "Mac OS", "sessions": 243},
            {"screen": "1280x1200", "browser": "chrome", "os": "Windows 10", "sessions": 131},
            {"screen": "1920x1080", "browser": "chrome", "os": "Linux", "sessions": 44},
        ],
    },
    "members": {
        "members": 148,
        "founders": 2,
        "newest_signup": "2026-09-18T21:04:00+00:00",
        "last_login": "2026-09-19T08:12:00+00:00",
        "acts": [
            {"act": "Likes", "n": 312, "by": 96, "at": "2026-09-19T07:55:00+00:00"},
            {"act": "Bookmarks", "n": 188, "by": 71, "at": "2026-09-18T19:20:00+00:00"},
            {"act": "Lyra answers", "n": 1204, "by": 44, "at": "2026-09-19T08:41:00+00:00"},
            # One account, to prove the singular in actItem's hint renders.
            {"act": "Research requests", "n": 61, "by": 1, "at": "2026-09-16T11:02:00+00:00"},
        ],
    },
```

`total` is 6, not 9: with `LIVE_LIMIT = 6` a response can never say "9 in the window, 6 shown" while
returning six rows, and a fixture that describes a state the API cannot emit gates nothing.

**26e.** `FIXTURES["sources"]` — `views` on every row plus the whole `log` block:

```python
    "sources": {
        "sources": [
            {"source": "google.com", "family": "google", "sessions": 612, "views": 903},
            {"source": "direct", "family": "direct", "sessions": 498, "views": 1204},
            {"source": "discord.com", "family": "discord.com", "sessions": 143, "views": 311},
            {"source": "youtube", "family": "youtube", "sessions": 96, "views": 142},
            {"source": "chatgpt.com", "family": "ai", "sessions": 61, "views": 88},
            {"source": "reddit.com", "family": "reddit.com", "sessions": 44, "views": 61},
            {"source": "bing.com", "family": "search", "sessions": 39, "views": 52},
            {"source": "t.co", "family": "t.co", "sessions": 12, "views": 14},
        ],
        "log": {
            "covered_from": "2026-08-21T06:19:00+00:00",
            "covered_days": 29.14,
            "lines": 8842,
            "families": [
                {"family": "search", "visits": 2914, "bots": 411},
                {"family": "social", "visits": 388, "bots": 44},
                {"family": "other", "visits": 204, "bots": 129},
                {"family": "ai", "visits": 97, "bots": 3},
            ],
            # REPORT_ROWS = 8, so eight is the widest this list ever gets.
            "hosts": [
                {"host": "google.com", "visits": 2801},
                {"host": "discord.com", "visits": 291},
                {"host": "chatgpt.com", "visits": 88},
                {"host": "bing.com", "visits": 74},
                {"host": "duckduckgo.com", "visits": 39},
                {"host": "perplexity.ai", "visits": 21},
                {"host": "reddit.com", "visits": 14},
                {"host": "news.ycombinator.com", "visits": 9},
            ],
            # Only is_bad_answer() statuses: no 301 (a redirect is followed by
            # its own 200) and no 404 (every live one is a forged referer).
            "statuses": [
                {"status": 410, "visits": 188},
                {"status": 499, "visits": 27},
                {"status": 500, "visits": 2},
            ],
        },
        "log_reason": None,
    },
```

**26f.** Insert one row into `FIXTURES["problems"]["problems"]`. The list at HEAD is
57 / 42 / 38 / 24 / 17 / 11 (`scripts/dashboard_screenshots.py:235-274`), so a score of 48 goes
**between the 57 (`js_error`) and the 42 (`slow_page · story · LCP`)** — first below the top row — and
the list reads 57 / 48 / 42 / 38 / 24 / 17 / 11:

```python
            {
                "kind": "webgl_lost",
                "label": "globe never started",
                "score": 48,
                "detail": "16 visitors, 19× — no_shader",
            },
```

The `PROBLEM_VISITORS` loop below needs no change: it is modulo five over whatever is in the list.

**26g.** New `EMPTY_FIXTURES`, a height budget, a fixture-parameterised route handler, and a third
pass. Add after `FIXTURES` and its `PROBLEM_VISITORS` loop:

```python
#: Every panel's day-one production state, which no unit test can render: the
#: repo has vitest but no jsdom and no @testing-library/react, so a state that
#: is not in a fixture is a state nothing checks (owner ruling, 2026-09-19).
#: Measured the same day: nobody in the live window during 20 % of all
#: minutes, no clusters at all as soon as the scrapers leave, no referral log
#: on any development box, and a members panel whose every act reads zero.
EMPTY_FIXTURES: dict[str, dict] = {
    "countries": {
        w: {"sessions": 0, "all": 0, "countries": []} for w in ("now", "today", "d7", "d30")
    },
    "overview": {
        "days": 7,
        "sessions": {"all": 0, "human": 0, "ai": 0},
        "types": {},
        "hours": [{**h, "sessions": 0, "human": 0, "ai": 0} for h in hour_buckets()],
    },
    "map": {"points": []},
    "content": {"sites": [], "stories": [], "papers": [], "searches": []},
    "feedback": {"items": []},
    "journeys": {
        "chains": [],
        "pages": {"sessions": 0, "one_page": 0, "moving": 0, "entries": [], "exits": []},
        "outbound": [],
    },
    "problems": {"problems": []},
    "sources": {
        "sources": [],
        "log": None,
        "log_reason": (
            "nginx's referral log is not readable at /app/logs/referrals.log. "
            "It is bind-mounted read-only into the API containers on the VPS "
            "(docker-compose.yml, ./logs:/app/logs:ro); a development box has none."
        ),
    },
    "live": {
        "window_minutes": 30,
        "lookback_hours": 24,
        "total": 0,
        "shown": 0,
        "visitors": [],
        "last": {
            "session": "9f0e1d2c",
            "country": "IN",
            "device": "mobile",
            "browser": "chrome",
            "page": "story",
            "title": "Ramp construction theories for the great pyramid",
            "here": 2220,
            "last_seen": "2026-09-19T07:30:00+00:00",
        },
    },
    "globe": {
        "loads": 0,
        "reached": 0,
        "gave_up": 0,
        "sessions": {"all": 0, "reached": 0},
        "ready_ms": {"min": None, "median": None, "max": None, "samples": 0},
    },
    "clusters": {"min_ids": 3, "flagged": 0, "clusters": []},
    "members": {
        "members": 5,
        "founders": 2,
        "newest_signup": "2026-08-28T01:33:22+00:00",
        "last_login": "2026-09-19T08:12:00+00:00",
        "acts": [
            {"act": "Likes", "n": 0, "by": 0, "at": None},
            {"act": "Bookmarks", "n": 0, "by": 0, "at": None},
            {"act": "Lyra answers", "n": 0, "by": 0, "at": None},
            {"act": "Research requests", "n": 0, "by": 0, "at": None},
        ],
    },
}

#: The phone page's height budget. MEASURED, not chosen - see step 26i.
#: The eight-panel page was 390 x 5064 CSS px (off the gate's own PNG on
#: 2026-09-19). Twelve panels plus a LiveNow list, three more BarLists in
#: Paths, two more plus a five-line note in Sources, two tiles and a note each
#: in GlobeReach and Members, a strip grown 56 -> 72 px and a seventh Problems
#: row land somewhere around 7 000-8 000, which is inside this gate's own
#: noise. Setting it by arithmetic would make the first honest run red.
MAX_MOBILE_HEIGHT = 0  # step 26i replaces this with the measured value
```

Replace `answer_stats`:

```python
def route_handler(fixtures: dict[str, dict]):
    def answer_stats(route: Route) -> None:
        name = route.request.url.split("/api/stats/", 1)[1].split("?", 1)[0]
        route.fulfill(json=fixtures[name])

    return answer_stats
```

Replace the loop body in `main()`:

```python
            for name, viewport, scale, fixtures in (
                ("dashboard-mobile.png", {"width": 390, "height": 844}, 2, FIXTURES),
                ("dashboard-mobile-empty.png", {"width": 390, "height": 844}, 2, EMPTY_FIXTURES),
                ("dashboard-desktop.png", {"width": 1280, "height": 800}, 1, FIXTURES),
            ):
                page = browser.new_page(viewport=viewport, device_scale_factor=scale)
                page.route("**/api/stats/**", route_handler(fixtures))
                page.goto(URL, wait_until="networkidle")
                # The strip, not .dash-map-dot: the map has no dots in the
                # empty pass, and the strip is the first thing every pass draws.
                page.wait_for_selector(".dash-spark")
                page.evaluate("document.fonts.ready")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                height = page.evaluate("document.body.scrollHeight")
                page.screenshot(path=str(OUT / name), full_page=True)
                print(f"{name}: {viewport['width']}px, overflow {overflow}px, height {height}px")
                if overflow > 0:
                    raise SystemExit(f"{name}: the page scrolls sideways by {overflow}px")
                if MAX_MOBILE_HEIGHT and viewport["width"] == 390 and height > MAX_MOBILE_HEIGHT:
                    raise SystemExit(
                        f"{name}: the phone page is {height}px tall, "
                        f"over the {MAX_MOBILE_HEIGHT}px budget"
                    )
                page.close()
```

**26i. Set `MAX_MOBILE_HEIGHT` in a second commit, from the measurement.** This step is the only one
in the plan that is deliberately two commits:

1. Land 26a-26h with `MAX_MOBILE_HEIGHT = 0`. The `if MAX_MOBILE_HEIGHT and …` guard means the gate
   is off; the script still prints `height` for all three passes.
2. Run `python scripts/dashboard_screenshots.py`, take the **larger** of the two 390 px heights, round
   it up to the next hundred and add ten per cent, and commit that number with the measurement in the
   `#:` block: `#: Measured 2026-09-19 with twelve panels: N px full and M px empty; the budget is the
   larger plus ten per cent.`

Doing it the other way round — asserting a guessed 7 000 in the same commit that adds four panels and
six lists — makes the gate's first run a coin toss, and a gate that goes red on arrival gets deleted
rather than believed. **If the measured height exceeds ~8 000, stop and re-open B5 (the three-band
collapse) with the owner, rather than raising the budget to fit.** B5's rejection rests on this
budget holding.

**26h.** Module docstring: add the third file and the height gate.

before
```
Writes docs/reports/screenshots/dashboard-mobile.png (390 x 844, 2x) and
dashboard-desktop.png (1280 x 800) and fails when the phone layout scrolls
sideways.
```
after
```
Writes docs/reports/screenshots/dashboard-mobile.png, dashboard-mobile-empty.png
(both 390 x 844, 2x) and dashboard-desktop.png (1280 x 800), and fails when the
phone layout scrolls sideways or grows past MAX_MOBILE_HEIGHT. The empty pass is
the repo's only check of the states production actually shows today: there is no
jsdom and no @testing-library/react, so nothing renders a component in a test.
```

---

### Step 27 — `tests/pipeline/test_stats_analysis.py` · OWNER: TESTS

Thirteen new tests. `ev()` already builds `SQL_SESSION_EVENTS`-shaped rows and gains nothing.

| Test | Asserts |
|---|---|
| `test_is_ai_entry_reads_both_columns_and_both_vocabularies` | `is_ai_entry(None, "chatgpt.com")`, `is_ai_entry(None, "perplexity")`, `is_ai_entry("gemini.google.com")` are all True; `is_ai_entry(None, "youtube")` and `is_ai_entry("google.com")` are False. The first two are the live utm values; a rule against `AI_HOSTS` alone finds one of them. |
| `test_source_family_buckets_a_bare_utm_label_as_ai` | `source_family("perplexity") == "ai"` and `source_family(None, "chatgpt.com") == "ai"`, while `source_family(None, "youtube") == "youtube"` and `source_family("google.com") == "google"`. The first call has one positional argument on purpose — that is how `/sources` calls it. |
| `test_a_session_without_a_page_view_is_not_human` | A session of one `scroll_depth` and no page view folds to `human is False`; adding one page view makes it True. Names the eight live sessions in the docstring. |
| `test_pages_is_the_length_of_page_steps` | After a two-page fold, `s.pages == 2 == len(s.page_steps)`, `s.page_steps == ["story", "site"]`, and `with pytest.raises(AttributeError): s.pages = 3`. |
| `test_page_steps_keep_only_pages_while_steps_interleave_events` | A session that visits `/search.html` and fires a `search` event has `page_steps == ["search"]` and `steps == ["search", "search"]`. This is why the two lists exist. |
| `test_hourly_sessions_draws_every_hour_even_the_empty_ones` | Rows in two of three hours produce `len(out) == hours`, the hours ascend by exactly one hour, the last bucket is `until`'s hour, and the middle bucket is `{"sessions": 0, "human": 0, "ai": 0}`. |
| `test_hourly_sessions_splits_human_from_the_rest_and_counts_ai_separately` | One human session and one unconfirmed session in the same hour give `sessions == 2, human == 1`; a session entered with `utm_source="chatgpt.com"` also raises `ai` to 1 while staying inside `sessions`. |
| `test_hourly_sessions_ignores_rows_outside_the_strip` | A row 100 hours old changes nothing. |
| `test_globe_funnel_counts_loads_and_reaches` | Two rows (`views 3 / ready 1` and `views 1 / ready 0`) give `loads 4, reached 1, gave_up 3, sessions {"all": 2, "reached": 1}`. A row with `views 0` is dropped and a row with `ready 2, views 1` counts one. |
| `test_globe_funnel_hides_the_middle_below_the_sample_floor` | Four samples give `median is None` but keep `min`, `max` and `samples == 4`; five samples fill `median`. |
| `test_clusters_report_the_flagged_total_and_the_fingerprints` | Two rows of 22 and 16 give `flagged == 38`, `min_ids` travels through, and the rows keep their `screen`/`browser`/`os`. Docstring names the live measurement. |
| `test_entry_exit_pages_count_landings_stops_and_one_page_sessions` | Two human sessions (`story→site` and `story` only) give `sessions 2, one_page 1, moving 1`; `entries[0] == {"page": "story", "sessions": 2, "stopped": 1}`; `exits` carries `views` and **no `share` key**. There is **no `no_page` key** — assert `"no_page" not in out`, with the reason in the docstring: `human` is False without a page view, so the branch that used to count it is unreachable and a permanent `0 of 46` on the panel was the bug. |
| `test_entry_exit_pages_ignore_sessions_that_are_not_human` | An unconfirmed one-page session appears in neither list, **and** a session with one `scroll_depth` and no page view at all is absent from `sessions` — the second half is what makes the missing `no_page` key correct rather than merely convenient. |
| `test_outbound_links_fold_from_the_session_rows` | Two `outbound_click` rows on `youtube.com` from one session and one from another give `[{"host": "youtube.com", "clicks": 3, "visitors": 2}]`. Drift must fail loudly and the test pins **which** failure: a row with `"data": None` (the realistic case — `SQL_SESSION_EVENTS`' `data` subquery is NULL when the event has no `event_data` row) raises `TypeError`, and a row with `"data": {}` raises `KeyError`. Assert both with `pytest.raises`, so nobody adds a silent guard later. |
| `test_without_brand_keeps_a_title_that_carries_no_brand` | `without_brand("Göbekli Tepe \| Ancient Nerds") == "Göbekli Tepe"`, `without_brand("Database - Ancient Nerds")` is unchanged (one of two live titles that do not end in the brand), and an inner pipe survives. |
| `test_live_row_uses_the_same_visitor_shape_and_id_rule` | `live_row()`'s first four keys equal `_last_visitor()`'s on the same data, the session is cut to `SESSION_ID_CHARS`, `here` is whole seconds, and `page` comes from `page_type`. |
| `test_problems_rank_a_lost_webgl_context_by_the_visitors_it_reached` | `problems(..., webgl=[{"phase": "loading", "reason": "no_shader", "n": 19, "sessions": 16, ...}])` yields a `webgl_lost` row with `score == 48` and `label == "globe never started"`. An unknown phase raises `KeyError` — asserted, so the label table stays honest. |
| `test_problems_list_eight_rows_by_default` | Twelve error rows produce eight problems; `limit=5` still produces five. |

Existing tests that must keep passing untouched: `test_sessions_carry_entry_scroll_depth_and_are_ordered_by_start`
(`early.pages == 1` now reads the property; `early.entry == "youtube"` still holds because `youtube`
is neither an AI host nor an AI label) and every `problems()` test (each call site already passes by
keyword, so `webgl` slots in between `searches` and `limit` safely — verified across all **13** call
sites repo-wide: `git grep -n 'problems(' -- api pipeline tests | grep -v 'def problems'`).

---

### Step 28 — `tests/pipeline/test_referral_log.py` (new) · OWNER: TESTS

| Test | Asserts |
|---|---|
| `test_referrer_host_reads_a_scheme_less_referer` | `referrer_host("www.google.com", "GET /x") == "google.com"` and `referrer_host("binance.com/wp-admin/", "GET /x") == "binance.com"`. 55 of 407 live lines are this shape and `urlsplit().hostname` returns None for all of them. |
| `test_referrer_host_reads_the_utm_source_when_there_is_no_referer` | `referrer_host("", "GET /x?utm_source=perplexity") == "perplexity.ai"` and `referrer_host("", "GET /x?utm_source=discord&utm_medium=bot") == "discord.com"` — the alias table, because neither tag carries a dot and the second is our own bot's link. |
| `test_an_unknown_utm_label_is_kept_as_it_is` | `referrer_host("", "GET /x?utm_source=newsletter") == "newsletter"`. The old CLI dropped a label that was not a known host; this module keeps it, so a campaign we invent tomorrow is visible rather than silently discarded. The test exists because it is the one behaviour change `scripts/referral_report.py` inherits (see step 29). |
| `test_referrer_host_drops_the_port_and_the_www` | `referrer_host("http://localhost:5199/globe.html", "GET /api/x") == "localhost"`. |
| `test_our_own_dev_server_is_not_a_referral` | `parse_lines` skips a localhost line entirely — 47 of 407 live lines. |
| `test_parse_lines_skips_a_half_line_and_broken_json` | A leading fragment, a `not json{` line and a well-formed line yield exactly one `Visit`. |
| `test_parse_lines_keep_the_logged_offset` | `Visit.at` of `"2026-09-17T12:00:00+02:00"` equals `10:00 UTC` — `strptime` without the offset would be two hours out for half the year. |
| `test_coverage_report_counts_only_answered_page_arrivals` | Six visits — a human page 200, a bot page 200, a human asset 200, a human page 410, a human page **404** and a human page **301** — give `families[0]["visits"] == 2` (the 200 and the 410), `families[0]["bots"] == 1`, `hosts[0]["visits"] == 2`, and `statuses == [{"status": 410, "visits": 1}]`. The 404 and the 301 appear **nowhere**. Docstring names the measurement: without this rule the live log puts `binance.com` second in `hosts` and 21 scanner 404s into `statuses`. |
| `test_coverage_report_counts_a_scanner_out_of_every_list` | A page request with a forged `binance.com` referer, an ordinary Chrome UA and a 404 leaves `families`, `hosts` and `statuses` all empty — the UA test is not what catches it. |
| `test_coverage_report_windows_the_visits` | A visit before `since` and one after `until` are both out; `covered_days` is measured from the oldest visit still in. |
| `test_read_visits_returns_none_when_the_log_is_missing` | With `REFERRAL_LOG_PATH` pointed at a non-existent file (monkeypatched module constant) `read_visits()` is None and `unavailable_reason()` names the path and the bind mount. |
| `test_read_visits_reads_only_the_tail` | With `MAX_TAIL_BYTES` monkeypatched small, a big temp file yields only the last lines and does not raise on the half line at the seek point. |
| `test_read_visits_does_not_reparse_within_the_minimum` | Two calls in a row parse once; the test asserts it by counting calls to a monkeypatched `parse_lines`. |
| `test_aggregate_counts_errors_only_with_all` | Mirrors the CLI's existing contract on `Visit`s. |

Module-level fixture: `autouse` reset of `referral_log._cache = None`, so cache state cannot leak
between tests.

---

### Step 29 — `tests/scripts/test_referral_report.py` · OWNER: TESTS *(same commit as step 3)*

**Seven** call sites, not five — `rr.aggregate(` appears at lines 47, 60, 72, 73, 83, 98 and 99.
Six of them change shape only: `rr.aggregate(lines, SINCE)` → `rr.aggregate(rl.parse_lines(lines),
SINCE)` with `from pipeline import referral_log as rl` at the top.

**The seventh changes behaviour and its assertion must be rewritten.**
`test_utm_source_ersetzt_fehlenden_referer_nur_fuer_bekannte_hosts` (lines 55-62) asserts
`"other" not in result` for `utm_source=newsletter`, which passes today only because
`source_host()` has a `"." in utm and family_of(utm) != "other"` gate. `referrer_host()` drops that
gate deliberately (B13: it is the same class of bug as the scheme-less referer — a source thrown away
because it does not look like a host). Replayed through the new module the same two lines give
`{'ai': {'chatgpt.com': {'human': 1}}, 'other': {'newsletter': {'human': 1}}}`.

Rename it to `test_utm_source_ersetzt_fehlenden_referer` and assert:

```python
    result = rr.aggregate(rl.parse_lines(lines), SINCE)
    assert result["ai"]["chatgpt.com"] == {"human": 1}
    # Ein unbekanntes utm-Label wird nicht mehr verworfen, sondern landet als
    # es selbst unter "other" - sonst ist eine eigene Kampagne unsichtbar.
    assert result["other"]["newsletter"] == {"human": 1}
```

`test_since_relativ_und_absolut` is untouched — `parse_since` stays in the script.
`test_ai_suche_social_und_rest_werden_nach_host_gezaehlt` keeps its German name: this file is
pipeline-internal and out of the English-only scope, which covers the dashboard and the strings the
backend renders into it.

---

### Step 30 — `tests/pipeline/test_members_stats.py` (new) · OWNER: TESTS

Both tests are DB-less. The panel's privacy boundary is asserted against the compiled SQL, which is
the only place a leak could appear.

| Test | Asserts |
|---|---|
| `test_the_member_query_never_selects_a_name_an_id_or_a_balance` | `str(members_query("933105341292486707").compile(dialect=postgresql.dialect()))` contains none of `username`, `discord_id`, `avatar_hash`, `credits`, `submitter_ip`. It does contain `discord_users`, `site_likes`, `site_bookmarks`, `token_usage_logs`, `research_requests` — and **not** `card_collections`, which lives under `api/` and may not be reached from here. |
| `test_the_founder_role_is_a_bound_parameter_not_a_literal` | The compiled SQL does not contain the literal role id, and `compile().params` has a value that equals `["933105341292486707"]`. This is what stops the `:founder_role::jsonb` bind-name truncation the raw-SQL draft would have hit. |
| `test_shape_members_stamps_naive_timestamps_as_utc` | `shape_members(SimpleNamespace(members=5, founders=2, newest_signup=datetime(2026, 8, 28, 1, 33, 22), last_login=None, n0=2, by0=1, at0=None, n1=0, by1=0, at1=None, n2=126, by2=2, at2=None, n3=59, by3=2, at3=None))` returns `newest_signup == "2026-08-28T01:33:22+00:00"`, `last_login is None`, and four acts whose labels are exactly `ACTS`' labels in order, each carrying its own `by`. |
| `test_the_founder_login_is_filtered_to_founders` | The compiled SQL contains the `roles @> …` predicate **twice** — once for the `founders` count and once for the `last_login` subquery — so the date under the "Founders" tile cannot be another member's. (Today the two dates happen to be the same row, `2026-09-19 06:26:02`; that is why this needs a test and not an eyeball.) |
| `test_every_act_carries_a_distinct_actor_count` | The compiled SQL contains four `count(DISTINCT` fragments, one per act. Without them the panel prints "Research requests 59" where the truth is "59 by 2 accounts, 57 of them one". |

---

### Step 31 — `tests/api/test_founders_stats_routes.py` · OWNER: TESTS

**31a.** `test_router_is_mounted_under_api_stats` — the name tuple becomes:

```python
    for name in ("overview", "countries", "map", "live", "globe", "clusters", "content", "feedback", "sources", "journeys", "problems", "members"):  # fmt: skip
```

**31b. Delete** `test_overview_windows_are_today_yesterday_and_the_requested_days` — the two
`SQL_OVERVIEW` blocks it pins are gone.

**31c. Rewrite** `test_overview_shapes_the_rows`:

```python
def test_overview_runs_one_query_and_answers_four_keys(monkeypatch):
    fetch = Fetch(**{"ORDER BY e.session_id": []})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.overview(days=7, _session=SESSION))
    assert set(out) == {"days", "sessions", "types", "hours"}
    assert out["sessions"] == {"all": 0, "human": 0, "ai": 0}
    # The strip is a fixed axis, not one bar per hour that had events.
    assert len(out["hours"]) == fs.HOURLY_STRIP_HOURS
    assert len(fetch.calls) == 1
```

**31d.** Extend `test_overview_counts_and_types_come_from_the_session_rows` — drop the
`live_sessions` and `date_trunc('hour'` markers from the `Fetch`, add an assertion that a session
entered with `utm_source="chatgpt.com"` raises `out["sessions"]["ai"]` to 1 while `all` is unchanged.

**31e.** New tests:

| Test | Asserts |
|---|---|
| `test_countries_still_slice_one_fetch_into_four_windows` | The existing body, plus `fr._country_windows.__wrapped__` is used so the Redis cache cannot make the assertion order-dependent (call the unwrapped helper directly). |
| `test_globe_asks_only_for_the_globe_path` | The single call's `params == {"path": fr.GLOBE_PATH}` and the response keys are exactly `{"loads","reached","gave_up","sessions","ready_ms"}`. |
| `test_clusters_pass_the_minimum_id_count` | One call, `params == {"min_ids": fr.CLUSTER_MIN_IDS}`, and `out["min_ids"] == 3`. No session total is returned — the panel divides by `/overview`. |
| `test_live_splits_the_here_and_now_from_the_last_visitor` | Two `SQL_LIVE` rows, one 3 minutes old and one 9 hours old, give `total == 1`, `shown == 1`, one visitor and `last is None`; with only the 9-hour row, `total == 0` and `last` is that row. One query either way, and its window is `LIVE_LOOKBACK`. |
| `test_live_caps_the_list_at_the_limit` | Eight in-window rows give `total == 8`, `shown == fr.LIVE_LIMIT`, `len(visitors) == fr.LIVE_LIMIT`. |
| `test_journeys_carry_chains_entries_exits_and_outbound_from_one_fetch` | `set(out) == {"chains", "pages", "outbound"}` and `len(fetch.calls) == 1`. |
| `test_problems_run_six_queries_in_one_window` | The existing body with `len(fetch.calls) == 6`, one window, and a `webgl_lost` row in the ranking. |
| `test_sources_carry_views_and_the_log_coverage` | With `referral_log.read_visits` monkeypatched to a list, `out["log"]` is a dict and `out["log_reason"] is None`; with it monkeypatched to `None`, `out["log"] is None` and `out["log_reason"]` names the path. Every source row carries `views`. |
| `test_sources_bucket_a_bare_perplexity_as_ai` | A `{"source": "perplexity", "sessions": 1, "views": 1}` row comes back with `family == "ai"` — the live row that falls to "Other" today. |
| `test_members_never_leak_a_name` | `members_stats.member_totals` monkeypatched to return a dict containing a `username` key would fail the route's own contract — instead assert the route calls `member_totals(db, jwt_auth.FOUNDER_ROLE_ID)` and returns its value verbatim, and that `set(out)` is exactly the six documented keys. |

**31f. Two existing tests break and are not covered by 31a-31e. Fix them in the same commit:**

* `test_sources_carry_the_family` (line 218) → `KeyError: 'views'`, because its four fixture rows at
  lines 220-223 carry only `source`/`sessions` and step 10h reads `r["views"]`. **Delete this test**
  and let `test_sources_carry_views_and_the_log_coverage` (31e) carry its assertions — it asserts the
  family mapping *and* `views` on every row, so keeping both is two tests for one rule.
* `test_journeys_returns_the_chains_of_the_requested_window` (line 257) → its
  `assert out == {"chains": [...]}` (line 262) now sees the added `pages` and `outbound` keys.
  **Delete it** in favour of `test_journeys_carry_chains_entries_exits_and_outbound_from_one_fetch`
  (31e), and move its window assertion (`fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=14)`)
  into that test so the `days` plumbing keeps its coverage.

**31g.** `Fetch` markers (canonical, one per query):

| Query | Marker |
|---|---|
| `SQL_SESSION_EVENTS` | `"ORDER BY e.session_id"` |
| `SQL_GLOBE` | `"'globe_ready'"` |
| `SQL_CLUSTERS` | `"date_trunc('minute'"` |
| `SQL_WEBGL_LOST` | `"'webgl_lost'"` |
| `SQL_LIVE` | `"AS last_seen"` |
| `SQL_NOT_FOUND` / `SQL_VITALS` / `SQL_ERRORS` / `SQL_CONTENT` | `"'not_found'"` / `"'vital'"` / `"'js_error'"` / `"'site_open', 'story_open'"` |
| `SQL_SOURCES` | `"nullif(utm_source"` |

`"live_sessions"` and `"date_trunc('hour'"` are retired with their queries.

`SQL_SOURCES`' marker is **not** `"'direct'"`, and the claim that the old table was "collision-free,
verified by substring search" was false: `pipeline/umami_db.py:192` (`SQL_NOT_FOUND`) also contains
`coalesce(nullif(referrer, ''), 'direct')`. `Fetch.__call__` returns the first marker that matches in
dict order, so a test registering both would silently hand `SQL_NOT_FOUND`'s rows to whichever came
first. `"nullif(utm_source"` appears in `SQL_SOURCES` and nowhere else. This is the only collision in
the ten markers — the other nine were re-checked by substring search against all thirteen final
constants.

---

### Step 32 — `ancient-nerds-map/src/components/dashboard/__tests__/` · OWNER: TESTS

Eight files, all importing pure functions, exactly like the six that exist.

| File | Tests |
|---|---|
| `pulse.test.ts` | `stackHour({sessions: 10, human: 4}, 10)` puts the human segment on the baseline (`humanY + humanH === 20`) and the rest directly above it (`restY + restH === humanY`); `max` of 0 does not divide by zero; an all-human hour leaves `restH === 0`. |
| `globeReach.test.ts` | `secs(9450) === '9.5 s'`; `timesLine` with `samples: 0` returns the empty sentence; with `median: null` it names only best and worst and never prints "null"; with a median it names all three. |
| `scrapers.test.ts` | `clusterItem` joins the three fields with ` · `, survives all three being null (`'unknown machine'`), and its `key` is stable across two identical fingerprints. |
| `liveNow.test.ts` | `fmtSpan(30) === '< 1 min'`, `fmtSpan(360) === '6 min'`, `fmtSpan(7860) === '2 h 11 min'`, `fmtSpan(3600) === '1 h 0 min'`; `secondsSince('2026-09-19T07:30:00Z', Date.parse('2026-09-19T08:07:00Z')) === 2220` and a future stamp clamps to 0. |
| `members.test.ts` | `actItem` prints `never` when `at` is null, and otherwise `by N accounts, last <stamp>` — singular `account` at `by: 1`; the value is the raw count. |
| `paths.test.ts` | `entryItem` marks a page whose every session stopped as `tone: 'warn'` and omits the hint at `stopped: 0`; `exitItem`'s hint is `of N views`; `outboundItem` says `1 visitor` and `4 visitors`. Plus the existing `chainChips` tests, moved over from `journeys.test.ts` (**delete that file**). |
| `sources.test.ts` | **First: add `views: <n>` to each of the five `SourceRow` literals at lines 20-24.** `SourceRow` gains a required `views` in step 12, and those five rows are the *only* type error the whole frontend patch produces — `npm run type-check` and `npm run build` both fail without it, which blocks CI's `lint-frontend` and the VPS deploy's build. Any value; `bucketTotals` ignores it. Then: the existing `bucketTotals` assertions unchanged, plus `familyItem` omits the hint at zero bots; `hostItem` carries no hint; `statusItem` warns on 410 and 500 but not on 499, and **always sets a hint** (`BarList` only paints `tone` on a row that has one, so a warn without a hint renders nothing). |
| `problems.test.ts` | Existing tests plus `severity('webgl_lost') === 'high'` and `problemLabel('webgl_lost') === 'WebGL lost'`. |

CI's knip invocation (`npx knip --no-progress --include files,dependencies,devDependencies`) stays
green: no new file is orphaned and no dependency is added. It does **not** gate exports — bare
`npx knip` is red at HEAD with 167 unused exports and 3 duplicate exports, and that is pre-existing.
`knip.json`'s vitest plugin already treats `__tests__/*.test.ts` as entries, and step 14 actually
*removes* one knip finding (`Flags` in `Pulse.tsx` gains a real importer).

---

### Step 33 — `ancient-nerds-map/src/components/Globe/rendering/animationLoop.ts` · OWNER: GLOBE

`requestAnimationFrame(animate)` at line 207 is the **first** statement of the callback, before the
guard at 211. three.js compiles programs lazily inside `renderer.render()`; on a dead context
`gl.createShader()` returns null and `shaderSource` throws a `TypeError` straight out of the rAF
callback — and the next frame is already booked. The live burst on 2026-09-18 is exactly three
errors because `MAX_ERRORS_PER_PAGE = 3`, not because it happened three times; the three rows span
31 ms in one session.

**33a.** Add one field to `AnimationLoopContext`, next to `webglContextLostRef`:

```ts
  /** Called once when the loop stops because the context is gone. `reason` is
   *  'context_lost' when the canvas told us, 'no_shader' when three.js found
   *  out first. Globe.tsx reports it and shows the visitor a reload button. */
  onContextLost: (reason: string) => void
```

**33b.** Replace the head of `animate`:

before
```ts
  const animate = () => {
    animationId.value = requestAnimationFrame(animate)

    // Skip rendering when tab is hidden or WebGL context is lost
    // This prevents wasted GPU cycles and state corruption
    if (!ctx.isPageVisibleRef.current || ctx.webglContextLostRef.current) {
      return
    }
```
after
```ts
  const animate = () => {
    // The context checks come BEFORE the reschedule. three.js compiles its
    // programs inside renderer.render(), so on a dead context gl.createShader()
    // returns null and shaderSource throws out of this callback - with the next
    // frame already booked. Stopping is the only way out; Globe.tsx restarts the
    // loop from webglcontextrestored.
    if (ctx.webglContextLostRef.current) {
      ctx.onContextLost('context_lost')
      return
    }
    if (renderer.getContext().isContextLost()) {
      ctx.webglContextLostRef.current = true
      ctx.onContextLost('no_shader')
      return
    }

    animationId.value = requestAnimationFrame(animate)

    // Skip rendering when the tab is hidden; the loop keeps running so a
    // backgrounded tab resumes on its own.
    if (!ctx.isPageVisibleRef.current) {
      return
    }
```

The hidden-tab early return stays **after** the reschedule on purpose, so a backgrounded tab still
resumes. `onContextLost` must be idempotent on the caller's side — `Globe.tsx` guards it with
`webglLostReportedRef` (step 35), so the event is sent once per page view even though the loop can
reach the branch twice.

---

### Step 34 — `ancient-nerds-map/src/components/Globe/rendering/sceneInit.ts` · OWNER: GLOBE

Two defects, both at HEAD.

**34a.** Add two callbacks to `SceneInitOptions`, next to `setSceneReady` (line 32):

```ts
  /** The canvas lost its WebGL context. */
  onContextLost: (reason: string) => void
  /** …and got it back. */
  onContextRestored: () => void
```

**and extend the destructure at `sceneInit.ts:72` in the same edit**, or 34b and 34c are
`TS2304: Cannot find name 'onContextLost'`:

before
```ts
  const { initialPosition, refs, setGpuName, setSoftwareRendering, setSceneReady } = options
```
after
```ts
  const {
    initialPosition,
    refs,
    setGpuName,
    setSoftwareRendering,
    setSceneReady,
    onContextLost,
    onContextRestored,
  } = options
```

**34b.** Lines 103-112 — the restore handler sets a flag nobody reads until the tab is hidden and
shown again. Its only dispatcher is `handleVisibilityChange` at line 132, so a context restored while
the tab is in front leaves every label texture dead for the rest of the visit.

before
```ts
  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault()
    refs.webglContextLostRef.current = true
    console.warn('[Globe] WebGL context lost - will recover when restored')
  })
  canvas.addEventListener('webglcontextrestored', () => {
    refs.webglContextLostRef.current = false
    // Labels need to be reloaded as their textures were lost
    refs.needsLabelReloadRef.current = true
  })
```
after
```ts
  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault()
    refs.webglContextLostRef.current = true
    onContextLost('context_lost')
  })
  canvas.addEventListener('webglcontextrestored', () => {
    refs.webglContextLostRef.current = false
    // The textures died with the context. Dispatch here, not only from the
    // visibility handler: a context restored while the tab is in FRONT used to
    // leave every label blank until the visitor switched away and back.
    refs.needsLabelReloadRef.current = false
    window.dispatchEvent(new CustomEvent('webgl-labels-need-reload'))
    onContextRestored()
  })
```

**34c.** Line 128 — the visibility handler renders without checking the context.

before
```ts
    if (wasHidden && refs.isPageVisibleRef.current) {
      // Force a render to refresh the display
      renderer.render(scene, camera)
```
after
```ts
    if (wasHidden && refs.isPageVisibleRef.current) {
      // A lost context makes this render throw out of an event listener.
      if (refs.webglContextLostRef.current) return
      // Force a render to refresh the display
      renderer.render(scene, camera)
```

**Do not also patch `src/hooks/globe/useGlobeAnimation.ts`.** It is a dead second copy of the loop —
exported from `src/hooks/globe/index.ts:45` and imported nowhere; `Globe.tsx` uses
`rendering/animationLoop.ts`. Patching both is the duplication CLAUDE.md forbids. Its deletion is
**ticket T5**.

---

### Step 35 — `ancient-nerds-map/src/components/Globe.tsx` · OWNER: GLOBE

* New optional props `onWebglLost?: (reason: string, phase: string) => void` and `onWebglRestored?: () => void`.
* `const webglLostReportedRef = useRef(false)` — one report per page view, so the rAF branch and the
  canvas event cannot send two.
* Store the `AnimationLoopContext` in `animationCtxRef` **before** `runAnimationLoop(ctx)` so the
  restore handler can restart the stopped loop with `runAnimationLoop(animationCtxRef.current)`.
* `handleContextLost(reason)`: return if `webglLostReportedRef.current`; set it; call
  `track('webgl_lost', { reason, phase: layersReadyCalledRef.current ? 'live' : 'loading' })`; call
  `onWebglLost?.(reason, phase)`.
* `handleContextRestored()`: clear `webglLostReportedRef`, call `onWebglRestored?.()`, restart the loop.
* Pass both into `initializeScene` and `runAnimationLoop`.

### Step 36 — `ancient-nerds-map/src/App.tsx` · OWNER: GLOBE

* `const [webglLost, setWebglLost] = useState(false)`, wired to the two new `<Globe>` props.
* Inside the loading overlay, when `webglLost`: the stamp reads `GPU LOST`, the text
  `GRAPHICS CONTEXT LOST`, and `.loading-hint` is replaced **in place** by a red "Reload the globe"
  button of the same height, so nothing shifts.
* When the overlay is already gone, render a `webgl-lost-bar` with `role="alert"` instead.

### Step 37 — `ancient-nerds-map/src/analytics/index.ts` · OWNER: GLOBE

One line in the taxonomy, after `globe_idle`:

```ts
  | 'webgl_lost' // globe's WebGL context died — reason, phase
```

### Step 38 — `ancient-nerds-map/src/styles/index.css` · OWNER: GLOBE

`.loading-retry` and `.webgl-lost-bar` (plus its button), next to the existing `.loading-hint`.
Different sheet from `dashboard.css`; no collision, and **not** the CSS owner's file.

**Accepted behaviour change, stated in the commit body:** the loop now *stops* on a lost context
instead of spinning. If a browser restores a context without dispatching `webglcontextrestored`
(Safari frequently does not), the globe stays frozen where it might previously have resumed — but the
visitor is now told and given a button, instead of watching a progress bar stuck at 90 % for
38 seconds, which is what the one real visitor did.

**Acceptance gate — no unit test can build an 80-field context in a jsdom the repo does not have, so
this is the gate.** On desktop `/globe.html`:

```js
const ext = document.querySelector('canvas').getContext('webgl2').getExtension('WEBGL_lose_context')
ext.loseContext()
// before: unbounded TypeError burst, overlay frozen at LOADING, no globe_ready
// after:  zero TypeErrors, stamp GPU LOST, one webgl_lost event, reload button
ext.restoreContext()
// before: labels stay dead until you switch tabs and back
// after:  notice clears, loop restarts, labels come back
```

Run it twice: once while the overlay still reads `LOADING` (`phase: 'loading'`, the 2026-09-18 case)
and once after `ALL SYSTEMS NOMINAL` (`phase: 'live'`, which shows the bar instead).

## 3. Parallelisation map

### 3.1 One owner per shared file — never two

| File | Sole owner | Steps |
|---|---|---|
| `pipeline/umami_db.py` | BACKEND | 1 |
| `pipeline/stats_analysis.py` | BACKEND | 9 |
| `pipeline/referral_log.py` | BACKEND | 3 |
| `pipeline/members_stats.py` | BACKEND | 8 |
| `api/routes/founders_stats.py` | BACKEND | 10 |
| `api/routes/goto.py` · `pyproject.toml` · `scripts/referral_report.py` · `scripts/funnel_report.py` | BACKEND | 4-7 |
| `pipeline/lyra/analytics_alerts.py` | BACKEND | 11 |
| `components/dashboard/types.ts` | TYPES | 12 |
| `components/dashboard/Tile.tsx` · `Flag.tsx` | PANEL:Tile | 13-14 |
| `Pulse.tsx` | PANEL:Pulse | 15 |
| `GlobeReach.tsx` | PANEL:GlobeReach | 16 |
| `Scrapers.tsx` | PANEL:Scrapers | 17 |
| `LiveNow.tsx` | PANEL:LiveNow | 18 |
| `Members.tsx` | PANEL:Members | 19 |
| `Journeys.tsx` → `Paths.tsx` | PANEL:Paths | 20 |
| `Sources.tsx` | PANEL:Sources | 21 |
| `Problems.tsx` | PANEL:Problems | 22 |
| `TopContent.tsx` | PANEL:TopContent | 23 |
| `pages/DashboardPage.tsx` | PAGE | 24 |
| `styles/dashboard.css` | CSS | 25 |
| `scripts/dashboard_screenshots.py` | FIXTURES | 26 |
| all `tests/**` | TESTS | 2, 27-32 |
| `Globe/rendering/*.ts` · `Globe.tsx` · `App.tsx` · `analytics/index.ts` · `styles/index.css` | GLOBE | 33-38 |

### 3.2 Waves

**All thirty-eight steps land on ONE feature branch and reach `main` as ONE merge — one deploy.**
This is not a preference, it is the plan's hardest constraint, and it overrides "each step is one
commit" in §2 (which governs commit granularity *on the branch*, not what reaches `main`):

* Every push to `main` deploys (CLAUDE.md). Wave 0 is backend-only, so it would pass all six gates
  and ship. It removes `today`/`yesterday` from `/overview`, and the **deployed**
  `Pulse.tsx:95` — `delta(o.today.sessions, o.yesterday.sessions)` — then reads `undefined.sessions`
  and throws during render. `dashboardMain.tsx` mounts with a bare `createRoot` and has **no error
  boundary**, so the whole root unmounts: a blank founders dashboard from the wave-0 deploy until
  wave 5. Verified at HEAD.
* Wave 3 is *designed* to compile-break `Pulse.tsx`, `Problems.tsx` and `sources.test.ts`. On `main`
  that is a red `lint-frontend`, i.e. a blocked deploy and a red default branch for as long as
  waves 4-7 take.

So: `git switch -c dashboard-v2`, run the waves below on that branch, run every line of §4 on the
branch tip, then one merge. The waves are a *parallelisation* order, not a release order.

```
Wave 0 (serial, one commit)      : 1 + 2 + 10  — umami_db, its query tests, and the route module
                                    that imports from it. They cannot land apart: deleting
                                    SQL_HOUR_BUCKETS without the other two is two failing tests
                                    and an ImportError.
Wave 1 (parallel, 4 tracks)      : 3+4+5+6+7 (referral log)  ||  8 (members_stats)
                                    ||  9 (stats_analysis)   ||  33-38 (GLOBE, fully independent)
Wave 2 (serial after wave 1)     : 10 again — the route bodies that call the wave-1 modules
                                    ||  11 (analytics_alerts, needs only 1 and 9)
Wave 3 (single writer)           : 12 (types.ts). Nothing in the frontend may start before it;
                                    it deliberately compile-breaks Pulse.tsx, Problems.tsx AND
                                    __tests__/sources.test.ts (SourceRow gains `views`).
Wave 4 (single writer)           : 13 + 14 (Tile.tsx, Flag.tsx). Pulse, GlobeReach and Members
                                    all import Tile, so this lands before any of them.
Wave 5 (parallel, 8 tracks)      : 15 || 16 || 17 || 18 || 19 || 20 || 21 || 22 || 23
Wave 6 (single writer)           : 25 (dashboard.css). Needs the class names from wave 5.
Wave 7 (single writer)           : 24 (DashboardPage.tsx). Last source file; imports everything.
Wave 8 (parallel, 2 tracks)      : 26 (fixtures, needs the frozen response shapes from wave 2
                                    and a built dist/)  ||  27-32 (tests)
```

Waves 0-2 (backend) and 33-38 (globe) can run at the same time as each other; they share no file.
Waves 3-7 are frontend and are strictly serial at the file level, which is why each has exactly one
owner. Nothing in waves 3-7 may start before wave 2 has frozen the API contract, because every
component is written against `types.ts` and `types.ts` transcribes the routes.

### 3.3 Merge hazards, named

* `Problems.tsx`'s two `Record<ProblemKind, …>` maps are the compile-time gate. If a second kind ever
  arrives, both maps fail to compile until it is added — do not soften either to `Partial<Record<…>>`.
* `problems()` gains `webgl` **between** `searches` and `limit`. All **13** call sites repo-wide pass
  by keyword (verified), so nothing breaks; a positional call added later would.
* `Session`'s new fields all carry defaults and sit after the five positional ones
  `sessions_from_rows` passes. Do not reorder them.
* `git grep -nE '\.pages\s*[-+*/|&^]?=[^=]' -- api pipeline scripts tests` **before landing step 9.**
  The only writer is `pipeline/stats_analysis.py:191` — `s.pages += 1` — which step 9e deletes; any
  other assignment now raises `AttributeError` at runtime. `\s*=` alone does **not** match `+=` and
  finds only the two `==` comparisons; that is the wrong command and it was in this file until now.
* `git mv` for `Journeys.tsx` → `Paths.tsx` in the same commit as the content change, or the rename
  shows as a delete plus an add and the review loses the diff.

## 4. Verification

Run in this order. Each line's "pass" is what the implementer must see before moving on.

| # | Command | Pass |
|---|---|---|
| 1 | `git grep -nE '\.pages\s*[-+*/\|&^]?=[^=]' -- api pipeline scripts tests` | **one hit**, `pipeline/stats_analysis.py:191` (`s.pages += 1`), before step 9e; **zero** after. `\s*=` cannot match `+=` — do not use it |
| 2 | `git grep -n 'SQL_HOUR_BUCKETS\|SQL_EXITS\|SQL_GLOBE_READY\|slow_start\|globe_start\|stats_cache\|members_db' -- api pipeline scripts tests ancient-nerds-map/src` | **no hits** — every one of these is a symbol this plan does not build. The path scope is required: `docs/superpowers/plans/` carries three hits at HEAD and this file adds more |
| 3 | `ruff format --check api/ pipeline/ scripts/ tests/` | clean. CI only checks `api/ pipeline/`, so `scripts/` and `tests/` are on the implementer. If it rewrites an aligned trailing comment, a `#:` block was turned into one — put it back above the constant. The two known traps: the `hourly_sessions` bucket comprehension must stay on one line, and `without_brand`'s docstring keeps its space after `"""` |
| 4 | `ruff check api/ pipeline/ scripts/ tests/` | clean. Watch `scripts/referral_report.py`: step 6 orphans five imports, and CI's vulture only scans `api/ pipeline/` so nothing else catches them |
| 5 | `lint-imports` | contracts kept. Fails loudly if step 5's two `pyproject.toml` entries are missing |
| 6 | `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80` | no new dead code. `GLOBE_PATH`, `CLUSTER_MIN_IDS` and `WEBGL_PHASES` are all read by name |
| 7 | `mypy api/` **and** `mypy pipeline/members_stats.py pipeline/referral_log.py` | both clean. `mypy api/` alone does **not** see `pipeline/` errors — `[[tool.mypy.overrides]] module = ["pipeline.*"]` sets `follow_imports = "silent"` (`pyproject.toml:134`). Without `ACTS`' `tuple[tuple[str, Any], ...]` annotation, the second command reports `"type[Base]" has no attribute "created_at"` |
| 8 | `pytest tests/pipeline/test_umami_db_queries.py -q` | **7** tests — the file has 6 today and step 2c adds `test_the_hour_bucket_query_is_gone` |
| 9 | `pytest tests/pipeline/test_stats_analysis.py tests/pipeline/test_referral_log.py tests/pipeline/test_members_stats.py tests/scripts/test_referral_report.py -q` | all green; ~55 tests |
| 10 | `pytest tests/api/test_founders_stats_routes.py -q` | all green, including the twelve-route mount assertion. Six existing tests break under the patch: 31b/31c/31d handle three, `test_problems_run_six_queries_in_one_window` a fourth, and **31f deletes the remaining two** (`test_sources_carry_the_family`, `test_journeys_returns_the_chains_of_the_requested_window`). If either is still in the file, this is red |
| 11 | `pytest -m "not integration and not live_llm and not slow"` | the whole DB-less suite green — `tests/pipeline/test_analytics_alerts.py` must pass with the `webgl=` argument added |
| 12 | `semgrep scan --config .semgrep` | no findings |
| 13 | `cd ancient-nerds-map && npm run type-check` | clean. Before step 22 it **must** fail on `Problems.tsx`'s two `Record` maps — that is the gate working |
| 14 | `npx knip --no-progress --include files,dependencies,devDependencies` | green, exactly as CI runs it (`ci.yml:76`). `Journeys.tsx` must be gone, not orphaned. **Do not run bare `npx knip`** as a gate: it is red at HEAD with 167 unused exports and 3 duplicate exports, none of them ours |
| 15 | `npm run test` | all `src/components/dashboard/__tests__/*.test.ts` green; `journeys.test.ts` is gone and `paths.test.ts` carries its assertions |
| 16 | `npm run build` | clean `tsc && vite build` |
| 17 | `npx size-limit` | `dist/assets/landing-*.js` still under 12 kB brotli. Nothing here touches the landing bundle; if this moves, something imported `boot.ts` into `index.html` and that needs the owner |
| 18 | `npm run build:ssr` | clean. The dashboard is not an SSR route, so this only proves nothing else broke |
| 19 | `python scripts/dashboard_screenshots.py` | three lines printed; `overflow 0px` on all three. **Run it twice: once with `MAX_MOBILE_HEIGHT = 0` to read the heights, then again after step 26i has set the constant from them.** This script is **not in CI** (T9) — if it is skipped, nothing in the repo checks the phone layout. Open `dashboard-mobile-empty.png` by hand once: it is the only picture of production's real state |
| 20 | Post-deploy, on the VPS | `curl -s localhost:8000/api/stats/members` behind the founder cookie returns five keys (`members`, `founders`, `newest_signup`, `last_login`, `acts`) and no name, and every act carries `n`, `by` and `at`; `GET /api/stats/sources` returns a non-null `log` whose `statuses` contains **no 404 and no 301** and whose `hosts` does **not** contain `binance.com`; `GET /api/stats/globe` returns `loads` in the low thirties |
| 21 | Post-deploy, in a browser | the WebGL gate in step 38, run twice |
| 22 | Post-deploy, `/sources` against the log | `log.hosts` google.com ≈ 189 and the Umami row for `google.com` ≈ 62 views / 51 sessions. If `hosts` reads ≈ 214, the status filter in `coverage_report` is missing and the panel is printing redirects and scanner probes as arrivals |

## 5. Known-bad and deferred

### 5.1 Dropped, with the trigger that revives each

| Dropped | Trigger |
|---|---|
| Devices & language panel | a 7-day window with ≥ 300 confirmed-human sessions |
| Reading / scroll funnel panel | ≥ 50 scrolled reads on one page type in a 7-day window |
| Exits panel, `/exits`, `SQL_EXITS` | never — outbound lives in Paths; Discord has its own trigger below |
| Discord funnel panel | ≥ 20 `discord_click` events in a 7-day window (needs T3 first) |
| Pulse period comparison | `[now-14d, now-7d)` holds ≥ 100 sessions — i.e. from ~2026-10-01 |
| Returning visitors, `/returning` | a calendar month with ≥ 200 confirmed-human visitors and ≥ 10 returners |
| Search follow-through | ≥ 50 `search` events in a 7-day window (needs T2 first) |
| Heritage matrix and "countries read about" | ≥ 300 sessions with a `site_open` whose `context` is not `site`, in 7 days |
| `globe_start` / `slow_start` problem kind | ≥ 10 `globe_ready` samples from ≥ 10 distinct sessions, i.e. the same floor `VITAL_MIN_SAMPLES` already applies to every other timing on that list |
| `pipeline/stats_cache.py` | the 7-day `SQL_SESSION_EVENTS` exceeds 100 ms under `EXPLAIN ANALYZE` (11.8 ms today) — and then it is `@cached` from `api/cache.py` on that one query's fold, not a new module. Note the prize is large and known: ~37 ms of the page's ~75 ms |
| Three-band collapse | never; the phone budget is held by a height gate instead |

### 5.2 Bugs found and deliberately not fixed here — one line each

* **T1 — a 410 raises no analytics event.** `pipeline/article_html_renderer.py`,
  `render_error_html`: the `not_found` track call lives inside `_NOT_FOUND_FEEDBACK`, which is only
  attached for 404. 21 of the ~25 real error answers to referred humans are 410s, so `broken_link` is
  structurally blind to the whole category. One-line fix (a `gone` event or the same tracker call), but
  it changes a public page.
* **T2 — `useSiteSearch.ts:360` swallows exactly the "found nothing" case.**
  `if (searchingRef.current) return` fires before `trackedQueryRef.current = q`, and the effect only
  re-runs on `debouncedQuery`, so a cross-source search that genuinely finds nothing never reports —
  permanently. This is why `search` and `search_empty` have zero rows, and it must be fixed before the
  search trigger above can ever fire honestly.
* **T3 — the landing page runs no analytics module.** `ancient-nerds-map/index.html`'s inline module
  imports only `disclaimerContent.ts`, so `boot.ts` never runs, so `discord_click` and
  `outbound_click` cannot fire from the surface with 10 of 23 human Discord clicks. The fix is one
  import; it needs the 12 kB brotli `landing` size-limit budget raised, which is the owner's call.
* **T4 — `useStats` polls forever in hidden tabs.** `useStats.ts:22` is a bare `setInterval` with no
  `document.hidden` guard and no jitter; twelve panels means twelve simultaneous requests in the same
  tick, every 60 s, per open tab, forever.
* **T5 — `src/hooks/globe/useGlobeAnimation.ts` is a dead second copy of the animation loop.**
  Exported from `src/hooks/globe/index.ts:45`, imported nowhere. Delete it; do not patch it.
* **T6 — `SQL_SOURCES` counts a session once per distinct source.** A session whose first view has
  `referrer_domain='google.com'` and whose second has none appears under both `google.com` and
  `direct`: 135 session-source pairs against 127 distinct page-view sessions, a 6.3 % overcount.
  Pre-existing, unchanged by this plan, and the reason the Sources panel prints buckets rather than a
  total.
* **T7 — `/var/www/ancientnerds/logs` is 7.4 GB** (`ancient_nerds_qdrant.log` 4.8 GB,
  `ancient_nerds_db.log` 2.5 GB, `ancient_nerds_api.log` 184 MB and growing). Disk is 53 % of 193 GB,
  so not urgent, but growth is unbounded. Log rotation is deploy configuration and needs the owner.
* **T8 — `SQL_CLUSTERS` sorts every event in the window** and cannot hash-aggregate. `work_mem` is
  4 MB and the plan uses ~154 B per row, so it spills to disk at roughly 27 000 events in the window —
  ten times today's traffic. Mitigated for now by polling `/clusters` every 300 s; at that volume move
  the detection into the daily orchestrator and store the result.
* **T9 — `scripts/dashboard_screenshots.py` is not in CI.** `lint-frontend` runs type-check, knip,
  vitest, build, size-limit and build:ssr and never this script, so the 390 px overflow rule, the
  height budget and every empty-state fixture are enforced only when a human remembers verification
  row 19. The fix is a step in that job (`pip install playwright && playwright install --with-deps
  chromium`, then the script after `npm run build`) — CI configuration, so the owner decides.
  Until then, do not call this script a gate without saying it is a local one.
* **T10 — the referral-log parse blocks the API event loop.** `/sources` is `async def` and
  `read_visits()` is blocking; measured, the parse runs at ~80 ms per megabyte, so at
  `MAX_TAIL_BYTES = 1 MB` one refresh in every 55 s stalls that container for ~80 ms. The fix is one
  line — `visits = await asyncio.to_thread(referral_log.read_visits)`, which is already this repo's
  idiom (`api/main.py:561`, `api/routes/theo.py:415`) — and it is deliberately not taken here,
  because every `fetch()` in this module is blocking too and threading one call and not the other
  eleven is worse than threading none. Do it when the log outgrows 1 MB, and do it for all of them.
* **T11 — `/live` can identify one person.** At `total == 1` the panel prints that visitor's country,
  device, browser, eight characters of their session id and the title of the page they have open
  right now, refreshed every minute. Cookieless and salt-rotated, but not anonymous in the moment.
  The panel's own note says so; if the dashboard ever gains a second reader beyond the two founders,
  this needs a decision rather than a note.

### 5.3 Numbers that will read badly on merge day — none of them a regression

| What a founder will see | Why |
|---|---|
| **GlobeReach: 8 of 33 loads reached the globe.** | True. It is the worst product number on the page and it is why the panel exists. |
| **Scrapers: 38 of 163 sessions (23 %) were one machine.** | True at the path-minute level. Not "38 bots": it means 38 session ids that a single client produced. |
| **Pulse: `human` drops from 54 to 46** the moment this ships. | `Session.human` now requires a page view. Eight sessions with one `scroll_depth` and no page view stop counting as people, and all eight sit inside the two `/clusters` fingerprints. That is a correction, not a decline — say so in the commit body. |
| **Members: "Research requests 61 by 1 account".** | Deliberate. Live today: 126 Lyra answers from 2 accounts (125 from one) and 59 research requests from 2 (57 from one). The count without the denominator was member activity that is one person's week. |
| **Sources: the status list has no 404 and no 301 row.** | Deliberate, and the single most-corrected decision in this plan. Every 404 and 403 in the live log is a forged referer, and 19 of the 27 301s are the legacy `/site.html` redirect doing its job before its own 200. What is left — 21×410, 4×499, 1×500 — is the part nothing else on the dashboard can see. |
| **The Today tile's sub-line changes** from "= same as yesterday" to "human sessions, N % of M". | The old line divided `/countries`' human count by `/overview`'s all-sessions count. It was wrong; it is gone. |
| **The strip's unit changes from views to sessions** and the 48-hour peak drops from 23 to 18. | Deliberate: the classes are per session, and the axis caption now says "Sessions per hour, UTC". |
| **7 days and 30 days return identical numbers everywhere until 2026-10-17.** | The tracker's first event is 2026-09-17 10:03:33 UTC. They are not two independent samples. |
| **Members: every act reads 0 for recency, 2/2/126/59 all-time; newest signup 22 days old.** | That is the funnel's end today, and nothing else on the page can see it. All-time counts are used precisely so the panel is not four zeros. |
| **LiveNow is empty about a fifth of the time.** | Measured: a 30-minute window was empty in 20 % of all minutes. The empty branch names the last visitor, so the panel is never blank. |
| **TopContent usually shows one list.** | `story_open`, `paper_open` and `search` have never fired. The note says so; three empty boxes are gone. |
| **Sources: nginx says 189 Google arrivals, Umami says 62 views from 51 sessions.** | Both are right and they count different things: nginx counts requests it answered 200 or 410, Umami counts page views whose tracker ran. The gap is the panel's point. |
| **7 days and 30 days cost the same.** | The 30-day `SQL_SESSION_EVENTS` returns the same 794 rows as the 7-day one today. `/countries`' cache is there for October, not for now. |
| **Problems shows no `webgl_lost` row on day one.** | The event does not exist until step 35 ships and a visitor's context actually dies. A reviewer seeing nothing is expected; the acceptance gate in step 38 is the proof. |
| **`/clusters` and `/members` refresh every five minutes, not every minute.** | Deliberate: a fingerprint and a signup count do not move in sixty seconds, and `/clusters` is the one query that sorts every event in the window. |
| **The "Now" tile still says "last 5 min" while `/countries` is cached for 90 s.** | Worst case the tile is 90 seconds stale. The TTL is deliberately longer than the 60 s poll: at 55 s it expired before every request and never hit once. Stated here so nobody reads either number as drift. |
| **Sources prints a third list, "Hosts nginx saw".** | Without it the panel claims "nginx sees more than Umami" and gives the reader no way to check it: `families` are buckets, the Umami list is hosts, and the two never line up. `log.hosts` existed in the response and was rendered nowhere. |

### 5.4 The caveat that belongs on every reading of this page

Umami drops declared crawlers before the insert: GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot and
Applebot appear **zero** times in the events table *and* zero times in the referral log, because they
send neither a referer nor a utm. "23 % of sessions are one machine" must therefore never be read as
"and the other 77 % are people". The honest crawlers are structurally invisible to this dashboard.
The Scrapers panel's note says this in one sentence — that sentence is not optional, and it is the
one thing in this plan that is a panel string rather than a handover note, on purpose.

The second caveat is the mirror of the first and lives in LiveNow's note: this page is cookieless in
the aggregate and identifying in the moment. One visitor in the live window is one person's country,
device, browser and current page, refreshed every sixty seconds (T11).

### 5.5 Claims raised against this plan and rejected, with the measurement that disproves each

Three adversarial checks were run against the 2026-09-19 draft. Everything they found that held is
folded into §0-§4 above. These four did not hold, the plan is unchanged where they apply, and the
measurement is recorded here so nobody re-opens them from memory.

* **"Add `AND event_type = 1` to `SQL_CLUSTERS`' first CTE, so the code matches the prose 'a page
  load'; I re-ran it with the filter and the answer is still 38."** **Rejected — measured the
  opposite.** Run on the live `umami` DB on 2026-09-19, the filtered query returns **zero rows at
  `min_ids = 3`**: the maximum number of session ids on one page view in one clock minute is **2**
  (`SELECT max(c) FROM (SELECT count(DISTINCT session_id) c … WHERE event_type = 1 GROUP BY url_path,
  date_trunc('minute', created_at))` → 2, and `>= 2` matches exactly one path-minute). These clients
  fire events *without* page views — 34 of 163 sessions have zero page views, all of them inside the
  two flagged fingerprints — so the shared thing is events, not loads. The filter would delete the
  detection. **The prose was corrected instead**, in `SQL_CLUSTERS`' own `#:` block and in the panel
  string: "a path several session ids touched inside one minute".
* **"The cheap fix that needs no cache is to fetch `SQL_SESSION_EVENTS` once per request — `/problems`
  and `/journeys` both already re-derive `sessions_from_rows` from it, and `/overview` does too."**
  **Rejected — not actionable.** Each of those is already exactly one fetch per request; they are
  *four separate HTTP requests* from four `useStats` hooks. De-duplicating them requires state that
  outlives a request, i.e. precisely the cross-request cache B4 rejects. The finding's **number** was
  right and is adopted (~37 ms of ~75 ms, not ~22 of ~55); its remedy was not.
* **"`Session.human`'s `no_page` number should be counted over `sessions` (all folds) rather than
  over `people` — 34 of 163."** **Rejected as a panel number.** The 34 is real and is quoted in §0.1
  and in `entry_exit_pages`' docstring, but every one of the 34 sits inside the two `/clusters`
  fingerprints, so printing it in **Paths** — a panel whose every other number is "confirmed human
  sessions only" — would put a scraper count inside the human funnel. `no_page` is deleted, not
  relocated; the Scrapers panel already owns that population.
* **"`MAX_TAIL_BYTES` should drop to 256 KB (≈ 22 ms)."** **Partly rejected.** The cost measurement
  is adopted (the old comment was 5× low: measured 8.6 ms for 408 lines / 110 KB, ~80 ms per MB, not
  "1.7 ms and 36 ms for two megabytes"), but 256 KB is ~4.5 days of log at today's 56 KB/day, which
  is **shorter than the panel's own 7-day default window** — the coverage block would silently cover
  less than the numbers beside it. Settled at **1 MB ≈ 19 days ≈ 80 ms**, with `covered_days` in the
  response so the shortfall is visible when a founder asks for 30 or 90 days, and T10 for the real
  fix.
