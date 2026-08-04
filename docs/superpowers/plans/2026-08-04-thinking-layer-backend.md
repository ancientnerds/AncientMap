# Thinking-Layer Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend der Denkschicht aus `docs/superpowers/specs/2026-08-04-thinking-layer-design.md` — Weltmodell (`knowledge_claims`), Graph-Miner, Curator-Agent, Frontier-Erweiterung (connection/hypothesis + gezielte Fragen), Provenance-Regel, Feedback + Activity-Endpoint.

**Architecture:** Mo–Do nächtliche „Denkstunde" im bestehenden `_feeder_loop` (api-Container): Miner (SQL, kein LLM) erzeugt strukturelle Verbindungs-Kandidaten, Curator (ein `structured_llm_call`) kuratiert sie, pflegt Claims und schreibt gezielte Fragen als neue Frontier-Nodes. Der Picker gewichtet die neuen Node-Kinds, der Feeder nutzt die gespeicherte Frage. Alles best-effort nach dem Injector-Muster — ein Ausfall degradiert auf heutiges Verhalten.

**Tech Stack:** SQLAlchemy (raw SQL via `text()`), PostGIS (`ST_DistanceSphere`), MiniMax M3 via `structured_llm_call`, FastAPI (public_v1), pytest.

**Frontend (Knowledge-Seite, Spec §7) ist ein SEPARATER Folgeplan** — dieser Plan liefert die Daten + `GET /api/v1/knowledge/activity`.

**Deploy-Hinweise:** Neue Spalten brauchen ALTER sowohl im Orchestrator-Startup (lyra-Container) als auch im api-Startup — der Worker/Feeder läuft im api-Container. Nach Deploy: `docker compose up -d --build api` kommt vom CI; `... --build lyra` manuell (Pipeline-Änderungen, siehe MEMORY.md).

---

### Task 1: DB-Modelle + Migrationen (knowledge_claims, thinking_log, research_nodes-Spalten)

**Files:**
- Modify: `pipeline/database.py` (nach `class ResearchEdge`, ~Zeile 1455)
- Modify: `pipeline/lyra/orchestrator.py` (ALTER-Block in main(), ~Zeile 387ff)
- Modify: `api/main.py` (nach dem `create_all`-Aufruf beim Startup — Anker per Grep `create_all`)

- [ ] **Step 1: Modelle anlegen** — in `pipeline/database.py` direkt nach `ResearchEdge` einfügen. `JSONB` wird in der Datei bereits verwendet (UserContribution.enrichment_data) — Import wiederverwenden:

```python
class KnowledgeClaim(Base):
    """One claim in the permanent researcher's world model (2026-08-04 design).

    status: established | contested | refuted | open
    `refuted` is terminal — the curator never reopens a refuted claim; a
    refuted thesis must not re-enter the frontier as an open question.
    """

    __tablename__ = "knowledge_claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    norm_text: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Provenance: which papers assert this, how many EXTERNAL tier-1/2
    # sources back it (self-citations never count — spec §5).
    paper_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    external_source_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # UNIQUE enforces the refuted-is-terminal invariant at the DB level:
    # duplicate norm_text rows would let the curator's LIMIT-1 lookup pick
    # the non-refuted twin and silently reopen a refuted claim.
    __table_args__ = (UniqueConstraint("norm_text", name="uq_knowledge_claim_norm_text"),)

    def __repr__(self) -> str:
        return f"<KnowledgeClaim {self.status} {self.text[:40]!r}>"


class ThinkingLogEntry(Base):
    """One event in the thinking-layer activity feed (spec §7).

    kind: curator | miner | run_event
    Powers GET /api/v1/knowledge/activity — the Knowledge page timeline.
    """

    __tablename__ = "thinking_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<ThinkingLogEntry {self.kind} {self.summary[:40]!r}>"
```

Zusaetzlich im bestehenden `ResearchNode`-Docstring (der die kind/status/created_from-Enums listet) zwei Zeilen ergaenzen — dort schauen spaetere Tasks nach:

```
    question: stored research question for curator-created frontier nodes (2026-08-04)
    outcome:  confirmed | refuted | inconclusive — hypothesis nodes only
```

- [ ] **Step 2: ALTERs im Orchestrator** — in `pipeline/lyra/orchestrator.py`, im bestehenden Migrations-Block von main() (eine Transaktion, ans Ende der bestehenden ALTERs):

```python
conn.execute(text("ALTER TABLE research_nodes ADD COLUMN IF NOT EXISTS question TEXT"))
conn.execute(
    text("ALTER TABLE research_nodes ADD COLUMN IF NOT EXISTS outcome VARCHAR(20)")
)
conn.execute(
    text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_claim_norm_text "
        "ON knowledge_claims (norm_text)"
    )
)
```

(Der UNIQUE INDEX ist safe: die Tabelle ist neu und leer, wenn er erstmals laeuft. Im api-Pfad dieselbe Anweisung als `_api_migrations`-Eintrag.)

- [ ] **Step 3: ALTERs im api-Startup** — `api/main.py`: den `create_all`-Aufruf im Startup finden (Grep `create_all`), direkt danach idempotent dieselben zwei ALTERs ausführen (der Feeder/Picker läuft im api-Container und braucht die Spalten auch, wenn der lyra-Container noch nicht neu gebaut wurde):

```python
from sqlalchemy import text as _sql_text

with engine.connect() as conn:
    conn.execute(_sql_text("ALTER TABLE research_nodes ADD COLUMN IF NOT EXISTS question TEXT"))
    conn.execute(
        _sql_text("ALTER TABLE research_nodes ADD COLUMN IF NOT EXISTS outcome VARCHAR(20)")
    )
    conn.commit()
```

(Falls `api/main.py` bereits einen eigenen ALTER-Block hat: dort anhängen statt neu bauen. `engine` kommt aus `pipeline.database`.)

- [ ] **Step 4: Import-Check** — `python -c "from pipeline.database import KnowledgeClaim, ThinkingLogEntry; print('ok')"` → `ok`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/database.py pipeline/lyra/orchestrator.py api/main.py
git commit -m "feat(theo): knowledge_claims + thinking_log tables, research_nodes question/outcome columns"
```

---

### Task 2: thinking_log-Helper

**Files:**
- Create: `pipeline/lyra/thinking_log.py`
- Test: `tests/pipeline/test_thinking_log.py`

- [ ] **Step 1: Failing Test schreiben**

```python
"""thinking_log helper — best-effort activity feed writer (spec §7)."""

from types import SimpleNamespace

from pipeline.lyra import thinking_log as tl


class _FakeSession:
    def __init__(self):
        self.executed = []
        self.committed = False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_log_thinking_writes_row(monkeypatch):
    fake = _FakeSession()
    monkeypatch.setattr(tl, "_session_factory", lambda: fake)
    tl.log_thinking("curator", "3 claims updated", {"claims": 3})
    assert fake.committed
    (stmt, params) = fake.executed[0]
    assert "INSERT INTO thinking_log" in stmt
    assert params["kind"] == "curator"
    assert params["summary"] == "3 claims updated"


def test_log_thinking_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(tl, "_session_factory", boom)
    tl.log_thinking("miner", "x", None)  # must not raise
```

- [ ] **Step 2: Test läuft rot** — `python -m pytest tests/pipeline/test_thinking_log.py -q` → FAIL (`No module named 'pipeline.lyra.thinking_log'`).

- [ ] **Step 3: Implementierung**

```python
"""Best-effort writer for the thinking-layer activity feed (spec §7).

Every curator pass, miner batch and research-run lifecycle event lands here;
GET /api/v1/knowledge/activity serves it to the Knowledge page. A write
failure must never break the caller (injector pattern).
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _session_factory():
    from pipeline.database import get_session

    return get_session()


def log_thinking(kind: str, summary: str, details: dict | None = None) -> None:
    """Append one activity-feed event. kind: curator | miner | run_event."""
    try:
        with _session_factory() as session:
            session.execute(
                text("""
                    INSERT INTO thinking_log (id, kind, summary, details, created_at)
                    VALUES (:id, :kind, :summary, CAST(:details AS jsonb), NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "kind": kind,
                    "summary": summary[:500],
                    "details": json.dumps(details) if details is not None else None,
                },
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001 — feed is observability, never load-bearing
        logger.warning("[THINK] log_thinking failed: %s", exc)
```

- [ ] **Step 4: Tests grün** — `python -m pytest tests/pipeline/test_thinking_log.py -q` → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/thinking_log.py tests/pipeline/test_thinking_log.py
git commit -m "feat(theo): thinking_log writer for the knowledge activity feed"
```

---

### Task 3: Graph-Miner (Link-Prediction + PostGIS-Kookkurrenz)

**Files:**
- Create: `pipeline/lyra/graph_miner.py`
- Test: `tests/pipeline/test_graph_miner.py`

> **REDESIGNED 2026-08-04 (Commit 46e4c6b) nach Prod-Evidence-Review — die
> Code-Blöcke unten sind das SUPERSEDED Original; maßgeblich ist der
> committete Code.** Befund (Replay gegen den Live-Graphen, 13.148 Nodes):
> explored Topics haben NUR Paper-Nachbarn, alle Site-Nodes sind
> `reference`, kein explored Node trägt `site_id` → beide Struktur-Miner
> lieferten dauerhaft 0 Zeilen; naives Aufweiten ergäbe 206.659 signallose
> country+period-Paare. Neues Design: (1) **Label-Bridge** — explored
> `topic` ↔ struktureller `site`-Node via gleichem `norm_label` (virtueller
> Join, keine neuen Kanten); (2) Link-Miner zählt nur CONTENT-Nachbarn
> (`story`/`culture`/`person`), GROUP BY Node-IDs (78 Duplikat-Labels);
> (3) Spatial-Miner über die gebridgten researched sites mit
> LEAST/GREATEST-Perioden-Normalisierung; (4) `merge_candidates` mit
> Quoten 7/5/3 vor dem Cap, Cross-Miner-Dedup und Suppression via
> `existing_connection_norms` (beide Paar-Orderings); (5) `run_miner`
> lädt die connection-Node-norm_labels mit, loggt Fehler mit
> `exc_info=True`. 8 Tests inkl. run_miner-Wiring + Swallow.
>
> **NACHTRAG (2. Review-Runde):** Root-Cause-Fix in
> `graph_injectors._insert_frontier` gehört zu diesem Task — das
> `ON CONFLICT DO UPDATE` setzte nie `status`, wodurch injizierte Sites
> ewig `reference` blieben (0 von 5.307 Site-Nodes recherchierbar, der
> Sites-Injector war seit dem Full-Project-Graph tot). Neu: reference →
> frontier-Promotion (nie Downgrades) + site_id-COALESCE. Dazu Miner-
> Ehrlichkeitsfixes: Bridge-Population heute = 1 Node (wächst durch
> Site-Forschung), ARRAY_AGG ORDER BY, Site-Twin-Arm im NOT EXISTS,
> toter Guard entfernt. 2-Hop-Content-Nachbarn (site→story→culture) und
> Alias-Bridging via unified_site_names sind BEWUSST vertagt (YAGNI).
>
> **WACHSTUMSPFAD (korrigiert, 3. Review-Runde):** NICHT der Sites-
> Injector — der hat noch nie gefeuert (card_stats hat heute keine
> rarity_tier≥4-Rows; alle 5.307 Site-Nodes stehen bei signal 0.0).
> Die Bridge wächst über story-injizierte `topic`-Nodes mit Site-Namen:
> 57 Frontier-Site-Twins tragen die höchsten Signale der gesamten
> Frontier (bis 1175 vs. Median 0) und gewinnen im signal-dominierten
> Picker fast jeden Slot → +1 Bridge-Row pro Batch-Run. Die gemessenen
> Payoff-Paare (Karahan Tepe ↔ Göbekli Tepe: 21 geteilte Stories;
> Stonehenge ↔ Avebury: 6) landen, sobald beide Partner explored sind.
> **WATCH-ITEM:** `source_signal` akkumuliert stündlich unbegrenzt
> (daher 1175). Solange Sites `reference` waren, folgenlos — mit der
> Promotion wird Monopolisierung erreichbar (vgl. null-Node-Incident bei
> Signal 2220). Mitigation, wenn nötig: LEAST-Cap im Injector-Upsert
> oder Signal-Decay im Picker-Score. In Task 10 prüfen.
>
> **ROADMAP-NOTIZ (Task-5-Review):** Innerhalb des Synthese-Pools ordnet
> nur Kind-Gewicht + random() — kein Alters-Term. Wächst der Pool
> schneller als der ~zweiwöchentliche Slot ihn leert, kann ein einzelner
> Node beliebig lange liegen bleiben. Falls relevant: `created_at ASC`
> als Tiebreak oder kleiner Age-Bonus. Kein Task-5-Defekt.

Kandidaten kommen aus STRUKTUR-Daten, nicht aus Theos Prosa (Echo-Schutz, Spec §2). SQL bleibt dünn; Merge/Format ist pure Function und wird getestet.

- [ ] **Step 1: Failing Tests für die pure Functions**

```python
"""Graph miner — structural connection candidates (spec §2)."""

from types import SimpleNamespace

from pipeline.lyra.graph_miner import merge_candidates


def _link(a="Göbekli Tepe", b="Karahan Tepe", shared=3, via=("Pre-Pottery Neolithic",)):
    return SimpleNamespace(a_label=a, b_label=b, shared=shared, via=list(via))


def _spatial(a="Nan Madol", b="Leluh", km=45):
    return SimpleNamespace(a_label=a, b_label=b, km=km)


def test_merge_orders_by_strength_and_caps():
    links = [_link(shared=2), _link(a="A", b="B", shared=5)]
    spatial = [_spatial()]
    out = merge_candidates(links, spatial, cap=2)
    assert len(out) == 2
    assert out[0]["label"] == "A ↔ B"  # strongest link first
    assert out[0]["miner"] == "link"
    assert "5 shared" in out[0]["evidence"]


def test_merge_formats_spatial_evidence():
    out = merge_candidates([], [_spatial()], cap=10)
    assert out[0]["miner"] == "spatial"
    assert out[0]["label"] == "Nan Madol ↔ Leluh"
    assert "45 km" in out[0]["evidence"]


def test_merge_skips_self_pairs():
    out = merge_candidates([_link(a="X", b="X")], [], cap=10)
    assert out == []


def test_merge_includes_contested_claim_tensions():
    t = SimpleNamespace(claim_text="Dating of X is disputed across papers", node_label="Site X")
    out = merge_candidates([], [], [t], cap=10)
    assert out[0]["miner"] == "tension"
    assert out[0]["label"] == "Site X"
    assert "contested" in out[0]["evidence"]
```

- [ ] **Step 2: Test läuft rot** — `python -m pytest tests/pipeline/test_graph_miner.py -q` → FAIL (import).

- [ ] **Step 3: Implementierung**

```python
"""Structural connection mining on the research + project graph (spec §2).

Candidates come from DATA (graph topology, PostGIS geometry), never from
Theo's own prose — that is the structural half of the echo-chamber defense.
The curator (LLM) ranks and turns the survivors into frontier questions.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

_REFERENCE_KINDS = "('culture', 'person', 'period', 'country', 'empire')"


def mine_link_prediction(session, limit: int = 20) -> list:
    """Explored topic/site pairs sharing >=2 reference neighbors but no
    direct edge — the classic 'nobody drew this line yet' signal."""
    return session.execute(
        text(f"""
            WITH neigh AS (
                SELECT src AS a, dst AS b FROM research_edges
                UNION
                SELECT dst AS a, src AS b FROM research_edges
            )
            SELECT n1.label AS a_label, n2.label AS b_label,
                   COUNT(*) AS shared,
                   ARRAY_AGG(rn.label ORDER BY rn.label) AS via
            FROM neigh x
            JOIN neigh y ON y.b = x.b AND x.a < y.a
            JOIN research_nodes n1 ON n1.id = x.a
                 AND n1.status = 'explored' AND n1.kind IN ('topic', 'site')
            JOIN research_nodes n2 ON n2.id = y.a
                 AND n2.status = 'explored' AND n2.kind IN ('topic', 'site')
            JOIN research_nodes rn ON rn.id = x.b AND rn.kind IN {_REFERENCE_KINDS}
            WHERE NOT EXISTS (
                SELECT 1 FROM neigh d WHERE d.a = x.a AND d.b = y.a
            )
            GROUP BY n1.label, n2.label
            HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()


def mine_spatial_cooccurrence(session, max_km: int = 200, limit: int = 20) -> list:
    """Explored sites that are geographically close AND temporally
    overlapping, with no graph edge between them."""
    return session.execute(
        text("""
            SELECT n1.label AS a_label, n2.label AS b_label,
                   ROUND(ST_DistanceSphere(
                       ST_MakePoint(s1.lon, s1.lat),
                       ST_MakePoint(s2.lon, s2.lat)) / 1000) AS km
            FROM research_nodes n1
            JOIN research_nodes n2 ON n1.id < n2.id
            JOIN unified_sites s1 ON s1.id = n1.site_id
            JOIN unified_sites s2 ON s2.id = n2.site_id
            WHERE n1.status = 'explored' AND n2.status = 'explored'
              AND ST_DistanceSphere(
                      ST_MakePoint(s1.lon, s1.lat),
                      ST_MakePoint(s2.lon, s2.lat)) < :max_m
              AND s1.period_start IS NOT NULL AND s2.period_start IS NOT NULL
              AND s1.period_start <= COALESCE(s2.period_end, s2.period_start)
              AND s2.period_start <= COALESCE(s1.period_end, s1.period_start)
              AND NOT EXISTS (
                  SELECT 1 FROM research_edges e
                  WHERE (e.src = n1.id AND e.dst = n2.id)
                     OR (e.src = n2.id AND e.dst = n1.id)
              )
            ORDER BY km ASC
            LIMIT :limit
        """),
        {"max_m": max_km * 1000, "limit": limit},
    ).fetchall()


def mine_contested_claims(session, limit: int = 10) -> list:
    """World-model tensions: contested claims are re-research candidates —
    the third miner source from spec §2 (conflict detector, claims level)."""
    return session.execute(
        text("""
            SELECT c.text AS claim_text, n.label AS node_label
            FROM knowledge_claims c
            LEFT JOIN research_nodes n ON n.id = c.node_id
            WHERE c.status = 'contested'
            ORDER BY c.confidence DESC, c.updated_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()


def merge_candidates(
    link_rows: list, spatial_rows: list, tension_rows: list | None = None, cap: int = 15
) -> list[dict]:
    """Pure merge: format, drop self-pairs, strongest first, cap."""
    out: list[dict] = []
    for r in sorted(link_rows, key=lambda r: -r.shared):
        if r.a_label == r.b_label:
            continue
        out.append(
            {
                "label": f"{r.a_label} ↔ {r.b_label}",
                "miner": "link",
                "evidence": (
                    f"{r.shared} shared reference neighbors "
                    f"({', '.join(list(r.via)[:4])}), no direct link researched"
                ),
            }
        )
    for r in spatial_rows:
        if r.a_label == r.b_label:
            continue
        out.append(
            {
                "label": f"{r.a_label} ↔ {r.b_label}",
                "miner": "spatial",
                "evidence": f"{int(r.km)} km apart, overlapping periods, no researched link",
            }
        )
    for r in tension_rows or []:
        label = (r.node_label or r.claim_text[:80]).strip()
        if not label:
            continue
        out.append(
            {
                "label": label,
                "miner": "tension",
                "evidence": f"world model marks this contested: {r.claim_text[:200]}",
            }
        )
    return out[:cap]


def run_miner() -> list[dict]:
    """Collect candidates from all miners. Best-effort (injector pattern)."""
    try:
        from pipeline.database import get_session
        from pipeline.lyra.thinking_log import log_thinking

        with get_session() as session:
            links = mine_link_prediction(session)
            spatial = mine_spatial_cooccurrence(session)
            tensions = mine_contested_claims(session)
        candidates = merge_candidates(links, spatial, tensions)
        log_thinking(
            "miner",
            f"Miner: {len(candidates)} connection candidates "
            f"({len(links)} link, {len(spatial)} spatial, {len(tensions)} tension)",
            {"candidates": [c["label"] for c in candidates]},
        )
        return candidates
    except Exception as exc:  # noqa: BLE001 — thinking must never kill the feeder
        logger.error("[THINK] miner failed: %s", exc)
        return []
```

- [ ] **Step 4: Tests grün** — `python -m pytest tests/pipeline/test_graph_miner.py -q` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/graph_miner.py tests/pipeline/test_graph_miner.py
git commit -m "feat(theo): graph miner — link-prediction + PostGIS co-occurrence candidates"
```

---

### Task 4: Curator-Agent (Denkstunde)

**Files:**
- Create: `pipeline/lyra/curator.py`
- Create: `pipeline/lyra/prompts/curator_pass.txt`
- Test: `tests/pipeline/test_curator.py`

- [ ] **Step 1: Prompt-Datei** — `pipeline/lyra/prompts/curator_pass.txt`:

```
You are the curator of the Ancient Nerds permanent researcher. You maintain
its world model and decide what is worth researching next. You are rigorous:
you prefer falsification over confirmation, and you treat the researcher's
own past papers as leads, never as proof.

You receive:
1. WORLD MODEL — current claims with status and confidence.
2. NEW PAPERS — excerpts of papers completed since your last pass.
3. CANDIDATES — structural connection candidates mined from the knowledge
   graph (shared neighbors, spatial-temporal co-occurrence). These come from
   data, not from the researcher's own texts.
4. OPEN HYPOTHESES — hypothesis topics whose research has completed and
   awaits your verdict.

Your tasks:
- claim_updates: extract NEW claims from the new papers and update existing
  ones. status: established (>=2 independent external tier-1/2 sources),
  contested (sources conflict), refuted (evidence against), open. NEVER
  change a refuted claim back — refuted is terminal. Count only EXTERNAL
  sources in external_source_count; the researcher's own papers (marked
  [self]) never count.
- connections: pick at most the 5 best CANDIDATES and write one precise,
  researchable question each. Reference what is already known ("We
  established X; Y remains open — investigate whether Z links them.").
  Discard weak candidates silently.
- hypotheses: formulate at most 3 falsifiable hypotheses from the world
  model. Each question MUST instruct the researcher to steelman the null
  hypothesis and to actively search for disconfirming evidence.
- hypothesis_outcomes: for each OPEN HYPOTHESIS, verdict confirmed ONLY if
  the paper cites >=2 independent external tier-1/2 sources for the link;
  refuted if the evidence contradicts it; otherwise inconclusive. A refuted
  verdict is a SUCCESS, not a failure.
- summary: 2-3 sentences on what you learned and decided this pass.

Be selective. An empty connections list is a valid answer.
```

- [ ] **Step 2: Failing Tests** — `tests/pipeline/test_curator.py`:

```python
"""Curator pass — apply logic + scheduling (specs §3, §6)."""

from datetime import UTC, datetime, timedelta

from pipeline.lyra.curator import CURATOR_SCHEMA, _apply_curator_output, thinking_pass_due


class _FakeSession:
    def __init__(self, existing_status=None):
        self.executed = []
        self._existing_status = existing_status
        self.committed = False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params or {}))

        class _R:
            def fetchone(inner):
                if "SELECT status FROM knowledge_claims" in str(stmt) and self._existing_status:
                    return type("Row", (), {"status": self._existing_status})()
                return None

        return _R()

    def commit(self):
        self.committed = True


def _out(**kw):
    base = {
        "claim_updates": [],
        "connections": [],
        "hypotheses": [],
        "hypothesis_outcomes": [],
        "summary": "s",
    }
    base.update(kw)
    return base


def test_connection_nodes_inserted_with_question():
    s = _FakeSession()
    stats = _apply_curator_output(
        s, _out(connections=[{"label": "A ↔ B", "question": "Does A explain B?"}])
    )
    assert stats["connections"] == 1
    stmt, params = next(e for e in s.executed if "INSERT INTO research_nodes" in e[0])
    assert params["kind"] == "connection"
    assert params["question"] == "Does A explain B?"
    # The connection node gets `connects` edges to its endpoints (data model).
    assert any("'connects'" in e[0] for e in s.executed)


def test_connection_cap_and_junk_guard():
    conns = [{"label": f"T{i} ↔ U{i}", "question": "q"} for i in range(9)]
    conns.append({"label": "null", "question": "q"})
    s = _FakeSession()
    stats = _apply_curator_output(s, _out(connections=conns))
    assert stats["connections"] == 5  # cap
    assert all("null" not in str(p) for _, p in s.executed if p)


def test_refuted_claim_never_reopens():
    s = _FakeSession(existing_status="refuted")
    stats = _apply_curator_output(
        s,
        _out(claim_updates=[{"text": "The X claim", "status": "established", "confidence": 0.9}]),
    )
    assert stats["claims"] == 0  # update skipped
    assert not any("UPDATE knowledge_claims" in e[0] for e in s.executed)


def test_hypothesis_outcome_updates_node():
    s = _FakeSession()
    _apply_curator_output(
        s, _out(hypothesis_outcomes=[{"node_label": "If X then Z", "outcome": "refuted"}])
    )
    stmt, params = next(e for e in s.executed if "SET outcome" in e[0])
    assert params["outcome"] == "refuted"


def test_thinking_pass_due_window():
    mon_night = datetime(2026, 8, 3, 3, 0, tzinfo=UTC)  # Monday 03:00 UTC
    fri_night = datetime(2026, 8, 7, 3, 0, tzinfo=UTC)  # Friday — research days
    mon_noon = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    assert thinking_pass_due(mon_night, None) is True
    assert thinking_pass_due(fri_night, None) is False
    assert thinking_pass_due(mon_noon, None) is False
    assert thinking_pass_due(mon_night, mon_night - timedelta(hours=2)) is False  # ran already


def test_schema_has_required_sections():
    assert set(CURATOR_SCHEMA["required"]) >= {"claim_updates", "connections", "hypotheses"}
```

- [ ] **Step 3: rot** — `python -m pytest tests/pipeline/test_curator.py -q` → FAIL (import).

- [ ] **Step 4: Implementierung** — `pipeline/lyra/curator.py`:

```python
"""Curator agent — the permanent researcher's nightly thinking pass (spec §3).

One structured LLM call Mon–Thu night: update the world model from new
papers, curate miner candidates into `connection` frontier nodes with
targeted questions, formulate falsifiable hypotheses, judge completed
hypothesis runs. Best-effort: any failure degrades to today's behavior.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from pipeline.lyra.research_graph import is_junk_label, normalize_label

logger = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_PASS = 5
MAX_HYPOTHESES_PER_PASS = 3

CURATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "node_label": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["established", "contested", "refuted", "open"],
                    },
                    "confidence": {"type": "number"},
                    "external_source_count": {"type": "integer"},
                    "paper_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "status"],
            },
        },
        "connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "question"],
            },
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "question"],
            },
        },
        "hypothesis_outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_label": {"type": "string"},
                    "outcome": {
                        "type": "string",
                        "enum": ["confirmed", "refuted", "inconclusive"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["node_label", "outcome"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["claim_updates", "connections", "hypotheses", "summary"],
}


def thinking_pass_due(now_utc: datetime, last_pass_at: datetime | None) -> bool:
    """Nightly Mon–Thu 02:00–05:00 UTC, at most once per 20h. Fri–Sun are
    research days (weekend batch gate) — the curator stays quiet."""
    if now_utc.weekday() > 3:
        return False
    if not (2 <= now_utc.hour < 5):
        return False
    return last_pass_at is None or (now_utc - last_pass_at) >= timedelta(hours=20)


def _insert_topic_node(session, label: str, kind: str, question: str, rationale: str) -> bool:
    if is_junk_label(label) or not question.strip():
        return False
    session.execute(
        text("""
            INSERT INTO research_nodes
                (id, label, norm_label, kind, status, created_from, source_signal,
                 question, created_at, updated_at)
            VALUES
                (:id, :label, :norm_label, :kind, 'frontier', 'curator', 2.0,
                 :question, NOW(), NOW())
            ON CONFLICT (kind, norm_label) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "label": label.strip()[:500],
            "norm_label": normalize_label(label)[:500],
            "kind": kind,
            "question": question.strip(),
        },
    )
    return True


def _link_connection_endpoints(session, conn_label: str) -> None:
    """A connection node 'A ↔ B' gets `connects` edges to A and B when those
    nodes exist — the Knowledge page draws the new line (spec data model).

    A label can exist as BOTH a topic and a site node (the miner's label
    bridge) — edges to both twins are deliberate: the connection anchors to
    every representation of its endpoint."""
    if "↔" not in conn_label:
        return
    conn_norm = normalize_label(conn_label)[:500]
    for part in conn_label.split("↔"):
        session.execute(
            text("""
                INSERT INTO research_edges (id, src, dst, kind, weight, created_at)
                SELECT CAST(:id AS uuid), c.id, t.id, 'connects', 1.0, NOW()
                FROM research_nodes c
                JOIN research_nodes t
                  ON t.norm_label = :part_norm AND t.kind != 'connection'
                WHERE c.kind = 'connection' AND c.norm_label = :conn_norm
                ON CONFLICT (src, dst, kind) DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "conn_norm": conn_norm,
                "part_norm": normalize_label(part)[:500],
            },
        )


def _apply_curator_output(session, out: dict) -> dict:
    """Apply a validated curator output. Pure DB writes, no LLM. Returns
    counters for the thinking log. Refuted claims never reopen."""
    stats = {"claims": 0, "connections": 0, "hypotheses": 0, "outcomes": 0}

    for cu in out.get("claim_updates", []):
        claim_text = (cu.get("text") or "").strip()
        if not claim_text:
            continue
        norm = normalize_label(claim_text)[:500]
        existing = session.execute(
            text("SELECT status FROM knowledge_claims WHERE norm_text = :norm LIMIT 1"),
            {"norm": norm},
        ).fetchone()
        if existing and existing.status == "refuted":
            continue  # refuted is terminal (spec §1)
        paper_ids = json.dumps(cu.get("paper_ids") or [])
        if existing:
            session.execute(
                text("""
                    UPDATE knowledge_claims
                    SET status = :status, confidence = :conf,
                        external_source_count = :ext,
                        paper_ids = (SELECT COALESCE(jsonb_agg(DISTINCT e), '[]'::jsonb)
                                     FROM jsonb_array_elements(
                                          COALESCE(paper_ids, '[]'::jsonb)
                                          || CAST(:paper_ids AS jsonb)) e),
                        updated_at = NOW()
                    WHERE norm_text = :norm
                """),
                {
                    "status": cu["status"],
                    "conf": float(cu.get("confidence") or 0.5),
                    "ext": int(cu.get("external_source_count") or 0),
                    "paper_ids": paper_ids,
                    "norm": norm,
                },
            )
        else:
            session.execute(
                text("""
                    INSERT INTO knowledge_claims
                        (id, text, norm_text, node_id, status, confidence,
                         external_source_count, paper_ids, created_at, updated_at)
                    VALUES
                        (:id, :text, :norm,
                         (SELECT id FROM research_nodes
                          WHERE norm_label = :node_norm LIMIT 1),
                         :status, :conf, :ext, CAST(:paper_ids AS jsonb), NOW(), NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "text": claim_text,
                    "norm": norm,
                    "node_norm": normalize_label(cu.get("node_label") or "")[:500],
                    "status": cu["status"],
                    "conf": float(cu.get("confidence") or 0.5),
                    "ext": int(cu.get("external_source_count") or 0),
                    "paper_ids": paper_ids,
                },
            )
        stats["claims"] += 1

    for conn in out.get("connections", [])[:MAX_CONNECTIONS_PER_PASS]:
        label = conn.get("label") or ""
        if _insert_topic_node(
            session, label, "connection",
            conn.get("question") or "", conn.get("rationale") or "",
        ):
            _link_connection_endpoints(session, label)
            stats["connections"] += 1

    for hyp in out.get("hypotheses", [])[:MAX_HYPOTHESES_PER_PASS]:
        if _insert_topic_node(
            session, hyp.get("label") or "", "hypothesis",
            hyp.get("question") or "", hyp.get("rationale") or "",
        ):
            stats["hypotheses"] += 1

    for ho in out.get("hypothesis_outcomes", []):
        session.execute(
            text("""
                UPDATE research_nodes
                SET outcome = :outcome, updated_at = NOW()
                WHERE kind = 'hypothesis' AND norm_label = :norm
            """),
            {
                "outcome": ho["outcome"],
                "norm": normalize_label(ho.get("node_label") or "")[:500],
            },
        )
        stats["outcomes"] += 1

    session.commit()
    return stats
```

Danach im selben File die Input-Sammlung + der LLM-Aufruf:

```python
def _gather_inputs(session) -> dict:
    """Collect world model, new papers, miner candidates, open hypotheses."""
    last_pass = session.execute(
        text("SELECT MAX(created_at) AS ts FROM thinking_log WHERE kind = 'curator'")
    ).fetchone()
    since = last_pass.ts if last_pass and last_pass.ts else datetime(2020, 1, 1)

    claims = session.execute(
        text("""
            SELECT text, status, confidence FROM knowledge_claims
            ORDER BY updated_at DESC LIMIT 100
        """)
    ).fetchall()

    papers = session.execute(
        text("""
            SELECT id::text AS request_id, question, result_json FROM research_requests
            WHERE status = 'completed' AND is_batch = TRUE AND completed_at > :since
            ORDER BY completed_at DESC LIMIT 5
        """),
        {"since": since},
    ).fetchall()
    paper_excerpts = []
    for p in papers:
        report = (json.loads(p.result_json).get("report") or "") if p.result_json else ""
        # Head (framing) + tail (conclusions) of the report; middle is bulk.
        paper_excerpts.append(
            {
                "request_id": p.request_id,
                "question": p.question,
                "excerpt": report[:4000] + "\n...\n" + report[-3000:],
            }
        )

    open_hypotheses = session.execute(
        text("""
            SELECT n.label, n.question, rr.result_json
            FROM research_nodes n
            JOIN research_requests rr ON rr.id = n.paper_id AND rr.status = 'completed'
            WHERE n.kind = 'hypothesis' AND n.status = 'explored' AND n.outcome IS NULL
            LIMIT 5
        """)
    ).fetchall()
    hyp_inputs = [
        {
            "label": h.label,
            "question": h.question,
            "paper_tail": ((json.loads(h.result_json).get("report") or "")[-3000:])
            if h.result_json
            else "",
        }
        for h in open_hypotheses
    ]

    from pipeline.lyra.graph_miner import run_miner

    return {
        "claims": [dict(r._mapping) for r in claims],
        "papers": paper_excerpts,
        "candidates": run_miner(),
        "open_hypotheses": hyp_inputs,
    }


def run_curator_pass() -> None:
    """One nightly thinking pass. Best-effort — never raises."""
    try:
        from pathlib import Path

        from pipeline.database import get_session
        from pipeline.lyra.config import LyraSettings
        from pipeline.lyra.minimax_shared import structured_llm_call
        from pipeline.lyra.thinking_log import log_thinking

        settings = LyraSettings()
        with get_session() as session:
            inputs = _gather_inputs(session)

        system = (Path(__file__).parent / "prompts" / "curator_pass.txt").read_text(
            encoding="utf-8"
        )
        out = structured_llm_call(
            system=system,
            user_message=json.dumps(inputs, ensure_ascii=False, default=str)[:60000],
            schema=CURATOR_SCHEMA,
            max_tokens=4096,
            settings=settings,
            temperature=settings.temperature_verification,
        )
        if not out:
            logger.warning("[THINK] curator returned empty output — skipping apply")
            return

        with get_session() as session:
            stats = _apply_curator_output(session, out)

        summary = (
            f"Denkstunde: {stats['claims']} claims, {stats['connections']} connections, "
            f"{stats['hypotheses']} hypotheses, {stats['outcomes']} verdicts"
        )
        log_thinking("curator", summary, {**stats, "llm_summary": out.get("summary", "")})
        try:
            from api.services.notify import send_discord_webhook

            send_discord_webhook(
                {
                    "embeds": [
                        {
                            "title": "🧠 Theo Denkstunde",
                            "description": f"{summary}\n{out.get('summary', '')[:500]}",
                            "color": 0x3498DB,
                        }
                    ]
                }
            )
        except Exception:  # noqa: BLE001 — notification is best-effort
            pass
    except Exception as exc:  # noqa: BLE001 — thinking must never kill the feeder
        logger.error("[THINK] curator pass failed: %s", exc)
```

Hinweis für den Executor: `settings.temperature_verification` existiert laut `structured_llm_call`-Docstring (config.py, per-Stage-Temperaturen) — vor Nutzung den exakten Feldnamen in `pipeline/lyra/config.py` verifizieren und ggf. anpassen.

- [ ] **Step 5: Tests grün** — `python -m pytest tests/pipeline/test_curator.py -q` → 7 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/lyra/curator.py pipeline/lyra/prompts/curator_pass.txt tests/pipeline/test_curator.py
git commit -m "feat(theo): curator agent — nightly thinking pass with world model + hypotheses"
```

---

### Task 5: Frontier-Erweiterung (Picker-Gewichte, gespeicherte Frage, Synthese-Quote)

**Files:**
- Modify: `pipeline/lyra/research_graph.py` (`pick_next_frontier_topic` ~Zeile 205, `question_for_node` ~Zeile 253)
- Modify: `api/services/theo_worker.py` (`_feeder_loop`, Feeder-Claim-Block ~Zeile 888)
- Test: `tests/pipeline/test_frontier_picker.py`

- [ ] **Step 1: Failing Tests**

```python
"""Frontier picker extensions — stored question, synthesis quota (spec §4)."""

from pipeline.lyra.research_graph import _allow_synthesis, question_for_node


def test_question_for_node_prefers_stored_question():
    node = {"kind": "connection", "label": "A ↔ B", "question": "Does A explain B?"}
    assert question_for_node(node) == "Does A explain B?"


def test_question_for_node_falls_back_to_template():
    node = {"kind": "topic", "label": "Ein Sof", "question": None}
    assert "Ein Sof" in question_for_node(node)


def test_allow_synthesis_quota():
    # Max 1 of the last 3 weekend runs may be connection/hypothesis (spec §4).
    assert _allow_synthesis(["topic", "topic", "topic"]) is True
    assert _allow_synthesis(["connection", "topic", "topic"]) is False
    assert _allow_synthesis([]) is True
    assert _allow_synthesis(["hypothesis"]) is False
```

- [ ] **Step 2: rot** — `python -m pytest tests/pipeline/test_frontier_picker.py -q` → FAIL.

- [ ] **Step 3: `research_graph.py` erweitern**

`question_for_node` — gespeicherte Frage gewinnt:

```python
def question_for_node(node: dict) -> str:
    """Format a frontier node as a research question for the pipeline.
    A curator-written question stored on the node always wins (spec §4)."""
    stored = (node.get("question") or "").strip()
    if stored:
        return stored
    label = node["label"].strip()
    if node["kind"] == "site":
        return (
            f"What is known about {label}? Cover discovery history, dating, "
            f"interpretation controversies, and fringe theories."
        )
    if label.endswith("?"):
        return label
    return (
        f"What does the evidence say about {label}? Contrast mainstream "
        f"scholarship with fringe interpretations."
    )
```

Neue pure Function + Picker-Änderung (Kind-Gewichte, `question` im SELECT, Kind-Filter als Parameter):

```python
def _allow_synthesis(recent_seed_kinds: list[str]) -> bool:
    """Max 1 of 3 recent batch runs may be synthesis (connection/hypothesis)
    — fresh external topics keep the majority (anti-echo, spec §4)."""
    return not any(k in ("connection", "hypothesis") for k in recent_seed_kinds)
```

In `pick_next_frontier_topic(session, include_synthesis: bool = True)`:
- SELECT ergänzen um `n.question` und den Gewichts-Term direkt hinter `n.source_signal`:

```sql
                   + CASE n.kind WHEN 'hypothesis' THEN 3.0
                                 WHEN 'connection' THEN 2.0
                                 ELSE 0 END
```

- Kind-Filter: `AND n.kind IN ('topic', 'site', 'connection', 'hypothesis')` bzw. bei `include_synthesis=False` nur `('topic', 'site')` — als gebundener Parameter:

```python
    kinds = ("topic", "site", "connection", "hypothesis") if include_synthesis else ("topic", "site")
```

und im SQL `AND n.kind = ANY(:kinds)` mit `{"kinds": list(kinds)}`.
- Rückgabe-Dict ergänzen: `"question": row.question`.

- [ ] **Step 4: Feeder in `theo_worker.py`** — im Feeder-Block (nach `gate_open`-Berechnung, vor `pick_next_frontier_topic`) die Quote bestimmen und durchreichen:

```python
                    with get_session() as session:
                        recent_kinds = [
                            r.kind
                            for r in session.execute(
                                text("""
                                    SELECT COALESCE(n.kind, 'topic') AS kind
                                    FROM research_requests rr
                                    LEFT JOIN research_nodes n
                                      ON n.paper_id = rr.id
                                     AND n.kind IN ('connection', 'hypothesis')
                                    WHERE rr.is_batch = TRUE
                                    ORDER BY rr.started_at DESC NULLS LAST
                                    LIMIT 3
                                """)
                            ).fetchall()
                        ]
                        from pipeline.lyra.research_graph import _allow_synthesis

                        node = pick_next_frontier_topic(
                            session, include_synthesis=_allow_synthesis(recent_kinds)
                        )
```

(ersetzt den bisherigen `node = pick_next_frontier_topic(session)`-Aufruf; Imports oben im bestehenden Import-Block des Feeders ergänzen.)

- [ ] **Step 5: Tests grün** — `python -m pytest tests/pipeline/test_frontier_picker.py tests/api/test_theo_worker_quota.py -q` → alle grün (Regression: Picker-Signatur ist rückwärtskompatibel).

- [ ] **Step 6: Commit**

```bash
git add pipeline/lyra/research_graph.py api/services/theo_worker.py tests/pipeline/test_frontier_picker.py
git commit -m "feat(theo): frontier picker — kind weights, stored questions, synthesis quota"
```

---

### Task 6: Provenance-Regel (eigene Papers = Kontext, nie Beleg)

**Files:**
- Modify: `pipeline/lyra/theo_sources.py` (`RawSource` ~Zeile 161, `AncientNerdsResearchAdapter` ~Zeile 1200)
- Modify: `pipeline/lyra/prompts/theo_specialist_analysis.txt`
- Test: `tests/pipeline/test_self_source_provenance.py`

- [ ] **Step 1: Failing Tests**

```python
"""Provenance rule — own papers are context, never evidence (spec §5)."""

from pipeline.lyra.theo_sources import AncientNerdsResearchAdapter, RawSource


def test_rawsource_has_self_flag_default_false():
    s = RawSource(url="u", title="t", snippet="s")
    assert s.self_source is False


def test_own_research_adapter_is_context_tier():
    adapter = AncientNerdsResearchAdapter()
    assert adapter.default_tier == 4  # context tier — sorts behind 1..3


def test_specialist_prompt_contains_self_rule():
    from pathlib import Path

    prompt = (
        Path("pipeline/lyra/prompts/theo_specialist_analysis.txt").read_text(encoding="utf-8")
    )
    assert "[self]" in prompt
```

- [ ] **Step 2: rot** — `python -m pytest tests/pipeline/test_self_source_provenance.py -q` → FAIL.

- [ ] **Step 3: Implementierung**

`RawSource` erweitern (Feld ans Ende der Dataclass):

```python
    # Own prior papers (ancientnerds_research): context/pointer only, never
    # independent corroboration (spec 2026-08-04 §5).
    self_source: bool = False
```

`AncientNerdsResearchAdapter`: `default_tier` von `2` auf `4` ändern (Kommentar: `# Context tier — own papers are leads, not evidence (2026-08-04)`), und in `search()` beim Bauen der `RawSource`-Objekte `title=f"[self] {hit['...']}"`-Präfix + `self_source=True` setzen (exakte Feldnamen beim Bauen aus dem bestehenden Code übernehmen, ~Zeile 1215ff).

`theo_specialist_analysis.txt` — am Ende des Regelblocks (bestehende Struktur der Datei respektieren) ergänzen:

```
SOURCES MARKED [self] are Ancient Nerds' own prior research papers. Treat
them as leads and context ONLY: never cite them as independent evidence,
never count them toward corroboration. Any claim that only [self] sources
support must be re-verified against external sources or flagged as
unverified.
```

- [ ] **Step 4: Tier-Sortierung prüfen** — die Dedup/Sortierung (`deduped.sort(key=lambda r: (r.default_tier, -r.citation_count))`, ~Zeile 1476) sortiert Tier 4 automatisch ans Ende — keine Änderung nötig. Kurz verifizieren, dass kein Code `default_tier <= 3` als Filter nutzt: `grep -n "default_tier" pipeline/lyra/*.py` lesen; falls ein Filter Tier 4 verwirft, stattdessen Tier-4-Quellen explizit als Kontext durchlassen (Befund im Commit dokumentieren).

- [ ] **Step 5: Tests grün** — `python -m pytest tests/pipeline/test_self_source_provenance.py -q` → 3 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/lyra/theo_sources.py pipeline/lyra/prompts/theo_specialist_analysis.txt tests/pipeline/test_self_source_provenance.py
git commit -m "feat(theo): provenance rule — own papers demoted to context tier, [self]-marked"
```

---

### Task 7: Run-Events in den Activity-Feed

**Files:**
- Modify: `api/services/theo_worker.py` (Completion-Pfad bei `mark_node_explored`, ~Zeile 278; Feeder-Enqueue-Log, ~Zeile 916)
- Test: bestehende Worker-Tests bleiben grün (reine Zusatz-Logs, keine Logikänderung)

- [ ] **Step 1: Completion-Event** — direkt nach dem bestehenden `mark_node_explored(request_id)`-Aufruf:

```python
                from pipeline.lyra.thinking_log import log_thinking

                log_thinking(
                    "run_event",
                    f"Research completed: {question[:200]}",
                    {"request_id": request_id},
                )
```

- [ ] **Step 2: Enqueue-Event** — im Feeder nach dem erfolgreichen `link_node_to_request(...)` (~Zeile 915):

```python
                            log_thinking(
                                "run_event",
                                f"Queued from frontier: {node['label'][:200]}",
                                {"request_id": request_id, "kind": node["kind"]},
                            )
```

(Import am Funktionsanfang des Feeder-Blocks: `from pipeline.lyra.thinking_log import log_thinking`.)

- [ ] **Step 3: Regression** — `python -m pytest tests/api/ -q` → alle grün.

- [ ] **Step 4: Commit**

```bash
git add api/services/theo_worker.py
git commit -m "feat(theo): run lifecycle events into the thinking activity feed"
```

---

### Task 8: Denkstunde in den Feeder-Loop verdrahten

**Files:**
- Modify: `api/services/theo_worker.py` (`_feeder_loop`, ~Zeile 845ff neben `injector_last`)
- Test: `tests/api/test_thinking_schedule.py`

- [ ] **Step 1: Failing Test**

```python
"""Feeder wiring — the nightly thinking pass fires Mon–Thu only (spec §3)."""

from datetime import UTC, datetime

from pipeline.lyra.curator import thinking_pass_due


def test_weekend_nights_never_think():
    # Fri–Sun nights belong to the research runs (weekend batch gate).
    for day in (7, 8, 9):  # Fri, Sat, Sun 2026-08
        assert thinking_pass_due(datetime(2026, 8, day, 3, 0, tzinfo=UTC), None) is False
```

- [ ] **Step 2: rot laufen lassen** — schlägt nur fehl, falls Task 4 die Fenster-Logik anders gebaut hat; sonst direkt grün → dann als Charakterisierungs-Test committen.

- [ ] **Step 3: Verdrahtung** — in `_feeder_loop`, direkt nach dem Injector-/Full-Ingest-Block (vor dem `pending`-Query):

```python
            # Nightly thinking pass (Mon-Thu 02-05 UTC): miner + curator.
            # last_pass comes from thinking_log so restarts don't double-run.
            from datetime import UTC as _UTC
            from datetime import datetime as _dt

            from pipeline.lyra.curator import run_curator_pass, thinking_pass_due

            with get_session() as session:
                last_curator = session.execute(
                    text("SELECT MAX(created_at) AS ts FROM thinking_log WHERE kind = 'curator'")
                ).fetchone()
            last_ts = last_curator.ts.replace(tzinfo=_UTC) if last_curator and last_curator.ts else None
            if thinking_pass_due(_dt.now(_UTC), last_ts):
                logger.info("[THINK] Nightly thinking pass starting")
                await asyncio.to_thread(run_curator_pass)
```

(Der Curator ruft den Miner selbst auf — `_gather_inputs` → `run_miner()`. LLM-Call läuft über den Limiter wie jeder andere Call; Low-Lane ist nicht nötig, der Pass läuft nachts außerhalb des Batch-Fensters.)

- [ ] **Step 4: Regression** — `python -m pytest tests/api/ tests/pipeline/test_curator.py -q` → grün.

- [ ] **Step 5: Commit**

```bash
git add api/services/theo_worker.py tests/api/test_thinking_schedule.py
git commit -m "feat(theo): wire nightly thinking pass into the feeder loop"
```

---

### Task 9: `GET /api/v1/knowledge/activity`

**Files:**
- Modify: `api/routes/public_v1.py` (nach dem `get_graph`-Endpoint, ~Zeile 1720; Response-Modelle zu den bestehenden Graph-Modellen)
- Test: `tests/api/test_knowledge_activity.py`

- [ ] **Step 1: Failing Test** (pure Shaping-Funktion, Route bleibt dünn)

```python
"""Activity feed endpoint shaping (spec §7)."""

from datetime import datetime
from types import SimpleNamespace

from api.routes.public_v1 import _activity_items


def test_activity_items_shape():
    rows = [
        SimpleNamespace(
            created_at=datetime(2026, 8, 4, 3, 0),
            kind="curator",
            summary="Denkstunde: 3 claims",
            details={"claims": 3},
        )
    ]
    items = _activity_items(rows)
    assert items[0]["kind"] == "curator"
    assert items[0]["summary"].startswith("Denkstunde")
    assert items[0]["created_at"].startswith("2026-08-04")
```

- [ ] **Step 2: rot** — FAIL (`_activity_items` fehlt).

- [ ] **Step 3: Implementierung** — in `public_v1.py`, Muster von `get_graph` (Cache, License, rate_limit) übernehmen:

```python
def _activity_items(rows) -> list[dict]:
    return [
        {
            "created_at": r.created_at.isoformat(),
            "kind": r.kind,
            "summary": r.summary,
            "details": r.details,
        }
        for r in rows
    ]


    # (innerhalb des public_app-Blocks, nach get_graph:)
    @public_app.get(
        "/knowledge/activity",
        summary="Thinking-layer activity feed",
        description=(
            "Chronological feed of the permanent researcher's thinking layer: "
            "nightly curator passes, miner batches, and research-run lifecycle "
            f"events.\n\n**License: {RESEARCH_LICENSE}**"
        ),
        tags=["Knowledge Graph"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def get_knowledge_activity(
        limit: int = Query(50, ge=1, le=200),
        db: Session = Depends(get_db),
    ):
        cache_key = f"pubv1:knowledge_activity:{limit}"
        cached = cache_get(cache_key)
        if cached:
            return cached
        rows = db.execute(
            text("""
                SELECT created_at, kind, summary, details
                FROM thinking_log
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()
        payload = {"items": _activity_items(rows), "license": RESEARCH_LICENSE}
        cache_set(cache_key, payload, ttl=60)
        return payload
```

- [ ] **Step 4: Tests grün + Lint** — `python -m pytest tests/api/test_knowledge_activity.py -q` → passed; `ruff format api/ pipeline/ tests/ && ruff check api/ pipeline/ tests/` → clean.

- [ ] **Step 5: Commit**

```bash
git add api/routes/public_v1.py tests/api/test_knowledge_activity.py
git commit -m "feat(api): GET /api/v1/knowledge/activity — thinking-layer feed"
```

---

### Follow-up-Tickets (aus den Reviews, NICHT Teil dieses Plans)

1. **Dead LLM-Source-Audit (pre-existing):** `AuditHandler.audit_angle`
   returnt auf JEDEM Angle früh — `reliability_tier == 0` ist unerreichbar
   (score_tier_by_domain liefert nie 0), `source_items` bleibt leer. Die
   ganze Audit-Stage inkl. Tier-3-Noise-Floor ist toter Code.
2. **Unbounded source_signal:** Injector-Akkumulation +120/Tag auf
   Top-Nodes; LEAST-Cap oder Decay, sobald Site-Promotion aktiv ist.
3. **Live-LLM-Test:** `test_journal_assessor::test_fuzzy_mismatch_detected`
   macht echte MiniMax-Calls pro Testlauf (quota-abhängig flaky) — mocken.
4. **Synthese-Pool-Aging:** created_at-Tiebreak, falls der Pool wächst.
5. **Journal-Audit clobbert Tier 4:** `research_stages._stage_audit` schreibt
   `reliability_tier` unconditional (Prompt kennt nur 1-3) — ein self-source
   kann im Journal als `[Reputable]` gerendert werden. Langfristig das
   References-Label aus `self_source` ableiten statt aus dem Tier. Dazu:
   Journal-Marker-Cleanup-Regex (`\[(V?\d+)\]`) lässt nicht-numerische
   Tokens passieren — ggf. auf validate_or_repair umstellen (separates
   Produkt, eigenes Ticket).
6. **Failed-Synthese-Sackgasse (Final-Review, Important):** Scheitert ein
   connection/hypothesis-Run terminal, bleibt der Node ewig `researching`
   (mark_node_explored greift nur bei Erfolg), der Miner supprimiert das
   Paar für immer, der Curator kann das Label nicht neu queuen (ON CONFLICT
   DO NOTHING). Geerbt von 2026-07-26 (Topics gleiches Problem), durch
   Hypothesen aber teurer. Fix: Node bei terminalem `failed` des Requests
   auf `frontier` zurücksetzen.

### Post-Deploy-Checkliste (erste Denk-Nacht — aus dem Final-Review)

1. Nach api-Deploy: `\d research_nodes` — question/outcome-Spalten da?
   `knowledge_claims` + `thinking_log` + `uq_knowledge_claim_norm_text`?
   (Guard gegen den Migration-Swallow in `_api_migrations`.)
2. **Manueller lyra-Rebuild** (`docker compose up -d --build lyra`) —
   journal-seitige [self]-Guards + research_stages-self_source.
3. Erste Mo–Do-Nacht 02–05 UTC: genau EINE `kind='curator'`-Row (+ eine
   `miner`-Row), kein `details.failed`, Discord-Embed „Denkstunde".
4. Inhalt: Claims aus den 5 ÄLTESTEN Batch-Papers (Cursor draint ASC,
   ~4 Nächte Backlog); kein `established` mit ext<2 (demoted-Zähler);
   Kandidaten ~0 ist ERWARTET (Bridge-Population = 1 Node).
5. `GET /api/v1/knowledge/activity` liefert Items + Lizenz; run_events da.
6. Bewusst: Curator läuft auch bei geschlossenem Pacing-Gate (das gated
   Claims, nicht das Denken) — Hypothesen akkumulieren bis zum Wochenende.
7. Injector-Promotion beobachten: erste Stunde kann reference-Sites zu
   frontier promoten; mit unbounded signal (Ticket 2) drohen Monopol-Picks.
8. Nächstes Paper: References mit `[self]`-Präfix ohne Tier-Badge, kein
   `[self]` in der Prose.

### Task 10: Gesamt-Verifikation

- [ ] **Step 1:** `python -m pytest tests/pipeline/ tests/api/ -q` → alles grün (inkl. der 86 bestehenden Quota/Pacing-Tests).
- [ ] **Step 2:** `ruff format api/ pipeline/ && ruff check api/ pipeline/` → clean (CI prüft beides).
- [ ] **Step 3:** Manuelle Probe der Denkstunde ohne Zeitfenster: `python -c "from pipeline.lyra.curator import run_curator_pass; run_curator_pass()"` gegen die lokale DB (oder VPS-Tunnel) — erwartet: thinking_log-Row `kind='curator'`, ggf. neue connection/hypothesis-Nodes, Discord-Embed.
- [ ] **Step 4:** Commit offener Reste, KEIN Push (User-Freigabe nötig; Deploy-Hinweise im Header beachten).
