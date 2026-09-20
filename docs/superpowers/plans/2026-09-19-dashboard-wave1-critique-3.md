I read the actual dashboard code, CSS, screenshot gate, and queried the live Umami DB. Findings ranked by severity, all on the mobile/layout lens.

---

## 1. §7.7's edit instruction cannot produce §5.4's order (provable contradiction)

`DashboardPage.tsx:84-91` renders **`SessionTypes` before `Sources`**. §5.4's target order has **`Sources` (4) before `SessionTypes` (6)**.

§7.7 specifies the change as *"4 JSX insertions at slots 2, 5, 7, 11"*. Insertions preserve the relative order of existing elements, so following §7.7 literally yields:

```
Pulse, LiveNow, VisitorMap, SessionTypes, Exits, Sources, Devices, Journeys, Problems, TopContent, Reading, FeedbackInbox
```

That pairs **SessionTypes↔Exits** and **Sources↔Devices** on desktop — the inverse of both semantic pairs §5.4 and §9.1 spend three paragraphs justifying ("Sources↔Exits and SessionTypes↔Devices are the two semantic pairs"). The grid still has no holes, so nothing fails; it just silently ships the wrong pairing. §7.7 must also say *swap `SessionTypes` and `Sources`*.

## 2. The narrowest column is 720 px, not 390 px — and it is completely ungated

Arithmetic from `dashboard.css`:

| viewport | `.dash` inner | narrow column | **panel content box** |
|---|---|---|---|
| 390 px | 366 (`padding:12px`, line 67) | 366 | **334 px** (−14−14 padding line 155, −3−1 borders line 156-157) |
| **720 px** | 680 (`padding:20px`, line 721-722) | (680−16)/2 = **332** | **292 px** (−18−18 line 731, −4) |
| 1280 px | 1140 (`max-width:1180`, line 65) | 562 | 522 px |

**A narrow panel at the 720 px breakpoint is 42 px tighter than the same panel on a 390 px phone.** Both new narrow panels (`Exits` slot 5, `Devices` slot 7) live there, and the range 720–~830 px is the whole worst case.

`scripts/dashboard_screenshots.py:345-348` shoots only 390 and 1280, and `:359-360` raises only on the mobile shot. So the contract's single layout gate (§7.9 "Gate: … `horizontal overflow 0px` for `dashboard-mobile.png`", §8 step 12) **never renders the tightest column that exists**.

Corroboration that 292 is the real number: §9.1 quotes the device spec's objection as "`.dash-lists` gives ~160 px columns inside a half-width panel at 720 px". The true figure is `(292 − 28 gap)/2 = 132 px` (`dashboard.css:738-741`). The ruling is right; the number it rests on is 20 % optimistic.

Secondary: `dashboard.css:46` sets `body { overflow-x: hidden }`, which propagates to the viewport — the `documentElement.scrollWidth − clientWidth` probe at `scripts/dashboard_screenshots.py:354-356` is weaker than §7.9 implies, and §6's justification for `.dash-exits .dash-bar-value` ("would push the 390 px layout sideways") names the wrong breakpoint.

## 3. `.dash-live-row` is not "a mirror of `.dash-problem`" — it drops the mechanism that makes `.dash-problem` survive 390 px

§6 justifies `grid-template-columns: 10px 18px auto minmax(0,1fr) auto` as "mirrors `.dash-problem`, which already passes 390 px".

`.dash-problem` (`dashboard.css:586-593`) is **four** tracks, and it passes 390 px *because its two long fields escape the single line*: `.dash-problem-detail` and `.dash-problem-who` both carry `grid-column: 2 / -1` (lines 646-650, 667-671). Only `[dot, kind(nowrap), label(1fr, 2-line clamp), score(nowrap)]` ever share a line.

`.dash-live-row` is **five** tracks with **no `grid-column` escape rule anywhere in §6's class list** — dot, flag, an unspecified `auto` track, the clamped title, and `.dash-live-here`. Budget at 390 px:

```
334 content − 10 (dot) − 18 (flag) − 4×8 gaps  = 274 px for [auto, 1fr, auto]
.dash-live-here "2 h 11 min" nowrap mono ≈ 77 px   (JetBrains Mono 0.6em @0.8rem)
track 3 (country/device/browser, cf. .dash-problem-who) ≈ 90-110 px
→ .dash-live-page gets ~90-110 px × 2 clamped lines ≈ 26-32 characters
```

Live `page_title` today: **209/209 filled, mean 72 chars, max 138** (verified). Minus `TITLE_BRAND` (16) that is still a 122-char worst case and a 56-char median. So **the median live row shows under half its headline**, on the panel §5.4 promotes to slot 2 answering *"what are they looking at right now?"*.

Two fixes exist and neither is in the contract: give `.dash-live-page` `grid-column: 2 / -1` on a sub-row (the `.dash-problem` pattern), or drop track 3 to a sub-row.

Related: §7.9.6's fixture headline is **86 chars**, i.e. *shorter* than the live max of 122 after brand-stripping. The clamp test is weaker than production.

## 4. The screenshot fixtures under-render the two tallest new panels

- §7.3 sets `LIVE_LIMIT = 12`. §7.9.6's fixture is *"six visitors, `total: 9`, `summary: "9 visitors in the last 30 minutes, 6 shown"`"*. With a limit of 12, a response with `total: 9` returns **9** rows, never 6 — the fixture describes a state the API cannot emit, and the gate never sees LiveNow at its 12-row maximum height (its position-2 worst case).
- §7.9.3 calls `nb` → "Norwegian Bokmål" *"the longest label the live data can produce"*. **`nb` is not in the live data.** Full live language set: `en-US 93, en-GB 21, zh-CN 12, de-DE 7, tr-TR 4, de 2, en-CA 2, pl 2, fr-FR 2, pt-BR 2, it-IT, sk-SK, es-MX, en-PK, sv-SE, nl-NL, en-IE, ru, en-US@posix, en-NZ` — longest label is "Portuguese" (10 chars). And it stresses nothing anyway: `.dash-bar-label` is `nowrap` + `text-overflow: ellipsis` (`dashboard.css:368-374`), so a long label truncates by construction. `en-US@posix` is confirmed present (1 session) — §9.13's guard is justified.

## 5. Nothing gates vertical length, which is this dashboard's actual mobile failure mode

The current 8-panel mobile screenshot is **780 × 10128 px @ 2× = 390 × 5064 CSS px — six full phone screens already**.

The four new panels add roughly: LiveNow ~650 px (12 rows), Exits ~400, Devices ~420 (4 device + 6 language bars + tail + note), Reading ~850 (5 headings + 5 base lines + up to 20 step bars + 2 notes) ≈ **+2 300 px → ~7 400 CSS px, ~8.8 screens**. `Reading` at slot 11 starts around **6 300 px = screen 7.5**.

The contract's gate checks one number (`overflow > 0`) and prints nothing about height. A `page.evaluate("document.body.scrollHeight")` assertion in `scripts/dashboard_screenshots.py` costs one line and is the only thing that would ever notice.

## 6. "Two clean pairs, zero holes" optimises grid cells, not visible emptiness

`.dash-grid` has no `align-items`, so grid default `stretch` applies and both panels in a narrow row render at the **taller one's height**. §9.1's whole case is "no hole", but the chosen pairing puts the tallest narrow panel next to the shortest:

- **Sources ↔ Exits**: Sources is 6 bucket bars + `<h3>` + up to 8 raw rows = **14 bar rows** (`Sources.tsx:46-55`, `RAW_ROWS = 8`). §10 says Exits renders **2 outbound rows + a Discord empty state + 2 notes**. That is a half-empty cell, just not a grid hole.
- **SessionTypes ↔ Devices**: SessionTypes is 5 rows + one note (`SessionTypes.tsx:9-15`); Devices is 4 + 6 = 10 rows + tail + note. SessionTypes gets ~5 rows of dead space.

Height-balanced pairing would be Sources↔Devices (14 vs 10) and SessionTypes↔Exits (5 vs ~4). That breaks the semantic pairs; the point is that §9.1 never weighed it and presents "zero holes" as if it settled the layout.

## 7. The panel a founder scrolls past: **Reading** (slot 11, wide)

Verified against live: **55 `scroll_depth` events, 17 distinct (session, path) pairs** — story 17, country 2, site 1 by my own path bucketing. §10's claim of "9 counted + 8 ghosts" reproduces exactly (17 = 9 + 8). With `SCROLL_MIN_READS = 10`, the best page type is **story at 9** → `rated: false` everywhere → §10's own description: a wide panel at position 11 that prints *"No page type reached 10 scrolled reads yet"*, a thin caveat line, and *"8 scrolls arrived without a page view"*.

Its own note (§10) then says **"`scrolled/opened` must never become a KPI"** because a page shorter than the viewport fires no scroll event at all (`boot.ts:84-91` gates on `CONTENT_PAGES`). A wide panel, ~850 px tall, at ~6 300 px scroll depth, whose data is empty for weeks and whose only ratio is declared un-usable, is the one to demote below `FeedbackInbox` or hold until `story` clears 10.

Runner-up is **Devices**: §10 concedes its numbers "will not match Umami's own device/language report (laptop 110 vs our 31, zh 12 vs our 1)". I confirmed the all-session figures live: `laptop 110 / mobile 43 / desktop 6`. A panel that contradicts the tool linked in the header (`DashboardPage.tsx:76`) by 3.5× will get clicked through to Umami once and ignored after.

## 8. Smaller, verified

- **§6 "all 68 selectors"**: `dashboard.css` has **102 rule blocks / 70 distinct `.dash*` class selectors**. The substantive claim holds — I grepped all eight proposed classes (`dash-live`, `dash-live-row`, `dash-live-page`, `dash-live-here`, `dash-dot--live`, `dash-funnel-base`, `dash-exits`, `dash-note--gap`) against `dashboard.css` and all of `src/`: **zero hits, no collisions**. `.dash-empty b` is genuinely inert (no `<b>` in any empty string — `BarList.tsx:26`, `Problems.tsx:65`, `Journeys.tsx:47`). The count "68" is just wrong.
- **§6's `.dash-exits h3:first-child` kill is correct**: `.dash-panel h3:first-child` (line 181-183) is a descendant selector and does match through a wrapper `<div class="dash-exits">`. Note the asymmetry it creates: Devices has **no** wrapper, so its first `<h3>` is *not* `:first-child` (the `<h2>` from `Panel.tsx:17` is) and keeps `margin-top:14px`, while Exits' first `<h3>` gets `0`. 2 px of inconsistency between two panels the contract pairs as "the Exits pattern" (§5.3).
- **`Flag` is a fragment of two elements** (`Flag.tsx:16-24`). `Problems.tsx:45-47` wraps it in `<span className="dash-flag">` specifically because `.dash-flag { position: relative }` exists to contain `.dash-sr` — `dashboard.css:274-279` records that omitting it "drags the phone layout 451 px sideways (measured 2026-09-19)". §6 gives `.dash-live-row` an 18 px track but never says the flag must be wrapped. Same trap, one commit later.
- **Unmentioned breakpoints**: `dashboard.css` has **three** width breakpoints — 720 (line 719), **560** (line 753, tiles 2-up), **1024** (line 759, tiles 4-up). The contract only ever names 720 and 390. The tile-sub worst case is at **1024 px**, not 560: tile content box there is `(1024−40−40−24)/4 − 22 ≈ 208 px`, and §6's longest new string `▼ 20 % vs previous 7 days (was 118)` at 0.65rem mono ≈ 218 px. It wraps, as §6 predicts — but it wraps at 1024, a width the contract never considers and the gate never shoots.
- **§3.5 re-derives the page type that the tracker already sends.** `boot.ts:91` emits `track('scroll_depth', { depth, page })` — `page` is already the `CONTENT_PAGES` type. `SQL_EXITS` (§2.4) reads exactly that key for exits, but `reading_funnels` throws it away and re-derives via `page_type(url_path)`. Off my lens, but it is a Python/TS drift surface the contract claims elsewhere to be avoiding.

---

## What I checked and found sound

- Grid math: 8 wide + 4 narrow, `grid-auto-flow` is default `row` (no `dense`), `.dash-panel--wide { grid-column: 1 / -1 }` (line 734-736) → §5.4's order produces exactly two full narrow rows and **zero empty grid cells**. Confirmed by hand-placing all 12.
- `.dash-exits .dash-bar-value { white-space: normal }` is the right fix: `.dash-bar` is `minmax(0,1fr) auto` (line 362) and `auto` bottoms out at min-content, so `normal` lets the hint wrap instead of pinning the track at max-content. Works at 292 px as well as 334 px.
- `.dash-dot--live` does not conflict with `--high`/`--mid` (lines 608-614); appending at EOF is safe (one modifier per element).
- `.dash-note--gap`, `.dash-funnel-base`, `.dash-live*` — no specificity or cascade problem from EOF append (§7.8).
- Live-data claims I re-ran: devices `laptop 110 / mobile 43 / desktop 6` ✓; `en-US@posix` present, 1 session ✓; `page_title` 209/209 filled ✓; outbound hosts `youtube.com ×5 / getty.edu ×1` ✓; `scroll_depth` 55 events ✓; 17 scrolled (session,path) pairs = 9 counted + 8 ghosts ✓. `Reading` is empty as §10 describes.
- `useStats(path, refreshMs = 60_000)` (`useStats.ts:11`) does take the parameter — §1.3's 30 s poll needs no hook change, and `refreshMs` is in the dep array (line 21) so it won't leak intervals.
- `DashboardPage.tsx:2` really does say "eight panels" — §5.5's docstring bump is a real edit, not a phantom one.