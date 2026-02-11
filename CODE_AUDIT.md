# Code Audit Framework

A playbook for AI-assisted code audits of the AncientMap project. This document defines what to check, how to classify findings, and how to report results.

## How to Use

Tell Claude Code to audit by hinting at this file and specifying a scope:

- `audit full` — periodic health check of the entire codebase
- `audit backend` — after backend changes (`api/` + `pipeline/`)
- `audit frontend` — after frontend changes (`ancient-nerds-map/src/`)
- `audit security` — security-focused review of all code
- `audit file <path>` — deep-dive on a single file

Claude will read this framework, scan the relevant code, and produce a structured report.

---

## Audit Modes

| Mode | Scope | When to Use |
|------|-------|-------------|
| `full` | Entire codebase | Periodic health check |
| `backend` | `api/`, `pipeline/` | After backend changes |
| `frontend` | `ancient-nerds-map/src/` | After frontend changes |
| `security` | All code, security lens only | Pre-release, after incidents |
| `file <path>` | Single file deep-dive | Targeted review |

---

## Severity Classification

| Level | Meaning | Action |
|-------|---------|--------|
| **Critical** | Will cause bugs, security vulnerabilities, data loss, or crashes | Must fix before merge/deploy |
| **Major** | Significant quality or maintainability problem | Should fix in current cycle |
| **Minor** | Style, convention, small improvement | Fix when convenient |
| **Info** | Observations, suggestions, future considerations | Optional |

---

## Audit Dimensions

### D1: Correctness & Reliability

Check for logic errors, off-by-one mistakes, race conditions, and null/undefined handling.

**Python**
- Unhandled exceptions in request handlers
- Wrong return types (e.g. returning `None` where a model is expected)
- `async`/`await` misuse (blocking calls in async functions, missing `await`)
- Mutable default arguments

**TypeScript**
- Unchecked nulls (accessing `.property` on potentially null values)
- Incorrect type assertions (`as` casts hiding real type mismatches)
- Stale closures in React hooks (missing dependencies in `useEffect`/`useCallback`)
- Promises not awaited or error-handled

**Project rule**: Code must work or be marked `available = False` with a reason. No fallback chains. No silent empty returns. (CLAUDE.md P1)

---

### D2: Security

Aligned with OWASP Top 10 2025 + LLM-specific risks.

| OWASP | What to Check |
|-------|---------------|
| A01 Broken Access Control | Admin PIN checks use timing-safe comparison; route protection on all admin endpoints |
| A03 Supply Chain | Dependency versions pinned; `pip-audit` / `npm audit` clean |
| A04 Cryptographic Failures | Secrets loaded from env vars, not hardcoded; timing-safe comparisons for auth |
| A05 Injection | SQLAlchemy queries use `:param` binding (not f-strings in WHERE); HTML output escaped; XSS in React (`dangerouslySetInnerHTML` audited) |
| A07 Auth | Turnstile verification on public submission endpoints; rate limiting on API routes |
| A09 Logging | No secrets/tokens/passwords in log output; error messages don't leak stack traces to clients |
| A10 Error Handling | Fail-closed (deny on error), not fail-open; tool errors sanitized before returning to user |

**LLM-specific**
- All 11 prompt files in `pipeline/lyra/prompts/` must constrain output format and reject off-topic injection attempts
- Tool error messages returned to the LLM must not contain raw SQL, stack traces, or secrets
- User input passed to LLM system prompts must be in the `HumanMessage`, never interpolated into `SystemMessage` content

---

### D3: Maintainability & Complexity

| Metric | Threshold |
|--------|-----------|
| Cognitive complexity per function | Flag > 15 |
| File length | Flag > 400 lines |
| Function length | Flag > 50 lines |
| Parameter count | Flag > 5 |
| Nesting depth | Flag > 4 levels |

**Project rules**:
- No duplicate utility functions — always check if it already exists and import it (MEMORY.md rule)
- Color helpers live in `src/constants/colors.ts`, re-exported from `src/data/sites.ts`
- Country flags live in `src/utils/countryFlags.ts`

---

### D4: Performance

**Database**
- N+1 query patterns (loop issuing individual queries instead of batch/join)
- Missing indexes on columns used in WHERE/JOIN
- Unbounded queries (missing `LIMIT`)

**Frontend**
- Unnecessary re-renders (missing `React.memo`, `useMemo`, `useCallback` on expensive ops)
- Large bundle imports (importing entire libraries when a subset suffices)
- Three.js: geometry/texture disposal in cleanup; avoiding per-frame allocations

**API**
- Missing cache usage on hot endpoints
- Response payloads larger than needed (sending full descriptions when summaries suffice)
- Missing compression headers

**Pipeline**
- Unbounded loops without batch limits
- Missing deduplication bounds (the 500-item dedup pattern is the baseline)

---

### D5: Architecture & Patterns

**Layer violations**
- Route handlers should not contain raw SQL — use service functions
- `api/` must not import from `pipeline/` internals (except `pipeline/database.py` for shared DB access)
- Components should not call API endpoints directly — use data hooks/services

**React patterns**
- Hooks called conditionally or inside loops
- Missing cleanup in `useEffect` (event listeners, timers, subscriptions)
- State updates after unmount

**Dual view sync**: Changes to `NewsFeedPanel.tsx` (`src/components/`) likely need mirroring in `NewsFeedPage.tsx` (`src/pages/`) and vice versa

---

### D6: Dead Code & Unused Dependencies

- Unreachable code paths (after unconditional return/throw)
- Unused imports, variables, and functions
- Orphaned files not imported or referenced anywhere
- Unused npm/pip packages in `package.json`/`requirements.txt`
- Commented-out code blocks (> 3 lines)

---

### D7: Documentation Accuracy

- Doc claims vs actual code behavior (function signatures, parameter names, return types)
- Stale comments referencing deleted or renamed code
- Missing or misleading docstrings on public API endpoints
- `README.md` / `ARCHITECTURE.md` / `CLAUDE.md` drift from actual project state

---

### D8: Configuration & Infrastructure

**Docker**
- Image versions pinned (not `latest`)
- Containers run as non-root user
- Health checks defined

**Environment**
- Secrets not hardcoded in source
- `.env` files in `.gitignore`
- No credentials in Docker build args

**CI** (`.github/workflows/ci.yml`)
- All jobs are blocking (no `|| true` on security scans)
- Build failures properly detected (not masked by `set -e` pitfalls)

**Dependencies**
- Known vulnerabilities in audit output
- License compliance for production dependencies

---

## Project-Specific Rules

These rules are derived from `CLAUDE.md`, `MEMORY.md`, and observed project patterns.

| ID | Rule | Rationale |
|----|------|-----------|
| P1 | No fallback/defensive code — fix root cause or mark `available = False` | CLAUDE.md core rule |
| P2 | No duplicate utility functions — check if it exists, import it | Prevents logic drift between copies |
| P3 | Diagnose before changing — read the code, explain why it fails, then fix | Avoids rewriting working code |
| P4 | Dual view sync — `NewsFeedPanel.tsx` ↔ `NewsFeedPage.tsx` | Two views render the same data |
| P5 | LLM prompt files must constrain output and reject injection | 11 files in `pipeline/lyra/prompts/` |
| P6 | Use `datetime.now(UTC)` not `datetime.utcnow()` | `utcnow()` is deprecated in Python 3.12+ |
| P7 | New DB columns need ALTER TABLE migrations in orchestrator | `create_all_tables()` won't add columns to existing tables |
| P8 | Never push to main without explicit user permission | Deployment safety |

---

## Output Format

Audit results follow this template:

```markdown
# Audit Report — [mode] — [YYYY-MM-DD]

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| Major | 0 |
| Minor | 0 |
| Info | 0 |

## Quality Gate: PASS / FAIL

Checked:
- [ ] Zero critical findings
- [ ] Zero major security findings
- [ ] No hardcoded secrets
- [ ] Docker images pinned
- [ ] LLM prompts have injection guards
- [ ] No new anti-patterns introduced

## Findings

### [CRITICAL] D2-SEC: SQL injection via f-string interpolation
**File:** `api/routes/sites.py:42`
**Rule:** A05 Injection
**What:** User-supplied `sort_by` parameter is interpolated directly into SQL ORDER BY clause.
**Why:** Allows attackers to inject arbitrary SQL via the sort parameter.
**Fix:** Use a whitelist of allowed column names and validate before interpolation.

### [MAJOR] D3-MAINT: Function exceeds complexity threshold
**File:** `pipeline/lyra/orchestrator.py:150`
**Rule:** Cognitive complexity > 15
**What:** `process_video()` has cognitive complexity of 23 with 6 levels of nesting.
**Why:** Hard to understand, test, and modify without introducing bugs.
**Fix:** Extract the inner retry logic and error handling into separate functions.

### [MINOR] D6-DEAD: Unused import
**File:** `api/services/lyra_agent.py:14`
**Rule:** Unused import
**What:** `from pathlib import Path` imported but only used in one conditional branch.
**Fix:** Move the import inside `_load_seshat_data()` where it's used.

### [INFO] D4-PERF: Consider caching Seshat data load
**File:** `api/services/lyra_agent.py:41`
**What:** `_load_seshat_data()` reads from disk on first call. Already cached via global, but could use `functools.lru_cache` for clarity.
```

---

## Quality Gate

The audit passes only if ALL conditions are met:

| Condition | Threshold |
|-----------|-----------|
| Critical findings | 0 |
| Major security findings (D2) | 0 |
| Hardcoded secrets | 0 |
| New anti-patterns (P1–P8 violations) | 0 |
| Docker images pinned | All |
| LLM prompts have injection guards | All 11 |

A failing quality gate means the code should not be deployed until findings are resolved.

---

## Quick-Reference Checklist

Use this for fast scanning. Each item maps to a dimension above.

### Correctness (D1)
- [ ] No unhandled exceptions in request handlers
- [ ] All async functions properly awaited
- [ ] No mutable default arguments
- [ ] React hook dependencies complete
- [ ] Type assertions match actual runtime types

### Security (D2)
- [ ] SQL queries use parameterized binding (`:param`, not f-strings)
- [ ] No secrets in source code or logs
- [ ] Admin endpoints protected with auth checks
- [ ] User input never interpolated into system prompts
- [ ] Tool errors sanitized before LLM sees them
- [ ] Turnstile on public submission endpoints
- [ ] Dependencies pass `pip-audit` / `npm audit`

### Maintainability (D3)
- [ ] No function exceeds 50 lines or complexity 15
- [ ] No file exceeds 400 lines
- [ ] No duplicate utility functions
- [ ] Parameter counts ≤ 5

### Performance (D4)
- [ ] No N+1 queries
- [ ] All DB queries have LIMIT
- [ ] Three.js geometries/textures disposed in cleanup
- [ ] No unbounded loops in pipeline

### Architecture (D5)
- [ ] Routes use service layer (no raw SQL in route handlers)
- [ ] `api/` does not import `pipeline/` internals (except `database.py`)
- [ ] `NewsFeedPanel.tsx` and `NewsFeedPage.tsx` are in sync
- [ ] React hooks follow rules of hooks

### Dead Code (D6)
- [ ] No unused imports or variables
- [ ] No commented-out code blocks > 3 lines
- [ ] No orphaned files

### Documentation (D7)
- [ ] Docstrings match actual function signatures
- [ ] No stale comments referencing deleted code
- [ ] README/CLAUDE.md reflects current architecture

### Infrastructure (D8)
- [ ] Docker images version-pinned
- [ ] `.env` in `.gitignore`
- [ ] CI jobs are blocking (no `|| true`)
- [ ] No credentials in Docker build args
