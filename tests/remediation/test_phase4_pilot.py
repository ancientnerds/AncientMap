"""Is the Phase-4 pilot drawn the way the design says, from the census's lanes, and nobody's choice?

`phase4/pilot4.py` (the pilot of 2026-09-24): the fixed members resolved from the design's id
prefixes and names, the seeded draws per stratum (lanes W and S from the census; the T and R
candidates the routes stage held for a search that is switched off; B3 from the routeless read;
extracts over 40,000 characters), the census read from a run directory, the forbidden anchors of
`gold_prose_errors.json` and the verbatim threshold blocks. No socket, database or model is touched:
the production read goes through a recording runner. The mutation cases are `P4_PILOT_MUTATIONS`
in `scripts/remediation/phase3/mutation_sweep.py` (label `p4 pilot: `).
"""

from __future__ import annotations

import dataclasses
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
