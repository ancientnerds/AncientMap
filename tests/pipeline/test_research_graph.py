"""Tests for the research knowledge-graph builder (pure functions, no DB)."""

from pipeline.lyra.research_graph import build_graph_from_state, normalize_label


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
