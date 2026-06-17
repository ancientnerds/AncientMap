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

## Status log
- [x] Bug D (caveat `$text` recovery) — committed b6a350b… (schema-coerce), tests green.
- [ ] A — thinking strategy rewrite.
- [ ] B — fail-loud.
- [ ] C — caching verification.
- Deploy: HOLD for user (prod Lyra shares this path; user AFK). Revert-of-harm is
  safe to deploy; new behavior wants a verification run when quota is free.
