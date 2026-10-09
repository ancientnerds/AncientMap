"""D15 (2026-10-08): the live heroes a Claude check called `other_site`, checked again and swapped.

DB-less and offline, on the fixtures of `test_served_image.py`: the derivation of the population
from the 2026-09-30 records, the recheck's context, the richer prompt and its stricter answer shape,
the `--sites` restriction of both stages, the role of the answering agents, and the plan - a
confirmed `other_site` moves the hero or clears the site, a `region_or_type` verdict keeps the
owner's picture.
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
import roles as RO  # noqa: E402
from served_image import plan as PL  # noqa: E402
from served_image import precheck as PC  # noqa: E402
from served_image import recheck as RC  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402

from tests.remediation import test_served_image as TS  # noqa: E402

THASOS, HABU, BARE, NOTHING = TS.THASOS, TS.HABU, TS.BARE, TS.NOTHING
SITES = [THASOS, HABU, BARE]


def _check_row(site_id: str, image_id: int, verdict: str, **extra: Any) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "verdict": verdict,
        "shows": "the island",
        "basis": "b",
        "answered_by": "check-001",
        "model": OH.SONNET_MODEL,
        "served": {"image_id": image_id, "file": "F.jpg"},
        **extra,
    }


def _replace_row(site_id: str, shown: list[tuple[str, int, str]]) -> dict[str, Any]:
    """`shown` is `(label, image id, verdict)` of gallery candidates."""
    return {
        "site_id": site_id,
        "candidates": {label: verdict for label, _, verdict in shown},
        "candidates_shown": [
            {"label": label, "kind": "gallery", "image_id": image_id, "file": f"G{image_id}.jpg"}
            for label, image_id, _ in shown
        ],
        "basis": "rb",
        "answered_by": "replace-001",
        "model": OH.SONNET_MODEL,
    }


def _context(site_id: str, **over: Any) -> dict[str, Any]:
    base = {
        "site_id": site_id,
        "description": "A walled city on an island.",
        "wikipedia_title": "Thasos",
        "wikipedia_cache_file": "C:/cache/en/thasos.json",
        "wikipedia_lead_image": "Thasos agora.jpg",
        "owner_link_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Thasos.jpg",
        "owner_link_file": "Thasos.jpg",
        "earlier_stage": "served-check",
        "earlier_verdict": "other_site",
        "earlier_shows": "a view of a different island",
        "earlier_answered_by": "check-001",
    }
    return base | over


# ============================================================================= the population
class TestTheDerivation:
    def test_a_live_hero_judged_other_site_is_in_and_nothing_else_is(self, tmp_path: Path) -> None:
        state = TS.write_read(tmp_path / "run")
        checks = [
            _check_row(THASOS, 1, "other_site"),  # the hero of Thasos
            _check_row(HABU, 10, "depicts"),  # the hero, but it depicts
            _check_row(BARE, 20, "other_site"),  # the hero of Klopot
        ]
        replaces = [_replace_row(THASOS, [("G1", 2, "other_site"), ("G2", 3, "depicts")])]
        got = RC.other_site_heroes(state, checks, replaces)
        # row 2 is a live gallery row judged other_site, but it is no hero
        assert [(h["image_id"], h["site_id"]) for h in got] == [(1, THASOS), (20, BARE)]
        assert got[0]["stage"] == "served-check" and got[0]["shows"] == "the island"

    def test_an_excluded_row_and_a_retired_site_are_out(self, tmp_path: Path) -> None:
        data = TS.read_fixture()
        data["images"][0]["is_excluded"] = True  # the Thasos hero is excluded since
        state = TS.write_read(tmp_path / "run", data)
        checks = [
            _check_row(THASOS, 1, "other_site"),
            _check_row(TS.RETIRED_SITE, 99, "other_site"),
        ]
        assert RC.other_site_heroes(state, checks, []) == []

    def test_the_later_stage_decides_for_a_row_judged_twice(self, tmp_path: Path) -> None:
        state = TS.write_read(tmp_path / "run")
        checks = [_check_row(THASOS, 1, "other_site")]
        replaces = [_replace_row(THASOS, [("G1", 1, "depicts")])]
        assert RC.other_site_heroes(state, checks, replaces) == []

    def test_the_derivation_is_written_once_and_names_a_site_per_line(self, tmp_path: Path) -> None:
        state = TS.write_read(tmp_path / "run")
        heroes = RC.other_site_heroes(state, [_check_row(THASOS, 1, "other_site")], [])
        got = RC.write_derivation(tmp_path / "run", heroes)
        assert got["heroes"] == 1
        assert RC.read_sites(tmp_path / "run" / RC.SITES_FILE) == [THASOS]
        with pytest.raises(ST.StateError, match="written once"):
            RC.write_derivation(tmp_path / "run", heroes)

    def test_an_empty_derivation_is_refused_by_name(self, tmp_path: Path) -> None:
        with pytest.raises(RC.RecheckError, match="nothing to re-check"):
            RC.write_derivation(tmp_path, [])

    def test_two_heroes_of_one_site_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RC.RecheckError, match="one hero"):
            RC.write_derivation(tmp_path, [{"site_id": "a"}, {"site_id": "a"}])

    def test_a_sites_file_names_each_site_once(self, tmp_path: Path) -> None:
        path = tmp_path / "s.txt"
        path.write_text("# the heroes\na\n\nb\n", encoding="utf-8")
        assert RC.read_sites(path) == ["a", "b"]
        path.write_text("a\na\n", encoding="utf-8")
        with pytest.raises(RC.RecheckError, match="twice"):
            RC.read_sites(path)
        path.write_text("\n# nothing\n", encoding="utf-8")
        with pytest.raises(RC.RecheckError, match="no site"):
            RC.read_sites(path)


class TestTheContext:
    def _heroes(self) -> list[dict[str, Any]]:
        return [
            {
                "site_id": THASOS,
                "stage": "served-check",
                "verdict": "other_site",
                "shows": "a view of another island",
                "basis": "b",
                "answered_by": "check-001",
            }
        ]

    def test_the_context_joins_the_read_the_import_and_the_earlier_verdict(self) -> None:
        asked: list[str] = []

        class Client:
            def get(self, url: str, params: dict[str, Any]) -> Any:
                asked.append(params["titles"])

                class Answer:
                    status_code = 200

                    def json(self) -> dict[str, Any]:
                        return {
                            "query": {
                                "pages": [{"title": "Thasos", "pageimage": "Thasos_agora.jpg"}]
                            }
                        }

                return Answer()

        rows = [{"site_id": THASOS, "description": "A walled city.", "wikipedia_title": "Thasos"}]
        owner = {
            THASOS: {"image": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Thasos_Gate.jpg"}
        }
        (got,) = RC.build_context(
            self._heroes(),
            rows,
            owner,
            Client(),
            cache_file=lambda sid: None,
            sleep=lambda _s: None,
        )
        assert asked == ["Thasos"]
        assert set(got) == RC.CONTEXT_KEYS
        assert got["wikipedia_lead_image"] == "Thasos agora.jpg"
        assert got["owner_link_file"] == "Thasos Gate.jpg"
        assert got["wikipedia_cache_file"] is None
        assert (got["earlier_verdict"], got["earlier_shows"]) == (
            "other_site",
            "a view of another island",
        )

    def test_the_cached_page_of_the_site_is_named_in_the_context(self) -> None:
        class Client:
            def get(self, url: str, params: dict[str, Any]) -> Any:
                class Answer:
                    status_code = 200

                    def json(self) -> dict[str, Any]:
                        return {"query": {"pages": [{"title": "Thasos"}]}}

                return Answer()

        rows = [{"site_id": THASOS, "description": "d", "wikipedia_title": "Thasos"}]
        (got,) = RC.build_context(
            self._heroes(),
            rows,
            {},
            Client(),
            cache_file=lambda sid: f"C:/cache/{sid}.json",
            sleep=lambda _s: None,
        )
        assert got["wikipedia_cache_file"] == f"C:/cache/{THASOS}.json"

    def test_a_site_without_an_article_has_no_lead_and_asks_nobody(self) -> None:
        class Client:
            def get(self, *a: Any, **k: Any) -> Any:
                raise AssertionError("nothing to ask")

        rows = [{"site_id": THASOS, "description": "", "wikipedia_title": None}]
        (got,) = RC.build_context(
            self._heroes(), rows, {}, Client(), cache_file=lambda sid: None, sleep=lambda _s: None
        )
        assert got["wikipedia_lead_image"] is None and got["description"] is None
        assert got["owner_link_url"] is None and got["owner_link_file"] is None

    def test_a_failed_wikipedia_request_is_not_read_as_no_image(self) -> None:
        class Client:
            def get(self, *a: Any, **k: Any) -> Any:
                class Answer:
                    status_code = 429

                return Answer()

        rows = [{"site_id": THASOS, "description": "d", "wikipedia_title": "Thasos"}]
        with pytest.raises(RC.RecheckError, match="HTTP 429"):
            RC.build_context(
                self._heroes(),
                rows,
                {},
                Client(),
                cache_file=lambda sid: None,
                sleep=lambda _s: None,
            )

    def test_a_hero_the_read_does_not_answer_is_refused(self) -> None:
        with pytest.raises(RC.RecheckError, match="answered nothing"):
            RC.build_context(
                self._heroes(), [], {}, object(), cache_file=lambda sid: None, sleep=lambda _s: None
            )

    def test_the_context_file_is_written_once_in_its_exact_shape(self, tmp_path: Path) -> None:
        RC.write_context(tmp_path, [_context(THASOS)])
        assert set(RC.load_context(tmp_path / RC.CONTEXT_FILE)) == {THASOS}
        with pytest.raises(ST.StateError, match="written once"):
            RC.write_context(tmp_path, [_context(THASOS)])
        with pytest.raises(RC.RecheckError, match="carries"):
            RC.write_context(tmp_path / "x", [{"site_id": THASOS}])

    def test_the_sql_reads_the_description_and_the_enwiki_title_only(self) -> None:
        sql = RC.context_sql([THASOS])
        assert "site_external_ids" in sql and "enwiki_title" in sql and "INSERT" not in sql
        assert f"'{THASOS}'::uuid" in sql


# ================================================================================ the prompt
def _question(**over: Any) -> V.CheckQuestion:
    base: dict[str, Any] = {
        "batch_id": "check-001",
        "site_id": THASOS,
        "name": "Thasos",
        "country": "Greece",
        "site_type": "City",
        "lat": 40.78,
        "lon": 24.71,
        "qid": "Q2",
        "served": {"image_id": 1},
        "source": "https://ancientnerds.com/x.webp",
        "image": "images/check-x.jpg",
        "jpeg_sha256": "0" * 64,
    }
    return V.CheckQuestion(**(base | over))


class TestThePrompt:
    def test_the_first_check_keeps_its_frozen_prompt_and_id(self) -> None:
        q = _question()
        assert q.prompt_id == "served-check-v1" and q.context is None
        assert "You check the picture a public page shows" in q.prompt()
        assert "re-check" not in q.prompt()

    def test_the_recheck_carries_the_context_the_first_check_lacked(self) -> None:
        q = _question(context=_context(THASOS))
        prompt = q.prompt()
        assert q.prompt_id == "served-check-v2"
        for part in (
            "re-check a verdict",
            "other_site: a view of a different island",
            "Thasos.jpg",  # the owner's 2025 link
            "Thasos agora.jpg",  # the Wikipedia lead image
            "A walled city on an island.",
            "Its text is cached: read C:/cache/en/thasos.json first",
            "a 403 or 429 is never a finding",
            "latitude 40.78",
            "commons.wikimedia.org/...",
        ):
            assert part in prompt, part
        # the verdict terms are the same words as the first check's
        assert V._VERDICT_TERMS in prompt

    def test_a_missing_part_of_the_context_reads_none(self) -> None:
        q = _question(
            context=_context(
                THASOS, wikipedia_lead_image=None, owner_link_file=None, owner_link_url=None
            )
        )
        assert "its lead image: none" in q.prompt()
        assert "by hand in 2025: none" in q.prompt()

    def test_the_question_round_trips_through_its_record(self) -> None:
        q = _question(context=_context(THASOS))
        assert V.CheckQuestion(**q.as_json()) == q
        old = _question().as_json()
        del old["context"]
        assert V.CheckQuestion(**old).prompt() == _question().prompt()


def _answer(verdict: str, shows: str = "the temple of Apollo at Delphi", basis: str = "") -> str:
    basis = basis or "commons.wikimedia.org/wiki/File:Delphi.jpg: the file shows Delphi"
    return json.dumps({"verdict": verdict, "shows": shows, "basis": basis})


class TestTheAnswerShape:
    def test_a_recheck_other_site_names_the_monument_and_cites_commons(self) -> None:
        q = _question(context=_context(THASOS))
        assert V.parse_check(_answer("other_site"), q)["verdict"] == "other_site"
        with pytest.raises(V.AnswerError, match="at least 3 words"):
            V.parse_check(_answer("other_site", shows="an island"), q)
        with pytest.raises(V.AnswerError, match="commons.wikimedia.org"):
            V.parse_check(_answer("other_site", basis="the picture looks like Delphi"), q)

    def test_a_recheck_depicts_needs_no_commons_page(self) -> None:
        q = _question(context=_context(THASOS))
        parsed = V.parse_check(_answer("depicts", shows="the agora", basis="the stoa"), q)
        assert parsed["verdict"] == "depicts"

    def test_the_first_check_is_not_stricter_than_before(self) -> None:
        got = V.parse_check(_answer("other_site", shows="x", basis="y"), _question())
        assert got["verdict"] == "other_site"
        assert V.parse_check(_answer("other_site", shows="x", basis="y"))["shows"] == "x"


# ==================================================================== the stages, restricted
def _recheck_run(
    tmp_path: Path, verdicts: dict[str, str], *, role: str | None = "adversarial"
) -> tuple[Path, Any, Path]:
    """The read, the pre-check, the recheck export for `SITES`, the answers and the import."""
    run, handoff, pictures = TS._setup(tmp_path, gone={"https://example.org/relief.jpg": "404"})
    state = ST.load_read(run / "READ.json")
    pre = PC.load_prechecks(run / "PRECHECK.jsonl")
    ctx = {sid: _context(sid) for sid in SITES}
    V.export_check(
        run, handoff, state, pre, pictures, population=V.RECHECK, sites=SITES, context=ctx
    )
    model = OH.ANSWER_MODELS[RO.role(role).model] if role else OH.OPUS_MODEL
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff,
            batch_id=line["batch_id"],
            stage=V.STAGE_CHECK,
            label=line["label"],
            text=_answer(verdicts[line["label"]]),
            answered_by=f"{role}:{line['batch_id']}" if role else line["batch_id"],
            model=model,
            now=lambda: "2026-10-09T03:00:00+00:00",
        )
    V.import_stage(run, V.STAGE_CHECK, role)
    return run, pictures, handoff


class TestTheRestrictedStages:
    def test_only_the_named_sites_are_asked_and_the_record_names_them(self, tmp_path: Path) -> None:
        run, handoff, pictures = TS._setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_check(run, handoff, state, pre, pictures, sites=[THASOS])
        assert got["questions"] == 1
        record = json.loads((run / V.EXPORT_CHECK).read_text(encoding="utf-8"))
        assert record["sites"] == [THASOS] and record["population"] == V.ALL
        assert [line["label"] for line in OH.manifest(handoff)] == [THASOS]

    def test_a_named_site_the_precheck_does_not_know_is_refused(self, tmp_path: Path) -> None:
        run, handoff, pictures = TS._setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        with pytest.raises(ST.StateError, match="not in the pre-check"):
            V.export_check(run, handoff, state, pre, pictures, sites=["nope"])

    def test_a_named_site_that_serves_nothing_is_refused(self, tmp_path: Path) -> None:
        run, handoff, pictures = TS._setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        with pytest.raises(ST.StateError, match="serve no image"):
            V.export_check(run, handoff, state, pre, pictures, sites=[THASOS, NOTHING])

    def test_a_list_names_each_site_once_and_at_least_one(self, tmp_path: Path) -> None:
        run, handoff, pictures = TS._setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        with pytest.raises(ST.StateError, match="twice"):
            V.export_check(run, handoff, state, pre, pictures, sites=[THASOS, THASOS])
        with pytest.raises(ST.StateError, match="names no site"):
            V.export_check(run, handoff, state, pre, pictures, sites=[])

    def test_a_recheck_needs_its_sites_and_its_context_and_no_one_else_takes_a_context(
        self, tmp_path: Path
    ) -> None:
        run, handoff, pictures = TS._setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        ctx = {THASOS: _context(THASOS)}
        with pytest.raises(ST.StateError, match="--sites is required"):
            V.export_check(run, handoff, state, pre, pictures, population=V.RECHECK, context=ctx)
        with pytest.raises(ST.StateError, match="needs its context"):
            V.export_check(run, handoff, state, pre, pictures, population=V.RECHECK, sites=[THASOS])
        with pytest.raises(ST.StateError, match="needs its context"):
            V.export_check(run, handoff, state, pre, pictures, sites=[THASOS], context=ctx)
        with pytest.raises(ST.StateError, match="no context"):
            V.export_check(
                run, handoff, state, pre, pictures, population=V.RECHECK,
                sites=[THASOS, HABU], context=ctx,
            )  # fmt: skip

    def test_the_question_file_keeps_the_context_and_the_prompt_id(self, tmp_path: Path) -> None:
        run, _, _ = _recheck_run(
            tmp_path, {THASOS: "other_site", HABU: "depicts", BARE: "region_or_type"}
        )
        rows = {r["site_id"]: r for r in V.read_jsonl(run / V.QUESTIONS_CHECK)}
        assert set(rows) == set(SITES)
        assert rows[THASOS]["context"]["earlier_verdict"] == "other_site"
        checks = {r["site_id"]: r for r in V.read_jsonl(run / V.CHECK)}
        assert {r["prompt_id"] for r in checks.values() if r["prompt_id"]} == {"served-check-v2"}
        assert checks[THASOS]["answered_by"].startswith("adversarial:")

    def test_only_a_confirmed_other_site_goes_on_to_the_replacement_stage(
        self, tmp_path: Path
    ) -> None:
        run, pictures, _ = _recheck_run(
            tmp_path, {THASOS: "other_site", HABU: "depicts", BARE: "region_or_type"}
        )
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_replace(
            run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures,
            sites=SITES,
        )  # fmt: skip
        assert got["failed"] == 1 and got["claimed"] == 0
        assert [q["site_id"] for q in V.read_jsonl(run / V.QUESTIONS_REPLACE)] == [THASOS]

    def test_the_replacement_stage_must_name_the_sites_of_the_check_stage(
        self, tmp_path: Path
    ) -> None:
        run, pictures, _ = _recheck_run(
            tmp_path, {THASOS: "other_site", HABU: "depicts", BARE: "region_or_type"}
        )
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        with pytest.raises(ST.StateError, match="not the list the check stage"):
            V.export_replace(
                run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures,
                sites=[THASOS],
            )  # fmt: skip

    def test_a_claimed_site_outside_the_list_is_not_asked(self, tmp_path: Path) -> None:
        run, pictures, _ = _recheck_run(
            tmp_path, {THASOS: "depicts", HABU: "depicts", BARE: "depicts"}
        )
        TS._claim(pictures, tmp_path)  # Ahu Akivi serves nothing and its item claims a file
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_replace(
            run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures,
            sites=SITES,
        )  # fmt: skip
        assert got["claimed"] == 0 and got["questions"] == 0

    def test_a_gallery_file_that_was_excluded_is_not_offered_again(self, tmp_path: Path) -> None:
        """Thasos has an excluded row (`Old excluded.jpg`): a Commons candidate of that name is a
        judged file coming back, and the hero it replaces must not be one (D15, WD2)."""
        read = TS.read_fixture()
        info = {"Old excluded.jpg": TS.GATE_INFO | {"title": "Old excluded.jpg"}}
        run, handoff, pictures = TS._setup(
            tmp_path, read=read, info=info,
            members=["Thasos agora.jpg", "Old excluded.jpg", "Thasos gate.jpg"],
        )  # fmt: skip
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        found, _ = V.candidates_for(
            state, pre[THASOS], PC.load_harvest(tmp_path / "harvest"), pictures.commons
        )
        offered = {c["file"] for c in found if c["kind"] == V.COMMONS_CANDIDATE}
        assert "Old excluded.jpg" not in offered and "Thasos gate.jpg" in offered


class TestTheRole:
    def test_the_brief_names_the_role_and_the_recording_command_carries_it(
        self, tmp_path: Path
    ) -> None:
        run, _, handoff = _recheck_run(
            tmp_path, {THASOS: "other_site", HABU: "depicts", BARE: "region_or_type"}
        )
        text = V.brief(run, handoff, "check-001", "adversarial")
        assert "running as claude-opus-5-5 in the role adversarial at effort high" in text
        assert "--role adversarial" in text
        legacy = V.brief(run, handoff, "check-001")
        assert "running as claude-sonnet-5-5." in legacy and "--role" not in legacy

    def test_an_unknown_role_is_refused(self, tmp_path: Path) -> None:
        run, _, handoff = _recheck_run(
            tmp_path, {THASOS: "other_site", HABU: "depicts", BARE: "region_or_type"}
        )
        with pytest.raises(RO.RoleError, match="no role"):
            V.brief(run, handoff, "check-001", "oracle")

    def test_an_import_in_a_role_the_answers_were_not_given_in_is_refused(
        self, tmp_path: Path
    ) -> None:
        run, handoff, pictures = TS._setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        V.export_check(
            run, handoff, state, pre, pictures, population=V.RECHECK, sites=SITES,
            context={sid: _context(sid) for sid in SITES},
        )  # fmt: skip
        for line in OH.manifest(handoff):
            OH.write_answer(
                handoff, batch_id=line["batch_id"], stage=V.STAGE_CHECK, label=line["label"],
                text=_answer("depicts", basis="b"), answered_by=f"adversarial:{line['batch_id']}",
                model=OH.OPUS_MODEL, now=lambda: "2026-10-09T03:00:00+00:00",
            )  # fmt: skip
        with pytest.raises(ST.StateError, match="not in the role image_depicts"):
            V.import_stage(run, V.STAGE_CHECK, "image_depicts")

    def test_a_stamp_that_is_not_the_roles_model_stops_the_import(self, tmp_path: Path) -> None:
        run, handoff, pictures = TS._setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        V.export_check(
            run, handoff, state, pre, pictures, population=V.RECHECK, sites=SITES,
            context={sid: _context(sid) for sid in SITES},
        )  # fmt: skip
        for line in OH.manifest(handoff):
            OH.write_answer(
                handoff, batch_id=line["batch_id"], stage=V.STAGE_CHECK, label=line["label"],
                text=_answer("depicts", basis="b"), answered_by=f"adversarial:{line['batch_id']}",
                model=OH.SONNET_MODEL, now=lambda: "2026-10-09T03:00:00+00:00",
            )  # fmt: skip
        with pytest.raises(ST.StateError, match="registered to claude-opus-5-5"):
            V.import_stage(run, V.STAGE_CHECK, "adversarial")


# ============================================================================== the plan
class TestThePlan:
    def _planned(
        self, tmp_path: Path, verdicts: dict[str, str], replace: dict[str, str] | None = None
    ):
        run, pictures, _ = _recheck_run(tmp_path, verdicts)
        if replace is not None:
            state = ST.load_read(run / "READ.json")
            pre = PC.load_prechecks(run / "PRECHECK.jsonl")
            handoff = tmp_path / "ho"
            V.export_replace(
                run, handoff, state, pre, PC.load_harvest(tmp_path / "harvest"), pictures,
                sites=SITES,
            )  # fmt: skip
            for line in OH.manifest(handoff):
                OH.write_answer(
                    handoff, batch_id=line["batch_id"], stage=V.STAGE_REPLACE,
                    label=line["label"], text=replace[line["label"]],
                    answered_by=f"adversarial:{line['batch_id']}", model=OH.OPUS_MODEL,
                    now=lambda: "2026-10-09T03:00:00+00:00",
                )  # fmt: skip
            V.import_stage(run, V.STAGE_REPLACE, "adversarial")
        return run, PL.write_plan(run)

    def _expected(self, run: Path) -> dict[str, dict[str, Any]]:
        lines = (run / "chunks" / "EXPECTED.jsonl").read_text(encoding="utf-8").splitlines()
        return {e["site_id"]: e for e in map(json.loads, lines)}

    def test_region_or_type_keeps_the_hero_and_other_site_clears(self, tmp_path: Path) -> None:
        run, summary = self._planned(
            tmp_path,
            {THASOS: "other_site", HABU: "depicts", BARE: "region_or_type"},
            {
                THASOS: json.dumps(
                    {
                        "candidates": {
                            "G1": "region_or_type",
                            "G2": "other_site",
                            "W1": "other_site",
                        },
                        "pick": None,
                        "basis": "none depicts",
                    }
                )
            },
        )
        # only the three rechecked sites are planned: Rag-i Bibi and Ahu Akivi are not examined
        assert set(self._expected(run)) == set(SITES)
        assert summary["counts"]["confirmed"] == 1  # Medinet Habu
        assert summary["counts"]["kept"] == 1  # Klopot, the owner's link
        assert summary["counts"]["cleared"] == 1  # Thasos: nothing depicts it
        expected = self._expected(run)
        assert expected[BARE]["outcome"] == "kept" and expected[BARE]["served_image_id"] == 20
        assert expected[THASOS]["served_image_id"] is None

    def test_a_confirmed_other_site_with_a_gallery_pick_moves_the_hero(
        self, tmp_path: Path
    ) -> None:
        run, summary = self._planned(
            tmp_path,
            {THASOS: "other_site", HABU: "depicts", BARE: "depicts"},
            {
                THASOS: json.dumps(
                    {
                        "candidates": {"G1": "depicts", "G2": "other_site", "W1": "other_site"},
                        "pick": "G1",
                        "basis": "the agora",
                    }
                )
            },
        )
        assert summary["counts"]["replaced"] == 1
        expected = self._expected(run)
        assert expected[THASOS]["served_image_id"] == 2
        chunk = PL.CW.load_chunk(run / "chunks" / "chunk-001")
        columns = sorted({(c.column, c.row_key) for c in chunk.changes if c.site_id == THASOS})
        # the old hero (1) loses the flag and the gallery, the pick (2) takes the flag, and the
        # other_site row (3) leaves the gallery with it
        assert ("is_excluded", "1") in columns and ("is_hero", "2") in columns

    def test_the_excluded_hero_is_the_row_the_first_run_judged(self, tmp_path: Path) -> None:
        run, _ = self._planned(
            tmp_path,
            {THASOS: "other_site", HABU: "depicts", BARE: "depicts"},
            {
                THASOS: json.dumps(
                    {
                        "candidates": {"G1": "depicts", "G2": "depicts", "W1": "other_site"},
                        "pick": "G1",
                        "basis": "the agora",
                    }
                )
            },
        )
        chunk = PL.CW.load_chunk(run / "chunks" / "chunk-001")
        (exclusion,) = [c for c in chunk.changes if c.column == "is_excluded"]
        assert exclusion.row_key == "1" and exclusion.rule == PL.RULE_EXCLUDE

    def test_a_plan_without_a_replacement_answer_for_a_confirmed_other_site_stops(
        self, tmp_path: Path
    ) -> None:
        run, _, _ = _recheck_run(
            tmp_path, {THASOS: "other_site", HABU: "depicts", BARE: "region_or_type"}
        )
        with pytest.raises((ST.StateError, FileNotFoundError)):
            PL.write_plan(run)

    def test_the_other_populations_still_plan_a_region_view_as_not_depicting(
        self, tmp_path: Path
    ) -> None:
        run, _ = TS._full_run(
            tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS}
        )
        assert V.needs_replacement({"verdict": "region_or_type"}, V.ALL)
        assert not V.needs_replacement({"verdict": "region_or_type"}, V.RECHECK)
        assert V.needs_replacement({"verdict": "unfetchable"}, V.RECHECK)
        assert V.run_sites(run) is None


class TestThePrecheckOfNamedSites:
    def test_only_the_named_sites_are_pre_checked_and_the_rest_of_the_harvest_is_none_of_its_business(
        self, tmp_path: Path
    ) -> None:
        state = TS.write_read(tmp_path / "run")
        TS.write_harvest(tmp_path / "harvest", TS.HARVEST_QIDS, TS.HARVEST_ENTITIES)
        fake = TS.FakeCommons(cats={"Thasos.jpg": ["Satellite pictures of Thasos"]})
        harvest = PC.load_harvest(tmp_path / "harvest")
        got = PC.run_precheck(state, harvest, fake, sites=[THASOS])
        assert [c.site_id for c in got.checks] == [THASOS]

    def test_a_named_site_the_read_or_the_harvest_lacks_is_refused(self, tmp_path: Path) -> None:
        state = TS.write_read(tmp_path / "run")
        TS.write_harvest(tmp_path / "harvest", {THASOS: "Q2"}, TS.HARVEST_ENTITIES)
        harvest = PC.load_harvest(tmp_path / "harvest")
        with pytest.raises(PC.HarvestError, match="not shown in the read"):
            PC.run_precheck(state, harvest, TS.FakeCommons(), sites=["nope"])
        with pytest.raises(PC.HarvestError, match="not in the harvest"):
            PC.run_precheck(state, harvest, TS.FakeCommons(), sites=[HABU])


def test_the_command_derives_the_population_from_the_two_stages_of_a_run(tmp_path: Path) -> None:
    from served_image import run as SR

    run = tmp_path / "served-image-2026-10-08-os47"
    TS.write_read(run)
    old = tmp_path / "served-image-2026-09-30"
    old.mkdir()
    (old / V.CHECK).write_text(
        ST.jsonl_text([_check_row(THASOS, 1, "other_site"), _check_row(HABU, 10, "depicts")]),
        encoding="utf-8",
    )
    (old / V.REPLACE).write_text(ST.jsonl_text([]), encoding="utf-8")
    assert SR.cmd_derive_sites(run, old)["sites"] == 1
    assert RC.read_sites(run / RC.SITES_FILE) == [THASOS]


class TestTheRunsSites:
    def test_a_run_without_an_export_examines_every_site(self, tmp_path: Path) -> None:
        assert V.run_sites(tmp_path) is None

    def test_the_check_and_the_replacement_export_must_name_the_same_sites(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / V.EXPORT_CHECK).write_text(json.dumps({"sites": ["a", "b"]}), encoding="utf-8")
        (tmp_path / V.EXPORT_REPLACE).write_text(
            json.dumps({"sites": ["b", "a"]}), encoding="utf-8"
        )
        assert sorted(V.run_sites(tmp_path) or []) == ["a", "b"]  # the order does not matter
        (tmp_path / V.EXPORT_REPLACE).write_text(
            json.dumps({"sites": ["a", "c"]}), encoding="utf-8"
        )
        with pytest.raises(ST.StateError, match="different sites"):
            V.run_sites(tmp_path)

    def test_an_unrestricted_stage_names_no_sites(self, tmp_path: Path) -> None:
        (tmp_path / V.EXPORT_CHECK).write_text(json.dumps({"sites": None}), encoding="utf-8")
        assert V.run_sites(tmp_path) is None


def test_a_wikipedia_answer_of_two_pages_is_not_read_as_one_lead_image() -> None:
    class Client:
        def get(self, url: str, params: dict[str, Any]) -> Any:
            class Answer:
                status_code = 200

                def json(self) -> dict[str, Any]:
                    return {"query": {"pages": [{"title": "A"}, {"title": "B"}]}}

            return Answer()

    with pytest.raises(RC.RecheckError, match="2 pages"):
        RC.lead_image(Client(), "A")
