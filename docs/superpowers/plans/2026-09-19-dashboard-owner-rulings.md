# Rulings and live findings that override both design contracts

Measured by the orchestrator against production on 2026-09-19, after the wave-one
contract was written. Where this file contradicts a contract, **this file wins**.

## R1 — The Discord funnel's truth is the server log, not the `discord_click` event

`discord_click` has **never fired**: zero rows in `website_event`, ever.
The server-side funnel redirect has **29 clicks, 23 of them human**:

| src | human | bot |
|---|---|---|
| landing | 10 | 3 |
| unknown | 6 | 1 |
| seo | 6 | 2 |
| app | 1 | 0 |

Root cause of the zero: `ancient-nerds-map/index.html` is static HTML with **no React
entry**, so `src/analytics/boot.ts` — which installs the click delegation — never runs
there. The landing page holds the most-clicked CTA (10 of 23) and structurally cannot
produce the event. The `seo`/`app` clicks predate the tracker (live since 2026-09-17),
which is why they are missing too.

**Ruling:** the Exits panel reads the **funnel log** for Discord
(`/var/www/ancientnerds/logs/ancient_nerds_api.log`, lines `goto_discord src=%s bot=%d`,
written by `api/routes/goto.py`; the directory is mounted into the api container at
`/app/logs`, verified). `outbound_click` stays on Umami. Do **not** ship a Discord list
fed by an event that cannot fire. `scripts/funnel_report.py` already parses these lines —
reuse its parser, do not write a second one.

**Checked and dismissed:** the six `src=unknown` clicks are *not* a bug in our markup.
Every rendered page carries a valid source (verified live: `/sites/...` → `src=seo`,
`/` → `src=landing`; `globe.html` and `theo.html` render no Discord link at all), and every
caller of `discordCtaUrl()` passes a value from the typed `DiscordCtaSource` union. The
`unknown` bucket is the route's designed fallback for a bare or hand-typed
`/goto/discord`. Do not spend an agent on it. Do surface the bucket in the panel so a real
regression would become visible.

## R2 — The globe's abandonment rate is the headline number

7 days: **33 pageviews of `/globe.html`, 8 `globe_ready` events** → about **76 % of globe
loads never reach an interactive globe**. Of the 8 that made it, 2 fired `globe_idle`
(ready, then untouched for 30 s). Time to ready ranged 9 450 – 80 383 ms.

**Ruling:** this must be visible, and it outranks the p75 as the headline. Denominator is
page loads of `/globe.html`, not sessions — state that in the UI. Beware the sample size:
8 successes is thin, so the UI says the counts, not only a percentage.

## R3 — Never call the third visitor class "Bot"

Cookieless data cannot separate a scraper from a person who read the headline and left.
The stacked hour strip's segments are **From AI · Human · Unconfirmed**, disjoint, in that
precedence. A "likely scraper" split may only appear once the fingerprint clustering
exists, and it must be worded as a suspicion.

## R4 — MiniMax PAYG does not exist and never will

Not a pending decision. Nothing in this work may depend on buying credits. Nothing in this
work calls an LLM at all; if a future step would, it plans inside the existing quota
(~9.7M tokens / 5 h rolling plus a weekly budget resetting Monday 00:00 UTC, shared with
Lyra and Theo) or uses the Anthropic path.

## R5 — No tracking cookie

Decided 2026-09-19. Retention is measured two ways only: Umami's session id **within one
calendar month**, and the **Discord login** (durable and consented — `an_auth_token` is
functionally necessary and needs no banner). `privacy.html` states we set no cookies and do
no fingerprinting; nothing here may contradict that published text.

## R6 — Events that have never fired

Zero rows, ever: `discord_click`, `not_found`, `search_empty`. Low volume: `globe_ready` 8,
`outbound_click` 6, `feedback` 2, `globe_idle` 2, `scroll_depth` 55.
A panel whose only input is one of the never-fired events must not ship as an empty box —
either it reads a source that has data (see R1) or it is deferred with a named trigger.

## R7 — Components are untestable today

`ancient-nerds-map/package.json` has vitest but **no jsdom and no @testing-library/react**,
so no existing test renders a component. The screenshot gate
(`scripts/dashboard_screenshots.py`) is the only visual check, and it only covers states
present in `FIXTURES`. Either add the render tooling as part of this work, or make the
fixtures cover every production state including the empty ones — and say which was chosen.

## R8 — Operational note, not part of this work

`/var/www/ancientnerds/logs` is **7.1 GB** (`ancient_nerds_db.log` alone 2.5 GB,
`ancient_nerds_api.log` 183 MB and growing). Disk is at 53 % of 193 GB, so this is not
urgent, but growth is unbounded and the funnel panel will read that api log. Report it;
changing log rotation is deploy configuration and needs the owner's approval.
