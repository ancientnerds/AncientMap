## Verdict on my lens: the 390 px story does not hold, and two of the CSS mechanisms it rests on are broken by specificity, not by taste.

I measured against the repo's own gate artefact (`docs/reports/screenshots/dashboard-mobile.png`, 780×10128 px at `device_scale_factor=2` = **390 × 5064 CSS px**) and against live `umami` on `ancient_nerds_db`.

---

### 1. The height budget in §5.4 is understated by ~60 %. Band A is ~3.8 screens, not 2.1.

Per-panel heights scanned off the green `border-left` in the existing mobile gate PNG (8 panels, source order from `DashboardPage.tsx:84-91`):

| panel | measured CSS px @390 |
|---|---|
| Pulse | 273 (**stale**: 3 tiles side-by-side, pre-`810cb15`) |
| VisitorMap | 649 |
| SessionTypes | 336 |
| Sources | 684 |
| Journeys | 526 |
| Problems | **507 for 6 fixture rows** |
| TopContent | **1281** |
| FeedbackInbox | 460 |

Two consequences the contract misses:

**Problems ≈ 600 px is wrong.** `problems()` is `limit: int = 15` (`pipeline/stats_analysis.py:308`). The fixture has 6 rows (`scripts/dashboard_screenshots.py:238-268`) and already costs 507 px. A live `js_error` row is taller than a fixture row: the seven live messages are ~100 chars —
`Uncaught Error: Minified React error #418; visit https://reactjs.org/docs/error-decoder.html?invaria` — and `.dash-problem-label` gets ≈225 px of the 334 px panel content width, so it hits the 2-line clamp at `dashboard.css:627-636` every time, on top of `.dash-problem-detail` and `.dash-problem-who`. A full 15-row Problems on a phone is **1050–1580 px**, not 600.

**Pulse ≈ 520 px is wrong for current HEAD.** The PNG predates `810cb15`/`572a46f`: it shows three tiles in a row and no flags. Today `.dash-tiles` is one column below 560 px (`dashboard.css:753-757`), so it is four stacked tiles ≈ 424 px, plus h2/chrome ≈ 63, plus the contract's own 110 px strip + legend + axis ≈ 162 → **≈ 649 px**.

Recomputed Band A: 178 (header, measured — first panel border starts at device y=357) + 649 + 300 + 340 + ~1300 + 36 gaps ≈ **2800 px ≈ 3.8 viewports**. The three-band architecture is justified entirely by the 1760/2.1 number, and the panel that blows it (Problems) is the one placed in the band that can never be collapsed.

**And nothing checks this.** §7 step 12 calls the 390 px gate "the acceptance test". `scripts/dashboard_screenshots.py:354-360` measures **horizontal** overflow only (`scrollWidth - clientWidth`) and screenshots `full_page=True`. It cannot fail on vertical length, and it cannot fail on colour. The contract's central 390 px claim has no gate behind it.

### 2. `page.wait_for_selector(".dash-map-dot")` will hang the moment bands land — and the contract edits that file without touching the line.

`scripts/dashboard_screenshots.py:352` waits for `.dash-map-dot` with no `state=` argument, i.e. Playwright's default `state="visible"`. `.dash-map-dot` lives only in VisitorMap, which §5.4 puts in **Band B**, rendered `hidden` at 390 px. The mobile leg runs first (`:346`), so the gate dies on a 30 s timeout before it takes a single screenshot. §7 step 12 lists two selectors to *add* and leaves `:352` alone.

### 3. `.dash-spark rect` beats `.dash-spark-ai` on specificity. The whole colour ruling renders as one green.

`dashboard.css:334-337`:
```css
.dash-spark rect { fill: var(--dash-green); fill-opacity: 0.85; }
```
That is specificity (0,1,1). §5.3's new `.dash-spark-{ai,human,unconfirmed}` are (0,1,0). §5.3's stated mechanism is source order — "Added, all at the end of the file" — and **source order never beats specificity**. Every segment of the stacked strip paints `--dash-green`. Worse, it fails silently: the added screenshot waiter `.dash-spark-ai` still matches, and no gate diffs pixels. The fix has to be `.dash-spark .dash-spark-ai` or `rect.dash-spark-ai`, or line 334 must be edited — the contract says neither.

Same section, two more: `.dash-spark { height: 110px }` appended at the end leaves the dead `height: 56px` at `:330` in place for the next reader, and `.dash-spark rect:hover` becomes a second block for a selector that already exists at `:339`.

### 4. The inverse bug: `.dash-band-body` "that is the existing `.dash-grid`" means `hidden` never hides anything.

§5.4 specifies the body as "the existing `.dash-grid`". If the element carries both classes, `.dash-grid { display: grid }` (`dashboard.css:147-151`) is an **author** declaration and the `[hidden] { display: none }` it must defeat is a **UA** declaration — author normal always wins over UA normal. Bands B and C would render open at every width and the phone collapse would be inert. The contract's own note ("class beats the UA `[hidden]` rule") is the fact that breaks it. It needs to say explicitly that `.dash-band-body` must not also carry `.dash-grid`, and re-declare the grid under `:not([hidden])`.

### 5. Colour blindness: the ramp does not exist, and the L\* values it claims put adjacent segments below 3:1.

**The hex values are nowhere.** §5.3 says `--dash-seg-ai / --dash-seg-human / --dash-seg-unconfirmed (spec 8's measured ramp)` and never gives them. `grep` across the repo and across every 2026-09-19 plan file returns zero `--dash-seg-*` and zero hex triples in the wave-1 documents. The single most-defended decision in the contract is not implementable from it, and "worst pair 38 ΔE" is unauditable.

**The claimed L\* values are self-defeating on a stacked bar.** In CIE Lab, L\* is a function of relative luminance alone, so 92/66/40 *fixes* the WCAG contrast between adjacent segments regardless of hue:

| boundary | contrast |
|---|---|
| ai (L\*92) ↔ human (L\*66) | **2.13 : 1** |
| human (L\*66) ↔ unconfirmed (L\*40) | **2.48 : 1** |
| unconfirmed (L\*40) ↔ panel bg (`rgba(0,0,0,.55)` over `#060604`, L\*0.7) | 3.16 : 1 |

In a stacked bar the boundary that carries meaning is segment↔segment, and both are under the 3:1 non-text threshold. ΔE between the *unsimulated* pairs is irrelevant here; the founder is reading a seam.

**Geometry defeats ΔE anyway.** At 390 px: `.dash` padding 12+12, `.dash-panel` border-left 3 + border-right 1 + padding 14+14 → 334 px of content. 48 buckets × `width={0.7}` in a `viewBox="0 0 48 20"` (`Pulse.tsx:71-73`) → **4.87 px per bar, 2.09 px gutter**. I confirmed this against the gate PNG (strip spans ~332 CSS px). Live 48-hour split, computed with the `INTERACTIONS`/`auto_opens` rule from `stats_analysis.py:142-145`:

```
max hour total = 18 sessions;  32 of 45 hours have <= 5 sessions
ai segment = 3 sessions in 48 hours, in 3 separate hours, 1 each
```

One session at an 18 max on a 110 px strip is **6.1 px tall**. So the AI segment — the one the whole ramp is built to make visible — is a **4.9 × 6.1 px patch**, ~0.85 × 1.06 mm on a phone, subtending ~0.16° × 0.20°. CIE ΔE\*ab is defined on the 2° standard observer (~10 mm at 30 cm). Below roughly 0.5° all observers enter small-field tritanopia and chromatic discrimination collapses; a dichromat simulation on large patches does not transfer to this geometry. And the brightest step is spent on 3 events in 48 hours while the dominant class in **every hour I measured** (unconfirmed, 3–7 of 1–18) gets the 3.16:1 step.

Compounding it: `.dash-spark-key--{ai,human}` — §5.3 lists key modifiers for **two of the three** classes. A three-segment stack whose legend names two segments is exactly the fallback that colour blindness needs.

### 6. "Red stays … never data" is false in three places today, and the contract adds a fourth.

- `dashboard.css:608-614` — `.dash-dot--high` `#ff2a2a` / `.dash-dot--mid` `#ffb020` / `.dash-dot` 55 % green. Severity is **colour-only, 10 px, `aria-hidden="true"`** (`Problems.tsx:71`); `.dash-problem-kind` prints the kind, never the severity.
- `dashboard.css:319-325` — `.dash-delta--up` green / `--down` red in the Pulse tile sub-line (redundant ▲/▼ from `Pulse.tsx:16-17` saves it).
- `dashboard.css:776-778` `.dash-bar-hint--warn` and `:503-509` `.dash-chip--yes/--no`.

Viénot 1999 dichromat simulation on the actual variables (composited over the real panel background):

| pair | ΔE normal | ΔE protan | ΔE deutan | contrast |
|---|---|---|---|---|
| high `#ff2a2a` vs mid `#ffb020` | 65.0 | 39.6 | **22.5** | 2.04 |
| high `#ff2a2a` vs low 55 % green | 121.7 | **19.0** | 53.7 | 1.63 |
| green `#00cc66` vs `#ff2a2a` | 142.2 | **25.3** | 34.9 | 1.75 |

Under protanopia `#ff2a2a` → `#797925` while `#00cc66` → `#bcbc67`: red reads *darker* than green, so the severity ordering inverts, at ΔE 19 in a 10 px dot. **The dashboard's only severity encoding already fails the contract's own 38-ΔE bar** — and §5.2 adds two kinds to it (`webgl_lost` → high/red, `globe_start` → mid/amber) while §5.3 forbids amber as a data colour 40 lines later. That is self-inconsistent inside one section.

### 7. Panel-order defects that are load-bearing rather than taste

- **Band C leaves a half-empty desktop cell.** Band C is Live (wide), Paths (wide), TopContent (wide), **Outbound (narrow)**, FeedbackInbox (wide). `.dash-grid` is `repeat(2, …)` and `.dash-panel--wide` spans `1 / -1` (`dashboard.css:725-736`), so Outbound sits alone in column 1 and column 2 is blank. Wave 1 §5.4 engineered exactly two complete pairs and wrote "**No half-empty cell anywhere** — which is why Devices had to become narrow and Exits could not be promoted to wide". Promoting Sources to `wide` (§5.2) destroys wave 1's pair (4+5) and orphans its partner. §5.4's claim "on desktop … the grid is unchanged from today, so nothing regresses" is false: three separate `.dash-grid`s also prevent pairing across band boundaries.
- **The two findings the contract calls biggest are behind a tap.** §1 spec 5 calls the nginx-vs-Umami gap "the largest single finding in the wave"; §1 spec 9 calls Members "the end of the funnel and nothing else on the page can see it". Both land in Band B, `hidden` by default at 390 px. The contract never reconciles that.
- **The header's range switch is a no-op for a month and eats a whole phone row.** I confirmed `min(created_at) = 2026-09-17 10:03:33` (767 events total), so `days=30` returns exactly `days=7` until 2026-10-17 — the contract establishes this in §0 and then leaves two 44 px buttons as the second-most prominent control on a 390 px header that already wraps to two rows. Panel #14 FeedbackInbox has 2 items, both `answer=no`, both from the same session, one of them `text=this is just a test from MrSchneebly`. Panel #13 Outbound has 6 events. Those are the two a founder scrolls past, and they are correctly last.
- **New Problems kinds have no score, but the list is capped at 15.** §4.3 specifies the `webgl` loop but gives neither `webgl_lost` nor `globe_start` a score formula. `js_error` scores `sessions × 3` (27 for the live React 418), so an unscored `globe_start` can be pushed off a list the contract calls "the worst product number on the page".

### 8. Cross-wave naming collisions inside the table that exists to prevent them

- §2 lists `outbound` / `/outbound` / "wave one owns the shape". Wave 1 ships `Exits` / `/exits` / `SQL_EXITS` / `ExitsData` / `.dash-exits` / `.dash-note--gap`. Neither `outbound` nor `/outbound` appears anywhere in wave 1.
- `ProblemKind`: wave 1 §5.2 rules `SEVERITY.slow_start = 'high'` with a stated reason; §5.2 here renames it `globe_start` and demotes it to `'mid'`, without declaring an override. §7's rule "resolve by keeping both entries, never by picking one" applied literally to `Problems.tsx`'s two `Record<ProblemKind, …>` maps gives two kinds for one phenomenon and fails to compile, because §5.1's union carries only `globe_start`.
- §2 moves wave 1's scroll funnel from `/overview` (wave 1 §5.5: "Devices and Reading ride `overview`") to `/journeys` while saying wave one owns the shape.
- §5.3's added-class list omits every wave-1 class and every class `Scrapers.tsx` / `GlobeReach.tsx` need (`Cluster.verdict`, `reasons[]`, `pages[]` — up to 40 paths per cluster — have no existing class). `.dash-tiles + .dash-lists` is the only genuinely new non-strip, non-band rule in the list.

### 9. Undocumented semantic change in the one panel being re-specced

`types.ts:17-22` `HourBucket` carries `views`; §5.1 replaces it with `{hour, ai, human, unconfirmed, sessions}`. `Pulse.tsx:65,73-74` reads `h.views` and `:80` prints "Views per hour, UTC". The strip therefore silently changes unit from page views to sessions — materially: 18.09 22:00 UTC has **23 views but 3 sessions**; the 48-hour peak drops 23 → 18. The axis caption is never mentioned, and `sessions` is left undefined against the three segments (sum of the classes, or `count(distinct session_id)` active in the hour as `SQL_HOUR_BUCKETS` does — these differ).

---

## What checked out on my lens

- **The "45 rows across a 48-hour axis" bug is real and exact.** Live: 45 hour rows in the last 48 h; the gaps are 2026-09-18 11:00, 19:00, 21:00 UTC. `Pulse.tsx:63` slices `hours.slice(-48)` and `:79-81` labels `recent[0]`/`recent[last]`, so gaps compress the axis and the aria-label says "last 45 hours" over a 48-hour span. Fixing it with 48 fixed buckets is right.
- **The 720 px breakpoint is real and `.dash-lists` behaves as §5.4 claims.** `dashboard.css:738-741` gives `.dash-lists` two columns from 720 and one column below, and `.dash-panel--wide` only exists inside the 720 block (`:734-736`), so a `wide` Sources with a two-column `.dash-lists` genuinely stacks cleanly at 390. That specific rebuttal to spec 5 is sound.
- **No class-name collision** between the contract's new names (`.dash-band*`, `.dash-spark-*`, `--dash-seg-*`) and the 68 existing selectors, other than the `.dash-spark rect` specificity problem above. `.loading-retry` / `.webgl-lost-bar` are indeed in `src/styles/index.css`, a different sheet.
- **`.dash-tiles + .dash-lists { margin-top: 14px }` is needed and correct once.** `.dash-panel h3:first-child { margin-top: 0 }` (`:181`) matches through the `.dash-lists > div` wrapper, so without it the Members panel would butt its first heading against the tiles.
- **Scrapers at #2 is defensible on the data.** My own classification of the live 48 hours shows `unconfirmed` is the majority in most hours (17.09 17:00 → 7/7; 18.09 14:00 → 7/7; 18.09 16:00 → 5/5), so the headline session count genuinely needs its correction adjacent. It is slightly weaker than argued, because `Pulse.tsx:58-59` already prints "human sessions, N % of M" on each tile.
- **Baseline numbers re-verified and correct:** event counts (`vital` 401 vs the contract's 400 — drift, not error; `scroll_depth` 55, `site_open` 39, `js_error` 26, `media_play` 12, `globe_ready` 8, `outbound_click` 6, `filter_toggle` 4, `feedback` 2, `globe_idle` 2), `/globe.html` is the only globe path (133 views all-time), `discord_users` = 5 with newest signup 2026-08-28, likes 2, bookmarks 2, tracker since 2026-09-17 10:03.
- **`useStats(path, refreshMs)` already supports the 300 s Members refresh** (`useStats.ts:10`); no change needed there.

Key files: `C:/PythonProjects/AncientMap/ancient-nerds-map/src/styles/dashboard.css`, `C:/PythonProjects/AncientMap/ancient-nerds-map/src/components/dashboard/Pulse.tsx`, `C:/PythonProjects/AncientMap/ancient-nerds-map/src/components/dashboard/Problems.tsx`, `C:/PythonProjects/AncientMap/ancient-nerds-map/src/components/dashboard/types.ts`, `C:/PythonProjects/AncientMap/ancient-nerds-map/src/pages/DashboardPage.tsx`, `C:/PythonProjects/AncientMap/scripts/dashboard_screenshots.py`, `C:/PythonProjects/AncientMap/docs/superpowers/plans/2026-09-19-dashboard-wave1-contract.md`, `C:/PythonProjects/AncientMap/docs/reports/screenshots/dashboard-mobile.png`.