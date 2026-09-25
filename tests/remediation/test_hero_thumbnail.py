"""T1 for the thumbnails that name a file their own site excluded (`hero_repair/thumbnail.py`).

`plan_thumbnails` is a pure function of the production read (sites, their image rows, the journal
rows of the excluded ones); the command reads through `persist_verdicts.read_rows`, faked here by
the statement it is sent. The delivered chunk is re-derived from its committed `READ.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from gallery_audit import decide  # noqa: E402
from hero_repair import thumbnail as T  # noqa: E402

SITE = "9a9a0dca-52c8-44c2-94f6-adb655db17dd"
OTHER = "0a1b2c3d-0000-4000-8000-000000000002"
HERO_WEBP = "/data/images/wiki/9a9a0dca/hero.webp"
DELIVERED = REPO / "output" / "remediation" / "hero_repair" / "thumbnail-2026-09-25"


def site(site_id: str = SITE, **over: Any) -> dict[str, Any]:
    return {
        "id": site_id,
        "name": "Lion Tombs of Dedan",
        "source_id": "ancient_nerds",
        "thumbnail_url": HERO_WEBP,
        **over,
    }


def image(image_id: int, filename: str, *, site_id: str = SITE, **over: Any) -> dict[str, Any]:
    return {
        "id": image_id,
        "site_id": site_id,
        "filename": filename,
        "is_hero": False,
        "is_lead": False,
        "sort_order": image_id,
        "is_excluded": False,
        **over,
    }


def journal(i: int, row: int, column: str, old: str, new: str) -> dict[str, Any]:
    return {
        "id": i,
        "run_stamp": "img-liveness-2026-09-23-001",
        "row_pk": str(row),
        "column_name": column,
        "old_value": old,
        "new_value": new,
    }


DEDAN_ROWS = [
    image(87351, "Dedan_tomb_1.webp", sort_order=1, is_excluded=True),
    image(87352, "hero.webp", sort_order=0, is_lead=True, is_excluded=True),
]
DEDAN_JOURNAL = [
    journal(32263, 87351, "is_excluded", "false", "true"),
    journal(32264, 87352, "is_excluded", "false", "true"),
    journal(32265, 87352, "is_hero", "true", "false"),
]


class TestThePath:
    def test_the_shard_is_the_site_s_short_id(self) -> None:
        assert T.local_path(SITE, "hero.webp") == HERO_WEBP
        assert T.local_path("ab-cd1234-ef56", "x.webp") == "/data/images/wiki/abcd1234/x.webp"


class TestThePlan:
    def test_a_site_that_serves_no_image_has_no_thumbnail(self) -> None:
        """Dedan: both rows excluded, the thumbnail names the excluded hero's file -> NULL."""
        changes, listed = T.plan_thumbnails([site()], DEDAN_ROWS, DEDAN_JOURNAL)
        assert not listed
        (change,) = changes
        assert (change.table, change.column, change.row_key, change.site_id) == (
            "unified_sites",
            "thumbnail_url",
            SITE,
            SITE,
        )
        assert (change.old_value, change.new_value, change.rule) == (HERO_WEBP, None, "T1")
        assert "serves no image" in change.reason and "87352" in change.reason
        sources = [e["source"] for e in change.evidence]
        assert sources == [
            "wiki_images:87352",
            "remediation_change_log:32264",
            "remediation_change_log:32265",
            "gallery_audit/worklist.py:served_row",
        ]

    def test_a_site_that_serves_a_live_image_gets_that_image_s_file(self) -> None:
        """The served row is the page's: hero first, then the lead, then sort_order."""
        rows = [
            image(1, "hero.webp", is_excluded=True),
            image(2, "lead.webp", is_lead=True, sort_order=0),
            image(3, "hero2.webp", is_hero=True, sort_order=9),
        ]
        (change,) = T.plan_thumbnails([site()], rows, [])[0]
        assert change.new_value == "/data/images/wiki/9a9a0dca/hero2.webp"
        assert "row 3" in change.reason
        rows[2]["is_hero"] = False
        (change,) = T.plan_thumbnails([site()], rows, [])[0]
        assert change.new_value == "/data/images/wiki/9a9a0dca/lead.webp"

    def test_a_null_exclusion_is_a_live_row(self) -> None:
        rows = [image(1, "hero.webp", is_excluded=True), image(2, "b.webp", is_excluded=None)]
        (change,) = T.plan_thumbnails([site()], rows, [])[0]
        assert change.new_value == "/data/images/wiki/9a9a0dca/b.webp"

    def test_a_thumbnail_that_names_a_live_row_is_not_this_lane_s(self) -> None:
        rows = [image(1, "hero.webp"), image(2, "b.webp", is_excluded=True)]
        changes, listed = T.plan_thumbnails([site()], rows, [])
        assert not changes
        assert [(entry["site_id"], entry["reason"]) for entry in listed] == [
            (SITE, "names-no-excluded-row")
        ]

    def test_a_file_of_another_shard_is_not_the_site_s(self) -> None:
        """The read matches the file name only; the shard must be the site's own."""
        rows = [image(1, "hero.webp", is_excluded=True)]
        other_shard = site(thumbnail_url="/data/images/wiki/ffffffff/hero.webp")
        changes, listed = T.plan_thumbnails([other_shard], rows, [])
        assert not changes and listed[0]["reason"] == "names-no-excluded-row"

    def test_a_file_an_excluded_and_a_live_row_share_is_still_served(self) -> None:
        rows = [image(1, "hero.webp", is_excluded=True), image(2, "hero.webp")]
        changes, listed = T.plan_thumbnails([site()], rows, [])
        assert not changes
        assert listed[0]["reason"] == "the-file-is-a-live-row-s-too"

    def test_a_site_outside_the_curated_source_is_refused(self) -> None:
        with pytest.raises(T.ThumbnailError, match="not an ancient_nerds site"):
            T.plan_thumbnails([site(source_id="osm")], DEDAN_ROWS, DEDAN_JOURNAL)

    def test_an_image_row_of_a_site_the_read_did_not_return_is_refused(self) -> None:
        with pytest.raises(T.ThumbnailError, match="belongs to no site of the read"):
            T.plan_thumbnails([site()], [*DEDAN_ROWS, image(5, "x.webp", site_id=OTHER)], [])

    def test_the_rule_table_says_what_a_site_without_an_image_gets(self) -> None:
        assert "NULL when the site serves no image" in decide.RULES["T1"]


class TestTheLane:
    def test_the_stamp_is_the_output_directory_s_date(self, tmp_path: Path) -> None:
        lane = T.chunk_lane(tmp_path / "thumbnail-2026-09-25")
        assert (lane.name, lane.test_id, lane.stamp, lane.confidence) == (
            "thumb-repoint",
            "H4/thumbnail",
            "thumb-repoint-2026-09-25",
            "authoritative",
        )
        with pytest.raises(T.ThumbnailError, match="not a thumbnail directory"):
            T.chunk_lane(tmp_path / "thumbs")


class TestTheCommand:
    def fake(self, monkeypatch: pytest.MonkeyPatch, sites: list[dict[str, Any]]) -> list[str]:
        sent: list[str] = []

        def read_rows(sql: str) -> list[dict[str, Any]]:
            sent.append(sql)
            if "FROM unified_sites u" in sql:
                assert "u.source_id = 'ancient_nerds'" in sql and "w.is_excluded IS TRUE" in sql
                return sites
            if "FROM wiki_images w" in sql:
                assert f"'{SITE}'::uuid" in sql
                return DEDAN_ROWS
            assert "FROM remediation_change_log l" in sql and "'87352'" in sql
            return DEDAN_JOURNAL

        monkeypatch.setattr(T.CW.pv, "read_rows", read_rows)
        return sent

    def test_the_command_reads_production_and_emits_one_chunk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = self.fake(monkeypatch, [site()])
        out = tmp_path / "thumbnail-2026-09-25"
        assert T.main(["chunk", "--out", str(out)]) == 0
        assert len(sent) == 3
        chunk = T.CW.check_delivered(out / "chunk-001")
        assert chunk.run_stamp == "thumb-repoint-2026-09-25-001" and not chunk.may_empty
        assert [(c.row_key, c.old_value, c.new_value) for c in chunk.changes] == [
            (SITE, HERO_WEBP, None)
        ]
        read = json.loads((out / "READ.json").read_text(encoding="utf-8"))
        assert read["sites"] == [site()] and read["images"] == DEDAN_ROWS
        assert T.main(["chunk", "--out", str(out)]) == 0  # the same chunk again is a no-op

    def test_a_read_that_plans_nothing_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.fake(monkeypatch, [])
        out = tmp_path / "thumbnail-2026-09-25"
        assert T.main(["chunk", "--out", str(out)]) == 1
        assert "no thumbnail names an excluded row" in capsys.readouterr().err
        assert not out.exists()


@pytest.mark.skipif(not (DELIVERED / "READ.json").exists(), reason="no delivered read yet")
def test_the_delivered_chunk_is_the_plan_of_its_read() -> None:
    """chunk-001 is what `plan_thumbnails` makes of the committed read: Dedan's thumbnail, which
    names the local file of its excluded hero 87352, cleared - the site serves no image."""
    read = json.loads((DELIVERED / "READ.json").read_text(encoding="utf-8"))
    chunk = T.CW.check_delivered(DELIVERED / "chunk-001")
    assert chunk.lane == T.chunk_lane(DELIVERED)
    changes, listed = T.plan_thumbnails(read["sites"], read["images"], read["journal"])
    assert list(chunk.changes) == changes and not listed
    assert [(c.row_key, c.old_value, c.new_value) for c in chunk.changes] == [
        (SITE, HERO_WEBP, None)
    ]
