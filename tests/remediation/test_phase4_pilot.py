"""Is the Phase-4 pilot drawn the way the design says, from the census's lanes, and nobody's choice?

`phase4/pilot4.py` (the pilot of 2026-09-24): the fixed members resolved from the design's id
prefixes and names, the seeded draws per stratum (lanes W and S from the census; the T and R
candidates the routes stage held for a search that is switched off; B3 from the routeless read;
extracts over 40,000 characters), the census read from a run directory, the forbidden anchors of
`gold_prose_errors.json` and the verbatim threshold blocks. No socket, database or model is touched:
the production read goes through a recording runner. Pilot 2 (seed 20260924): pilot 1's fixed members
kept, its draws excluded, its sealed thresholds unchanged. Pilot 3 (seed 20260925): the same fixed
members, the draws of pilots 1 and 2 excluded, the thresholds still pilot 1's. The mutation cases are
`P4_PILOT_MUTATIONS`, `P4_PILOT2_MUTATIONS` and `P4_PILOT3_MUTATIONS` in
`scripts/remediation/phase3/mutation_sweep.py` (label `p4 pilot: `).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

from phase3 import run as R  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import pilot4 as PL  # noqa: E402
from phase4 import route_stage as RS  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402

GOLD_FILE = REPO / "output" / "remediation" / "gold_standard" / "sites.json"
REMEDIATION_PLAN = REPO / "docs" / "procedures" / "SITES_DB_REMEDIATION_2026-09.md"
STOPPED = (M.HoldReason.SEARCH_STOPPED.value,)


def sid(prefix: str, n: int = 1) -> str:
    return f"{prefix}-0000-4000-8000-{n:012d}"


def site(site_id: str, name: str = "Stone Temple", **over: Any) -> M.PlanSite:
    return dataclasses.replace(X.plan_site(site_id, name=name), **over)


def facts(
    lane: M.Lane = M.Lane.W, holds: tuple[str, ...] = (), chars: int | None = 100
) -> PL.Census:
    if lane not in (M.Lane.W, M.Lane.S, M.Lane.T):
        chars = None
    return PL.Census(batch_id="p4-0001", lane=lane, holds=holds, extract_chars=chars)


def named_sites() -> dict[str, M.PlanSite]:
    """One curated site for every member the design names, and the 7 Q309 sites."""
    sites: dict[str, M.PlanSite] = {}
    for named in (*PL.CANARIES, *PL.B5_FIXTURES, *PL.IDENTITY_TRAPS, *PL.SPECIAL):
        site_id = sid(named.prefix)
        sites[site_id] = site(site_id, named.name or "Abri de la Madeleine")
    for n in range(1, 8):
        site_id = sid("0e0e0e0e", n)
        sites[site_id] = site(site_id, f"Q309 site {n}")
    for title, n in (("Theatre", 1), ("Mortuary temple", 2), ("Mortuary temple", 3)):
        site_id = sid("0f0f0f0f", n)
        sites[site_id] = site(site_id, f"Trap {n}", enwiki_title=title)
    return sites


Q309 = [sid("0e0e0e0e", n) for n in range(1, 8)]


def build(
    sites: Mapping[str, M.PlanSite],
    census: Mapping[str, PL.Census],
    *,
    gold: list[str] | None = None,
    routeless: set[str] | None = None,
    seed: int = PL.SEED,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return PL.build_pilot(
        sites, census, gold=gold or [], q309=Q309, routeless=routeless or set(), seed=seed
    )


def with_facts(sites: Mapping[str, M.PlanSite]) -> dict[str, PL.Census]:
    return {site_id: facts(M.Lane.ZERO, ("scope-pending",)) for site_id in sites}


def drawn(lines: list[dict[str, Any]], stratum: str) -> list[str]:
    return [line["site_id"] for line in lines if stratum in line["strata"]]


# ========================================================================= the fixed members


def test_the_fixed_members_come_first_in_the_designs_order() -> None:
    sites = named_sites()
    gold = [sid("0a0a0a0a", n) for n in (2, 1)]
    for site_id in gold:
        sites[site_id] = site(site_id, "Gold site")
    lines, summary = build(sites, with_facts(sites), gold=gold)

    order = [line["site_id"] for line in lines]
    expected = [
        *gold,
        *(sid(n.prefix) for n in (*PL.CANARIES, *PL.B5_FIXTURES, *PL.IDENTITY_TRAPS)),
        *Q309,
        sid("0f0f0f0f", 1),  # Theatre
        sid("0f0f0f0f", 2),
        sid("0f0f0f0f", 3),  # Mortuary temple
        *(sid(n.prefix) for n in PL.SPECIAL),
    ]
    assert order == expected
    assert summary["fixed"] == len(expected) and summary["sites"] == len(expected)
    by_id = {line["site_id"]: line for line in lines}
    assert by_id[sid("2968fd35")]["strata"] == ["canary"]
    assert by_id[sid("0f0f0f0f", 1)]["strata"] == ["identity-trap-theatre"]


def test_a_site_named_twice_is_one_line_with_both_strata() -> None:
    sites = named_sites()
    arc = sid("82f23c96")
    lines, _ = build(sites, with_facts(sites), gold=[arc])
    (line,) = [line for line in lines if line["site_id"] == arc]
    assert line["strata"] == ["gold-standard", "b5-fixture"]
    assert [line["site_id"] for line in lines].count(arc) == 1


def test_a_named_site_must_carry_the_designs_name() -> None:
    sites = named_sites()
    wrong = sid("411cacb0")
    sites[wrong] = site(wrong, "Kit Hill Country Park")  # the design's name is still in it
    PL.resolve(PL.CANARIES[1], sites)
    for other in ("Kithill", "Kit Hillside"):  # the name's words, whole
        sites[wrong] = site(wrong, other)
        with pytest.raises(R.InputError, match="not the design's 'Kit Hill'"):
            PL.resolve(PL.CANARIES[1], sites)


def test_an_alias_carrying_the_designs_name_is_enough() -> None:
    sites = named_sites()
    faun = sid("5752ff6c")
    sites[faun] = site(faun, "Casa del Fauno", aliases=("House of the Faun, Pompeii",))
    assert PL.resolve(PL.IDENTITY_TRAPS[-1], sites) == faun


def test_a_prefix_that_names_no_site_or_two_is_refused() -> None:
    sites = named_sites()
    del sites[sid("dae9bc10")]
    with pytest.raises(R.InputError, match="names 0 curated sites"):
        PL.resolve(PL.SPECIAL[1], sites)
    sites = named_sites()
    sites[sid("dae9bc10", 2)] = site(sid("dae9bc10", 2), "Wroxeter Stone")
    with pytest.raises(R.InputError, match="names 2 curated sites"):
        PL.resolve(PL.SPECIAL[1], sites)


def test_the_q309_traps_are_the_repairs_old_links_and_what_the_export_still_shows() -> None:
    sites = named_sites()
    repair = [
        {"kind": "wikidata_qid", "old_value": "Q309", "site_id": site_id} for site_id in Q309[:5]
    ]
    repair.append({"kind": "enwiki_title", "old_value": "History", "site_id": Q309[0]})
    sites[Q309[5]] = site(Q309[5], "Crantit", wikidata_qid="Q309")
    sites[Q309[6]] = site(Q309[6], "Estipeon", enwiki_title="History")
    assert PL.q309_sites(repair, sites) == sorted(Q309)


def test_any_other_count_of_q309_sites_than_the_designs_seven_is_refused() -> None:
    sites = named_sites()
    repair = [
        {"kind": "wikidata_qid", "old_value": "Q309", "site_id": site_id} for site_id in Q309[:6]
    ]
    with pytest.raises(R.InputError, match="7 sites"):
        PL.q309_sites(repair, sites)


# ============================================================================ the seeded draws


def census_of(
    sites: dict[str, M.PlanSite], extra: Mapping[str, tuple[M.PlanSite, PL.Census]]
) -> dict[str, PL.Census]:
    census = with_facts(sites)
    for site_id, (plan_site, fact) in extra.items():
        sites[site_id] = plan_site
        census[site_id] = fact
    return census


def lane_sites(prefix: str, count: int, lane: M.Lane) -> dict[str, tuple[M.PlanSite, PL.Census]]:
    return {
        sid(prefix, n): (site(sid(prefix, n), f"{lane.value} site {n}"), facts(lane))
        for n in range(1, count + 1)
    }


def test_the_lane_draws_take_the_census_lanes_and_are_seeded() -> None:
    sites = named_sites()
    census = census_of(
        sites, {**lane_sites("0b0b0b0b", 50, M.Lane.W), **lane_sites("0c0c0c0c", 12, M.Lane.S)}
    )
    lines, summary = build(sites, census)
    again, _ = build(sites, census)

    assert lines == again  # nobody's choice: the seed decides
    w, s = drawn(lines, PL.DRAW_W), drawn(lines, PL.DRAW_S)
    pool = sorted(sid("0b0b0b0b", n) for n in range(1, 51))
    assert w == sorted(random.Random(PL.SEED).sample(pool, 30))  # noqa: S311 - the seeded draw
    assert len(w) == 30 and all(census[x].lane is M.Lane.W for x in w)
    assert len(s) == 8 and all(census[x].lane is M.Lane.S for x in s)
    assert summary["draws"][PL.DRAW_W] == {
        "asked": 30,
        "population": 50,
        "eligible": 50,
        "taken": 30,
    }
    other, _ = build(sites, census, seed=PL.SEED + 1)
    assert drawn(other, PL.DRAW_W) != w


def test_a_stratum_with_fewer_sites_is_taken_whole() -> None:
    sites = named_sites()
    census = census_of(sites, lane_sites("0c0c0c0c", 3, M.Lane.S))
    lines, summary = build(sites, census)
    assert drawn(lines, PL.DRAW_S) == sorted(sid("0c0c0c0c", n) for n in (1, 2, 3))
    assert summary["draws"][PL.DRAW_S]["taken"] == 3


def test_a_draw_never_takes_a_site_placed_before_it() -> None:
    """A fixed member (or an earlier stratum's site) is not drawn again: every stratum excludes
    everything placed before it, so the pilot is its members once each."""
    sites = named_sites()
    census = census_of(sites, lane_sites("0b0b0b0b", 30, M.Lane.W))
    gold = [sid("0b0b0b0b", n) for n in range(1, 6)]  # 5 lane-W sites are gold
    lines, summary = build(sites, census, gold=gold)
    w = drawn(lines, PL.DRAW_W)
    assert not set(w) & set(gold) and len(w) == 25
    assert summary["draws"][PL.DRAW_W]["eligible"] == 25


# ================================================================ pilot 2: a fresh draw (2026-09-24)


def fixed_lines(lines: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    return [
        (line["site_id"], line["strata"])
        for line in lines
        if not set(line["strata"]) & {stratum for stratum, _ in PL.DRAWS}
    ]


def test_pilot_2_keeps_pilot_1s_fixed_members_and_draws_anew_without_its_draws() -> None:
    """The design's failure rule: "re-pilot on a fresh draw of the same strata". The fixed members
    are exactly pilot 1's; every stratum is drawn with pilot 2's seed, pilot 1's draws excluded."""
    sites = named_sites()
    census = census_of(
        sites, {**lane_sites("0b0b0b0b", 80, M.Lane.W), **lane_sites("0c0c0c0c", 12, M.Lane.S)}
    )
    first, _ = build(sites, census)
    second, summary = PL.build_pilot(
        sites, census, gold=[], q309=Q309, routeless=set(), seed=PL.SEED_PILOT2, earlier=[first]
    )

    assert PL.SEED_PILOT2 == 20260924
    assert (
        fixed_lines(second) == fixed_lines(first)
        and second[: summary["fixed"]] == first[: summary["fixed"]]
    )
    w1, w2 = drawn(first, PL.DRAW_W), drawn(second, PL.DRAW_W)
    eligible = sorted({sid("0b0b0b0b", n) for n in range(1, 81)} - set(w1))
    assert w2 == sorted(random.Random(PL.SEED_PILOT2).sample(eligible, 30))  # noqa: S311
    assert summary["draws"][PL.DRAW_W] == {
        "asked": 30,
        "population": 80,
        "eligible": 50,
        "taken": 30,
    }
    # a stratum pilot 1 nearly used up is taken whole: 12 lane-S sites, 8 drawn before
    assert drawn(second, PL.DRAW_S) == sorted(
        {sid("0c0c0c0c", n) for n in range(1, 13)} - set(drawn(first, PL.DRAW_S))
    )
    assert summary["earlier_draws_excluded"] == 38


def test_pilot_2_refuses_fixed_members_that_are_not_pilot_1s() -> None:
    sites = named_sites()
    census = census_of(sites, lane_sites("0b0b0b0b", 40, M.Lane.W))
    first, _ = build(sites, census)
    for earlier in (first[1:], [first[1], first[0], *first[2:]]):
        with pytest.raises(R.InputError, match="not the earlier pilot's"):
            PL.build_pilot(
                sites, census, gold=[], q309=Q309, routeless=set(), seed=1, earlier=[earlier]
            )


def test_pilot_3_keeps_the_fixed_members_and_excludes_both_earlier_pilots_draws() -> None:
    """Pilot 2 failed too (T3, T4, T6, T8): pilot 3 is a fresh draw of the same strata with its own
    seed, the fixed members exactly pilots 1's and 2's, and none of either pilot's draws."""
    sites = named_sites()
    census = census_of(
        sites, {**lane_sites("0b0b0b0b", 100, M.Lane.W), **lane_sites("0c0c0c0c", 20, M.Lane.S)}
    )
    first, _ = build(sites, census)
    kwargs: dict[str, Any] = {"gold": [], "q309": Q309, "routeless": set()}
    second, _ = PL.build_pilot(sites, census, seed=PL.SEED_PILOT2, earlier=[first], **kwargs)
    third, summary = PL.build_pilot(
        sites, census, seed=PL.SEED_PILOT3, earlier=[first, second], **kwargs
    )

    assert PL.SEED_PILOT3 == 20260925
    assert third[: summary["fixed"]] == first[: summary["fixed"]] == second[: summary["fixed"]]
    before = set(drawn(first, PL.DRAW_W)) | set(drawn(second, PL.DRAW_W))
    eligible = sorted({sid("0b0b0b0b", n) for n in range(1, 101)} - before)
    w3 = drawn(third, PL.DRAW_W)
    assert w3 == sorted(random.Random(PL.SEED_PILOT3).sample(eligible, 30))  # noqa: S311
    assert summary["draws"][PL.DRAW_W]["eligible"] == 40
    # 20 lane-S sites, 16 drawn by the two earlier pilots: the stratum is taken whole
    assert drawn(third, PL.DRAW_S) == sorted(
        {sid("0c0c0c0c", n) for n in range(1, 21)}
        - set(drawn(first, PL.DRAW_S))
        - set(drawn(second, PL.DRAW_S))
    )
    assert summary["earlier_draws_excluded"] == 76


def test_pilot_3_refuses_an_earlier_pilot_whose_fixed_members_differ() -> None:
    """Every earlier pilot is checked, not only the first: a second whose fixed lines moved is
    refused, since the pilots would no longer share one fixed set."""
    sites = named_sites()
    census = census_of(sites, lane_sites("0b0b0b0b", 90, M.Lane.W))
    first, _ = build(sites, census)
    kwargs: dict[str, Any] = {"gold": [], "q309": Q309, "routeless": set()}
    second, _ = PL.build_pilot(sites, census, seed=PL.SEED_PILOT2, earlier=[first], **kwargs)
    moved = [second[1], second[0], *second[2:]]
    with pytest.raises(R.InputError, match="not the earlier pilot's"):
        PL.build_pilot(sites, census, seed=PL.SEED_PILOT3, earlier=[first, moved], **kwargs)


def test_pilot_4_keeps_the_fixed_members_and_excludes_all_three_earlier_pilots_draws() -> None:
    """Pilot 3 failed T1, T4, T7 and T8: pilot 4 is a fresh draw of the same strata with its own
    seed, the fixed members exactly the three earlier pilots', and none of their draws; a stratum
    the earlier pilots nearly used up is taken whole."""
    sites = named_sites()
    census = census_of(
        sites, {**lane_sites("0b0b0b0b", 130, M.Lane.W), **lane_sites("0c0c0c0c", 30, M.Lane.S)}
    )
    first, _ = build(sites, census)
    kwargs: dict[str, Any] = {"gold": [], "q309": Q309, "routeless": set()}
    second, _ = PL.build_pilot(sites, census, seed=PL.SEED_PILOT2, earlier=[first], **kwargs)
    third, _ = PL.build_pilot(sites, census, seed=PL.SEED_PILOT3, earlier=[first, second], **kwargs)
    fourth, summary = PL.build_pilot(
        sites, census, seed=PL.SEED_PILOT4, earlier=[first, second, third], **kwargs
    )

    assert PL.SEED_PILOT4 == 20260926
    fixed = summary["fixed"]
    assert fourth[:fixed] == first[:fixed] == second[:fixed] == third[:fixed]
    before = {s for pilot in (first, second, third) for s in drawn(pilot, PL.DRAW_W)}
    eligible = sorted({sid("0b0b0b0b", n) for n in range(1, 131)} - before)
    assert drawn(fourth, PL.DRAW_W) == sorted(
        random.Random(PL.SEED_PILOT4).sample(eligible, 30)  # noqa: S311
    )
    assert summary["draws"][PL.DRAW_W]["eligible"] == 40
    # 30 lane-S sites, 24 drawn by the three earlier pilots: the stratum is taken whole
    taken = {s for pilot in (first, second, third) for s in drawn(pilot, PL.DRAW_S)}
    assert drawn(fourth, PL.DRAW_S) == sorted({sid("0c0c0c0c", n) for n in range(1, 31)} - taken)
    assert summary["earlier_draws_excluded"] == 114


def test_an_earlier_line_that_is_neither_fixed_nor_one_draw_is_refused() -> None:
    mixed = {"site_id": sid("0b0b0b0b"), "strata": ["gold-standard", PL.DRAW_W]}
    with pytest.raises(R.InputError, match="neither fixed nor one draw"):
        PL.earlier_pilot([mixed])
    two = {"site_id": sid("0b0b0b0b"), "strata": [PL.DRAW_W, PL.DRAW_S]}
    with pytest.raises(R.InputError, match="neither fixed nor one draw"):
        PL.earlier_pilot([two])


def _held(site_id: str, source_url: str | None, holds: tuple[str, ...] = STOPPED) -> tuple:
    plan_site = site(site_id, "Held site", enwiki_title=None, source_url=source_url)
    return plan_site, facts(M.Lane.ZERO, holds)


def test_a_t_candidate_waits_on_its_search_and_names_an_other_language_article() -> None:
    fr = "https://fr.wikipedia.org/wiki/Tour_de_Pise"
    candidate, other_census = _held(sid("0d0d0d0d", 1), fr)
    assert PL.is_t_candidate(candidate, other_census)
    english, fact = _held(sid("0d0d0d0d", 2), "https://en.wikipedia.org/wiki/Stone_Temple")
    assert not PL.is_t_candidate(english, fact)
    held_otherwise, fact = _held(sid("0d0d0d0d", 3), fr, ("fetch-failed",))
    assert not PL.is_t_candidate(held_otherwise, fact)
    two, fact = _held(sid("0d0d0d0d", 4), "https://example.org/x\n" + fr)
    assert PL.is_t_candidate(two, fact)


def test_an_r_candidate_waits_on_its_search_with_only_non_wiki_web_pages() -> None:
    web = "https://www.megalithic.co.uk/article.php?sid=1"
    candidate, fact = _held(sid("0d0d0d0d", 1), web)
    assert PL.is_r_candidate(candidate, fact)
    for url in (
        "https://fr.wikipedia.org/wiki/X",  # an article: the T route
        "https://simple.wikipedia.org/wiki/X",  # no article route, but a wiki host
        "https://www.wikidata.org/wiki/Q1",
        "www.megalithic.co.uk/article.php?sid=1",  # no scheme: no page a fetch could ask
        "https://",
    ):
        plan_site, fact = _held(sid("0d0d0d0d", 2), url)
        assert not PL.is_r_candidate(plan_site, fact), url
    mixed, fact = _held(sid("0d0d0d0d", 3), web + "\nhttps://de.wikipedia.org/wiki/X")
    assert not PL.is_r_candidate(mixed, fact)
    not_held, fact = _held(sid("0d0d0d0d", 4), web, ())
    assert not PL.is_r_candidate(not_held, fact)


def test_the_t_and_r_draws_take_their_candidates() -> None:
    sites = named_sites()
    extra = {
        sid("0d0d0d0d", n): _held(sid("0d0d0d0d", n), f"https://it.wikipedia.org/wiki/T{n}")
        for n in range(1, 4)
    }
    extra.update(
        {
            sid("0e1e1e1e", n): _held(sid("0e1e1e1e", n), f"https://example.org/r{n}")
            for n in range(1, 11)
        }
    )
    census = census_of(sites, extra)
    lines, summary = build(sites, census)
    assert drawn(lines, PL.DRAW_T) == sorted(sid("0d0d0d0d", n) for n in range(1, 4))
    r = drawn(lines, PL.DRAW_R)
    assert len(r) == 8 and all(x.startswith("0e1e1e1e") for x in r)
    assert summary["draws"][PL.DRAW_R]["population"] == 10


def test_the_long_draw_takes_lane_sources_over_40000_characters() -> None:
    sites = named_sites()
    extra = {
        sid("0a1a1a1a", 1): (site(sid("0a1a1a1a", 1), "Long"), facts(M.Lane.W, chars=40_001)),
        sid("0a1a1a1a", 2): (site(sid("0a1a1a1a", 2), "Edge"), facts(M.Lane.S, chars=40_000)),
        sid("0a1a1a1a", 3): (site(sid("0a1a1a1a", 3), "Short"), facts(M.Lane.W, chars=39_999)),
    }
    census = census_of(sites, extra)
    # The lane draws come first and would take them all; a draw of zero W/S is not what is tested.
    pools = PL.populations(sites, census, set())
    assert pools[PL.DRAW_LONG] == [sid("0a1a1a1a", 1)]


def test_the_b3_draw_takes_the_routeless_read() -> None:
    sites = named_sites()
    extra = {
        sid("0c1c1c1c", n): _held(sid("0c1c1c1c", n), None, ("no-source",)) for n in range(1, 8)
    }
    census = census_of(sites, extra)
    for site_id in extra:
        sites[site_id] = dataclasses.replace(sites[site_id], wikidata_qid=None)
    routeless = PL.routeless_ids([{"id": site_id} for site_id in extra], sites)
    lines, _ = build(sites, census, routeless=routeless)
    b3 = drawn(lines, PL.DRAW_B3)
    assert len(b3) == 5 and set(b3) <= set(extra)


@pytest.mark.parametrize(
    "over",
    [
        {"wikidata_qid": "Q5"},
        {"enwiki_title": "Stone Temple"},
        {"source_url": "see https://example.org/stone"},
    ],
)
def test_a_routeless_site_the_plan_gives_a_route_is_refused(over: dict[str, Any]) -> None:
    site_id = sid("0c1c1c1c")
    base = site(site_id, "Routeless", enwiki_title=None, wikidata_qid=None, source_url=None)
    sites = {site_id: base}
    assert PL.routeless_ids([{"id": site_id}], sites) == {site_id}
    sites[site_id] = dataclasses.replace(base, **over)
    with pytest.raises(R.InputError, match="denies"):
        PL.routeless_ids([{"id": site_id}], sites)


def test_the_routeless_read_is_one_read_only_select_through_the_runner(tmp_path: Path) -> None:
    asked: list[str] = []

    def runner(sql: str, *, host: str) -> str:
        asked.append(sql)
        return json.dumps({"id": "b", "name": "B"}) + "\n" + json.dumps({"id": "a", "name": "A"})

    args = PL.build_parser().parse_args(["routeless", "--out", str(tmp_path / "r.json")])
    assert PL.cmd_routeless(args, runner=runner) == 0
    (sql,) = asked
    assert sql == PL.ROUTELESS_SQL and sql.startswith("SELECT ") and sql.count(";") == 1
    for word in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE"):
        assert word not in sql.upper()
    payload = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in payload["sites"]] == ["a", "b"]


# ================================================================================= the census


def census_run(tmp_path: Path, setups: list[X.SiteSetup], holds: list[M.Hold]) -> tuple[Path, Path]:
    batch_dir = X.make_batch(tmp_path, setups, run="census")
    (batch_dir / RS.ROUTES_REPORT).write_text("{}", encoding="utf-8")
    (batch_dir / M.HOLDS_FILE).write_text(M.dump_jsonl(holds), encoding="utf-8")
    plan = tmp_path / "PLAN4.census.jsonl"
    line = {"batch_id": "p4-0001", "ordinal": 1, "sites": [s.site.to_dict() for s in setups]}
    plan.write_text(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return plan, batch_dir.parent


def test_the_census_is_each_sites_lane_site_holds_and_lane_source_length(tmp_path: Path) -> None:
    held = X.SiteSetup(site=X.plan_site("site-2"), lane=M.Lane.ZERO)
    card_hold = M.Hold(
        site_id="site-1", scope=M.HoldScope.CARD, reason=M.HoldReason.V10, detail="x"
    )
    stop = M.Hold(
        site_id="site-2", scope=M.HoldScope.SITE, reason=M.HoldReason.SEARCH_STOPPED, detail="S1b"
    )
    plan, run_dir = census_run(tmp_path, [X.w_site("site-1"), held], [card_hold, stop])

    sites, census = PL.read_census(plan, run_dir)

    assert set(sites) == {"site-1", "site-2"}
    assert census["site-1"] == PL.Census("p4-0001", M.Lane.W, (), len(X.ARTICLE))
    assert census["site-2"] == PL.Census("p4-0001", M.Lane.ZERO, ("search-stopped",), None)


def test_a_census_batch_without_its_routes_report_is_refused(tmp_path: Path) -> None:
    plan, run_dir = census_run(tmp_path, [X.w_site("site-1")], [])
    (run_dir / "p4-0001" / RS.ROUTES_REPORT).unlink()
    with pytest.raises(R.InputError, match="not complete"):
        PL.read_census(plan, run_dir)


def test_a_census_run_of_another_plan_is_refused(tmp_path: Path) -> None:
    plan, run_dir = census_run(tmp_path, [X.w_site("site-1")], [])
    line = json.loads(plan.read_text(encoding="utf-8"))
    line["sites"][0]["name"] = "Another Temple"
    plan.write_text(json.dumps(line) + "\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="not the plan's line"):
        PL.read_census(plan, run_dir)


def test_build_writes_pilot_jsonl_byte_identically_and_prints_its_exit_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setups = [X.SiteSetup(site=plan_site, lane=M.Lane.ZERO) for plan_site in named_sites().values()]
    setups += [X.w_site(sid("0b0b0b0b", n), name=f"W {n}") for n in range(1, 4)]
    plan, run_dir = census_run(tmp_path, setups, [])
    (tmp_path / "gold.json").write_text(
        json.dumps({"records": [{"site_id": sid("0b0b0b0b", 1)}]}), encoding="utf-8"
    )
    repair = "".join(
        json.dumps({"kind": "wikidata_qid", "old_value": "Q309", "site_id": s}) + "\n" for s in Q309
    )
    (tmp_path / "repair.jsonl").write_text(repair, encoding="utf-8")
    (tmp_path / "routeless.json").write_text(json.dumps({"sites": []}), encoding="utf-8")
    argv = [
        "build",
        f"--plan={plan}",
        f"--run-dir={run_dir}",
        f"--gold={tmp_path / 'gold.json'}",
        f"--qid-repair={tmp_path / 'repair.jsonl'}",
        f"--routeless={tmp_path / 'routeless.json'}",
    ]

    assert PL.main([*argv, f"--out={tmp_path / 'a.jsonl'}"]) == 0
    assert PL.main([*argv, f"--out={tmp_path / 'b.jsonl'}"]) == 0

    out = capsys.readouterr().out
    assert out.rstrip().endswith("STAGE_EXIT=0")
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()
    lines = R.read_jsonl(tmp_path / "a.jsonl")
    assert lines[0]["site_id"] == sid("0b0b0b0b", 1) and lines[0]["strata"] == ["gold-standard"]
    assert drawn(lines, PL.DRAW_W) == [sid("0b0b0b0b", 2), sid("0b0b0b0b", 3)]

    # pilot 2: `--after` keeps the fixed lines, excludes the draws, and names its input's digest
    second = tmp_path / "second.jsonl"
    after = [f"--after={tmp_path / 'a.jsonl'}", f"--seed={PL.SEED_PILOT2}", f"--out={second}"]
    assert PL.main([*argv, *after]) == 0
    printed = capsys.readouterr().out
    summary = json.loads(printed[: printed.rindex("STAGE_EXIT=")])
    assert summary["earlier_draws_excluded"] == 2
    assert summary["inputs"]["after"] == [PL._sha256(tmp_path / "a.jsonl")]
    lines2 = R.read_jsonl(second)
    assert fixed_lines(lines2) == fixed_lines(lines) and drawn(lines2, PL.DRAW_W) == []

    # pilot 3: `--after` once per earlier pilot, each one's digest named in order
    third = tmp_path / "third.jsonl"
    after3 = [f"--after={tmp_path / 'a.jsonl'}", f"--after={second}", f"--seed={PL.SEED_PILOT3}"]
    assert PL.main([*argv, *after3, f"--out={third}"]) == 0
    printed = capsys.readouterr().out
    summary = json.loads(printed[: printed.rindex("STAGE_EXIT=")])
    assert summary["inputs"]["after"] == [PL._sha256(tmp_path / "a.jsonl"), PL._sha256(second)]
    assert summary["earlier_draws_excluded"] == 2
    assert fixed_lines(R.read_jsonl(third)) == fixed_lines(lines)


# =========================================================================== the prose errors


def gold_record(error_id: str, field: str, text_field: str, text: str) -> dict[str, Any]:
    return {
        "site_id": sid("0a0a0a0a"),
        "site_name": "Gold",
        "db_fields": {"description": "", "card_description": "", text_field: text},
        "errors_found": [{"id": error_id, "field": field, "severity": "moderate", "claim": "c"}],
    }


@pytest.mark.skipif(not GOLD_FILE.exists(), reason="the versioned gold standard is missing")
def test_the_gold_prose_errors_are_the_fifteen_with_anchors_in_their_own_text() -> None:
    gold = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    entries = PL.gold_errors(gold, "gold.json")
    assert len(entries) == 15 and {e["id"] for e in entries} == set(PL.GOLD_ANCHORS)
    ls1 = next(e for e in entries if e["id"] == "LS-1")
    assert ls1["claim"].startswith("description dates the petroglyphs")
    assert {"field": "description", "text": "1000 BC-300 AD"} in ls1["anchors"]


def test_an_anchor_that_is_not_in_the_gold_text_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PL, "GOLD_ANCHORS", {"XX-1": ("description", ("1000 BC",))})
    monkeypatch.setattr(PL, "GOLD_PROSE_ERRORS", 1)
    gold = {"records": [gold_record("XX-1", "description", "description", "Built c. 900 BC.")]}
    with pytest.raises(R.InputError, match="is not in its description"):
        PL.gold_errors(gold, "gold.json")


def test_a_gold_prose_error_without_anchors_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PL, "GOLD_ANCHORS", {})
    gold = {"records": [gold_record("XX-2", "period_start + description", "description", "x")]}
    with pytest.raises(R.InputError, match="no anchors"):
        PL.gold_errors(gold, "gold.json")


def canary_rows() -> dict[str, dict[str, Any]]:
    """An export row per canary whose texts carry every stored anchor."""
    rows: dict[str, dict[str, Any]] = {}
    for canary, named in zip(PL.CANARY_DEFECTS, PL.CANARIES, strict=True):
        texts = {"description": [], "card_description": []}
        for field, anchor in canary.anchors:
            if field is not None:
                texts[field].append(anchor)
        rows[sid(canary.prefix)] = {
            "id": sid(canary.prefix),
            "name": named.name,
            "names": [],
            "description": " ".join(texts["description"]),
            "card": " ".join(texts["card_description"]),
        }
    return rows


def canary_sources() -> dict[str, str]:
    """Each source label's text: every claim and quote, verbatim."""
    texts: dict[str, list[str]] = {}
    for canary in PL.CANARY_DEFECTS:
        for source, text in ((canary.source, canary.claim), *canary.quotes):
            texts.setdefault(source, []).append(text)
    return {source: "\n".join(parts) for source, parts in texts.items()}


def test_the_ten_canaries_carry_their_claims_and_anchors() -> None:
    entries = PL.canary_errors(canary_rows(), canary_sources())
    assert [e["id"] for e in entries] == [f"CANARY-{n:02d}" for n in range(1, 11)]
    assert [e["site_id"] for e in entries] == [sid(n.prefix) for n in PL.CANARIES]
    hatunmarka = entries[0]
    assert {"field": "card_description", "text": "Choquequirao"} in hatunmarka["anchors"]


def test_a_canary_anchor_the_export_does_not_carry_is_refused() -> None:
    rows = canary_rows()
    rows[sid("3dd6b568")]["card"] = "A site along the Qhapaq Nan."
    with pytest.raises(R.InputError, match="'30,000 km' is not in the stored card_description"):
        PL.canary_errors(rows, canary_sources())


def test_a_canary_claim_that_is_not_verbatim_in_its_source_is_refused() -> None:
    sources = canary_sources()
    sources[PL.PLAN_42] = sources[PL.PLAN_42].replace("hillfort", "hill fort")
    with pytest.raises(R.InputError, match="not verbatim"):
        PL.canary_errors(canary_rows(), sources)


def test_a_canary_row_of_another_site_is_refused() -> None:
    rows = canary_rows()
    rows[sid("411cacb0")]["name"] = "Kithill"
    with pytest.raises(R.InputError, match="not the canary 'Kit Hill'"):
        PL.canary_errors(rows, canary_sources())


@pytest.mark.skipif(not REMEDIATION_PLAN.exists(), reason="the remediation plan is missing")
def test_every_canary_claim_from_the_plan_is_verbatim_in_it() -> None:
    text = PL._collapsed(REMEDIATION_PLAN.read_text(encoding="utf-8"))
    for canary in PL.CANARY_DEFECTS:
        for source, quoted in ((canary.source, canary.claim), *canary.quotes):
            if source in (PL.PLAN_42, PL.PLAN_51):
                assert PL._collapsed(quoted) in text, quoted


# =============================================================================== the thresholds


def test_the_threshold_blocks_are_cut_exactly_at_the_designs_headings() -> None:
    text = (
        "PILOT RUN\n1. x\n\n"
        "THRESHOLDS (fixed now; never loosened after the data is seen)\n- T1: a\n\nReported: b\n\n"
        "ON FAILURE\n- A failure on T1 means STOP.\n\nMASS RUN GATES\n- y\n"
    )
    thresholds, failure = PL.threshold_blocks(text)
    assert thresholds == (
        "THRESHOLDS (fixed now; never loosened after the data is seen)\n- T1: a\n\nReported: b"
    )
    assert failure == "ON FAILURE\n- A failure on T1 means STOP."


def test_the_thresholds_document_carries_both_blocks_verbatim_and_the_note() -> None:
    text = (
        "THRESHOLDS (fixed now; never loosened after the data is seen)\n- T1: 0 UNSUPPORTED.\n\n"
        "ON FAILURE\n- STOP.\n\nMASS RUN GATES\n"
    )
    document = PL.thresholds_document({"pilot_and_thresholds": text})
    assert "- T1: 0 UNSUPPORTED.\n" in document and "ON FAILURE\n- STOP.\n" in document
    assert "everything with Opus" in document and "search-stopped" in document


def test_a_design_file_that_is_not_the_pinned_one_is_refused(tmp_path: Path) -> None:
    fake = tmp_path / "design.json"
    fake.write_text(json.dumps([{}] * 7), encoding="utf-8")
    with pytest.raises(R.InputError, match="not the design file"):
        PL.design_entries(fake)


def test_the_canary_defects_are_the_designs_ten_canaries_in_its_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, sources = canary_rows(), canary_sources()
    monkeypatch.setattr(PL, "CANARY_DEFECTS", PL.CANARY_DEFECTS[1:])
    with pytest.raises(R.InputError, match="10 canaries"):
        PL.canary_errors(rows, sources)


def test_an_anchored_id_the_gold_standard_does_not_have_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        PL, "GOLD_ANCHORS", {"XX-1": ("description", ("900 BC",)), "XX-9": ("description", ())}
    )
    monkeypatch.setattr(PL, "GOLD_PROSE_ERRORS", 1)
    gold = {"records": [gold_record("XX-1", "description", "description", "Built c. 900 BC.")]}
    with pytest.raises(R.InputError, match="are not the 1 GOLD_ANCHORS names"):
        PL.gold_errors(gold, "gold.json")


def test_a_routeless_id_the_plan_does_not_have_is_refused() -> None:
    with pytest.raises(R.InputError, match="does not have"):
        PL.routeless_ids([{"id": sid("0c1c1c1c")}], {})


# ================================================================ the sealed artefacts (2026-09-24)

RUNNER = REPO / "output" / "remediation" / "phase4_runner"
AUDIT_LOG = REPO / "output" / "remediation" / "AUDIT_LOG.md"
DESIGN = REPO / "output" / "remediation" / "logs" / "design_texts_images_2026-09-22.json"
#: The digests AUDIT_LOG.md recorded before the first model question of the pilot was exported.
SEALED = {
    "PILOT.jsonl": "7f66f987186151108879105745f082da3b4c8623ca5bd0a201c32a95e4e063fc",
    "gold_prose_errors.json": "e4e63d56cbc9cca0f9cea018967fac40e897faddb9c43ad064e6203a74ebb7df",
    "PILOT_THRESHOLDS.md": "64ac53341068234c905cff00095a9d7244cd4703353f63bbd0997add63fe0c13",
}


def test_the_sealed_artefacts_keep_the_digests_the_audit_log_recorded() -> None:
    """Design: "Their sha256 values are recorded in AUDIT_LOG.md before any model call" - and
    nothing in them may change after the data is seen."""
    log = AUDIT_LOG.read_text(encoding="utf-8")
    for name, digest in SEALED.items():
        assert PL._sha256(RUNNER / name) == digest, name
        assert f"`{digest}`" in log, f"AUDIT_LOG.md does not record {name}'s sha256"


def test_the_sealed_pilot_holds_every_member_the_design_names() -> None:
    lines = R.read_jsonl(RUNNER / "PILOT.jsonl")
    ids = [line["site_id"] for line in lines]
    assert len(ids) == len(set(ids)) == 132
    gold = R._gold_site_ids(GOLD_FILE)
    assert ids[: len(gold)] == gold
    for named in (*PL.CANARIES, *PL.B5_FIXTURES, *PL.IDENTITY_TRAPS, *PL.SPECIAL):
        assert sum(site_id.startswith(named.prefix) for site_id in ids) == 1, named
    strata = [stratum for line in lines for stratum in line["strata"]]
    assert strata.count("identity-trap-q309-history") == PL.Q309_SITES
    for stratum, count in PL.DRAWS:
        assert strata.count(stratum) == count, stratum  # every stratum was large enough


@pytest.mark.skipif(not GOLD_FILE.exists(), reason="the versioned gold standard is missing")
def test_the_sealed_prose_errors_are_the_gold_standards_fifteen_and_the_ten_canaries() -> None:
    payload = json.loads((RUNNER / "gold_prose_errors.json").read_text(encoding="utf-8"))
    gold = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    errors = payload["errors"]
    assert [e["id"] for e in errors if e["kind"] == "gold"] == [
        e["id"] for e in PL.gold_errors(gold, "gold.json")
    ]
    assert [e["id"] for e in errors if e["kind"] == "canary"] == [
        f"CANARY-{n:02d}" for n in range(1, 11)
    ]
    # The seal (fab4f57) hashed the gold standard as the workstation's CRLF checkout wrote it
    # (core.autocrlf=true, no eol attribute on gold_standard/): 18653fc1...b2756, the value
    # AUDIT_LOG.md records too. The committed blob is LF (1e71022d...242e5), so an LF checkout -
    # CI - holds other bytes for the same content. The sealed digest is compared against the
    # content in the sealing checkout's CRLF form, whatever EOL this checkout has.
    lf = GOLD_FILE.read_bytes().replace(b"\r\n", b"\n")
    sealed_bytes = lf.replace(b"\n", b"\r\n")
    assert payload["inputs"]["gold_standard"]["sha256"] == hashlib.sha256(sealed_bytes).hexdigest()


@pytest.mark.skipif(not DESIGN.exists(), reason="needs the gitignored design file")
def test_the_sealed_thresholds_are_the_designs_blocks_verbatim() -> None:
    text = (RUNNER / "PILOT_THRESHOLDS.md").read_text(encoding="utf-8")
    entry = PL.design_entries(DESIGN)[PL.DESIGN_ENTRY]
    thresholds, failure = PL.threshold_blocks(entry["pilot_and_thresholds"])
    assert f"\n{thresholds}\n\n{failure}\n" in text
    assert text == PL.thresholds_document(entry)


# ========================================================= pilot 2's seal (2026-09-24, seed 20260924)

#: The audit log's section that sealed pilot 2 before its first model question was exported.
PILOT2_SECTION = "## 2026-09-24 - Phase-4 pilot 2, sealed before its first model question"
#: Pilot 2's new draw, and the two documents it keeps from pilot 1, byte for byte.
SEALED_PILOT2 = {
    "PILOT2.jsonl": "9caaaa0312369155bb489a0c96ba6fb1b5e57ec988e787a0206c10503cc9f81c",
    "PILOT_THRESHOLDS.md": SEALED["PILOT_THRESHOLDS.md"],
    "gold_prose_errors.json": SEALED["gold_prose_errors.json"],
}


def _section(log: str, heading: str) -> str:
    start = log.index(heading)
    end = log.find("\n## ", start + len(heading))
    return log[start:] if end == -1 else log[start:end]


def test_pilot_2_is_sealed_with_pilot_1s_thresholds_byte_for_byte() -> None:
    """The thresholds are "never loosened after the data is seen": pilot 2 runs under the document
    sealed before pilot 1's first question, byte for byte, and the audit log's pilot-2 section
    records PILOT2.jsonl's digest beside the two unchanged ones before its first export."""
    section = _section(AUDIT_LOG.read_text(encoding="utf-8"), PILOT2_SECTION)
    for name, digest in SEALED_PILOT2.items():
        assert PL._sha256(RUNNER / name) == digest, name
        assert f"`{digest}`" in section, f"the pilot-2 section does not record {name}'s sha256"


def test_the_sealed_pilot_2_keeps_pilot_1s_fixed_members_and_none_of_its_draws() -> None:
    first = R.read_jsonl(RUNNER / "PILOT.jsonl")
    second = R.read_jsonl(RUNNER / "PILOT2.jsonl")
    fixed, drawn_first = PL.earlier_pilot(first)
    fixed_second, drawn_second = PL.earlier_pilot(second)
    assert fixed_second == fixed and len(fixed) == 70
    assert second[:70] == first[:70]  # the same census: the fixed lines are pilot 1's, whole
    assert not drawn_first & drawn_second and len(drawn_second) == 62
    ids = [line["site_id"] for line in second]
    assert len(ids) == len(set(ids)) == 132
    strata = [stratum for line in second for stratum in line["strata"]]
    for stratum, count in PL.DRAWS:
        assert strata.count(stratum) == count, stratum


# ========================================================= pilot 3's seal (2026-09-24, seed 20260925)

#: The audit log's section that sealed pilot 3 before its first model question was exported.
PILOT3_SECTION = "## 2026-09-24 - Phase-4 pilot 3, sealed before its first model question"
#: Pilot 3's new draw, and the two documents it keeps from pilot 1, byte for byte.
SEALED_PILOT3 = {
    "PILOT3.jsonl": "a4fa2f5ff26676374a48ced6fa249fc530d2003d340647e84581ef87f04152fc",
    "PILOT_THRESHOLDS.md": SEALED["PILOT_THRESHOLDS.md"],
    "gold_prose_errors.json": SEALED["gold_prose_errors.json"],
}


def test_pilot_3_is_sealed_with_pilot_1s_thresholds_byte_for_byte() -> None:
    """Pilot 2's failures changed code, never the thresholds: pilot 3 runs under the document
    sealed before pilot 1's first question, byte for byte, and the audit log's pilot-3 section
    records PILOT3.jsonl's digest beside the two unchanged ones before its first export."""
    section = _section(AUDIT_LOG.read_text(encoding="utf-8"), PILOT3_SECTION)
    for name, digest in SEALED_PILOT3.items():
        assert PL._sha256(RUNNER / name) == digest, name
        assert f"`{digest}`" in section, f"the pilot-3 section does not record {name}'s sha256"


def test_the_sealed_pilot_3_keeps_the_fixed_members_and_none_of_the_earlier_draws() -> None:
    first = R.read_jsonl(RUNNER / "PILOT.jsonl")
    second = R.read_jsonl(RUNNER / "PILOT2.jsonl")
    third = R.read_jsonl(RUNNER / "PILOT3.jsonl")
    fixed, drawn_first = PL.earlier_pilot(first)
    _, drawn_second = PL.earlier_pilot(second)
    fixed_third, drawn_third = PL.earlier_pilot(third)
    assert fixed_third == fixed and len(fixed) == 70
    lines = [
        (RUNNER / name).read_bytes().splitlines(keepends=True)
        for name in ("PILOT.jsonl", "PILOT3.jsonl")
    ]
    assert lines[1][:70] == lines[0][:70]  # the same census: the fixed lines, byte for byte
    assert not (drawn_first | drawn_second) & drawn_third and len(drawn_third) == 62
    ids = [line["site_id"] for line in third]
    assert len(ids) == len(set(ids)) == 132
    strata = [stratum for line in third for stratum in line["strata"]]
    for stratum, count in PL.DRAWS:
        assert strata.count(stratum) == count, stratum


# ========================================================= pilot 4's seal (2026-09-24, seed 20260926)

#: The audit log's section that sealed pilot 4 before its first model question was exported.
PILOT4_SECTION = "## 2026-09-24 - Phase-4 pilot 4, sealed before its first model question"
#: Pilot 4's new draw, and the two documents it keeps from pilot 1, byte for byte.
SEALED_PILOT4 = {
    "PILOT4.jsonl": "30ab5e9d28b71388f79319b93e945dfd223d5d3edeb9a62e42064844757b2a26",
    "PILOT_THRESHOLDS.md": SEALED["PILOT_THRESHOLDS.md"],
    "gold_prose_errors.json": SEALED["gold_prose_errors.json"],
}


def test_pilot_4_is_sealed_with_pilot_1s_thresholds_byte_for_byte() -> None:
    """Pilot 3's failures changed code, never the thresholds: pilot 4 runs under the document
    sealed before pilot 1's first question, byte for byte, and the audit log's pilot-4 section
    records PILOT4.jsonl's digest beside the two unchanged ones before its first export."""
    section = _section(AUDIT_LOG.read_text(encoding="utf-8"), PILOT4_SECTION)
    for name, digest in SEALED_PILOT4.items():
        assert PL._sha256(RUNNER / name) == digest, name
        assert f"`{digest}`" in section, f"the pilot-4 section does not record {name}'s sha256"


def test_the_sealed_pilot_4_keeps_the_fixed_members_and_none_of_the_earlier_draws() -> None:
    earlier = [
        R.read_jsonl(RUNNER / name) for name in ("PILOT.jsonl", "PILOT2.jsonl", "PILOT3.jsonl")
    ]
    fourth = R.read_jsonl(RUNNER / "PILOT4.jsonl")
    fixed, _ = PL.earlier_pilot(earlier[0])
    drawn_before = {site_id for lines in earlier for site_id in PL.earlier_pilot(lines)[1]}
    fixed_fourth, drawn_fourth = PL.earlier_pilot(fourth)
    assert fixed_fourth == fixed and len(fixed) == 70
    lines = [
        (RUNNER / name).read_bytes().splitlines(keepends=True)
        for name in ("PILOT.jsonl", "PILOT4.jsonl")
    ]
    assert lines[1][:70] == lines[0][:70]  # the same census: the fixed lines, byte for byte
    assert len(drawn_before) == 186 and not drawn_before & drawn_fourth and len(drawn_fourth) == 62
    ids = [line["site_id"] for line in fourth]
    assert len(ids) == len(set(ids)) == 132
    strata = [stratum for line in fourth for stratum in line["strata"]]
    for stratum, count in PL.DRAWS:
        assert strata.count(stratum) == count, stratum
