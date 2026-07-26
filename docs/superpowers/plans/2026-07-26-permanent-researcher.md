# Permanent Researcher + Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continuous low-priority Theo research fed by a knowledge graph (frontier = topic queue), with website-submitted runs executing in parallel at full speed, and quality-gate-passing papers auto-published.

**Architecture:** Part B builds the graph data layer (two Postgres tables written by the pipeline at run end + source injectors) and the frontier topic engine. Part A replaces the global crawl pin with contextvar-based pacing lanes, gives the worker two slots (max one batch run), adds the feeder that keeps the batch queue filled from the frontier, and moves auto-publish into the worker.

**Tech Stack:** SQLAlchemy models (tables auto-create via `Base.metadata.create_all` in `api/main.py:82`), contextvars (proven pattern: `pipeline/lyra/token_accounting.py` — propagates through `asyncio.create_task` and `asyncio.to_thread`), FastAPI worker loops in `api/services/theo_worker.py`.

**Spec:** `docs/superpowers/specs/2026-07-26-permanent-researcher-design.md`

**Conventions:** run `python -m ruff check` + `ruff format` on every touched file before each commit. Never push (owner instruction; deploys kill in-flight research runs). Author every commit with the standard Co-Authored-By line.

---

## Part B — Graph data layer + topic engine

### Task 1: Graph models

**Files:**
- Modify: `pipeline/database.py` (append after `TtsRequest`, ~line 1390)

- [ ] **Step 1: Add models**

```python
class ResearchNode(Base):
    """A node in the research knowledge graph.

    kind:   topic | paper | site | entity
    status: frontier (unexplored topic), researching (feeder claimed it),
            explored (paper exists / entity extracted)
    created_from: rabbit_hole | story | journal | site | manual | backfill | paper
    """

    __tablename__ = "research_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    norm_label: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="frontier", index=True)
    created_from: Mapped[str] = mapped_column(String(20), nullable=False)
    source_signal: Mapped[float] = mapped_column(Float, default=0.0)
    paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_requests.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unified_sites.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("kind", "norm_label", name="uq_research_node_kind_label"),)


class ResearchEdge(Base):
    """A directed edge between research nodes.

    kind: leads_to (paper -> rabbit hole) | cites | contradicts | about_site | related
    """

    __tablename__ = "research_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    src: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_nodes.id", ondelete="CASCADE"), index=True
    )
    dst: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_nodes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("src", "dst", "kind", name="uq_research_edge"),)
```

Note: edge FKs CASCADE on research_nodes is allowed (graph-owned data); the
node FKs to research_requests / unified_sites are SET NULL per project rule.

- [ ] **Step 2: Verify import + ruff, commit** — `python -c "from pipeline.database import ResearchNode, ResearchEdge"`.

### Task 2: Graph builder + persistence

**Files:**
- Create: `pipeline/lyra/research_graph.py`
- Test: `tests/test_research_graph.py`

- [ ] **Step 1: Failing test for the pure builder**

```python
from pipeline.lyra.research_graph import build_graph_from_state, normalize_label

class FakeAngle:
    def __init__(self, id, topic, spawned_from=None, rabbit_holes=None):
        self.id, self.topic, self.spawned_from = id, topic, spawned_from
        self.rabbit_holes = rabbit_holes or []

class FakeState:
    def __init__(self):
        self.question = "Cyclical ages?"
        self.paper_title = "Cyclical World Ages"
        self.angles = [
            FakeAngle("a1", "Canonical sources", rabbit_holes=["Lurianic Kabbalah"]),
            FakeAngle("a2", "Kabbalah deep dive", spawned_from="a1"),
        ]

def test_builder_emits_paper_node_and_frontier():
    nodes, edges = build_graph_from_state(FakeState(), "req-123")
    kinds = {(n["kind"], n["status"], n["label"]) for n in nodes}
    assert ("paper", "explored", "Cyclical World Ages") in kinds
    # spawned angle a2 covers "Kabbalah deep dive" -> explored topic;
    # un-spawned rabbit hole stays frontier
    assert ("topic", "frontier", "Lurianic Kabbalah") in kinds
    assert any(e["kind"] == "leads_to" for e in edges)

def test_normalize_label():
    assert normalize_label("  The  Kybalion! ") == "the kybalion"
```

- [ ] **Step 2: Implement** — `normalize_label` (lower, collapse whitespace, strip punctuation), `build_graph_from_state(state, request_id)` returns plain dicts (no DB), `persist_graph(nodes, edges, session)` upserting on `(kind, norm_label)` (`INSERT ... ON CONFLICT DO UPDATE SET source_signal = greatest(...)`, frontier never downgrades an explored node), and `persist_state_graph(state, request_id)` opening its own session, wrapped in try/except with `logger.error` (spec: best-effort, must never fail the paper).

- [ ] **Step 3: Tests green, ruff, commit.**

### Task 3: Collect rabbit holes + persist at run end

**Files:**
- Modify: `pipeline/lyra/research_state.py` (ResearchAngle: add `rabbit_holes: list[str] = field(default_factory=list)`)
- Modify: `pipeline/lyra/handlers/angle_specialist.py:251` (after `rabbit_holes_found = ...`: `angle.rabbit_holes.extend(rabbit_holes_found)`)
- Modify: `pipeline/lyra/convergence_orchestrator.py` (after the empty-paper guard, before `return state`: `persist_state_graph(state, request_id)` — only when `request_id` and no `state.error`)

- [ ] Steps: add field → wire collection → wire persistence → ruff → commit.

### Task 4: Source injectors

**Files:**
- Create: `pipeline/lyra/graph_injectors.py`
- Test: extend `tests/test_research_graph.py`

- [ ] **Step 1:** Implement four injector functions, each returning the number of new frontier nodes; all insert via a shared `_insert_frontier(label, created_from, signal, site_id=None)` that dedupes on `(kind='topic'|'site', norm_label)`:
  - `inject_from_stories(session, days=7)` — recent `news_items` headlines grouped by `site_name_extracted`/headline keywords; signal = count.
  - `inject_from_journal(session)` — latest `news_articles` title + summary topics.
  - `inject_from_sites(session, limit=20)` — `card_stats` rarity_tier >= 4 joined to `unified_sites`, sites without an existing paper node; kind `site`.
  - `inject_from_radar(session, limit=20)` — `user_contributions` where source='lyra' and enrichment_status in ('enriched','promoted') ordered by mention_count.
  `run_all_injectors()` opens a session, runs all four, logs counts, never raises.
- [ ] **Step 2:** Unit test `_insert_frontier` dedupe (same label twice → one row, signal accumulates).
- [ ] **Step 3:** ruff, commit.

### Task 5: Frontier topic engine

**Files:**
- Modify: `pipeline/lyra/research_graph.py`

- [ ] **Step 1:** `pick_next_frontier_topic(session) -> dict | None`:

```sql
SELECT n.id, n.label, n.kind,
       n.source_signal
       + COALESCE(deg.cnt, 0) * 0.5
       - CASE WHEN recent.hit IS NOT NULL THEN 2.0 ELSE 0 END  -- diversity penalty
       + random() * 0.5 AS score
FROM research_nodes n
LEFT JOIN (SELECT dst, COUNT(*) cnt FROM research_edges GROUP BY dst) deg ON deg.dst = n.id
LEFT JOIN (  -- penalize children of the 3 most recently explored papers
    SELECT e.dst AS hit FROM research_edges e
    JOIN research_nodes p ON p.id = e.src AND p.kind = 'paper'
    WHERE p.updated_at > NOW() - INTERVAL '3 days'
) recent ON recent.hit = n.id
WHERE n.status = 'frontier' AND n.kind IN ('topic', 'site')
ORDER BY score DESC
LIMIT 1
```

  Marks the picked node `status='researching'`, returns `{id, label, kind, site_id}`. `question_for_node(node)` formats the research question (site nodes: "What is known about <label>? Cover discovery history, dating, interpretation controversies, and fringe theories."; topic nodes: label used directly if it already ends with '?', else "What does the evidence say about <label>? Contrast mainstream scholarship with fringe interpretations.").
- [ ] **Step 2:** ruff, commit.

### Task 6: Backfill script

**Files:**
- Create: `scripts/backfill_research_graph.py`

- [ ] One M3 structured call per published paper (`structured_llm_call` pattern from the pipeline) extracting `{topics: [...], entities: [...], site_names: [...], open_questions: [...]}` from the report; insert paper node (explored) + extracted nodes + edges. Runs inside the api container post-deploy: `docker exec ancient_nerds_api python scripts/backfill_research_graph.py`. Commit; execution deferred to post-deploy.

---

## Part A — Permanent operation

### Task 7: Contextvar pacing lanes (replaces global pin)

**Files:**
- Modify: `pipeline/lyra/minimax_limiter.py`
- Modify: `pipeline/lyra/convergence_orchestrator.py` (pin block → contextvar bind)
- Test: `tests/test_minimax_limiter_lanes.py`

- [ ] **Step 1:** In `minimax_limiter.py`: module-level `_run_low_priority: contextvars.ContextVar[bool] = ContextVar("minimax_low_priority", default=False)` + `bind_low_priority(flag)`. In `request()`: read the var; low-priority calls pace against **lane-local state** (`_low_last_call_time`, `_low_active_count`, clamped to concurrency 1 and `>= _crawl_delay_s`), high-priority calls use the existing adaptive state untouched. Keep freeze/quota logic shared. Remove `pin_crawl`/`unpin_crawl` and their call sites (dead once lanes exist); keep `throttle()` (watchdog band) which now also only clamps the low lane's delay floor AND the high lane's adaptive delay as before.
- [ ] **Step 2:** Orchestrator: replace the pin/unpin block with `bind_low_priority(low_priority and self._settings.theo_low_priority)`.
- [ ] **Step 3:** Test: two threads sharing one limiter, one context-bound low + one high; assert the high lane completes N calls while the low lane is still waiting out its crawl delay, and stats expose `low_lane_calls`.
- [ ] **Step 4:** ruff, commit.

### Task 8: Saturation controller

**Files:**
- Modify: `pipeline/lyra/minimax_limiter.py` (crawl delay becomes `set_crawl_delay_s()` module hook, default 60)
- Modify: `api/services/theo_quota_monitor.py` (on every probe: `set_crawl_delay_s(delay_for_window(pct))`)
- Test: extend `tests/test_minimax_limiter_lanes.py`

- [ ] `delay_for_window(five_hour_pct)` ladder — percentage-based so it survives the Plus→Max upgrade unchanged: `>=60% → 30s`, `>=40% → 60s`, `<40% → 90s` (watchdog THROTTLED/EXHAUSTED bands unchanged below that). Unit-test the ladder; ruff; commit.

### Task 9: Worker: two slots, max one batch

**Files:**
- Modify: `api/services/theo_config.py` (`THEO_PARALLEL_SLOTS = 2`)
- Modify: `api/services/theo_worker.py` (poll loop refactor)

- [ ] **Step 1:** Replace the inline `async with _semaphore: await wait_for(...)` with task spawning: module dict `_active_runs: dict[str, tuple[asyncio.Task, bool]]` (request_id → (task, is_batch)). Poll loop: prune finished tasks; claim only when `len(_active_runs) < THEO_PARALLEL_SLOTS`; extend the claim query with `AND (is_batch = FALSE OR :no_batch_running)` so at most one batch run exists; after claim, `asyncio.create_task(_supervise(row))` where `_supervise` wraps the existing `wait_for(_run_with_stall_guard(...), timeout=...)` + timeout/stall handling + inter-task backoff, then removes itself from `_active_runs`. The `_semaphore` global is deleted.
- [ ] **Step 2:** Stall guard: `_read_limiter_activity()` is process-global; with two concurrent runs it can mask a stalled batch run while the UI run makes calls. Change the guard's activity signal to per-request progress counters only (`_read_progress_sig` already exists) — drop the limiter-activity leniency.
- [ ] **Step 3:** ruff, commit. (No unit tests — verified by the live E2E in Task 12.)

### Task 10: Feeder loop

**Files:**
- Modify: `api/services/theo_worker.py` (new `_feeder_loop()`, started in `start_worker` alongside `cleanup_stale_deferred`)

- [ ] Every 10 min: if no `queued`/`running` batch rows AND the batch gate would be open (reuse `_batch_claim_allowed` inputs) → `pick_next_frontier_topic()` → `INSERT INTO research_requests (id, user_id, question, effort, status, is_batch, created_at) VALUES (..., '442000112756064260', <question_for_node>, 'high', 'queued', TRUE, NOW())` and stamp the node with `paper_id = request_id`. Also run `run_all_injectors()` once per hour from the same loop (cheap SQL only). Log every feed. ruff, commit.

### Task 11: Auto-publish in worker

**Files:**
- Modify: `api/services/theo_worker.py` (completion path after the quality gate)
- Modify: `pipeline/lyra/research_graph.py` (`mark_node_explored(paper_id)`)

- [ ] On completed batch runs where `quality_score.passed and audit.passed`: DB-level publish (no HTTP, no Discord role refresh): set `approved_by/approved_at` in result_json, `is_public=TRUE, published_at=NOW(), published_by='Theo', slug=<_make_slug + collision suffix>`, `published_report = report` (no section approvals exist), then `index_paper(...)` (same call as `api/routes/theo.py` publish) and `mark_node_explored(request_id)`. Gate failures: leave unpublished + POST the existing watchdog Discord webhook with paper id + failing metrics. The VPS host poller `scripts/auto_publish_batch.py` is retired at next deploy (kill PID; keep the file untracked). ruff, commit.

### Task 12: Verification + docs

- [ ] Run the full local test suite (`python -m pytest tests/ -x -q`), fix fallout, ruff format everything touched, update memory (`project-theo-low-priority-crawl.md` → graph-brain architecture note), final commit. Post-deploy checklist (for the owner, do NOT push autonomously): deploy → run backfill script → kill host poller → verify two-lane behavior with one UI run during a batch crawl.

---

## Self-review notes

- Spec coverage: B tables/writers/injectors/scoring/backfill → Tasks 1–6; A lanes/slots/feeder/saturation/auto-publish → Tasks 7–11; C explicitly out of scope. Open item "Theo author account" resolved as `published_by='Theo'` with owner user_id (no new account needed — display name only).
- Types: node/edge dict shape used by builder == column names in Task 1; `pick_next_frontier_topic` returns the keys the feeder consumes.
- Known risk: worker refactor (Task 9) changes live scheduling; mitigated by keeping `_run_with_stall_guard` and `_process_request` signatures untouched and by the live E2E after deploy.
