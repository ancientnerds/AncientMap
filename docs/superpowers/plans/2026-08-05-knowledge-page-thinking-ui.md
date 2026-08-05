# Knowledge-Page Thinking-UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spec §7 der Denkschicht sichtbar machen (`docs/superpowers/specs/2026-08-04-thinking-layer-design.md`): connection/hypothesis-Nodes im Graph, Focus-Card mit Frage/Outcome/Claims, Aktivitäts-Feed aus `thinking_log`, Live-Panel — auf der bestehenden Knowledge-Seite.

**Architecture:** Zwei kleine Backend-Erweiterungen (GraphNode-Felder, Claims-Endpoint), dann rein additive Frontend-Arbeit in `KnowledgePage.tsx`/`KnowledgePage.css` nach den dortigen `kg-*`-Konventionen. Der Renderer (`knowledgeGraphRenderer.ts`, hand-rolled Three.js Points-Shader, KEIN 3d-force-graph) bleibt unangetastet — neue Kinds fließen über die bestehenden Farb-/Sichtbarkeits-Pfade.

**Tech Stack:** FastAPI (public_v1), React + eigenes Three.js-Rendering, plain CSS (`kg-*`-Präfix), Vite Multi-Page.

**CI-Gates:** Backend `ruff check/format api/ pipeline/` + `mypy api/`; Frontend `npm run type-check` + `npm run build` (in `ancient-nerds-map/`).

**Exploration-Fakten (verifiziert 2026-08-05):** Farben `KnowledgePage.tsx:26-40` (`KIND_COLORS`, 13 Kinds); Layer-Chips `LAYERS` Zeile 62-67 (4 Gruppen) + Render 456-464; Focus `computeFocusSet` 151-189, `applyColors` 191-219, Info-Card 514-541 (`.kg-infocard`); Typen `RenderNode` in `knowledgeGraphRenderer.ts:14-29`, `GraphData/GraphEdge` inline in `KnowledgePage.tsx:13-23`; Fetch Zeile 107-115 (einmalig, ohne `?kinds=`); Inline-Live-Mini `.kg-live` 442-447 (Duplikat von `LiveResearchPanel`); Hook `useCurrentResearch` wird in Zeile 99 schon aufgerufen; Activity-Endpoint existiert backend-seitig (`/api/v1/knowledge/activity`), ist frontend-seitig unkonsumiert; `GraphNode`-Schema `api/schemas/public_v1.py:548-564` OHNE question/outcome; `get_graph`-SQL `api/routes/public_v1.py:1713-1739`.

---

### Task 1: Backend — GraphNode um question/outcome erweitern

**Files:**
- Modify: `api/schemas/public_v1.py` (GraphNode ~548)
- Modify: `api/routes/public_v1.py` (get_graph SQL ~1713 + Node-Bau darunter)
- Test: `tests/api/test_graph_thinking_fields.py` (neu)

- [ ] **Step 1 (Test zuerst):**

```python
"""GraphNode carries the thinking-layer fields (spec §7)."""

from api.schemas.public_v1 import GraphNode


def test_graphnode_thinking_fields_default_none():
    n = GraphNode(id="x", label="L", kind="hypothesis", status="frontier", signal=0.0, degree=0)
    assert n.question is None
    assert n.outcome is None


def test_graphnode_accepts_thinking_values():
    n = GraphNode(
        id="x", label="L", kind="hypothesis", status="explored",
        signal=2.0, degree=1, question="Does A explain B?", outcome="refuted",
    )
    assert n.outcome == "refuted"
```

- [ ] **Step 2:** rot laufen lassen (Feld fehlt).
- [ ] **Step 3:** `GraphNode` ergänzen (nach `site_id`):

```python
    # Thinking layer (spec §7): curator-authored nodes carry their stored
    # research question; hypothesis nodes their verdict.
    question: str | None = None
    outcome: str | None = Field(None, description="confirmed | refuted | inconclusive")
```

Außerdem den stalen `kind`-Field-Kommentar („topic | paper | site | entity") auf die reale Liste inkl. `connection | hypothesis` aktualisieren.

- [ ] **Step 4:** `get_graph`-SQL: `n.question, n.outcome` in die SELECT-Liste aufnehmen und beim `GraphNode(...)`-Bau durchreichen (`question=r.question, outcome=r.outcome`). Cache-Key bleibt; TTL 300s rolliert die Payload-Form von selbst.
- [ ] **Step 5:** Tests grün; `ruff format`/`check` auf beiden Dateien; mypy-Delta-Check: `mypy api/ --no-error-summary` darf keine NEUEN Fehler gegen den Stand vor dem Task zeigen (Zeilennummern-Shifts ignorieren).
- [ ] **Step 6:** Commit `feat(api): graph nodes carry question/outcome for the thinking UI`.

---

### Task 2: Backend — Claims-per-Node-Endpoint

**Files:**
- Modify: `api/routes/public_v1.py` (nach `get_knowledge_activity` ~1813), `api/schemas/public_v1.py` (neben ActivityResponse)
- Test: `tests/api/test_knowledge_claims_endpoint.py` (neu)

- [ ] **Step 1 (Test zuerst, pure Helper wie `_activity_items`):**

```python
"""Claims-per-node shaping (spec §7 Focus-Card)."""

from types import SimpleNamespace

from api.routes.public_v1 import _claim_items


def test_claim_items_shape():
    rows = [
        SimpleNamespace(
            text="The dating is contested",
            status="contested",
            confidence=0.6,
            external_source_count=1,
            paper_ids=["abc"],
        )
    ]
    items = _claim_items(rows)
    assert items[0]["status"] == "contested"
    assert items[0]["confidence"] == 0.6
    assert items[0]["paper_ids"] == ["abc"]
```

- [ ] **Step 2:** rot.
- [ ] **Step 3:** Schemas `ClaimItem` (text, status, confidence float, external_source_count int, paper_ids list[str] | None) + `ClaimsResponse` (items, license) im Stil von ActivityItem/ActivityResponse. Modul-Helper:

```python
def _claim_items(rows) -> list[dict]:
    """Shape knowledge_claims rows for the Focus-Card (spec §7). Pure."""
    return [
        {
            "text": r.text,
            "status": r.status,
            "confidence": r.confidence,
            "external_source_count": r.external_source_count,
            "paper_ids": r.paper_ids,
        }
        for r in rows
    ]
```

Route nach dem Muster von `get_knowledge_activity` (rate_limit, Tags "Knowledge Graph", License-Zeile):

```python
    @public_app.get("/knowledge/claims", response_model=ClaimsResponse, ...)
    async def get_knowledge_claims(
        node_id: str = Query(..., description="research_nodes UUID"),
        db: Session = Depends(get_db),
    ):
        cache_key = f"pubv1:knowledge_claims:{node_id}"
        cached = cache_get(cache_key)
        if cached:
            return cached
        rows = db.execute(
            text("""
                SELECT text, status, confidence, external_source_count, paper_ids
                FROM knowledge_claims
                WHERE node_id = CAST(:nid AS uuid)
                ORDER BY updated_at DESC
                LIMIT 20
            """),
            {"nid": node_id},
        ).fetchall()
        response = ClaimsResponse(
            items=[ClaimItem(**i) for i in _claim_items(rows)], license=RESEARCH_LICENSE
        )
        cache_set(cache_key, response.model_dump(), ttl=60)
        return response
```

Ein ungültiger/unbekannter node_id liefert schlicht `items: []` (CAST wirft bei Nicht-UUID → das Verhalten prüfen: FastAPI 500 wäre falsch — bei ValueError/DBAPIError sauber HTTP 422 zurückgeben; wenn das dem No-Fallback-Stil widerspricht, UUID vorab mit `uuid.UUID(node_id)` validieren und bei ValueError `raise HTTPException(422)`).

- [ ] **Step 4:** Tests grün; ruff; mypy-Delta.
- [ ] **Step 5:** Commit `feat(api): GET /api/v1/knowledge/claims — focus-card world-model data`.

---

### Task 3: Frontend — Kinds, Farben, Thinking-Layer-Chip, Typen

**Files:**
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.tsx` (KIND_COLORS 26-40, LAYERS 62-67, GraphData-Typen 13-23)
- Modify: `ancient-nerds-map/src/pages/knowledgeGraphRenderer.ts` (RenderNode 14-29)

- [ ] **Step 1:** `RenderNode` um `question?: string | null` und `outcome?: string | null` ergänzen. (`GraphData` in KnowledgePage konsumiert RenderNode — nichts weiter nötig.)
- [ ] **Step 2:** `KIND_COLORS` + zwei Einträge:

```ts
  connection: '#5eead4', // thinking layer: curator-mined link candidates
  hypothesis: '#fbbf24', // thinking layer: falsifiable hypotheses
```

(Kontrast geprüft gegen die 13 Bestandsfarben: Türkis hell vs. culture `#14b8a6` dunkler, Amber vs. paper-Gold `#ffd700` heller/kälter — bewusste Nachbarschaft: Hypothesen sind Vor-Papers.)

- [ ] **Step 3:** Outcome-Farbvarianten NUR für hypothesis-Nodes in der Farb-Pipeline (dort, wo `KIND_RGB` aufgelöst wird — `applyColors`/Basis-Farbzuweisung): `outcome === 'confirmed'` → `#4ade80`, `outcome === 'refuted'` → `#94a3b8` (grau = abgeschlossen/tot), sonst Basis-Amber. Als kleine Helper-Funktion `nodeBaseRgb(node)` neben `KIND_RGB`, damit Erst-Färbung und Focus-Recoloring dieselbe Logik nutzen (kein Duplikat!).
- [ ] **Step 4:** `LAYERS` bekommt eine 5. Gruppe `thinking: ['connection', 'hypothesis']`; der Chip rendert automatisch über das bestehende `Object.keys(LAYERS)`-Mapping. Default: aktiv.
- [ ] **Step 5:** `npm run type-check` grün.
- [ ] **Step 6:** Commit `feat(knowledge): thinking-layer kinds — colors, outcome tints, layer chip`.

---

### Task 4: Frontend — Focus-Card: Frage, Outcome-Badge, Claims

**Files:**
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.tsx` (Info-Card 514-541 + neuer Lazy-Fetch)
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.css` (kg-*-Konventionen)

- [ ] **Step 1:** Lazy-Claims-Fetch: bei `focused`-Wechsel auf einen Node mit `kind in ('connection','hypothesis','topic','site')` → `fetch('/api/v1/knowledge/claims?node_id=' + focused.id)`, State `claims: ClaimItem[] | null` (null = lädt/none), Fehler still (Feed-Daten sind Zusatz, kein Kernpfad — Kommentar dazu). Bei Focus-Wechsel State zurücksetzen.
- [ ] **Step 2:** Info-Card ergänzt (innerhalb `.kg-infocard`):
  - `focused.question` (falls vorhanden): eigener Block `.kg-card-question` mit kursiver Frage.
  - Outcome-Badge (nur hypothesis): `.kg-badge` mit Text confirmed/refuted/open und Farbe passend zu Task 3.
  - Claims-Liste (max 5 sichtbar): `.kg-claim` Zeilen — Status-Punkt (established grün / contested amber / refuted grau / open blau), `text` (2-zeilig geclampt), Konfidenz als `62%`-Mini-Label. Leerer Zustand: nichts rendern (kein „No claims"-Rauschen).
- [ ] **Step 3:** CSS: `.kg-card-question`, `.kg-badge`, `.kg-claim`-Familie im bestehenden Stil (JetBrains Mono, Border `#1f4a56`, Panel-BG `rgba(15,35,42,0.85)`); Mobile-Breakpoint beachten (Info-Card bleibt sichtbar, Claims auf 3 geclampt).
- [ ] **Step 4:** `npm run type-check` + `npm run build` grün.
- [ ] **Step 5:** Commit `feat(knowledge): focus card — stored question, outcome badge, world-model claims`.

---

### Task 5: Frontend — Aktivitäts-Feed-Panel

**Files:**
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.tsx`
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.css`

- [ ] **Step 1:** Datentyp + Fetch: `ActivityItem { created_at: string; kind: 'curator'|'miner'|'run_event'; summary: string; details: Record<string, unknown> | null }`. Initial-Fetch `/api/v1/knowledge/activity?limit=50` + 60s-Poll (Muster `useCurrentResearch`: setInterval + cleanup; Fehler still).
- [ ] **Step 2:** UI: collapsible Panel `.kg-activity` (Desktop: rechts unten, über der Legende; Toggle-Chip „Activity" neben den Layer-Chips). Zeilen: relative Zeit (`vor 2 h` — kleine Helper-Fn, keine Lib), Kind-Icon (🧠 curator / ⛏️ miner / 🔬 run_event), `summary` einzeilig ellipsiert, Titel-Attribut = voll. `details.failed === true` → Zeile rot getönt (`#c02023`-Border-Left). Leerer Feed: dezenter Hinweis „Theo hat noch nicht gedacht — erste Denkstunde Mo–Do 02:00–05:00 UTC".
- [ ] **Step 3:** Mobile (`max-width: 700px`): Panel versteckt wie `.kg-legend`.
- [ ] **Step 4:** type-check + build grün.
- [ ] **Step 5:** Commit `feat(knowledge): thinking activity feed panel`.

---

### Task 6: Frontend — LiveResearchPanel statt Inline-Duplikat

**Files:**
- Modify: `ancient-nerds-map/src/components/theo/LiveResearchPanel.tsx` (+ optionaler Prop)
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.tsx` (Inline `.kg-live` 442-447 raus, Panel rein)
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.css` (`.kg-live`/`.kg-live-dot`/`kg-pulse` CSS entfernen, 34-72)

- [ ] **Step 1:** `LiveResearchPanel` bekommt Prop `showGraphLink?: boolean` (default `true`); der „Explore the Knowledge Graph →"-Link (Zeile 49-51) rendert nur bei `true` (Selbst-Link auf der Knowledge-Seite wäre absurd).
- [ ] **Step 2:** KnowledgePage: Inline-`.kg-live`-Block ersetzen durch `<LiveResearchPanel showGraphLink={false} />` (der Hook-Aufruf Zeile 99 kann bleiben, falls andernorts genutzt — prüfen; wenn nur fürs Inline-Panel: mit entfernen). Duplikat-CSS löschen (NEVER duplicate — Repo-Regel).
- [ ] **Step 3:** TheoPage-Verhalten unverändert (default-Prop). type-check + build grün.
- [ ] **Step 4:** Commit `refactor(knowledge): shared LiveResearchPanel replaces inline duplicate`.

---

### Task 7: Gesamt-Verifikation, Review, Deploy

- [ ] **Step 1:** Backend: `python -m pytest tests/api/ tests/pipeline/ -q --ignore=tests/pipeline/test_journal_assessor.py` (Baseline: 2 bekannte Failures + DB-Errors), `ruff format --check api/ pipeline/`, `ruff check api/ pipeline/`, mypy-Delta gegen main.
- [ ] **Step 2:** Frontend: `npm run type-check && npm run build` in `ancient-nerds-map/` (Worktree — main-WIP `exportFormats.ts` existiert dort nicht).
- [ ] **Step 3:** Kombiniertes Quality-Review (ein Reviewer über den ganzen Branch; Fokus: Farb-/Focus-Pipeline ohne Duplikate, Fetch-Fehlerpfade still-aber-dokumentiert, CSS-Konventionstreue, Endpoint-Validierung).
- [ ] **Step 4:** Merge → main, Push, `gh run watch <id> --exit-status` (ohne Pipe), Deploy verifizieren: Live-Checks auf `https://ancientnerds.com/knowledge.html` (HTTP 200 + neuer Build-Hash), `/api/v1/graph` enthält question/outcome-Keys, `/api/v1/knowledge/claims?node_id=<uuid>` antwortet.
- [ ] **Step 5:** Worktree + Branch aufräumen, Memory aktualisieren, Bericht.
