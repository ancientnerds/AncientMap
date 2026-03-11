# Lyra & Theo Pipeline Ops Dashboards — NERV UI

## Context

The Lyra (news discovery) and Theo (research agent) pipelines have monitoring data available via API but no dedicated ops dashboard. We'll build two separate pages (`/lyra-ops.html` and `/theo-ops.html`) using the full NERV Operations Console aesthetic — true black void, CRT scanlines, orange/green/cyan/red color coding, IBM Plex Mono typography, escalation states, and bilingual JP/EN labeling. Self-contained CSS that doesn't leak into other pages.

---

## Shared Infrastructure (Step 1)

### Files to create
- `ancient-nerds-map/src/styles/nerv-ops.css` — Full NERV design system, scoped under `.nerv-ops`
- `ancient-nerds-map/src/components/nerv/NervPanel.tsx` — Reusable panel frame (title, JP subtitle, corner brackets, status dot)
- `ancient-nerds-map/src/components/nerv/NervTickerTape.tsx` — Scrolling bottom ticker
- `ancient-nerds-map/src/components/nerv/NervBootSequence.tsx` — DOS-style boot animation on page load

### CSS tokens (scoped to `.nerv-ops`)
```css
--void: #000000; --nerv-orange: #FF9830; --data-green: #50FF50;
--wire-cyan: #20F0FF; --alert-red: #FF4840; --steel: #E0E0D8;
--font-nerv: 'IBM Plex Mono', 'JetBrains Mono', monospace;
--font-nerv-stamp: 'Bebas Neue', 'Orbitron', sans-serif;
```

### NERV CSS includes
- CRT scanlines (6% opacity), vignette overlay, phosphor flicker
- Panel frames with corner bracket decorations
- LED indicators with glow
- Escalation state classes (nominal/active/caution/alert/critical)
- Data readouts (large mono number + small label)
- Command blocks with status stamps (COMPLETED/FAILED/RUNNING)
- Horizontal bar charts (pure CSS div widths)
- Ticker tape scroll animation
- `prefers-reduced-motion` + `prefers-contrast` support
- Responsive: 3-col > 2-col > 1-col via CSS Grid + media queries

### Font loading
IBM Plex Mono (400/500/700) + Bebas Neue (400) + Noto Sans JP (400/700) loaded via Google Fonts in each ops HTML file only. Falls back to JetBrains Mono + Orbitron (already global).

### Files to modify
- `ancient-nerds-map/vite.config.ts` — Add `lyraOps` and `theoOps` entries to `rollupOptions.input`

---

## Lyra Ops Dashboard (Step 2)

### New files
| File | Purpose |
|------|---------|
| `ancient-nerds-map/lyra-ops.html` | HTML entry (follows `theo.html` pattern, adds NERV fonts, `noindex`) |
| `ancient-nerds-map/src/lyraOpsMain.tsx` | Mount point: `OfflineProvider > LyraOpsPage` |
| `ancient-nerds-map/src/pages/LyraOpsPage.tsx` | Main page component |

### Layout
```
[ESCALATION BANNER — bilingual status: NOMINAL/警戒態勢]
┌─────────────────────┬──────────────────────────────────┐
│ PIPELINE STATUS     │ VIDEO PROCESSING   QUEUE STATUS  │
│ パイプライン状態      │ (items, videos,    (active,      │
│ LED + heartbeat age │  channels, hours)   slots)       │
├─────────────────────┼──────────────────────────────────┤
│ PIPELINE STEPS      │ REJECTION ANALYSIS               │
│ パイプライン手順      │ 却下分析                          │
│ 11 steps list       │ Bar chart: rejected/low/dup      │
├─────────────────────┼──────────────────────────────────┤
│ DISCOVERY RADAR     │ KNOWLEDGE BASE                   │
│ レーダー発見          │ 知識基盤                          │
│ enriched/pending/   │ discoveries, sites,              │
│ added counts        │ name variants                    │
└─────────────────────┴──────────────────────────────────┘
[TICKER — latest item date, cycle status, scrolling]
```

### Data flow — existing endpoints, no backend changes needed
| Endpoint | Poll interval | Data |
|----------|--------------|------|
| `GET /api/news/lyra-status` | 15s | status, heartbeat, last_cycle_ok |
| `GET /api/news/stats` | 30s | items, videos, channels, hours, rejections |
| `GET /api/contributions/lyra/stats` | 30s | discoveries, sites_known, name_variants |
| `GET /api/radar/stats` | 30s | enriched, pending, added counts |
| `GET /api/lyra/queue-status` | 10s | queue_length, active, slots |

### Escalation logic (derived from lyra-status)
| State | Condition | Visual |
|-------|-----------|--------|
| NOMINAL | online, heartbeat < 90min, last_cycle_ok | Green LED, green banner |
| CAUTION | online, heartbeat 90min–2h | Orange banner |
| ALERT | error status or !last_cycle_ok | Red banner |
| CRITICAL | offline or heartbeat > 2h or no data | Red pulsing banner + flash |

### Pipeline steps panel
Static list of all 11 steps (fetch, retry, summarize, match, posts, verify, rescore, dedup, screenshots, backfill, identify) with name, description, and frequency (hourly/daily). Per-step live timings deferred to a future enhancement (requires new DB table + orchestrator changes).

---

## Theo Ops Dashboard (Step 3)

### New backend endpoint
**`GET /api/theo/ops`** — Founder-only aggregate stats.

Add to `api/routes/theo.py` using existing `require_founder` from `api/services/jwt_auth.py`.

Response:
```json
{
  "worker_status": "idle|processing",
  "queue_depth": 0,
  "active_request": { "id": "...", "question": "...", "started_at": "..." },
  "stats_24h": {
    "total_requests": 34, "completed": 29, "failed": 5,
    "avg_duration_ms": 185000, "total_tokens": 142580,
    "total_sites_found": 87, "total_tools_used": 234
  },
  "recent": [{ "id": "...", "user_id": "ab12...", "question": "...", "effort": "deep",
               "status": "completed", "sites_found": 5, "tools_used": 12,
               "duration_ms": 185000, "created_at": "..." }],
  "tool_breakdown": { "search_sites": 23, "vector_search": 14 },
  "effort_distribution": { "quick": 12, "deep": 24, "full": 6, "auto": 31 }
}
```

Also add `get_worker_status()` helper to `api/services/theo_worker.py` (exposes `_live_events` liveness).

### New frontend files
| File | Purpose |
|------|---------|
| `ancient-nerds-map/theo-ops.html` | HTML entry (NERV fonts, `noindex`) |
| `ancient-nerds-map/src/theoOpsMain.tsx` | Mount: `AuthProvider > OfflineProvider > TheoOpsPage` |
| `ancient-nerds-map/src/pages/TheoOpsPage.tsx` | Main page (auth-gated to founders) |
| `ancient-nerds-map/src/components/theo-ops/CommandLog.tsx` | Recent requests as NERV command blocks |

### Layout
```
[BOOT SEQUENCE — 3s timed DOS animation, then fade to dashboard]
[ESCALATION BANNER — SYSTEM NOMINAL / システム正常]
┌──────────────────────┬─────────────────────────────────┐
│ SYSTEM STATUS        │ QUEUE MONITOR                   │
│ システム状態           │ キュー監視                       │
│ Escalation + worker  │ Depth, active request,          │
│ status + model info  │ visual slot display             │
├──────────────────────┴─────────────────────────────────┤
│ RECENT OPERATIONS — 最近の作戦                           │
│ [COMPLETED] "What sites in Peru..."      2m14s  ✓     │
│ [FAILED]    "Ancient Egyptian harbors"   error msg    │
│ [RUNNING]   "Mesopotamian temples"       ● 45s        │
│ [QUEUED]    "Bronze age collapse"        #2 in queue  │
├──────────────────────┬─────────────────────────────────┤
│ TOKEN CONSUMPTION    │ TOOL USAGE                      │
│ トークン消費          │ ツール使用                       │
│ 24h total, avg/req   │ Bar chart of tool frequency     │
├──────────────────────┼─────────────────────────────────┤
│ SUCCESS RATE         │ EFFORT DISTRIBUTION             │
│ 成功率                │ 努力配分                         │
│ 87% (29/34)          │ quick/deep/full/auto bars       │
└──────────────────────┴─────────────────────────────────┘
```

### Data flow
| Endpoint | Poll interval | Auth |
|----------|--------------|------|
| `GET /api/theo/ops` | 5s | Founder token required |

### Escalation logic
| State | Condition |
|-------|-----------|
| NOMINAL | idle, no errors in last hour |
| ACTIVE | worker processing a request |
| CAUTION | queue_depth >= 3 |
| ALERT | failure rate > 30% (min 5 requests in last hour) |
| CRITICAL | 3+ consecutive fetch failures (worker down) |

### Auth gate
Page checks founder status on mount. Non-founders see NERV-styled "ACCESS DENIED / アクセス拒否" screen. Real protection is `require_founder` on the API endpoint (returns 403).

---

## Implementation Order

1. **Shared NERV CSS + components** — `nerv-ops.css`, NervPanel, NervTickerTape, NervBootSequence
2. **Lyra ops page** — HTML, main entry, page component (no backend changes)
3. **Theo backend** — `get_worker_status()` in theo_worker.py, `GET /theo/ops` endpoint
4. **Theo ops page** — HTML, main entry, page component with CommandLog
5. **Vite config** — Add both entry points
6. **Nav links** — Add to HamburgerNav (optional, founder-visible only)

## Key files to reference
- `ancient-nerds-map/src/pages/TheoPage.tsx` — Polling pattern, auth headers
- `ancient-nerds-map/src/styles/theo.css` — Page-scoped CSS token pattern
- `ancient-nerds-map/theo.html` — HTML entry template
- `ancient-nerds-map/src/theoMain.tsx` — Mount point template
- `ancient-nerds-map/vite.config.ts:78-93` — rollupOptions.input
- `api/routes/theo.py` — Existing Theo endpoints, add ops endpoint here
- `api/services/theo_worker.py` — Add get_worker_status() helper
- `api/services/jwt_auth.py:108` — `require_founder` dependency
- `api/routes/news.py:640-674` — lyra-status endpoint (reference)
- `pipeline/lyra/orchestrator.py:44-230` — Step definitions and cycle summary

## Verification
1. `npm run build` succeeds with new entry points
2. Dev server serves both `/lyra-ops.html` and `/theo-ops.html`
3. Lyra ops page shows live data from all 5 endpoints, escalation state updates correctly
4. Theo ops page shows ACCESS DENIED for non-founders, live data for founders
5. CRT effects render, `prefers-reduced-motion` disables animations
6. Responsive layout works at mobile/tablet/desktop widths
7. `curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/theo/ops` returns expected JSON
