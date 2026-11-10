"""D14: do the duplicate pairs get exactly their move and their retirement - and nothing else?

`mechanical/dup_merge.py` turns `DUP_DECISIONS.jsonl` into waves (`PAIRS.json`), and a wave into two
plans: `dup-merge-move-<wave>` (the loser's images, content links and name row go to the survivor) and
`dup-merge-retire-<wave>` (the loser is retired as `duplicate_of:<survivor>`). Each plan is a pure
function of one read-only production read; every refusal below has its own test, and a pair the plan
cannot carry is held back, listed and never written.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
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
THIRD = "11111111-1111-4111-8111-111111111111"
THIRD_SURVIVOR = "22222222-2222-4222-8222-222222222222"
NOW = "2026-10-10T00:00:00+00:00"
QUOTES = (
    {
        "source": "https://en.wikipedia.org/wiki/Banias",
        "quote": "also known as",
        "url": "https://en.wikipedia.org/wiki/Banias",
    },
)


LIMIT_QUOTES = (
    {
        "source": "https://en.wikipedia.org/wiki/Amathus",
        "quote": "the two names denote one site",
        "url": "https://en.wikipedia.org/wiki/Amathus",
    },
)


def pair(loser: str = LOSER, survivor: str = SURVIVOR, **over: Any) -> D.WavePair:
    base: dict[str, Any] = {
        "loser": loser, "survivor": survivor, "loser_name": "Banias",
        "survivor_name": "Caesarea Philippi", "metres_limit": 2000, "already_retired": False,
        "cluster_id": "dup-1", "why": "one site", "quotes": QUOTES, "limit_evidence": (),
    }  # fmt: skip
    return D.WavePair(**{**base, **over})


def lanes(pairs: list[D.WavePair]) -> tuple[L.Lane, L.Lane]:
    return D._lanes(WAVE, pairs)


def img(
    i: int,
    site: str,
    url: str,
    *,
    hero: bool = False,
    excluded: bool | None = False,
    sort: int = 0,
    filename: str | None = None,
) -> dict[str, Any]:
    return {
        "id": i,
        "site_id": site,
        "original_url": url,
        "filename": filename or f"{i}.webp",
        "is_hero": hero,
        "is_excluded": excluded,
        "sort_order": sort,
    }


def sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def folders_of(images: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, dict[str, str]]:
    """The image folders as the rows describe them: every row's file is in the folder of its site,
    and its bytes are its URL's (two rows of one URL are one picture)."""
    listing: dict[str, dict[str, str]] = {}
    for site, rows in images.items():
        listing.setdefault(D.site_id_short(site), {}).update(
            {i["filename"]: sha(i["original_url"]) for i in rows}
        )
    return listing


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
        files={},
    )
    read = replace(read, **over)
    if "files" not in over:
        read = replace(read, files=folders_of(read.images))
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
                "metres": 10.0, "metres_limit": 2000, "limit_evidence": []}  # fmt: skip
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

    def test_the_override_s_evidence_reaches_the_pair(self) -> None:
        item = self.decision(LOSER, SURVIVOR, metres_limit=2500, limit_evidence=list(LIMIT_QUOTES))
        [only] = D.decided_pairs([item])
        assert only.limit_evidence == LIMIT_QUOTES

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
                limit_evidence=LIMIT_QUOTES,
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


class TestTheExclusion:
    """`waves --exclude`: decided pairs left out of the waves with their reason (O5: Tarxien and
    Dodona wait for part B), recorded beside the wave's PAIRS.json; a bad exclusion is refused."""

    def test_an_excluded_loser_leaves_the_waves_with_its_reason(self) -> None:
        pairs = [pair(), pair(LOSER2, SURVIVOR2)]
        kept, excluded = D.exclude_pairs(pairs, [{"loser": LOSER2, "reason": "O5"}])
        assert kept == [pairs[0]]
        assert [(e["loser"], e["excluded_because"]) for e in excluded] == [(LOSER2, "O5")]

    @pytest.mark.parametrize(
        ("exclusions", "message"),
        [
            ([{"loser": OTHER, "reason": "x"}], "no decided pair"),
            ([{"loser": LOSER, "reason": " "}], "needs a loser id and a reason"),
            ([{"loser": LOSER}], "needs a loser id and a reason"),
            ([{"loser": LOSER, "reason": "a"}, {"loser": LOSER, "reason": "b"}], "twice"),
        ],
    )
    def test_a_bad_exclusion_is_refused(self, exclusions, message: str) -> None:
        with pytest.raises(P.PlanError, match=message):
            D.exclude_pairs([pair()], exclusions)

    def test_the_cli_writes_the_kept_pairs_and_the_excluded_file(self, tmp_path: Path) -> None:
        run = tmp_path / "root" / "output" / "remediation" / "final-2026-10-08" / "identity"
        run.mkdir(parents=True)
        decision = TestTheWaves().decision
        rows = [decision(LOSER, SURVIVOR), {**decision(LOSER2, SURVIVOR2), "cluster_id": "dup-2"}]
        (run / "DUP_DECISIONS.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        exclude = tmp_path / "exclude.json"
        exclude.write_text(json.dumps([{"loser": LOSER2, "reason": "O5"}]), encoding="utf-8")
        out = tmp_path / "out"
        argv = ["--root", str(tmp_path / "root"), "--out", str(out), "waves", "--date", WAVE]
        assert D.main([*argv, "--exclude", str(exclude)]) == 0
        assert [p.loser for p in D.load_wave(WAVE, out)] == [LOSER]
        data = json.loads((L.pairs_path(WAVE, out).with_name(D.EXCLUDED_FILE)).read_text("utf-8"))
        assert [(e["loser"], e["excluded_because"]) for e in data["excluded"]] == [(LOSER2, "O5")]


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
            (THIRD, "Third", 35.0),
            (THIRD_SURVIVOR, "Third survivor", 35.0 + 0.0171),
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
        db.execute(
            "UPDATE unified_sites SET scope_reason = 'duplicate_of:' || ? WHERE id = ?",
            (THIRD_SURVIVOR, THIRD),
        )
        wide = L.dup_merge_retire_lane(
            WAVE,
            [
                L.MergePair(LOSER, SURVIVOR, 2500),
                L.MergePair(LOSER2, SURVIVOR2),
                L.MergePair(THIRD, THIRD_SURVIVOR),
            ],
        )
        far = wide.site_invariants[2].predicate
        rows = dict(
            db.execute(
                f"SELECT u.id, {far} FROM unified_sites u WHERE u.id IN (?, ?, ?)",
                (LOSER, LOSER2, THIRD),
            ).fetchall()
        )
        # 2.1 km: inside the 2,500 m limit of the first pair, outside the 2,000 m default of the
        # second; 1.9 km: inside the default of the third, which the first pair's limit does not touch
        assert rows == {LOSER: 0, LOSER2: 1, THIRD: 0}


class TestTheDecidedSurvivorInvariant:
    """The retirement lands on the survivor the wave decided, not on another curated site near the
    loser (the move lane's `dest-named-near`, for the retire lane)."""

    PAIRS = [L.MergePair(LOSER, SURVIVOR), L.MergePair(LOSER2, SURVIVOR2)]
    NEIGHBOUR = "33333333-3333-4333-8333-333333333333"

    def world(self) -> Any:
        from tests.remediation.test_mechanical_rowlane import sqlite_world

        db = sqlite_world()
        for site_id, name, lat in (
            (LOSER, "Banias", 33.0),
            (SURVIVOR, "Caesarea Philippi", 33.0 + 0.0045),
            (LOSER2, "Ancient Amathunta", 34.0),
            (SURVIVOR2, "Amathus", 34.0 + 0.0045),
            (self.NEIGHBOUR, "Neighbour", 33.0 + 0.0090),
        ):
            db.execute(
                "INSERT INTO unified_sites VALUES (?, ?, 'ancient_nerds', NULL, NULL, ?, 35.0)",
                (site_id, name, lat),
            )
        for loser, survivor in ((LOSER, SURVIVOR), (LOSER2, SURVIVOR2)):
            db.execute(
                "UPDATE unified_sites SET scope_status = 'retired', scope_reason = ? WHERE id = ?",
                (f"duplicate_of:{survivor}", loser),
            )
        return db

    def broken(self, db: Any, site: str) -> int:
        invariant = L.decided_survivor_invariant(self.PAIRS)
        return db.execute(
            f"SELECT {invariant.predicate} FROM unified_sites u WHERE u.id = ?", (site,)
        ).fetchone()[0]

    def test_the_retire_lane_ends_with_it_and_probes_it_with_a_neighbour(self) -> None:
        retire = L.dup_merge_retire_lane(WAVE, self.PAIRS)
        last = retire.site_invariants[-1]
        assert [i.probe_name for i in retire.site_invariants][-1] == "survivor-decided"
        assert last.probe_column == "scope_reason"
        assert last.probe_values == (f"duplicate_of:{L.PROBE_NEIGHBOUR}",)
        assert len(retire.site_invariants) == 4

    def test_the_decided_survivor_breaks_nothing_and_another_curated_site_does(self) -> None:
        db = self.world()
        assert (self.broken(db, LOSER), self.broken(db, LOSER2)) == (0, 0)
        db.execute(
            "UPDATE unified_sites SET scope_reason = ? WHERE id = ?",
            (f"duplicate_of:{self.NEIGHBOUR}", LOSER),
        )
        assert (self.broken(db, LOSER), self.broken(db, LOSER2)) == (1, 0)
        # another pair's survivor is as wrong as a stranger: each loser has its own
        db.execute(
            "UPDATE unified_sites SET scope_reason = ? WHERE id = ?",
            (f"duplicate_of:{SURVIVOR2}", LOSER),
        )
        assert self.broken(db, LOSER) == 1

    def test_the_neighbour_probe_passes_the_three_survivor_checks_and_only_this_one_fires(
        self,
    ) -> None:
        db = self.world()
        db.execute(
            "UPDATE unified_sites SET scope_reason = ? WHERE id = ?",
            (f"duplicate_of:{self.NEIGHBOUR}", LOSER),
        )
        retire = L.dup_merge_retire_lane(WAVE, self.PAIRS)
        fired = [
            i.probe_name
            for i in retire.site_invariants
            if db.execute(
                f"SELECT {i.predicate} FROM unified_sites u WHERE u.id = ?", (LOSER,)
            ).fetchone()[0]
        ]
        assert fired == ["survivor-decided"]

    def test_the_neighbour_is_the_nearest_curated_shown_site_that_is_not_planned(self) -> None:
        db = self.world()
        sql = L.survivor_neighbour_sql(LOSER, SURVIVOR, [LOSER, LOSER2])
        assert db.execute(sql).fetchall() == [(self.NEIGHBOUR,)]
        planned = L.survivor_neighbour_sql(LOSER, SURVIVOR, [LOSER, self.NEIGHBOUR])
        assert db.execute(planned).fetchall() == []
        # a planned loser (retired inside the probe), a retired and a far site are no neighbours
        db.execute(
            "UPDATE unified_sites SET scope_status = 'retired' WHERE id = ?", (self.NEIGHBOUR,)
        )
        assert db.execute(sql).fetchall() == []
        db.execute(
            "UPDATE unified_sites SET scope_status = NULL, lat = 40.0 WHERE id = ?",
            (self.NEIGHBOUR,),
        )
        assert db.execute(sql).fetchall() == []

    def test_a_single_probe_value_that_is_no_placeholder_is_refused(self) -> None:
        with pytest.raises(ValueError, match="one placeholder"):
            L.SiteInvariant(
                says="x", predicate="1 = 0", probe_column="scope_reason", probe_values=("x",)
            )

    def records(self, pairs: Sequence[tuple[str, str]]) -> list[A.ChangeRecord]:
        return [
            A.ChangeRecord(site_id=loser, site_name="n", old_value=None, new_value=v, rule="r", condition="c", reason="r", evidence=({"source": "t", "quote": "q"},), premise="p", column=c)
            for loser, survivor in pairs
            for c, v in (("scope_status", "retired"), ("scope_reason", f"duplicate_of:{survivor}"))
        ]  # fmt: skip

    def test_probing_reads_the_neighbour_of_the_first_loser_and_a_lonely_one_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        retire = L.dup_merge_retire_lane(WAVE, self.PAIRS)
        records = self.records([(LOSER, SURVIVOR)])
        asked: list[str] = []

        def reader(rows: list[dict[str, str]]) -> Any:
            return lambda: lambda sql: asked.append(sql) or rows

        monkeypatch.setattr(A, "psql_json_reader", reader([{"id": self.NEIGHBOUR}]))
        assert A.neighbour_of(records, retire) == {
            "neighbour": self.NEIGHBOUR,
            "neighbour_of": LOSER,
        }
        assert f"= '{LOSER}'" in asked[0] and f"<> '{SURVIVOR}'" in asked[0]
        monkeypatch.setattr(A, "psql_json_reader", reader([]))
        with pytest.raises(P.PlanError, match="cannot be probed with this plan"):
            A.neighbour_of(records, retire)
        # a plan without the cell it would corrupt reads nothing either
        assert A.neighbour_of(records[:1], retire) == {}
        # a lane that probes with no placeholder reads nothing
        assert A.neighbour_of(records, L.DUP_RETIRE) == {}
        # and the probe splices the id in
        cases = {
            c[0]: c for c in A.probe_cases(records, retire, {"id": "x", "name": "n", "premise": "p", "neighbour": self.NEIGHBOUR, "neighbour_of": LOSER})
        }  # fmt: skip
        assert (
            cases["invariant-survivor-decided"][2][1].new_value == f"duplicate_of:{self.NEIGHBOUR}"
        )

    def test_a_lonely_first_loser_is_passed_over_for_the_first_that_has_a_neighbour(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gap G3: about a third of the duplicates have no other curated site within 2,000 m. The
        probe takes the first planned loser that has one and corrupts that loser's cell: the
        neighbour is near it and far from every other planned site."""
        retire = L.dup_merge_retire_lane(WAVE, self.PAIRS)
        records = self.records([(LOSER, SURVIVOR), (LOSER2, SURVIVOR2)])
        asked: list[str] = []

        def answer(sql: str) -> list[dict[str, str]]:
            asked.append(sql)
            return [{"id": self.NEIGHBOUR}] if f"= '{LOSER2}'" in sql else []

        monkeypatch.setattr(A, "psql_json_reader", lambda: answer)
        found = A.neighbour_of(records, retire)
        assert found == {"neighbour": self.NEIGHBOUR, "neighbour_of": LOSER2}
        # the losers are asked in plan order, each with its own survivor left out, and every
        # planned site left out of both readings
        assert len(asked) == 2 and f"= '{LOSER}'" in asked[0] and f"<> '{SURVIVOR2}'" in asked[1]
        assert f"'{LOSER2}'" in asked[0].split("NOT IN")[1]
        assert f"'{LOSER}'" in asked[1].split("NOT IN")[1]
        probes = A.probe_cases(records, retire, {"id": "x", "name": "n", "premise": "p", **found})
        mutated = next(p[2] for p in probes if p[0] == "invariant-survivor-decided")
        changed = [
            (m.site_id, m.new_value) for m, r in zip(mutated, records, strict=True) if m != r
        ]
        assert changed == [(LOSER2, f"duplicate_of:{self.NEIGHBOUR}")]
        # the three survivor checks need no neighbour: they still corrupt the plan's first loser
        for suffix in ("survivor-not-curated", "survivor-retired", "survivor-far"):
            other = next(p[2] for p in probes if p[0] == f"invariant-{suffix}")
            assert [m.site_id for m, r in zip(other, records, strict=True) if m != r] == [LOSER]

    def test_a_wave_in_which_no_loser_has_a_neighbour_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        retire = L.dup_merge_retire_lane(WAVE, self.PAIRS)
        records = self.records([(LOSER, SURVIVOR), (LOSER2, SURVIVOR2)])
        asked: list[str] = []
        monkeypatch.setattr(A, "psql_json_reader", lambda: lambda sql: asked.append(sql) or [])
        with pytest.raises(P.PlanError, match="none of the 2 planned site\\(s\\) has another"):
            A.neighbour_of(records, retire)
        assert len(asked) == 2  # every loser was asked before the refusal


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

    def test_a_pair_beyond_two_kilometres_journals_the_evidence_of_its_limit(self) -> None:
        plan, _, _ = moved(pairs=[pair(metres_limit=2500, limit_evidence=LIMIT_QUOTES)])
        quotes = [e["quote"] for e in plan.changes[0].evidence]
        assert "the two names denote one site" in quotes
        plain, _, _ = moved()
        assert "the two names denote one site" not in [
            e["quote"] for e in plain.changes[0].evidence
        ]

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
    def test_the_retirement_journals_the_evidence_of_a_widened_limit(self) -> None:
        plan, _ = retired(pairs=[pair(metres_limit=2500, limit_evidence=LIMIT_QUOTES)])
        assert "the two names denote one site" in [e["quote"] for e in plan.changes[0].evidence]

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
            images={**read.images, LOSER: (img(7, LOSER, "u/unmoved"), img(3, LOSER, "u/shared"))},
        )
        read = replace(read, files=folders_of(read.images))
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
                lambda r: {
                    "images": {
                        **r.images,
                        SURVIVOR: (img(10, SURVIVOR, "u/shared", excluded=True),),
                    }
                },
                "loser shows an image and the survivor shows none",
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
        with pytest.raises(P.PlanError, match="no loser of the wave can be retired yet") as refused:
            retired(pairs=[pair(already_retired=True)])
        assert "\n  - " not in str(refused.value)  # skipped, not held back with a reason

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
            and sql.count("-- site invariant:") == 4
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
        # the filename is what a row's picture is served under: the plans need it
        assert "w.filename" in dict(parts)["image"]

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
        folders = {D.site_id_short(LOSER): {"1.webp": sha("u/1")}}
        text = "\n".join(json.dumps(x) for x in lines)
        read = D.parse_read(text, pairs, move, retire, folders)
        assert read.files == folders and read.images[LOSER][0]["filename"] == "1.webp"
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
            D.parse_read(text, pairs, move, retire, {})

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
            and "stops at `uq_usn`" in md
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
            "merges": [{"kind": "MERGE", "site_id": LOSER, "name": "Banias", "target": SURVIVOR, "target_name": "Caesarea Philippi", "why": "w", "quotes": [], "metres": 3.0, "metres_limit": 2000, "limit_evidence": []}],
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
            "CREATE TABLE unified_sites (id TEXT PRIMARY KEY, name TEXT, scope_status TEXT, "
            "scope_reason TEXT);"
            "CREATE TABLE site_external_ids (site_id TEXT, kind TEXT, value TEXT);"
            "CREATE TABLE wiki_images (site_id TEXT, is_excluded INTEGER);"
            "CREATE TABLE site_content_links (site_id TEXT);"
        )
        for site_id, row in read.sites.items():
            db.execute(
                "INSERT INTO unified_sites VALUES (?, ?, ?, ?)",
                (site_id, row["name"], row["scope_status"], row["scope_reason"]),
            )
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

    def test_the_move_premise_names_the_loser_s_scope_so_the_move_cannot_be_undone_while_it_is_retired(
        self,
    ) -> None:
        """The retirement is rolled back first, then the move: a loser that is retired prints
        another premise than the one the move was planned on, and guard 5 refuses the reversal."""
        read = after_the_move()
        move, _ = lanes([pair()])
        planned = D.move_premise(read, read.sites[LOSER], read.sites[SURVIVOR])
        assert "| NULL | NULL | survivor " in planned
        retired_site = {
            **read.sites[LOSER],
            "scope_status": "retired",
            "scope_reason": f"duplicate_of:{SURVIVOR}",
        }
        retired_read = replace(read, sites={**read.sites, LOSER: retired_site})
        printed = self.printed(self.database(retired_read), move.premise_sql)
        assert printed == D.move_premise(retired_read, retired_site, read.sites[SURVIVOR])
        assert printed != planned and f"| retired | duplicate_of:{SURVIVOR} | survivor " in printed

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


class TestTwoLosersOneSurvivor:
    """A survivor that two losers of one wave move onto is met by the second as the first left it."""

    SECOND = "99999999-9999-4999-8999-999999999999"

    def pairs(self) -> list[D.WavePair]:
        return [pair(), pair(self.SECOND, SURVIVOR, loser_name="banias")]

    def read(self, **over: Any) -> D.Read:
        base: dict[str, Any] = {
            "images": {
                LOSER: (img(1, LOSER, "u/a", hero=True), img(2, LOSER, "u/both")),
                self.SECOND: (img(3, self.SECOND, "u/b", hero=True), img(4, self.SECOND, "u/both")),
                SURVIVOR: (img(10, SURVIVOR, "u/own"),),
            },
            "links": {
                LOSER: (link(1, LOSER, content="x"),),
                self.SECOND: (link(2, self.SECOND, content="x"),),
                SURVIVOR: (),
            },
            "names": {
                LOSER: (nm(5, LOSER, "Banias", "banias"),),
                self.SECOND: (nm(6, self.SECOND, "banias", "banias"),),
                SURVIVOR: (nm(9, SURVIVOR, "Caesarea Philippi", "caesarea philippi"),),
            },
        }
        return a_read(self.pairs(), **{**base, **over})

    def planned(self, **over: Any):
        pairs = self.pairs()
        move, _ = lanes(pairs)
        plan, held, totals = D.build_move(self.read(**over), pairs, move, NOW)
        return plan, held, totals

    def cells(self, plan: P.Plan, site: str) -> set[tuple[str, str, str]]:
        return {(v.table, v.row_id, v.column) for v in plan.changes if v.site_id == site}

    def test_a_url_both_losers_hold_moves_once(self) -> None:
        plan, _, totals = self.planned()
        assert ("wiki_images", "2", "site_id") in self.cells(plan, LOSER)
        assert ("wiki_images", "4", "site_id") not in self.cells(plan, self.SECOND)
        assert totals["images"] == 3 and totals["images_stay"] == 1

    def test_the_first_hero_stays_and_the_second_is_demoted(self) -> None:
        plan, _, totals = self.planned()
        assert ("wiki_images", "1", "is_hero") not in self.cells(plan, LOSER)
        assert ("wiki_images", "3", "is_hero") in self.cells(plan, self.SECOND)
        assert totals["heroes_demoted"] == 1

    def test_a_content_link_both_hold_moves_once(self) -> None:
        plan, _, totals = self.planned()
        assert ("site_content_links", "1", "site_id") in self.cells(plan, LOSER)
        assert ("site_content_links", "2", "site_id") not in self.cells(plan, self.SECOND)
        assert totals["links"] == 1 and totals["links_stay"] == 1

    def test_a_name_key_both_hold_moves_once(self) -> None:
        plan, _, totals = self.planned()
        assert ("unified_site_names", "5", "site_id") in self.cells(plan, LOSER)
        assert not [c for c in self.cells(plan, self.SECOND) if c[0] == "unified_site_names"]
        assert totals["names"] == 1

    def test_a_survivor_with_a_hero_demotes_both(self) -> None:
        images = {
            LOSER: (img(1, LOSER, "u/a", hero=True),),
            self.SECOND: (img(3, self.SECOND, "u/b", hero=True),),
            SURVIVOR: (img(10, SURVIVOR, "u/own", hero=True),),
        }
        plan, _, totals = self.planned(images=images)
        assert totals["heroes_demoted"] == 2
        assert {
            c for c in self.cells(plan, LOSER) | self.cells(plan, self.SECOND) if c[2] == "is_hero"
        } == {
            ("wiki_images", "1", "is_hero"),
            ("wiki_images", "3", "is_hero"),
        }

    def test_a_held_pair_adds_nothing_to_what_the_next_one_meets(self) -> None:
        names = {
            LOSER: (),
            self.SECOND: (nm(6, self.SECOND, "banias", "banias"),),
            SURVIVOR: (nm(9, SURVIVOR, "Caesarea Philippi", "caesarea philippi"),),
        }
        plan, held, _ = self.planned(names=names)
        assert [h["loser"] for h in held] == [LOSER]
        assert ("wiki_images", "4", "site_id") in self.cells(
            plan, self.SECOND
        )  # not taken by the held pair
        assert ("unified_site_names", "6", "site_id") in self.cells(plan, self.SECOND)


# ------------------------------------------------------------------------------ the pictures
FOLDER_L, FOLDER_S = D.site_id_short(LOSER), D.site_id_short(SURVIVOR)
BASH = shutil.which("bash")


def _bash_can(probe: str) -> bool:
    """Whether the local bash runs `probe` in a temp directory: the tests that run the lane's own
    scripts need what the VPS has, and say so when this machine does not."""
    if BASH is None:
        return False
    with tempfile.TemporaryDirectory() as scratch:
        done = subprocess.run([BASH, "-s"], input=probe.encode(), capture_output=True, cwd=scratch)
    return done.returncode == 0


#: GNU find and `sha256sum -b -z` (a Windows shell whose `find` is find.exe has neither).
needs_the_listing_tools = pytest.mark.skipif(
    not _bash_can("find . -maxdepth 0 -type d -exec sha256sum -b -z --version {} + > /dev/null\n"),
    reason="no bash with GNU find and sha256sum -b -z on this machine",
)
#: A file system with POSIX modes (Git Bash on Windows cannot `mkdir -m 777`: measured 2026-11-10).
needs_the_copy_tools = pytest.mark.skipif(
    not _bash_can("mkdir -m 777 x && cp --version > /dev/null && chmod 666 x\n"),
    reason="no bash that can mkdir -m 777 here (a Windows file system): the copy script cannot run",
)


def entry(name: str, content: str | None = None, row: int = 1) -> dict[str, str]:
    """One line of FILES.jsonl: the picture `name` of the loser, planned with `content`'s bytes."""
    return {
        "row_id": str(row),
        "filename": name,
        "source": f"{FOLDER_L}/{name}",
        "dest": f"{FOLDER_S}/{name}",
        "sha256": sha(name if content is None else content),
    }


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A wiki image tree in a temp directory. `run_on_vps` runs as it is, with one change: what it
    would hand to `ssh ancientnerds bash -s` goes to the local bash, inside that tree."""
    root = tmp_path / "wiki"
    root.mkdir()
    real = subprocess.run

    def instead_of_ssh(argv: list[str], **kwargs: Any) -> Any:
        assert argv[0] == "ssh" and argv[-3:] == [D.SSH_HOST, "bash", "-s"], argv
        return real([BASH, "-s"], cwd=root, **kwargs)

    monkeypatch.setattr(D.subprocess, "run", instead_of_ssh)
    monkeypatch.setattr(D, "WIKI_TREE", ".")
    return root


def put(root: Path, folder: str, name: str, content: str | None = None) -> Path:
    (root / folder).mkdir(exist_ok=True)
    path = root / folder / name
    path.write_bytes((name if content is None else content).encode())
    return path


class TestAFilenameTheSurvivorUses:
    """Gap G1: a row's picture is served from `<folder of its site>/<filename>`, and no key keeps
    two rows of one site off one filename. A row that would land on another picture's filename
    stays on the loser, like a row whose URL the survivor holds."""

    def images(self) -> dict[str, tuple[dict[str, Any], ...]]:
        return {
            LOSER: (img(1, LOSER, "u/1", hero=True, filename="hero.webp"), img(2, LOSER, "u/2")),
            SURVIVOR: (img(11, SURVIVOR, "u/own", hero=True, filename="hero.webp"),),
        }

    def test_a_row_whose_filename_a_row_of_the_survivor_uses_stays(self) -> None:
        cells, counts = D.move_cells(a_read(images=self.images()), pair())
        # neither the move nor the demotion of row 1: it is not touched at all
        assert [(c.row_id, c.column) for c in cells if c.table == "wiki_images"] == [
            ("2", "site_id")
        ]
        assert (counts["images"], counts["images_stay"], counts["images_stay_filename"]) == (
            1,
            0,
            1,
        )

    def test_a_file_no_row_names_keeps_its_name_too(self) -> None:
        """The folder is asked, not only the rows: 4 of the 272 folders read on 2026-11-10 hold a
        `hero.webp` no row names."""
        images = {LOSER: (img(1, LOSER, "u/1", filename="hero.webp"),), SURVIVOR: ()}
        files = {
            FOLDER_L: {"hero.webp": sha("u/1")},
            FOLDER_S: {"hero.webp": sha("another picture")},
        }
        cells, counts = D.move_cells(a_read(images=images, files=files), pair())
        assert [c for c in cells if c.table == "wiki_images"] == []
        assert counts["images_stay_filename"] == 1

    def test_the_same_file_in_the_survivor_s_folder_is_no_other_picture(self) -> None:
        images = {LOSER: (img(1, LOSER, "u/1", filename="hero.webp"),), SURVIVOR: ()}
        files = {FOLDER_L: {"hero.webp": sha("u/1")}, FOLDER_S: {"hero.webp": sha("u/1")}}
        cells, counts = D.move_cells(a_read(images=images, files=files), pair())
        assert [(c.row_id, c.column) for c in cells if c.table == "wiki_images"] == [
            ("1", "site_id")
        ]
        assert counts["images_stay_filename"] == 0

    def test_an_image_whose_file_is_not_in_the_loser_s_folder_holds_the_pair(self) -> None:
        read = a_read(files={FOLDER_L: {"2.webp": sha("u/2")}, FOLDER_S: {}})
        with pytest.raises(D.Held, match="row 1 names the file '1.webp'.*no picture to carry"):
            D.move_cells(read, pair())
        # row 3 stays for its URL and is asked for no file
        read = a_read(files={FOLDER_L: {"1.webp": sha("u/1"), "2.webp": sha("u/2")}})
        assert D.move_cells(read, pair())[1]["images"] == 2

    def test_the_plan_counts_the_rows_that_stay_for_their_filename(self) -> None:
        plan, held, totals = moved(a_read(images=self.images()))
        assert held == [] and totals["images_stay_filename"] == 1
        assert plan.counters["images_stay_filename"] == 1

    def test_a_second_loser_meets_the_filename_the_first_one_moved(self) -> None:
        second = TestTwoLosersOneSurvivor.SECOND
        pairs = [pair(), pair(second, SURVIVOR, loser_name="banias")]
        images = {
            LOSER: (img(1, LOSER, "u/a", filename="plan.webp"),),
            second: (img(3, second, "u/b", filename="plan.webp"), img(4, second, "u/c")),
            SURVIVOR: (),
        }
        read = a_read(pairs, images=images, links={})
        move, _ = lanes(pairs)
        plan, _, totals = D.build_move(read, pairs, move, NOW)
        assert [(v.site_id, v.row_id) for v in plan.changes if v.table == "wiki_images"] == [
            (LOSER, "1"),
            (second, "4"),
        ]
        assert totals["images"] == 2 and totals["images_stay_filename"] == 1

    def after(self, loser_extra: dict[str, Any], survivor_extra: tuple[dict[str, Any], ...]):
        read = after_the_move()
        images = {
            LOSER: (*read.images[LOSER], loser_extra),
            SURVIVOR: (*read.images[SURVIVOR], *survivor_extra),
        }
        return replace(read, images=images, files=folders_of(images))

    def test_the_retirement_takes_a_row_that_stayed_for_its_filename(self) -> None:
        read = self.after(
            img(7, LOSER, "u/the-loser-s-hero", filename="hero.webp"),
            (img(12, SURVIVOR, "u/the-survivor-s-hero", filename="hero.webp"),),
        )
        plan, held = retired(with_premises(read, [pair()]))
        assert held == [] and len(plan.changes) == 2

    def test_the_retirement_takes_a_row_whose_name_a_file_without_a_row_uses(self) -> None:
        read = self.after(img(7, LOSER, "u/the-loser-s-hero", filename="hero.webp"), ())
        files = {**read.files, FOLDER_S: {**read.files[FOLDER_S], "hero.webp": sha("an old hero")}}
        plan, held = retired(with_premises(replace(read, files=files), [pair()]))
        assert held == [] and len(plan.changes) == 2

    def test_a_copied_file_whose_row_is_still_on_the_loser_is_a_move_not_done(self) -> None:
        """`files --copy` ran, the apply did not: the picture is in both folders and its row on
        the loser - the survivor lacks it."""
        read = self.after(img(7, LOSER, "u/unmoved"), ())
        files = {**read.files, FOLDER_S: {**read.files[FOLDER_S], "7.webp": sha("u/unmoved")}}
        with pytest.raises(P.PlanError, match="1 image\\(s\\) the survivor lacks"):
            retired(with_premises(replace(read, files=files), [pair()]))


class TestTheFileList:
    """`FILES.jsonl`: the picture of every image row the move plan moves."""

    def written(self, tmp_path: Path) -> Path:
        plan, held, _ = moved()
        return D.write_plan(plan, held, a_read(), [pair()], tmp_path)

    def load(self, directory: Path) -> list[dict[str, str]]:
        return D.load_files(directory / D.FILES_FILE, directory / "PLAN.jsonl")

    def test_each_moved_image_row_names_its_file_and_where_it_is_served_from(self) -> None:
        plan, _, _ = moved()
        assert D.move_files(plan, a_read()) == [
            {
                "row_id": str(n),
                "filename": f"{n}.webp",
                "source": f"{FOLDER_L}/{n}.webp",
                "dest": f"{FOLDER_S}/{n}.webp",
                "sha256": sha(f"u/{n}"),
            }
            for n in (1, 2)
        ]

    def test_the_move_plan_writes_it_and_its_run_puts_the_pictures_first(
        self, tmp_path: Path
    ) -> None:
        directory = self.written(tmp_path)
        assert [f["row_id"] for f in self.load(directory)] == ["1", "2"]
        md = (directory / "PLAN.md").read_text(encoding="utf-8")
        copy = md.index(f"dup_merge.py files --wave {WAVE} --copy")
        served = md.index(f"dup_merge.py files --wave {WAVE} --served")
        assert copy < md.index(f"--lane dup-merge-move-{WAVE} --apply") < served

    def test_the_retire_plan_has_no_pictures(self, tmp_path: Path) -> None:
        plan, held = retired()
        directory = D.write_plan(plan, held, after_the_move(), [pair()], tmp_path)
        assert not (directory / D.FILES_FILE).exists()
        assert "dup_merge.py files" not in (directory / "PLAN.md").read_text(encoding="utf-8")

    def test_a_plan_written_without_its_file_list_is_refused(self, tmp_path: Path) -> None:
        directory = self.written(tmp_path)
        (directory / D.FILES_FILE).unlink()
        with pytest.raises(P.PlanError, match="written without its file list"):
            self.load(directory)

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda f: f[:1], "is not the file list of"),
            (lambda f: [*f, {**f[1], "row_id": "99"}], "is not the file list of"),
            (lambda f: [{**f[0], "dest": f"{FOLDER_L}/1.webp"}, f[1]], "is not the file list of"),
            (lambda f: [{**f[0], "dest": f"{FOLDER_S}/x.webp"}, f[1]], "is not one file's"),
            (lambda f: [{**f[0], "sha256": "not a digest"}, f[1]], "is not one file's"),
        ],
    )
    def test_a_file_list_that_is_not_the_plan_s_is_refused(
        self, tmp_path: Path, change, message: str
    ) -> None:
        directory = self.written(tmp_path)
        files = change(self.load(directory))
        (directory / D.FILES_FILE).write_text(
            "".join(json.dumps(f) + "\n" for f in files), encoding="utf-8"
        )
        with pytest.raises(P.PlanError, match=message):
            self.load(directory)


class TestTheListing:
    def raw(self, *records: str) -> bytes:
        return b"".join(r.encode() + b"\0" for r in records)

    def test_a_folder_name_that_is_not_eight_hex_is_never_sent(self) -> None:
        for bad in ("..", "ae2ca7b", "AE2CA7B1", "ae2ca7b1; rm -rf x", "ae2ca7b1\n"):
            with pytest.raises(P.PlanError, match="is not an image folder"):
                D.list_script([FOLDER_L, bad])

    def test_the_listing_script_writes_nothing(self) -> None:
        script = D.list_script([FOLDER_L, FOLDER_S])
        for word in ("rm ", "mv ", "cp ", "chmod", "mkdir", ">", "tee", "touch"):
            assert word not in script, word
        assert f"for d in {FOLDER_L} {FOLDER_S}; do" in script

    def test_a_record_is_a_sha256_a_folder_and_a_filename_as_it_is(self) -> None:
        raw = self.raw(f"{sha('a')} *{FOLDER_L}/a * b/c.webp", f"{D.LISTED} 2")
        assert D.parse_listing(raw, [FOLDER_L, FOLDER_S]) == {
            FOLDER_L: {"a * b/c.webp": sha("a")},
            FOLDER_S: {},
        }

    @pytest.mark.parametrize(
        ("records", "message"),
        [
            ((f"{sha('a')} *{FOLDER_L}/a.webp",), "did not finish"),
            ((f"{sha('a')} *{FOLDER_L}/a.webp", f"{D.LISTED} 2"), "did not finish"),
            ((), "did not finish"),
            ((f"{sha('a')} *{FOLDER_S}/a.webp", f"{D.LISTED} 1"), "cannot read"),
            ((f"{sha('a')[:63]} *{FOLDER_L}/a.webp", f"{D.LISTED} 1"), "cannot read"),
            ((f"{sha('a')} *{FOLDER_L}/", f"{D.LISTED} 1"), "cannot read"),
            ((f"{sha('a')}  {FOLDER_L}/a.webp", f"{D.LISTED} 1"), "cannot read"),
        ],
    )
    def test_a_listing_that_cannot_be_read_whole_is_refused(
        self, records: tuple[str, ...], message: str
    ) -> None:
        with pytest.raises(P.PlanError, match=message):
            D.parse_listing(self.raw(*records), [FOLDER_L])

    def test_a_listing_cut_inside_its_last_record_is_refused(self) -> None:
        # the closing record without its terminator: read loosely, the file before it would be
        # taken for the end of the listing and dropped
        cut = self.raw(f"{sha('a')} *{FOLDER_L}/a.webp", f"{D.LISTED} 1")[:-1]
        with pytest.raises(P.PlanError, match="did not finish"):
            D.parse_listing(cut, [FOLDER_L])

    def test_the_wave_s_folders_are_those_of_every_loser_and_survivor(self) -> None:
        assert D.wave_folders([pair(), pair(LOSER2, SURVIVOR)]) == sorted(
            {FOLDER_L, FOLDER_S, D.site_id_short(LOSER2)}
        )


class TestTheStateOfAPicture:
    LISTING = {FOLDER_L: {"a.webp": sha("a.webp")}, FOLDER_S: {}}

    def state(self, there: dict[str, str], listing: dict[str, dict[str, str]] | None = None) -> str:
        base = listing or self.LISTING
        return D.file_state(entry("a.webp"), {**base, FOLDER_S: there})

    def test_it_is_in_place_only_with_the_planned_bytes(self) -> None:
        assert self.state({"a.webp": sha("a.webp")}) == D.IN_PLACE
        assert self.state({}) == D.TO_COPY
        assert self.state({"a.webp": sha("another picture")}) == D.DEST_TAKEN

    def test_a_source_that_changed_or_is_gone_is_said_first(self) -> None:
        changed = {FOLDER_L: {"a.webp": sha("edited")}, FOLDER_S: {}}
        assert self.state({"a.webp": sha("a.webp")}, changed) == D.SOURCE_CHANGED
        assert self.state({}, {FOLDER_L: {}, FOLDER_S: {}}) == D.SOURCE_CHANGED

    def test_a_plan_that_moves_no_image_asks_the_vps_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(D, "run_on_vps", lambda script: pytest.fail("asked the VPS"))
        assert D.file_states([]) == []
        assert D.copy_files([]) == {"files": 0, "copied": 0, "already_there": 0}


class TestTheTransport:
    def test_a_script_goes_to_bash_on_the_vps_as_utf8_bytes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def run(argv: list[str], **kwargs: Any) -> Any:
            seen.update(argv=argv, **kwargs)
            return subprocess.CompletedProcess(argv, 0, b"out\0", b"")

        monkeypatch.setattr(D.subprocess, "run", run)
        assert D.run_on_vps("ls 'Hattuşa Örenyeri'\n") == b"out\0"
        assert seen["argv"][0] == "ssh" and seen["argv"][-3:] == ["ancientnerds", "bash", "-s"]
        assert seen["input"] == "ls 'Hattuşa Örenyeri'\n".encode()

    def test_a_failed_script_is_a_refusal_that_says_why(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        failed = subprocess.CompletedProcess([], 7, b"", b"cp: cannot stat 'x'\n")
        monkeypatch.setattr(D.subprocess, "run", lambda argv, **kwargs: failed)
        with pytest.raises(P.PlanError, match="exited 7: cp: cannot stat 'x'"):
            D.run_on_vps("c x y\n")

    def test_a_vps_that_does_not_answer_is_a_refusal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def run(argv: list[str], **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        monkeypatch.setattr(D.subprocess, "run", run)
        with pytest.raises(P.PlanError, match="did not answer within 5s"):
            D.run_on_vps("true\n", timeout=5)


class TestTheFoldersOnDisk:
    """The lane's own scripts, run by the local bash in a temp tree: what the VPS would do."""

    NAMES = (
        "20140415 dodoni016.webp",
        "Greek_Marble_Muse_Terpsichore,_Late_4th_to_Mid_2nd_BC_(10451853483).webp",
        "it's 100% $HOME `x` & co.webp",
        "Hattuşa Örenyeri — Δωδώνη.webp",
    )

    @needs_the_listing_tools
    def test_a_listing_is_every_file_of_each_folder_under_its_own_name(self, tree: Path) -> None:
        for name in self.NAMES:
            put(tree, FOLDER_L, name)
        put(tree, FOLDER_S, "hero.webp", "h")
        (tree / FOLDER_L / "deeper").mkdir()
        (tree / FOLDER_L / "deeper" / "x.webp").write_bytes(b"x")
        assert D.read_folders([FOLDER_L, FOLDER_S, "00000000"]) == {
            FOLDER_L: {name: sha(name) for name in self.NAMES},
            FOLDER_S: {"hero.webp": sha("h")},
            "00000000": {},
        }

    @needs_the_copy_tools
    def test_the_copy_puts_each_picture_in_place_and_leaves_the_loser_s(self, tree: Path) -> None:
        files = [entry(name, row=n) for n, name in enumerate(self.NAMES)]
        for name in self.NAMES:
            put(tree, FOLDER_L, name)
        assert D.copy_files(files) == {"files": 4, "copied": 4, "already_there": 0}
        for name in self.NAMES:
            assert (tree / FOLDER_S / name).read_bytes() == name.encode()
            assert (tree / FOLDER_L / name).read_bytes() == name.encode()  # copied, never moved
        # nothing but the pictures: no partial copy is left behind
        assert sorted(p.name for p in (tree / FOLDER_S).iterdir()) == sorted(self.NAMES)
        assert [state for _, state in D.file_states(files)] == [D.IN_PLACE] * 4
        if os.name != "nt":  # the modes of the tree: the API container writes there as another user
            assert (tree / FOLDER_S).stat().st_mode & 0o777 == 0o777
            assert (tree / FOLDER_S / self.NAMES[0]).stat().st_mode & 0o777 == 0o666
        # a second run finds them and copies nothing
        assert D.copy_files(files) == {"files": 4, "copied": 0, "already_there": 4}

    @needs_the_copy_tools
    def test_a_destination_that_holds_another_file_is_never_overwritten(self, tree: Path) -> None:
        put(tree, FOLDER_L, "a.webp")
        put(tree, FOLDER_L, "b.webp")
        other = put(tree, FOLDER_S, "b.webp", "another picture")
        with pytest.raises(P.PlanError, match="nothing was copied") as refused:
            D.copy_files([entry("a.webp", row=1), entry("b.webp", row=2)])
        assert f"{D.DEST_TAKEN}: {FOLDER_L}/b.webp -> {FOLDER_S}/b.webp (row 2)" in str(
            refused.value
        )
        assert other.read_bytes() == b"another picture"
        assert not (tree / FOLDER_S / "a.webp").exists()  # nothing: not even the free one

    @needs_the_copy_tools
    def test_a_source_that_is_not_the_planned_file_any_more_is_refused(self, tree: Path) -> None:
        put(tree, FOLDER_L, "a.webp", "edited since the plan")
        with pytest.raises(P.PlanError, match="nothing was copied") as refused:
            D.copy_files([entry("a.webp"), entry("gone.webp", row=2)])
        assert str(refused.value).count(D.SOURCE_CHANGED) == 2
        assert not (tree / FOLDER_S).exists()

    @needs_the_copy_tools
    def test_the_copy_script_itself_replaces_nothing(self, tree: Path) -> None:
        """The check before the copy is Python's; the script holds on its own."""
        put(tree, FOLDER_L, "a.webp")
        other = put(tree, FOLDER_S, "a.webp", "another picture")
        D.run_on_vps(D.copy_script([entry("a.webp")]))
        assert other.read_bytes() == b"another picture"
        assert [p.name for p in (tree / FOLDER_S).iterdir()] == ["a.webp"]

    @needs_the_copy_tools
    def test_a_copy_that_cannot_be_made_stops_the_script(self, tree: Path) -> None:
        put(tree, FOLDER_L, "b.webp")
        with pytest.raises(P.PlanError, match="exited 7"):
            D.run_on_vps(D.copy_script([entry("b.webp"), entry("a-gone.webp")]))
        # the copies go in the order of their paths, and the script stopped at the first
        # failure: the picture after it was not copied, and no partial copy is left
        assert list((tree / FOLDER_S).iterdir()) == []

    @needs_the_copy_tools
    def test_a_copy_that_is_not_the_planned_bytes_afterwards_is_refused(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        put(tree, FOLDER_L, "a.webp")
        real = D.copy_script
        # a copy that lands as other bytes (here: the script copies a neighbour instead)
        put(tree, FOLDER_L, "b.webp", "other bytes")
        monkeypatch.setattr(
            D, "copy_script", lambda files: real([{**files[0], "source": f"{FOLDER_L}/b.webp"}])
        )
        with pytest.raises(P.PlanError, match="after the copy these pictures are not in place"):
            D.copy_files([entry("a.webp")])


class TestServed:
    def test_each_moved_picture_is_asked_for_under_its_survivor_s_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[str] = []

        def status(url: str) -> int:
            asked.append(url)
            return 404 if "b%20c" in url else 301 if url.endswith("/moved.webp") else 200

        monkeypatch.setattr(D, "served_status", status)
        files = [
            entry("a.webp"),
            entry("b c.webp", row=2),
            entry("Ğ%.webp", row=3),
            entry("moved.webp", row=4),
        ]
        # only a 200 is a served picture: a redirect is named like a 404
        assert D.not_served(files) == [
            f"404 {D.SERVED_ROOT}/{FOLDER_S}/b%20c.webp",
            f"301 {D.SERVED_ROOT}/{FOLDER_S}/moved.webp",
        ]
        assert f"{D.SERVED_ROOT}/{FOLDER_S}/%C4%9E%25.webp" in asked and len(asked) == 4
        assert D.SERVED_ROOT == "https://ancientnerds.com/data/images/wiki"

    def test_an_http_error_is_an_answer_and_no_answer_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import urllib.error

        class Answer:
            status = 200

            def __enter__(self) -> Answer:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        def answers(outcome: Any) -> Any:
            def urlopen(request: Any, timeout: int) -> Any:
                assert request.get_method() == "HEAD" and timeout == 60
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            return urlopen

        url = f"{D.SERVED_ROOT}/{FOLDER_S}/a.webp"
        monkeypatch.setattr(D.urllib.request, "urlopen", answers(Answer()))
        assert D.served_status(url) == 200
        gone = urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        monkeypatch.setattr(D.urllib.request, "urlopen", answers(gone))
        assert D.served_status(url) == 404
        monkeypatch.setattr(D.urllib.request, "urlopen", answers(urllib.error.URLError("down")))
        with pytest.raises(urllib.error.URLError):
            D.served_status(url)


class TestTheFilesCommand:
    def wave(self, tmp_path: Path) -> Path:
        D.write_wave(WAVE, [pair()], tmp_path)
        plan, held, _ = moved()
        return D.write_plan(plan, held, a_read(), [pair()], tmp_path)

    def run(self, tmp_path: Path, step: str) -> int:
        return D.main(["--out", str(tmp_path), "files", "--wave", WAVE, step])

    def test_verify_names_what_is_not_in_place_and_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.wave(tmp_path)
        listing = {
            FOLDER_L: {"1.webp": sha("u/1"), "2.webp": sha("u/2")},
            FOLDER_S: {"1.webp": sha("u/1")},
        }
        monkeypatch.setattr(D, "read_folders", lambda folders: listing)
        assert self.run(tmp_path, "--verify") == 1
        answer = json.loads(capsys.readouterr().out)
        assert answer["files"] == 2 and answer["not"] == [
            f"{D.TO_COPY}: {FOLDER_L}/2.webp -> {FOLDER_S}/2.webp (row 2)"
        ]
        listing[FOLDER_S]["2.webp"] = sha("u/2")
        assert self.run(tmp_path, "--verify") == 0
        assert json.loads(capsys.readouterr().out)["not"] == []

    def test_served_exits_1_for_a_picture_the_site_does_not_answer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.wave(tmp_path)
        monkeypatch.setattr(D, "served_status", lambda url: 404 if url.endswith("/2.webp") else 200)
        assert self.run(tmp_path, "--served") == 1
        assert json.loads(capsys.readouterr().out)["not"] == [
            f"404 {D.SERVED_ROOT}/{FOLDER_S}/2.webp"
        ]
        monkeypatch.setattr(D, "served_status", lambda url: 200)
        assert self.run(tmp_path, "--served") == 0

    def test_a_site_that_cannot_be_reached_is_a_refusal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import urllib.error

        def down(url: str) -> int:
            raise urllib.error.URLError("no route")

        self.wave(tmp_path)
        monkeypatch.setattr(D, "served_status", down)
        assert self.run(tmp_path, "--served") == 1
        assert "REFUSED" in capsys.readouterr().err

    def test_a_step_is_required_and_a_plan_without_its_list_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        directory = self.wave(tmp_path)
        with pytest.raises(SystemExit):
            D.main(["--out", str(tmp_path), "files", "--wave", WAVE])
        (directory / D.FILES_FILE).unlink()
        assert self.run(tmp_path, "--verify") == 1
        assert "written without its file list" in capsys.readouterr().err

    @needs_the_copy_tools
    def test_copy_then_verify_end_to_end(
        self, tmp_path: Path, tree: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.wave(tmp_path)
        for n in (1, 2, 3):
            put(tree, FOLDER_L, f"{n}.webp", f"u/{n}" if n < 3 else "u/shared")
        assert self.run(tmp_path, "--verify") == 1
        capsys.readouterr()
        assert self.run(tmp_path, "--copy") == 0
        assert json.loads(capsys.readouterr().out) == {
            "lane": f"dup-merge-move-{WAVE}",
            "files": 2,
            "copied": 2,
            "already_there": 0,
        }
        assert self.run(tmp_path, "--verify") == 0
        # the row that stays for its URL is not copied
        assert sorted(p.name for p in (tree / FOLDER_S).iterdir()) == ["1.webp", "2.webp"]


class TestTheApplyAsksForThePictures:
    """`apply.py --apply` of a move: the database cannot see a folder, so the write goes out only
    when every moved picture is in its survivor's folder (playbook rule: never apply before)."""

    class Reached(Exception):
        """The apply went on to production."""

    def emitted(self, tmp_path: Path, *, retire: bool = False):
        if retire:
            plan, held = retired()
            read = after_the_move()
        else:
            plan, held, _ = moved()
            read = a_read()
        directory = D.write_plan(plan, held, read, [pair()], tmp_path)
        records = A.load_records(directory / "PLAN.jsonl")
        A.emit(records, directory, plan.lane, plan_path=directory / "PLAN.jsonl")
        return records, directory, plan.lane

    def production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def reached(*args: Any, **kwargs: Any) -> Any:
            raise self.Reached

        monkeypatch.setattr(A, "journal_count", lambda stamp: 0)
        monkeypatch.setattr(A, "run_psql", reached)

    def test_a_move_whose_pictures_are_not_in_place_is_refused_before_the_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, directory, lane = self.emitted(tmp_path)
        self.production(monkeypatch)
        listing = {
            FOLDER_L: {"1.webp": sha("u/1"), "2.webp": sha("u/2")},
            FOLDER_S: {"1.webp": sha("u/1")},
        }
        monkeypatch.setattr(D, "read_folders", lambda folders: listing)
        with pytest.raises(P.PlanError, match="1 picture\\(s\\) .* not in place") as refused:
            A.cmd_apply(records, directory, lane, plan_path=directory / "PLAN.jsonl")
        assert f"{FOLDER_L}/2.webp -> {FOLDER_S}/2.webp (row 2)" in str(refused.value)
        assert "files --copy" in str(refused.value)

    def test_a_move_whose_pictures_are_in_place_goes_on(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, directory, lane = self.emitted(tmp_path)
        self.production(monkeypatch)
        both = {"1.webp": sha("u/1"), "2.webp": sha("u/2")}
        monkeypatch.setattr(D, "read_folders", lambda folders: {FOLDER_L: both, FOLDER_S: both})
        with pytest.raises(self.Reached):
            A.cmd_apply(records, directory, lane, plan_path=directory / "PLAN.jsonl")

    def test_a_move_plan_without_its_file_list_is_not_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, directory, lane = self.emitted(tmp_path)
        self.production(monkeypatch)
        (directory / D.FILES_FILE).unlink()
        with pytest.raises(P.PlanError, match="written without its file list"):
            A.cmd_apply(records, directory, lane, plan_path=directory / "PLAN.jsonl")

    def test_the_retirement_moves_no_picture_and_is_not_asked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, directory, lane = self.emitted(tmp_path, retire=True)
        self.production(monkeypatch)
        monkeypatch.setattr(D, "read_folders", lambda folders: pytest.fail("asked for folders"))
        with pytest.raises(self.Reached):
            A.cmd_apply(records, directory, lane, plan_path=directory / "PLAN.jsonl")


class TestTheCopyDecision:
    """What `files --copy` sends and when it refuses, on listings it is handed (the scripts
    themselves run in `TestTheFoldersOnDisk`)."""

    def folders(self, monkeypatch: pytest.MonkeyPatch, *listings: dict[str, dict[str, str]]):
        """`read_folders` answers the listings in turn; what is sent to the VPS is kept."""
        answers, sent = list(listings), []
        monkeypatch.setattr(D, "read_folders", lambda folders: answers.pop(0))
        monkeypatch.setattr(D, "run_on_vps", lambda script: sent.append(script) or b"")
        return sent

    def test_only_what_is_missing_is_sent_and_everything_is_read_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = {"a.webp": sha("a.webp"), "b.webp": sha("b.webp")}
        sent = self.folders(
            monkeypatch,
            {FOLDER_L: source, FOLDER_S: {"a.webp": sha("a.webp")}},
            {FOLDER_L: source, FOLDER_S: source},
        )
        done = D.copy_files([entry("a.webp", row=1), entry("b.webp", row=2)])
        assert done == {"files": 2, "copied": 1, "already_there": 1}
        assert len(sent) == 1 and f"c {FOLDER_L}/b.webp {FOLDER_S}/b.webp\n" in sent[0]
        assert "a.webp" not in sent[0]

    def test_nothing_is_sent_when_a_folder_is_not_as_the_plan_read_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = {"a.webp": sha("a.webp"), "b.webp": sha("b.webp")}
        taken = {FOLDER_L: source, FOLDER_S: {"b.webp": sha("another picture")}}
        sent = self.folders(monkeypatch, taken)
        with pytest.raises(P.PlanError, match="nothing was copied") as refused:
            D.copy_files([entry("a.webp", row=1), entry("b.webp", row=2)])
        assert sent == [] and D.DEST_TAKEN in str(refused.value)
        assert "a.webp" not in str(refused.value)  # only what is wrong is named

    def test_a_copy_that_did_not_land_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        missing = {FOLDER_L: {"a.webp": sha("a.webp")}, FOLDER_S: {}}
        sent = self.folders(monkeypatch, missing, missing)
        with pytest.raises(P.PlanError, match="after the copy these pictures are not in place"):
            D.copy_files([entry("a.webp")])
        assert len(sent) == 1

    def test_a_filename_travels_quoted_for_the_shell(self) -> None:
        name = "it's $HOME `x`; rm -rf ~ & co.webp"
        script = D.copy_script([entry(name), entry(name, row=2)])
        copies = [line for line in script.splitlines() if line.startswith("c ")]
        # one copy for the two rows of one file; read as a shell reads it, the line is the two
        # paths, and nothing of the name stands outside single quotes
        assert [shlex.split(line) for line in copies] == [
            ["c", f"{FOLDER_L}/{name}", f"{FOLDER_S}/{name}"]
        ]
        assert '"' not in copies[0].replace("'\"'\"'", "")
        # the copy never replaces a file and leaves no partial one
        for word in ('if [ -e "$2" ]; then return 0; fi', "mv -n -- ", 'rm -f -- "$2.d14-part"'):
            assert word in script


class TestARowOwnsItsFilename:
    def test_a_survivor_row_keeps_its_filename_whatever_the_folder_holds(self) -> None:
        """A row of the survivor names `hero.webp` and its file is not in the folder (or is the
        same bytes): the loser's row still stays - moved, it would put its file under that row."""
        images = {
            LOSER: (img(1, LOSER, "u/1", filename="hero.webp"),),
            SURVIVOR: (img(11, SURVIVOR, "u/own", filename="hero.webp"),),
        }
        for there in ({}, {"hero.webp": sha("u/1")}):
            files = {FOLDER_L: {"hero.webp": sha("u/1")}, FOLDER_S: there}
            cells, counts = D.move_cells(a_read(images=images, files=files), pair())
            assert [c for c in cells if c.table == "wiki_images"] == []
            assert counts["images_stay_filename"] == 1


class TestThePlanCommand:
    """`plan-move --write` end to end, with the two reads answered from fixtures."""

    def export(self, read: D.Read, move: L.Lane) -> str:
        lines: list[dict[str, Any]] = [{"kind": "site", "row": row} for row in read.sites.values()]
        for site, ids in read.ext.items():
            lines += [{"kind": "ext", "row": {"id": site, "kind": k, "value": v}} for k, v in ids]
        for kind, rows in (("image", read.images), ("link", read.links), ("name", read.names)):
            lines += [{"kind": kind, "row": row} for group in rows.values() for row in group]
        lines += [
            {"kind": "metres", "row": {"loser": k, "metres": v}} for k, v in read.metres.items()
        ]
        lines.append({"kind": "stamp", "row": {"run_stamp": move.run_stamp, "n": 0}})
        lines.append({"kind": "snapshot", "row": {"exported_at": read.read_at}})
        return "\n".join(json.dumps(line) for line in lines) + "\n"

    def test_plan_move_reads_the_folders_and_writes_the_file_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        D.write_wave(WAVE, [pair()], tmp_path)
        read = a_read()
        move, _ = lanes([pair()])
        asked: list[list[str]] = []

        def write_read(path: Path, *_: Any) -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.export(read, move), encoding="utf-8", newline="\n")
            return path

        def read_folders(folders: list[str]) -> dict[str, dict[str, str]]:
            asked.append(list(folders))
            return {name: dict(read.files.get(name, {})) for name in folders}

        monkeypatch.setattr(D, "write_read", write_read)
        monkeypatch.setattr(D, "read_folders", read_folders)
        assert D.main(["--out", str(tmp_path), "plan-move", "--wave", WAVE, "--write"]) == 0
        printed = json.loads(capsys.readouterr().out)
        assert (printed["images"], printed["images_stay"], printed["images_stay_filename"]) == (
            2,
            1,
            0,
        )
        assert asked == [sorted([FOLDER_L, FOLDER_S])]
        directory = tmp_path / move.out_dir_name
        assert json.loads((directory / D.DISK_FILE).read_text(encoding="utf-8")) == read.files
        files = D.load_files(directory / D.FILES_FILE, directory / "PLAN.jsonl")
        assert [(f["row_id"], f["sha256"]) for f in files] == [("1", sha("u/1")), ("2", sha("u/2"))]
