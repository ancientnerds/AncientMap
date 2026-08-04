"""Graph miner — structural connection candidates (spec §2).

Redesigned after prod-evidence review (2026-08-04): the original miners
returned 0 rows against the live graph (13,148 nodes / 21,583 edges) because
explored `topic` nodes only ever neighbor `paper` nodes, `site` nodes never
carry status='explored', and no explored node carries site_id. The fix
bridges an explored `topic` node to its structural `site` twin via a shared
`norm_label` (78 such cross-kind labels exist in prod) — see graph_miner.py
docstrings on mine_link_prediction / mine_spatial_cooccurrence for the SQL.
"""

from types import SimpleNamespace

import pipeline.lyra.graph_miner as gm
from pipeline.lyra.graph_miner import merge_candidates
from pipeline.lyra.research_graph import normalize_label


def _link(a="Göbekli Tepe", b="Karahan Tepe", shared=3, via=("Pre-Pottery Neolithic",)):
    return SimpleNamespace(a_label=a, b_label=b, shared=shared, via=list(via))


def _spatial(a="Nan Madol", b="Leluh", km=45):
    return SimpleNamespace(a_label=a, b_label=b, km=km)


def _tension(claim_text="Dating of X is disputed across papers", node_label="Site X"):
    return SimpleNamespace(claim_text=claim_text, node_label=node_label)


class _FakeMinerSession:
    """Context-manager session whose .execute().fetchall() is configurable."""

    def __init__(self, connection_norm_rows=None):
        self._connection_norm_rows = connection_norm_rows or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        rows = self._connection_norm_rows

        class _R:
            def fetchall(inner):
                return rows

        return _R()


# ---------------------------------------------------------------------------
# merge_candidates — pure function
# ---------------------------------------------------------------------------


def test_merge_applies_per_miner_quota_before_global_cap():
    # 20 link candidates would swamp cap=15 alone under naive concatenation,
    # crowding out spatial/tension entirely. Per-miner quotas (7/5/3)
    # guarantee minority miners survive even a small global cap.
    links = [_link(a=f"T{i}", b=f"U{i}", shared=20 - i) for i in range(20)]
    spatial = [_spatial()]
    tension = [_tension()]
    out = merge_candidates(links, spatial, tension, cap=15)
    kinds = [c["miner"] for c in out]
    assert kinds.count("link") == 7
    assert kinds.count("spatial") == 1
    assert kinds.count("tension") == 1
    link_items = [c for c in out if c["miner"] == "link"]
    assert link_items[0]["label"] == "T0 ↔ U0"  # strongest (shared=20) first
    assert "20 shared" in link_items[0]["evidence"]


def test_merge_formats_spatial_evidence():
    out = merge_candidates([], [_spatial()], cap=10)
    assert out[0]["miner"] == "spatial"
    assert out[0]["label"] == "Nan Madol ↔ Leluh"
    assert "45 km" in out[0]["evidence"]


def test_merge_skips_self_pairs():
    out = merge_candidates([_link(a="X", b="X")], [], cap=10)
    assert out == []


def test_merge_includes_contested_claim_tensions():
    out = merge_candidates([], [], [_tension()], cap=10)
    assert out[0]["miner"] == "tension"
    assert out[0]["label"] == "Site X"
    assert "contested" in out[0]["evidence"]


def test_merge_cross_miner_dedup():
    # Same pair surfaced by both link and spatial miners (either ordering)
    # must appear once — link wins because it is merged first.
    link = _link(a="A", b="B", shared=5)
    spatial_same_pair_reversed = _spatial(a="B", b="A", km=10)
    out = merge_candidates([link], [spatial_same_pair_reversed], cap=10)
    assert len(out) == 1
    assert out[0]["miner"] == "link"
    assert out[0]["label"] == "A ↔ B"


def test_merge_suppresses_existing_connections():
    # A pair already promoted to a `connection` node must not resurface,
    # regardless of which ordering the miner happens to emit.
    existing = {normalize_label("A ↔ B")}
    forward = merge_candidates(
        [_link(a="A", b="B", shared=5)], [], cap=10, existing_connection_norms=existing
    )
    reversed_order = merge_candidates(
        [_link(a="B", b="A", shared=5)], [], cap=10, existing_connection_norms=existing
    )
    assert forward == []
    assert reversed_order == []


# ---------------------------------------------------------------------------
# run_miner — wiring + best-effort behavior
# ---------------------------------------------------------------------------


def test_run_miner_wiring(monkeypatch):
    calls = {}

    def fake_link(session, limit=20):
        return ["L"]

    def fake_spatial(session, max_km=200, limit=20):
        return ["S"]

    def fake_tension(session, limit=10):
        return ["T"]

    def fake_merge(
        link_rows, spatial_rows, tension_rows=None, cap=15, existing_connection_norms=frozenset()
    ):
        calls["args"] = (link_rows, spatial_rows, tension_rows)
        calls["existing"] = existing_connection_norms
        return [{"label": "X", "miner": "link", "evidence": "e"}]

    logged = {}

    def fake_log_thinking(kind, summary, details):
        logged["kind"] = kind
        logged["summary"] = summary
        logged["details"] = details

    monkeypatch.setattr(gm, "mine_link_prediction", fake_link)
    monkeypatch.setattr(gm, "mine_spatial_cooccurrence", fake_spatial)
    monkeypatch.setattr(gm, "mine_contested_claims", fake_tension)
    monkeypatch.setattr(gm, "merge_candidates", fake_merge)
    monkeypatch.setattr(
        "pipeline.database.get_session",
        lambda: _FakeMinerSession(connection_norm_rows=[SimpleNamespace(norm_label="a b")]),
    )
    monkeypatch.setattr("pipeline.lyra.thinking_log.log_thinking", fake_log_thinking)

    out = gm.run_miner()

    assert out == [{"label": "X", "miner": "link", "evidence": "e"}]
    # tensions land in the third positional slot of merge_candidates.
    assert calls["args"] == (["L"], ["S"], ["T"])
    assert calls["existing"] == {"a b"}
    assert logged["kind"] == "miner"
    assert "1 link" in logged["summary"]
    assert "1 spatial" in logged["summary"]
    assert "1 tension" in logged["summary"]


def test_run_miner_swallows_exceptions(monkeypatch, caplog):
    def boom(session, limit=20):
        raise RuntimeError("db down")

    monkeypatch.setattr(gm, "mine_link_prediction", boom)
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeMinerSession())

    with caplog.at_level("ERROR"):
        out = gm.run_miner()

    assert out == []
    assert any("miner failed" in r.message for r in caplog.records)
