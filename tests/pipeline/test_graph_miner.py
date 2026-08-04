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
