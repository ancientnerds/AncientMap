"""The 2025 import's linked image takes the hero flag (WD2/IH, owner decision 2026-10-05).

DB-less and offline: the read is a fixture READ.json, the import a fixture GeoJSON, the local
dimensions a dictionary, and no step of this lane fetches anything - the 1600 px downloads are
their own step, and a row that needs one is refused until its fetch is in the manifest.
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

from gallery_audit.chunk_writer import ChunkError  # noqa: E402
from import_hero import fetch as IF  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from import_hero import run as IR  # noqa: E402
from import_hero import verify as IV  # noqa: E402
from served_image import state as ST  # noqa: E402

THASOS = "33d2d754-e50a-4305-beff-87d2ad2c0227"
HABU = "0088c7e5-4a78-4b89-945d-3d5c787818e5"
BARE = "5b36f014-cb4a-4c2f-84b3-80996c503702"
HIDDEN = "7c8d0bac-0869-4b73-8044-79fad8c75985"
NOTHING = "2dab79e8-1ece-4f9b-beb3-a91573d545c3"
SMALL = "9f0d4b8f-5a11-4a6e-9a6a-0f0d4b8f5a44"

#: The file each fixture row holds, as a Commons URL (the shape the import links).
AGORA = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Thasos_agora.jpg"
GATE = "https://upload.wikimedia.org/wikipedia/commons/c/cd/Thasos_gate.jpg"
HIDDEN_FILE = "https://upload.wikimedia.org/wikipedia/commons/e/ef/Thasos_hidden.jpg"
RUIN = "https://upload.wikimedia.org/wikipedia/commons/g/gh/Thasos_ruin.jpg"


def _row(image_id: int, site_id: str, file: str, **flags: Any) -> dict[str, Any]:
    under = file.rsplit("/", 1)[-1]
    return {
        "id": image_id,
        "site_id": site_id,
        "filename": under.rsplit(".", 1)[0] + ".webp",
        "title": under.rsplit(".", 1)[0],
        "original_url": file,
        "commons_page_url": f"https://commons.wikimedia.org/wiki/File%3A{under}",
        "author": flags.get("author", "Jane Doe"),
        "author_url": "https://commons.wikimedia.org/wiki/User:Jane",
        "license": flags.get("license", "CC BY-SA 4.0"),
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "is_hero": bool(flags.get("hero")),
        "is_lead": bool(flags.get("lead", flags.get("hero"))),
        "is_excluded": bool(flags.get("excluded")),
        "sort_order": int(flags.get("order", 0)),
        "file_size_bytes": int(flags.get("size", 500_000)),
        "width": int(flags.get("width", 1600)),
        "height": int(flags.get("height", 1067)),
    }


def _site(site_id: str, name: str, thumb: str | None, url: str | None) -> dict[str, Any]:
    return {
        "id": site_id,
        "name": name,
        "country": "Greece",
        "site_type": "City/town/settlement",
        "lat": 40.78,
        "lon": 24.71,
        "thumbnail_url": thumb,
        "source_url": url,
    }


def _read() -> dict[str, Any]:
    return {
        "read_at": "2026-10-05T16:00:00Z",
        "sites": [
            # two live rows, the hero is the agora; the import links the gate
            _site(THASOS, "Thasos", "/data/images/wiki/33d2d754/Thasos_agora.webp", None),
            # one live row (hero) the import links the same file: nothing to move
            _site(HABU, "Medinet Habu", None, "https://en.wikipedia.org/wiki/Medinet_Habu"),
            # one hidden row only
            _site(HIDDEN, "Hidden row", None, "https://en.wikipedia.org/wiki/Hidden_row"),
            # no row at all
            _site(NOTHING, "Nothing", None, "https://en.wikipedia.org/wiki/Nothing"),
            # a row whose local file is the 800 px derivative - and it already holds the flag
            _site(BARE, "Small hero", None, "https://en.wikipedia.org/wiki/Small_hero"),
            # a site whose hero is a good file and whose import file is the 800 px derivative
            _site(SMALL, "Small target", None, "https://en.wikipedia.org/wiki/Small_target"),
        ],
        "images": [
            _row(1, THASOS, AGORA, hero=True, lead=True, order=0),
            _row(2, THASOS, GATE, order=1),
            _row(3, HABU, GATE, hero=True, lead=True),
            _row(4, HIDDEN, HIDDEN_FILE, excluded=True),
            _row(5, BARE, RUIN, hero=True, lead=True, width=800, height=551),
            _row(6, SMALL, RUIN, hero=True, lead=True),
            _row(
                7,
                SMALL,
                AGORA,
                order=1,
                width=800,
                height=551,
                title="Old caption",
                author="Old Author",
                license="CC BY 2.0",
            ),
        ],
        "retired": [],
    }


def _state(tmp_path: Path) -> ST.State:
    run = tmp_path / "run"
    run.mkdir(parents=True, exist_ok=True)
    ST.write_read(run / "READ.json", _read())
    return ST.load_read(run / "READ.json")


def _import(tmp_path: Path, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    path = tmp_path / "ancient_nerds_original.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "properties": {
                            "Title": r["title"],
                            "Source": r.get("url", ""),
                            "Images": r.get("image", ""),
                        }
                    }
                    for r in rows
                ],
            }
        ),
        encoding="utf-8",
    )
    return IH.read_import(path)


BIG = {
    1: (1600, 1067),
    2: (1600, 1067),
    3: (1600, 1067),
    4: (1600, 1067),
    5: (800, 551),
    6: (1600, 1067),
    7: (800, 551),
}


class TestTheJoin:
    def test_the_import_is_read_with_its_image_and_its_keys(self, tmp_path: Path) -> None:
        features = _import(
            tmp_path,
            [{"title": "Thasos", "url": "https://en.wikipedia.org/wiki/Thasos", "image": GATE}],
        )
        assert features[0]["image"] == GATE
        assert features[0]["image_host"] == "upload.wikimedia.org"

    def test_a_missing_import_file_is_refused_by_name(self, tmp_path: Path) -> None:
        with pytest.raises(IH.ImportHeroError, match="only surviving copy"):
            IH.read_import(tmp_path / "nope.geojson")

    def test_the_join_prefers_the_source_url_and_falls_back_to_the_title(
        self, tmp_path: Path
    ) -> None:
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [
                # the same title, a different source URL: the URL decides
                {
                    "title": "Medinet Habu",
                    "url": "https://en.wikipedia.org/wiki/Medinet_Habu",
                    "image": AGORA,
                },
                {"title": "Nothing", "url": "", "image": RUIN},
            ],
        )
        claims = IH.join_import(state, features)
        assert claims[HABU]["matched_on"] == "url"
        assert claims[HABU]["image"] == AGORA
        assert claims[NOTHING]["matched_on"] == "title"
        assert claims[NOTHING]["image"] == RUIN

    def test_an_ambiguous_join_is_reported_not_resolved(self, tmp_path: Path) -> None:
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [
                {"title": "Nothing", "url": "", "image": RUIN},
                {"title": "Nothing", "url": "", "image": AGORA},
            ],
        )
        claims = IH.join_import(state, features)
        assert claims[NOTHING]["ambiguous"] is True
        assert claims[NOTHING]["features"] == 2


class TestThePlan:
    def _plan(self, tmp_path: Path, fetched: dict[str, Any] | None = None) -> tuple[list, list]:
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [
                {"title": "Thasos", "url": "", "image": GATE},
                {
                    "title": "Medinet Habu",
                    "url": "https://en.wikipedia.org/wiki/Medinet_Habu",
                    "image": GATE,
                },
                {
                    "title": "Hidden row",
                    "url": "https://en.wikipedia.org/wiki/Hidden_row",
                    "image": HIDDEN_FILE,
                },
                {"title": "Nothing", "url": "https://en.wikipedia.org/wiki/Nothing", "image": RUIN},
                {
                    "title": "Small hero",
                    "url": "https://en.wikipedia.org/wiki/Small_hero",
                    "image": RUIN,
                },
                {
                    "title": "Small target",
                    "url": "https://en.wikipedia.org/wiki/Small_target",
                    "image": AGORA,
                },
            ],
        )
        planned = IH.plan(state, IH.join_import(state, features), dimensions=BIG, fetched=fetched)
        return planned.changes, planned.refusals

    def _fetch(self, site_id: str, filename: str) -> dict[str, Any]:
        return {
            site_id: {
                "image": AGORA,
                "filename": filename,
                "original_url": AGORA,
                "commons_page_url": "https://commons.wikimedia.org/wiki/File%3AThasos_agora.jpg",
                "title": "Thasos agora",
                "author": "Jane Doe",
                "author_url": "https://commons.wikimedia.org/wiki/User:Jane",
                "license": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "width": 1600,
                "height": 1067,
                "file_size_bytes": 812_345,
            }
        }

    def _may_empty(self, tmp_path: Path) -> list[str]:
        """The sites a chunk may leave without an image: the ones whose every row is excluded,
        so the import's file would be their *first* picture rather than a new hero."""
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [
                {
                    "title": "Hidden row",
                    "url": "https://en.wikipedia.org/wiki/Hidden_row",
                    "image": HIDDEN_FILE,
                },
            ],
        )
        return IH.plan(state, IH.join_import(state, features), dimensions=BIG).may_empty

    def test_a_site_that_shows_no_image_today_is_named_may_empty(self, tmp_path: Path) -> None:
        """The writer's guard asks "does every touched site still hold an image". For a site
        that shows none, unhiding its row is a first picture, and the reversal restores "none" -
        which the guard reads as a loss unless the chunk names the site (measured 2026-10-05:
        three of the pilot's 100 sites, 35 of the wave's 1,555)."""
        assert self._may_empty(tmp_path) == [HIDDEN]

    def test_a_site_with_a_live_image_is_never_may_empty(self, tmp_path: Path) -> None:
        state = _state(tmp_path)
        features = _import(tmp_path, [{"title": "Thasos", "url": "", "image": GATE}])
        assert IH.plan(state, IH.join_import(state, features), dimensions=BIG).may_empty == []

    def _by(self, changes: list, site_id: str) -> dict[tuple[str, str, str], Any]:
        return {(c.table, c.column, c.row_key): c for c in changes if c.site_id == site_id}

    def test_the_import_image_takes_the_flag_and_the_old_hero_gives_it_up(
        self, tmp_path: Path
    ) -> None:
        changes, refusals = self._plan(tmp_path)
        got = self._by(changes, THASOS)
        assert (
            got[("wiki_images", "is_hero", "2")].old_value,
            got[("wiki_images", "is_hero", "2")].new_value,
        ) == (
            "false",
            "true",
        )
        assert got[("wiki_images", "is_hero", "2")].rule == IH.RULE_HERO
        assert (
            got[("wiki_images", "is_hero", "1")].old_value,
            got[("wiki_images", "is_hero", "1")].new_value,
        ) == (
            "true",
            "false",
        )
        assert got[("wiki_images", "is_hero", "1")].rule == IH.RULE_DEMOTE
        assert all(c.evidence for c in changes)

    def test_the_thumbnail_follows_the_served_image(self, tmp_path: Path) -> None:
        changes, _ = self._plan(tmp_path)
        thumb = self._by(changes, THASOS)[("unified_sites", "thumbnail_url", THASOS)]
        assert thumb.column == "thumbnail_url"
        assert thumb.new_value == f"/data/images/wiki/{THASOS[:8]}/Thasos_gate.webp"
        assert thumb.rule == IH.RULE_THUMBNAIL

    def test_the_thumbnail_follows_a_row_this_wave_renames(self, tmp_path: Path) -> None:
        """`ih5` writes the fetched file's own name into the row, so the thumbnail has to name
        *that* - the name the read found is the one the wave replaces.

        Measured 2026-10-06: run `import-hero-2026-10-06-004` applied 229 sites and the acceptance
        refused all 228 on this one question - the page served the 1600 px file, the globe popup
        still asked for the file the read held.
        """
        changes, _ = self._plan(tmp_path, fetched=self._fetch(SMALL, "Thasos_agora_1600.webp"))
        got = self._by(changes, SMALL)
        rename = [c for key, c in got.items() if key[:2] == ("wiki_images", "filename")]
        assert len(rename) == 1
        assert rename[0].rule == IH.RULE_FETCH and rename[0].new_value == "Thasos_agora_1600.webp"
        thumb = got[("unified_sites", "thumbnail_url", SMALL)]
        assert thumb.new_value == f"/data/images/wiki/{SMALL[:8]}/Thasos_agora_1600.webp"

    def test_a_site_whose_row_is_not_renamed_keeps_the_name_the_row_holds(
        self, tmp_path: Path
    ) -> None:
        """The other half: a fetched manifest that names the file the row already holds must not
        move the thumbnail away from the row's own name."""
        changes, _ = self._plan(tmp_path, fetched=self._fetch(SMALL, "hero.webp"))
        thumb = self._by(changes, SMALL)[("unified_sites", "thumbnail_url", SMALL)]
        assert thumb.new_value == f"/data/images/wiki/{SMALL[:8]}/hero.webp"

    def test_a_site_that_already_serves_the_import_image_gets_no_flag_move(
        self, tmp_path: Path
    ) -> None:
        changes, _ = self._plan(tmp_path)
        assert not [k for k in self._by(changes, HABU) if k[1] == "is_hero"]

    def test_a_hidden_row_becomes_visible_before_it_can_be_the_hero(self, tmp_path: Path) -> None:
        changes, _ = self._plan(tmp_path)
        got = self._by(changes, HIDDEN)
        assert (
            got[("wiki_images", "is_excluded", "4")].old_value,
            got[("wiki_images", "is_excluded", "4")].new_value,
        ) == (
            "true",
            "false",
        )
        assert got[("wiki_images", "is_excluded", "4")].rule == IH.RULE_UNHIDE
        assert got[("wiki_images", "is_hero", "4")].new_value == "true"

    def test_a_site_without_a_row_for_the_import_file_is_refused_by_name(
        self, tmp_path: Path
    ) -> None:
        _changes, refusals = self._plan(tmp_path)
        refused = {r.site_id: r for r in refusals}
        assert NOTHING in refused
        assert refused[NOTHING].reason == "no_target_row"
        assert "insert" in refused[NOTHING].detail

    def test_a_row_under_1600x900_is_refused_until_its_fetch_is_manifested(
        self, tmp_path: Path
    ) -> None:
        _changes, refusals = self._plan(tmp_path)
        refused = {r.site_id: r for r in refusals}
        assert refused[BARE].reason == "local_file_too_small"
        assert "800x551" in refused[BARE].detail

    def test_a_manifested_fetch_plans_the_file_columns(self, tmp_path: Path) -> None:
        changes, refusals = self._plan(tmp_path, fetched=self._fetch(BARE, "Thasos_ruin_1600.webp"))
        assert BARE not in {r.site_id for r in refusals}
        got = {(c.column, c.row_key): c for c in changes if c.site_id == BARE}
        assert got[("filename", "5")].new_value == "Thasos_ruin_1600.webp"
        assert got[("width", "5")].new_value == "1600"
        assert got[("file_size_bytes", "5")].new_value == "812345"
        # the row already holds the flag, so a fetched file is all this site needs
        assert ("is_hero", "5") not in got

    def test_after_the_fetch_the_flag_moves_and_the_old_hero_gives_it_up(
        self, tmp_path: Path
    ) -> None:
        changes, refusals = self._plan(
            tmp_path, fetched=self._fetch(SMALL, "Thasos_agora_1600.webp")
        )
        assert SMALL not in {r.site_id for r in refusals}
        got = {(c.column, c.row_key): c for c in changes if c.site_id == SMALL}
        assert (got[("is_hero", "7")].old_value, got[("is_hero", "7")].new_value) == (
            "false",
            "true",
        )
        assert (got[("is_hero", "6")].old_value, got[("is_hero", "6")].new_value) == (
            "true",
            "false",
        )
        assert got[("filename", "7")].new_value == "Thasos_agora_1600.webp"
        assert got[("width", "7")].new_value == "1600"

    def test_a_fetch_without_a_licence_is_refused_rather_than_writing_pixels_only(
        self, tmp_path: Path
    ) -> None:
        """A row that shows the new file while crediting the old one is a wrong attribution on
        the page, so an incomplete manifest is refused by name instead of half-applied."""
        manifest = self._fetch(BARE, "Thasos_ruin_1600.webp")
        del manifest[BARE]["license_url"]
        with pytest.raises(IH.ImportHeroError, match="license_url"):
            self._plan(tmp_path, fetched=manifest)

    def test_the_fetch_writes_the_caption_and_the_licence_with_the_pixels(
        self, tmp_path: Path
    ) -> None:
        changes, _ = self._plan(tmp_path, fetched=self._fetch(SMALL, "Thasos_agora_1600.webp"))
        got = {(c.column, c.row_key): c for c in changes if c.site_id == SMALL}
        assert got[("license", "7")].new_value == "CC BY-SA 4.0"
        assert got[("title", "7")].new_value == "Thasos agora"
        assert got[("author", "7")].new_value == "Jane Doe"
        assert got[("license", "7")].rule == IH.RULE_FETCH

    def test_an_import_link_that_names_no_commons_file_is_refused(self, tmp_path: Path) -> None:
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [
                {
                    "title": "Thasos",
                    "url": "",
                    "image": "https://pbs.twimg.com/media/DeoYb3QX4AEFPL-?format=jpg",
                }
            ],
        )
        refusals = IH.plan(state, IH.join_import(state, features), dimensions=BIG).refusals
        refused = {r.site_id: r for r in refusals}
        assert refused[THASOS].reason == "no_target_row"
        assert "no Commons file" in refused[THASOS].detail


class TestTheOwnerFloor:
    """The owner's lowered floor (2026-10-06): for the sites that already have a picture, the
    import's linked picture becomes the hero once its file reaches 800 px of width.

    Measured over the rest inventory before the pair was chosen: all 26 sites refused as
    `import_picture_too_small` hold a row of at least 800 px width and none below, and the smallest
    of their heights is 337 px (800x600 and taller for the rest). So 800 px clears every one of them
    and no width below 800 would, while the height has to travel with it or the 800x337 row stays
    refused - which is why the floor is a pair and not a number.
    """

    def _plan(
        self,
        tmp_path: Path,
        *,
        dimensions: dict[int, tuple[int, int]] | None = None,
        floor: tuple[int, int] | None = None,
    ) -> IH.Planned:
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [
                {"title": "Thasos", "url": "", "image": GATE},
                {
                    "title": "Medinet Habu",
                    "url": "https://en.wikipedia.org/wiki/Medinet_Habu",
                    "image": GATE,
                },
                {
                    "title": "Hidden row",
                    "url": "https://en.wikipedia.org/wiki/Hidden_row",
                    "image": HIDDEN_FILE,
                },
                {"title": "Nothing", "url": "https://en.wikipedia.org/wiki/Nothing", "image": RUIN},
                {
                    "title": "Small hero",
                    "url": "https://en.wikipedia.org/wiki/Small_hero",
                    "image": RUIN,
                },
                {
                    "title": "Small target",
                    "url": "https://en.wikipedia.org/wiki/Small_target",
                    "image": AGORA,
                },
            ],
        )
        return IH.plan(
            state,
            IH.join_import(state, features),
            dimensions=dimensions or BIG,
            floor=floor,
        )

    def test_the_lane_s_own_floor_refuses_the_800_px_row(self, tmp_path: Path) -> None:
        planned = self._plan(tmp_path)
        refused = {r.site_id: r for r in planned.refusals}
        assert refused[BARE].reason == "local_file_too_small"
        assert "1600x900" in refused[BARE].detail

    def test_the_owner_s_floor_plans_the_row_the_lane_refuses(self, tmp_path: Path) -> None:
        planned = self._plan(tmp_path, floor=(IH.OWNER_FLOOR_WIDTH, IH.OWNER_FLOOR_HEIGHT))
        assert BARE not in {r.site_id for r in planned.refusals}
        got = {(c.column, c.row_key): c for c in planned.changes if c.site_id == BARE}
        # the row already holds the flag, so the only thing left to write is the thumbnail, and it
        # names the file that row already has on disk (`Thasos_ruin.webp`)
        assert (
            got[("thumbnail_url", BARE)].new_value == "/data/images/wiki/5b36f014/Thasos_ruin.webp"
        )
        assert ("is_hero", "5") not in got

    def test_the_height_is_half_of_the_floor_and_not_decoration(self, tmp_path: Path) -> None:
        """800 px wide and 299 px high is refused as well: one floor, both halves, or the lane
        serves a hero it would refuse again on the next plan."""
        planned = self._plan(tmp_path, dimensions={**BIG, 5: (800, 299)}, floor=(800, 300))
        refused = {r.site_id: r for r in planned.refusals}
        assert refused[BARE].reason == "local_file_too_small"
        assert "800x300" in refused[BARE].detail

    def test_the_owner_s_floor_is_the_pair_measured_over_the_inventory(self) -> None:
        assert (IH.OWNER_FLOOR_WIDTH, IH.OWNER_FLOOR_HEIGHT) == (800, 300)

    def test_a_fetch_at_the_owner_s_floor_reaches_the_manifest_the_lane_s_own_refuses(self) -> None:
        small = _Result(width=800, height=531)
        with pytest.raises(IF.FetchError, match="1600"):
            IF.manifest_entry(THASOS, FETCH_TITLE, FETCH_META, small)
        entry = IF.manifest_entry(THASOS, FETCH_TITLE, FETCH_META, small, floor=(800, 300))
        assert (entry["width"], entry["height"]) == ("800", "531")


class TestTheFloorOfARun:
    """One floor per run, recorded in the run directory: the plan and the fetch of the same wave
    have to serve the same size, or the fetch refuses what the plan accepted."""

    def _run(self, tmp_path: Path) -> tuple[Path, Path]:
        _state(tmp_path)
        _import(
            tmp_path,
            [
                {"title": "Thasos", "url": "", "image": GATE},
                {
                    "title": "Small hero",
                    "url": "https://en.wikipedia.org/wiki/Small_hero",
                    "image": RUIN,
                },
            ],
        )
        return tmp_path / "run", tmp_path / "ancient_nerds_original.geojson"

    def test_a_plan_records_the_floor_it_planned_at(self, tmp_path: Path) -> None:
        run, source = self._run(tmp_path)
        out = IR.cmd_plan(run, source=source, floor=(800, 300))
        assert out["floor"] == {"min_width": 800, "min_height": 300}
        recorded = json.loads((run / IR.FLOOR).read_text(encoding="utf-8"))
        assert (recorded["min_width"], recorded["min_height"]) == (800, 300)

    def test_the_plan_after_it_fetches_at_the_floor_it_recorded(self, tmp_path: Path) -> None:
        """No flags the second time: the run's own `FLOOR.json` is the floor, which is what keeps a
        resumed wave from silently serving at the lane's 1600x900 again."""
        run, source = self._run(tmp_path)
        IR.cmd_plan(run, source=source, floor=(800, 300))
        out = IR.cmd_plan(run, source=source)
        assert out["floor"] == {"min_width": 800, "min_height": 300}

    def test_a_run_without_a_floor_serves_the_lane_s_own(self, tmp_path: Path) -> None:
        run, source = self._run(tmp_path)
        out = IR.cmd_plan(run, source=source)
        assert out["floor"] == {"min_width": IH.HERO_MIN_WIDTH, "min_height": IH.HERO_MIN_HEIGHT}

    def test_half_a_floor_is_refused_by_name(self, tmp_path: Path) -> None:
        run, _ = self._run(tmp_path)
        with pytest.raises(IH.ImportHeroError, match="travel together"):
            IR.cmd_plan(run, source=tmp_path / "ancient_nerds_original.geojson", floor=(800, None))

    def test_a_command_without_the_flags_reads_the_runs_own_floor(self, tmp_path: Path) -> None:
        """`--min-width` belongs to `plan` and `fetch` alone. `main()` must not read an attribute the
        other subparsers never defined - measured 2026-10-06: `accept` died on the missing
        `min_width` the same minute the floor flags went in."""
        run, source = self._run(tmp_path)
        IR.cmd_plan(run, source=source, floor=(800, 300))
        assert IR.main(["remainder", "--run-dir", str(run)]) == 0
        recorded = json.loads((run / IR.REMAINDER).read_text(encoding="utf-8"))
        assert recorded["floor"] == {"min_width": 800, "min_height": 300}


class TestTheChunks:
    def test_a_chunk_carries_the_lane_the_undo_and_the_digest(self, tmp_path: Path) -> None:
        state = _state(tmp_path)
        features = _import(tmp_path, [{"title": "Thasos", "url": "", "image": GATE}])
        out = tmp_path / "wave"
        summary = IH.write_chunks(
            out,
            state,
            IH.join_import(state, features),
            run_stamp="import-hero-2026-10-05-001",
            dimensions=BIG,
        )
        assert summary["planned_sites"] == 1
        assert summary["chunks"] == 1
        directory = out / "chunk-001"
        assert (directory / "CHUNK.json").is_file()
        assert (directory / "PLAN.jsonl").is_file()
        # the undo exists before the write, never after
        assert (directory / "ROLLBACK.sql").is_file()
        assert (directory / "APPLY.sql").is_file()
        rollback = (directory / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert "false" in rollback and "true" in rollback

    def test_a_plan_with_no_row_is_refused(self, tmp_path: Path) -> None:
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [{"title": "Nothing", "url": "https://en.wikipedia.org/wiki/Nothing", "image": RUIN}],
        )
        with pytest.raises(IH.ImportHeroError, match="no row"):
            IH.write_chunks(
                tmp_path / "wave",
                state,
                IH.join_import(state, features),
                run_stamp="import-hero-2026-10-05-002",
                dimensions=BIG,
            )

    def test_a_plan_that_refuses_every_site_still_names_them(self, tmp_path: Path) -> None:
        """A wave where nothing is writable is the one case where the refusals are the whole result.

        Measured 2026-10-07, run `import-hero-2026-10-07-010`: 37 sites seeded, all 37 refused, and
        the run could not say why any of them was - the refusals were written after the raise.
        """
        state = _state(tmp_path)
        features = _import(
            tmp_path,
            [{"title": "Nothing", "url": "https://en.wikipedia.org/wiki/Nothing", "image": RUIN}],
        )
        out = tmp_path / "wave"
        with pytest.raises(IH.ImportHeroError, match="no row") as caught:
            IH.write_chunks(
                out,
                state,
                IH.join_import(state, features),
                run_stamp="import-hero-2026-10-05-003",
                dimensions=BIG,
            )
        assert "no_target_row" in str(caught.value)
        written = [
            json.loads(line)
            for line in (out / IH.PLAN_REFUSALS).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert written and written[0]["reason"] == "no_target_row"
        assert written[0]["detail"]

    def test_a_plan_that_refuses_every_site_keeps_the_seeded_record(self, tmp_path: Path) -> None:
        """`IMPORT_HERO_REFUSALS.jsonl` is what a run prepared for the INSERT lane reads back."""
        state = _state(tmp_path)
        out = tmp_path / "wave"
        out.mkdir(parents=True)
        seeded = out / "IMPORT_HERO_REFUSALS.jsonl"
        seeded.write_text(
            json.dumps(
                {
                    "site_id": "11111111-1111-1111-1111-111111111111",
                    "reason": "no_target_row",
                    "detail": "seeded",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        features = _import(
            tmp_path,
            [{"title": "Nothing", "url": "https://en.wikipedia.org/wiki/Nothing", "image": RUIN}],
        )
        with pytest.raises(IH.ImportHeroError, match="no row"):
            IH.write_chunks(
                out,
                state,
                IH.join_import(state, features),
                run_stamp="import-hero-2026-10-05-004",
                dimensions=BIG,
            )
        assert "seeded" in seeded.read_text(encoding="utf-8")

    def test_a_site_that_already_serves_the_import_image_plans_nothing(
        self, tmp_path: Path
    ) -> None:
        """The plan must not write a value onto a row that already holds it: the import's file is
        the site's hero and its thumbnail already names that row, so the site is not in the plan."""
        state = _state(tmp_path)
        features = _import(tmp_path, [{"title": "Thasos", "url": "", "image": AGORA}])
        planned = IH.plan(state, IH.join_import(state, features), dimensions=BIG)
        assert planned.changes == []
        assert planned.refusals == []


class TestTheAcceptance:
    """What the wave is accepted on: a fresh production read, every planned site, three questions.

    The read is not the plan's. The proof has to come from production - what the page serves, what
    the thumbnail names, how many rows hold the hero flag - and not from what the wave meant to
    write."""

    def _applied(self, tmp_path: Path) -> ST.State:
        """The fixture read after Thasos' gate row took the hero flag and the hidden row its
        unhide - the two shapes the wave's rules ih1 and ih3 produce."""
        read = _read()
        for row in read["images"]:
            if row["id"] == 1:
                row["is_hero"] = False
                row["is_lead"] = False
            if row["id"] == 2:
                row["is_hero"] = True
                row["is_lead"] = True
            if row["id"] == 4:
                row["is_excluded"] = False
                row["is_hero"] = True
                row["is_lead"] = True
        for site in read["sites"]:
            if site["id"] == THASOS:
                site["thumbnail_url"] = "/data/images/wiki/33d2d754/Thasos_gate.webp"
            if site["id"] == HIDDEN:
                site["thumbnail_url"] = "/data/images/wiki/7c8d0bac/Thasos_hidden.webp"
        run = tmp_path / "applied"
        run.mkdir(parents=True, exist_ok=True)
        ST.write_read(run / "READ.json", read)
        return ST.load_read(run / "READ.json")

    def _claims(self) -> dict[str, dict[str, Any]]:
        return {
            THASOS: {"image": GATE, "matched_on": "title"},
            HIDDEN: {"image": HIDDEN_FILE, "matched_on": "title"},
        }

    def test_a_wave_that_did_what_it_said_measures_clean(self, tmp_path: Path) -> None:
        result = IV.check_wave(self._applied(tmp_path), self._claims(), [THASOS, HIDDEN])
        assert result.sites == 2
        assert result.served_the_import == 2
        assert result.thumbnail_follows == 2
        assert result.one_hero == 2
        assert result.problems == []
        assert result.ok

    def test_a_site_whose_thumbnail_names_the_old_row_is_refused_by_name(
        self, tmp_path: Path
    ) -> None:
        """Rule ih4 is what keeps the gallery and the card on one picture: a hero that moved but a
        thumbnail that did not is the wave half-done, and the acceptance has to name it."""
        state = self._applied(tmp_path)
        state.sites[THASOS]["thumbnail_url"] = "/data/images/wiki/33d2d754/Thasos_agora.webp"
        result = IV.check_wave(state, self._claims(), [THASOS, HIDDEN])
        assert result.thumbnail_follows == 1
        assert not result.ok
        assert any("thumbnail" in p and "Thasos_gate.webp" in p for p in result.problems)

    def test_two_live_hero_rows_are_refused_by_name(self, tmp_path: Path) -> None:
        state = self._applied(tmp_path)
        for row in state.rows[THASOS]:
            if row["id"] == 1:
                row["is_hero"] = True
        result = IV.check_wave(state, self._claims(), [THASOS, HIDDEN])
        assert result.one_hero == 1
        assert not result.ok
        assert any("2 live hero row" in p for p in result.problems)

    def test_a_site_that_left_the_read_is_refused_by_name(self, tmp_path: Path) -> None:
        state = self._applied(tmp_path)
        del state.sites[NOTHING]
        result = IV.check_wave(state, self._claims(), [NOTHING])
        assert result.sites == 1
        assert not result.ok
        assert any("not in the read" in p for p in result.problems)

    def test_a_thumbnail_alone_does_not_make_a_site_accepted(self, tmp_path: Path) -> None:
        """A site whose every row is hidden still shows the import's file through its thumbnail, so
        the picture is not missing - but no live row carries the hero flag, which is what the wave's
        rule ih3 was for. The acceptance has to say that instead of passing the site."""
        state = self._applied(tmp_path)
        for row in state.rows[HIDDEN]:
            row["is_excluded"] = True
        result = IV.check_wave(state, self._claims(), [HIDDEN])
        assert result.served_the_import == 1
        assert result.one_hero == 0
        assert not result.ok
        assert any("0 live hero row" in p for p in result.problems)


#: The Commons file the 807 refusals name, and the imageinfo answer the downloader returned for it.
#: Measured 2026-10-05 against production, field for field.
FETCH_FILE = "Area_archeologica_di_Herakleia_e_Siris_-_3.jpg"
#: The same file as the Commons API spells it: MediaWiki's title form, `File:` off, spaces. The
#: downloader normalises every answer to it (`fetch_image_metadata_batch`'s own note), so this is
#: what `plan_targets` hands to the API and what the lane therefore names the stored file after.
FETCH_TITLE = ST.canonical_file(FETCH_FILE)
FETCH_META = {
    "author": "Alessandro Antonelli",
    "author_url": "https://commons.wikimedia.org/wiki/User:Una_giornata_uggiosa_%2794",
    "height": "3000",
    "license": "CC BY 3.0",
    "license_url": "https://creativecommons.org/licenses/by/3.0",
    "original_url": (
        "https://upload.wikimedia.org/wikipedia/commons/1/1e/"
        "Area_archeologica_di_Herakleia_e_Siris_-_3.jpg"
    ),
    "width": "4000",
}


class _Result:
    """What `download_image` returns: the stored derivative's own size, not the original's."""

    def __init__(self, *, width: int = 1600, height: int = 1200, file_size: int = 548_938) -> None:
        self.width = width
        self.height = height
        self.file_size = file_size
        self.fetch_url = "https://upload.wikimedia.org/…/1920px-Area_archeologica….jpg"
        self.fetched_bucket = 1920


class TestTheFetchManifest:
    """The fetch step's only deliverable: one manifest entry per site, carrying all eleven columns.

    `fetch_image_metadata_batch` answers seven columns; the lane refuses a manifest entry that does
    not carry all eleven, because a row must credit the file it shows. The four it cannot know are
    assembled here from the download's own result and the naming rule (owner decision 2026-10-05:
    the Commons name verbatim, only the extension becomes `.webp`).
    """

    def _entry(self, meta: dict[str, str] | None = None, result: _Result | None = None) -> dict:
        return IF.manifest_entry(
            THASOS, FETCH_TITLE, meta if meta is not None else FETCH_META, result or _Result()
        )

    def test_the_entry_carries_exactly_the_columns_the_lane_demands(self) -> None:
        """Measured: the lane refuses any manifest missing one of `FETCH_COLUMNS` - by name."""
        assert sorted(self._entry()) == sorted(IH.FETCH_COLUMNS)

    def test_the_local_name_is_the_commons_name_with_only_the_extension_swapped(self) -> None:
        """The wave names its files the Commons title, the spelling 43,392 of the 47,920 production
        `commons_page_url` rows already use (measured 2026-10-05 over the read's 48,567 rows)."""
        entry = self._entry()
        assert entry["filename"] == "Area archeologica di Herakleia e Siris - 3.webp"
        assert entry["title"] == "Area archeologica di Herakleia e Siris - 3"

    def test_the_underscore_spelling_is_passed_through_untouched(self) -> None:
        """The other half of verbatim: an import link that spells its file with underscores stores that
        name, only the extension swapped."""
        assert IF.local_name(FETCH_FILE) == "Area_archeologica_di_Herakleia_e_Siris_-_3.webp"

    def test_the_commons_page_url_encodes_the_colon_the_way_production_does(self) -> None:
        entry = self._entry()
        assert entry["commons_page_url"] == (
            "https://commons.wikimedia.org/wiki/"
            "File%3AArea%20archeologica%20di%20Herakleia%20e%20Siris%20-%203.jpg"
        )

    def test_the_derivative_carries_its_own_size_not_the_originals(self) -> None:
        """A 4000x3000 original becomes a 1600x1200 file; a row that claimed the original's size
        would lie about the picture the page serves."""
        entry = self._entry()
        assert (entry["width"], entry["height"]) == ("1600", "1200")
        assert entry["file_size_bytes"] == "548938"

    def test_an_imageinfo_answer_without_the_licence_is_refused_by_name(self) -> None:
        thin = {k: v for k, v in FETCH_META.items() if k != "license"}
        with pytest.raises(IF.FetchError, match="license"):
            self._entry(meta=thin)

    def test_a_download_narrower_than_the_lane_serves_is_refused_by_name(self) -> None:
        """`local_file_too_small` is the very refusal this wave clears; a 800 px download that
        reached the manifest would put the same site back where it started."""
        with pytest.raises(IF.FetchError, match="1600"):
            self._entry(result=_Result(width=800, height=531))

    def test_a_download_shorter_than_the_lane_serves_is_refused_by_name(self) -> None:
        """The plan's hero minimum is 1600x900, not 1600 alone: 121 of the 807 refusals are a
        1600 px panorama under 900 px high (measured 2026-10-05), and the downloader keeps the
        aspect ratio, so a 1600 px fetch of one returns the same box. Accepting it would install a
        hero the lane itself calls too small, and the next plan would refuse the site again."""
        with pytest.raises(IF.FetchError, match="900"):
            self._entry(result=_Result(width=1600, height=812))

    def test_the_minimum_the_manifest_enforces_is_the_plan_s_own(self) -> None:
        """One rule, not two that can drift apart: `plan.py` decides what a hero may be."""
        assert (IH.HERO_MIN_WIDTH, IH.HERO_MIN_HEIGHT) == (1600, 900)

    def test_a_commons_name_without_an_extension_is_refused_by_name(self) -> None:
        with pytest.raises(IF.FetchError, match="extension"):
            IF.manifest_entry(THASOS, "Area archeologica di Herakleia", FETCH_META, _Result())

    def test_a_name_the_local_filesystem_refuses_is_refused_by_name(self) -> None:
        """Windows refuses `"` in a file name with `OSError: [Errno 22]` - measured 2026-10-06,
        where it killed a run of 807 targets at `Makedonisches Grab Korinos "A" Dromos.webp`.
        The rule is the Commons name verbatim, so such a file is named and refused, never renamed."""
        with pytest.raises(IF.FetchError, match="cannot be stored"):
            IF.local_name('Makedonisches Grab Korinos "A" Dromos.jpg')

    def test_the_author_is_required_where_the_licence_asks_for_attribution(self) -> None:
        """D18 and X4 (2026-10-08): a CC BY* file without an author is a row that credits nobody."""
        thin = {k: v for k, v in FETCH_META.items() if k != "author"}
        with pytest.raises(IF.FetchError, match="author"):
            self._entry(meta=thin)

    def test_the_author_url_is_never_required(self) -> None:
        """D18: the link to the author's page is not a condition. The measured form is NULL (1,333
        of the 11,632 CC BY-SA 3.0 rows have none), and the manifest carries it as ''."""
        no_page = {k: v for k, v in FETCH_META.items() if k != "author_url"}
        entry = self._entry(meta=no_page)
        assert entry["author_url"] == ""
        assert entry["author"] == FETCH_META["author"]

    def test_the_licence_url_is_required_where_the_licence_asks_for_attribution(self) -> None:
        thin = {k: v for k, v in FETCH_META.items() if k != "license_url"}
        with pytest.raises(IF.FetchError, match="license_url"):
            self._entry(meta=thin)

    @pytest.mark.parametrize(
        "licence", ["Public domain", "PD-old-100", "CC0", "CC0 1.0", "No restrictions"]
    )
    def test_a_free_licence_needs_neither_an_author_nor_a_licence_url(self, licence: str) -> None:
        """5,952 curated rows are 'Public domain', none has a licence URL and 350 no author: a
        literal 'author and licence URL for every file' would refuse them all."""
        free = {
            k: v for k, v in FETCH_META.items() if k not in ("author", "author_url", "license_url")
        } | {"license": licence}
        entry = self._entry(meta=free)
        assert (entry["author"], entry["author_url"], entry["license_url"]) == ("", "", "")
        assert entry["license"] == licence

    def test_commons_attribution_licence_needs_the_author_but_has_no_licence_page(self) -> None:
        """None of the 135 curated 'Attribution' rows carries a licence URL, 130 carry an author."""
        meta = {k: v for k, v in FETCH_META.items() if k != "license_url"} | {
            "license": "Attribution"
        }
        assert self._entry(meta=meta)["license_url"] == ""
        with pytest.raises(IF.FetchError, match="author"):
            self._entry(meta={k: v for k, v in meta.items() if k != "author"})

    @pytest.mark.parametrize(
        "licence", ["CC BY-SA 4.0", "CC BY 2.5", "GFDL 1.2", "OGL 3", "FAL", "KOGL Type 1", "Foo"]
    )
    def test_every_other_licence_name_is_strict_never_free(self, licence: str) -> None:
        """A name the rule does not know demands both, because a wrong 'free' would publish a file
        without the credit its terms ask for."""
        assert IF.credit_columns(licence) == ("author", "license_url")

    def test_the_hero_wave_stores_a_missing_credit_as_null(self) -> None:
        """`_fetch_changes` turns the manifest's '' into NULL for the three nullable columns, and a
        row that already holds NULL there is no change."""
        state = ST.State(
            sites={THASOS: {"id": THASOS, "name": "Thasos"}},
            rows={},
            retired=frozenset(),
            read_at="2026-10-09T00:00:00Z",
            sha256="0" * 64,
        )
        row = _row(1, THASOS, AGORA)
        free = IF.manifest_entry(
            THASOS,
            FETCH_TITLE,
            {
                k: v
                for k, v in FETCH_META.items()
                if k not in ("author", "author_url", "license_url")
            }
            | {"license": "Public domain"},
            _Result(),
        )
        changes = {c.column: c for c in IH._fetch_changes(state, THASOS, row, free, reason="r")}
        assert changes["author"].new_value is None and changes["author"].old_value == "Jane Doe"
        assert changes["author_url"].new_value is None
        assert changes["license_url"].new_value is None
        nulls = _row(1, THASOS, AGORA) | {"author": None, "author_url": None, "license_url": None}
        assert not {"author", "author_url", "license_url"} & {
            c.column for c in IH._fetch_changes(state, THASOS, nulls, free, reason="r")
        }

    def test_the_entry_is_the_sites_own_file_and_not_another_sites(self) -> None:
        """Two sites may link the same Commons file; the manifest is keyed by site, so the entry
        must carry the file it fetched, never a neighbour's."""
        entry = IF.manifest_entry(HABU, FETCH_TITLE, FETCH_META, _Result())
        assert entry["filename"].endswith("Siris - 3.webp")
        assert entry["original_url"] == FETCH_META["original_url"]


def _stem_key(name: str) -> str:
    """One file under both of the lane's spellings: MediaWiki writes titles with spaces, the upload
    URL with underscores, and a target reaches the stub as one and is stored as the other."""
    return Path(name).stem.replace(" ", "_").lower()


def _stub_downloader(monkeypatch, fail_file: str | None = None, meta: dict | None = None) -> None:
    """Stand in for the Commons calls. `fetch_site` must be testable without the network, and the
    stub is where a refusal is produced: a download whose file Commons does not hold."""
    from pipeline import wiki_image_downloader as DL

    def metadata(titles: list[str]) -> dict[str, dict]:
        return {title: dict(meta if meta is not None else FETCH_META) for title in titles}

    def download(url: str | None, dest: Path, width: int) -> _Result:
        if fail_file is not None and _stem_key(fail_file) in _stem_key(dest.name):
            raise DL.DownloadError(url, f"{fail_file} is gone")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"RIFF....WEBP")
        return _Result()

    monkeypatch.setattr(DL, "fetch_image_metadata_batch", metadata)
    monkeypatch.setattr(DL, "download_image", download)


def test_a_file_commons_does_not_host_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """9 of the 270 refusals of the INSERT wave read `not an upload.wikimedia.org original: None`,
    which said nothing: Commons answers a page it does not have with no `imageinfo` at all, and the
    batch reader turns that into an entry whose fields are all None - the download then failed on a
    URL that was never there. Measured 2026-10-06 with one API call over all nine: every page
    answers `missing` (e.g. File:Thul Hairo Khan.jpg), so the import links pictures Commons does
    not host."""
    from pipeline import wiki_image_downloader as DL

    def metadata(titles: list[str]) -> dict[str, dict]:
        gone = {**FETCH_META, "original_url": None, "width": None, "height": None}
        return {title: dict(gone) for title in titles}

    monkeypatch.setattr(DL, "fetch_image_metadata_batch", metadata)
    monkeypatch.setattr(
        DL,
        "download_image",
        lambda *a, **k: pytest.fail("a file Commons does not host must not be downloaded"),
    )
    with pytest.raises(IF.FetchError, match="hosts no file of this name"):
        IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)
    with pytest.raises(IF.FetchError, match="`missing`"):
        IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)
    assert not list(tmp_path.rglob("*"))


class TestTheFetchRun:
    """The loop around that entry: which sites to fetch, where the file lands, what happens to
    one that fails."""

    def test_the_targets_are_the_refused_sites_that_name_a_commons_file(self) -> None:
        claims = {
            THASOS: {"image": f"https://upload.wikimedia.org/wikipedia/commons/1/1e/{FETCH_FILE}"},
            HABU: {"image": f"https://upload.wikimedia.org/wikipedia/commons/2/2f/{FETCH_FILE}"},
        }
        refusals = [
            {"site_id": THASOS, "reason": "local_file_too_small", "detail": ""},
            {"site_id": HABU, "reason": "local_file_too_small", "detail": ""},
            {"site_id": HIDDEN, "reason": "no_target_row", "detail": ""},
        ]
        # the title form, not the URL's underscores: that is what the API is asked for and what the
        # lane names the stored file after
        assert IF.plan_targets(claims, refusals) == [(THASOS, FETCH_TITLE), (HABU, FETCH_TITLE)]

    def test_a_refusal_whose_import_link_names_no_commons_file_is_refused_by_name(self) -> None:
        """`local_file_too_small` means the row holds the file, so a refusal without one is a
        contradiction: fetching something the plan never named would be a guess."""
        claims = {THASOS: {"image": ""}}
        refusals = [{"site_id": THASOS, "reason": "local_file_too_small", "detail": ""}]
        with pytest.raises(IF.FetchError, match="no Commons file"):
            IF.plan_targets(claims, refusals)

    def test_the_insert_wave_skips_a_site_whose_import_link_names_no_commons_file(self) -> None:
        """The other half, measured 2026-10-06: 37 of the 326 `no_target_row` sites link
        en.wikipedia, UNESCO, a blog or a Twitter image. There is no Commons file to fetch, and no
        row this lane could name - so they are not targets, and the wave is not a defect for them.
        """
        claims = {
            THASOS: {"image": "https://www.cais-soas.com/CAIS/Images2/x.jpg"},
            HABU: {"image": FETCH_META["original_url"]},
        }
        refusals = [
            {"site_id": THASOS, "reason": "no_target_row", "detail": ""},
            {"site_id": HABU, "reason": "no_target_row", "detail": ""},
        ]
        assert IF.plan_targets(claims, refusals, reasons=("no_target_row",)) == [
            (HABU, FETCH_TITLE)
        ]

    def test_a_wave_with_nothing_to_fetch_is_refused_by_name(self) -> None:
        with pytest.raises(IF.FetchError, match="no site to fetch"):
            IF.plan_targets({}, [{"site_id": THASOS, "reason": "no_target_row", "detail": ""}])

    def test_the_file_lands_in_the_sites_own_directory_under_the_offsite_root(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _stub_downloader(monkeypatch)
        entry = IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)
        assert entry["filename"] == "Area archeologica di Herakleia e Siris - 3.webp"
        assert (tmp_path / THASOS[:8] / entry["filename"]).is_file()

    def test_a_panorama_is_refused_before_a_single_byte_is_downloaded(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A 4000x2030 original stores as 1600x812 and the downloader keeps the aspect ratio, so the
        bytes would be spent on the very box `manifest_entry` refuses afterwards - and the file would
        stay on disk, named by nothing. `imageinfo` already knows the original's size, and
        `stored_size` is the downloader's own rule for what it will write."""
        _stub_downloader(monkeypatch, meta={**FETCH_META, "width": "4000", "height": "2030"})
        with pytest.raises(IF.FetchError, match="1600x812"):
            IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)
        assert list(tmp_path.rglob("*.webp")) == []

    def test_a_name_the_filesystem_refuses_never_reaches_the_downloader(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The name is known before anything is fetched, so the refusal costs no download and
        leaves no file: 3 of the wave's 807 targets, 2 of them otherwise fetchable."""
        _stub_downloader(monkeypatch)
        with pytest.raises(IF.FetchError, match="cannot be stored"):
            IF.fetch_site(THASOS, 'Makedonisches Grab Korinos "A" Dromos.jpg', tmp_path)
        assert list(tmp_path.rglob("*.webp")) == []

    def test_a_local_filesystem_error_does_not_take_the_manifest_with_it(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """One site must never end a wave of several hundred. `download_image` writes with
        `open("xb")`, so a name the filesystem refuses raises `OSError` - which is neither a
        `FetchError` nor a `DownloadError` and killed the 807-target run (measured 2026-10-06)."""
        from pipeline import wiki_image_downloader as DL

        _stub_downloader(monkeypatch)
        download = DL.download_image

        def flaky(url: str | None, dest: Path, width: int) -> _Result:
            if "Broken" in dest.name:
                raise OSError(22, "Invalid argument", str(dest))
            return download(url, dest, width)

        monkeypatch.setattr(DL, "download_image", flaky)
        manifest, failures = IF.fetch_manifest(
            [(THASOS, FETCH_TITLE), (SMALL, "Broken_gate.jpg")], tmp_path, delay_s=0.0
        )
        assert sorted(manifest) == [THASOS]
        assert failures[0][:2] == (SMALL, "Broken_gate.jpg")
        assert "Invalid argument" in failures[0][2]

    def test_one_site_that_fails_does_not_take_the_manifest_with_it(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _stub_downloader(monkeypatch, fail_file="Broken_gate.jpg")
        manifest, failures = IF.fetch_manifest(
            [(THASOS, FETCH_FILE), (SMALL, "Broken_gate.jpg")], tmp_path, delay_s=0.0
        )
        assert sorted(manifest) == [THASOS]
        site_id, commons_file, why = failures[0]
        assert (site_id, commons_file) == (SMALL, "Broken_gate.jpg")
        # the downloader's own wording, which also carries the URL it asked for
        assert why.startswith("the fetch failed: Broken_gate.jpg is gone")

    def test_a_run_where_nothing_was_fetched_is_refused(self, tmp_path: Path, monkeypatch) -> None:
        """A manifest of zero rows would look like a finished fetch and leave the plan refusing
        every site of the wave."""
        _stub_downloader(monkeypatch, fail_file="Broken")
        with pytest.raises(IF.FetchError, match="no file of this wave"):
            IF.fetch_manifest([(SMALL, "Broken_gate.jpg")], tmp_path, delay_s=0.0)

    def test_the_manifest_is_written_once_and_its_digest_returned(self, tmp_path: Path) -> None:
        path = tmp_path / "FETCHED.json"
        digest = IF.write_manifest(path, {THASOS: {"filename": "a.webp"}})
        assert path.is_file() and len(digest) == 64
        with pytest.raises(IF.FetchError, match="already"):
            IF.write_manifest(path, {THASOS: {"filename": "b.webp"}})


class TestTheFetchCommand:
    """`run.py fetch`: the loop behind four arguments, writing the manifest a later `plan --fetched`
    reads. Commons is not a test fixture - the downloader is the stub above."""

    def _run_dir(self, tmp_path: Path) -> Path:
        run = tmp_path / "import-hero-2026-10-05-004"
        run.mkdir()
        (run / IR.CLAIMS).write_text(
            json.dumps(
                {
                    THASOS: {
                        "image": f"https://upload.wikimedia.org/wikipedia/commons/1/1e/{FETCH_FILE}"
                    },
                    SMALL: {
                        "image": "https://upload.wikimedia.org/wikipedia/commons/2/2f/Broken_gate.jpg"
                    },
                }
            ),
            encoding="utf-8",
        )
        (run / IR.REFUSALS).write_text(
            "".join(
                json.dumps(row, sort_keys=True) + "\n"
                for row in (
                    {"site_id": THASOS, "reason": "local_file_too_small", "detail": "800x600"},
                    {"site_id": SMALL, "reason": "local_file_too_small", "detail": "800x600"},
                    {"site_id": HIDDEN, "reason": "no_target_row", "detail": ""},
                )
            ),
            encoding="utf-8",
        )
        return run

    def _fetch(self, capsys, tmp_path: Path, *extra: str) -> tuple[int, dict, Path]:
        run = self._run_dir(tmp_path)
        code = IR.main(
            [
                "fetch",
                "--run-dir",
                str(run),
                "--root",
                str(tmp_path / "images"),
                "--delay",
                "0",
                *extra,
            ]
        )
        return code, json.loads(capsys.readouterr().out), run

    def test_the_command_writes_the_manifest_and_names_what_it_could_not_fetch(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        _stub_downloader(monkeypatch, fail_file="Broken_gate.jpg")
        code, printed, run = self._fetch(capsys, tmp_path)
        assert code == 0
        manifest = json.loads((run / IR.FETCHED).read_text(encoding="utf-8"))
        assert sorted(manifest) == [THASOS]
        assert manifest[THASOS]["filename"] == "Area archeologica di Herakleia e Siris - 3.webp"
        failures = [
            json.loads(line)
            for line in (run / IR.FETCH_FAILURES).read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert [row["site_id"] for row in failures] == [SMALL]
        # the title form it was fetched under, the one the manifest and the plan both speak
        assert failures[0]["commons_file"] == "Broken gate.jpg"
        assert printed["fetched"] == 1 and printed["failed"] == 1
        assert (
            tmp_path / "images" / THASOS[:8] / "Area archeologica di Herakleia e Siris - 3.webp"
        ).is_file()

    def test_a_limit_fetches_the_first_targets_only(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """The pilot before a wave of several hundred: a few files prove the path, the rest follows.
        The pilot's manifest goes elsewhere, because a manifest is written once per path and the
        wave's own still has to fit into this run directory."""
        _stub_downloader(monkeypatch)
        pilot = tmp_path / "pilot" / IR.FETCHED
        code, printed, run = self._fetch(capsys, tmp_path, "--limit", "1", "--out", str(pilot))
        assert code == 0 and printed["targeted"] == 1 and printed["fetched"] == 1
        assert json.loads(pilot.read_text(encoding="utf-8")) != {}
        assert not (run / IR.FETCHED).exists()

    def test_a_run_without_its_claims_is_refused_by_name(self, tmp_path: Path, capsys) -> None:
        """The refusal has to name the run and cost nothing: no directory created, and production
        never read. Measured 2026-10-06: `fetch` wrote the floor into the run before `_wave_of`
        looked at it, so the very directory the refusal looks for was created first - and the fetch
        went on to read production instead. On the CI runner, which has no route to the VPS, that
        surfaced as the only red test of the push (run 37508910683); here it was green for the wrong
        reason, refused by the missing import export, which says "does not exist" as well.

        The marker this test carried on main is gone with that fix, as 72b4eac asked for it."""
        missing = tmp_path / "no-such-run"
        code = IR.main(
            [
                "fetch",
                "--run-dir",
                str(missing),
                "--root",
                str(tmp_path / "images"),
            ]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert f"{missing} does not exist" in err
        assert "plan --run-dir" in err
        assert not missing.exists()


class TestTheJoinRefusesAnEmptyKey:
    """`url_key("")` is a key like any other, so a feature without a `Source` and a site without a
    `source_url` used to meet in one bucket - and the site inherited the bucket's first feature.

    Measured 2026-10-06: 49 curated sites carry no `source_url`, 111 of the import's 5,995 features
    carry no `Source`, and the first of those is the church `Iglesia de San Antoni de l'Aldosa` in
    Cardona - claimed for sites in Ukraine, Peru, Sweden and Australia alike. The plan refused them
    all as `no_target_row`, so nothing was written; the premise was wrong all the same.
    """

    def _state(self, source_url: str, name: str = "Apolyanka") -> ST.State:
        return ST.State(
            sites={THASOS: {"id": THASOS, "name": name, "source_url": source_url}},
            rows={},
            retired=(),
            read_at="2026-10-06T00:00:00Z",
            sha256="0" * 64,
        )

    def _features(self) -> list[dict[str, Any]]:
        return [
            {
                "feature": 1,
                "title": "Iglesia de San Antoni de l'Aldosa",
                "source_url": "",
                "image": "https://upload.wikimedia.org/wikipedia/commons/0/01/Iglesia.jpg",
                "image_host": "upload.wikimedia.org",
            },
            {
                "feature": 2,
                "title": "Apolyanka",
                "source_url": "https://en.wikipedia.org/wiki/Apolyanka",
                "image": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Apolyanka.jpg",
                "image_host": "upload.wikimedia.org",
            },
        ]

    def test_a_site_without_a_source_url_does_not_inherit_the_first_feature_without_one(
        self,
    ) -> None:
        """The case as measured: no `source_url` on either side, and no title match either."""
        claims = IH.join_import(self._state("", name="Kvitky"), self._features())
        assert claims[THASOS]["image"] is None
        assert claims[THASOS]["matched_on"] is None

    def test_a_site_without_a_source_url_falls_back_to_its_own_title(self) -> None:
        """The proven key still decides - a site with no URL but a title the import knows."""
        claims = IH.join_import(self._state("   "), self._features())
        assert claims[THASOS]["matched_on"] == "title"
        assert claims[THASOS]["import_title"] == "Apolyanka"
        assert claims[THASOS]["image"].endswith("Apolyanka.jpg")

    def test_a_feature_without_a_source_url_never_becomes_a_url_hit(self) -> None:
        """The other side of the same key: the bucket must not exist at all."""
        features = [self._features()[0]]
        claims = IH.join_import(self._state("https://en.wikipedia.org/wiki/Apolyanka"), features)
        assert claims[THASOS]["image"] is None
        assert claims[THASOS]["matched_on"] is None

    def test_a_site_with_a_real_source_url_still_matches_it_first(self) -> None:
        """The guard costs the proven arm nothing."""
        features = [
            {
                "feature": 1,
                "title": "Iglesia de San Antoni de l'Aldosa",
                "source_url": "https://en.wikipedia.org/wiki/Apolyanka",
                "image": "https://upload.wikimedia.org/wikipedia/commons/0/01/Iglesia.jpg",
                "image_host": "upload.wikimedia.org",
            },
            {
                "feature": 2,
                "title": "Apolyanka",
                "source_url": "https://en.wikipedia.org/wiki/Apolyanka",
                "image": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Apolyanka.jpg",
                "image_host": "upload.wikimedia.org",
            },
        ]
        claims = IH.join_import(self._state("https://en.wikipedia.org/wiki/Apolyanka"), features)
        assert claims[THASOS]["matched_on"] == "url"
        assert claims[THASOS]["image"].endswith("Iglesia.jpg")  # first hit wins, ambiguity kept


def _write_webp(path: Path, size: tuple[int, int]) -> None:
    """A real picture on disk - `stored_file` opens it, a stub that writes `RIFF` would not do."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (11, 22, 33)).save(path, "WEBP", quality=80)


def _image_size(path: Path) -> tuple[int, int]:
    """The size on disk, read back the way `fetch.stored_file` reads it."""
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _no_download(monkeypatch) -> None:
    """A Commons answer, and a download that fails the test if it is ever reached."""
    from pipeline import wiki_image_downloader as DL

    def metadata(titles: list[str]) -> dict[str, dict]:
        return {title: dict(FETCH_META) for title in titles}

    def download(url: str | None, dest: Path, width: int) -> _Result:
        raise AssertionError(f"no download was expected, but one was asked for ({dest})")

    monkeypatch.setattr(DL, "fetch_image_metadata_batch", metadata)
    monkeypatch.setattr(DL, "download_image", download)


class TestTheResumableFetchRun:
    """`fetch_manifest` hands the whole wave over at the end; `run_fetch` carries the manifest along,
    because `download_image` opens with `O_EXCL` and 800 downloads against a link that may drop are
    not a single transaction. The step also has to *replace* the file the wave exists to replace."""

    def _manifest(self, tmp_path: Path) -> Path:
        return tmp_path / "FETCHED.json"

    def test_the_manifest_is_written_after_every_file(self, tmp_path: Path, monkeypatch) -> None:
        """Not at the end: an interruption after the first file has to leave the first file recorded."""
        _stub_downloader(monkeypatch)
        outcome = IF.run_fetch(
            [(THASOS, FETCH_FILE), (HABU, FETCH_FILE)],
            tmp_path,
            self._manifest(tmp_path),
            delay_s=0.0,
        )
        assert (outcome.fetched, outcome.already, outcome.failures) == (2, 0, [])
        assert sorted(IF.load_manifest(self._manifest(tmp_path))) == sorted([THASOS, HABU])

    def test_an_interrupted_run_continues_where_it_stopped(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The second target dies after its file landed; the retry must not download it again -
        `download_image` would raise on its own file, and the plan would never see the site."""
        from pipeline import wiki_image_downloader as DL

        def metadata(titles: list[str]) -> dict[str, dict]:
            return {title: dict(FETCH_META) for title in titles}

        calls: list[Path] = []

        def download(url: str | None, dest: Path, width: int) -> _Result:
            calls.append(dest)
            if len(calls) == 2:
                raise RuntimeError("the link dropped")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"RIFF....WEBP")
            return _Result()

        monkeypatch.setattr(DL, "fetch_image_metadata_batch", metadata)
        monkeypatch.setattr(DL, "download_image", download)
        manifest = self._manifest(tmp_path)
        with pytest.raises(RuntimeError):
            IF.run_fetch(
                [(THASOS, FETCH_FILE), (HABU, FETCH_FILE)], tmp_path, manifest, delay_s=0.0
            )
        assert sorted(IF.load_manifest(manifest)) == [THASOS]
        calls.clear()
        outcome = IF.run_fetch(
            [(THASOS, FETCH_FILE), (HABU, FETCH_FILE)], tmp_path, manifest, delay_s=0.0
        )
        assert (outcome.fetched, outcome.already) == (1, 1)
        # only the site the manifest did not carry was downloaded
        assert calls == [tmp_path / HABU[:8] / f"{IF.local_name(FETCH_FILE)}.fetching"]

    def test_a_failed_site_is_recorded_and_retried_by_the_next_run(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A refusal is not a result: the site stays in the next run's work, never in the manifest."""
        _stub_downloader(monkeypatch, fail_file="Broken_gate.jpg")
        manifest = self._manifest(tmp_path)
        refusals = tmp_path / "FETCH_REFUSALS.jsonl"
        outcome = IF.run_fetch(
            [(THASOS, FETCH_FILE), (SMALL, "Broken_gate.jpg")],
            tmp_path,
            manifest,
            failures_path=refusals,
            delay_s=0.0,
        )
        assert sorted(IF.load_manifest(manifest)) == [THASOS]
        assert [f[0] for f in outcome.failures] == [SMALL]
        assert SMALL in refusals.read_text(encoding="utf-8")
        _stub_downloader(monkeypatch)
        second = IF.run_fetch(
            [(THASOS, FETCH_FILE), (SMALL, "Broken_gate.jpg")],
            tmp_path,
            manifest,
            failures_path=refusals,
            delay_s=0.0,
        )
        assert sorted(IF.load_manifest(manifest)) == sorted([THASOS, SMALL])
        assert (second.fetched, second.already) == (1, 1)

    def test_a_run_where_nothing_was_fetched_and_nothing_stands_is_refused(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A manifest of zero rows would look like a finished fetch and leave the plan refusing
        every site of the wave."""
        _stub_downloader(monkeypatch, fail_file="Broken")
        with pytest.raises(IF.FetchError, match="no file of this wave"):
            IF.run_fetch(
                [(SMALL, "Broken_gate.jpg")], tmp_path, self._manifest(tmp_path), delay_s=0.0
            )

    def test_the_manifest_is_replaced_atomically(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        first = IF.save_manifest(path, {THASOS: {"filename": "a.webp"}})
        assert len(first) == 64 and not path.with_name("FETCHED.json.tmp").exists()
        second = IF.save_manifest(path, {THASOS: {"filename": "b.webp"}})
        assert second != first
        assert IF.load_manifest(path)[THASOS]["filename"] == "b.webp"

    def test_a_manifest_that_is_not_readable_json_is_refused_by_name(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Starting again from nothing would re-download files `O_EXCL` refuses to overwrite."""
        _stub_downloader(monkeypatch)
        path = self._manifest(tmp_path)
        path.write_text("{halber", encoding="utf-8")
        with pytest.raises(IF.FetchError, match="readable JSON"):
            IF.run_fetch([(THASOS, FETCH_FILE)], tmp_path, path, delay_s=0.0)

    def test_a_stored_file_that_already_reaches_the_minimum_is_adopted(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The state an interruption leaves behind: the file landed, the entry did not. It is
        measured, not downloaded again - the download is the one thing that would fail here."""
        _no_download(monkeypatch)
        dest = IF.site_dest(tmp_path, THASOS, FETCH_TITLE)
        _write_webp(dest, (1600, 1200))
        entry = IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)
        assert (entry["width"], entry["height"]) == ("1600", "1200")
        assert entry["file_size_bytes"] == str(dest.stat().st_size)

    def test_a_stored_panorama_is_refused_without_a_download(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """1600 px wide, under 900 px high: `download_image` keeps the aspect ratio, so the fetch
        returns the same box. 121 of the 807 refusals of run -002 are exactly this."""
        _no_download(monkeypatch)
        _write_webp(IF.site_dest(tmp_path, THASOS, FETCH_TITLE), (1600, 812))
        with pytest.raises(IF.FetchError, match="panorama"):
            IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)

    def test_an_original_narrower_than_the_minimum_is_refused_without_a_download(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """`imageinfo` states the original's width before anything is downloaded, and a fetch
        cannot deliver more pixels than the original holds."""
        from pipeline import wiki_image_downloader as DL

        def metadata(titles: list[str]) -> dict[str, dict]:
            return {title: dict(FETCH_META, width="1200") for title in titles}

        def download(url: str | None, dest: Path, width: int) -> _Result:
            raise AssertionError("no download was expected, but one was asked for")

        monkeypatch.setattr(DL, "fetch_image_metadata_batch", metadata)
        monkeypatch.setattr(DL, "download_image", download)
        with pytest.raises(IF.FetchError, match="1200 px wide"):
            IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)

    def test_a_too_small_stored_file_is_replaced_by_the_download(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The wave's own case: the site serves an 800 px copy and the fetch has to swap in the
        1600 px one. `download_image` never replaces anything, so the swap is the lane's own."""
        from pipeline import wiki_image_downloader as DL

        def metadata(titles: list[str]) -> dict[str, dict]:
            return {title: dict(FETCH_META) for title in titles}

        def download(url: str | None, dest: Path, width: int) -> _Result:
            _write_webp(dest, (1600, 1200))
            return _Result(width=1600, height=1200, file_size=dest.stat().st_size)

        monkeypatch.setattr(DL, "fetch_image_metadata_batch", metadata)
        monkeypatch.setattr(DL, "download_image", download)
        dest = IF.site_dest(tmp_path, THASOS, FETCH_TITLE)
        _write_webp(dest, (800, 600))
        entry = IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)
        assert (entry["width"], entry["height"]) == ("1600", "1200")
        assert _image_size(dest) == (1600, 1200)
        assert not dest.with_name(f"{dest.name}.fetching").exists()

    def test_a_file_on_disk_that_is_not_a_picture_is_refused_by_name(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Half a download from an interrupted run would otherwise be measured as a picture."""
        _no_download(monkeypatch)
        dest = IF.site_dest(tmp_path, THASOS, FETCH_TITLE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00\x01\x02 not a picture")
        with pytest.raises(IF.FetchError, match="not a picture"):
            IF.fetch_site(THASOS, FETCH_TITLE, tmp_path)

    def test_a_name_the_file_system_refuses_is_refused_by_name(self) -> None:
        """The offsite tree and the VPS tree both live on Windows volumes, where `"` cannot be in a
        file name; production carries no row whose filename has one (measured 2026-10-06 over the
        read's 48,567 rows), so three of the 807 refusals are named instead of renamed."""
        with pytest.raises(IF.FetchError, match="cannot be stored"):
            IF.local_name('Makedonisches Grab Korinos "A" Dromos.jpg')

    def test_a_target_whose_name_cannot_be_written_is_a_refusal_not_a_crash(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The first full run died on exactly this: `download_image` raised `OSError: [Errno 22]`
        and took the other 750 sites of the wave with it."""
        _stub_downloader(monkeypatch)
        manifest = tmp_path / "FETCHED.json"
        refusals = tmp_path / "FETCH_REFUSALS.jsonl"
        outcome = IF.run_fetch(
            [(THASOS, FETCH_FILE), (HABU, 'Piezas del Conjunto "Los Gemelos".jpg')],
            tmp_path,
            manifest,
            failures_path=refusals,
            delay_s=0.0,
        )
        assert sorted(IF.load_manifest(manifest)) == [THASOS]
        assert [f[0] for f in outcome.failures] == [HABU]
        assert "cannot be stored" in refusals.read_text(encoding="utf-8")


class TestTheReadCommand:
    """`insert-plan` measures its rows against `READ.json`, and a prepared run has no `fetch --start`
    to get one - that command would read production *and* fetch the import's own 417 targets. The
    read is written once, so a second one refuses instead of swapping the state under the plan."""

    def test_the_read_is_written_once_and_a_second_refuses_by_name(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        from import_hero import read as RD

        monkeypatch.setattr(RD, "read_production", _read)
        run = tmp_path / "insert-2026-10-07-001"
        assert IR.main(["read", "--run-dir", str(run)]) == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed["shown_sites"] == len(_read()["sites"])
        assert (run / RD.READ).is_file() and len(printed["read_sha256"]) == 64
        summary = json.loads((run / IR.READ_SUMMARY).read_text(encoding="utf-8"))
        assert summary["read_at"] == "2026-10-05T16:00:00Z"
        assert IR.main(["read", "--run-dir", str(run)]) == 1
        assert "written once" in capsys.readouterr().err
