"""D17 (2026-10-08): the whole picture research on three invented sites, from the population to the
targets, with every Claude answer written by the test in the stamp of the role's registered model.

Offline: Commons is `test_candidate_routes.FakeCommons`, the picture download a stub client.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from candidate_search import judge as CJ  # noqa: E402
from candidate_search import search as CS  # noqa: E402
from image_roles import depicts as DP  # noqa: E402
from image_roles import flow as FL  # noqa: E402
from image_roles import hero_recheck as HR  # noqa: E402
from image_roles import identity as ID  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402
from served_image import state as ST  # noqa: E402

from tests.remediation.test_candidate_routes import FLOOR, FakeCommons, Store, item  # noqa: E402

A, B, C = (
    "aaaaaaaa-0000-4000-8000-000000000001",
    "bbbbbbbb-0000-4000-8000-000000000002",
    "cccccccc-0000-4000-8000-000000000003",
)
NOW = "2026-10-09T03:00:00+00:00"


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1600, 900), (90, 90, 90)).save(out, format="JPEG")
    return out.getvalue()


def read_line(site_id: str, name: str, **over: Any) -> dict[str, Any]:
    base = {
        "site_id": site_id, "name": name, "country": "Italy", "site_type": "Tomb", "lat": 40.0,
        "lon": 9.0, "description": f"{name} is a tomb.", "qids": [], "enwiki_titles": [],
        "coord_kind": None, "coord_marker_current": False, "rows": [],
    }  # fmt: skip
    return base | over


class Response:
    status_code = 200

    def __init__(self, content: bytes) -> None:
        self.content = content


class Client:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> Response:
        self.urls.append(url)
        return Response(jpeg())


def answer(handoff: Path, spec: SG.Spec, texts: dict[str, str]) -> None:
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff, batch_id=line["batch_id"], stage=spec.name, label=line["label"],
            text=texts[line["label"]], answered_by=f"{spec.role}:{line['batch_id']}",
            model=OH.ANSWER_MODELS[RO.role(spec.role).model], now=lambda: NOW,
        )  # fmt: skip


def search_run(tmp_path: Path) -> Path:
    run = tmp_path / "candidates"
    FL.write_population(
        run,
        [
            read_line(A, "Tomb Alpha", qids=["Q9"], enwiki_titles=["Tomb Alpha"]),
            read_line(B, "Tomb Beta"),
            read_line(C, "Tomb Gamma"),
        ],
    )
    commons = FakeCommons()
    commons.categories["Tomb Alpha (site)"] = ["A-front.jpg", "A-back.jpg"]
    commons.articles["Tomb Alpha"] = {"missing": False, "lead": "A-front.jpg", "files": []}
    commons.hits["Tomb Beta filetype:bitmap"] = ["B-map.jpg"]
    commons.hits["Tomb Gamma filetype:bitmap"] = ["C-good.jpg", "C-better.jpg"]
    store = Store({"Q9": item(p373=["Tomb Alpha (site)"])})
    FL.search(run, commons, entities=store, floor=FLOOR)
    return run


def kinds(run: Path, plan: dict[str, tuple[str, bool]]) -> str:
    """A prefilter answer for each question: `{file: (kind, usable)}`."""
    question = next(iter(SG.load_questions(run, PF.SPEC).values()))
    items = {
        item["label"]: {"kind": plan[item["file"]][0], "usable": plan[item["file"]][1]}
        for item in question.meta["items"]
    }
    return json.dumps({"items": items})


def judged(
    run: Path, spec: SG.Spec, verdicts: dict[tuple[str, str], tuple[str, int | None]]
) -> dict[str, str]:
    """A depicts answer for each site-question: `{(site, file): (verdict, quality)}`."""
    out = {}
    for (_, label), question in SG.load_questions(run, spec).items():
        candidates = {}
        for entry in question.meta["items"]:
            verdict, quality = verdicts[(label, entry["file"])]
            candidates[entry["label"]] = {
                "verdict": verdict,
                "quality": quality,
                "note": f"{verdict} {entry['file']}",
            }
        out[label] = json.dumps({"candidates": candidates})
    return out


def recheck_answers(run: Path, spec: SG.Spec, verdicts: dict[str, str]) -> dict[str, str]:
    out = {}
    for _, label in SG.load_questions(run, spec):
        verdict = verdicts[label]
        shows = "the Treasury at Petra in Jordan" if verdict == "other_site" else "the tomb"
        basis = (
            "commons.wikimedia.org/wiki/File:X.jpg"
            if verdict == "other_site"
            else "the chamber is visible"
        )
        out[label] = json.dumps({"verdict": verdict, "shows": shows, "basis": basis})
    return out


class TestTheChain:
    def test_the_population_is_written_with_its_counts(self, tmp_path: Path) -> None:
        run = search_run(tmp_path)
        population = [json.loads(x) for x in (run / "POPULATION.jsonl").read_text().splitlines()]
        assert [p["site_id"] for p in population] == [A, B, C]
        assert population[0]["qid"] == "Q9" and population[1]["qid"] is None

    def test_the_search_ran_every_route_the_sites_have(self, tmp_path: Path) -> None:
        run = search_run(tmp_path)
        rows = {
            json.loads(x)["site_id"]: json.loads(x)
            for x in (run / CS.CANDIDATES).read_text().splitlines()
        }
        # the lead image is also in the category: the first route that names a file keeps it
        assert {c["route"] for c in rows[A]["candidates"]} == {"p373"}
        assert [c["file"] for c in rows[B]["candidates"]] == ["B-map.jpg"]

    def test_the_pictures_are_fetched_and_recorded_with_their_paths(self, tmp_path: Path) -> None:
        run = search_run(tmp_path)
        client = Client()
        summary = FL.pictures(run, client)
        assert summary == {"sites": 3, "pictures": 5, "refused": 0}
        sites = [json.loads(x) for x in (run / FL.PICTURES).read_text().splitlines()]
        assert all(Path(c["path"]).is_file() for s in sites for c in s["candidates"])
        with pytest.raises(ST.StateError, match="written once"):
            FL.pictures(run, client)

    def test_from_the_population_to_the_targets(self, tmp_path: Path) -> None:
        run = search_run(tmp_path)
        FL.pictures(run, Client())
        # ---- the prefilter (Haiku): Beta's only picture is a map
        pre_handoff = tmp_path / "h-pre"
        assert FL.prefilter_export(run, pre_handoff, read=lambda c: jpeg())["questions"] == 1
        plan = dict.fromkeys(
            ("A-front.jpg", "A-back.jpg", "C-good.jpg", "C-better.jpg"), ("site_photo", True)
        )
        plan["B-map.jpg"] = ("map_or_document", True)
        answer(pre_handoff, PF.SPEC, {"pre-0001": kinds(run, plan)})
        SG.import_answers(run, pre_handoff, PF.SPEC)
        # ---- the depicts role (Sonnet): only the survivors are asked, Beta is not
        dep_handoff = tmp_path / "h-dep"
        summary = FL.depicts_export(run, dep_handoff, cache=None, read=lambda c: jpeg())
        assert summary["sites"] == 2 and summary["left_out"] == 0
        assert {label for _, label in SG.load_questions(run, DP.SPEC)} == {A, C}
        verdicts = {
            (A, "A-front.jpg"): ("depicts", 5), (A, "A-back.jpg"): ("region_or_type", None),
            (C, "C-good.jpg"): ("depicts", 3), (C, "C-better.jpg"): ("depicts", 4),
        }  # fmt: skip
        answer(dep_handoff, DP.SPEC, judged(run, DP.SPEC, verdicts))
        done = FL.depicts_import(run, dep_handoff)
        assert (
            done["verdicts"] == {"depicts": 3, "region_or_type": 1}
            and done["sites_with_depicts"] == 2
        )
        rows = [json.loads(x) for x in (run / CJ.VERDICTS).read_text().splitlines()]
        assert {r["file"]: r["width"] for r in rows}["A-front.jpg"] == 3000
        # ---- the hero re-check (Opus), round 1: the best pick of each site
        one = HR.spec_for_round(1)
        h1 = tmp_path / "h-rck-1"
        got = FL.recheck_export(run, h1, read=lambda p: jpeg())
        assert (got["round"], got["picks"]) == (1, 2)
        assert {label for _, label in SG.load_questions(run, one)} == {A, C}
        picked = {q.meta["site_id"]: q.meta["file"] for q in SG.load_questions(run, one).values()}
        assert picked == {A: "A-front.jpg", C: "C-better.jpg"}
        answer(h1, one, recheck_answers(run, one, {A: "depicts", C: "other_site"}))
        SG.import_answers(run, h1, one)
        # ---- round 2: only Gamma waits, with its next candidate
        two = HR.spec_for_round(2)
        h2 = tmp_path / "h-rck-2"
        got = FL.recheck_export(run, h2, read=lambda p: jpeg())
        assert (got["round"], got["picks"]) == (2, 1)
        assert [q.meta["file"] for q in SG.load_questions(run, two).values()] == ["C-good.jpg"]
        # targets are refused while round 2 is unanswered
        with pytest.raises(SG.StageError, match="wait for a re-check round"):
            FL.write_targets(run)
        answer(h2, two, recheck_answers(run, two, {C: "depicts"}))
        SG.import_answers(run, h2, two)
        with pytest.raises(FL.FlowError, match="no site waits"):
            FL.recheck_export(run, tmp_path / "h-rck-3", read=lambda p: jpeg())
        # ---- the targets
        summary = FL.write_targets(run)
        assert summary["sites_to_fetch"] == 2
        targets = {
            t["site_id"]: t for t in map(json.loads, (run / CJ.TARGETS).read_text().splitlines())
        }
        assert targets[A]["commons_file"] == "A-front.jpg" and targets[A]["quality"] == 5
        assert targets[C]["commons_file"] == "C-good.jpg"  # the better one was an other_site
        # ---- the pictures go once the targets stand, their hashes stay
        gone = FL.prune_pictures(run)
        assert gone["pictures"] == 5 and not (run / "pictures").exists()
        sums = [json.loads(x) for x in (run / FL.PICTURES_SHA).read_text().splitlines()]
        assert len(sums) == 5 and all(len(s["sha256"]) == 64 for s in sums)

    def test_pictures_are_not_pruned_while_the_targets_are_unwritten(self, tmp_path: Path) -> None:
        run = search_run(tmp_path)
        FL.pictures(run, Client())
        with pytest.raises(FL.FlowError, match="targets are not written yet"):
            FL.prune_pictures(run)
        assert (run / "pictures").is_dir()

    def test_the_depicts_role_needs_the_prefilter_first(self, tmp_path: Path) -> None:
        run = search_run(tmp_path)
        FL.pictures(run, Client())
        with pytest.raises(SG.StageError, match="import the stage first"):
            FL.depicts_export(run, tmp_path / "h", cache=None, read=lambda c: jpeg())

    def test_a_fetched_site_the_population_does_not_hold_stops_the_depicts_export(
        self, tmp_path: Path
    ) -> None:
        run = search_run(tmp_path)
        FL.pictures(run, Client())
        pre_handoff = tmp_path / "h-pre"
        FL.prefilter_export(run, pre_handoff, read=lambda c: jpeg())
        plan = dict.fromkeys(
            ("A-front.jpg", "A-back.jpg", "C-good.jpg", "C-better.jpg", "B-map.jpg"),
            ("site_photo", True),
        )
        answer(pre_handoff, PF.SPEC, {"pre-0001": kinds(run, plan)})
        SG.import_answers(run, pre_handoff, PF.SPEC)
        kept = [x for x in (run / "POPULATION.jsonl").read_text().splitlines() if A not in x]
        (run / "POPULATION.jsonl").write_text("\n".join(kept) + "\n", encoding="utf-8")
        with pytest.raises(FL.FlowError, match="no site record in the population"):
            FL.depicts_export(run, tmp_path / "h-dep", cache=None, read=lambda c: jpeg())

    def test_a_run_step_without_its_input_names_the_step_before(self, tmp_path: Path) -> None:
        with pytest.raises(FL.FlowError, match="run the step before it"):
            FL.pictures(tmp_path, Client())


class TestThePicksOfTheRecheck:
    def test_a_pick_carries_the_site_its_picture_and_its_cached_wikipedia_page(
        self, tmp_path: Path
    ) -> None:
        run = search_run(tmp_path)
        FL.pictures(run, Client())

        class Cache:
            def file_of(self, site_id: str) -> Path | None:
                return Path(f"C:/cache/{site_id}.json") if site_id == A else None

        rows = [
            {
                "site_id": A,
                "file": "A-front.jpg",
                "note": "the tomb",
                "answered_by": "image_depicts:dep-0001",
            },
            {
                "site_id": C,
                "file": "C-good.jpg",
                "note": "the wall",
                "answered_by": "image_depicts:dep-0001",
            },
        ]
        picks = FL._picks_for(run, rows, Cache())
        assert [p["site_id"] for p in picks] == [A, C]
        assert picks[0]["wikipedia_cache_file"] == "C:/cache/" + A + ".json"
        assert picks[1]["wikipedia_cache_file"] is None
        assert Path(picks[0]["path"]).is_file() and picks[0]["name"] == "Tomb Alpha"

    def test_a_pick_without_a_site_or_a_picture_is_refused(self, tmp_path: Path) -> None:
        run = search_run(tmp_path)
        FL.pictures(run, Client())
        with pytest.raises(FL.FlowError, match="no site record or no picture"):
            FL._picks_for(
                run, [{"site_id": A, "file": "Nope.jpg", "note": "n", "answered_by": "x"}], None
            )


class TestTheIdentityStep:
    def _run(self, tmp_path: Path) -> Path:
        run = tmp_path / "c"
        FL.write_population(
            run,
            [
                read_line(A, "Pukara de Quitor", qids=["Q1"], enwiki_titles=["Pukara de Quitor"]),
                read_line(B, "Nameless"),
                read_line(C, "Fine Site", qids=["Q2"], enwiki_titles=["Fine Site"]),
            ],
        )
        return run

    def _store(self) -> Store:
        def entity(label: str, lat: float) -> dict[str, Any]:
            return {
                "id": "Q", "labels": {"en": {"value": label}}, "aliases": {},
                "claims": {"P625": [{"mainsnak": {"datavalue": {"value": {"latitude": lat, "longitude": 9.0}}}, "rank": "normal"}]},
            }  # fmt: skip

        return Store({"Q1": entity("Pukara de Quitor", 45.0), "Q2": entity("Fine Site", 40.0)})

    def test_verify_asks_the_flagged_sites_and_research_the_nameless(self, tmp_path: Path) -> None:
        run = self._run(tmp_path)
        verify = FL.identity_export(
            run, tmp_path / "h-v", "verify", entities=self._store(), cache=None
        )
        assert verify["sites"] == 1 and verify["role"] == "web_verifier"
        research = FL.identity_export(
            run, tmp_path / "h-r", "research", entities=self._store(), cache=None
        )
        assert research["sites"] == 1
        assert [
            q.meta["sites"][0]["site_id"] for q in SG.load_questions(run, ID.RESEARCH_SPEC).values()
        ] == [B]

    def test_a_mode_with_no_site_to_ask_is_refused_by_name(self, tmp_path: Path) -> None:
        run = tmp_path / "c"
        FL.write_population(
            run, [read_line(A, "Fine Site", qids=["Q2"], enwiki_titles=["Fine Site"])]
        )
        with pytest.raises(FL.FlowError, match="no site to verify"):
            FL.identity_export(run, tmp_path / "h", "verify", entities=self._store(), cache=None)
        with pytest.raises(FL.FlowError, match="no site to research"):
            FL.identity_export(run, tmp_path / "h2", "research", entities=self._store(), cache=None)

    def test_a_site_a_first_search_found_nothing_for_is_researched_too(
        self, tmp_path: Path
    ) -> None:
        run = self._run(tmp_path)
        got = FL.identity_export(
            run, tmp_path / "h-r", "research", entities=self._store(), cache=None, found_nothing=[C]
        )
        assert got["sites"] == 2

    def test_an_item_nobody_holds_stops_the_verify_export(self, tmp_path: Path) -> None:
        run = self._run(tmp_path)
        with pytest.raises(FL.FlowError, match="in neither the harvest nor its delta"):
            FL.identity_export(run, tmp_path / "h", "verify", entities=Store({}), cache=None)

    def test_the_answers_are_merged_into_a_second_population(self, tmp_path: Path) -> None:
        run = self._run(tmp_path)
        FL.identity_export(run, tmp_path / "h-v", "verify", entities=self._store(), cache=None)
        text = json.dumps(
            {
                "sites": {
                    A: {
                        "qid": "Q77", "qid_status": "wrong", "enwiki_title": "Pukara de Quitor",
                        "enwiki_status": "confirmed", "commons_category": "Pukara de Quitor",
                        "local_names": ["Pukara"], "evidence": ["https://www.wikidata.org/wiki/Q77"],
                        "note": "the item is the town",
                    }
                }
            }
        )  # fmt: skip
        answer(tmp_path / "h-v", ID.VERIFY_SPEC, {"idv-0001": text})
        SG.import_answers(run, tmp_path / "h-v", ID.VERIFY_SPEC)
        got = FL.identity_apply(run, SG.read_results(run, ID.VERIFY_SPEC))
        assert got["answered"] == 1 and got["changed"] == 1 and got["with_commons_category"] == 1
        merged = {
            json.loads(x)["site_id"]: json.loads(x)
            for x in (run / FL.POPULATION_2).read_text().splitlines()
        }
        assert merged[A]["qid"] == "Q77" and merged[A]["local_names"] == ["Pukara"]
        assert FL._population(run)[0]["qid"] == "Q77"  # the later steps read the merged population

    def test_an_answer_for_a_site_outside_the_population_is_refused(self, tmp_path: Path) -> None:
        run = self._run(tmp_path)
        row = {"sites": {"zzz": {}}, "answered_by": "x", "model": "m"}
        with pytest.raises(FL.FlowError, match="outside the population"):
            FL.identity_apply(run, [row])

    def test_a_claude_pass_excludes_a_file_a_minimax_pass_never_does(self, tmp_path: Path) -> None:
        verdicts = tmp_path / "VERDICTS.jsonl"
        rows = [
            {
                "site_id": "a",
                "file": "claude-no.jpg",
                "verdict": "other_site",
                "model": OH.SONNET_MODEL,
            },
            {
                "site_id": "a",
                "file": "minimax-no.jpg",
                "verdict": "other_site",
                "model": OH.MINIMAX_MODEL,
            },
            {
                "site_id": "a",
                "file": "claude-yes.jpg",
                "verdict": "depicts",
                "model": OH.SONNET_MODEL,
            },
        ]
        verdicts.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        assert FL.judged_not_depicts([verdicts]) == {"a": ["claude-no.jpg"]}


class TestThePoolStep:
    def test_the_old_pictures_are_the_input_of_the_same_steps(self, tmp_path: Path) -> None:
        from tests.remediation.test_candidate_routes import _pool_run

        old = _pool_run(tmp_path)
        run = tmp_path / "pool"
        FL.write_population(run, [read_line("a", "Site a"), read_line("b", "Site b")])
        got = FL.pool(run, old)
        assert got == {"sites": 1, "pictures": 1, "pictures_gone": 2}
        sites = [json.loads(x) for x in (run / FL.PICTURES).read_text().splitlines()]
        assert [s["site_id"] for s in sites] == ["a"]
        picks = FL.pool_picks(run, old)
        assert [p["file"] for p in picks] == ["Here.jpg"]
