"""The dedup acceptance pairs from the design, run through the gates without SQL.

Every number here was measured on prod on 2026-09-14 (word_similarity,
token document frequencies, distances). The SQL nets produce Hit objects;
this exercises what happens to them next, which is where the two historical
incidents were decided:

  Great Zimbabwe   vs Great Ziggurat of Ur    -> dies at G1 (ZW/IQ) and G3 ({great} df 1959)
  Lake Van         vs Glastonbury Lake Village -> dies at G2 (>50 km) and G3 ({lake} df 472)
  Derinkuyu        vs Derinkuyu Underground City -> auto-skip (same name, same country, near)
  Meadowcroft Rockshelter vs Tham Lod Rockshelter -> passes G3 ({rockshelter} df 22) yet is
                                                     NOT auto-skipped: different name, US vs TH
"""

from pipeline.lyra.prospector.dedup import Candidate, Hit, _auto_skip, _gate
from pipeline.lyra.site_matcher import _is_same_name

DF = {
    "great": 1959,
    "lake": 472,
    "village": 2218,
    "underground": 77,
    "city": 1482,
    "derinkuyu": 6,
    "rockshelter": 22,
    "meadowcroft": 2,
    "tham": 40,
    "lod": 12,
    "zimbabwe": 5,
    "ziggurat": 58,
    "ur": 35,
    "van": 501,
    "glastonbury": 9,
    "of": 99999,
}


def hit(cand_name, site_name, site_country, distance_m, signal=0.6, rung="N1_trgm"):
    return Hit(
        rung=rung,
        site_id="x",
        site_name=site_name,
        site_country=site_country,
        source_id="ancient_nerds",
        distance_m=distance_m,
        signal=signal,
        same_name=_is_same_name(cand_name, site_name),
    )


def test_great_zimbabwe_dies_at_the_country_gate():
    c = Candidate(0, "Great Zimbabwe", country="Zimbabwe", lat=-20.27, lon=30.93)
    h = hit("Great Zimbabwe", "Great Ziggurat of Ur", "Iraq", distance_m=5_900_000, signal=0.533)
    _gate(h, c, DF)
    assert h.killed_by == "G1_country"
    assert not _auto_skip(h, c)


def test_great_zimbabwe_would_also_die_at_the_rare_token_gate():
    c = Candidate(0, "Great Zimbabwe", country=None, lat=None, lon=None)
    h = hit("Great Zimbabwe", "Great Ziggurat of Ur", None, distance_m=None, signal=0.533)
    _gate(h, c, DF)
    assert h.killed_by == "G3_rare_token"
    assert h.detail["shared_tokens"] == ["great"]


def test_lake_van_dies_at_the_distance_gate():
    c = Candidate(0, "Lake Van", country="Turkey", lat=38.6, lon=42.8)
    h = hit("Lake Van", "Glastonbury Lake Village", "England", distance_m=3_600_000, signal=0.667)
    _gate(h, c, DF)
    # Country differs too, and G1 runs first — both kill it.
    assert h.killed_by in ("G1_country", "G2_distance")
    c2 = Candidate(0, "Lake Van", country=None, lat=38.6, lon=42.8)
    h2 = hit("Lake Van", "Glastonbury Lake Village", None, distance_m=3_600_000, signal=0.667)
    _gate(h2, c2, DF)
    assert h2.killed_by == "G2_distance"


def test_lake_van_without_geography_dies_at_g3():
    c = Candidate(0, "Lake Van")
    h = hit("Lake Van", "Glastonbury Lake Village", None, distance_m=None, signal=0.667)
    _gate(h, c, DF)
    assert h.killed_by == "G3_rare_token"


def test_derinkuyu_is_auto_skipped():
    c = Candidate(0, "Derinkuyu", country="Turkey", lat=38.373, lon=34.734)
    h = hit("Derinkuyu", "Derinkuyu Underground City", "Türkiye", distance_m=120, signal=1.0)
    _gate(h, c, DF)
    assert h.killed_by is None
    assert h.same_name is True
    assert _auto_skip(h, c)


def test_meadowcroft_passes_g3_but_is_not_auto_skipped():
    c = Candidate(0, "Meadowcroft Rockshelter", country="United States", lat=40.29, lon=-80.49)
    h = hit(
        "Meadowcroft Rockshelter",
        "Tham Lod Rockshelter",
        "Thailand",
        distance_m=14_000_000,
        signal=0.5,
    )
    # Run only the token gate to prove the design's caveat: G3 alone is not a discriminator.
    c_no_geo = Candidate(0, "Meadowcroft Rockshelter")
    h_no_geo = hit("Meadowcroft Rockshelter", "Tham Lod Rockshelter", None, None, 0.5)
    _gate(h_no_geo, c_no_geo, DF)
    assert h_no_geo.killed_by is None  # {rockshelter} df 22 <= 300
    assert h_no_geo.same_name is False
    assert not _auto_skip(h_no_geo, c_no_geo)
    # With geography present, G1 kills it before anything else.
    _gate(h, c, DF)
    assert h.killed_by == "G1_country"


def test_auto_skip_requires_all_three_conditions():
    c = Candidate(0, "Derinkuyu", country="Turkey")
    far = hit("Derinkuyu", "Derinkuyu Underground City", "Türkiye", distance_m=900, signal=1.0)
    assert not _auto_skip(far, c)  # > 250 m: proximity is never identity in our data
    other_country = hit("Derinkuyu", "Derinkuyu Underground City", "Greece", distance_m=100)
    assert not _auto_skip(other_country, c)
    # Unknowns never confirm: with neither country nor distance known, a
    # same-name hit is a question for the human, not a silent skip.
    unknowns = hit("Derinkuyu", "Derinkuyu Underground City", None, distance_m=None)
    assert not _auto_skip(unknowns, c)
    country_only = hit("Derinkuyu", "Derinkuyu Underground City", "Türkiye", distance_m=None)
    assert _auto_skip(country_only, c)
    distance_only = hit("Derinkuyu", "Derinkuyu Underground City", None, distance_m=90)
    assert _auto_skip(distance_only, Candidate(0, "Derinkuyu"))


def test_generic_curated_name_cannot_swallow_a_specific_candidate():
    # First full run: "Funerary Temple" absorbed "Khafre's funerary temple".
    c = Candidate(0, "Khafre's funerary temple")
    h = hit("Khafre's funerary temple", "Funerary Temple", None, distance_m=None, signal=0.6)
    assert h.same_name  # containment says yes ...
    assert not _auto_skip(h, c)  # ... but nothing physical confirms it


def test_proximity_alone_is_context_not_identity():
    # KV62 sits 574 m from Deir el-Bahari: a neighbour, not the same site.
    c = Candidate(0, "KV62", country="Egypt", lat=25.7402, lon=32.6014)
    h = hit("KV62", "Deir el-Bahari", "Egypt", distance_m=574, signal=574, rung="N3_geo")
    _gate(h, c, DF)
    assert h.killed_by == "G3_rare_token"
    assert not _auto_skip(h, c)


def test_levenshtein_net_survives_g3_without_a_rare_token():
    # Osirion / Osireion share no whole token ("osirion" != "osireion") but are 1 edit apart.
    c = Candidate(0, "Osireion", country="Egypt")
    h = hit("Osireion", "Osirion", "Egypt", distance_m=40, signal=1.0, rung="N2_lev")
    _gate(h, c, DF)
    assert h.killed_by is None
