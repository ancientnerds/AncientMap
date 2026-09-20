## Verdict

The three new SQL constants are **correct SQL**: parameterised, website- and window-scoped, read-only, and none of them fans out across a join. I ran all three against production and they return exactly what §2.2/§2.4/§10 claim. The data-correctness defects are all in the **Python fold**, and two of them are real: one makes every period comparison biased upward, one lets known scrapers into the two new "human" panels.

Environment: `ssh ancientnerds` → `ancient_nerds_db`, db `umami`, website `02372c1d-36e8-4aed-a4bd-80829e2b6098`. The table moved 761→764 events / 159→160 sessions *during* this review, so single-unit drift below is real.

---

## F1 (high) — `countries(until=…)` counts "sessions whose **last** event fell in the window", not "sessions active in the window". Every `previous` comparison is biased upward.

§3.3 / §7.3.5 / §9.4. The filter is `pipeline/stats_analysis.py:239`:

```python
if since is not None and (s.last_seen is None or s.last_seen < since):
```

Adding `until` turns this into a half-open test on **`last_seen` alone**. For the *current* window (`until = now`) that is identical to "had an event in the window". For any *previous* window it is not: a session that was active in the window and kept going afterwards falls out of **both** buckets.

Measured live, yesterday to the same time of day (`[midnight−1d, now−1d)`):

| counting rule | all sessions | human |
|---|---|---|
| `last_seen` slice (what §3.3 builds) | **26** | **5** |
| had an event in the window (what `SQL_OVERVIEW` does) | **29** | **8** |
| had an event in the window, human judged on window-local events | 29 | 7 |

The three dropped sessions are `0b8cf0c0…` (3 events), `109a462e…` (18 events), `19c6b455…` (9 events) — i.e. the *most engaged* ones. Umami's `session_id` is a global PK with no visit rotation (`session_pkey btree (session_id)`), and 9 of 160 sessions already span >30 min, max span 14 h 27 m, 2 span midnight. The bias grows with engagement and with repeat visitors.

Consequences:
- §9.4 and §10 promise the Today tile will read **"▲ 20 % vs yesterday (was 5)"**. Today's human count is 6; honest counting of yesterday gives 7–8, i.e. a *decline*. The headline is manufactured by the slicing rule. §9.4's defence — "a bug fix, not a regression — the number and the percentage finally describe the same population" — is true of the *current* window and false of the *previous* one.
- §4's comment "the panel never does this arithmetic, so dashboard and Monday digest cannot disagree" is false. `weekly_digest` keeps `SQL_OVERVIEW` (`pipeline/lyra/analytics_alerts.py:231-232`), which is `count(DISTINCT session_id)` over the window — the correct semantics. Sharing `pct_change()` unifies the *formula*, not the *population*; the two will still print different numbers.

A correct previous-window count needs per-session event timestamps inside the window (or a second `count(DISTINCT session_id)` query), not `last_seen`. The interval-overlap shortcut (`started < until and last_seen >= since`) is not equivalent either — with 117-minute gaps in the stream a session can straddle a window it had no event in.

---

## F2 (high) — 8 headless scraper sessions with **zero page views** are counted as "confirmed human" by the two new panels, while the reading funnel in the same endpoint calls them scrapers and drops them.

`Session.human` (`pipeline/stats_analysis.py:141-145`) returns True on one interaction event, and `scroll_depth` is in `INTERACTIONS` (line 45). A session with `pages == 0` and one `scroll_depth` therefore passes.

Those sessions exist, and they are exactly the ones §3.5 drops as `reading.ignored`:

```
session      pages inter auto human  names         device screen     lang   country
0ffbd068…      0     1     0   t     scroll_depth  laptop 1280x1200  en-US  VN
1c4dbede…      0     1     0   t     scroll_depth  laptop 1366x1366  en-US  SG
32b8b2eb…      0     1     0   t     scroll_depth  laptop 1366x1366  en-US  SG
337cc19e…      0     1     0   t     scroll_depth  laptop 1366x1366  en-US  SG
4f6b91aa…      0     1     0   t     scroll_depth  laptop 1280x1200  en-US  VN
5ca1eabc…      0     1     0   t     scroll_depth  laptop 1280x1200  en-US  VN
70c6535d…      0     1     0   t     scroll_depth  laptop 1366x1366  en-US  SG
c0cb24f0…      0     1     0   t     scroll_depth  laptop 1280x1200  en-US  VN
```

Two tight clusters (4× square `1366x1366` / SG, 4× `1280x1200` / VN), one scroll event each, on two story URLs, no page view anywhere in the session. `ancient-nerds-map/src/analytics/boot.ts:93-95` already names them: *"gave every headless fetch four depth events at once (SG/VN scraper bursts, 2026-09-17)"*.

So of the 53 "confirmed humans": **laptop 31 contains 8 bots (real 23); English 39 contains 8 bots (real 31)**. The Devices panel overstates the laptop share by ~26 %.

§3.4 presents "device all-sessions is laptop 110 … but 34 of those laptops share one square 1366x1366 screen; human-only is laptop 31" as proof the human filter removes the cluster. It removes 30 of 34 and leaves 4 — plus 4 more from a second, identical VN cluster the contract never mentions. Verified: of the 34 `1366x1366` sessions, 4 are `human`; of the 18 `1280x1200` sessions, 4 are `human`; 4+4 = the 8 above.

The internal contradiction is the tell: §3.5's own comment calls these rows *"a scraper"* while §3.4 counts them as confirmed humans in the same response body.

---

## F3 (medium) — §9.2's equivalence proof measures a different quantity than the code it approves

- §9.2: *"my fold over the live 7-day window reproduces **167 opens** / 12 scrolled reads / 8 ghosts exactly."*
- §10: story 64 + country 15 + site 25 + paper 7 + journal 1 = **112 opens**.

Measured by replaying the §3.5 algorithm in SQL over the same window:

| quantity | measured |
|---|---|
| distinct (session, path) pageview keys, **all** page types | 168 |
| distinct (session, path) pageview keys, SCROLL_PAGES only (= what `reading_funnels` returns) | **115** |
| scrolled | 12 ✔ |
| ignored (scroll, no page view) | 8 ✔ |

Per page: story 64/9, site 27/1, country 16/2, paper 7/0, journal 1/0.

So "167" is the unfiltered figure — not the panel's. The §9.2 **ruling is still sound** (I verified its three load-bearing facts independently: all 55 `scroll_depth` events carry `url_path`; `depth` arrives in *both* `string_value` `"25.0000"` and `number_value` `25.0000`, so `int(float(…))` is right; and there are **0 orphan events**, so `SQL_SESSION_EVENTS`' inner `JOIN session` loses nothing). But the number cited as the proof is for a different metric, and §10's per-page opens are 2–3 low.

---

## F4 (low) — the `UNKNOWN_DEVICE` rationale is contradicted by the bundle the contract itself read

§3.4: `UNKNOWN_DEVICE = "unknown"   # Umami writes no device when no screen arrived`.

The snippet §9.14 quotes is verbatim correct — I pulled it off the running container:

```js
p=t?.device??function(e,t=""){let{device:i}=eq(e),[r]=t.split("x"),n=i?.type||"desktop";return"desktop"===n&&t&&1920>=+r?"laptop":n}
```

With no screen, `t` is `""` → falsy → it returns **`"desktop"`**, never null. Live: 0 of 160 sessions have a null or empty `device` (or `language`, or `country`). Keep the constant if you like, but the stated reason is wrong. Note also that `[r] = t.split("x")` takes the **width**, which is why a 1366×1366 headless viewport lands in the laptop row at all — that is the mechanism behind F2.

---

## F5 (low) — LiveNow's note "the same window as the Now tile above" cannot be literally true

§5.4 makes this binding (*"that must be literally true"*). But §1.3/§7.3.3 give the panel a **30-minute** window, while the Pulse "Now" tile is `LIVE_WINDOW = timedelta(minutes=5)` (`api/routes/founders_stats.py:36`, consumed by `visitor_countries()` at line 98). Only the *quiet* flag shares the five minutes. Either the note or the window has to change.

---

## Smaller notes

- **N1** `SQL_EXITS` `LIMIT 40` applies to the grouped `(event_name, target)` rows, so `ExitsData.clicks` folded in Python is a top-40 total, not the true click total. Invisible at 2 rows; silently wrong later. Same shape as the existing `SQL_CONTENT LIMIT 300`.
- **N2** Dead branch in §3.5: inside `if not views.get(key):`, the guard `if depth is not None:` can never be false — a key without views can only have come from `deepest`, which always stores an `int`. CLAUDE.md forbids exactly this defensive shape.
- **N3** §2.2: *"only /globe.html mounts App.tsx today (vite.config.ts has one input)"* — `ancient-nerds-map/vite.config.ts:198-222` declares 21 inputs. The accurate statement is that `src/main.tsx:4` is the only importer of `./App`, and `globe.html:103` is the only page loading it. The `GROUP BY url_path` is right; the reason is not.
- **N4** `outbound_click`/`discord_click` carry `page` captured once at boot (`const page = pageType(location.pathname)`, `boot.ts:133`, passed into `installOutboundClicks` at line 140), so on the globe SPA the page type is the *entry* page, not the current one. Today all 6 clicks are on MPA story pages, so it does not show.
- **N5** `without_brand()` must not return `""` for the one live title with no `" | "` — `"Database - Ancient Nerds"`, 1 of 112 distinct titles. The contract knows; pin it in the test.
- **N6** §10 says "53 of 158" while §3.4's own device numbers sum to 159 (measured: 110+43+6 = 159). Internal inconsistency in a document that says both were re-verified in the same session.

---

## What I checked that is sound

**SQL, all three new constants** — parameterised (`:website_id`, `:since`, `:until`), scoped to one website and a half-open window, read-only, no `{`/`%s`/`'%`:

- `SQL_GLOBE_READY` — `ev` groups by `e.event_id` (PK), so the `event_data` join cannot fan out; `samples` = events, `sessions` = distinct sessions. Live result is **exactly** the claim: `/globe.html | p75 24758.25 | fastest 9450 | samples 8 | sessions 6`. 8 < `VITAL_MIN_SAMPLES` 10, so §9.6's "no row on merge day" holds.
- `SQL_LIVE` — no fan-out anywhere (`seen` grouped by `session_id`; `session` joined on its PK; `LATERAL … LIMIT 1`). `EXPLAIN (ANALYZE, BUFFERS)`: **0.778 ms**, using `website_event_website_id_session_id_created_at_idx` for the LATERAL — matches §9.10's 0.675 ms. Returned 59 rows over the 24 h lookback, inside `LIMIT 60`, ordered by last sign of life so the clip is oldest-first as documented. The inner LATERAL drops exactly the **10 of 68** sessions with no page view (§9.12 verified).
- `SQL_EXITS` — `count(DISTINCT ev.session_id)` is taken off `ev`, not summed over `per_page`, so no cross-page double count; the correlated `jsonb_object_agg` cannot emit a duplicate key. Live: `outbound_click | youtube.com | 5 | 5 | {"story": 5}` and `getty.edu | 1 | 1 | {"story": 1}`, last at `2026-09-19 08:12:33`; `discord_click` 0 rows. Exactly §2.4/§10.
- **Guard test** (`tests/pipeline/test_umami_db_queries.py:44-48`): "LATERAL" does not contain "ALTER" — correct, the letters are not consecutive. All three new constants pass both shape tests.
- `session.session_id` is a global PK and the instance holds exactly one website, so the unqualified `JOIN session` in `SQL_LIVE`/`SQL_GLOBE_READY` is safe. **0 orphan events.**

**Data claims that reproduced exactly:** `page_title` 209/209 (now 210/210) filled · `device`/`language`/`country` never null (0/160) · `en-US@posix` present exactly once, `nb-NO` present once · human-only devices laptop 31 / mobile 18 / desktop 4 = 53 · `zh` 12 → 1 · human languages en 39, de 6, fr 2, then es/it/pt/sk/tr/zh 1 each, so §10's tail "3 more sessions in 3 other languages" is right · `[now−14d, now−7d)` holds **0 events** (§9.5) · `globe · INP` p75 504 / 14 samples (§9.16) · React #418 `js_error` 2 sessions → score 6 · `not_found` 0, `search` 0, `discord_click` 0 · both `globe_idle` events belong to session `17eea5a9…`, whose two `globe_ready` were 38 703 ms and 19 917 ms (§9.9) · max gap between events **1:57:19** = 117 min · a 30-min window empty in **561/2812** minutes = 20 %, a 5-min one in 76 % (§10).

**Code citations that check out:** `App.tsx:1822` `track('globe_ready', …)` and `:1823` `globe_idle` with the literal `30000`; `MIN_SPLASH_DURATION = 3000` at `App.tsx:195`; `layersReadyCalled` guard at `src/hooks/globe/useLayersReady.ts:32,41,52` · `useStats(path, refreshMs = 60_000)` at `components/dashboard/useStats.ts:10` · `DayBlock` read only at `components/dashboard/Pulse.tsx:95`, which does mix `o.today.sessions` (all) with `c.today` (human) as §9.4 diagnoses · `SQL_OVERVIEW` still consumed by `analytics_alerts.py:231-232`, `_delta`'s maths at `:144`, `problem_lines` labels at `:158-164` missing `slow_start` · `boot.ts:15-16` `SCROLL_STEPS`/`CONTENT_PAGES` match §3.5 · `boot.ts:115,119` send `{src, page}` / `{host, page}` where `page` is the page *type* · `vite.config.ts:174-188` injects the tracker everywhere except `dashboard.html`, so the landing page is tracked for pageviews but has no `boot.ts` — §9.8's blind-spot note is accurate · Umami does ship `isbot` server-side, so §9.11's "drops bot UAs" is true for *declared* bots only, which is precisely the gap F2 falls through.