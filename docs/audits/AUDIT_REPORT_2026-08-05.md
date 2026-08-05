# Audit Report — full — 2026-08-05

Executed per `docs/procedures/CODE_AUDIT.md` (all 8 steps). Deep review fanned out
to 10 parallel review agents (~104 files fully read); fixes applied by 5 fix agents
plus the coordinator; every fix re-verified by the full gate suite.

## Summary

| Severity | Found | Fixed | Manual/Backlog |
|----------|-------|-------|----------------|
| Critical | 3 | 3 | 0 (1 with follow-up decision) |
| Major | 51 | 34 | 17 |
| Minor | ~97 | ~48 | ~49 |
| Info | ~37 | n/a (per procedure) | tracked below where actionable |

New-file discovery (Step 0.5): **54 files were missing from the Key Files table**
(entire Theo V2 + knowledge-graph stack) — table updated in this run; `api/routes/patreon.py`
removed (file no longer exists in the codebase).

## Quality Gate: PASS (with 2 documented MANUAL items)

| Condition | Result |
|-----------|--------|
| Critical findings = 0 (after fixes) | PASS |
| Major security findings (D2) = 0 (after fixes) | PASS — remaining D2 items are hardening follow-ups, not open holes (see Backlog) |
| Hardcoded secrets = 0 | PASS (gitleaks clean; 1 expired JWT removed from HEAD; **Serper key rotation = MANUAL**) |
| New anti-patterns (P1–P14) = 0 | PASS (all new code verified) |
| Docker images pinned | PASS |
| LLM prompt injection guards | PASS (61/61, CI-enforced) |
| Deprecated API usage (P6) = 0 | PASS (semgrep rule hardened to catch bare `datetime.utcnow` references) |
| No eval/exec on external data | PASS |
| API contract preserved (P9) | PASS (no parameter defaults/limits changed) |
| DB schema compatible (P10) | PASS (only additive: `onupdate` on 2 columns) |
| Credit grant idempotency (app + DB) | PASS |
| Credit deduction row locking | PASS (stale-lock hole closed via `populate_existing()`) |
| OAuth CSRF protection | PASS with caveat — state signed/expiring/allowlisted, but not browser-bound (**MANUAL M3**) |
| Webhook signature verification | N/A — Patreon integration removed from codebase |
| Admin endpoints server-side auth | PASS (library/refresh rate-limited; auth decision = MANUAL M2) |
| JWT signing key enforced | PASS |
| Tier lifecycle correctness | PARTIAL — rejoin-in-same-month grant collision found (**MANUAL M4**) |

## Fixed (Critical)

1. **Citation laundering** — `journal_assessor` D2/D3 fixes inserted LLM-chosen `[N]`
   markers AFTER `verify_all_citations` ran. New re-verification pass in
   `article_generator.py` (step 8) re-runs the verifier whenever the assessor
   applied fixes. Additionally: `citation_verifier` now **fails closed** on
   check exceptions (was: exception → citation kept).
2. **Unauthenticated heavy endpoint** — `POST /api/library/refresh` had no
   auth/rate limit. Now rate-limited 2/10min/IP (deploy pipeline unaffected).
   Auth decision deferred (MANUAL M2 — deploy script curls it unauthenticated).
3. **Cardgame stale-lock double-spend** — `with_for_update()` re-queries did not
   refresh already-loaded attributes (SQLAlchemy identity map), so concurrent
   pack opens/claims passed the balance check on stale values. Fixed with
   `.populate_existing()` at all 7 sites (packs, rewards ×2, expedition ×2,
   quiz, achievements) + guarded UPDATEs for quiz submit/achievement claim.

## Fixed (Major — grouped)

**Auth/Payment:** `/me` DetachedInstanceError for paying monthly-tier users
(anchor date read after session close); admin UUID 400s; ledger note (see M4).

**Theo API/Worker:** credit-reservation leak on DELETE of queued requests;
watchdog demotes to UNKNOWN after 5 failed probes (was: fail-open forever);
SSRF validation for user-supplied `web_urls` (scheme + DNS-resolve + non-global
IP rejection); TOCTOU on section-approval version (conditional UPDATE);
claim/complete UPDATEs now status-guarded (cancel no longer overwritten);
`pipeline_trace` capped; event-loop blockers wrapped in `to_thread`
(quota probe ×2, `_auto_publish`, Discord webhook, graph injectors).

**Theo Pipeline:** `research_state.started_at` naive-utcnow default (the
parens-less form the original semgrep rule missed — rule hardened);
`token_accounting` race (real lock, wrong GIL comment corrected); citation tier
spoofing via URL substring (`evil.com/?x=nature.com` scored Academic — now
netloc suffix-match); `_stage_write_section` now uses the registry-assigned
reference number (was coincidental agreement); MiniMax auth-class failures
(401/403) now raise `MiniMaxAuthError` instead of silent `""` (full fail-loud
conversion = backlog M14); audit stage no longer resets scored tiers; passed
drafts now beat higher-scored failed drafts.

**Knowledge Graph:** fabricated web citations deleted (LLM URLs not in search
results never become references); curator applies per-item savepoints (one bad
row no longer discards the nightly pass); ingest rollback no longer poisons the
node-id cache; blocked-domain matching host-suffix-based (was: "x.com" blocked
linux.com).

**News Pipeline/Renderers:** HTML sanitization switched from bypassable regex
blocklist to **nh3 allowlist sanitizer** (verified against `onerror=`,
`<svg onload>`, `<details ontoggle>`, `javascript:` — fixes both journal/story
and research SSR pages); JSON-LD `</script>` breakout escaped; JSONB
lost-update in tweet_verifier (web sources silently dropped); orchestrator
migration hardening (card_stats existence guard, `CREATE EXTENSION unaccent`,
date-fix sentinel only stamped after an actual run); tweet_verifier HEAD
requests SSRF-guarded.

**Lyra Services:** `expand_markers` drops non-http(s) LLM link/image URLs
(LLM05); Discord bot sends with `AllowedMentions.none()` (@everyone injection);
ILIKE escaping unified on `_escape_ilike` everywhere (4 inline copies removed
earlier in the day, 6 more sites this pass); cache falsy-JSON treated as hit.

**Core Routes:** `/clustered` cached (was 750K-row scan per request);
article-citations cache TypeError (never populated Redis); daemon
`create_task` refs stored (GC-death risk); UUID validation before casts
(radar/public_v1/library); `/news/logs` key via header + `compare_digest`;
stream refund on client disconnect (`finally`); image download hardening
(scheme/private-IP/content-type/25MB/429-retry).

**Frontend:** chat scroll-tracking dead-effect; news-feed infinite retry loop
on API failure; Globe `toggleEmpire` impure updater (StrictMode double-fire);
LLM link URL guards; dual-view deep-link protocol whitelist; credit-adjust
double-click guard; assorted timer/abort cleanups.

## MANUAL — needs operator/user decision

| # | Item | Why manual |
|---|------|-----------|
| M1 | **Rotate the Serper API key** (leaked in git history, deleted file, repo public) | Account access required — serper.dev dashboard |
| M2 | `/api/library/refresh` auth | Deploy script curls it unauthenticated from the VPS; adding auth needs a deploy-script change (e.g. secret header from `.env`) |
| M3 | OAuth state browser-binding (nonce cookie double-submit) | Login-flow change; subtle breakage risk (cross-device link opens) — needs a decided rollout |
| M4 | Monthly grant period keying: cancel+rejoin in same calendar month collides with the unique constraint → paying rejoiner gets 0 credits until next month; also role-flicker can reset `grant_anchor_date`; "remove" action ledgers full amount instead of actual delta | Payment semantics + possibly a data migration (P14 — trace all 5 lifecycle scenarios before changing) |
| M5 | `api/main.py` migration swallow (`skipped (lock contention)` for ALL errors) | Re-raising can block prod boot; needs SQLSTATE-gated rollout when someone is watching |

## Backlog (tracked, ordered by value)

1. Async hygiene, systemic: sync SQLAlchemy in `async def` handlers across
   sites/news/radar/public_v1/main (convert to `def` for threadpool);
   lyra_agent tool execution + `_get_related_news`/`_hybrid_search` off the
   loop; orphan stream tasks cancel; rate_limiter/api-cache Redis I/O.
2. LLM01 redesign: retrieved transcripts/web content out of SystemMessage
   (HumanMessage/tool_result), lyra_agent points 1351/2073/370.
3. `_hybrid_search` explicit error surfacing (P1) + `vector_search` limit clamp.
4. minimax_shared full fail-loud conversion (per-handler audit, M14 above);
   `structured_llm_call` `{}`-on-failure raise.
5. Citation completeness: uncited-claim pass for the article pipeline
   (sentence removal was never implemented — docstring now honest); curator
   `external_source_count` derivation from tier-labeled refs instead of LLM
   self-report; D2-coverage insertion should see snippets.
6. Cardgame: `lyra_duel` unique (user,tier,day) index + row lock; deck-count/
   daily-quiz TOCTOU under lock; starter INSERT..ON CONFLICT; `battle_complete`
   event never fired (3 achievements unobtainable); GET /achievements query
   storm redesign; N+1s in packs/leaderboard/duel.
7. Reservation double-release idempotency (needs a released-flag column +
   migration); stale-deferred cleanup FOR UPDATE SKIP LOCKED.
8. Perf: `/random` TABLESAMPLE rewrite; `/sites/search` limiter+cache;
   contributions stats caching; `/graph` SQL-side edge join; upload
   citation/hero matching by id (wrong-site on duplicate names);
   restore-all batch UPDATE + missing raw_data columns; snapshots retention;
   `state.debug_log` ring buffer; graph ingest batching + updated_at churn;
   graph_miner CTE scoping; OpenAlex 5th-request bug.
9. P2 consolidation: fenced-JSON parser exists 9+ times → one
   `parse_fenced_json()`; web-citation regex/renumbering duplicates in
   lyra_agent; leaderboard/collection logic duplicated between cardgame routes
   and discord_commands; `_significant_keywords`, paragraph-splitting,
   think-strip, yt_domains duplicates.
10. Frontend: P4 dual-view drift (onAskLyra + LIVE/OFFLINE status + AiNotice
    banner + headlines-only persistence differ between NewsFeedPanel and
    NewsFeedPage); console.log sweep (57 statements); feed append dedupe;
    Safari<16.4 lookbehind in chat citation regex; `useIsFounder` → useAuth.
11. Ops: lyra container healthcheck (probe design); orchestrator YouTube
    date-fix restructure (network out of migration transaction); per-step
    process isolation for pipeline steps; node_id (kind,norm) keying +
    frontier SKIP LOCKED in research_graph; thinking_log retention.
12. Theo governance: `/approve` is author-self-approval, `/unpublish` needs
    only ownership, `?override=1` available to any Researcher — product
    decision on role gates.
13. **Test infrastructure (D8, found during confirming audit): CI runs NO
    backend tests at all** — lint-backend does ruff/mypy only. That is how 5
    stale tests rotted unnoticed (test_security imports the long-removed
    `api.routes.ai`; canonical-coverage and strip-injection integration tests
    assert outdated behavior). Add a pytest job (unit-marker subset that needs
    no DB, or a services container) and repair/delete the stale tests.

## Coverage

- Deep review: 104 files fully read (10 agents; auth/payment, Theo API,
  Lyra services, cardgame, core routes, Theo pipeline, knowledge graph,
  news pipeline, image tools, frontend) + security files by coordinator.
- Mechanical scans: semgrep ruleset (now 6 rules, utcnow rule hardened),
  gitleaks (full history, 13 triaged), vulture, knip, import-linter (2
  ratchet contracts), prompt-guard check, grep batteries from the procedure.
- Confirming audit: ruff ✓, ruff format ✓, semgrep ✓, import-linter ✓,
  vulture ✓, prompt guards 61/61 ✓, mypy (0 errors in changed files) ✓,
  tsc ✓, knip ✓, production build ✓, targeted pytest suites during fixes
  (theo_citations/theo_sources 144, quota_monitor 49, worker suites 37) ✓.
- Full pytest run: **838 passed** after fixes. The remaining red is
  pre-existing, verified by re-running against commit 61eab08 (pre-audit)
  in a throwaway worktree: 40 ERRORs are local-env only (no Postgres/Redis
  running — those tests need the docker containers), and 5 FAILs are stale
  tests broken before this audit (`tests/test_security.py` imports the
  removed `api.routes.ai` module; `test_canonical_coverage::
  test_extract_subquestions_basic` and `test_strip_injection_integration::
  test_strip_metrics_count_restored_sections` assert behavior the code no
  longer has). The 8 `test_curator` failures caused by the per-item-savepoint
  fix were resolved (test double now provides `begin_nested`).

## Positive findings worth keeping

Parameterized SQL throughout (incl. all knowledge-graph writes); UUIDs
validated in Theo/Lyra tool paths; JWT fail-fast + bounded expiry; dual-layer
grant idempotency; Turnstile fails closed; XFF only behind TRUSTED_PROXY;
LLM tools SELECT-only with allowlists and caps; ReactMarkdown urlTransform
sanitization; knowledgeGraphRenderer full disposal; FK rules on unified_sites
fully compliant (9/9); PvP/PvE randomness not user-controllable.
