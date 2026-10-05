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

    def test_the_entry_is_the_sites_own_file_and_not_another_sites(self) -> None:
        """Two sites may link the same Commons file; the manifest is keyed by site, so the entry
        must carry the file it fetched, never a neighbour's."""
        entry = IF.manifest_entry(HABU, FETCH_TITLE, FETCH_META, _Result())
        assert entry["filename"].endswith("Siris - 3.webp")
        assert entry["original_url"] == FETCH_META["original_url"]


def _stub_downloader(monkeypatch, fail_file: str | None = None) -> None:
    """Stand in for the Commons calls. `fetch_site` must be testable without the network, and the
    stub is where a refusal is produced: a download whose file Commons does not hold."""
    from pipeline import wiki_image_downloader as DL

    def metadata(titles: list[str]) -> dict[str, dict]:
        return {title: dict(FETCH_META) for title in titles}

    def download(url: str | None, dest: Path, width: int) -> _Result:
        # the stem, because `local_name` swaps the extension: "Broken_gate.jpg" is stored as
        # "Broken_gate.webp" and a match on the whole name would never fire
        if fail_file is not None and Path(fail_file).stem in dest.stem:
            raise DL.DownloadError(url, f"{fail_file} is gone")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"RIFF....WEBP")
        return _Result()

    monkeypatch.setattr(DL, "fetch_image_metadata_batch", metadata)
    monkeypatch.setattr(DL, "download_image", download)


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
