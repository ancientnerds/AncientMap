# Radar Promotion Upgrade — Design

**Date:** 2026-07-19
**Status:** Approved (user pre-approved autonomous implementation)

## Problem

Radar's purpose is extracting legit archaeological sites from news coverage and getting them onto the globe. Extraction and enrichment work well (738 candidates processed on prod), but the promotion gate requires a 100% completeness score — all 8 fields including Wikipedia URL, thumbnail, and Wikidata QID. Measured on prod (2026-07-19): of 314 `enriched` candidates, 307 lack a Wikipedia URL, 280 lack a thumbnail, 109 lack a QID. Only 4 are promotable. Newly discovered sites — Radar's entire point — usually have no Wikipedia article yet, so the gate structurally contradicts the feature's goal. Only 25 sites have ever been promoted.

Additional gaps: no reject/dismiss action, no way to merge a candidate into an existing site (the "Near AN site" warning is display-only), AI confidence is never checked at promotion time, and a candidate with one wrong field can only be rejected or promoted wrong.

## Decisions (user-confirmed)

1. **Hybrid review model**: auto-promote stays for a high bar; everything else goes through a founder review workflow.
2. **Review actions**: Approve, Reject, Merge into existing site, Edit-before-approve. No re-run-enrichment button.
3. **Visibility**: promoted sites keep `source_id='lyra'`, opt-in via Filter panel (status quo). No `enabled_by_default` change.
4. **Review UX**: action buttons on the existing Radar cards. No dedicated review mode, no bulk actions.

## Design

### 1. Status model & gates

`enrichment_status` on `user_contributions` stays the single source of truth. One new value, no schema change (String column):

```
enriched --approve--> promoted
enriched --reject---> dismissed   (NEW value)
enriched --merge----> matched
```

- **Manual gate (approve)**: core fields must be present *after* overrides are applied — `lat`, `lon`, `country`, `site_type`, `description` >= 50 chars. Wikipedia URL, thumbnail, QID, and period remain score bonuses, not blockers.
- **Auto-promote gate**: CORRECTION vs. the brainstorm discussion — the existing pipeline gate is `score >= min_score_for_promotion` with a default of **55** (`pipeline/lyra/config.py:175`), not 100. The 314 enriched rows only escaped auto-promotion because the facts-hash skip never re-evaluates them (prod check 2026-07-19: 250 of them pass every `_maybe_promote` guard and would promote on their next re-mention). To implement the approved "high bar" hybrid: raise the `min_score_for_promotion` default to **100** and additionally require `enrichment_data['identification']['confidence'] == 'high'` in `_maybe_promote()`. Existing guards (date cutoff, AN spatial dedup) stay.
- `dismissed` must NOT reuse the existing `rejected` value: `site_identifier.py`'s work query re-enriches `rejected` rows each cycle, so a founder-rejected card would resurrect. `dismissed` is simply not in that query's status set — no pipeline change needed for exclusion.
- `site_matcher._upsert_lyra_suggestion()` only increments `mention_count`/backfills metadata on existing rows and never touches `enrichment_status`, so dismissed cards stay dismissed when re-mentioned.

### 2. API changes (`api/routes/radar.py`, all `require_founder`)

**`POST /radar/{contribution_id}/promote` (extended)**
- Accepts an optional JSON body of field overrides: `name`, `lat`, `lon`, `country`, `site_type`, `period_name`, `period_start`, `period_end`, `description`.
- Replaces the `score == 100` guard with the core-fields check evaluated after overrides.
- Overrides are applied at promotion time only — never written to the un-promoted contribution. This prevents a later enrichment pass (facts-hash change) from clobbering founder edits, and means a candidate missing a core field can be approved by filling it in.
- Keeps existing guards: `enrichment_status == 'enriched'`, `promoted_site_id IS NULL`. Keeps cache busting (`radar:*`, `sites:*`) and the `unified_site_names` insert.
- Records `{action: 'promote', user, at, overrides}` in `enrichment_data['review']`.

**`POST /radar/{contribution_id}/dismiss` (new)**
- Sets `enrichment_status='dismissed'`, records `{action: 'dismiss', user, at}` in `enrichment_data['review']`, busts `radar:*`.
- Guard: current status must be `enriched`.

**`POST /radar/{contribution_id}/merge` (new)**
- Body: `{site_id}` (UUID of a `unified_sites` row).
- Verifies the target site exists; inserts the candidate's `name` (and `corrected_name` if different) into `unified_site_names` as aliases using the existing name-normalization util — so future news mentions match the real site and this card never regenerates.
- Sets `enrichment_status='matched'`, records `{action: 'merge', user, at, site_id}` in `enrichment_data['review']`, busts `radar:*`.
- Guard: current status must be `enriched`. Skips alias insert (idempotently) if the normalized name already exists for that site.

**`GET /radar/list`**
- The `rejected` status filter now returns both `rejected` and `dismissed` rows.

### 3. Pipeline changes

- `pipeline/lyra/config.py`: `min_score_for_promotion` default raised 55 → 100.
- `pipeline/lyra/site_identifier.py` `_maybe_promote()`: additionally requires identification confidence `'high'` (read from `enrichment_data['identification']['confidence']`). Everything else untouched.

Consistency rule for the new status: everywhere the API treats `rejected`, it also treats `dismissed` (list filter, map exclusions, stats) — dismissed behaves exactly like rejected except the pipeline never re-enriches it.

### 4. Frontend (`ancient-nerds-map/src/pages/LyraRadarPage.tsx`, founders only)

On each `enriched` card, replace the current score-100-only "Add to DB" button with three actions:

- **Approve** → compact modal: all promotable fields pre-filled and editable, missing core fields highlighted, numeric lat/lon inputs. Submit = `POST promote` with overrides (only changed/filled fields sent). Complete candidates are confirm-and-submit; incomplete ones require filling highlighted fields first. A 422 response names the missing fields; the modal highlights them.
- **Reject** → inline confirm (two-step button, no modal) → `POST dismiss`.
- **Merge** → shown when `nearby_an_site` data exists; small picker pre-filled with the nearby suggestion(s) plus a name-search input against existing sites (reuses the existing `GET /api/sites/search?q=` endpoint, `api/routes/sites.py:715`). Selecting a site calls `POST merge`.

After any action: refetch list + stats (server busts caches). No new pages.

### 5. Error handling

Consistent with the existing promote endpoint, no silent fallbacks:
- 404 — unknown contribution id; merge target site not found.
- 409 — wrong status (not `enriched`) or already promoted.
- 422 — core fields still missing after overrides; response body lists the missing field names.

### 6. Testing

API tests alongside the existing suite:
- Manual gate: core-fields pass/fail; overrides filling gaps; 422 lists missing fields.
- Status transitions: approve → `promoted`; dismiss → `dismissed`; merge → `matched`; each rejects wrong starting status with 409.
- `dismissed` rows excluded from the identifier work query.
- Merge inserts aliases; matcher would match the alias (no card regeneration).
- Auto-promote requires high confidence (100-score + medium confidence does NOT auto-promote).

### 7. Out of scope

Bulk review, re-run-enrichment button, `enabled_by_default` visibility change, map dot clustering, score formula changes, dedicated audit table, review-mode UI.

## Operational notes

- No DB migration (new status value is just a new string in an existing column).
- No deploy-flow changes. Standard deploy: push to main → CI → VPS (only when the user explicitly asks to push).
- Backlog effect: unlocks ~270 of 314 enriched candidates for one-click review; the rest become approvable via edit-in-modal.
