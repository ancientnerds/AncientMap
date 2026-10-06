"""The candidate search (owner decision 2026-10-06): a name the Commons answers with pictures.

DB-less and offline: the Commons client is a stub whose answers are dictionaries, exactly as
`test_served_image.FakeCommons` answers the three questions of that lane. What is measured here is
the search's own discipline - which questions it asks, which candidates it keeps, and the four ways
it refuses a site by name.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts" / "remediation"))

from candidate_search import search as CS  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from served_image import commons as CM  # noqa: E402

FLOOR = (IH.OWNER_FLOOR_WIDTH, IH.OWNER_FLOOR_HEIGHT)

MONTE = "0d9bd81d-d41c-4381-8e2e-7626928fedc1"
GONNUS = "25cf40c9-4d5a-4818-9d6a-254bc7e097a7"
YMARKA = "217b6292-d8ee-403b-a8ad-236304ac481d"


class FakeCommons:
    """The four questions the search asks, answered from dictionaries - no network."""

    def __init__(
        self,
        *,
        hits: dict[str, list[str]] | None = None,
        members: dict[str, list[str]] | None = None,
        info: dict[str, dict[str, Any]] | None = None,
        sizes: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self.hits = hits or {}
        self.member_map = members or {}
        self.info = info or {}
        self.boxes = sizes or {}
        self.asked: list[str] = []

    def search(self, term: str, limit: int) -> list[str]:
        self.asked.append(term)
        return self.hits.get(term, [])[:limit]

    def members(self, category: str, limit: int) -> list[str]:
        self.asked.append(f"category:{category}")
        return self.member_map.get(category, [])[:limit]

    def imageinfo(self, files: Any) -> dict[str, dict[str, Any]]:
        return {f: self.info.get(f, {"status": CM.MISSING}) for f in files}

    def sizes(self, files: Any) -> dict[str, tuple[int, int]]:
        return {f: self.boxes.get(f, (0, 0)) for f in files}


def _ok(width: int = 1600, height: int = 1200) -> dict[str, Any]:
    return {
        "status": CM.OK,
        "title": "x",
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/x.jpg",
        "render_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/x.jpg/1280px-x.jpg",
        "mime": "image/jpeg",
    }


def _picture(width: int = 1600, height: int = 1200) -> dict[str, Any]:
    entry = _ok()
    entry["render_url"] = (
        f"https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/{width}px-x.jpg"
    )
    return entry


class TestTheSearches:
    def test_the_free_search_is_asked_for_bitmaps_only(self) -> None:
        """Measured: the same query without `filetype:bitmap` answers scanned books - the five hits
        for *Monte Lazzu* are all PDFs from a library digitisation project."""
        assert CS.terms("Monte Lazzu")[0][0] == "Monte Lazzu filetype:bitmap"

    def test_the_title_search_asks_for_the_name_as_a_title(self) -> None:
        assert CS.terms("Gonnus")[1][0] == 'intitle:"Gonnus" filetype:bitmap'

    def test_a_name_without_text_is_refused_by_name(self) -> None:
        commons = FakeCommons()
        found, reason, detail = CS.candidates(
            commons, {"site_id": MONTE, "name": "   "}, floor=FLOOR
        )
        assert (found, reason) == ([], CS.NO_NAME)
        assert "no name" in detail
        assert commons.asked == []  # nothing was asked of Commons for a site that has no name

    def test_a_name_commons_answers_with_no_file_is_refused_by_name(self) -> None:
        commons = FakeCommons()
        found, reason, detail = CS.candidates(
            commons, {"site_id": YMARKA, "name": "Wamanmarka, Lima"}, floor=FLOOR
        )
        assert (found, reason) == ([], CS.NO_CANDIDATE)
        assert "names no file" in detail

    def test_both_searches_and_the_category_are_asked(self) -> None:
        commons = FakeCommons()
        CS.candidates(commons, {"site_id": GONNUS, "name": "Gonnus"}, floor=FLOOR)
        assert commons.asked == [
            "Gonnus filetype:bitmap",
            'intitle:"Gonnus" filetype:bitmap',
            "category:Gonnus",
        ]

    def test_a_file_the_gallery_already_holds_is_never_a_candidate(self) -> None:
        commons = FakeCommons(
            hits={"Gonnus filetype:bitmap": ["Gonnus.jpg"]},
            info={"Gonnus.jpg": _picture()},
            sizes={"Gonnus.jpg": (4000, 3000)},
        )
        found, reason, _ = CS.candidates(
            commons, {"site_id": GONNUS, "name": "Gonnus"}, floor=FLOOR, exclude=["Gonnus.jpg"]
        )
        assert (found, reason) == ([], CS.NOT_A_PICTURE)
        assert "Gonnus.jpg" not in commons.asked


class TestTheFloor:
    def test_a_candidate_under_the_floor_is_not_offered(self) -> None:
        """The owner's floor of 2026-10-06 (800x300), measured over the rest inventory: the files
        this search would offer are the site's own, and a 799 px one is not a hero."""
        commons = FakeCommons(
            hits={"Apazzu filetype:bitmap": ["Apazzu.jpg"]},
            info={"Apazzu.jpg": _picture()},
            sizes={"Apazzu.jpg": (799, 1200)},
        )
        found, reason, detail = CS.candidates(
            commons, {"site_id": "x", "name": "Apazzu"}, floor=FLOOR
        )
        assert (found, reason) == ([], CS.ALL_TOO_SMALL)
        assert "800x300" in detail

    def test_a_candidate_of_exactly_the_floor_is_offered(self) -> None:
        commons = FakeCommons(
            hits={"Apazzu filetype:bitmap": ["Apazzu.jpg"]},
            info={"Apazzu.jpg": _picture()},
            sizes={"Apazzu.jpg": FLOOR},
        )
        found, reason, _ = CS.candidates(commons, {"site_id": "x", "name": "Apazzu"}, floor=FLOOR)
        assert reason == ""
        assert (found[0]["width"], found[0]["height"]) == FLOOR
        # the URL the judge will look at and the fetch will download is Commons' own rendering
        assert found[0]["picture_url"] == _picture()["render_url"]
        assert found[0]["original_url"] == _ok()["url"]

    def test_a_pdfs_rendering_is_not_a_picture(self) -> None:
        commons = FakeCommons(
            hits={"Yarrowbury filetype:bitmap": ["Yarrowbury.pdf"]},
            info={
                "Yarrowbury.pdf": {"status": CM.OK, "title": "Yarrowbury.pdf", "render_url": None}
            },
            sizes={"Yarrowbury.pdf": (3000, 4000)},
        )
        found, reason, _ = CS.candidates(
            commons, {"site_id": "x", "name": "Yarrowbury"}, floor=FLOOR
        )
        assert (found, reason) == ([], CS.NOT_A_PICTURE)

    def test_the_owner_s_floor_is_the_pair_measured_over_the_inventory(self) -> None:
        assert FLOOR == (800, 300)


class TestTheRun:
    def test_the_run_counts_what_it_found_and_refuses_the_rest_by_name(
        self, tmp_path: Path
    ) -> None:
        commons = FakeCommons(
            hits={"Gonnus filetype:bitmap": ["Gonnus.jpg", "Gonnus 2.jpg"]},
            members={"Cerna": ["Cerna.jpg"]},
            info={
                "Gonnus.jpg": _picture(4000, 3000),
                "Gonnus 2.jpg": _picture(2576, 1952),
                "Cerna.jpg": _picture(4288, 2848),
            },
            sizes={
                "Gonnus.jpg": (4000, 3000),
                "Gonnus 2.jpg": (2576, 1952),
                "Cerna.jpg": (4288, 2848),
            },
        )
        summary = CS.run(
            tmp_path,
            [
                {"site_id": GONNUS, "name": "Gonnus", "country": "Italy"},
                {"site_id": YMARKA, "name": "Wamanmarka, Lima", "country": "Peru"},
                {"site_id": MONTE, "name": "", "country": "Italy"},
            ],
            commons,
            floor=FLOOR,
        )
        assert summary["sites"] == 3
        assert summary["sites_with_candidates"] == 1
        assert summary["candidates"] == 2
        assert summary["refused_sites"] == 2
        assert summary["refusals"] == {CS.NO_CANDIDATE: 1, CS.NO_NAME: 1}
        rows = (tmp_path / CS.CANDIDATES).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 1
        assert '"why"' in rows[0]

    def test_a_site_the_commons_answers_from_its_category_is_a_candidate_too(
        self, tmp_path: Path
    ) -> None:
        """The name-as-category route measured 0 still pictures on 9 of 10 sample sites - kept
        anyway, because a category is named after the site and a search only matches words."""
        commons = FakeCommons(
            members={"Apazzu": ["Apazzu.jpg"]},
            info={"Apazzu.jpg": _picture(1800, 1200)},
            sizes={"Apazzu.jpg": (1800, 1200)},
        )
        found, reason, _ = CS.candidates(commons, {"site_id": "x", "name": "Apazzu"}, floor=FLOOR)
        assert reason == ""
        assert "category" in found[0]["why"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
