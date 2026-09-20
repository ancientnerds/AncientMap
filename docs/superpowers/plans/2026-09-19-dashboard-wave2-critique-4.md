## Verdict

Spec 2 (scraper clusters), spec 4 (entry/exit), spec 10 (WebGL) and the globe *funnel* all reproduce exactly against production. The ruling structure is sound. But three of the contract's headline numbers do not survive re-measurement, the merge seam with wave one is broken in at least four places, and the 390 px screenshot gate — which §7 step 12 calls "the acceptance test" — dies on the first run.

Everything below was run today against `ancient_nerds_db` (`umami` + `ancient_map`) and `/var/www/ancientnerds/logs/referrals.log`. I wrote no files in the repo.

---

## 1. Panels that would mislead

**1.1 The globe percentile is one visitor's first load, and it reverses a wave-one ruling.**
`SQL_GLOBE` run verbatim on production returns 8 `ready_ms` values: `9450, 10023, 11059, 12488, 19917, 20110, 38703, 80383`. They come from **6 browsers**: session `17eea5a9` contributed `38703` *and* `19917`, session `1aa7846a` contributed `80383` *and* `10023`. p75 = 24 758 lands between `20110` and `38703` — it is pinned by one visitor's first load, a load that also fired two `globe_ready`s 68 s apart.

§4.3 sets the floor at 5 samples and fires a `globe_start` problem row at `p75 > 10_000, samples >= 5` ("so it fires today"). In the same list, `pipeline/stats_analysis.py:254-257` suppresses `radar · LCP` — live p75 **4717 ms from 3 samples** — with the comment *"A 75th percentile out of three measurements is one visitor's phone, not a percentile."* Two floors, one list, no reconciliation.

Worse: `docs/superpowers/plans/2026-09-19-dashboard-wave1-contract.md:651` already ruled this: *"**Do not lower `VITAL_MIN_SAMPLES`.** Re-verified: 8 globe_ready samples from 6 sessions, p75 24 758 ms … 8 < 10, so `/problems` returns no `slow_start` row today."* This contract reverses it and does not list the reversal in §9. Owner ruling R2 also says *"the UI says the counts, not only a percentage"* — a percentile is further from a count than a percentage is.

**1.2 "70 dead answers to real referred visitors" is ~54 false.** This is §5's stated reason for folding coverage into `/sources` ("the one nothing else on the dashboard can produce"). Measured from the live log:

| status | n | what it actually is |
|---|---|---|
| 404 | 50 | **28** `ref:"binance.com"` (no scheme) on `/wp-admin/css/`, `/.well-known/`, `/uploads/`, `/admin/controller/extension/…`; **22** `ref:"www.google.com"` (no scheme, forged) on `//images/images/cache.php`, `//cgi-bin/cgi-bin/cgi-bin/cgi-bin/cache.php`. **Zero real visitors.** |
| 403 | 4 | same `binance.com` scanner on `/images/` |
| 307 | 14 | **all** `GET /api/auth/discord/callback?code=…` — our own OAuth login working |
| 301 | 27 | 20 real (Google → legacy `/site.html?id=…`), 4 scanner, 2 our own utm link |
| 410 | 21 | **real** — Google still sending people to retracted stories |
| 499 | 4 | **real** — Google visitors who aborted |

The honest headline is **~25**, not 70. Note also that `source_host()` (`scripts/referral_report.py:96-105`) returns `""` for a scheme-less `ref`, so `aggregate()` drops 74 of 402 lines — the contract never says whether `coverage_report`'s `statuses[]` filters on a resolved host. With the filter you get ~3 404s; without it you print scanner noise as "answers to referred visitors". Neither produces 50.

**1.3 The `182 vs 60` number baked into `SQL_SOURCES`' comment is wrong.** §3.1 ships this as a source comment. I measure **165** human, 200-status, page-level Google arrivals (`google.com` 164 + `google.ca` 1) over the *entire* log, later in the same day; Umami has 61 views / 50 sessions. The log only appends and was never rotated (owner ruling R8), so 182 was never reachable. The 2.7× gap is real and the finding stands — but a falsifiable claim with a date on it is going into shipped source, and it is off by 17.

**1.4 "52 provably" overstates the proof by 14.** The fingerprint analysis reproduces exactly — only two fingerprints ever share a page load: `1366x1366 chrome Mac OS` (11 loads with ≥2 ids, max **7**) and `1280x1200 chrome Windows 10` (4 loads, max **6**); every other fingerprint peaks at 1; 52 sessions in those two groups; 39 of them SG/VN with no city. But **52 is the group's total session count.** Only **38** sessions actually appear inside a load shared by ≥3 ids (48 at ≥2) — the contract's own `CLUSTER_SHARED_IDS = 3`. The remaining 14 are guilt by fingerprint. `proven_fingerprints` has the same shape problem: the proof is at the *load* level and wave one's `/devices` is told to subtract the whole *fingerprint*.

**1.5 Two different "human" numbers, one screen.** §5.1 says `sessions: {all, human, ai}` with "human and ai OVERLAP", while `hours[]`'s classes are disjoint (R3, ai > human > unconfirmed). Live: `all=162, human=53, ai=12`, and **6 of the 12 AI sessions are human**. So the Pulse tile reads 53 human and the strip directly under it sums to 47 human. (Nit: §9.2 says `s.entry == "ai"` finds 0 — running the real `sessions_from_rows` over the live rows, it finds **1**.)

**1.6 TopContent's fifth list is the heritage panel's data under a softer title.** §9.7 kills heritage because 36 of 39 `site_open`s carry `context='site'` (SSR page firing itself) — confirmed: site 36, globe 2, radar 1. The "Countries read about" fold uses the same 40 events, and `TopContent.tsx:17` already prints `Name · Country` on every Sites row — it is the same column, re-aggregated, one list down. Meanwhile 3 of TopContent's 4 existing lists are permanently empty (`story_open`, `paper_open`, `search`: zero rows ever). The contract adds a fifth list to a 75 %-empty panel and specifies no empty state.

---

## 2. Things that end up half-built

**2.1 The 390 px gate dies.** `scripts/dashboard_screenshots.py:352` is `page.wait_for_selector(".dash-map-dot")` and Playwright's default is `state="visible"`. `VisitorMap` is panel #5 = Band B, which §5.4 renders as `<div className="dash-band-body" hidden>` on phones. The selector never becomes visible → `TimeoutError` → the mobile run fails. Step 12 adds `.dash-spark-ai` and `.dash-band-body` and never touches this line.

**2.2 …and even fixed, it stops testing the new work.** The mobile screenshot and its `scrollWidth - clientWidth` assertion (`:354-360`) would then cover Band A only. The 10 panels in Bands B/C — including the new two-column `Sources` `.dash-lists` and the `Members` tiles — are `display:none` and cannot produce measurable overflow. Owner ruling R7 says the screenshot gate "only covers states present in `FIXTURES`" and demands either render tooling or fixtures for every state; the contract answers neither.

**2.3 The stacked strip renders monochrome green.** §5.3: "Added, all at the end of the file." `dashboard.css:334-337` already has `.dash-spark rect { fill: var(--dash-green) }` at specificity (0,1,1), which beats a later `.dash-spark-ai` at (0,1,0). Appending wins nothing. Same for `.dash-spark { height: 56px }` (`:327`) and `.dash-spark rect:hover` (`:339`), both of which the contract re-declares instead of editing in place — the memory note `feedback_slider_approach` is explicit about this.

**2.4 The weekly digest breaks its own promise.** `pipeline/lyra/analytics_alerts.py` is in neither §7 nor the "files both waves touch" list, yet it is the second caller of `problems()` (`:236`) and `problem_lines()`'s `labels` dict hard-codes exactly the five current kinds with a raw-string fallback (`:158-164`). After this wave the Discord digest prints literal `webgl_lost` / `globe_start`, and `webgl=` is never passed — breaking the docstring's *"damit Digest und Panel nie zwei Wahrheiten erzählen."*

**2.5 `MembersData` is a placeholder, not a type.** §5.1: `export interface MembersData { /* exactly the §2 key list */ }`. `interface MembersData {}` compiles; every field read in `Members.tsx` is then a TS error. It is the only new interface not written out.

**2.6 `/sources` has two incompatible shapes inside one document.** §2: `log{available, reason?, covered_from, covered_days, families[], pages[], statuses[], ai[]}`. §5.1: `log: LogCoverage | null` (no `available`) plus a sibling `log_reason: string | null`. Backend and frontend get written from different sections.

**2.7 Two of the "fourteen" endpoints do not exist in wave one, and one that does is missing.** Wave one (`…wave1-contract.md:10-15, 56-70`) folds devices into `/overview` with **no new query**, and builds `/live` and **`/exits`**. §2 lists `/devices` and `/outbound` as "wave1 owns the shape" and never mentions `/exits`. §3.6 reserves `SQL_DEVICES`, `SQL_OUTBOUND`, `SQL_LIVE` — and misses `SQL_EXITS`, the one wave-one constant that genuinely collides with this wave's `entry_exit_pages` fold. `ExitPage` is declared in §5.1 *and* in wave one (`:587`, alongside `ExitRow`/`ExitsData`) with a different shape. "Fourteen" is a number this contract did not count either.

**2.8 §7's conflict rule produces broken merges.** "Keep both entries, never pick one" applied to `tests/pipeline/test_umami_db_queries.py`'s `QUERIES` keeps wave one's `"hour_buckets"` and `"globe_ready"` — both of which this contract deletes/renames — and the tuple is consumed by a module-level `getattr` loop (`:20-36`), so the module raises `AttributeError` at import, exactly the failure §7 warns about. The same rule on `ProblemKind` yields both `slow_start` (wave one) and `globe_start` (here) for one row.

**2.9 Two of the six named test files cannot be written.** Every existing dashboard test imports a pure named export (`chainChips`, `bucketTotals`, `severity`, `collapsePairs`, `dotRadius`), and `ancient-nerds-map/package.json` has **no jsdom and no @testing-library/react** — this is owner ruling R7 verbatim. §5.2 specifies pure exports only for `Pulse` (`stackHour`) and `Journeys` (`entryItem`/`exitItem`); `Scrapers.tsx` and `Members.tsx` get none, so `scrapers.test.ts` and `members.test.ts` have nothing to import.

Related: §5.4 claims the band collapse is "the same class of bug as React 418 … avoided by construction, and `render.test.tsx`'s storage guard is joined by an assertion that the dashboard calls no `matchMedia` during render." Both halves are wrong. `src/seo/__tests__/render.test.tsx` renders `SeoRoute` only — `DashboardPage` is not in that registry — and `src/dashboardMain.tsx:8` uses `createRoot`, not `hydrateRoot`. The dashboard is never server-rendered, so the hydration risk the mechanism is justified by cannot occur, while the mechanism's real cost (2.1, 2.2) is unacknowledged.

---

## 3. Cost and complexity

**3.1 The §2.1 cache has no measurement behind it.** `EXPLAIN (ANALYZE, BUFFERS)` on the heaviest query on the page — `SQL_SESSION_EVENTS` over 30 days, run on production — is **5.442 ms execution, 2.015 ms planning**. The contract adds a new shared module, a decorator, a minute-quantised clock and a disclosed staleness regression on the live tile to remove roughly 45 ms of DB work per minute for two readers. The whole §6 table is denominated in query counts and never in milliseconds.

And it is per-container: `docker-compose.yml:149-156` runs `api` (8000) and `api2` (8001) behind an nginx upstream, so 14 parallel fetches round-robin across two caches. "Six scans collapse to one **for all open tabs combined**" is wrong by at least 2× — the same split the contract correctly calls out for the referral log in §6.

**3.2 The "Now" tile is staler than disclosed.** `_now()` floors to the minute and `until` is exclusive, so the current partial minute (0–59 s) is dropped *on top of* the 55 s TTL — up to ~115 s, not one extra minute. `Pulse.tsx:101` prints "sessions, last 5 min".

**3.3 `ttl_cached` has no eviction and touches an existing test.** Key = `(sql, since, until, params)` with `since/until` changing every minute, so ~3 new entries per minute each holding a full row set, and nothing in the "~25 lines" removes them. `tests/pipeline/test_umami_db_queries.py:102-128` calls `u.fetch(...)` and asserts `calls[0]`; a process-lifetime memo on that function makes the assertion order-dependent, and no cache-clear fixture is specified.

**3.4 A fourth name for one constant.** §4.2 adds `EXIT_RATE_MIN_VIEWS = 10` beside the existing `VITAL_MIN_SAMPLES = 10` (`stats_analysis.py:257`) and the globe's new floor of 5; wave one adds `SCROLL_MIN_READS = 10`, which its own critique already flagged as duplication (`…wave1-critique-1.md:76`). Four names, one idea, one module — the exact thing the memory file says the user will be furious about.

**3.5 §4.4's justification for raw SQL is wrong for 5 of 6 tables.** "The card-game tables are declared in `api/cardgame/models.py`, which `pipeline` may not import — hence raw SQL." In fact `discord_users` (`pipeline/database.py:1120`), `token_usage_logs` (`:1208`), `site_likes` (`:1243`), `site_bookmarks` (`:1271`) and `research_requests` (`:1328`) are all in `pipeline/database.py`. Only `card_collections` (`api/cardgame/models.py:72`) is out of reach. The contract trades compile-time column names for *"a live smoke call of `GET /api/stats/members` after deploy is the only check that catches a rename"* — which is the posture CLAUDE.md bans.

**3.6 `/devices?exclude=` is unimplementable as written.** `useStats(path)` takes one string and fires independently; nothing lets `/devices` receive `proven_fingerprints` (an array of objects) from `/clusters`, no encoding is specified, and the endpoint does not exist in wave one (2.7).

---

## 4. What is missing entirely

**4.1 The one fact that makes the whole error story honest is not in the plan.** `pipeline/article_html_renderer.py:462` is `feedback = _NOT_FOUND_FEEDBACK if code == 404 else ""`, and the `not_found` track call lives inside that block (`:425`). **A 410 emits no event by design.** Live, 21 of the ~25 real error responses to referred visitors are 410s — Google sending people to retracted stories. So `SQL_NOT_FOUND` / the `broken_link` kind is structurally blind to the entire real category, while `not_found`'s zero for 404s is *correct* (all 50 404s were headless scanners). §0 blames the gap on "`not_found` has 0 rows"; the actual diagnosis — and the one-line fix — is nowhere, and unlike spec 6's `searchingRef` bug it gets no step-15 ticket.

**4.2 No empty state, anywhere, for the four new panels.** Verified today's actual production state for Members: **0 likes, 0 bookmarks, 0 cards, 0 token rows, 0 research requests in 7 days**; at 30 days: 2/2/35/1/0, newest signup 22 days old. So `Members` ships as a *wide* panel of zeros in Band B. `Scrapers` with `clusters: []` is the normal state as soon as the scrapers leave; `GlobeReach` with `loads: 0` is a plausible day; `Sources` with `log: null` is every dev box. `Panel.tsx:24-28`'s `Status` only covers "no data yet". R7 required a stated choice.

**4.3 The caveat that keeps panel #2 honest is deliberately kept off the page.** §9's closing note — Umami drops declared crawlers before the insert, so GPTBot/ClaudeBot/PerplexityBot appear zero times in *both* sources, and "42 % automated" must never read as "the rest are people" — is consigned "to the handover, not a panel note". That sentence is the only thing standing between the Scrapers panel and the opposite misreading, and it is placed in the one document the founders will not have open.

**4.4 One 401 blanks the page.** `DashboardPage.tsx:60` computes `unauthorized = panels.some(s => s.error === 'unauthorized')` over the panel array and `:80` swaps the whole grid for `<Entry />`. Adding `/members` — the only route that touches a different database and a different session dependency — to that array means one auth hiccup there replaces all 14 panels with "Session expired". The contract adds the endpoint and never mentions the array's semantics.

---

## 5. What I checked that holds up

- **Spec 2's proof** — exactly two fingerprints ever share a load (7 and 6 ids max), every other peaks at 1, 52 sessions, 39 of them SG/VN with no city. Reproducible, zero false positives at the load level.
- **The 48-hour axis bug is real** — 45 distinct hours carry events in the last 48; `Spark` draws `recent.length` bars across the viewBox, so 45 bars span a 48-hour label. The fixture's contiguous curve hides it.
- **Globe facts** — `/globe.html` is the only path matching `%globe%`; 33 views / 19 sessions; all 8 `globe_ready` fired there and all carry `ms`. **Bonus the contract could use:** none of the 33 loads come from either scraper fingerprint, so the funnel is not cluster-contaminated.
- **`globe_idle` precision 0/2** — both events belong to session `17eea5a9` and fired 10 s and 21 s after `filter_toggle` events on the same page. `markGlobeActivity` has exactly three call sites (`App.tsx:516, 1020, 1024`).
- **`App.tsx` never calls pushState** — only `AccountPage.tsx:451,476` and `ArticlesPage.tsx:694`.
- **AI arrivals: 12** (utm `chatgpt.com` 9 + 2 with referer, `perplexity` 1); 10 of 12 carry only `utm_source`. §9.1's ruling that spec 5 was wrong and spec 7 right is correct — `/sources` passes the coalesced source into `source_family`'s *referrer* position, so only bare `perplexity` falls to Other.
- **Spec 4's numbers**, reproduced by running the real `sessions_from_rows` over the live 7-day rows: 45 human sessions with a page; story 20 entries / 12 one-page; country 2 / 2; globe 9 / 1; site 9 / 2; home 5 / 0. 34 sessions have no page view at all, which `PageEnds.no_page` covers.
- **`SQL_GLOBE` runs as written** on production, and the `ARRAY[]::float8[]` gotcha is right — `'{}'` would trip `assert "{" not in sql` (`test_umami_db_queries.py:38`).
- **`SQL_HOUR_BUCKETS` consumers** are exactly `founders_stats.py:23,68` and `test_umami_db_queries.py:23`; `analytics_alerts.py:27-35` does not import it.
- **`problems()` kwarg insertion is safe** — every call site passes `not_found/vitals/errors/searches/limit` by keyword (`test_stats_analysis.py:279-398`, `analytics_alerts.py:236`).
- **`Session.pages` → property is safe** — the only assignment is `stats_analysis.py:191`; reads are `:143`, `:395`, `test_stats_analysis.py:151`.
- **Members DB** — 5 users, likes 2, bookmarks 2, card_collections 47, token_usage_logs 126, research_requests 59, newest signup 2026-08-28. The join warning is exact: `u.discord_id = r.user_id` → 59 rows; `u.id::text = r.user_id` → **0**. `user_contributions` is 932/932 `source='lyra'`.
- **Log plumbing** — `docker-compose.yml:125` binds `./logs:/app/logs:ro`, api2 inherits via `&api-service` (`:152-153`); file is 402 lines / 111 KB over 2 days, so `MAX_TAIL_BYTES = 8 MB` ≈ 5 months; `$time_iso8601` really is `+02:00`.
- **`getCountryCode()`** folds England/Scotland/Wales→GB (`countryFlags.ts:81-83`) and Türkiye→TR (`:61`), and the module is already in the dashboard bundle via `Flag.tsx:1` — the fold costs no bytes. UK block: 12 of 40 site_opens (30 %).
- **§8's three WebGL defects are all real.** `animationLoop.ts:207` books `requestAnimationFrame` before the context guard; `sceneInit.ts:108-112` sets `needsLabelReloadRef` without dispatching `webgl-labels-need-reload`, whose only dispatcher is inside `handleVisibilityChange` (`:123-136`); that handler calls `renderer.render()` unguarded (`:128`). The live burst is 3 `js_error` rows, one session, spanning **31 ms** (`02:28:12.081 → .112`) — consistent with `MAX_ERRORS_PER_PAGE = 3` (`boot.ts:17,72`), not with three incidents. `useGlobeAnimation` is exported from `src/hooks/globe/index.ts:45` and imported nowhere: a genuine dead copy.
- **Eight endpoints today vs "seven" in the docstring** (`founders_stats.py:2`) — correct.

---

## 6. One defect in the funnel's own arithmetic

`SQL_GLOBE`'s `vitals` column is the basis for `never_booted`, and the docstring argues *"a load with no Core Web Vital never executed our module bundle at all."* That is not what the metric means. `boot.ts:137` arms `onTTFB`, and `node_modules/web-vitals/dist/modules/onTTFB.js`'s `whenReady()` waits for `document.readyState === 'complete'` — i.e. the **`load` event** — before reporting. A visitor who bails during the loading overlay on a page whose median time-to-ready is 16 s may well leave before `load` fires and report nothing.

Those loads are exactly the abandoners the panel exists to count, and the funnel *removes them from the denominator*: today 6 of 33 loads sit in zero-vital sessions, so "8 of 33" quietly becomes "8 of 27" — 30 % instead of 24 %, biased in the flattering direction. Two further problems in the same column: `vitals` is aggregated **per session**, not per load (session `a8cfa4f3` has 4 globe views and 9 vitals — there is no way to tell which of its 4 loads booted), and `SQL_GLOBE` selects no device or os, so the panel structurally cannot say whether the abandonment is a phone problem. At 33 loads it cannot be split either way — which is itself the note the panel needs and does not have.