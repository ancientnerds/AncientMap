"""GraphNode carries the thinking-layer fields (spec §7)."""

from api.schemas.public_v1 import GraphNode


def test_graphnode_thinking_fields_default_none():
    n = GraphNode(id="x", label="L", kind="hypothesis", status="frontier", signal=0.0, degree=0)
    assert n.question is None
    assert n.outcome is None


def test_graphnode_accepts_thinking_values():
    n = GraphNode(
        id="x",
        label="L",
        kind="hypothesis",
        status="explored",
        signal=2.0,
        degree=1,
        question="Does A explain B?",
        outcome="refuted",
    )
    assert n.outcome == "refuted"
