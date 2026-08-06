"""Tests for the research knowledge-graph builder (pure functions, no DB)."""

from pipeline.lyra.research_graph import (
    build_graph_from_state,
    is_junk_label,
    normalize_label,
    persist_graph,
    reset_node_for_failed_request,
)


class _FakeGraphSession:
    """Captures executed statement/params pairs; supports the `with
    get_session() as session:` context-manager usage (see
    tests/pipeline/test_thinking_log.py's _FakeSession for the pattern)."""

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


class FakeAngle:
    def __init__(self, id, topic, spawned_from=None, rabbit_holes=None):
        self.id = id
        self.topic = topic
        self.spawned_from = spawned_from
        self.rabbit_holes = rabbit_holes or []


class FakeState:
    def __init__(self):
        self.question = "How do cyclical world ages appear across mythologies?"
        self.paper_title = "Cyclical World Ages"
        self.angles = [
            FakeAngle("a1", "Canonical sources", rabbit_holes=["Lurianic Kabbalah"]),
            # Spawned angle: its topic was a rabbit hole that WAS explored.
            FakeAngle("a2", "Lurianic Kabbalah", spawned_from="a1"),
            FakeAngle(
                "a3",
                "Destruction typology",
                rabbit_holes=["Stoic ekpyrosis", "Lurianic Kabbalah"],
            ),
        ]


def test_normalize_label():
    assert normalize_label("  The  Kybalion! ") == "the kybalion"
    assert normalize_label("Ein-Sof (Kabbalah)") == "ein-sof kabbalah"


def test_is_junk_label_rejects_whitespace_and_punctuation_only():
    # "   " and "..." both normalize to "" — not in JUNK_LABELS, so they
    # slipped through before the M14 fix (2026-08-05 review).
    assert is_junk_label("   ") is True
    assert is_junk_label("...") is True
    assert is_junk_label("null") is True
    assert is_junk_label(None) is True
    assert is_junk_label("Ein Sof") is False


def test_builder_emits_paper_node():
    nodes, _edges = build_graph_from_state(FakeState(), "req-123")
    papers = [n for n in nodes if n["kind"] == "paper"]
    assert len(papers) == 1
    assert papers[0]["label"] == "Cyclical World Ages"
    assert papers[0]["status"] == "explored"


def test_explored_rabbit_hole_is_not_frontier():
    """A rabbit hole that spawned an angle was researched in this paper —
    it must surface as an explored topic, not as frontier."""
    nodes, _edges = build_graph_from_state(FakeState(), "req-123")
    by_label = {n["norm_label"]: n for n in nodes if n["kind"] == "topic"}
    assert by_label["lurianic kabbalah"]["status"] == "explored"
    assert by_label["stoic ekpyrosis"]["status"] == "frontier"


def test_leads_to_edges_from_paper_to_topics():
    nodes, edges = build_graph_from_state(FakeState(), "req-123")
    paper = next(n for n in nodes if n["kind"] == "paper")
    leads = [e for e in edges if e["kind"] == "leads_to"]
    assert leads, "expected leads_to edges"
    assert all(e["src_norm"] == paper["norm_label"] for e in leads)
    # Duplicate rabbit hole across angles must not produce duplicate edges
    dsts = [e["dst_norm"] for e in leads]
    assert len(dsts) == len(set(dsts))


def test_builder_stamps_request_id_only_on_paper_node():
    # Audit P15: stamping every node gave frontier rabbit holes the creating
    # run's paper_id, so _pick_frontier's 24h failure cooldown (keyed on
    # paper_id -> research_requests) blocked ALL topics a run surfaced when
    # that run later failed. Only the paper node may carry the run id;
    # topics get theirs via link_node_to_request when actually researched.
    nodes, _edges = build_graph_from_state(FakeState(), "req-123")
    for n in nodes:
        if n["kind"] == "paper":
            assert n["request_id"] == "req-123"
        else:
            assert n["request_id"] == ""


def test_builder_edges_carry_endpoint_kinds():
    # Audit P14: persist_graph resolves endpoints by exact (kind, norm) when
    # the edge says which kind each side is — the builder must emit them.
    _nodes, edges = build_graph_from_state(FakeState(), "req-123")
    assert edges
    for e in edges:
        assert e["src_kind"] == "paper"
        assert e["dst_kind"] == "topic"


class _FakePersistSession:
    """Node INSERT ... RETURNING gets sequential ids (id-1, id-2, ...);
    every stmt/params pair is recorded. Edge inserts don't call fetchone."""

    def __init__(self):
        self.executed = []
        self.committed = False
        self._next_id = 0

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        sess = self

        class _R:
            def fetchone(self):
                sess._next_id += 1
                return type("Row", (), {"id": f"id-{sess._next_id}"})()

        return _R()

    def commit(self):
        self.committed = True


def _persist_nodes():
    """A paper and a topic sharing the same norm_label, plus a second topic.
    Insert order fixes the fake ids: paper=id-1, topic(atlantis)=id-2,
    topic(ekpyrosis)=id-3."""
    return [
        {
            "label": "Atlantis",
            "norm_label": "atlantis",
            "kind": "paper",
            "status": "explored",
            "created_from": "paper",
            "request_id": "req-1",
        },
        {
            "label": "Atlantis",
            "norm_label": "atlantis",
            "kind": "topic",
            "status": "frontier",
            "created_from": "rabbit_hole",
            "request_id": "",
        },
        {
            "label": "Ekpyrosis",
            "norm_label": "ekpyrosis",
            "kind": "topic",
            "status": "frontier",
            "created_from": "rabbit_hole",
            "request_id": "",
        },
    ]


def test_persist_graph_resolves_edge_endpoints_by_kind_and_norm():
    # Audit P14: with a paper and a topic sharing a norm_label, the old
    # norm-only lookup (kind order topic > paper) resolved the PAPER side of
    # an edge to the topic's id. Kind-qualified edges must hit exactly.
    session = _FakePersistSession()
    edges = [
        {
            "src_norm": "atlantis",
            "dst_norm": "atlantis",
            "kind": "leads_to",
            "src_kind": "paper",
            "dst_kind": "topic",
        }
    ]
    persist_graph(_persist_nodes(), edges, session)
    edge_inserts = [(s, p) for s, p in session.executed if "INSERT INTO research_edges" in s]
    assert len(edge_inserts) == 1
    _, params = edge_inserts[0]
    assert params["src"] == "id-1"  # the paper node, not the same-norm topic
    assert params["dst"] == "id-2"
    assert session.committed


def test_persist_graph_norm_only_fallback_for_kindless_edges():
    # scripts/backfill_research_graph.py builds bare src_norm/dst_norm edges
    # — the ordered fallback (topic > paper > entity > person) must survive
    # for that caller, unchanged.
    session = _FakePersistSession()
    edges = [{"src_norm": "atlantis", "dst_norm": "ekpyrosis", "kind": "related"}]
    persist_graph(_persist_nodes(), edges, session)
    edge_inserts = [(s, p) for s, p in session.executed if "INSERT INTO research_edges" in s]
    assert len(edge_inserts) == 1
    _, params = edge_inserts[0]
    assert params["src"] == "id-2"  # topic wins over paper in the fallback order
    assert params["dst"] == "id-3"


def test_persist_graph_drops_edges_with_unresolvable_endpoints():
    session = _FakePersistSession()
    edges = [
        {
            "src_norm": "atlantis",
            "dst_norm": "missing topic",
            "kind": "leads_to",
            "src_kind": "paper",
            "dst_kind": "topic",
        }
    ]
    persist_graph(_persist_nodes(), edges, session)
    edge_inserts = [(s, p) for s, p in session.executed if "INSERT INTO research_edges" in s]
    assert edge_inserts == []


def test_epoch_for_year_buckets():
    from pipeline.lyra.graph_full_ingest import epoch_for_year

    assert epoch_for_year(-9600) == "< 4500 BC"
    assert epoch_for_year(-3000) == "3000 - 1500 BC"
    assert epoch_for_year(0) == "500 BC - 1 AD"
    assert epoch_for_year(800) == "500 - 1000 AD"
    assert epoch_for_year(1900) == "1500+ AD"
    assert epoch_for_year(None) is None


def test_reset_node_for_failed_request_resets_frontier(monkeypatch):
    fake = _FakeGraphSession()
    import pipeline.database as database_module

    monkeypatch.setattr(database_module, "get_session", lambda: fake)
    reset_node_for_failed_request("req-1")
    assert fake.committed
    stmt, params = fake.executed[0]
    assert "UPDATE research_nodes" in stmt
    assert "SET status = 'frontier'" in stmt
    assert "WHERE paper_id = CAST(:rid AS uuid) AND status = 'researching'" in stmt
    assert params["rid"] == "req-1"


def test_reset_node_for_failed_request_never_raises(monkeypatch):
    import pipeline.database as database_module

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(database_module, "get_session", boom)
    reset_node_for_failed_request("req-1")  # must not raise


def test_entity_mention_threshold():
    from pipeline.lyra.graph_full_ingest import entity_mention_counts

    counts = entity_mention_counts(
        [
            ["Randall Carlson", "One-Off Guy"],
            ["Randall  Carlson!"],  # normalizes to the same key
            ["Someone Else"],
        ]
    )
    assert counts["randall carlson"] == 2
    assert counts["one-off guy"] == 1
    # duplicate within ONE story counts once
    dup = entity_mention_counts([["Plato", "Plato"]])
    assert dup["plato"] == 1
