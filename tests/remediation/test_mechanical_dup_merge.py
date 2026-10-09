"""D14: do the duplicate pairs get exactly their move and their retirement - and nothing else?

`mechanical/dup_merge.py` turns `DUP_DECISIONS.jsonl` into waves (`PAIRS.json`), and a wave into two
plans: `dup-merge-move-<wave>` (the loser's images, content links and name row go to the survivor) and
`dup-merge-retire-<wave>` (the loser is retired as `duplicate_of:<survivor>`). Each plan is a pure
function of one read-only production read; every refusal below has its own test, and a pair the plan
cannot carry is held back, listed and never written.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import dup_merge as D  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402

WAVE = "2026-10-10"
LOSER = "ae2ca7b1-89da-46cb-8924-f9d04dd5da2e"
SURVIVOR = "ce7db300-8777-425d-917a-2f6d9f325b58"
LOSER2 = "3ebb514f-ac4a-4913-b54b-409bcc29eff4"
SURVIVOR2 = "51daf6c9-25d3-4818-8857-0543f1203c57"
OTHER = "dafc7527-c6c8-45c3-8c7d-4813d20a4dcf"
NOW = "2026-10-10T00:00:00+00:00"
QUOTES = (
    {
        "source": "https://en.wikipedia.org/wiki/Banias",
        "quote": "also known as",
        "url": "https://en.wikipedia.org/wiki/Banias",
    },
)


def pair(loser: str = LOSER, survivor: str = SURVIVOR, **over: Any) -> D.WavePair:
    base: dict[str, Any] = {
        "loser": loser, "survivor": survivor, "loser_name": "Banias",
        "survivor_name": "Caesarea Philippi", "metres_limit": 2000, "already_retired": False,
        "cluster_id": "dup-1", "why": "one site", "quotes": QUOTES,
    }  # fmt: skip
    return D.WavePair(**{**base, **over})


def lanes(pairs: list[D.WavePair]) -> tuple[L.Lane, L.Lane]:
    return D._lanes(WAVE, pairs)


def img(
    i: int, site: str, url: str, *, hero: bool = False, excluded: bool | None = False, sort: int = 0
) -> dict[str, Any]:
    return {
        "id": i,
        "site_id": site,
        "original_url": url,
        "is_hero": hero,
        "is_excluded": excluded,
        "sort_order": sort,
    }


def link(i: int, site: str, source: str = "topostext", content: str = "1") -> dict[str, Any]:
    return {"id": i, "site_id": site, "content_source": source, "content_id": content}


def nm(i: int, site: str, name: str, key: str, kind: str | None = "label") -> dict[str, Any]:
    return {"id": i, "site_id": site, "name": name, "name_normalized": key, "name_type": kind}


def a_read(pairs: list[D.WavePair] | None = None, **over: Any) -> D.Read:
    """A read of the pair Banias -> Caesarea Philippi: the loser holds two images (one hero), a
    content link and its own name row; the survivor holds an image, a hero and its name row."""
    pairs = pairs or [pair()]
    move, retire = lanes(pairs)
    sites: dict[str, dict[str, Any]] = {}
    for p in pairs:
        for sid, name in ((p.loser, p.loser_name), (p.survivor, p.survivor_name)):
            sites[sid] = {
                "id": sid, "name": name, "source_id": "ancient_nerds", "scope_status": None,
                "scope_reason": None, "lat": 33.0, "lon": 35.0, "name_key": name.lower(),
                "move_premise": "", "retire_premise": "",
            }  # fmt: skip
    read = D.Read(
        sites=sites,
        ext=dict.fromkeys(sites, (("enwiki_title", "Banias"), ("wikidata_qid", "Q606295"))),
        images={
            LOSER: (
                img(1, LOSER, "u/1", hero=True),
                img(2, LOSER, "u/2"),
                img(3, LOSER, "u/shared"),
            ),
            SURVIVOR: (img(10, SURVIVOR, "u/shared"), img(11, SURVIVOR, "u/own", hero=True)),
        },
        links={
            LOSER: (link(1, LOSER, content="a"), link(2, LOSER, content="shared")),
            SURVIVOR: (link(9, SURVIVOR, content="shared"),),
        },  # fmt: skip
        names={
            LOSER: (nm(5, LOSER, "Banias", "banias"),),
            SURVIVOR: (nm(6, SURVIVOR, "Caesarea Philippi", "caesarea philippi"),),
        },  # fmt: skip
        metres={p.loser: 289.5 for p in pairs},
        onto=(),
        journal={},
        stamps={},
        read_at="2026-10-10 10:00:00+00",
    )
    read = replace(read, **over)
    return with_premises(read, pairs)


def with_premises(read: D.Read, pairs: list[D.WavePair]) -> D.Read:
    """The premises the database would print for each loser, from the read's own rows."""
    sites = dict(read.sites)
    for p in pairs:
        loser, survivor = sites[p.loser], sites[p.survivor]
        sites[p.loser] = {
            **loser,
            "move_premise": D.move_premise(read, loser, survivor),
            "retire_premise": D.retire_premise(read, loser, survivor),
        }
    return replace(read, sites=sites)


def moved(read: D.Read | None = None, pairs: list[D.WavePair] | None = None):
    pairs = pairs or [pair()]
    move, _ = lanes(pairs)
    return D.build_move(read or a_read(pairs), pairs, move, NOW)


# --------------------------------------------------------------------------------- the waves
class TestTheWaves:
    def decision(self, site: str, target: str, **over: Any) -> dict[str, Any]:
        item = {"kind": "MERGE", "site_id": site, "name": f"n-{site[:4]}", "target": target,
                "target_name": f"n-{target[:4]}", "why": "w", "quotes": [dict(q) for q in QUOTES],
                "metres": 10.0, "metres_limit": 2000}  # fmt: skip
        return {"cluster_id": "dup-1", "status": "complete", "merges": [{**item, **over}]}

    def test_a_decided_merge_is_a_pair_with_its_names_and_limit(self) -> None:
        pairs = D.decided_pairs([self.decision(LOSER, SURVIVOR, metres_limit=2500)])
        assert [(p.loser, p.survivor, p.metres_limit, p.already_retired) for p in pairs] == [
            (LOSER, SURVIVOR, 2500, False)
        ]
        assert (pairs[0].loser_name, pairs[0].survivor_name) == (
            f"n-{LOSER[:4]}",
            f"n-{SURVIVOR[:4]}",
        )

    def test_an_already_retired_loser_is_marked(self) -> None:
        pairs = D.decided_pairs([self.decision(LOSER, SURVIVOR, already_retired=True)])
        assert pairs[0].already_retired is True

    def test_a_survivor_that_is_merged_away_is_followed_to_the_final_survivor(self) -> None:
        a = self.decision(LOSER, SURVIVOR)
        b = {**self.decision(SURVIVOR, OTHER), "cluster_id": "dup-2"}
        pairs = {p.loser: p.survivor for p in D.decided_pairs([a, b])}
        assert pairs == {LOSER: OTHER, SURVIVOR: OTHER}

    def test_two_decisions_that_merge_into_each_other_are_refused(self) -> None:
        a = self.decision(LOSER, SURVIVOR)
        b = {**self.decision(SURVIVOR, LOSER), "cluster_id": "dup-2"}
        with pytest.raises(P.PlanError, match="in a circle"):
            D.decided_pairs([a, b])

    def test_the_labels_are_the_date_then_letters(self) -> None:
        assert D.wave_labels("2026-10-10", 3) == ["2026-10-10", "2026-10-10b", "2026-10-10c"]
        with pytest.raises(ValueError, match="not a wave label"):
            D.wave_labels("tomorrow", 1)
        with pytest.raises(P.PlanError, match="split the date"):
            D.wave_labels("2026-10-10", 30)

    def test_a_wave_holds_whole_survivors_and_at_most_the_sites(self) -> None:
        def p(n: int, survivor: str) -> D.WavePair:
            return pair(f"00000000-0000-4000-8000-{n:012d}", survivor)

        s1, s2 = "10000000-0000-4000-8000-000000000001", "10000000-0000-4000-8000-000000000002"
        pairs = [p(1, s1), p(2, s1), p(3, s2), p(4, s2)]
        waves = D.split_waves(pairs, max_sites=5)
        assert [len(w) for w in waves] == [2, 2]
        assert {x.survivor for x in waves[0]} == {s1} and {x.survivor for x in waves[1]} == {s2}
        assert [len(w) for w in D.split_waves(pairs, max_sites=100)] == [4]
        with pytest.raises(P.PlanError, match="one survivor has 3 sites"):
            D.split_waves(pairs, max_sites=2)

    def test_a_wave_file_is_written_once_and_read_back(self, tmp_path: Path) -> None:
        pairs = [
            pair(),
            pair(
                LOSER2,
                SURVIVOR2,
                loser_name="Ancient Amathunta",
                survivor_name="Amathus",
                metres_limit=2500,
            ),
        ]
        path = D.write_wave(WAVE, pairs, tmp_path)
        assert path == tmp_path / L.DUP_MERGE_ROOT / WAVE / "PAIRS.json"
        assert D.load_wave(WAVE, tmp_path) == pairs
        assert [(m.loser, m.metres_limit) for m in L.load_pairs(WAVE, tmp_path)] == [
            (LOSER, 2000),
            (LOSER2, 2500),
        ]
        with pytest.raises(P.PlanError, match="planned once"):
            D.write_wave(WAVE, pairs, tmp_path)

    def test_a_file_of_another_wave_is_refused(self, tmp_path: Path) -> None:
        D.write_wave(WAVE, [pair()], tmp_path)
        path = L.pairs_path(WAVE, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**data, "wave": "2026-10-11"}), encoding="utf-8")
        with pytest.raises(ValueError, match="is the file of wave"):
            L.load_pairs(WAVE, tmp_path)

    def test_a_missing_file_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="plan the wave first"):
            L.load_pairs(WAVE, tmp_path)


class TestTheLaneFamily:
    def test_a_pair_is_two_lower_case_uuids_that_differ(self) -> None:
        with pytest.raises(ValueError, match="two lower-case uuids"):
            L.MergePair("x", SURVIVOR)
        with pytest.raises(ValueError, match="two lower-case uuids"):
            L.MergePair(LOSER.upper(), SURVIVOR)
        with pytest.raises(ValueError, match="not its own survivor"):
            L.MergePair(LOSER, LOSER)

    def test_a_limit_only_widens(self) -> None:
        with pytest.raises(ValueError, match="only ever widens"):
            L.MergePair(LOSER, SURVIVOR, 1999)
        assert L.MergePair(LOSER, SURVIVOR, 2000).metres_limit == L.DUP_RETIRE_METRES

    @pytest.mark.parametrize(
        ("pairs", "message"),
        [
            ([], "at least one pair"),
            (
                [L.MergePair(LOSER, SURVIVOR), L.MergePair(LOSER, SURVIVOR2)],
                "two pairs of the wave",
            ),
            (
                [L.MergePair(LOSER, SURVIVOR), L.MergePair(SURVIVOR, SURVIVOR2)],
                "a chain, not a pair",
            ),
        ],
    )
    def test_a_wave_of_pairs_is_a_set_of_losers_without_a_chain(
        self, pairs: list[L.MergePair], message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            L.check_pairs(pairs)

    def test_two_losers_may_share_one_survivor(self) -> None:
        L.check_pairs([L.MergePair(LOSER, SURVIVOR), L.MergePair(LOSER2, SURVIVOR)])

    def test_the_names_are_the_wave_s_and_the_directories_are_apart(self) -> None:
        move, retire = lanes([pair()])
        assert (move.name, retire.name) == (f"dup-merge-move-{WAVE}", f"dup-merge-retire-{WAVE}")
        assert move.run_stamp != retire.run_stamp and move.plan_table != retire.plan_table
        assert (move.out_dir_name, retire.out_dir_name) == (
            f"mechanical_dup_merge/{WAVE}/move",
            f"mechanical_dup_merge/{WAVE}/retire",
        )
        assert move.row_cells and retire.cells and not retire.row_cells
        assert L.parent_lane(WAVE).out_dir_name == f"mechanical_parent/{WAVE}"

    def test_the_lanes_resolve_from_a_wave_s_pairs_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(L, "REMEDIATION_ROOT", tmp_path)
        with pytest.raises(KeyError, match="plan the wave first"):
            L.resolve_lane(f"dup-merge-move-{WAVE}")
        D.write_wave(WAVE, [pair()], tmp_path)
        assert L.resolve_lane(f"dup-merge-move-{WAVE}").row_cells
        assert L.resolve_lane(f"dup-merge-retire-{WAVE}").cells == L.DUPLICATE_HIDE_CELLS
        assert L.resolve_lane(f"parent-{WAVE}").cells == L.PARENT_CELLS
        for bad in ("dup-merge-move-tomorrow", "parent-2026-10", "dup-merge-undo-2026-10-10"):
            with pytest.raises(KeyError):
                L.resolve_lane(bad)

    def test_the_apply_cli_names_the_missing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import argparse

        monkeypatch.setattr(L, "REMEDIATION_ROOT", tmp_path)
        with pytest.raises(argparse.ArgumentTypeError, match="plan the wave first"):
            A._lane_argument(f"dup-merge-move-{WAVE}")

    def test_a_pair_with_its_own_limit_changes_only_the_retire_survivor_check(self) -> None:
        plain = L.dup_merge_retire_lane(WAVE, [L.MergePair(LOSER, SURVIVOR)])
        wide = L.dup_merge_retire_lane(WAVE, [L.MergePair(LOSER, SURVIVOR, 2500)])
        assert (
            plain.site_invariants[2].says == "planned site(s) name a survivor further than 2000 m"
        )
        assert "their limit" in wide.site_invariants[2].says
        assert f"WHEN '{LOSER}' THEN 2500 ELSE 2000 END" in wide.site_invariants[2].predicate
        assert plain.site_invariants[:2] == wide.site_invariants[:2]

    def test_the_per_loser_limit_is_read_in_sql(self) -> None:
        import sqlite3

        from tests.remediation.test_mechanical_rowlane import sqlite_world

        db: sqlite3.Connection = sqlite_world()
        db.execute("CREATE TABLE IF NOT EXISTS x (a)")
        for site_id, name, lat in (
            (LOSER, "Banias", 33.0),
            (SURVIVOR, "Caesarea Philippi", 33.0 + 0.0189),
            (LOSER2, "Ancient Amathunta", 34.0),
            (SURVIVOR2, "Amathus", 34.0 + 0.0189),
        ):
            db.execute(
                "INSERT INTO unified_sites VALUES (?, ?, 'ancient_nerds', NULL, NULL, ?, 35.0)",
                (site_id, name, lat),
            )
        db.execute(
            "UPDATE unified_sites SET scope_reason = 'duplicate_of:' || ? WHERE id = ?",
            (SURVIVOR, LOSER),
        )
        db.execute(
            "UPDATE unified_sites SET scope_reason = 'duplicate_of:' || ? WHERE id = ?",
            (SURVIVOR2, LOSER2),
        )
        wide = L.dup_merge_retire_lane(
            WAVE, [L.MergePair(LOSER, SURVIVOR, 2500), L.MergePair(LOSER2, SURVIVOR2)]
        )
        far = wide.site_invariants[2].predicate
        rows = dict(
            db.execute(
                f"SELECT u.id, {far} FROM unified_sites u WHERE u.id IN (?, ?)", (LOSER, LOSER2)
            ).fetchall()
        )
        # 2.1 km: inside the 2,500 m limit of the first pair, outside the 2,000 m default of the second
        assert rows == {LOSER: 0, LOSER2: 1}


# ------------------------------------------------------------------------------- the checks
class TestTheChecks:
    def check(self, read: D.Read, p: D.WavePair | None = None):
        move, _ = lanes([p or pair()])
        return D.check_pair(read, p or pair(), [move.run_stamp, move.rollback_run_stamp])

    def test_the_pair_as_decided_passes(self) -> None:
        loser, survivor = self.check(a_read())
        assert (loser["id"], survivor["id"]) == (LOSER, SURVIVOR)

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (
                lambda r: {"sites": {k: v for k, v in r.sites.items() if k != LOSER}},
                "the loser .* is not in unified_sites",
            ),
            (
                lambda r: {
                    "sites": {**r.sites, SURVIVOR: {**r.sites[SURVIVOR], "source_id": "geonames"}}
                },
                "survivor is not a curated site",
            ),
            (
                lambda r: {"sites": {**r.sites, LOSER: {**r.sites[LOSER], "name": "Banyas"}}},
                "the decision names 'Banias'",
            ),
            (
                lambda r: {
                    "sites": {
                        **r.sites,
                        SURVIVOR: {
                            **r.sites[SURVIVOR],
                            "scope_status": "retired",
                            "scope_reason": "x",
                        },
                    }
                },
                "the survivor is retired",
            ),
            (
                lambda r: {
                    "sites": {
                        **r.sites,
                        LOSER: {
                            **r.sites[LOSER],
                            "scope_status": "retired",
                            "scope_reason": "scope",
                        },
                    }
                },
                "retired for another reason",
            ),
            (
                lambda r: {
                    "onto": ({"id": OTHER, "name": "x", "scope_reason": f"duplicate_of:{LOSER}"},)
                },
                "retired onto the loser already",
            ),
            (lambda r: {"metres": {}}, "no distance"),
            (lambda r: {"metres": {LOSER: 2000.1}}, "limit is 2000 m"),
        ],
    )
    def test_each_check_holds_a_pair_back_on_its_own(self, change, message: str) -> None:
        with pytest.raises(D.Held, match=message):
            self.check(replace(a_read(), **change(a_read())))

    def test_a_loser_retired_for_the_survivor_is_a_pair_for_the_move(self) -> None:
        read = a_read()
        sites = {
            **read.sites,
            LOSER: {
                **read.sites[LOSER],
                "scope_status": "retired",
                "scope_reason": f"duplicate_of:{SURVIVOR}",
            },
        }
        self.check(replace(read, sites=sites), pair(already_retired=True))

    def test_a_loser_the_decision_calls_retired_but_which_is_shown_is_held(self) -> None:
        with pytest.raises(D.Held, match="says the loser is already retired"):
            self.check(a_read(), pair(already_retired=True))

    def test_a_pair_wider_than_two_kilometres_passes_with_its_own_limit(self) -> None:
        read = replace(a_read(), metres={LOSER: 2300.0})
        self.check(read, pair(metres_limit=2500))

    def test_a_lane_that_has_written_is_never_planned_again(self) -> None:
        move, _ = lanes([pair()])
        read = replace(a_read(), stamps={move.rollback_run_stamp: 3})
        with pytest.raises(P.PlanError, match="never re-planned"):
            self.check(read)


# ---------------------------------------------------------------------------------- the cells
class TestTheMoveCells:
    def cells(self, read: D.Read | None = None, p: D.WavePair | None = None):
        return D.move_cells(read or a_read(), p or pair())

    def summary(self, cells) -> list[tuple[str, str, str]]:
        return [(c.table, c.row_id, c.column) for c in cells]

    def test_the_loser_s_rows_move_and_a_collision_stays(self) -> None:
        cells, counts = self.cells()
        assert ("wiki_images", "1", "site_id") in self.summary(cells)
        assert ("wiki_images", "2", "site_id") in self.summary(cells)
        assert ("wiki_images", "3", "site_id") not in self.summary(
            cells
        )  # u/shared is on the survivor
        assert ("site_content_links", "1", "site_id") in self.summary(cells)
        assert ("site_content_links", "2", "site_id") not in self.summary(cells)
        assert counts["images"] == 2 and counts["images_stay"] == 1
        assert counts["links"] == 1 and counts["links_stay"] == 1

    def test_the_cell_moves_from_the_loser_to_the_survivor(self) -> None:
        cells, _ = self.cells()
        first = next(
            c for c in cells if (c.table, c.row_id, c.column) == ("wiki_images", "1", "site_id")
        )
        assert (first.site_id, first.old, first.new) == (LOSER, LOSER, SURVIVOR)

    def test_a_moved_hero_is_demoted_when_the_survivor_has_a_live_hero(self) -> None:
        cells, counts = self.cells()
        demote = [c for c in cells if c.column == "is_hero"]
        assert [(c.row_id, c.old, c.new) for c in demote] == [("1", "true", "false")]
        assert counts["heroes_demoted"] == 1

    def test_a_moved_hero_stays_when_the_survivor_has_none(self) -> None:
        read = a_read(
            images={
                LOSER: (img(1, LOSER, "u/1", hero=True), img(2, LOSER, "u/2")),
                SURVIVOR: (img(11, SURVIVOR, "u/own"),),
            }
        )
        cells, counts = self.cells(read)
        assert [c for c in cells if c.column == "is_hero"] == [] and counts["heroes_demoted"] == 0

    def test_a_survivor_hero_that_is_excluded_does_not_count(self) -> None:
        read = a_read(
            images={
                LOSER: (img(1, LOSER, "u/1", hero=True),),
                SURVIVOR: (img(11, SURVIVOR, "u/own", hero=True, excluded=True),),
            }
        )
        assert [c for c in self.cells(read)[0] if c.column == "is_hero"] == []

    def test_a_null_exclusion_is_live(self) -> None:
        read = a_read(
            images={
                LOSER: (img(1, LOSER, "u/1", hero=True, excluded=None),),
                SURVIVOR: (img(11, SURVIVOR, "u/own", hero=True, excluded=None),),
            }
        )
        assert [c.row_id for c in self.cells(read)[0] if c.column == "is_hero"] == ["1"]

    def test_all_but_the_first_of_several_moved_heroes_are_demoted(self) -> None:
        read = a_read(images={
            LOSER: (img(1, LOSER, "u/1", hero=True, sort=5), img(2, LOSER, "u/2", hero=True, sort=1), img(3, LOSER, "u/3", hero=True, sort=1)),
            SURVIVOR: (),
        })  # fmt: skip
        demoted = [c.row_id for c in self.cells(read)[0] if c.column == "is_hero"]
        assert demoted == ["3", "1"] or sorted(demoted) == ["1", "3"]
        assert "2" not in demoted  # the lowest sort order, then id, keeps the hero

    def test_an_excluded_image_moves_and_its_hero_flag_is_left_alone(self) -> None:
        read = a_read(
            images={
                LOSER: (img(1, LOSER, "u/1", hero=True, excluded=True),),
                SURVIVOR: (img(11, SURVIVOR, "u/own", hero=True),),
            }
        )
        cells, _ = self.cells(read)
        assert self.summary(cells)[:1] == [("wiki_images", "1", "site_id")]
        assert [c for c in cells if c.column == "is_hero"] == []

    def test_the_loser_s_name_row_becomes_an_alias_of_the_survivor(self) -> None:
        cells, counts = self.cells()
        names = [
            (c.row_id, c.column, c.old, c.new) for c in cells if c.table == "unified_site_names"
        ]
        assert names == [("5", "name_type", "label", "alias"), ("5", "site_id", LOSER, SURVIVOR)]
        assert counts["names"] == 1

    def test_a_name_row_that_is_an_alias_already_only_changes_site(self) -> None:
        read = a_read(names={LOSER: (nm(5, LOSER, "Banias", "banias", "alias"),), SURVIVOR: ()})
        assert [(c.column) for c in self.cells(read)[0] if c.table == "unified_site_names"] == [
            "site_id"
        ]

    def test_a_null_name_type_is_filled_not_replaced(self) -> None:
        read = a_read(names={LOSER: (nm(5, LOSER, "Banias", "banias", None),), SURVIVOR: ()})
        cell = next(c for c in self.cells(read)[0] if c.column == "name_type")
        assert (cell.old, cell.new) == ("", "alias")

    def test_a_name_the_survivor_holds_already_needs_no_cell(self) -> None:
        read = a_read(
            names={
                LOSER: (nm(5, LOSER, "Banias", "banias"),),
                SURVIVOR: (nm(6, SURVIVOR, "Banias", "banias", "alias"),),
            }
        )
        cells, counts = self.cells(read)
        assert [c for c in cells if c.table == "unified_site_names"] == [] and counts["names"] == 0

    def test_no_name_row_to_carry_the_alias_holds_the_pair(self) -> None:
        read = a_read(
            names={
                LOSER: (),
                SURVIVOR: (nm(6, SURVIVOR, "Caesarea Philippi", "caesarea philippi"),),
            }
        )
        with pytest.raises(D.Held, match="would need an INSERT"):
            self.cells(read)

    def test_the_lowest_row_of_the_name_key_carries_the_alias(self) -> None:
        read = a_read(
            names={
                LOSER: (
                    nm(9, LOSER, "Banias", "banias"),
                    nm(5, LOSER, "Banias", "banias", "alias"),
                ),
                SURVIVOR: (),
            }
        )
        assert {c.row_id for c in self.cells(read)[0] if c.table == "unified_site_names"} == {"5"}


# ---------------------------------------------------------------------------------- the move plan
class TestTheMovePlan:
    def test_the_plan_is_the_cells_of_the_loser_under_the_move_lane(self) -> None:
        plan, held, totals = moved()
        assert plan.lane.name == f"dup-merge-move-{WAVE}" and held == []
        assert [(v.table, v.row_id, v.column) for v in plan.changes] == [
            ("wiki_images", "1", "site_id"), ("wiki_images", "2", "site_id"), ("wiki_images", "1", "is_hero"),
            ("site_content_links", "1", "site_id"), ("unified_site_names", "5", "name_type"), ("unified_site_names", "5", "site_id"),
        ]  # fmt: skip
        assert plan.counters["cells"] == 6 and totals["pairs"] == 1 and plan.counters["sites"] == 1

    def test_every_cell_carries_the_premise_the_database_printed_and_the_evidence(self) -> None:
        plan, _, _ = moved()
        read = a_read()
        assert {v.premise for v in plan.changes} == {read.sites[LOSER]["move_premise"]}
        assert all(v.site_id == LOSER and v.rule == D.RULE_MOVE for v in plan.changes)
        quotes = [e["quote"] for v in plan.changes[:1] for e in v.evidence]
        assert any("MERGE 'Banias' into 'Caesarea Philippi'" in q for q in quotes)
        assert any("289.5 m apart" in q for q in quotes)

    def test_the_plan_is_renderable_by_the_row_lane(self) -> None:
        plan, _, _ = moved()
        records = [
            A.ChangeRecord(
                site_id=v.site_id,
                site_name=v.site_name,
                old_value=v.old_value,
                new_value=v.new_value,
                rule=v.rule,
                condition="c",
                reason="r",
                evidence=v.evidence,
                premise=v.premise,
                column=v.column,
                table=v.table,
                row_id=v.row_id,
            )
            for v in plan.changes
        ]
        sql = A.render_transaction(records, site_ids={LOSER}, lane=plan.lane)
        assert "apply_remediation_change(" in sql and "dup-merge-move-" + WAVE in sql
        assert A.rollback_statement(records, plan.lane).count("rollback") >= 1

    def test_a_premise_the_rows_do_not_give_holds_the_pair(self) -> None:
        read = a_read()
        sites = {
            **read.sites,
            LOSER: {**read.sites[LOSER], "move_premise": "Banias | something else"},
        }
        with pytest.raises(P.PlanError, match="no pair of the wave has a row to move"):
            moved(replace(read, sites=sites))

    def test_a_held_pair_is_listed_beside_the_planned_one(self) -> None:
        pairs = [
            pair(),
            pair(LOSER2, SURVIVOR2, loser_name="Ancient Amathunta", survivor_name="Amathus"),
        ]
        read = a_read(pairs)
        sites = {
            **read.sites,
            SURVIVOR2: {**read.sites[SURVIVOR2], "scope_status": "retired", "scope_reason": "x"},
        }
        plan, held, totals = moved(replace(read, sites=sites), pairs)
        assert totals["pairs"] == 1 and {v.site_id for v in plan.changes} == {LOSER}
        assert [(h["loser"], h["reason"]) for h in held] == [
            (LOSER2, "the survivor is retired ('x')")
        ]

    def test_a_pair_with_nothing_to_move_is_listed_for_its_retirement(self) -> None:
        pairs = [
            pair(),
            pair(LOSER2, SURVIVOR2, loser_name="Ancient Amathunta", survivor_name="Amathus"),
        ]
        read = a_read(pairs)
        read = replace(
            read,
            names={
                **read.names,
                LOSER2: (nm(7, LOSER2, "Ancient Amathunta", "ancient amathunta"),),
                SURVIVOR2: (
                    nm(8, SURVIVOR2, "Amathus", "amathus"),
                    nm(9, SURVIVOR2, "Ancient Amathunta", "ancient amathunta", "alias"),
                ),
            },
        )
        plan, held, _ = moved(read, pairs)
        assert {v.site_id for v in plan.changes} == {LOSER}
        assert [h["reason"] for h in held] == [
            "nothing to move: the pair goes straight to its retirement"
        ]

    def test_a_wave_with_nothing_to_move_is_refused(self) -> None:
        read = a_read(
            images={},
            links={},
            names={
                LOSER: (nm(5, LOSER, "Banias", "banias"),),
                SURVIVOR: (nm(6, SURVIVOR, "Banias", "banias", "alias"),),
            },
        )
        with pytest.raises(P.PlanError, match="nothing to plan"):
            moved(read)

    def test_a_lane_that_has_written_is_not_planned_again(self) -> None:
        move, _ = lanes([pair()])
        with pytest.raises(P.PlanError, match="never re-planned"):
            moved(a_read(stamps={move.run_stamp: 6}))


# -------------------------------------------------------------------------------- the retire plan
def after_the_move() -> D.Read:
    """The read taken after the move: the loser holds only collisions, its name is the survivor's."""
    read = a_read(
        images={LOSER: (img(3, LOSER, "u/shared"),), SURVIVOR: (img(10, SURVIVOR, "u/shared"), img(11, SURVIVOR, "u/own", hero=True), img(1, SURVIVOR, "u/1"), img(2, SURVIVOR, "u/2"))},
        links={LOSER: (link(2, LOSER, content="shared"),), SURVIVOR: (link(9, SURVIVOR, content="shared"), link(1, SURVIVOR, content="a"))},
        names={LOSER: (), SURVIVOR: (nm(6, SURVIVOR, "Caesarea Philippi", "caesarea philippi"), nm(5, SURVIVOR, "Banias", "banias", "alias"))},
    )  # fmt: skip
    return read


def retired(read: D.Read | None = None, pairs: list[D.WavePair] | None = None):
    pairs = pairs or [pair()]
    _, retire = lanes(pairs)
    return D.build_retire(read or after_the_move(), pairs, retire, NOW)


class TestTheRetirePlan:
    def test_the_loser_gets_its_two_cells(self) -> None:
        plan, held = retired()
        assert held == [] and plan.lane.name == f"dup-merge-retire-{WAVE}"
        assert [(v.column, v.old_value, v.new_value) for v in plan.changes] == [
            ("scope_status", None, "retired"), ("scope_reason", None, f"duplicate_of:{SURVIVOR}"),
        ]  # fmt: skip
        assert {v.premise for v in plan.changes} == {
            after_the_move().sites[LOSER]["retire_premise"]
        }

    def test_the_premise_counts_what_the_loser_holds_and_the_survivor_shows(self) -> None:
        premise = D.retire_premise(
            after_the_move(), after_the_move().sites[LOSER], after_the_move().sites[SURVIVOR]
        )
        assert premise == (
            "Banias | content links 1, images 1 | enwiki_title=Banias, wikidata_qid=Q606295 | "
            "survivor Caesarea Philippi | enwiki_title=Banias, wikidata_qid=Q606295 | live images 4"
        )

    def test_a_loser_whose_move_is_not_done_is_held(self) -> None:
        read = after_the_move()
        read = replace(
            read,
            images={**read.images, LOSER: (img(1, LOSER, "u/unmoved"), img(3, LOSER, "u/shared"))},
        )
        with pytest.raises(
            P.PlanError, match="image\\(s\\) the survivor lacks are still on the loser"
        ):
            retired(with_premises(read, [pair()]))

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (
                lambda r: {"links": {**r.links, LOSER: (link(1, LOSER, content="unmoved"),)}},
                "content link\\(s\\) the survivor lacks",
            ),
            (
                lambda r: {
                    "names": {
                        **r.names,
                        SURVIVOR: (nm(6, SURVIVOR, "Caesarea Philippi", "caesarea philippi"),),
                    }
                },
                "name is not among the survivor's",
            ),
            (
                lambda r: {"images": {**r.images, SURVIVOR: ()}, "links": r.links},
                "survivor lacks|survivor shows none",
            ),
            (
                lambda r: {
                    "sites": {
                        **r.sites,
                        LOSER: {**r.sites[LOSER], "scope_status": "pending", "scope_reason": "x"},
                    }
                },
                "already has a scope decision",
            ),
        ],
    )
    def test_each_incomplete_state_holds_the_loser(self, change, message: str) -> None:
        read = replace(after_the_move(), **change(after_the_move()))
        with pytest.raises(P.PlanError, match=message):
            retired(with_premises(read, [pair()]))

    def test_a_journal_that_does_not_end_at_the_live_value_holds_the_loser(self) -> None:
        read = replace(
            after_the_move(),
            journal={(LOSER, "scope_status"): (P.JournalLink(1, "s", "t", None, "pending"),)},
        )
        with pytest.raises(P.PlanError, match="journal-disagrees"):
            retired(read)

    def test_the_premise_must_be_the_one_the_rows_give(self) -> None:
        read = after_the_move()
        sites = {**read.sites, LOSER: {**read.sites[LOSER], "retire_premise": "drifted"}}
        with pytest.raises(P.PlanError, match="is not the one the read's rows give"):
            retired(replace(read, sites=sites))

    def test_an_already_retired_loser_is_not_planned(self) -> None:
        with pytest.raises(P.PlanError, match="no loser of the wave can be retired yet"):
            retired(pairs=[pair(already_retired=True)])

    def test_the_cells_render_under_the_retire_lane(self) -> None:
        plan, _ = retired()
        records = [
            A.ChangeRecord(
                site_id=v.site_id,
                site_name=v.site_name,
                old_value=v.old_value,
                new_value=v.new_value,
                rule=v.rule,
                condition="c",
                reason="r",
                evidence=v.evidence,
                premise=v.premise,
                column=v.column,
            )
            for v in plan.changes
        ]
        sql = A.render_transaction(records, site_ids={LOSER}, lane=plan.lane)
        assert (
            "D14 duplicate retirement" in sql
            and "live images" in sql
            and sql.count("-- site invariant:") == 3
        )


# ------------------------------------------------------------------------------------ the files
class TestTheFiles:
    def test_the_read_is_one_read_only_snapshot_of_the_wave(self) -> None:
        pairs = [pair()]
        move, retire = lanes(pairs)
        parts = D.read_parts(pairs, move, retire)
        assert [k for k, _ in parts] == [
            "site",
            "ext",
            "image",
            "link",
            "name",
            "metres",
            "onto",
            "journal",
            "stamp",
        ]
        script = P.tagged_export_script(parts)
        assert "READ ONLY" in script
        for verb in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER"):
            assert verb not in script.upper().replace("ON_ERROR_STOP", "")
        assert move.premise_sql in dict(parts)["site"] and retire.premise_sql in dict(parts)["site"]

    def test_the_tagged_read_becomes_the_read(self) -> None:
        pairs = [pair()]
        move, retire = lanes(pairs)
        lines = [
            {"kind": "site", "row": {"id": LOSER, "name": "Banias"}},
            {"kind": "site", "row": {"id": SURVIVOR, "name": "Caesarea Philippi"}},
            {"kind": "ext", "row": {"id": LOSER, "kind": "wikidata_qid", "value": "Q606295"}},
            {"kind": "image", "row": img(1, LOSER, "u/1")},
            {"kind": "link", "row": link(1, LOSER)},
            {"kind": "name", "row": nm(5, LOSER, "Banias", "banias")},
            {"kind": "metres", "row": {"loser": LOSER, "metres": 289.5}},
            {"kind": "onto", "row": {"id": OTHER, "name": "x", "scope_reason": "duplicate_of:y"}},
            {
                "kind": "journal",
                "row": {
                    "id": 7,
                    "row_pk": LOSER,
                    "column_name": "scope_status",
                    "run_stamp": "s",
                    "test_id": "",
                    "old_value": None,
                    "new_value": "retired",
                },
            },
            {"kind": "stamp", "row": {"run_stamp": move.run_stamp, "n": 0}},
            {"kind": "snapshot", "row": {"exported_at": "2026-10-10 10:00:00+00"}},
        ]
        read = D.parse_read("\n".join(json.dumps(x) for x in lines), pairs, move, retire)
        assert read.metres == {LOSER: 289.5} and read.ext[LOSER] == (("wikidata_qid", "Q606295"),)
        assert [i["id"] for i in read.images[LOSER]] == [1] and read.journal[
            (LOSER, "scope_status")
        ][0].id == 7
        assert read.read_at == "2026-10-10 10:00:00+00" and read.stamps == {move.run_stamp: 0}

    def test_a_read_with_a_line_of_another_kind_is_refused(self) -> None:
        pairs = [pair()]
        move, retire = lanes(pairs)
        text = (
            json.dumps({"kind": "mystery", "row": {}})
            + "\n"
            + json.dumps({"kind": "snapshot", "row": {"exported_at": "x"}})
        )
        with pytest.raises(P.PlanError, match="kind 'mystery'"):
            D.parse_read(text, pairs, move, retire)

    def test_the_plan_files_are_the_lane_s_and_the_rollback_comes_first(
        self, tmp_path: Path
    ) -> None:
        plan, held, _ = moved()
        D.write_plan(plan, held, a_read(), [pair()], tmp_path)
        directory = tmp_path / plan.lane.out_dir_name
        for name in ("PLAN.jsonl", "PLAN.md", "ROLLBACK.sql", D.HELD_FILE):
            assert (directory / name).exists(), name
        records = A.load_records(directory / "PLAN.jsonl")
        assert len(records) == 6 and records[0].table == "wiki_images"
        rollback = (directory / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert (
            rollback.startswith("-- plan sha256 ")
            and f"{WAVE}_mechanical-dup-merge-move-rollback" in rollback
        )
        md = (directory / "PLAN.md").read_text(encoding="utf-8")
        assert (
            "The reversal order is retire, then move." in md
            and f"--lane {plan.lane.name} --rehearse-rollback" in md
        )
        A.emit(records, directory, plan.lane, plan_path=directory / "PLAN.jsonl")
        assert (directory / "APPLY.sql").exists()

    def test_the_held_pairs_are_written_beside_the_plan(self, tmp_path: Path) -> None:
        plan, _, _ = moved()
        held = [{"loser": LOSER2, "survivor": SURVIVOR2, "name": "x", "reason": "because"}]
        D.write_plan(plan, held, a_read(), [pair()], tmp_path)
        text = (tmp_path / plan.lane.out_dir_name / D.HELD_FILE).read_text(encoding="utf-8")
        assert json.loads(text)["reason"] == "because"
        assert "## Held back" in (tmp_path / plan.lane.out_dir_name / "PLAN.md").read_text(
            encoding="utf-8"
        )


class TestTheCLI:
    def test_the_waves_command_writes_one_file_per_wave(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from identity import common

        run = tmp_path / "run"
        run.mkdir()
        common.write_jsonl(run / "DUP_DECISIONS.jsonl", [{
            "cluster_id": "dup-1", "status": "complete", "part_of": [], "wrong_id": [], "distinct": [], "held": [],
            "merges": [{"kind": "MERGE", "site_id": LOSER, "name": "Banias", "target": SURVIVOR, "target_name": "Caesarea Philippi", "why": "w", "quotes": [], "metres": 3.0, "metres_limit": 2000}],
        }])  # fmt: skip
        monkeypatch.setattr(common, "run_dir", lambda root=None: run)
        assert D.main(["--out", str(tmp_path / "out"), "waves", "--date", WAVE]) == 0
        assert json.loads(capsys.readouterr().out)[WAVE]["pairs"] == 1
        assert (tmp_path / "out" / L.DUP_MERGE_ROOT / WAVE / "PAIRS.json").exists()

    def test_a_plan_command_without_write_only_says_what_it_would_do(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        D.write_wave(WAVE, [pair()], tmp_path)
        assert D.main(["--out", str(tmp_path), "plan-move", "--wave", WAVE]) == 0
        assert "add --write" in capsys.readouterr().out

    def test_a_refusal_is_printed_and_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert D.main(["--out", str(tmp_path), "plan-move", "--wave", WAVE]) == 1
        assert "REFUSED" in capsys.readouterr().err


class StringAgg:
    """PostgreSQL's `string_agg(value, separator)` for SQLite, which orders it itself (3.44+)."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.separator = ""

    def step(self, value: str | None, separator: str) -> None:
        if value is not None:
            self.parts.append(value)
            self.separator = separator

    def finalize(self) -> str | None:
        return self.separator.join(self.parts) if self.parts else None


class TestThePremisesInSQL:
    """The SQL of each premise and the Python that rebuilds it from the read print the same text:
    guard 5 compares what the database prints with what the plan carries."""

    def database(self, read: D.Read) -> Any:
        import sqlite3

        db = sqlite3.connect(":memory:")
        db.create_aggregate("string_agg", 2, StringAgg)
        db.executescript(
            "CREATE TABLE unified_sites (id TEXT PRIMARY KEY, name TEXT);"
            "CREATE TABLE site_external_ids (site_id TEXT, kind TEXT, value TEXT);"
            "CREATE TABLE wiki_images (site_id TEXT, is_excluded INTEGER);"
            "CREATE TABLE site_content_links (site_id TEXT);"
        )
        for site_id, row in read.sites.items():
            db.execute("INSERT INTO unified_sites VALUES (?, ?)", (site_id, row["name"]))
        for site_id, ids in read.ext.items():
            db.executemany(
                "INSERT INTO site_external_ids VALUES (?, ?, ?)", [(site_id, k, v) for k, v in ids]
            )
        for site_id, images in read.images.items():
            db.executemany(
                "INSERT INTO wiki_images VALUES (?, ?)",
                [
                    (site_id, None if i["is_excluded"] is None else int(i["is_excluded"]))
                    for i in images
                ],
            )
        for site_id, links in read.links.items():
            db.executemany("INSERT INTO site_content_links VALUES (?)", [(site_id,) for _ in links])
        return db

    def printed(self, db: Any, sql: str) -> str:
        return db.execute(f"SELECT {sql} FROM unified_sites u WHERE u.id = ?", (LOSER,)).fetchone()[
            0
        ]

    def test_the_move_premise_is_the_name_the_ids_and_the_survivor_s_name_and_ids(self) -> None:
        read = after_the_move()
        move, _ = lanes([pair()])
        loser, survivor = read.sites[LOSER], read.sites[SURVIVOR]
        assert self.printed(self.database(read), move.premise_sql) == D.move_premise(
            read, loser, survivor
        )

    def test_the_retire_premise_adds_what_the_loser_holds_and_how_many_images_the_survivor_shows(
        self,
    ) -> None:
        read = after_the_move()
        _, retire = lanes([pair()])
        loser, survivor = read.sites[LOSER], read.sites[SURVIVOR]
        sql = self.printed(self.database(read), retire.premise_sql)
        assert sql == D.retire_premise(read, loser, survivor)
        assert sql.endswith("| live images 4")

    def test_an_excluded_image_of_the_survivor_is_not_live(self) -> None:
        read = after_the_move()
        images = {
            **read.images,
            SURVIVOR: (
                *read.images[SURVIVOR],
                img(12, SURVIVOR, "u/x", excluded=True),
                img(13, SURVIVOR, "u/y", excluded=None),
            ),
        }
        read = replace(read, images=images)
        _, retire = lanes([pair()])
        assert self.printed(self.database(read), retire.premise_sql).endswith("| live images 5")
        assert D.retire_premise(read, read.sites[LOSER], read.sites[SURVIVOR]).endswith(
            "| live images 5"
        )

    def test_a_site_the_lane_names_no_pair_for_prints_an_empty_survivor(self) -> None:
        read = after_the_move()
        move, _ = lanes([pair(OTHER, SURVIVOR)])
        assert self.printed(self.database(read), move.premise_sql).endswith("| survivor ")

    def test_the_parent_premise_is_the_name_the_country_and_the_point(self) -> None:
        import sqlite3

        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE unified_sites (id TEXT, name TEXT, country TEXT, lat REAL, lon REAL)"
        )
        db.execute(
            "INSERT INTO unified_sites VALUES (?, 'Theatre', 'Italy', 40.75, 14.5)", (LOSER,)
        )
        assert (
            db.execute(f"SELECT {L.PARENT_PREMISE_SQL} FROM unified_sites u").fetchone()[0]
            == "Theatre | Italy | 40.75, 14.5"
        )
        db.execute("UPDATE unified_sites SET country = NULL")
        assert (
            db.execute(f"SELECT {L.PARENT_PREMISE_SQL} FROM unified_sites u").fetchone()[0]
            == "Theatre | NULL | 40.75, 14.5"
        )


class TestTheWavesCommandOnNothing:
    def test_the_waves_command_writes_one_file_per_wave_and_refuses_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from identity import common

        run = tmp_path / "run"
        run.mkdir()
        common.write_jsonl(
            run / "DUP_DECISIONS.jsonl",
            [
                {
                    "cluster_id": "dup-1",
                    "status": "held",
                    "merges": [],
                    "part_of": [],
                    "wrong_id": [],
                    "distinct": [],
                    "held": [],
                }
            ],
        )
        monkeypatch.setattr(common, "run_dir", lambda root=None: run)
        assert D.main(["--out", str(tmp_path / "out"), "waves", "--date", WAVE]) == 1
        assert "holds no decided MERGE" in capsys.readouterr().err
        assert not (tmp_path / "out").exists()
