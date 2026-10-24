"""D59 (owner decision of 2026-10-24): the shown sites whose only picture is a hotlinked thumbnail.

DB-less and offline: the two populations (third-party hotlinks join the D17 research, Commons hotlinks
get a credited row of the same file), the one candidate per Commons site and every refusal by name,
the D59 wording and marker of the INSERT claim, the INSERT plan's lift of the thumbnail-only rule
(only for the claimed thumbnail and only for that very file), and the NULL plan of the third-party
thumbnails no research found a picture for - which waits for a finished research.
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
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _research(tmp_path: Path, *, targets: list[dict[str, Any]], refused: bool = False) -> Path:
    run = tmp_path / "candidates-2026-10-25"
    run.mkdir()
    _write(run / PP.POPULATION_FILE, [{"site_id": SITE}, {"site_id": SITE_B}])
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


def test_a_site_whose_research_found_nothing_is_emptied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=False)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG},
                               {"id": SITE_B, "name": "B", "thumbnail_url": BLOG}])  # fmt: skip
    summary = D59.null_plan(run, [research])
    assert summary["cleared"] == 2 and summary["pending_insert"] == 0
    chunk = CW.check_delivered(run / "chunks" / "chunk-001")
    assert {(c.old_value, c.new_value, c.rule) for c in chunk.changes} == {
        (BLOG, None, D59.RULE_NULL)
    }
    reasons = {c.site_id: c.evidence[0]["outcome"] for c in chunk.changes}
    assert reasons == {SITE: D59.NONE_CONFIRMED, SITE_B: D59.NO_CANDIDATE}


def test_a_site_with_a_target_waits_for_the_insert_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[{"site_id": SITE, "commons_file": FILE}])
    _prefilter(monkeypatch, survives=True)
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    summary = D59.null_plan(run, [research])
    assert summary["cleared"] == 0 and summary["pending_insert"] == 1


def test_an_unfinished_research_empties_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research = _research(tmp_path, targets=[])
    _prefilter(monkeypatch, survives=None)  # no prefilter answer for the candidate
    run = _null_run(tmp_path, [{"id": SITE, "name": "A", "thumbnail_url": BLOG}])
    with pytest.raises(D59.D59Error, match="no prefilter answer"):
        D59.null_plan(run, [research])
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
