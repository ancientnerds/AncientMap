I've read the implementation surface and re-run the contract's own SQL against production. Findings below, ordered by how much of a feature they leave half-built.

---

## A. Every panel's day-one production state is unfixtured — and the repo has no way to test it

The screenshot script is the **only** visual gate (`scripts/dashboard_screenshots.py:354-360`), and the repo has **no jsdom / no `@testing-library/react`** — `ancient-nerds-map/package.json:43-57` lists only `vitest`, and all six existing tests (`src/components/dashboard/__tests__/`) import pure functions, never render (e.g. `problems.test.ts:3` imports `problemLabel, severity` only). So a state that isn't in `FIXTURES` is a state nothing checks.

The contract's fixtures (§7.9) deliberately avoid exactly the four states production will show on merge day:

| Panel | Production state on 2026-09-19 (contract's own §10) | Fixture §7.9 |
|---|---|---|
| LiveNow | "Nobody in the last 30 minutes…" — §10 measures this at **20 % of all minutes** | six visitors, `total: 9` |
| LiveNow `last` fallback | the named last visitor, rendered only in the empty branch | `last: None` |
| Exits / Discord | the empty state (`discord_click` = **0 rows, ever** — I re-confirmed: zero `discord_click` rows in `event_data`) | 6 discord rows |
| Reading | "No page type reached 10 scrolled reads yet" + the thin unrated line | 4 rated funnels + 1 unrated |
| Pulse `d7` | `change.pct = null` → falls back to `humanSub` (§9.5) | `d7 = country_window(4, change={"previous": 118, "pct": -20})` |

§10 even instructs "Render the empty branch once by hand from the fixture before merging" — impossible, the fixture it specifies has six visitors. Concretely: the `compare()` branch in the rewritten `Pulse.tsx` that handles `change != null && change.pct == null` — the *only* branch the live d7 tile will take until 24 Sep — is exercised by neither a fixture nor a test.

**Minimum fix:** a second fixture set (or a `--empty` flag) that runs the same 390 px overflow gate over the production-shaped payloads, plus `.dash-empty b` actually getting rendered once (it is currently inert — `dashboard.css:185-192` has no `b` rule).

---

## B. Reading is the only `/overview` key that counts scrapers, and no ruling covers it

`device_shares()` and `languages()` filter `s.human` internally (§3.4), `session_type_shares` does too (`pipeline/stats_analysis.py:217-218`). `reading_funnels(rows)` (§3.5) folds **raw rows** and has no `Session`, so it cannot.

Measured on production just now (7-day window, the project's own `human` rule reimplemented in SQL), opens per page type as the §3.5 fold would count them:

```
story    40 human / 24 non-human
site     10 human / 16 non-human
country   3 human / 13 non-human
paper     1 human /  6 non-human
journal   0 human /  1 non-human
```

So 62 % of `site` opens, 81 % of `country` opens and 86 % of `paper` opens are sessions that fail the human test. §10's note blames the site/country gap on short pages ("a page shorter than the viewport fires no scroll event") — the larger driver today is the scraper share, and the note says nothing about it. This is the same trap `problems()` was fixed for (`pipeline/stats_analysis.py:386-391`: "twenty-two headless story fetches turned into the second-worst problem on the panel").

§9.11 sets the rule — "Both correct, and the notes must say which" — and then only applies it to `/live`. Reading needs the same ruling: either filter (`sessions_from_rows` already runs in the same handler, the human ids are free) or say so in the note.

---

## C. `LiveData.total` is never defined, and the fixture contradicts `LIVE_LIMIT`

- §1.3 lists `"total": int` with no definition; §3.8's `live_now(rows, *, now, window, quiet_after, lookback, limit)` never says what it counts.
- §7.3 item 3 sets `LIVE_LIMIT = 12`.
- §7.9 item 6 sets `total: 9`, six visitors, `summary: "9 visitors in the last 30 minutes, 6 shown"`.

With a limit of 12 and 9 visitors in the window, nine rows render — "6 shown" is unreachable. And `SQL_LIVE`'s inner `LATERAL` (§2.3, §9.12) means page-less sessions never reach Python, so `total` cannot be "sessions in the window" either. This is the panel's headline number; it needs a definition, and the fixture needs to agree with `LIVE_LIMIT`.

Related: §10's empty sentence is *"Last seen 🇮🇳 37m ago"* — `"37m ago"` is verbatim the output of `timeAgo()` (`src/utils/formatters.ts:33-42`), which §6 explicitly rejects in favour of the new `fmtSpan` ("< 1 min" / "6 min" / "2 h 11 min"). The empty branch's formatter is therefore unassigned — exactly the gap that produces the duplicated helper §9.17 is written to prevent.

---

## D. §5.4's panel order is a reorder; §7.7 describes only insertions

Current source order (`src/pages/DashboardPage.tsx:84-91`) is Pulse, VisitorMap, **SessionTypes, Sources**, Journeys, Problems, TopContent, FeedbackInbox. §5.4 requires **Sources before SessionTypes**. §7.7 says only "4 JSX insertions at slots 2, 5, 7, 11".

Follow §7.7 literally and you get `… SessionTypes(N), Exits(N), Sources(N), Devices(N) …` — still four narrows in a row, still no desktop hole (so §9.1's argument survives), but the semantic pairs become SessionTypes↔Exits and Sources↔Devices, i.e. the opposite of what §5.4 declares binding, and the phone reading order is wrong. Name the swap.

---

## E. "Eleven endpoints" is ten

§1 header and §7.3 item 1 both say eleven. Count §1: overview, countries, live, exits, problems + the five in §1.6 (map, content, journeys, feedback, sources) = **ten**. The existing docstring at `api/routes/founders_stats.py:2` says "seven" and is already wrong by one (there are eight routes: lines 44, 77, 105, 114, 129, 141, 159, 168). §7.3 is the one pass over that docstring and it hard-codes the wrong replacement. While in there: line 4 still points at `api.services.founders_stats`, a module that no longer exists (the code moved to `pipeline/stats_analysis.py`).

Also `tests/api/test_founders_stats_routes.py:87` enumerates the mounted routes — the contract never adds `"live"` and `"exits"` to it, so both new endpoints ship without a mount assertion.

---

## F. `slow_start`'s detail sentence is pinned by a fixture but never specified in code

§3.6 defines `GLOBE_READY_LIMIT`, `_seconds()`, the score (`sessions * 2`) and the label (`page_type(url_path)` → `"globe"`) — but never the `detail` string. §7.9 item 5 then pins *"p75 19.2 s to interactive against a 3.8 s budget, best 9.5 s, 41 loads by 17 visitors"* into the screenshot. Nothing makes the Python produce that sentence; nothing tests it. Combined with §9.6 ("no `slow_start` row today, 8 samples vs the 10 gate" — I re-verified live: `/globe.html | p75 24758.25 | fastest 9450 | 8 samples | 6 sessions`), the feature merges with **zero observable output and zero string-level coverage** — its only proof is a hand-run SQL query. At minimum, pin the sentence in `tests/pipeline/test_stats_analysis.py` the way `slow_page`'s is implicitly pinned by `stats_analysis.py:360-362`.

Same shape, smaller: §7.4 item 5 adds `"slow_start": "Slow start"` to the hand-kept `labels` dict at `pipeline/lyra/analytics_alerts.py:158-164`. Widening `ProblemKind` breaks TS at compile time (`Record<ProblemKind,…>`, §5.2) but nothing guards the Python mirror, and §8 step 3 scopes the alerts test to `_delta` only. The next kind will silently print `snake_case` in Monday's digest.

---

## G. Smaller, but real

1. **Devices' first `<h3>` will not be flush.** §6 kills `.dash-exits h3:first-child` because `.dash-panel h3:first-child` (`dashboard.css:181`) "matches through the wrapper div" — correct for Exits, which has a `.dash-exits` wrapper. **Devices adds no wrapper and no CSS** (§5.3, §6), so its first `h3` is a sibling of `<h2>`, not a first child, and keeps `margin-top: 14px` (line 172). The two panels sit in adjacent desktop rows with different top spacing.
2. **`ExitsData.clicks` is undefined.** §1.4 declares `"clicks": int`; §10 reads it as outbound-only ("6 clicks") while the fixture sets `clicks: 427` alongside 7 outbound + 6 discord rows. Say whether Discord counts.
3. **`BarList` requires an `empty` prop** (`BarList.tsx:17, 25`). The contract names the sentence for Exits/Discord and for Reading, but not for Devices' two lists or the languages tail.
4. **`languageName(null)`** — the signature accepts `null` (§6) but no return value is specified; `countryName` returns `'Unknown'` (`format.ts:39-42`). Pick one.
5. **`_PRIMARY_SUBTAG = re.compile(r"[a-z]{2,3}")`** (§3.4) only matches lowercase; live data is lowercase-primary (`en-US`, `zh-CN`, `nb-NO`, `en-US@posix` — all verified), but the contract never says `.lower()` is applied, and §9.13 leans on this function to "remove the whole class of input".
6. **`summary: str` contradicts §3.9/§9.17's plural ruling.** §3.9 rules that Python does *not* format "1 visitor" / "4 visitors" and that `fmtVisitors()` is "the single TS mirror". `live_now` then returns `"9 visitors in the last 30 minutes, 6 shown"` — a Python-composed plural. It is consistent with `problems[].detail` (already server-composed prose), but it is a third plural site the ruling claims does not exist.

---

## What I checked and found sound

- **Every live number re-verified against production** (`ssh ancientnerds` → `ancient_nerds_db`, db `umami`, 761 events, 2026-09-17 10:03:33 → 2026-09-19 09:03:36): `globe_ready` p75 24758.25 / fastest 9450 / 8 samples / 6 sessions on `/globe.html`; 6 `outbound_click`, all on `/news-archive/…`, youtube.com ×5 + getty.edu ×1, 6 distinct sessions; `discord_click` = 0; `page_title` 209/209; `1366x1366|laptop|34`; `en-US@posix` ×1; `nb-NO` ×1; device 111/43/6 (contract said 110 — the drift §9.15 predicted); 10 of 69 sessions in 24 h with no page view (§9.12 said 10 of 68).
- **Column/storage assumptions hold:** `website_event.page_title` and `session.language` (varchar 35) exist; `globe_ready.ms` and `scroll_depth.depth` both populate `number_value` **and** `string_value` (data_type 2), so `max(d.number_value)` in `SQL_GLOBE_READY` and `int(float(...))` in the reading fold are both safe.
- **Query guards pass:** `"LATERAL"` contains no `ALTER`; all three new constants carry `:website_id`/`:since`/`:until` and no `{` (`tests/pipeline/test_umami_db_queries.py:34-49`).
- **`Fetch` markers (§2.6) are collision-free** against all fourteen SQL texts — verified by substring search, including `"AS last_seen"` vs `_LAST_VISITOR`'s `AS last_at` (`pipeline/umami_db.py:167`).
- **`countries(until=…)` breaks nothing:** both call sites (`api/routes/founders_stats.py:88-89`) pass by keyword; the only other caller is a test (`tests/pipeline/test_stats_analysis.py:202`).
- **`DayBlock` grep is correct:** only `Pulse.tsx:95` reads `today`/`yesterday`.
- **§9.8 confirmed:** all 18 `*Main.tsx` import `./analytics/boot` except `dashboardMain.tsx` (deliberate); the landing page's inline module in `index.html` does not.
- **Query budget 15 → 16 confirmed** by counting the current handlers.
- **No nginx change needed** (`/api/stats/` already proxied wholesale), **no service-worker risk** (`dashboard.html` is in `globIgnores`, `vite.config.ts:288`, and the `/api/sources` runtime cache regex does not match `/api/stats/sources`).
- **`_digest_fetch` tolerates the new query** (`tests/pipeline/test_analytics_alerts.py:36` returns `[]` for unknown SQL), so adding `SQL_GLOBE_READY` to `weekly_digest` breaks no existing test.
- **The CSS claims hold:** `.dash-tile` is `min-width: 0` + flex column and `.dash-tile-sub` has no `nowrap` (lines 214-218, 312-317), so the long delta string wraps instead of overflowing; `.dash-delta--up/--down` exist (319-325).
- **Grid layout math is right** given §5.4's order: 8 wide + exactly two narrow pairs, no half-empty cell.