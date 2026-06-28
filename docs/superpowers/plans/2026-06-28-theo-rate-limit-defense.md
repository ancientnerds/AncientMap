# Theo / MiniMax — durable rate-limit defense (2026-06-28)

Goal: Theo soll dauerhaft laufen können, ohne sich selber auszuknocken oder
in 429-Spiralen zu landen. Konkret: ein 50-Prompt-Batch muss durchlaufen,
auch wenn Lyra parallel News pipelinet.

## Root cause (bestätigt, 2026-06-28 live)

MiniMax Token Plan Plus hat zwei Caps die gleichzeitig greifen:
- **5h-rolling ~9.7M tokens** (Token Plan Plus)
- **Weekly cap** (M3 mit adaptive thinking verbrennt ~89% der Output-Tokens
  als Reasoning-Tokens, also explodiert der Verbrauch)

Bei der gestrigen 52-Prompt-Batch hat der Limiter `82% Rate-Limited` gemeldet
(730/890 calls 429 mit Fehler 2056 "Token Plan usage limit reached"). Davon:

1. **Limiter ist auf RPS-Cap gebaut, regelt aber Token-Cap.** Adaptive
   Concurrency wächst bei Erfolg (`+5 nach 10 successes`, 3→8→13→18),
   was eine Token-Quota nur SCHNELLER leerbrennt.
2. **`global_limiter.reset()` in `convergence_orchestrator.py:117`** ruft
   `self._current_concurrency = self._max_concurrency` (= 100) bei JEDEM
   neuen Theo-Run auf. Limiter "vergisst" das globale Quota-Burn-Level und
   knallt mit Vollgas in eine eventuell schon leere Quota.
3. **Fehler werden nicht unterschieden.** `minimax_shared.py:231` und
   `config.py:567` checken beide nur `"429" in error_str`. Ein 429 von
   "rate limit" (RPS) und ein 429 von "Token Plan usage limit reached"
   (Quota) werden identisch behandelt. Bei Quota-Sperre hilft Backoff
   nicht — der 5h-Window muss ablaufen.
4. **Ein Limiter für alle Pipelines.** Lyra news + Theo research + journals
   + radar teilen sich eine Quota, aber die einzelnen Pipelines wissen
   nichts voneinander. Lyra-News-Spitzen verbrauchen Theo's Budget.

## Layer-Plan

5 Layer, in Reihenfolge. Erst 1-3, dann 4 (Billing), dann 5 wenn nötig.

### Layer 1 — Stop the self-knockout (Code, 1-2h, ship asap)

**Ziel:** Limiter hört auf sich selbst zu zerstören.

1. **`convergence_orchestrator.py:117` — `global_limiter.reset()` RAUS.**
   Begründung im Kommentar: "Reset entfernt — Token-Quota ist global, nicht
   per-Task. reset() auf max_concurrency=100 ist Grund für 82%-limited
   direkt nach jedem neuen Run." Stattdessen: einmaliger Init beim
   Container-Start, dann lernt der Limiter kontinuierlich.

2. **`minimax_limiter.py` Init-Werte senken:**
   - `max_concurrency`: 100 → 8 (8 parallele Calls sind bei 5h-Quota
     sicher; darüber knallt es)
   - `grow_step`: 5 → 1 (langsam wachsen, nicht in 5er-Sprüngen)
   - `grow_after_successes`: 10 → 20 (konservativer)
   - `min_concurrency`: 3 → 1 (bei Quota-Sperre ist 1 der einzige sichere Wert)
   - `base_delay`: 0.1s → 0.5s (5 req/s baseline statt 10)

3. **`minimax_limiter.py` neue Methode `_on_quota_exhausted()`:**
   - Setzt `self._frozen_until = time.monotonic() + 300` (5 min)
   - `request()` blockt sofort mit `raise QuotaExhaustedError` wenn frozen
   - Wird ausgelöst wenn `error_str` enthält:
     `"Token Plan usage limit reached"` ODER `"usage limit"` ODER Code `2056`
   - Loggt klare Meldung: `"[minimax-limiter] Quota exhausted — freezing all
     calls for 300s (5h window reset in ~Xh Ymin)"`

4. **Beide Call-Sites (`minimax_shared.py:203`, `config.py:554`):**
   - Bei `QuotaExhaustedError`: KEIN retry, fail fast mit klarem Reason
   - Bei echtem 429 (RPS): bisheriges Backoff-Verhalten
   - Im Orchestrator-Error-Handler: bei Quota-Fail `status='failed'`,
     `error_message="quota_exhausted: <details>"`, KEIN stall-guard nötig

### Layer 2 — Quota sichtbar machen (Code, 30min)

**Ziel:** Vor jedem Run wissen ob die Quota noch reicht.

1. **Neue Funktion `minimax_shared.probe_quota() -> dict`** mit
   `GET /v1/token_plan/remains` (MiniMax-Endpoint, gibt 5h-rolling +
   weekly remaining tokens zurück). Cache 60s, sonst bei jedem Run.

2. **Im `convergence_orchestrator.run()`** vor dem Start:
   - Wenn `remaining_5h < 500_000` (50k tokens reichen kaum für ein
     Decomposition) → raise `InsufficientQuotaError` mit klarer Meldung
   - Der theo_worker fängt das, setzt `status='failed'`, `error_message`
     enthält den genauen Stand (`"5h_remaining=123k, weekly=4.2M"`)
   - KEIN Stall-Guard, KEIN 45min-Warten — fail fast

3. **Neuer Endpoint `GET /api/theo/research/quota`** der die probe
   durchreicht, damit theo.html oben im Header den 5h-Status anzeigen
   kann. UI: "Quota: 2.3M/9.7M tokens remaining (5h)"

### Layer 3 — Sanftes Retry bei Quota (Code, 30min)

**Ziel:** Wenn der Run mitten in einer Quota-Sperre startet, soll er
nicht sofort failed sein sondern auf das Window-Ende warten.

1. **Im theo_worker:** Bei `InsufficientQuotaError` UND `remaining_5h <
   1M` → NICHT failed markieren, sondern Request auf "deferred" setzen
   mit `resume_at = now + 1h`. Worker holt diese Requests nach 1h wieder.

2. **Im theo_worker:** Bei `remaining_5h > 1M` aber < 5M → proceed but
   log a warning, run as normal (Limiter regelt via Layer 1).

3. **DB-Migration:** `research_requests.status` braucht neuen Wert
   `'deferred'`. Der Worker pollt `status IN ('queued', 'deferred')`.

### Layer 4 — Billing-Headroom (User, ~5min Arbeit + Geld)

**Ziel:** 9.7M/5h ist nicht genug für Dauerbetrieb mit Theo + Lyra.

1. **MiniMax Credits kaufen** (Pay-as-you-go). Memory-Note
   `project_theo_m3_quota_fix.md` Section D erklärt das: bei PAYG-Key
   deckt 2056 automatisch aus dem Credit-Guthaben, kein leerer Return.
2. **Anthropic-Fallback für Decomposition** (optional, 1-2h Code):
   - Decomposition ist der einzige 1-Call-Bottleneck (siehe unsere 6
     "Decomposition produced no research angles" failures)
   - Der Schritt macht ~1 Call, ~5k tokens — auf Anthropic Sonnet
     vielleicht $0.01 pro Run
   - Rest (specialists, synthesis, debate) bleibt auf MiniMax
   - Config: `THEO_DECOMPOSITION_MODEL = "minimax" | "anthropic"`
   - Default: `"minimax"`, umschaltbar wenn Quota eng

### Layer 5 — Cross-Pipeline-Awareness (Code, ~2h, nur wenn Layer 1-4 nicht reichen)

**Ziel:** Lyra-News-Spitzen sollen Theo's Quota nicht aufbrauchen.

1. **Pro-Pipeline Token-Buckets:** Eine separate `TokenBucket` pro
   Pipeline (Lyra/Theo/journals/radar). Summen-Cap = 5h-Limit. Jede
   Pipeline kriegt z.B. 30% des 5h-Limits zugeteilt, kann mehr ziehen
   wenn andere idle sind.

2. **ODER (einfacher):** Soft-Lock — wenn Lyra in den letzten 5min
   > 500k tokens verbraucht hat, Theo-Starts um 2-3min verzögern.
   Pragmatisch, keine perfekte Fairness, aber verhindert Quota-Killer.

3. **ODER (am einfachsten):** Cron-style Schedule — Theo nur in
   definierten Zeitfenstern (z.B. 02:00-06:00 UTC), Lyra news den
   Rest. Konfigurierbar via env.

## Was ich NICHT vorschlage

- Komplett-Umbau auf Anthropic: M3 ist gut für synthesis, ~89% der
  Calls. Bulk-Wechsel kostet mehr als er nutzt.
- Eigene Quota-Datenbank: MiniMax hat `/v1/token_plan/remains`, kein
  Bedarf das zu re-implementieren.
- Globalen Locking-Mechanismus zwischen Lyra und Theo: übertrieben
  für 1 Theo-Run pro Tag Use-Case.
- Den 12h-Worker-Timeout anfassen: orthogonal zum Quota-Problem.

## Reihenfolge

1. **Sofort (heute):** Layer 1 (remove reset, sane defaults, quota
   error detection) — committed auf Branch, getestet mit `THEO_FAST=1`
   smoke, gepushed + deployed.
2. **Morgen:** Layer 2 (probe_quota) + Layer 3 (deferred-Status) — gibt
   uns Sichtbarkeit + verhindert 45min Stalls für nichts.
3. **User-Action:** Layer 4 (PAYG-Key) — biggest single lever, sofort.
4. **Nur wenn 1-3 nicht reichen:** Layer 5.

## Erwartete Wirkung

| Metrik | Heute (vorher) | Nach Layer 1-3 | Nach Layer 4 (PAYG) |
|---|---|---|---|
| 429-Rate bei Batch-Start | 82% | <5% | ~0% |
| Decomposition-Failures | 6/52 | 0-1/52 | 0/52 |
| Stall-Cancels | 1/52 | 0/52 | 0/52 |
| Wall-Clock für 50 Prompts | ~30h | ~10-15h | ~8-10h |
| Quota-Reserve am Ende | leer | 20-40% | n/a (PAYG) |

## Offene Fragen

- **Lyra news** ruft auch durch den globalen Limiter. Sollte Layer 5
  vor Layer 4 deployed werden? (Antwort: nein, Layer 4 entkoppelt das.)
- **Weekly cap**: Layer 2 probed nur 5h. Weekly burnout ist seltener
  (einmal pro Woche) aber real. Sollte der probe beide zurückgeben und
  der Run bei weekly-niedrig auch deferred werden? Default: ja.
- **Smoke-Test-Regression**: nach Layer 1-Änderungen den
  `scripts/smoke_theo_host.py` lokal + auf VPS laufen lassen um zu
  prüfen dass normale Runs (kein Quota-Druck) noch funktionieren.
