# Theo Citation Integrity — Artifact Validation & Deterministic Repair

**Date:** 2026-07-28
**Status:** Implemented 2026-07-29 (commits e40ad18..4f8a821 + follow-ups; plan:
`docs/superpowers/plans/2026-07-28-theo-citation-integrity.md`). Two design points
were changed during adversarial review — this doc reflects the AS-BUILT state.
**Scope decision:** Referential integrity is guaranteed mechanically (hard gate). Semantic
support (does the source actually back the claim) stays with the existing LLM
verifier/judge as a soft gate — it is not part of this spec.

## Problem

Two graded papers (Kybalion, judge 98; DMT, judge 100) failed citation integrity in ways
the stored audit did not detect. Root causes, confirmed in code:

1. **The audit validates the registry, not the artifact.** `audit_citations()`
   (`pipeline/lyra/theo_citations.py`) compares prose `[N]` markers against the in-memory
   `registry.reference_numbers`. The rendered `## References` list — the thing readers see —
   is never itself validated. In `handlers/presentation.py` the references block is split
   off and re-appended **verbatim**, while `inject_citation_for_paragraph()` may assign new
   numbers (M+1…) and the prune helpers mutate the registry afterwards. The rendered list
   is never re-rendered, so registry and artifact drift apart. Observed result: audit
   reported `total_references = 50` while the rendered list held 45 entries; prose cited
   [46]–[50] into nothing; `orphaned_refs` came back empty. False confidence by design.

2. **Grouped markers `[9, 7, 1]` are invisible to the whole machinery.** Every regex in
   the system matches only `\[(\d+)\]`. Grouped markers are not renumbered by
   `finalize_references()` — after renumbering, the digits inside a grouped marker still
   carry the *old working numbering* and can point at the wrong sources. That is a silent
   misattribution risk, worse than an orphan.

3. **`[N1]`-class tokens fall through every net.** `strip_debug_tokens()` only knows bare
   `[N]` / `[...]` / `[…]`; the placeholder regex requires a dash (`[N - topic]`). `[N1]`
   is *detected* as a `non_numeric_marker` (audit honestly fails) but nothing repairs it —
   and the publish gate (`api/routes/theo.py`) reads the **stored** audit from the DB
   instead of recomputing, so stale audits pass defective papers.

## Design

### 1. New building blocks — all in `pipeline/lyra/theo_citations.py`, pure functions, zero LLM/quota

**`validate_paper_artifact(markdown: str) -> dict`** — the heart of the guarantee. Takes
only the final paper markdown; no registry. Checks:

- Exactly one `## References` / `### References` / `## Sources` section exists.
- Every reference line parses (legacy or rich regex via `parse_references_section`);
  unparseable non-empty lines in the refs block are a failure, not silently skipped.
- Reference numbers are contiguous `1..M` with no duplicates.
- Every numeric prose marker `[N]` has a rendered list entry.
- Every rendered reference is cited at least once in prose.
- Zero non-numeric bracketed tokens in prose: `[N1]`, `[N - topic]`, `[...]`, hex IDs,
  grouped forms `[9, 7, 1]`, anything bracketed that is not a plain `[N]`
  (markdown links `[x](y)` and footnotes `[^n]` excluded, as today).

Returns a **superset** of the existing `audit_result` dict shape (`passed`,
`total_citations`, `total_references`, `orphaned_refs`, `invalid_markers`,
`non_numeric_markers`, `issues`, plus new keys `references_sections`,
`unparseable_ref_lines`, `duplicate_ref_nums`, `non_contiguous`) so DB rows, frontend,
and judge keep working — but `total_references` now counts the **rendered list**, making
the 50-vs-45 class of bug structurally impossible. Additional as-built details: input is
CRLF-normalized at entry; an empty/unparseable References section fails; the heading
anchor is the LAST `## References`-style heading with exact-line-end matching, mirroring
the frontend's `splitBodyAndRefs` (colon-suffixed or `## Sources of Evidence`-style
lines are NOT refs headings). `uncited_paragraphs`, `placeholder_markers`,
`language_bleed` keep their current prose-based computation so the dict stays complete.

**`normalize_grouped_markers(text: str) -> tuple[str, int]`** — rewrites `[9, 7, 1]` →
`[9] [7] [1]` (any count ≥ 2, optional spaces) and expands dash ranges `[2-4]`/`[2–4]` →
`[2] [3] [4]` (bounds: start < end < 100, span ≤ 10, no leading zeros — year ranges like
`[1990-1995]` and thousands numerals like `[3,000]` are left intact and HOLD via the
validator). Runs **before** `finalize_references()` so renumbering sees each digit —
this closes the misattribution hole — and runs again inside repair for stored papers.

**`repair_artifact(markdown: str) -> tuple[str, dict]`** — deterministic only; never adds
a citation, never remaps a marker to a different source, never deletes prose:

1. Normalize CRLF; bail immediately when the text contains NUL (sentinel collision).
2. Split grouped/range markers (`normalize_grouped_markers`).
3. Strip ONLY allowlisted artifact tokens — `[N]`/`[N1]`-style, `[...]`/`[…]`,
   12-char hex source-ids containing a digit, `[N - topic]` placeholders. **All other
   bracket tokens (`[sic]`, quote interpolations, nested alt text, hex-like English
   words) are left in place** — the validator flags them and the paper HOLDs. (The
   original blanket-strip design was replaced after adversarial review proved it
   silently destroyed legitimate prose that then PASSED the gate.)
4. Bail to HOLD when the rendered list is broken (missing heading, unparseable or
   duplicate-numbered line) or when a numeric marker is glued to `(` or `]`
   (ambiguous markdown-link/nesting adjacency — renumbering it would risk
   misattribution).
5. Strip numeric prose markers with no rendered list entry (consuming one leading
   space at the strip site — no global whitespace tidy, which mangled markdown).
6. Drop rendered reference entries never cited in prose.
7. Renumber prose + list atomically to contiguous `1..M` in first-citation order
   (sentinel two-pass, same technique as `finalize_references`).

Idempotent: `repair(repair(x)) == repair(x)`. Returns the repaired markdown plus the
fresh `validate_paper_artifact` report of the result.

### 2. Pipeline integration

- `handlers/paper.py`: call `normalize_grouped_markers` as Step 7.4, immediately before
  `finalize_references` (Step 7.5).
- `handlers/presentation.py` (the last text mutator in the pipeline): after the existing
  strip/prune chain, **re-render the references list from the registry** (replace the
  stale block instead of re-appending verbatim) — this fixes the Kybalion [46]–[50]
  drift class at its source. Then run `validate → repair → validate` as the guaranteed
  final act; the result becomes `state.audit_result`. Document the invariant in code:
  **no LLM pass may touch `paper_text` after this point.**
- `_split_paper_for_presentation` heading regex is aligned with
  `_find_references_heading` (today it misses `### References` / `## Sources`).

### 3. Publish gate (`api/routes/theo.py`)

- Publish — manual endpoint **and** permanent-researcher auto-publish — recomputes
  `validate_paper_artifact` on the exact markdown it is about to publish. The stored
  audit becomes informational. Validation failure → 409 with the report in the body.
- **Audit-of-record semantics (as built):** the persisted `result.audit` always describes
  the artifact readers see — the route validates and stores the assembled
  `published_report`; `_auto_publish` runs `validate_or_repair` unconditionally on
  `report` (adopting the repaired text) and holds + Discord-pings when it cannot reach
  clean; a crash in `_auto_publish` also Discord-pings (fail-loud). The repair CLI
  persists the audit of the published view only for public rows, else of `report`.
- `?override=1` (+ `X-Theo-Override-Reason`) continues to bypass judge/quality-score, but
  **no longer bypasses referential integrity** — there is no legitimate reason to
  force-publish a paper whose defects are deterministically repairable.
- New optional `?repair=1`: applies `repair_artifact` to the assembled published view,
  persists the repaired markdown and refreshed audit, then publishes only if the
  re-validation is clean. (The private `report` field is not touched by the route.)
- PATCH `edit_research` now refuses published papers (409, "unpublish first") so edits
  can never silently invalidate the publish-time audit.

### 4. Repair CLI + backfill

`scripts/repair_theo_citations.py`:

- Scans all stored research papers, prints a per-paper validation report (`--scan`).
- `--apply [request_id ...]` repairs in place and refreshes the stored audit — same
  functions as the pipeline, no special-case code path.
- First use: fix the two pending papers (Kybalion: strip `[N#]` + `[46]–[50]`; DMT: split
  `[9, 7, 1]`, strip `[44]`, drop uncited refs [32] [33] [35], renumber) and sweep the
  rest of the DB for undetected dirty papers.
- Runs locally against the tunnel (psql 15432 / API 18000) or directly on the VPS.

### 5. Tests + failure path

- As built: a NEW file `tests/pipeline/test_theo_artifact_gate.py` (48 tests) with golden
  fixtures distilled from the real defects of both papers — each defect class caught by
  the validator, `repair_artifact` produces validator-clean output or HOLDs, idempotence,
  plus adversarially-derived cases (legit bracketed prose survives, image alt text
  survives, year ranges/thousands numerals untouched, CRLF, hex-like English words).
- If repair cannot reach clean (e.g. no parseable references section at all): the paper
  stays unpublished, `passed=false`, reason logged. No silent success, no LLM fallback.

## Non-goals

- No change to the semantic citation verifier, judge, tier ranking, or source selection.
- No LLM-based repair (rejected: quota cost + misattribution risk).
- No change to the Lyra news/article pipelines (their `[N]` handling is separate).

## Deploy notes

- Pipeline changes require the manual lyra container rebuild after deploy
  (`docker compose up -d --build lyra`); the API gate change ships with the normal
  `api` rebuild.
- CI runs lint only — run `pytest tests/pipeline/test_theo_citations.py` and
  `ruff format` locally before pushing.
