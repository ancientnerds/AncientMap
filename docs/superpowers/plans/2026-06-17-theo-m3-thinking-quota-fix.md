# Theo / MiniMax M3 — short-paper & quota repair (2026-06-17)

Autonomous session. Goal: stop Theo producing short/empty research papers.

## TL;DR root cause

Two compounding causes, both dating to MiniMax's **M3 launch + per-token billing
switch on 2026-06-01/02**:

1. **Quota exhaustion (primary).** MiniMax moved the Token Plan from per-*call* to
   per-*token* metering. M3 is a heavy reasoning model (~89% of its output tokens
   are reasoning). A Theo run makes ~230 LLM calls over huge source context →
   blows the 5h-rolling **and** weekly Token-Plan caps → `429 (2056) "Token Plan
   usage limit reached"` → calls return empty → **89-char "completed" paper.**
2. **Self-inflicted regression (commit b6a350b, deployed 2026-06-16).** It forced
   `thinking={"type":"enabled","budget_tokens":4096}` on *every* MiniMax call,
   on the (now-false) M2-era belief that "M3's default thinking is unbounded and
   eats max_tokens." **Live re-verification 2026-06-16 proves that belief wrong**
   and the fix net-harmful (see Evidence).

Plus secondary bugs: caveat `$text` drop (FIXED, commit b6a350b… see below),
silent acceptance of empty/truncated output as "completed", structured-output
retry loops on large prompts.

## Evidence — live probes against api.minimax.io/anthropic, MiniMax-M3, 2026-06-16

Plain calls:
| thinking arg | thinking block? | think tokens | note |
|---|---|---|---|
| omitted (default) | **NO** | 0 | **default = OFF** (inverts old belief) |
| `{"type":"adaptive"}` | yes | 1155 | clean "thinking on" |
| `{"type":"disabled"}` | no | 0 | **works, non-empty** (old "disabled=empty" FALSE) |
| `enabled, budget 4096` | yes | 922 | accepted (no 400) |
| `enabled, budget 128`, big task | yes | **3448** | **budget_tokens IGNORED (27× over)** |

Forced tool-call (structured output), 3 trials each:
| thinking | tool_use returned | out tokens |
|---|---|---|
| omitted | 3/3 | 138–166 |
| disabled | **3/3** | 139–174 |
| adaptive | 3/3 | 200–328 (≈2× — thinking cost) |

Conclusions:
- `budget_tokens` is **dead config** — `thinking_for_effort`'s 256/1024/4096/8192
  ladder maps to nothing; `enabled`≈`adaptive` (unbounded). Root of the
  `max_tokens=16384 → output 5720 chars` truncation.
- M3 default (omit) = OFF; `disabled` = OFF and non-empty; `adaptive` = ON.
- `disabled` does **not** break the forced tool trick → mechanical structured
  calls can run thinking-off (≈½ the tokens).
- Quality A/B (2026-06-03, still valid): adaptive/full thinking gives best
  synthesis source-grounding (100% vs 75% bounded). So reasoning-heavy stages
  must stay `adaptive`; only mechanical stages go `disabled`.

## Fix plan

### A. Thinking strategy (config.py + minimax_shared.py) — the core fix
- Rewrite `thinking_for_effort()` to emit the **current** M3 contract:
  - `instant`, `low` → `{"type":"disabled"}`  (mechanical: extract/score/query-gen)
  - `medium`, `high` → `{"type":"adaptive"}`   (reasoning: synthesis/narrative/debate)
  - thinking disabled in settings → omit (None)
  - drop the `budget_tokens` ladder entirely.
- **Revert b6a350b's force-on-None** in `_call_anthropic_api` and
  `minimax_chat_anthropic`: do NOT inject thinking when the caller passed none.
  Default (omit) = OFF is correct and lean for M3.
- Remove `_MINIMAX_THINKING_OUTPUT_HEADROOM` "budget+headroom" math (keyed off the
  ignored budget). Replace with absolute `max_tokens` floors:
  - structured w/ adaptive: ≥ 8192; narrative w/ adaptive: 16k–32k.

### B. Fail loud, never publish empty (CLAUDE.md: no silent-empty)
- When the finalized `paper_text` is empty / below a sane floor (e.g. < 2000
  chars), mark the request **failed** with a clear reason (quota/truncation),
  do NOT save it as `completed` with a quality score.

### C. Token economy (reduce quota burn so we stop hitting 429)
- Disabling thinking on mechanical calls (A) is the biggest lever (~½ tokens on
  many calls).
- Verify prompt caching actually fires (cache_control on system block already
  set; confirm cache-read tokens appear in usage — MiniMax may strip it for
  `minimax-*` model names).
- Keep source context < 512K (avoid 2× long-context tier).

### D. Account-level (needs the user) — flagged in handoff
- Attach a **PAYG key + buy Credits** so 2056 auto-covers instead of returning
  empty (documented MiniMax overflow). And/or upgrade Plus→Max.

## Status log (final, 2026-06-17 autonomous session)

Commits on local `main` (NOT pushed — see Deploy):
- `b6a350b` *(pushed/deployed earlier today)* — forced thinking budget. **This is
  the regression**; superseded by 03cc26b below but still LIVE in prod.
- `682ebd6` then `7dacb32` — Bug D ($text recovery) **added then REVERTED.**
  Reversal reason: the news summarizer already handles this exact M3 bug
  (`test_summarizer_facts.py`, 2026-06-09) by **drop+retry** to protect prod
  content integrity. Recovering mangled output diverged from that reviewed
  pattern, changed prod Lyra behavior as a side effect, and risked storing
  unverified content (against "integrity > availability"). Aligned on drop.
- `03cc26b` — **A: thinking strategy rewrite** (the core fix). Adaptive/disabled
  per the verified contract; revert force-on-every-call; max_tokens floor.
  24 unit tests green.
- `<this commit>` — **B: empty-paper fail-loud guard** + unit tests.

Verification (cheap, no heavy runs):
- [x] Live M3 probes (thinking contract, budget ignored, disabled-works, forced
  tool 3/3 across modes).
- [x] **C: prompt caching VERIFIED WORKING** — 2nd identical call read 2950 cached
  tokens (`cache_read=2950`, `input=14`). System-block `cache_control` fires; no
  fix needed. (Source-content caching is an unimplemented follow-up.)
- [x] Unit tests: 531 pass. The 7 failures are ALL pre-existing (verified at
  baseline b08749e): canonical_coverage, strip_injection, theo_citations,
  journal_assessor, + 4 `lyra_agent.py:1573 "expected 8, got 7"` (a separate
  pre-existing prod bug worth its own fix).
- [ ] Full Theo run — NOT done (needs quota + ~30min; would re-risk the limit).

## Deploy — HELD for user (AFK, prod-Lyra risk, push rule)
Prod is still running the regression `b6a350b` (forces thinking ON every call).
Lyra is idle (0 new videos) and the Theo queue is empty, so live harm is low.
To ship the fix when you're back:
1. `git push origin main` (ships 03cc26b + the fail-loud guard + revert).
2. CI rebuilds the API container.
3. Kick a `THEO_FAST` smoke run (`docker exec -e THEO_FAST=1 ancient_nerds_api
   python scripts/theo_test_run.py "..."`) and confirm: 0 MiniMax-429, a real
   multi-thousand-char paper, far fewer total tokens than the 850k/231-call run.
   Watch `cache_read` and that mechanical calls show no `thinking` block.

## D. Account-level (your call, biggest single lever for "never empty again")
MiniMax switched to per-TOKEN metering (2026-06-02) with a 5h-rolling **and**
weekly cap; M3 thinking ≈ 89% of output tokens. Even with the code fix, a big run
can hit the cap. Documented mitigations:
- **Attach a PAYG key + buy Credits** → 2056 overflow is auto-covered instead of
  returning empty (the documented fix for exactly our empty-paper failure).
- Or **upgrade Plus→Max** (more 5h/weekly quota + concurrency).
- Check real remaining quota: `GET /v1/token_plan/remains` (needs the secret key).

## Follow-ups (not done; flagged)
- Cache the large **source-content** blocks (not just system) for in-run reuse —
  potentially big quota win; needs careful message-assembly restructuring + test.
- Per-stage thinking tuning: confirm decomposition/specialist quality with
  thinking OFF; bump specific reasoning-heavy structured stages to `medium` if an
  A/B shows quality loss.
- Fix the pre-existing `lyra_agent.py:1573` unpack bug (run_agent_stream).
