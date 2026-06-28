# MEE6 Monetize Integration — Design Spec

**Date:** 2026-04-07

## Summary

Replace Patreon as the subscription platform with MEE6 Monetize. Users subscribe through MEE6's payment page, MEE6 assigns Discord roles, and the existing role-based credit grant system handles the rest. Rename "Archaeologist" tier to "Pathfinder" across the codebase.

## Subscription Tiers

| Tier | MEE6 Price | Credits/Month | Cap Multiplier |
|------|-----------|---------------|----------------|
| Explorer | $5/mo | 5,000 | 1x |
| Pathfinder | $10/mo | 15,000 | 2x |
| Scholar | $25/mo | 50,000 | 3x |

## How It Works

1. User subscribes via MEE6 Monetize page → MEE6 assigns a Discord role
2. User logs into website → OAuth flow fetches Discord roles → existing `CREDIT_ROLES` config matches MEE6 role → monthly credits granted
3. User uses `/credits` in Discord → same role check → same grant logic
4. If subscription lapses → MEE6 removes the role → next login sees no tier role → no new credits granted, existing balance untouched

No new bot code, no webhooks, no periodic scans. The existing login + role-check flow handles everything.

## Code Changes

### 1. `api/routes/auth.py` — Replace Patreon role IDs with MEE6 role IDs

Replace the three `PATRON_*_ROLE_ID` constants with new MEE6 Monetize role IDs (to be created in Discord by the user and configured in MEE6 dashboard).

Rename all `archaeologist` references to `pathfinder`:
- `PATRON_ARCHAEOLOGIST_ROLE_ID` → `MEE6_PATHFINDER_ROLE_ID`
- `PATRON_EXPLORER_ROLE_ID` → `MEE6_EXPLORER_ROLE_ID`
- `PATRON_SCHOLAR_ROLE_ID` → `MEE6_SCHOLAR_ROLE_ID`
- `"monthly_patron_archaeologist"` reason → `"monthly_mee6_pathfinder"`
- `"monthly_patron_explorer"` reason → `"monthly_mee6_explorer"`
- `"monthly_patron_scholar"` reason → `"monthly_mee6_scholar"`
- `CREDIT_ROLES` entries: update names from `"Patron Explorer"` → `"Explorer"`, etc.
- `get_user_tier()`: rename `"archaeologist"` → `"pathfinder"`
- `/auth/me` tier check: `"archaeologist"` → `"pathfinder"` in the monthly-tier list

### 2. `api/services/discord_bot.py` — Update `/credits` embed

- Tier display names: `"Archaeologist (Patron)"` → `"Pathfinder"`, `"Explorer (Patron)"` → `"Explorer"`, `"Scholar (Patron)"` → `"Scholar"`
- Replace Patreon upgrade link with MEE6 Monetize page URL

### 3. `api/routes/patreon.py` — Remove

Delete the Patreon webhook handler entirely. Remove the router registration from `api/main.py`.

### 4. `api/main.py` — Remove Patreon router

Remove the `patreon` import and `app.include_router(patreon.router, ...)` line.

### 5. `pipeline/database.py` — PatreonEvent table

Leave the `PatreonEvent` model in place (table has historical data). Do not drop the table. Just stop using it.

## What the User Does (MEE6 Dashboard + Discord)

1. Create 3 Discord roles: `Explorer`, `Pathfinder`, `Scholar`
2. Note the role IDs
3. Set up MEE6 Monetize with 3 plans at $5/$10/$25, each assigning the corresponding role
4. Provide the role IDs so we can update the code
5. Rename existing Patreon "Archaeologist" role to "Pathfinder" in Discord (or create new)

## Cancellation Behavior

- MEE6 removes the role when subscription lapses
- Next login: bot sees no tier role → no new monthly grant
- Existing credit balance is untouched (no clawback)

## Stacking

Not applicable — Patreon is being removed. Only MEE6 Monetize roles will grant monthly credits. One-time Discord role grants (OG Nerd, Team, etc.) remain unchanged and independent.

## Migration

- Existing Patreon subscribers keep their already-granted credits
- The `CreditGrant` table retains historical Patreon grants (reason `monthly_patron_*`)
- New MEE6 grants use new reason keys (`monthly_mee6_*`), so there's no conflict with historical data
- No database migration needed — all changes are in application code
