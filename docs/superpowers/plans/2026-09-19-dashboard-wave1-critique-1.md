## Verdict

Not sound on this lens. Fifteen findings, four of which will either fail a gate in §8 step 13 or ship something the contract itself forbids elsewhere. The **English-only rule is clean** (details at the end).

---

## A. Gate-blocking / CLAUDE.md violations

### A1. Every new constant in §3 uses an aligned trailing comment — `ruff format --check` fails, and it inverts the module's own convention

Offending lines, verbatim from the contract:

```
UNKNOWN_DEVICE = "unknown"                      # Umami writes no device when no screen arrived      (§3.4)
SCROLL_PAGES = ("story", "site", "paper", "journal", "country")   # = CONTENT_PAGES in boot.ts        (§3.5)
SCROLL_STEPS = (25, 50, 75, 100)                                  # = SCROLL_STEPS in boot.ts         (§3.5)
GLOBE_READY_LIMIT = 3800          # Lighthouse's good/needs-improvement TTI line; …                    (§3.6)
EXIT_LISTS = {"outbound_click": "outbound", "discord_click": "discord"}   # next to INTERACTIONS/…     (§3.7)
TITLE_BRAND = " | "                                    # after page_type()                            (§3.8)
```

I ran the formatter (`ruff format -` over stdin, ruff is the CI one): it collapses all of them to exactly two spaces. §8 step 13 lists `ruff format --check` as a gate, so the contract as literally transcribed fails it.

Worse than the whitespace: `pipeline/stats_analysis.py` documents **every** module constant with a `#:` block *above* it — lines 47, 51, 221, 251, 254, 258, 260, 262, 273. There is not one trailing-comment constant in the file. The contract's own `umami_db.py` additions (§2.2, §2.3, §2.4) get this right with `#:` blocks; only the `stats_analysis.py` half breaks it.

And three of those trailing comments are **placement directives to the implementer**, not documentation: `# next to INTERACTIONS/JOURNEY_EVENTS`, `# after page_type()`. Copied literally they ship as code comments that say nothing about the code.

### A2. `SQL_EXITS`' `coalesce` chain is fallback code — and contradicts §3.7 on the same page

§2.4:
```sql
coalesce(
    nullif(max(d.string_value) FILTER (WHERE d.data_key = 'host'), ''),
    nullif(max(d.string_value) FILTER (WHERE d.data_key = 'src'), ''),
    'unknown'
) AS target,
coalesce(nullif(max(d.string_value) FILTER (WHERE d.data_key = 'page'), ''), 'other') AS page
```

§3.7 two pages later: *"an unknown event name means the SQL drifted and must fail loudly (CLAUDE.md: no defensive wrapping)"*. The SQL does the exact opposite for the *key* name.

`ancient-nerds-map/src/analytics/boot.ts:110-119` proves both arms are unconditional:
- `outbound_click` is only tracked when `outboundHost()` returned non-null → `host` is never absent or empty.
- `discord_click` sends `src: …get('src') ?? 'unknown'` — the `'unknown'` sentinel **already exists in TypeScript**. The SQL literal is a second copy of the same rule.

The `page` arm is the worse one: `'other'` is a real `pageType()` return value (`src/analytics/index.ts:150`). A drifted event that lost its `page` key lands silently in a legitimate bucket and nothing ever reports it. Verified live: all 6 `outbound_click` rows carry both `host` and `page`; `discord_click` = 0 rows.

### A3. §7.7 cannot produce §5.4's panel order, and miscounts the `useStats` lines

§7.7: *"4 JSX insertions at slots 2, 5, 7, 11 per §5.4"*.

`DashboardPage.tsx:84-91` renders `Pulse, VisitorMap, SessionTypes, Sources, Journeys, Problems, TopContent, FeedbackInbox`. Pure insertion at those slots yields:

`Pulse, LiveNow, VisitorMap, SessionTypes, Exits, Sources, Devices, Journeys, …`

§5.4 demands `… VisitorMap, **Sources**, Exits, **SessionTypes**, Devices, …`. The existing `SessionTypes`/`Sources` lines must **swap**, and §7.7 — the "one pass per file" section whose whole job is to be exhaustive — omits it. The layout still has no half-empty cell, so nothing breaks visibly; what breaks is exactly the claim §5.4 rests on: *"Sources↔Exits and SessionTypes↔Devices are the two semantic pairs, so the desktop pairing and the phone narrative agree."* With the literal §7.7 edit the desktop pairs become (SessionTypes, Exits) and (Sources, Devices).

Same section: *"3 new `useStats` lines"*. §5.5's block has ten calls; `DashboardPage.tsx:50-58` has eight. The new ones are `live` and `exits` — **two**. §5.5 itself says "Ten `useStats` calls for twelve panels."

### A4. A shipped comment states a false, checkable fact

§2.2, inside the `SQL_GLOBE_READY` docstring that goes into `pipeline/umami_db.py`:

> *"only /globe.html mounts App.tsx today (**vite.config.ts has one input**)"*

`ancient-nerds-map/vite.config.ts:197-217` declares ~20 rollup inputs (`landing`, `main`, `news`, `story`, `radar`, `lyra`, `lyraOps`, `db`, `articles`, `account`, `search`, `site`, `api`, `cards`, `game`, `theo`, `research`, …). The conclusion is right, the cited evidence is wrong. The provable form: `src/main.tsx:4` is the only module that imports `./App`, and `globe.html:103` is the only page that loads `/src/main.tsx`. In a file where every comment is a dated, verified citation, a false parenthetical is the one thing that must not ship.

---

## B. Duplication the contract's own audit (§3.9) missed

### B1. `SCROLL_MIN_READS = 10` beside a reused `VITAL_MIN_SAMPLES = 10`

§3.6 rules: *"`VITAL_MIN_SAMPLES = 10` is **reused, not duplicated**; its comment gains 'The globe's time to interactive is gated by the same number for the same reason.'"*

§3.5 then creates `SCROLL_MIN_READS = 10` for the identical idea, and §10 words it identically: *"too few to read as a rate"* vs `stats_analysis.py:254-257` *"A 75th percentile out of three measurements is one visitor's phone, not a percentile. Below this many samples a page stays out of the list."* Two constants, one value, one rationale, one commit. §3.9's table does not list the pair.

### B2. `reading_funnels(rows)` re-walks rows `/overview` has already folded, and re-implements the dispatch

Every analysis entry point in the module takes `list[Session]` — `journeys()` (205), `session_type_shares()` (217), `countries()` (225), `problems()` (302). Only `sessions_from_rows()` takes raw rows. §3.5 adds a second raw-row consumer whose loop body

```python
if r["event_type"] == 1:  …
elif r["event_name"] == "scroll_depth":
    depth = int(float((r.get("data") or {}).get("depth", 0) or 0))
```

is a second copy of `sessions_from_rows` lines 188-199, and the route now iterates the same list twice per request. §3.9 rules only on the one-line depth parse (*"extracting a 1-line parse would be worse"*) and never considers the alternative that removes the whole duplicate: two per-path counters (`reads`, `depths`) filled inside the existing loop, then `reading_funnels(sessions)` like every sibling. That deserves an explicit rejection, not silence.

### B3. Nothing owns "37m ago"

§6 adds `fmtSpan` for `"< 1 min" / "6 min" / "2 h 11 min"` and dismisses `timeAgo()` with *"needs a timestamp"*. §10's LiveNow empty branch prints *"Last seen 🇮🇳 **37m ago** on …"* — which is literally `timeAgo()`'s output format (`src/utils/formatters.ts:33-43`), a different vocabulary from `fmtSpan`'s, in the same panel. No dashboard file imports from `utils/formatters` today (verified: zero hits across `components/dashboard/` and `DashboardPage.tsx`). So LiveNow either becomes the first cross-import and prints two time dialects, or invents a third rule — which §9.17's naming-ownership ruling forbids. §4/§6 never say which.

---

## C. Logic in the contract's own code blocks

### C1. Dead defensive branch in §3.5

```python
for key in views.keys() | deepest.keys():
    …
    if not views.get(key):
        if depth is not None:
            ignored += 1
```
`views[key] += 1` guarantees every key in `views` has value ≥ 1, so `not views.get(key)` is true only when `key ∉ views`, which (given the union) means `key ∈ deepest`, which means `depth is not None`. The inner guard can never be false. Per CLAUDE.md that `if` is exactly the kind of thing that should not be written; `ignored += 1` unguarded is the honest line.

### C2. The 25 % step is `scrolled` by construction

`boot.ts:16` `SCROLL_STEPS = [25, 50, 75, 100]` and `newDepthSteps` (lines 20-35) never fire below 25. So any key in `deepest` has `depth >= 25`, so `reached[page][25] == scrolled[page]` in **every** funnel row, always. `ReadingFunnel.steps[0]` carries no information and the first bar is 100 % forever. Either drop it or state in §4's comment that it is the denominator drawn again.

### C3. Fixture under-tests the clamp it exists to test

§7.9 item 6: *"Includes an **86-char** story headline (clamp test)"* for the 2-line `.dash-live-page` clamp, gated at 390 px. Live production today already serves a 122-character de-branded title (`Inca polygonal masonry in Cusco, Sacsayhuamán, and highland sites features massive irregular blocks fitting without mortar`; max raw `page_title` = 138). The fixture is 36 characters short of what the panel will meet on day one — and §7.9's stated purpose is *"the screenshot fixtures are deliberately rich so the layout is gated even while production is nearly empty."*

---

## D. Naming / smaller style breaks

- **`LIVE_WINDOW` changes meaning (§7.3 item 3).** It stays at 5 min and becomes `/live`'s **quiet** threshold, while the new `HERE_WINDOW` is `/live`'s actual window. A reader of `founders_stats.py` meets `LIVE_WINDOW`, `LIVE_LOOKBACK`, `LIVE_LIMIT`, `HERE_WINDOW` and will read `LIVE_WINDOW` as the live panel's window. §9.17 spends a paragraph on one-word-one-meaning; this is the one place the batch breaks it.
- **`SCROLL_PAGES` is a tuple** used only for `if page not in SCROLL_PAGES`. Membership constants in this module are sets — `INTERACTIONS` (35), `JOURNEY_EVENTS` (52), `SHALLOW_PAGES` (264, the constant it sits next to). Its own comment says *"= CONTENT_PAGES in boot.ts"*, and `boot.ts:17` is `new Set([...])`.
- **`problems()`'s docstring keeps five weights for six kinds.** Lines 312-315 enumerate them (*"a JavaScript error counts triple …, a dead link double, a slow page as often as it was measured, a bounce and an empty search once"*). §7.2 item 10 only says *"docstring (five kinds → six)"*. §5.2 updates the panel note and §7.4 item 5 updates the digest labels, so after this commit the Python docstring is the only one of the three still describing five weights.
- **`FINISH_WARN` is exported (§5.1).** Every dashboard component keeps its constants private and exports only behaviour and types: `SEVERITY`/`KIND_LABELS` private in `Problems.tsx:10,19` (exports `severity`, `problemLabel`); `BUCKET_LABELS`/`RAW_ROWS` private in `Sources.tsx:8,17`. `steps` is also a very thin export name next to `SCROLL_STEPS` and `FunnelStep`.
- **`without_brand` has a second separator to handle.** §3.8 says it *"keeps … 'Database - Ancient Nerds'"*. That title is live (it is one of only two page titles on the site that do not end in `" | Ancient Nerds"`), so the LiveNow list will print one row with the brand attached and every other row without. The fix belongs in `db.html`'s `<title>`, not in the panel — but the contract records it as intended behaviour without saying so.
- **§9.13's justification is the banned reasoning.** *"`session.language` and `session.device` are never NULL or empty (0 rows) — but `UNKNOWN_DEVICE`/`null` language stay, because 'never so far' is not 'never'."* I confirmed 0 nulls on both columns. The constants are fine — they mirror `UNKNOWN_COUNTRY` (`stats_analysis.py:221-222`) and `Session.device` is already `str | None` (line 126) — but *that* is the defensible reason. "It might happen one day" is the sentence CLAUDE.md exists to reject; a reviewer will read it as a licence.

---

## English-only rule: clean

No German string, label, comment or docstring is introduced anywhere in the contract. §7.4 item 3 (*"`_delta()` keeps its German docstring and Discord wording"*) touches `pipeline/lyra/analytics_alerts.py`, whose module docstring and comments are German throughout (lines 2-16, 41-46, 229-230) — keeping it is consistent, and its Discord output (`"none last week"`, `"last week 118, +20 %"`) is already English, as commit 30fb64d required. `DEVICE_LABELS` (Phone/Tablet/Laptop/Desktop/Unknown), the empty-state sentences in §10, `Intl.DisplayNames(['en'], {type:'language'})` and the `en-GB` number formatting all hold the line. One unavoidable exception nobody named: `LiveVisitor.title` prints the page's own `<title>`, and production already carries `Globo 3D: Explore 1,7M+ de Sítios Arqueológicos | Nerds Antigos` — visitor content, not chrome, so not a violation, but worth one sentence in the panel note.

---

## What I checked and found accurate

Every live number in the contract reproduced against production (`ssh ancientnerds` → `ancient_nerds_db`, db `umami`), 761 events, `2026-09-17 10:03:33` → `2026-09-19 09:03:36`:

- `session.language` and `website_event.page_title` exist as plain columns; 0 NULL/empty languages, 0 NULL devices.
- 55/55 `scroll_depth` events carry `url_path`; 209/209 page views carry `page_title`; longest `url_path` = 139 chars (§2.3's "139-character slug" is exact).
- `globe_ready`: `/globe.html | p75 24758.25 | fastest 9450 | 8 samples | 6 sessions` — exactly §2.2.
- Devices laptop 110 / mobile 43 / desktop 6; `zh-CN` 12; `en-US@posix` present on exactly one session.
- 6 `outbound_click`, all on `/news-archive/…`, youtube.com ×5 + getty.edu ×1, 6 distinct sessions; `discord_click` 0 rows ever.
- 10 of 69 sessions in the last 24 h have zero page views (§9.12's inner-`LATERAL` argument holds; the contract said 68, one session arrived since — §9.15 pre-declares this drift).
- `globe · INP` p75 504 ms / 14 samples and `globe` LCP p75 2004 ms — §9.16 and §4's `slow_start` comment are correct; `slow_start` score today would be 6 × 2 = 12, second behind 14, exactly as §9.16 predicts, and the §7.9 fixture's 17 visitors → 34 is consistent.
- `App.tsx:1822` `track('globe_ready', {ms: Math.round(performance.now())})`, `:1823` `globe_idle` with the literal `30000`, `MIN_SPLASH_DURATION = 3000` at `:195` — §3.6 and §9.9 verified.
- §9.8 verified: all 19 `*Main.tsx` reference `analytics/boot` (`dashboardMain.tsx:1-2` only as a comment explaining its deliberate absence), and `index.html`'s inline module at line 661 imports only `./src/shared/disclaimerContent.ts`.
- Guard tests: `"LATERAL"` does not contain `"ALTER"`; none of the three new queries contains `{`, `%s` or `'%`; all three bind `:website_id`/`:since`/`:until` — `tests/pipeline/test_umami_db_queries.py:35-50` passes. `test_problem_queries_read_the_events_the_frontend_actually_sends:80` asserts `"s.browser" in SQL_SESSION_EVENTS`, which survives the `s.browser, s.language,` edit.
- The `Fetch` markers in §2.6 are each unique across the final query set.
- Query arithmetic: 15 → 16 per refresh is right; `/problems` really goes 5 → 6 fetches.
- `Session(...)` is never constructed positionally outside `sessions_from_rows` (tests build rows through `ev()` in `tests/pipeline/test_stats_analysis.py:17-36`), so the new `language` field breaks nothing.
- CSS: `--dash-amber`, `--dash-green`, `--dash-paper` all exist (`dashboard.css:9-18`); none of the 11 proposed class names collides with the 68 present; `.dash-panel h3:first-child` (line 181) does match through a `.dash-exits` wrapper, so killing the duplicate rule is correct; `.dash-bar-value` is `white-space: nowrap` in an `auto` track (lines 357-380), so the Exits override is justified; wide/narrow counts (6 wide + 2 narrow today → 8 + 4) are right and produce no half-empty cell.
- `E501` is in `pyproject.toml:167`'s ignore list, so long comments alone will not fail `ruff check` — only the alignment does, via the formatter.
- `knip.json` entry globs plus the vitest plugin cover `__tests__/*.test.ts`, so the new test-only exports will not trip `npx knip`.
- No `try`/`except` is introduced anywhere in the contract.