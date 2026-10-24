"""D59 (owner decision of 2026-10-24): the shown sites whose only picture is a hotlinked thumbnail.

DB-less and offline: the two populations (third-party hotlinks join the D17 research, Commons hotlinks
get a credited row of the same file), the one candidate per Commons site and every refusal by name,
the D59 wording and marker of the INSERT claim, the INSERT plan's lift of the thumbnail-only rule
(only for the claimed thumbnail and only for that very file), and the NULL plan of the third-party
thumbnails - when no research found a picture (only once the research is finished) or the INSERT lane
refused the confirmed one for good, and never for a site whose INSERT has not ended -, the D59 run's
way past the prefilter to the depicts role, the per-site outcomes and owner list, and the write
order (nothing is written before the Commons answers are in).
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
from candidate_search import judge as CJ  # noqa: E402
from candidate_search import population as PP  # noqa: E402
from gallery_audit import chunk_writer as CW  # noqa: E402
from image_roles import d59 as D59  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from import_hero import insert as IN  # noqa: E402
from served_image import commons as CM  # noqa: E402
from served_image import state as ST  # noqa: E402

SITE = "11111111-1111-4111-8111-111111111111"
SITE_B = "22222222-2222-4222-8222-222222222222"
FILE = "Monte Lazzu dolmen.jpg"
UPLOAD = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Monte_Lazzu_dolmen.jpg"
THUMB = (
    "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Monte_Lazzu_dolmen.jpg/"
    "400px-Monte_Lazzu_dolmen.jpg"
)
BLOG = "https://1.bp.blogspot.com/x/Monte.jpg"


# --------------------------------------------------------------------------- the populations
@pytest.mark.parametrize(
    ("url", "commons", "third_party"),
    [
        (UPLOAD, True, False),
        (THUMB, True, False),
        (BLOG, False, True),
        ("https://www.megalithic.co.uk/a312/x.jpg", False, True),
        ("https://upload.wikimedia.org/wikipedia/en/a/ab/Fair_use.jpg", False, True),
        ("/data/images/wiki/11111111/x.webp", False, False),
        ("", False, False),
        (None, False, False),
    ],
)
def test_a_thumbnail_is_commons_third_party_or_neither(
    url: str | None, commons: bool, third_party: bool
) -> None:
    assert PP.is_commons_thumbnail(url) is commons
    assert PP.is_third_party_thumbnail(url) is third_party


def test_the_research_population_takes_the_third_party_hotlinks() -> None:
    sql = PP.population_sql()
    assert "coalesce(u.thumbnail_url, '') = '' OR" in sql
    assert PP.third_party_thumbnail_sql() in sql
    assert "u.thumbnail_url," in sql


def test_the_commons_population_takes_the_hotlinked_commons_files_only() -> None:
    sql = PP.population_sql(kind=PP.COMMONS_THUMBNAIL)
    assert PP.commons_thumbnail_sql() in sql
    assert "coalesce(u.thumbnail_url, '') = ''" not in sql
    assert (
        "NOT EXISTS (SELECT 1 FROM wiki_images w WHERE w.site_id = u.id AND NOT w.is_excluded)"
        in sql
    )
    with pytest.raises(PP.PopulationError):
        PP.population_sql(kind="everything")


def test_a_population_line_carries_the_thumbnail_it_serves() -> None:
    line = {
        "site_id": SITE, "name": "Monte Lazzu", "country": "France", "site_type": "Dolmen",
        "lat": 42.0, "lon": 8.7, "description": "", "qids": [], "enwiki_titles": [],
        "coord_kind": None, "coord_marker_current": False, "rows": [], "thumbnail_url": BLOG,
    }  # fmt: skip
    assert PP.site_record(line)["thumbnail_url"] == BLOG
    assert PP.site_record(line | {"thumbnail_url": ""})["thumbnail_url"] is None
    assert PP.counts([PP.site_record(line)])["third_party_thumbnail"] == 1


# --------------------------------------------------------------------- the Commons candidates
class FakeCommons:
    def __init__(self, info: dict[str, Any], sizes: dict[str, tuple[int, int]]) -> None:
        self.info, self.boxes = info, sizes

    def imageinfo(self, files: Any) -> dict[str, Any]:
        return {f: self.info[f] for f in files}

    def sizes(self, files: Any) -> dict[str, tuple[int, int]]:
        return {f: self.boxes[f] for f in files}


def _ok(file: str, **over: Any) -> dict[str, Any]:
    return {
        "status": CM.OK,
        "title": file,
        "url": UPLOAD,
        "render_url": "https://upload.wikimedia.org/thumb/1280px-x.jpg",
        "mime": "image/jpeg",
    } | over


def _site(sid: str = SITE, thumb: str = THUMB, held: list[str] | None = None) -> dict[str, Any]:
    return {"site_id": sid, "name": "Monte Lazzu", "country": "France", "thumbnail_url": thumb,
            "held_files": held or []}  # fmt: skip


def test_the_one_candidate_is_the_thumbnails_own_file() -> None:
    commons = FakeCommons({FILE: _ok(FILE)}, {FILE: (2000, 1500)})
    lines, refusals = D59.commons_candidates([_site()], commons, floor=(800, 300))
    assert not refusals
    [candidate] = lines[0]["candidates"]
    assert (candidate["file"], candidate["route"], candidate["original_url"]) == (
        FILE,
        D59.ROUTE,
        UPLOAD,
    )
    assert candidate["picture_url"] == "https://upload.wikimedia.org/thumb/1280px-x.jpg"


@pytest.mark.parametrize(
    ("info", "size", "held", "reason"),
    [
        ({"status": CM.MISSING}, (0, 0), [], "missing_on_commons"),
        (_ok(FILE, title="Renamed.jpg"), (2000, 1500), [], "renamed_on_commons"),
        (_ok(FILE, mime="application/pdf"), (2000, 1500), [], "not_a_still_picture"),
        (_ok(FILE), (2000, 1500), [FILE], "an_excluded_row_holds_the_file"),
        (_ok(FILE), (640, 480), [], "all_too_small"),
    ],
)
def test_every_refusal_is_named(
    info: dict[str, Any], size: tuple[int, int], held: list[str], reason: str
) -> None:
    commons = FakeCommons({FILE: info}, {FILE: size})
    lines, refusals = D59.commons_candidates([_site(held=held)], commons, floor=(800, 300))
    assert not lines and [r["reason"] for r in refusals] == [reason]


def test_a_site_that_is_no_commons_hotlink_is_refused() -> None:
    with pytest.raises(D59.D59Error, match="no hotlinked Commons file"):
        D59.commons_candidates([_site(thumb=BLOG)], FakeCommons({}, {}), floor=(800, 300))


def test_the_candidate_run_is_written_once(tmp_path: Path) -> None:
    rows = [
        {"site_id": SITE, "name": "Monte Lazzu", "country": "France", "site_type": "Dolmen",
         "lat": 42.0, "lon": 8.7, "description": "", "qids": [], "enwiki_titles": [],
         "coord_kind": None, "coord_marker_current": False, "rows": [], "thumbnail_url": THUMB},
    ]  # fmt: skip
    commons = FakeCommons({FILE: _ok(FILE)}, {FILE: (2000, 1500)})
    summary = D59.write_candidates(tmp_path, rows, commons, floor=(800, 300))
    assert summary["candidates"] == 1 and summary["decision"] == "D59"
    for name in (PP.POPULATION_FILE, "CANDIDATES.jsonl", "CANDIDATE_REFUSALS.jsonl", D59.MARKER):
        assert (tmp_path / name).is_file()
    with pytest.raises(D59.D59Error, match="never replaced"):
        D59.write_candidates(tmp_path, rows, commons, floor=(800, 300))


# ------------------------------------------------------------------------ the INSERT claims
def _claims_run(tmp_path: Path, thumb: str | None, file: str = FILE) -> Path:
    out = tmp_path / "candidates"
    out.mkdir()
    target = {"site_id": SITE, "commons_file": file}
    (out / CJ.TARGETS).write_text(json.dumps(target) + "\n", encoding="utf-8")
    (out / CJ.VERDICTS).write_text(
        json.dumps({"site_id": SITE, "file": file, "verdict": CJ.DEPICTS, "model": OH.SONNET_MODEL})
        + "\n",
        encoding="utf-8",
    )
    (out / CJ.CANDIDATES).write_text(
        json.dumps(
            {
                "site_id": SITE,
                "candidates": [
                    {"file": file, "original_url": UPLOAD if file == FILE else UPLOAD + "x"}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (out / PP.POPULATION_FILE).write_text(
        json.dumps({"site_id": SITE, "thumbnail_url": thumb}) + "\n", encoding="utf-8"
    )
    return out


def _refusals(insert_run: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (insert_run / "IMPORT_HERO_REFUSALS.jsonl").read_text().splitlines()
    ]


def test_a_commons_thumbnail_claim_is_worded_and_marked_d59(tmp_path: Path) -> None:
    out = _claims_run(tmp_path, THUMB)
    CJ.insert_claims(out, tmp_path / "insert")
    [refusal] = _refusals(tmp_path / "insert")
    assert refusal["decision"] == CJ.D59 and refusal["thumbnail_url"] == THUMB
    assert "D59" in refusal["source"] and "showed nothing at all" not in refusal["source"]


def test_a_third_party_thumbnail_claim_is_worded_as_a_replacement(tmp_path: Path) -> None:
    out = _claims_run(tmp_path, BLOG)
    CJ.insert_claims(out, tmp_path / "insert")
    [refusal] = _refusals(tmp_path / "insert")
    assert refusal["decision"] == CJ.D59 and "third-party" in refusal["source"]


def test_a_commons_thumbnail_site_never_claims_another_file(tmp_path: Path) -> None:
    out = _claims_run(tmp_path, THUMB, file="Some other file.jpg")
    result = CJ.insert_claims(out, tmp_path / "insert")
    assert [r["reason"] for r in result["refused_targets"]] == ["d59_not_the_thumbnail_file"]
    assert _refusals(tmp_path / "insert") == []


def test_a_site_without_a_thumbnail_keeps_the_first_row_wording(tmp_path: Path) -> None:
    out = _claims_run(tmp_path, None)
    CJ.insert_claims(out, tmp_path / "insert")
    [refusal] = _refusals(tmp_path / "insert")
    assert "decision" not in refusal and "showed nothing at all" in refusal["source"]


# --------------------------------------------------------------------- the INSERT plan's lift
VALUES = {
    "filename": "Monte Lazzu dolmen.webp",
    "original_url": UPLOAD,
    "commons_page_url": "https://commons.wikimedia.org/wiki/File:Monte_Lazzu_dolmen.jpg",
    "title": "Monte Lazzu dolmen",
    "author": "A. Photographer",
    "author_url": "",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
    "width": "1600",
    "height": "1200",
    "file_size_bytes": "548938",
}


def _state(thumb: str | None) -> ST.State:
    site = {"id": SITE, "name": "Monte Lazzu", "thumbnail_url": thumb}
    return ST.State(
        read_at="now", sites={SITE: site}, rows={SITE: ()}, retired=frozenset(), sha256="0" * 64
    )


def _d59(thumb: str) -> dict[str, Any]:
    return {"site_id": SITE, "reason": "no_target_row", "decision": IN.D59, "thumbnail_url": thumb,
            "source": "D59 wording", "evidence_source": "D59 check"}  # fmt: skip


def test_without_d59_a_thumbnail_only_site_keeps_the_2026_10_05_rule() -> None:
    planned = IN.plan(
        _state(THUMB), [{"site_id": SITE, "reason": "no_target_row"}], fetched={SITE: VALUES}
    )
    assert [r.reason for r in planned.refusals] == ["no_row_at_all"]


def test_d59_lifts_the_rule_for_the_same_commons_file() -> None:
    planned = IN.plan(_state(THUMB), [_d59(THUMB)], fetched={SITE: VALUES})
    assert not planned.refusals
    [row] = planned.inserts
    assert row.old_thumbnail == THUMB
    assert row.new_thumbnail == "/data/images/wiki/11111111/Monte Lazzu dolmen.webp"
    assert row.reason == "D59 wording"


def test_d59_never_lifts_it_for_another_file() -> None:
    other = dict(VALUES, original_url=UPLOAD.replace("Monte_Lazzu", "Other"))
    planned = IN.plan(_state(THUMB), [_d59(THUMB)], fetched={SITE: other})
    assert [r.reason for r in planned.refusals] == ["d59_not_the_thumbnail_file"]


def test_d59_never_lifts_it_once_the_thumbnail_moved() -> None:
    planned = IN.plan(_state(UPLOAD), [_d59(THUMB)], fetched={SITE: VALUES})
    assert [r.reason for r in planned.refusals] == ["d59_thumbnail_moved"]


def test_d59_replaces_a_third_party_thumbnail_with_the_confirmed_file() -> None:
    planned = IN.plan(_state(BLOG), [_d59(BLOG)], fetched={SITE: VALUES})
    assert not planned.refusals and planned.inserts[0].old_thumbnail == BLOG


def test_d59_covers_no_local_thumbnail() -> None:
    local = "/data/images/wiki/11111111/x.webp"
    planned = IN.plan(_state(local), [_d59(local)], fetched={SITE: VALUES})
    assert [r.reason for r in planned.refusals] == ["d59_not_a_hotlink"]


# --------------------------------------------------------------------------- the NULL plan
def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _research(tmp_path: Path, *, targets: list[dict[str, Any]], refused: bool = False) -> Path:
    run = tmp_path / "candidates-2026-10-25"
    run.mkdir()
    _write(
        run / PP.POPULATION_FILE,
        [{"site_id": SITE, "thumbnail_url": BLOG}, {"site_id": SITE_B, "thumbnail_url": BLOG}],
    )
    _write(run / CJ.TARGETS, targets)
    _write(
        run / "CANDIDATE_REFUSALS.jsonl",
        [{"site_id": SITE_B, "reason": "no_candidate", "detail": "Commons names no file"}],
    )
    _write(
        run / CJ.CANDIDATES, [] if refused else [{"site_id": SITE, "candidates": [{"file": FILE}]}]
    )
    return run


def _null_run(tmp_path: Path, sites: list[dict[str, Any]]) -> Path:
    run = tmp_path / "d59-thumb-2026-10-26"
    run.mkdir()
    (run / "READ.json").write_text(json.dumps({"read_at": "now", "sites": sites}), encoding="utf-8")
    return run


def _prefilter(monkeypatch: pytest.MonkeyPatch, survives: bool | None) -> None:
    rows = [] if survives is None else [{"site_id": SITE, "file": FILE, "survives": survives}]
    monkeypatch.setattr(D59.SG, "read_results", lambda run, spec: [])
    monkeypatch.setattr(PF, "judged", lambda results: rows)


def _insert_run(
    tmp_path: Path,
    *,
    refusal: str | None = None,
    planned: bool = False,
    fetch_failure: str | None = None,
    claimed: str = UPLOAD,
    name: str = "insert-2026-10-25-d17",
) -> Path:
    """An INSERT run of the INSERT lane that claims `claimed` for SITE and planned or refused it."""
    run = tmp_path / name
    _write(
        run / D59.INSERT_SEEDS,
        [{"site_id": SITE, "reason": "no_target_row", "decision": IN.D59, "thumbnail_url": BLOG}],
    )
    (run / D59.INSERT_CLAIMS).write_text(json.dumps({SITE: {"image": claimed}}), encoding="utf-8")
    if planned:
        _write(run / "chunk-001" / "INSERT.jsonl", [{"site_id": SITE}])
    if refusal is not None or planned:
        refusals = [] if refusal is None else [{"site_id": SITE, "reason": refusal, "detail": "d"}]
        _write(run / D59.INSERT_REFUSALS, refusals)
    if fetch_failure is not None:
        _write(
            run / D59.FETCH_FAILURES,
            [{"site_id": SITE, "commons_file": FILE, "why": fetch_failure}],
        )
    return run


def test_a_site_whose_research_found_nothing_is_emptied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=False)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG},
                               {"id": SITE_B, "name": "B", "thumbnail_url": BLOG}])  # fmt: skip
    summary = D59.null_plan(run, [research])
    assert summary["cleared"] == 2
    assert summary["cleared_by"] == {D59.NONE_CONFIRMED: 1, D59.NO_CANDIDATE: 1}
    chunk = CW.check_delivered(run / "chunks" / "chunk-001")
    assert {(c.old_value, c.new_value, c.rule) for c in chunk.changes} == {
        (BLOG, None, D59.RULE_NULL)
    }
    reasons = {c.site_id: c.evidence[0]["outcome"] for c in chunk.changes}
    assert reasons == {SITE: D59.NONE_CONFIRMED, SITE_B: D59.NO_CANDIDATE}


@pytest.mark.parametrize(
    ("insert", "match"),
    [
        ({}, "not_claimed"),
        ({"planned": True}, "planned"),
        ({"refusal": None}, "not_planned"),
        ({"refusal": "not_fetched"}, "never fetched"),
    ],
)
def test_a_confirmed_site_the_insert_lane_has_not_ended_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, insert: dict[str, Any], match: str
) -> None:
    research = _research(tmp_path, targets=[{"site_id": SITE, "commons_file": FILE}])
    _prefilter(monkeypatch, survives=True)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    runs = [] if not insert else [_insert_run(tmp_path, **insert)]
    with pytest.raises(D59.D59Error, match=match):
        D59.null_plan(run, [research], runs)
    assert not (run / "chunks").exists()


def test_a_confirmed_site_whose_insert_was_refused_for_good_is_emptied_with_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[{"site_id": SITE, "commons_file": FILE}])
    _prefilter(monkeypatch, survives=True)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    insert = _insert_run(
        tmp_path, refusal="not_fetched", fetch_failure="the fetch failed: no author"
    )
    summary = D59.null_plan(run, [research], [insert])
    assert summary["cleared_by"] == {"insert_refused:not_fetched": 1}
    [change] = CW.check_delivered(run / "chunks" / "chunk-001").changes
    assert change.new_value is None and "INSERT lane refused it" in change.reason
    [proof] = [e for e in change.evidence if e["source"].startswith("import_hero/")]
    assert proof["insert_refusal"] == "not_fetched"
    assert proof["fetch_failure"] == "the fetch failed: no author"


def test_an_insert_refusal_about_another_state_of_the_site_empties_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[{"site_id": SITE, "commons_file": FILE}])
    _prefilter(monkeypatch, survives=True)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    insert = _insert_run(tmp_path, refusal="d59_thumbnail_moved")
    with pytest.raises(D59.D59Error, match="another state of the site"):
        D59.null_plan(run, [research], [insert])


def test_an_insert_claim_of_another_file_or_by_two_runs_is_refused(
    tmp_path: Path,
) -> None:
    other = _insert_run(tmp_path, refusal="not_fetched", claimed=UPLOAD.replace("Monte", "Other"))
    with pytest.raises(D59.D59Error, match="not the research's"):
        D59.insert_state([other], SITE, FILE)
    one = _insert_run(tmp_path, refusal="not_fetched", name="insert-a")
    two = _insert_run(tmp_path, refusal="not_fetched", name="insert-b")
    with pytest.raises(D59.D59Error, match="two INSERT runs"):
        D59.insert_state([one, two], SITE, FILE)


def test_the_null_plan_refuses_a_thumbnail_the_research_did_not_see(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=False)
    other = "https://www.megalithic.co.uk/a312/x.jpg"
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": other}])
    with pytest.raises(D59.D59Error, match="researched the site while it showed"):
        D59.null_plan(run, [research])


def test_an_unfinished_research_empties_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=None)  # no prefilter answer for the candidate
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    with pytest.raises(D59.D59Error, match="no prefilter answer"):
        D59.null_plan(run, [research])
    assert not (run / "chunks").exists()
    (research / CJ.TARGETS).unlink()
    with pytest.raises(D59.D59Error, match="not finished"):
        D59.research_outcome(research, SITE)


def test_a_survivor_without_a_depicts_verdict_empties_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=True)
    with pytest.raises(D59.D59Error, match="no depicts verdict"):
        D59.research_outcome(research, SITE)


def test_the_null_plan_refuses_a_site_no_research_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=False)
    other = "33333333-3333-4333-8333-333333333333"
    run = _null_run(tmp_path, [{"id": other, "name": "C", "thumbnail_url": BLOG}])
    with pytest.raises(D59.D59Error, match="no research run holds"):
        D59.null_plan(run, [research])


def test_the_null_plan_refuses_a_thumbnail_that_is_no_third_party_hotlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=False)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": THUMB}])
    with pytest.raises(D59.D59Error, match="no third-party thumbnail"):
        D59.null_plan(run, [research])


def test_a_delivered_null_plan_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=False)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    D59.null_plan(run, [research])
    with pytest.raises(D59.D59Error, match="holds a plan already"):
        D59.null_plan(run, [research])


def test_the_null_lane_is_named_by_its_run_directory(tmp_path: Path) -> None:
    assert D59.lane_for(tmp_path / "d59-thumb-2026-10-26").stamp == "d59-thumb-2026-10-26"
    with pytest.raises(D59.D59Error):
        D59.lane_for(tmp_path / "d59-2026-10-26")


def test_the_null_accept_names_a_thumbnail_that_is_still_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=False)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    D59.null_plan(run, [research])
    answers = iter([[{"id": SITE, "thumbnail_url": BLOG, "source_id": "ancient_nerds"}], []])
    monkeypatch.setattr(CW.pv, "read_rows", lambda sql: next(answers))
    found = D59.null_accept(run, run / "chunks" / "chunk-001")["deviations"]
    assert found and "thumbnail_url" in found[0]


# ------------------------------------------------------------- the D59 run: no prefilter, outcomes
SITE_C = "33333333-3333-4333-8333-333333333333"


def _d59_run(tmp_path: Path) -> Path:
    """A D59 candidate run: SITE confirmed, SITE_B below the floor, SITE_C judged not depicts."""
    run = tmp_path / "candidates-2026-10-25-d59"
    _write(
        run / PP.POPULATION_FILE,
        [
            {"site_id": s, "name": s[:4], "thumbnail_url": THUMB, "lat": 42.0, "lon": 8.7}
            for s in (SITE, SITE_B, SITE_C)
        ],
    )
    (run / D59.MARKER).write_text("{}", encoding="utf-8")
    _write(run / CJ.TARGETS, [{"site_id": SITE, "commons_file": FILE}])
    _write(
        run / "CANDIDATE_REFUSALS.jsonl",
        [{"site_id": SITE_B, "reason": "all_too_small", "detail": "640x480, below 800x300"}],
    )
    _write(
        run / CJ.CANDIDATES,
        [{"site_id": s, "candidates": [{"file": FILE}]} for s in (SITE, SITE_C)],
    )
    _write(
        run / CJ.VERDICTS,
        [
            {"site_id": SITE, "file": FILE, "verdict": "depicts"},
            {"site_id": SITE_C, "file": FILE, "verdict": "region_or_type"},
        ],
    )
    return run


def test_a_d59_run_needs_no_prefilter_answer(tmp_path: Path) -> None:
    run = _d59_run(tmp_path)
    assert D59.research_outcome(run, SITE_C) == (
        D59.NONE_CONFIRMED,
        "1 candidate(s): 1 not depicts",
    )


def test_a_d59_run_goes_straight_to_the_depicts_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from image_roles import flow as FL

    run = _d59_run(tmp_path)
    _write(
        run / FL.PICTURES,
        [{"site_id": SITE, "name": "A", "candidates": [{"file": FILE, "path": "x.jpg"}]}],
    )
    with pytest.raises(FL.FlowError, match="straight to depicts-export"):
        FL.prefilter_export(run, tmp_path / "handoff")
    asked: list[Any] = []

    def build(sites: Any, read: Any) -> tuple[list[Any], dict[str, Any], list[Any]]:
        asked.extend(sites)
        return [], {}, []

    monkeypatch.setattr(FL.DP, "build_questions", build)
    monkeypatch.setattr(FL.SG, "export", lambda *a: {})
    monkeypatch.setattr(FL.PF, "judged", lambda results: pytest.fail("the prefilter was read"))
    FL.depicts_export(run, tmp_path / "handoff", cache=None)
    assert [(s["site_id"], [c["file"] for c in s["candidates"]]) for s in asked] == [(SITE, [FILE])]


def test_the_outcomes_name_every_site_that_keeps_its_uncredited_hotlink(tmp_path: Path) -> None:
    run = _d59_run(tmp_path)
    summary = D59.outcomes(run)
    assert summary["sites"] == 3 and summary["owner_list"] == 2
    owner = {
        line["site_id"]: line["reason"]
        for line in map(json.loads, (run / D59.OWNER_LIST).read_text().splitlines())
    }
    assert owner[SITE_B] == D59.FLOOR_QUESTION
    assert owner[SITE_C].startswith(D59.NONE_CONFIRMED)
    lines = [json.loads(x) for x in (run / D59.OUTCOMES).read_text().splitlines()]
    assert {x["site_id"]: x["research"] for x in lines} == {
        SITE: D59.TARGET,
        SITE_B: D59.NO_CANDIDATE,
        SITE_C: D59.NONE_CONFIRMED,
    }


def test_an_insert_refusal_puts_a_confirmed_d59_site_on_the_owner_list(tmp_path: Path) -> None:
    run = _d59_run(tmp_path)
    insert = _insert_run(tmp_path, refusal="already_holds_the_file")
    summary = D59.outcomes(run, [insert])
    assert summary["outcomes"]["target:refused"] == 1 and summary["owner_list"] == 3
    planned = _insert_run(tmp_path, planned=True, name="insert-planned")
    assert D59.outcomes(run, [planned])["owner_list"] == 2


def test_outcomes_need_a_d59_run(tmp_path: Path) -> None:
    research = _research(tmp_path, targets=[])
    with pytest.raises(D59.D59Error, match="no D59 candidate run"):
        D59.outcomes(research)


def test_a_commons_failure_leaves_no_candidate_run_behind(tmp_path: Path) -> None:
    class Down:
        def imageinfo(self, files: Any) -> dict[str, Any]:
            raise CM.CommonsError("HTTP 503")

        def sizes(self, files: Any) -> dict[str, Any]:
            raise AssertionError("not reached")

    rows = [
        {"site_id": SITE, "name": "Monte Lazzu", "country": "France", "site_type": "Dolmen",
         "lat": 42.0, "lon": 8.7, "description": "", "qids": [], "enwiki_titles": [],
         "coord_kind": None, "coord_marker_current": False, "rows": [], "thumbnail_url": THUMB},
    ]  # fmt: skip
    with pytest.raises(CM.CommonsError):
        D59.write_candidates(tmp_path, rows, Down(), floor=(800, 300))
    assert list(tmp_path.iterdir()) == []
