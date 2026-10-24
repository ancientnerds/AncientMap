"""D48/D49 (owner decisions of 2026-10-19): the hero moves the D15 pass carries.

DB-less and offline: the problems of a site (unflagged, strip, hotlink, no author), what makes a row
a qualifying hero (a Claude `depicts` of that very file, the floor, the credit, larger than a strip),
the ranking (a confirmed check-run pick, then the replacement stage's pick), the D15 deferral of an
`other_site` hero, vetoes, the check population of the rows nobody judged, the chunks the shared
writer takes, the small-hero owner list, and the read-only acceptance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
from gallery_audit import chunk_writer as CW  # noqa: E402
from served_image import hero_moves as HM  # noqa: E402

SITE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
UPLOAD = "https://upload.wikimedia.org/wikipedia/commons/a/ab/"


def _site(sid: str = SITE, thumb: str | None = None, **over: Any) -> dict[str, Any]:
    return {
        "id": sid,
        "name": "Thasos",
        "country": "Greece",
        "site_type": "City",
        "lat": 40.7,
        "lon": 24.7,
        "thumbnail_url": thumb,
        "description": "A walled city.",
        "qid": "Q1",
        "enwiki_title": "Thasos",
    } | over


def _row(
    image_id: int,
    file: str,
    *,
    sid: str = SITE,
    hero: bool = False,
    size: tuple[int, int] = (2000, 1200),
    license: str = "CC BY-SA 4.0",
    author: str | None = "A. Photographer",
    license_url: str | None = "https://creativecommons.org/licenses/by-sa/4.0",
    excluded: bool = False,
    order: int = 0,
) -> dict[str, Any]:
    return {
        "id": image_id,
        "site_id": sid,
        "filename": file.rsplit(".", 1)[0] + ".webp",
        "title": file,
        "commons_page_url": None,
        "original_url": UPLOAD + file.replace(" ", "_"),
        "is_hero": hero,
        "is_lead": False,
        "is_excluded": excluded,
        "sort_order": order,
        "width": size[0],
        "height": size[1],
        "license": license,
        "license_url": license_url,
        "author": author,
        "file_size_bytes": 1000,
    }


def _check(sid: str, file: str, verdict: str = "depicts", **over: Any) -> HM.Check:
    base = {
        "site_id": sid,
        "file": file,
        "verdict": verdict,
        "source": "served_image/served-image-2026-09-30/CHECK.jsonl",
        "stage": "served-check",
        "answered_by": "check-001",
        "model": OH.SONNET_MODEL,
    }
    return HM.Check(**(base | over))


def _read(sites: list[dict[str, Any]], rows: list[dict[str, Any]]) -> HM.Read:
    by_site: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_site.setdefault(row["site_id"], []).append(row)
    return HM.Read(
        {s["id"]: s for s in sites}, {k: tuple(v) for k, v in by_site.items()}, "0" * 64, "now"
    )


# ------------------------------------------------------------------------------- problems
def test_the_four_problems_are_measured_on_the_read() -> None:
    hero = _row(1, "A.jpg", hero=True, size=(700, 200), author=None)
    live = [hero, _row(2, "B.jpg")]
    found = HM.problems_of(_site(thumb="https://example.org/x.jpg"), live, hero)
    assert found == [HM.STRIP, HM.HOTLINK, HM.NO_AUTHOR]
    assert HM.problems_of(_site(), [_row(2, "B.jpg")], None) == [HM.UNFLAGGED]


def test_a_site_without_live_rows_has_no_problem_here() -> None:
    assert HM.problems_of(_site(thumb="https://example.org/x.jpg"), [], None) == []


def test_an_empty_thumbnail_string_is_a_broken_thumbnail() -> None:
    hero = _row(1, "A.jpg", hero=True)
    assert HM.problems_of(_site(thumb=""), [hero], hero) == [HM.HOTLINK]


def test_a_free_licence_asks_for_no_author() -> None:
    hero = _row(1, "A.jpg", hero=True, license="Public domain", author=None, license_url=None)
    assert HM.problems_of(_site(thumb="/data/x"), [hero], hero) == []


# ------------------------------------------------------------------------------- qualifies
def test_an_unchecked_row_never_qualifies() -> None:
    assert HM.qualifies(_row(2, "B.jpg"), None) == HM.UNCHECKED


def test_a_row_judged_other_than_depicts_does_not_qualify() -> None:
    reason = HM.qualifies(_row(2, "B.jpg"), _check(SITE, "B.jpg", "region_or_type"))
    assert reason is not None and reason.startswith("judged region_or_type")


def test_a_check_of_another_file_does_not_speak_for_the_row() -> None:
    assert HM.qualifies(_row(2, "B.jpg"), _check(SITE, "C.jpg")) == HM.OTHER_FILE


def test_a_row_below_the_floor_does_not_qualify() -> None:
    row = _row(2, "B.jpg", size=(800, 299))
    assert HM.qualifies(row, _check(SITE, "B.jpg")) == HM.BELOW_FLOOR


def test_a_strip_is_replaced_only_by_a_larger_row() -> None:
    strip = _row(1, "A.jpg", hero=True, size=(3000, 250))
    row = _row(2, "B.jpg", size=(800, 300))
    assert HM.qualifies(row, _check(SITE, "B.jpg"), larger_than=strip) == HM.NOT_LARGER


def test_a_row_without_its_credit_does_not_qualify() -> None:
    reason = HM.qualifies(_row(2, "B.jpg", author=""), _check(SITE, "B.jpg"))
    assert reason is not None and reason.startswith(HM.CREDIT) and "author" in reason
    reason = HM.qualifies(_row(2, "B.jpg", license_url=None), _check(SITE, "B.jpg"))
    assert reason is not None and "license_url" in reason


# ------------------------------------------------------------------------------- decide
def test_an_unflagged_site_gets_its_checked_row_as_hero() -> None:
    site = _site(thumb="/data/images/wiki/11111111/B.webp")
    rows = [_row(2, "B.jpg")]
    decision = HM.decide(site, rows, {2: _check(SITE, "B.jpg")}, {})
    assert decision is not None and decision.plan is not None
    assert decision.plan.outcome == HM.FLAGGED
    [change] = decision.plan.changes
    assert (change.column, change.row_key, change.old_value, change.new_value, change.rule) == (
        "is_hero",
        "2",
        "false",
        "true",
        HM.RULE_D48_HERO,
    )


def test_a_strip_hero_moves_to_the_checked_larger_row_and_the_globe_follows() -> None:
    site = _site(thumb="/data/images/wiki/11111111/A.webp")
    rows = [_row(1, "A.jpg", hero=True, size=(800, 128)), _row(2, "B.jpg")]
    decision = HM.decide(site, rows, {2: _check(SITE, "B.jpg")}, {})
    assert decision is not None and decision.plan is not None
    got = {(c.column, c.row_key): (c.old_value, c.new_value, c.rule) for c in decision.plan.changes}
    assert got == {
        ("is_hero", "1"): ("true", "false", HM.RULE_D48_HERO),
        ("is_hero", "2"): ("false", "true", HM.RULE_D48_HERO),
        ("thumbnail_url", SITE): (
            "/data/images/wiki/11111111/A.webp",
            "/data/images/wiki/11111111/B.webp",
            HM.RULE_D48_ALIGN,
        ),
    }
    assert decision.plan.served_image_id == 2


def test_a_hero_without_its_author_moves_under_the_d49_rule() -> None:
    rows = [_row(1, "A.jpg", hero=True, author=None), _row(2, "B.jpg")]
    decision = HM.decide(_site(thumb="/data/x"), rows, {2: _check(SITE, "B.jpg")}, {})
    assert decision is not None and decision.plan is not None
    assert {c.rule for c in decision.plan.changes} == {HM.RULE_D49_HERO, HM.RULE_D49_ALIGN}


def test_a_hotlinked_thumbnail_follows_a_qualifying_hero_without_a_move() -> None:
    rows = [_row(1, "A.jpg", hero=True)]
    site = _site(thumb="https://thumb.wikimedia.org/x/400px-A.jpg")
    decision = HM.decide(site, rows, {1: _check(SITE, "A.jpg")}, {})
    assert decision is not None and decision.plan is not None
    assert decision.plan.outcome == HM.ALIGNED
    [change] = decision.plan.changes
    assert change.column == "thumbnail_url" and change.rule == HM.RULE_D48_ALIGN


def test_an_empty_thumbnail_keeps_its_exact_old_value() -> None:
    rows = [_row(1, "A.jpg", hero=True)]
    decision = HM.decide(_site(thumb=""), rows, {1: _check(SITE, "A.jpg")}, {})
    assert decision is not None and decision.plan is not None
    [change] = decision.plan.changes
    assert change.old_value == ""


def test_a_site_without_a_qualifying_row_goes_to_the_owner_list_with_the_reason() -> None:
    rows = [_row(1, "A.jpg", hero=True, size=(800, 128)), _row(2, "B.jpg"), _row(3, "C.jpg")]
    decision = HM.decide(_site(), rows, {3: _check(SITE, "C.jpg", "other_site")}, {})
    assert decision is not None and decision.plan is None
    assert decision.owner_reason is not None and "no Claude check" in decision.owner_reason
    assert set(decision.rejected or {}) == {2, 3}


def test_an_excluded_row_is_never_a_candidate() -> None:
    rows = [_row(1, "A.jpg", hero=True, size=(800, 128)), _row(2, "B.jpg", excluded=True)]
    decision = HM.decide(_site(), rows, {2: _check(SITE, "B.jpg")}, {})
    assert decision is not None and decision.plan is None
    assert decision.owner_reason == "no other live row" and decision.rejected == {}


def test_a_hero_judged_other_site_is_deferred_to_the_d15_recheck() -> None:
    rows = [_row(1, "A.jpg", hero=True, author=None), _row(2, "B.jpg")]
    served = {1: _check(SITE, "A.jpg", "other_site"), 2: _check(SITE, "B.jpg")}
    decision = HM.decide(_site(), rows, served, {})
    assert decision is not None and decision.plan is None and decision.deferred is not None


def test_the_replacement_stages_pick_beats_a_larger_row() -> None:
    rows = [
        _row(1, "A.jpg", hero=True, author=None),
        _row(2, "Big.jpg", size=(6000, 4000)),
        _row(3, "Best.jpg", size=(2000, 1200)),
    ]
    served = {2: _check(SITE, "Big.jpg"), 3: _check(SITE, "Best.jpg", picked=True)}
    decision = HM.decide(_site(), rows, served, {})
    assert decision is not None and decision.plan is not None
    assert decision.plan.served_image_id == 3


def test_a_confirmed_check_run_pick_beats_every_served_verdict() -> None:
    rows = [
        _row(1, "A.jpg", hero=True, size=(800, 128)),
        _row(2, "Big.jpg", size=(6000, 4000)),
        _row(3, "Pick.jpg", size=(2000, 1200)),
    ]
    served = {2: _check(SITE, "Big.jpg", picked=True)}
    picks = {SITE: _check(SITE, "Pick.jpg", confirmed=True, quality=5)}
    decision = HM.decide(_site(), rows, served, picks)
    assert decision is not None and decision.plan is not None
    assert decision.plan.served_image_id == 3


def test_a_vetoed_row_is_never_chosen() -> None:
    rows = [_row(1, "A.jpg", hero=True, author=None), _row(2, "B.jpg"), _row(3, "C.jpg")]
    served = {2: _check(SITE, "B.jpg", picked=True), 3: _check(SITE, "C.jpg")}
    decision = HM.decide(_site(), rows, served, {}, {2: "a find, not the site (pilot_judge)"})
    assert decision is not None and decision.plan is not None
    assert decision.plan.served_image_id == 3
    decision = HM.decide(_site(), rows, served, {}, {2: "x (y)", 3: "x (y)"})
    assert decision is not None and decision.plan is None
    assert decision.owner_reason is not None and "vetoed" in decision.owner_reason


def test_two_live_heroes_are_refused() -> None:
    rows = [_row(1, "A.jpg", hero=True), _row(2, "B.jpg", hero=True)]
    with pytest.raises(HM.HeroMovesError, match="one-hero"):
        HM.decide(_site(), rows, {}, {})


def test_a_verdict_recorded_for_another_site_is_refused() -> None:
    rows = [_row(1, "A.jpg", hero=True, author=None), _row(2, "B.jpg")]
    with pytest.raises(HM.HeroMovesError, match="carries a verdict"):
        HM.decide(_site(), rows, {2: _check(OTHER, "B.jpg")}, {})


# ------------------------------------------------------------------------- the verdict files
def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _served_run(tmp_path: Path, *, model: str = OH.SONNET_MODEL) -> Path:
    run = tmp_path / "served-image-2026-09-30"
    _write_jsonl(
        run / "CHECK.jsonl",
        [
            {
                "site_id": SITE,
                "verdict": "depicts",
                "shows": "the walls",
                "basis": "b",
                "answered_by": "check-001",
                "model": model,
                "served": {"image_id": 2, "file": "B.jpg"},
            }
        ],
    )
    _write_jsonl(
        run / "REPLACE.jsonl",
        [
            {
                "site_id": SITE,
                "candidates": {"G1": "depicts"},
                "candidates_shown": [
                    {"label": "G1", "kind": "gallery", "image_id": 3, "file": "C.jpg"}
                ],
                "pick": "G1",
                "basis": "rb",
                "answered_by": "replace-001",
                "model": model,
            }
        ],
    )
    return run


def test_served_checks_keep_claude_stamps_and_mark_the_replacement_pick(tmp_path: Path) -> None:
    checks = HM.served_checks([_served_run(tmp_path)])
    assert checks[2].verdict == "depicts" and checks[2].shows == "the walls"
    assert checks[3].picked and not checks[2].picked
    assert checks[3].source.endswith("REPLACE.jsonl")


def test_a_minimax_stamp_is_no_check(tmp_path: Path) -> None:
    assert HM.served_checks([_served_run(tmp_path, model=OH.MINIMAX_MODEL)]) == {}


def test_a_later_run_replaces_an_earlier_verdict(tmp_path: Path) -> None:
    first = _served_run(tmp_path)
    later = tmp_path / "later" / "served-image-2026-10-25-os47"
    _write_jsonl(
        later / "CHECK.jsonl",
        [
            {
                "site_id": SITE,
                "verdict": "other_site",
                "shows": "another island",
                "answered_by": "adversarial:check-001",
                "model": OH.SONNET_MODEL,
                "served": {"image_id": 2, "file": "B.jpg"},
            }
        ],
    )
    assert HM.served_checks([first, later])[2].verdict == "other_site"
    assert HM.served_checks([later, first])[2].verdict == "depicts"


def _check_run(tmp_path: Path, *, confirmed: bool = True, model: str = OH.SONNET_MODEL) -> Path:
    run = tmp_path / "candidates-2026-10-24-heromoves"
    _write_jsonl(run / "TARGETS.jsonl", [{"site_id": SITE, "commons_file": "C.jpg"}])
    _write_jsonl(
        run / "VERDICTS.jsonl",
        [
            {
                "site_id": SITE,
                "file": "C.jpg",
                "verdict": "depicts",
                "quality": 4,
                "note": "the walls",
                "answered_by": "image_depicts:d-001",
                "model": model,
            }
        ],
    )
    _write_jsonl(
        run / "RECHECK_01.jsonl",
        [
            {
                "meta": {"site_id": SITE, "file": "C.jpg"},
                "verdict": "depicts" if confirmed else "other_site",
                "model": OH.SONNET_MODEL,
            }
        ],
    )
    return run


def test_a_check_run_pick_is_a_confirmed_claude_judgement(tmp_path: Path) -> None:
    picks = HM.check_picks([_check_run(tmp_path)])
    assert picks[SITE].confirmed and picks[SITE].quality == 4


def test_a_check_run_pick_nobody_confirmed_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HM.HeroMovesError):
        HM.check_picks([_check_run(tmp_path, confirmed=False)])


def test_a_minimax_target_without_a_recheck_is_refused(tmp_path: Path) -> None:
    run = _check_run(tmp_path, model=OH.MINIMAX_MODEL)
    (run / "RECHECK_01.jsonl").unlink()
    with pytest.raises(HM.HeroMovesError, match="no Claude model judged"):
        HM.check_picks([run])


# --------------------------------------------------------------------------- the whole plan
def _hero_moves_run(
    tmp_path: Path, sites: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> Path:
    run = tmp_path / "hero-moves-2026-10-24"
    run.mkdir(parents=True)
    (run / "READ.json").write_text(
        json.dumps({"read_at": "now", "sites": sites, "images": rows}), encoding="utf-8"
    )
    return run


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    sites = [_site(thumb="/data/images/wiki/11111111/A.webp")]
    rows = [
        _row(1, "A.jpg", hero=True, size=(800, 128)),
        _row(2, "B.jpg"),
        _row(3, "C.jpg", size=(3000, 2000)),
    ]
    return _hero_moves_run(tmp_path, sites, rows), _served_run(tmp_path)


def test_the_plan_emits_one_chunk_the_shared_writer_takes(tmp_path: Path) -> None:
    run, served = _fixture(tmp_path)
    summary = HM.write_plan(run, [served], [])
    assert summary["planned_sites"] == 1 and summary["rows"] == 3 and summary["chunks"] == 1
    chunk = CW.check_delivered(run / "chunks" / "chunk-001")
    assert chunk.lane.name == HM.LANE_NAME and chunk.run_stamp == "hero-moves-2026-10-24-001"
    assert chunk.may_empty == frozenset()
    [planned] = [json.loads(line) for line in (run / HM.PLANNED).read_text().splitlines()]
    assert planned["new_hero"]["image_id"] == 3  # the replacement stage picked C
    [expected] = [
        json.loads(line) for line in (run / "chunks" / HM.EXPECTED).read_text().splitlines()
    ]
    assert expected == {
        "site_id": SITE,
        "outcome": HM.MOVED,
        "served_image_id": 3,
        "thumbnail_url": "/data/images/wiki/11111111/C.webp",
        "chunk": 1,
    }


def test_a_delivered_plan_is_never_replaced(tmp_path: Path) -> None:
    run, served = _fixture(tmp_path)
    HM.write_plan(run, [served], [])
    with pytest.raises(HM.HeroMovesError, match="holds a plan already"):
        HM.write_plan(run, [served], [])


def test_the_plan_needs_a_verdict_run(tmp_path: Path) -> None:
    run, _ = _fixture(tmp_path)
    with pytest.raises(HM.HeroMovesError, match="--verdicts-run"):
        HM.write_plan(run, [], [])


def test_a_veto_without_a_reviewer_or_of_a_foreign_row_is_refused(tmp_path: Path) -> None:
    run, served = _fixture(tmp_path)
    veto = tmp_path / "veto.jsonl"
    _write_jsonl(veto, [{"site_id": SITE, "image_id": 3, "reason": "a find"}])
    with pytest.raises(HM.HeroMovesError, match="no reviewer"):
        HM.write_plan(run, [served], [], veto)
    _write_jsonl(veto, [{"site_id": SITE, "image_id": 99, "reason": "x", "by": "pilot_judge"}])
    with pytest.raises(HM.HeroMovesError, match="does not hold"):
        HM.write_plan(run, [served], [], veto)


def test_a_veto_moves_the_choice_to_the_next_row(tmp_path: Path) -> None:
    run, served = _fixture(tmp_path)
    veto = tmp_path / "veto.jsonl"
    _write_jsonl(veto, [{"site_id": SITE, "image_id": 3, "reason": "a find", "by": "pilot_judge"}])
    summary = HM.write_plan(run, [served], [], veto)
    assert summary["veto"]["sha256"]
    [planned] = [json.loads(line) for line in (run / HM.PLANNED).read_text().splitlines()]
    assert planned["new_hero"]["image_id"] == 2


def test_the_run_directory_names_the_journal_stamp(tmp_path: Path) -> None:
    with pytest.raises(HM.HeroMovesError, match="not a run directory"):
        HM.lane_for(tmp_path / "hero-moves")
    assert HM.lane_for(tmp_path / "hero-moves-2026-10-24b").stamp == "hero-moves-2026-10-24b"


def test_small_heroes_follow_the_census_definition() -> None:
    sites = [_site(), _site(OTHER)]
    rows = [
        _row(1, "A.jpg", hero=True, size=(800, 600)),
        _row(2, "B.jpg", size=(1600, 900)),
        _row(3, "C.jpg", sid=OTHER, hero=True, size=(800, 600)),
        _row(4, "D.jpg", sid=OTHER, size=(1599, 900)),
    ]
    small = HM.small_heroes(_read(sites, rows))
    assert [(s["site_id"], s["hero_id"], s["larger_rows"]) for s in small] == [(SITE, 1, [2])]


# ------------------------------------------------------------------------ the check population
def test_check_pictures_offers_only_the_rows_nobody_judged(tmp_path: Path) -> None:
    sites = [_site()]
    rows = [
        _row(1, "A.jpg", hero=True, size=(800, 128)),
        _row(2, "B.jpg", size=(800, 100)),  # below the floor
        _row(3, "C.jpg"),  # judged other_site
        _row(4, "D.jpg"),  # nobody judged it
        _row(5, "E.jpg", author=None),  # no credit
    ]
    run = _hero_moves_run(tmp_path, sites, rows)
    served = tmp_path / "served-image-2026-09-30"
    _write_jsonl(
        served / "CHECK.jsonl",
        [
            {
                "site_id": SITE,
                "verdict": "other_site",
                "answered_by": "check-001",
                "model": OH.SONNET_MODEL,
                "served": {"image_id": 3, "file": "C.jpg"},
            }
        ],
    )
    check_run = tmp_path / "candidates-check"
    out = HM.check_pictures(run, check_run, [served], lambda sid, name: Path("C:/x") / name)
    assert out == {"sites": 1, "pictures": 1, "refused": 0}
    [line] = [json.loads(x) for x in (check_run / "PICTURES.jsonl").read_text().splitlines()]
    assert [c["image_id"] for c in line["candidates"]] == [4]
    [pop] = [json.loads(x) for x in (check_run / "POPULATION.jsonl").read_text().splitlines()]
    assert pop["lat"] == 40.7 and pop["site_id"] == SITE


def test_check_pictures_names_a_row_without_an_offsite_copy(tmp_path: Path) -> None:
    sites = [_site()]
    rows = [_row(1, "A.jpg", hero=True, size=(800, 128)), _row(4, "D.jpg"), _row(5, "F.jpg")]
    run = _hero_moves_run(tmp_path, sites, rows)
    served = tmp_path / "served-image-2026-09-30"
    _write_jsonl(served / "CHECK.jsonl", [])

    def path_of(sid: str, name: str) -> Path:
        if name.startswith("D"):
            raise HM.HeroMovesError("no offsite file")
        return Path("C:/x") / name

    check_run = tmp_path / "candidates-check"
    out = HM.check_pictures(run, check_run, [served], path_of)
    assert out == {"sites": 1, "pictures": 1, "refused": 1}
    [refusal] = [json.loads(x) for x in (check_run / HM.CHECK_REFUSALS).read_text().splitlines()]
    assert refusal["file"] == "D.jpg"


# ------------------------------------------------------------------------------ acceptance
def test_accept_reads_production_and_names_every_deviation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, served = _fixture(tmp_path)
    HM.write_plan(run, [served], [])
    good_sites = [
        {
            "id": SITE,
            "thumbnail_url": "/data/images/wiki/11111111/C.webp",
            "source_id": "ancient_nerds",
        }
    ]
    good_images = [
        {
            "id": 1,
            "site_id": SITE,
            "is_hero": False,
            "is_lead": False,
            "is_excluded": False,
            "sort_order": 0,
            "filename": "A.webp",
        },
        {
            "id": 2,
            "site_id": SITE,
            "is_hero": False,
            "is_lead": False,
            "is_excluded": False,
            "sort_order": 0,
            "filename": "B.webp",
        },
        {
            "id": 3,
            "site_id": SITE,
            "is_hero": True,
            "is_lead": False,
            "is_excluded": False,
            "sort_order": 0,
            "filename": "C.webp",
        },
    ]
    answers = iter([good_sites, good_images])
    monkeypatch.setattr(CW.pv, "read_rows", lambda sql: next(answers))
    assert HM.accept(run, run / "chunks" / "chunk-001")["deviations"] == []
    bad_images = [dict(r, is_hero=r["id"] == 1) for r in good_images]
    answers = iter([good_sites, bad_images])
    found = HM.accept(run, run / "chunks" / "chunk-001")["deviations"]
    assert found and "serves image 1" in found[0]
