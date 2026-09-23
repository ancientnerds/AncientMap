"""Does T09 actually have teeth?

T09's job is to say what has to happen to a site's hero, using dimensions the snapshot does
not carry. These tests feed it synthetic sites whose truth is known by construction - a hero
stuck at the 800 px export cap, a local 1600x900 image waiting for the flag, an original too
small to ever be a hero, a Commons file that is gone - and assert that it says so. A check
that reports zero findings is indistinguishable from a broken one, and a check that flags a
site whose hero is already fine is worse: it buries the real repairs.

They are deliberately not end-to-end: no snapshot, no network. The index the collector folds
from `imageinfo` is written by hand here, which is also how the partial-response behaviour
(Commons answers only for the titles it recognises) is pinned down.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402

EXPORTED_AT = "2026-09-20T20:20:01+02:00"

#: A Commons original big enough for a 1600 px hero with a 900 px short side.
BIG = (6000, 4500)


def _img(
    img_id: int,
    site_id: str,
    name: str,
    *,
    width: int | None,
    height: int | None,
    hero: bool = False,
    excluded: bool = False,
    sort_order: int | None = None,
    lead: bool | None = None,
    local_path: bool = False,
    commons_page_url: str | None = None,
) -> dict[str, Any]:
    """One wiki_images row, in the shape the check reads."""
    original = (
        f"/data/images/wiki/{site_id[:8]}/{name}"
        if local_path
        else f"https://upload.wikimedia.org/wikipedia/commons/4/4f/{name}"
    )
    return {
        "id": img_id,
        "site_id": site_id,
        "filename": name.replace("_", " "),
        "original_url": original,
        "commons_page_url": commons_page_url
        if commons_page_url is not None
        else (None if local_path else f"https://commons.wikimedia.org/wiki/File%3A{name}"),
        "thumb_width": None,
        "author": None if local_path else "Someone",
        "author_url": None,
        "license": None if local_path else "CC BY-SA 4.0",
        "license_url": None,
        "title": name.replace("_", " "),
        "is_hero": hero,
        "is_lead": lead if lead is not None else hero,
        "sort_order": sort_order if sort_order is not None else (0 if hero else 1),
        "source_type": "wikimedia",
        "file_size_bytes": 202862,
        "width": width,
        "height": height,
        "created_at": "2026-03-14T20:18:20",
        "is_excluded": excluded,
    }


def _ok(width: int, height: int, *, size: int = 3416003) -> dict[str, Any]:
    return {
        "status": "ok",
        "canonical": "File:x",
        "width": width,
        "height": height,
        "bytes": size,
        "url": "https://upload.wikimedia.org/wikipedia/commons/4/4f/x.jpg",
    }


def _status(status: str) -> dict[str, Any]:
    return {"status": status, "canonical": None if status != "missing" else "File:x"}


class Harness:
    """The parts of Context the check reads: sites, snapshot rows, and the cache path."""

    def __init__(
        self,
        tmp_path: Path,
        images: list[dict[str, Any]],
        index: dict[str, dict[str, Any]] | None,
        exported_at: str | None = EXPORTED_AT,
    ) -> None:
        by_site: dict[str, list[dict[str, Any]]] = {}
        for row in images:
            by_site.setdefault(str(row["site_id"]), []).append(row)
        site_ids = sorted(by_site) or ["00000000-0000-0000-0000-000000000001"]
        self.sites = [
            {"id": s, "source_id": "ancient_nerds", "name": f"Site {s}"} for s in site_ids
        ]
        self.snap = SimpleNamespace(
            rows=lambda table: images if table == "wiki_images" else [],
            images=lambda sid: by_site.get(str(sid), []),
            exported_at=lambda: exported_at,
        )
        self.cache = tmp_path
        if index is not None:
            (tmp_path / "commons_imageinfo.json").write_text(
                json.dumps(
                    {
                        "api": "x",
                        "iiprop": "size|url|extmetadata",
                        "snapshot_exported_at": exported_at,
                        "entries": index,
                    }
                ),
                encoding="utf-8",
            )


def _index(names: list[tuple[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return dict(names)


@pytest.fixture(scope="module")
def t09():
    import importlib

    return importlib.import_module("census.tests.t09_commons_dimensions")


def _hero_findings(findings: list[M.Finding]) -> list[M.Finding]:
    return [f for f in findings if f.field == "wiki_images.is_hero"]


# ------------------------------------------------------------------ the hero decision
class TestHeroDecision:
    def test_hero_not_best_names_the_flag_move(self, t09, tmp_path):
        """§6.3: the hero is the 800 px export cap, a 1600x900 image is already local."""
        sid = "11111111-1111-1111-1111-111111111111"
        images = [
            _img(1, sid, "hero.webp", width=800, height=600, hero=True),
            _img(2, sid, "gallery.webp", width=1600, height=1200, sort_order=3),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(4272, 2848)),
                    ("gallery.webp", _ok(3000, 2250)),
                ]
            ),
        )
        got = t09.run(ctx)
        hero = _hero_findings(got)
        assert len(hero) == 1, got
        f = hero[0]
        assert f.test_id == "T09/hero-not-best"
        assert f.current_value["replacement_image_id"] == 2
        assert f.proposal is M.Proposal.REVIEW and f.proposed_value is None
        assert not f.applicable, "a two-row flag move is never a single-field auto-write"
        assert f.evidence, "the candidate's own row must be quoted"
        assert "sort_order" in f.note, "the note must say why both rows have to change"

    def test_the_flag_move_prefers_a_backed_image_over_a_larger_upscale(self, t09, tmp_path):
        """A 1600x1200 crop of a 900 px original must not be proposed over a real 1600x900."""
        sid = "16161616-1616-1616-1616-161616161616"
        images = [
            _img(1, sid, "hero.webp", width=800, height=600, hero=True),
            _img(2, sid, "big_fake.webp", width=1600, height=1200, sort_order=2),
            _img(3, sid, "small_real.webp", width=1620, height=1080, sort_order=5),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(4272, 2848)),
                    ("big_fake.webp", _ok(900, 675)),
                    ("small_real.webp", _ok(3240, 2160)),
                ]
            ),
        )
        got = t09.run(ctx)
        hero = [f for f in got if f.test_id == "T09/hero-not-best"]
        assert len(hero) == 1, got
        assert hero[0].current_value["replacement_image_id"] == 3, hero[0].current_value
        assert hero[0].current_value["replacement_is_upscaled"] is False
        assert hero[0].current_value["candidates"] == 2

    def test_a_hero_that_already_meets_the_requirement_is_clean(self, t09, tmp_path):
        """No finding for a site whose hero is 1600x900 - otherwise nothing here is usable."""
        sid = "22222222-2222-2222-2222-222222222222"
        images = [
            _img(1, sid, "hero.webp", width=1600, height=1200, hero=True),
            _img(2, sid, "gallery.webp", width=1600, height=1200, sort_order=2),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(*BIG)),
                    ("gallery.webp", _ok(3000, 2250)),
                ]
            ),
        )
        assert t09.run(ctx) == []

    def test_a_1600x609_strip_is_not_offered_as_the_hero_repair(self, t09, tmp_path):
        """§6.1's "too small" class: the short side is what disqualifies a panorama strip."""
        sid = "33333333-3333-3333-3333-333333333333"
        images = [
            _img(1, sid, "hero.webp", width=800, height=300, hero=True),
            _img(2, sid, "strip.webp", width=1600, height=609, sort_order=2),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(4896, 2752)),
                    ("strip.webp", _ok(7000, 2664)),
                ]
            ),
        )
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/hero-new-fetch"], got
        assert got[0].current_value["largest_original"] == "7000x2664"
        # 7000x2664 is a 1600x609 strip and 4896x2752 rounds to 1600x899: neither original
        # yields a 1600x900 hero, so the local 1600 px file is not the repair either.

    def test_no_local_candidate_but_a_bigger_original_means_redownload(self, t09, tmp_path):
        """The truth decides the work: a re-export fixes it, no new image needed."""
        sid = "44444444-4444-4444-4444-444444444444"
        images = [_img(1, sid, "hero.webp", width=800, height=450, hero=True)]
        ctx = Harness(tmp_path, images, _index([("hero.webp", _ok(3456, 1944))]))
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/hero-redownload"], got
        assert got[0].proposal is M.Proposal.REVIEW
        assert "1600x900" in got[0].note

    def test_an_original_too_small_needs_a_new_image(self, t09, tmp_path):
        """400x134 can never carry a 1600 px hero, however it is exported."""
        sid = "55555555-5555-5555-5555-555555555555"
        images = [_img(1, sid, "hero.webp", width=800, height=268, hero=True)]
        ctx = Harness(tmp_path, images, _index([("hero.webp", _ok(400, 134))]))
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/hero-new-fetch"], got
        assert got[0].current_value["largest_original"] == "400x134"

    def test_unknown_truth_makes_the_fetch_question_undecidable(self, t09, tmp_path):
        sid = "66666666-6666-6666-6666-666666666666"
        images = [_img(1, sid, "hero.webp", width=800, height=450, hero=True)]
        ctx = Harness(tmp_path, images, _index([("hero.webp", _status("unresolved"))]))
        got = t09.run(ctx)
        ids = sorted(f.test_id for f in got)
        assert ids == ["T09/hero-undecidable", "T09/unresolved"], got
        undecidable = [f for f in got if f.test_id == "T09/hero-undecidable"][0]
        assert undecidable.confidence is M.Confidence.UNVERIFIABLE

    def test_lost_hero_flag_is_reported(self, t09, tmp_path):
        sid = "77777777-7777-7777-7777-777777777777"
        images = [_img(1, sid, "gallery.webp", width=1600, height=1200, lead=False)]
        ctx = Harness(tmp_path, images, _index([("gallery.webp", _ok(3000, 2250))]))
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/no-hero-flag"], got

    def test_a_site_without_images_says_so(self, t09, tmp_path):
        ctx = Harness(tmp_path, [], _index([]))
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/no-images"], got
        assert got[0].confidence is M.Confidence.UNVERIFIABLE

    def test_a_site_whose_every_row_is_excluded_says_so(self, t09, tmp_path):
        """18 sites in this snapshot: one excluded row, no servable image, no hero."""
        sid = "15151515-1515-1515-1515-151515151515"
        images = [_img(1, sid, "hero.webp", width=800, height=457, excluded=True, lead=True)]
        ctx = Harness(tmp_path, images, _index([("hero.webp", _ok(3000, 1714))]))
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/no-servable-image"], got
        assert got[0].current_value == {"images": 1, "excluded": 1, "hero": "none"}


# ------------------------------------------------------------------ the row-level truth
class TestRowTruth:
    def test_gallery_upscale_is_flagged(self, t09, tmp_path):
        """The label set's "die DB-Maße täuschen Qualität vor"."""
        sid = "88888888-8888-8888-8888-888888888888"
        images = [
            _img(1, sid, "hero.webp", width=1600, height=1200, hero=True),
            _img(2, sid, "small.webp", width=1600, height=1200, sort_order=2),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(*BIG)),
                    ("small.webp", _ok(568, 799)),
                ]
            ),
        )
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/upscaled"], got
        f = got[0]
        assert f.current_value == {"image_id": 2, "width": 1600, "height": 1200}
        assert f.confidence is M.Confidence.AUTHORITATIVE
        assert not f.applicable, "no column carries the fix; the export has to change"

    def test_a_deliberate_gallery_crop_is_not_flagged(self, t09, tmp_path):
        """1600 px of a 4000 px original is GALLERY_WIDTH working as designed."""
        sid = "99999999-9999-9999-9999-999999999999"
        images = [
            _img(1, sid, "hero.webp", width=1600, height=1200, hero=True),
            _img(2, sid, "gallery.webp", width=1600, height=1200, sort_order=2),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(*BIG)),
                    ("gallery.webp", _ok(4000, 3000)),
                ]
            ),
        )
        assert t09.run(ctx) == []

    def test_a_missing_file_is_not_a_missing_answer(self, t09, tmp_path):
        """Commons saying "missing" is the canonical source's own answer, not a hole."""
        sid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        images = [_img(1, sid, "gone.jpg", width=1600, height=1200, hero=True)]
        ctx = Harness(tmp_path, images, _index([("gone.jpg", _status("missing"))]))
        got = t09.run(ctx)
        row = [f for f in got if f.test_id == "T09/commons-missing"]
        assert len(row) == 1, got
        assert row[0].confidence is M.Confidence.AUTHORITATIVE
        assert row[0].field == "wiki_images.commons_page_url"
        assert not [f for f in got if f.test_id == "T09/unresolved"]

    def test_an_absent_title_is_unresolved_not_missing(self, t09, tmp_path):
        """A partial response must not be read as "the file does not exist"."""
        sid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        images = [_img(1, sid, "never_answered.jpg", width=1600, height=1200, hero=True)]
        ctx = Harness(tmp_path, images, _index([("never_answered.jpg", _status("unresolved"))]))
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/unresolved"], got
        assert got[0].confidence is M.Confidence.UNVERIFIABLE

    def test_a_local_path_row_has_no_commons_identity(self, t09, tmp_path):
        sid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        images = [
            _img(
                1,
                sid,
                "local_only.webp",
                width=1600,
                height=1200,
                hero=True,
                local_path=True,
                commons_page_url=None,
            )
        ]
        ctx = Harness(tmp_path, images, _index([]))
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/no-commons-identity"], got
        assert got[0].confidence is M.Confidence.UNVERIFIABLE
        assert got[0].proposed_value is None
        assert "NULL" in got[0].note, "the missing attribution belongs in the note"

    def test_a_commons_page_url_alone_still_identifies_the_file(self, t09, tmp_path):
        """24 rows have a local original_url and a Commons page - they are answerable."""
        sid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        images = [
            _img(
                1,
                sid,
                "hero.webp",
                width=1600,
                height=1200,
                hero=True,
                local_path=True,
                commons_page_url="https://commons.wikimedia.org/wiki/File%3AReal.jpg",
            )
        ]
        ctx = Harness(tmp_path, images, _index([("Real.jpg", _ok(*BIG))]))
        assert t09.run(ctx) == []

    def test_a_row_without_stored_dimensions_is_reported(self, t09, tmp_path):
        sid = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        images = [_img(1, sid, "hero.webp", width=None, height=None, hero=True)]
        ctx = Harness(tmp_path, images, _index([("hero.webp", _ok(*BIG))]))
        got = t09.run(ctx)
        assert sorted(f.test_id for f in got) == [
            "T09/hero-redownload",
            "T09/stored-dims-missing",
        ], got
        missing = [f for f in got if f.test_id == "T09/stored-dims-missing"][0]
        assert missing.confidence is M.Confidence.UNVERIFIABLE
        assert missing.field == "wiki_images.width"

    def test_a_hero_below_the_cap_is_reported_once_not_twice(self, t09, tmp_path):
        """The hero decision already carries the upscale; two findings for one defect bury it."""
        sid = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        images = [
            _img(1, sid, "hero.webp", width=800, height=600, hero=True),
            _img(2, sid, "gallery.webp", width=1600, height=1200, sort_order=2),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(400, 300)),
                    ("gallery.webp", _ok(3000, 2250)),
                ]
            ),
        )
        got = t09.run(ctx)
        assert [f.test_id for f in got] == ["T09/hero-not-best"], got


# ------------------------------------------------------------------ the container
class TestIndexContract:
    def test_every_flagged_row_carries_evidence(self, t09, tmp_path):
        sid = "12121212-1212-1212-1212-121212121212"
        images = [
            _img(1, sid, "hero.webp", width=800, height=600, hero=True),
            _img(2, sid, "small.webp", width=1600, height=1200, sort_order=2),
            _img(3, sid, "gone.jpg", width=1600, height=1200, sort_order=3),
            _img(
                4,
                sid,
                "local.webp",
                width=1600,
                height=1200,
                sort_order=4,
                local_path=True,
                commons_page_url=None,
            ),
        ]
        ctx = Harness(
            tmp_path,
            images,
            _index(
                [
                    ("hero.webp", _ok(4272, 2848)),
                    ("small.webp", _ok(568, 799)),
                    ("gone.jpg", _status("missing")),
                ]
            ),
        )
        got = t09.run(ctx)
        assert len(got) >= 4
        for f in got:
            assert f.evidence, f"{f.test_id} claims something without a source"
            assert f.site_id == sid
            if f.proposal is M.Proposal.REVIEW:
                assert f.proposed_value is None, "REVIEW carries no value"
            assert not f.applicable, "nothing in T09 is a single-field auto-write"

    def test_run_refuses_a_missing_index(self, t09, tmp_path):
        ctx = Harness(tmp_path, [], index=None)
        with pytest.raises(FileNotFoundError, match="collect"):
            t09.run(ctx)

    @pytest.mark.parametrize(
        ("exported_at", "says"),
        [
            ("2026-09-23T00:00:00+02:00", "exported after the downloader"),
            ("2026-10-01T09:00:00+02:00", "exported after the downloader"),
            (None, "names no export time"),
        ],
    )
    def test_the_800_and_1600_px_notes_are_refused_for_a_later_snapshot(
        self, t09, tmp_path, exported_at, says
    ):
        """The caps T09 quotes made the 2026-09-20 rows; the new downloader stores other sizes."""
        sid = "15151515-1515-1515-1515-151515151515"
        images = [_img(1, sid, "hero.webp", width=800, height=600, hero=True)]
        ctx = Harness(
            tmp_path, images, _index([("hero.webp", _ok(4272, 2848))]), exported_at=exported_at
        )
        with pytest.raises(RuntimeError, match=says):
            t09.run(ctx)
        # the snapshot the census was built on still runs
        assert t09._pipeline_widths(EXPORTED_AT) == {"THUMB_WIDTH": 800, "GALLERY_WIDTH": 1600}

    def test_run_refuses_an_index_from_another_snapshot(self, t09, tmp_path):
        """Collecting truth about snapshot A and applying it to snapshot B is a silent lie."""
        sid = "13131313-1313-1313-1313-131313131313"
        images = [_img(1, sid, "hero.webp", width=800, height=600, hero=True)]
        ctx = Harness(tmp_path, images, _index([("hero.webp", _ok(4272, 2848))]))
        (tmp_path / "commons_imageinfo.json").write_text(
            json.dumps(
                {
                    "snapshot_exported_at": "2026-01-01T00:00:00+01:00",
                    "entries": {"hero.webp": _ok(4272, 2848)},
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(RuntimeError, match="re-collect"):
            t09.run(ctx)

    def test_run_refuses_an_index_that_does_not_cover_the_snapshot(self, t09, tmp_path):
        """A file the snapshot references but the index never asked about is not "clean"."""
        sid = "14141414-1414-1414-1414-141414141414"
        images = [_img(1, sid, "hero.webp", width=800, height=600, hero=True)]
        ctx = Harness(tmp_path, images, _index([("something_else.jpg", _ok(1, 1))]))
        with pytest.raises(RuntimeError, match="does not match this snapshot"):
            t09.run(ctx)
