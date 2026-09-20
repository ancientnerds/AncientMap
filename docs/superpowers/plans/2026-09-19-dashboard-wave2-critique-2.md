I re-ran every load-bearing query against `ancient_nerds_db` (both `umami` and `ancient_map`), the VPS referral log, and the tree at `572a46f`. Findings first, then what I checked and found sound.

---

# FINDINGS

## 1. The headline AI fix does not fire: `AI_UTM_SOURCES` omits the value 11 of 12 AI sessions actually send
`§4.2` defines `AI_UTM_SOURCES = ("chatgpt", "perplexity", "copilot", "gemini", "claude", "openai")`. Live, today:

```
utm         | ref          | sessions
chatgpt.com | -            | 9
chatgpt.com | chatgpt.com  | 2
perplexity  | -            | 1
```

The utm value is literally **`chatgpt.com`**, not `chatgpt`. `§4.3` gives only the signature `def is_ai_entry(referrer, utm_source=None) -> bool` and never the body. With exact membership — which `§4.1`'s own rationale argues for ("`perplexity.ai` is a host, `perplexity` is a label, **neither contains the other**") — `is_ai_entry(None, "chatgpt.com")` is `False`, so `§4.1`'s rewrite `return AI_ENTRY if is_ai_entry(None, utm_source) else utm_source` returns `"chatgpt.com"` verbatim: exactly the bug `§9.2` declares mandatory to fix ("any rule written as 'entry referrer in `AI_HOSTS`' finds 2 of 12"). It would find **1** of 12. Since `AI_HOSTS` (`pipeline/stats_analysis.py:70-77`) already contains `chatgpt.com`, the utm column must be tested against `AI_HOSTS` too; `AI_UTM_SOURCES` is then only needed for bare labels.

## 2. Five overlapping AI vocabularies land in `pipeline/`, and the contract rules on none of them
`§9.8` adjudicates a 12-line `Tile` duplication in detail. After steps 3 and 5 the same package holds, with no import barrier between the files:

- `pipeline/stats_analysis.py:70` `AI_HOSTS` (6 hosts) and new `AI_UTM_SOURCES` (6 labels)
- `pipeline/referral_log.py` `ASSISTANT_HOSTS`, `UTM_ALIASES`, and `FAMILIES["ai"]` (13 hosts as regex, moved from `scripts/referral_report.py:58-66`)
- plus `stats_analysis.SEARCH_HOSTS` (7) vs `FAMILIES["search"]` (11)
- plus **two implementations of one function**: `source_family()` (`pipeline/stats_analysis.py:106`) and `family_of()` (`scripts/referral_report.py:89` → `pipeline/referral_log.py`)

MEMORY.md: *"NEVER duplicate utility functions. Check if it already exists and import it."* The contract needs an explicit ruling here, or the merge ships the exact thing `§9.8` spent a paragraph forbidding.

## 3. `ttl_cached`'s key drops the bound-parameter *values*
`§2.1`, the one code snippet the contract spells out:
> `def ttl_cached(ttl: float): ...   # decorator; key = (sql, since, until, sorted(params)) hashed`

`params` is the `**params` dict from `fetch(sql, since, until, **params)`. `sorted(params)` yields the **key names** (`['live']`), not the values. `/overview`'s `block()` passes `live=`, `SQL_GLOBE` passes `:path`, `SQL_CLUSTERS` passes `:min_sessions`/`:unknown_country`. No collision survives today only because `since`/`until` happen to differ — the first route that varies only a parameter silently serves another route's rows. Must be `sorted(params.items())`.

## 4. "so there is exactly one such helper in the repo" is false — there are already three
`§2.1` justifies `pipeline/stats_cache.py` on that claim. Existing:
- `api/cache.py:200` — `def cached(key_prefix: str, ttl: int = 3600)`, Redis with in-memory fallback, `_memory_lock`
- `api/routes/landing_html.py:73-80` — `_CACHE_TTL = 300.0`, `_cache: dict[str, tuple[float, bytes]]`, `_cache_lock`
- `pipeline/connectors/cache.py` — multi-tier LRU + Redis + DB

`stats_cache.py` is the fourth. There *are* real reasons for a new one (`api/cache.py`'s `cached` is `async`-only and lives under `api/`, which `Dockerfile.lyra:61 COPY pipeline/ ./pipeline/` does not ship). Say that; do not assert something untrue in a document that says "the live data wins and you stop and report".

## 5. The cache is unbounded, unlocked, and its saving is per-container, not global
- **Unbounded:** the key contains `until`, which advances every minute and is never evicted. ~14 keys/min × 1440 min = ~20 000 retained result lists/day in a `restart: unless-stopped` container — one of them the 30-day `SQL_SESSION_EVENTS` scan. Both existing in-process caches are single-key or Redis-TTL-evicted.
- **Unlocked:** `§2.1` says "stdlib only, ~25 lines"; `api/cache.py` and `landing_html.py` both guard with a lock.
- **Per-container:** `docker-compose.yml:86` `api: &api-service` and `:151-157` `api2: <<: *api-service` — two API containers behind an nginx upstream (8000+8001). `§2.1`'s "six scans collapse to one — **for all open tabs combined, not per tab**" and `§6`'s "~14 distinct queries/min **total**" are wrong by the process count. `§6` gets this right for the referral log ("`api` and `api2` each hold their own cache") and wrong two sections earlier.

## 6. The mobile band collapse cannot work, and the contract's own CSS note is the proof
`§5.4`: "a `.dash-band-body` that is the existing `.dash-grid`", `<div className="dash-band-body" hidden={!open}>`, plus
```css
@media (min-width: 720px) { .dash-band-body[hidden] { display: grid; } }   /* class beats the UA [hidden] rule */
```
That note is correct — and it kills the design. `ancient-nerds-map/src/styles/dashboard.css:147-151`:
```css
.dash-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
}
```
Author-origin, unconditional. If the band body carries `dash-grid`, `hidden` is overridden **at every width**, so the phone never collapses and `§5.4`'s entire 390 px justification evaporates. The other reading — `.dash-band-body` restates those three declarations plus the `@media (min-width:720px)` two-column override at `:725-728` — is a verbatim duplicate of `.dash-grid`. Pick one and write it down.

## 7. Two new CSS rules collide with rules already in the file, and the strip renders all green
`§5.3` says the additions land "all at the end of the file". Already present:
```css
/* dashboard.css:327 */ .dash-spark { display:block; width:100%; height:56px; margin-top:14px }
/* dashboard.css:334 */ .dash-spark rect { fill: var(--dash-green); fill-opacity: .85 }
/* dashboard.css:339 */ .dash-spark rect:hover { fill-opacity: 1 }
```
Appending a second `.dash-spark { height: 110px }` and a second `.dash-spark rect:hover {…}` leaves two blocks for the same selectors 480 lines apart — the pattern `feedback_slider_approach.md` forbids ("never strip working CSS to rely on global cascading; restyle in-place"). Worse: `.dash-spark rect` has specificity (0,1,1) and outranks `.dash-spark-ai` / `-human` / `-unconfirmed` (0,1,0), so the Viénot/CIE-Lab-validated ramp `§5.3` spends a paragraph defending **renders as flat green**. Needs `.dash-spark rect.dash-spark-ai` or an in-place edit of line 334.

## 8. `SourcesData` is specified two incompatible ways and re-declares an existing type
`§2`: `log{available, reason?, covered_from, covered_days, families[], pages[], statuses[], ai[]}` — availability *inside* `log`.
`§5.1`: `log: LogCoverage | null` plus a sibling `log_reason: string | null`, and `LogCoverage` carries neither `available` nor `reason`.

Separately, `§5.1` inlines the row shape — `sources: Array<{ source; family; sessions; views }>` — while `ancient-nerds-map/src/components/dashboard/types.ts:145-149` already exports `interface SourceRow` and `Sources.tsx:31` consumes it as `bucketTotals(rows: SourceRow[])`. The instruction should read "add `views: number` to `SourceRow`".

## 9. `§9.1` "Do not touch `Sources.tsx`" contradicts `§5.2` and `§5.4`
`§5.2` CHANGED panels: *"`Sources.tsx` — gains a second column: `.dash-lists` …, the coverage sentence as `.dash-note`, and a `LogStatus` list …. Panel becomes `wide`. Question becomes …"*. Same pattern for `/countries`: `§2` marks it "**unchanged**" while `§2.1` routes it through the new `_now()`.

Related and unresolved: because the `/sources` route calls `fs.source_family(r["source"])` (`api/routes/founders_stats.py:179`) — one positional arg, i.e. the **referrer** slot — `§4.1`'s rewrite of the `if utm_source:` branch never executes there. The bare `perplexity` row keeps falling to Other on the panel after this wave. `§9.1` never says so.

## 10. The dashboard is never server-rendered, so `§5.4`'s hydration argument targets a page with no hydration
`ancient-nerds-map/dashboard.html:24` loads `/src/dashboardMain.tsx`, which does:
```tsx
ReactDOM.createRoot(document.getElementById('root')!).render(…)
```
`createRoot`, not `hydrateRoot`. `§5.4` calls the band state "hydration-safe … identical on server and client … the same class of bug as React 418 in `reference-ssr-hydration-storage.md`", and proposes that "`render.test.tsx`'s storage guard is joined by an assertion that the dashboard calls no `matchMedia` during render". `render.test.tsx` is `ancient-nerds-map/src/seo/__tests__/render.test.tsx`; it renders the 10 **SEO** route types through `SeoRoute`/`RouteProvider` from `./fixtures`. `DashboardPage` is not in `FIXTURES` and is unreachable from `SeoRoute`. The "avoided by construction" reasoning is what let finding 6 through.

## 11. Three counts wrong, in a document whose own rule is "nobody writes a number they did not count" (`§2`, `§9.13`)
- `§4.1`: "all **six** existing call sites [of `problems()`] … keep passing". There are **12**: `api/routes/founders_stats.py:149`, `pipeline/lyra/analytics_alerts.py:236`, and `tests/pipeline/test_stats_analysis.py:279,314,329,334,349,359,360,367,387,398`. *(The substantive claim holds — every call site uses keyword arguments, including `limit=5` at line 398 — so inserting `webgl` between `searches` and `limit` is safe.)*
- `§0`'s referral-log status row omits four statuses. My tally of all 402 lines today: `200:266, 404:50, 301:27, 410:21, 307:14, **302:13**, 403:4, 499:4, **405:2, 500:1, 206:1**`. 302 is the third-largest non-200 and the panel's spec is `status >= 300`.
- `§7` step 11 lands `DashboardPage.tsx` last but never fixes its docstring — `ancient-nerds-map/src/pages/DashboardPage.tsx:2` says "**eight panels**", becoming 14 in three bands. `§9.13` fixes the identical stale count in `founders_stats.py:2` and misses this one.

## 12. `Flags` belongs in `Flag.tsx`, which already exists
`§5.2` moves `Tile` (`Pulse.tsx:44-55`) and `Flags` (`Pulse.tsx:28-42`) into a new `components/dashboard/Tile.tsx`. But `components/dashboard/Flag.tsx` already exists and exports the single `Flag` that `Flags` renders in its loop (`Pulse.tsx:35`). A file named `Tile.tsx` exporting `Flags` while `Flag.tsx` sits beside it splits one concern across two files on a name collision. Also `Tile` gains an optional `value?: number` beside its currently-required `window: CountryWindow` — two mutually exclusive props with nothing at the type level saying so, where the rest of `types.ts` uses discriminated shapes.

## 13. Minor
- `§3.2`'s `SQL_GLOBE` doc-comment hard-codes `App.tsx:207`; `§1`/`§7` hard-code `useSiteSearch.ts:360`. Both are accurate today, but the repo has only two precedents for line numbers in comments (`pipeline/lyra/theo_citations.py:319`, `api/routes/articles_html.py:310`), both prose ranges; everything else cites file + symbol (`pipeline/article_html_renderer.py, _NOT_FOUND_FEEDBACK`).
- `§7` step 12 calls `scripts/dashboard_screenshots.py` "the 390 px **gate** … the acceptance test". It is a manual script — `grep dashboard .github/workflows/ci.yml` returns nothing.
- `scripts/funnel_report.py:10` — "known bot substrings, see `BOT_UA_RE` in `goto.py`" — is a straggler the `§4.5` follow-on edit list misses; it will point at a deleted symbol.
- The English `detail` strings `problems()` will emit for `webgl_lost` and `globe_start` are never quoted. Commit `30fb64d` explicitly pulled "die Problemdetails aus `pipeline/stats_analysis.py`" under the English-only rule, so they are in scope and unspecified.

---

# SOUND ON MY LENS — WHAT I CHECKED

**English-only rule (commit `30fb64d`, scope = "Jede sichtbare Zeile der acht Panels, dazu die Texte, die das Backend liefert … und der Discord-Digest"):** clean. `WEBGL_PHASES`, `LIFESPAN_BUCKETS`, `SESSION_CLASSES`, `AI_ENTRY`, every panel sentence and the new `/sources` question are English; keys are English too, which is the commit's explicit second rule. Pipeline-internal German (`tests/pipeline/test_umami_db_queries.py:2-7`, `pipeline/lyra/analytics_alerts.py`'s docstring) is untouched and out of scope.

**No fallback code / no defensive try-except:** clean. `§8` states "Not one of them is fixed with a try/catch" and the three WebGL defects are genuine root causes. The `log: null` + `log_reason` / `unavailable_reason()` shape is CLAUDE.md's *prescribed* pattern (`available = False` + `unavailable_reason`), not graceful degradation. `parse_lines` skipping unparsable lines mirrors the existing `except json.JSONDecodeError: continue` at `scripts/referral_report.py:137-138`.

**Import boundary — correct in both directions.** `pyproject.toml:46-59` forbids `pipeline → api` with 5 frozen exceptions (none relevant); `:61-96` forbids `api → pipeline` with an `ignore_imports` allowlist. The two proposed entries have the right form, the right comment style (prose + parenthesised date, matching `:84-95`), and are genuinely required. `pipeline.stats_cache` correctly needs no entry: every path from `api` into it runs through `pipeline.umami_db` / `pipeline.members_db`, whose edges the ignore list already removes, so no chain survives. All four `§4.4` reasons verified: `Dockerfile.lyra:61` copies `pipeline/` only; `pipeline/database.py:59 def get_db` exists and is the first sanctioned exception (`pyproject.toml:68`); the card-game models live under `api/`. The `BOT_UA_RE` move **removes** a real violation — `scripts/referral_report.py:51 from api.routes.goto import BOT_UA_RE` behind a `sys.path.insert` — and `api/routes/goto.py:20 import re` is indeed dead afterwards (`BOT_UA_RE` at `:40-45` is its only user).

**`Session.pages` → property is safe.** Repo-wide the only writer is `pipeline/stats_analysis.py:191 s.pages += 1`; readers are `:143`, `:395`, and `tests/pipeline/test_stats_analysis.py:151`. No construction passes `pages=`.

**`SQL_HOUR_BUCKETS` deletion:** confirmed repo-wide — exactly `api/routes/founders_stats.py:23,68`, `pipeline/umami_db.py:69`, `tests/pipeline/test_umami_db_queries.py:23`. `pipeline/lyra/analytics_alerts.py:27-35` does **not** import it. The `QUERIES` tuple is a module-level `getattr` loop (`:34-36`, `:41-43`), so the same-commit rule is real. The `ARRAY[]::float8[]` gotcha is real too: `:38` asserts `"{" not in sql`.

**Test compatibility:** route tests patch `fr.fetch` (`tests/api/test_founders_stats_routes.py:110,135,145`), so `@ttl_cached` on `umami_db.fetch` is invisible to them. `Record<ProblemKind, …>` is a genuine conflict gate (`Problems.tsx:10` `SEVERITY`, `:19` `KIND_LABELS`).

**`§3.5` application-DB facts — all hold live:** `research_requests.user_id` is `character varying` and joins **59/59** against `discord_users.discord_id` (`u.id` is a `uuid` and would match nothing); `discord_users.roles` is `jsonb`; every timestamp on both tables is `timestamp without time zone`; `user_contributions` has `submitter_ip` and no user column, all **932** rows `source='lyra'`. Counts: discord_users 5, site_likes 2, site_bookmarks 2, card_collections 47, token_usage_logs 126, research_requests 59.

**`§4.5` log mechanics:** `docker-compose.yml:125` binds `./logs:/app/logs:ro` on `api: &api-service`, `:153 <<: *api-service` gives `api2` the same mount; file is `-rw-r--r-- www-data:root`, 402 lines; every `t` carries `+02:00`.

**Live baseline re-verified:** 211 views / 161 sessions in 7 d. Custom events exactly as stated (vital 400, scroll_depth 55, site_open 39, js_error 26, media_play 12, globe_ready 8, outbound_click 6, filter_toggle 4, feedback 2, globe_idle 2). All-time `event_type=2` returns those ten names and nothing else — `search`, `search_empty`, `story_open`, `paper_open`, `not_found`, `share`, `lyra_chat`, `discord_click`, `hub_click` have **never** fired. `site_open` context = site 36 / globe 2 / radar 1. `/globe.html` is the only path matching "globe": 33 views / 19 sessions. AI arrivals 12 sessions, 10 utm-only. `a5a1307` **is** an ancestor of `572a46f` and `HEAD == origin/main`, so `§9.3`'s correction stands.

**`§5.2`'s `getCountryCode()` reuse is right:** exported at `ancient-nerds-map/src/utils/countryFlags.ts:338`, folds England/Scotland/Wales→GB (`:81-83`) and Türkiye→TR (`:61`) — and the live `site_open` `country` values are **names** ("England" 8, "Scotland" 3, "Wales" 1, "Bosnia and Herzegovina" 3), so a name→code function is the correct one and the UK block is real.

**`§15`'s two bug tickets check out:** `markGlobeActivity` is defined at `App.tsx:207` with exactly three call sites (`:516`, `:1020`, `:1024`); `useSiteSearch.ts:360` is `if (searchingRef.current) return // API results still pending: no count to report`, and because it returns before `trackedQueryRef.current = q` and the effect only re-runs on `debouncedQuery`, the event for that query is lost permanently.