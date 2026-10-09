"""Lane wd5, step 6: the Opus adversarial re-check of the cells the lane would write
(`scripts/remediation/fields/adversarial.py`).

Offline: the pages are kept files, the counter-quotes' pages an `httpx.MockTransport`, the cache and
the runs temporary directories. No model is called - the tests answer every question themselves.
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

import opus_handoff as OH  # noqa: E402
from acceptance.answers import AnswerError  # noqa: E402
from fields import adversarial as AD  # noqa: E402
from fields import carry as CA  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import plan as FP  # noqa: E402
from fields import rule as R  # noqa: E402
from fields import wiki as W  # noqa: E402
from mechanical.plan import PlanError  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation import test_fields_carry as TC  # noqa: E402
from tests.remediation import test_fields_handoff as TH  # noqa: E402
from tests.remediation import test_fields_plan as TP  # noqa: E402
from tests.remediation import test_fields_wd3 as TW  # noqa: E402
from tests.remediation import test_fields_wd5 as T5  # noqa: E402
from tests.remediation import test_fields_wd5_ops as OPS  # noqa: E402

A_ID, B_ID, C_ID = TH.A_ID, TH.B_ID, "11111111-2222-4333-8444-555555555555"
BUILT = "The Temple of Hephaestus was built in 449 BC."
REASON = "The page names the temple and gives 449 BC as the year it was built."


def put_page(directory: Path, url: str, body: str | None = None) -> None:
    Q.store_page(
        directory / "pages", url, status=200, final_url=url, content_type="text/html",
        body=(body or TH.PAGES[url]).encode(), error="", fetched_at="t",
    )  # fmt: skip


def dec(site: str = A_ID, field: str = "period_start", verdict: str = "replace",
        value: Any = "-449", via: str = "counted", quote: str = BUILT,
        url: str = TH.WIKI, **over: Any) -> dict[str, Any]:  # fmt: skip
    row = {
        "site_id": site, "name": "Temple of Hephaestus", "field": field, "status": "MISSING",
        "stored": None, "asked": 1, "decision": verdict, "value": value, "via": via, "round": 0,
        "counted_rounds": [0], "answered_by": "field_researcher:wd5-r0-b0001",
        "model": OH.SONNET_MODEL, "reasoning": "The article dates the temple to 449 BC.",
        "quotes": [{"source": url, "quote": quote, "outcome": "found"}], "value_page": None,
    }  # fmt: skip
    return {**row, **over}


def lines(*sites: str) -> list[dict[str, Any]]:
    out = []
    for site in sites:
        line = TW.wd3_line(site, asked=["period_start", "coordinates"])
        line["open"]["coordinates"] = {"why": "unsourced-point", "wd1": None}
        out.append(line)
    return out


def make_run(tmp_path: Path, decisions: list[dict[str, Any]], *sites: str) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    R.write_run(run, R.RECHECK)
    HO._write_jsonl(run / C.CLASSIFIED_FILE, lines(*(sites or (A_ID, B_ID, C_ID))))
    HO._write_jsonl(run / HO.DECISIONS_FILE, decisions)
    HO._write_json(run / HO.REASK_FILE, {"after_round": 0, "fields": {}})
    put_page(run, TH.WIKI)
    put_page(run, TH.REGISTER)
    return run


def reply(field: str, decision: str, reasoning: str = REASON, quotes: Any = ()) -> str:
    body = {"decision": decision, "value": None, "reasoning": reasoning,
            "quotes": [{"url": u, "quote": q} for u, q in quotes]}  # fmt: skip
    return json.dumps({"fields": {field: body}})


def record(handoff: Path, batch: str, cell: str, text: str, *, role: bool = True,
           model: str = OH.OPUS_MODEL) -> None:  # fmt: skip
    OH.write_answer(handoff, batch_id=batch, stage=AD.STAGE, label=cell, text=text,
                    answered_by=f"adversarial:{batch}" if role else batch, model=model)  # fmt: skip


def cell_of(site: str = A_ID, field: str = "period_start") -> str:
    return AD.cell_id(site, field)


class TestSelection:
    def test_every_replace_and_a_seeded_tenth_of_the_keeps_are_checked(
        self, tmp_path: Path
    ) -> None:
        keeps = [dec(f"00000000-0000-4000-8000-{n:012d}", "site_type", "keep", "Temple", via="counted")
                 for n in range(20)]  # fmt: skip
        run = make_run(tmp_path, [dec(A_ID), dec(B_ID), *keeps], A_ID, B_ID,
                       *[k["site_id"] for k in keeps])  # fmt: skip
        result = AD.select(run, seed=7, wiki=None)
        assert result["replace"] == 2 and result["keep"] == 20 and result["keep_checked"] == 2
        cells = AD.read_cells(run / HO.ADV_DIR)
        assert {cell_of(A_ID), cell_of(B_ID)} <= set(cells) and len(cells) == 4

    @pytest.mark.parametrize(
        ("keeps", "share", "checked"),
        [(25, 0.1, 3), (100, 0.07, 7), (5, 0.1, 1), (10, 0.5, 5), (20, 1, 20)],
    )
    def test_the_share_of_the_keeps_is_rounded_up_and_not_by_a_float(
        self, tmp_path: Path, keeps: int, share: float, checked: int
    ) -> None:
        """0.07 times 100 is 7.000000000000001 in floating point: 7 % of 100 keeps are 7, not 8."""
        rows = [dec(f"00000000-0000-4000-8000-{n:012d}", "site_type", "keep", "Temple")
                for n in range(keeps)]  # fmt: skip
        run = make_run(tmp_path, rows, *[r["site_id"] for r in rows])
        result = AD.select(run, seed=1, wiki=None, keep_share=share)
        assert result["keep_checked"] == checked

    def test_the_draw_is_seeded_and_the_seed_decides_it(self, tmp_path: Path) -> None:
        def drawn(seed: int, sub: str) -> list[str]:
            keeps = [dec(f"00000000-0000-4000-8000-{n:012d}", "site_type", "keep", "Temple")
                     for n in range(30)]  # fmt: skip
            base = tmp_path / sub
            base.mkdir()
            run = make_run(base, keeps, *[k["site_id"] for k in keeps])
            AD.select(run, seed=seed, wiki=None)
            return sorted(AD.read_cells(run / HO.ADV_DIR))

        assert drawn(1, "a") == drawn(1, "b")
        assert drawn(1, "c") != drawn(2, "d")

    def test_a_cell_is_frozen_with_the_passage_the_quote_was_found_in(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        AD.select(run, seed=1, wiki=None)
        [quote] = AD.read_cells(run / HO.ADV_DIR)[cell_of()]["quotes"]
        assert quote["reading"] == "visible text" and BUILT in quote["passage"]
        assert quote["head"].startswith("The Temple of Hephaestus") and quote["outcome"] == "found"

    def test_the_lead_of_the_sites_own_article_comes_from_the_cache(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        cache = W.WikiCache(OPS.a_cache(tmp_path / "wc"))
        AD.select(run, seed=1, wiki=cache)
        wiki = AD.read_cells(run / HO.ADV_DIR)[cell_of()]["wiki"]
        assert wiki["title"] == "Temple of Hephaestus" and BUILT in wiki["lead"]
        assert wiki["url"] == "https://en.wikipedia.org/wiki/Temple_of_Hephaestus"

    def test_a_carried_decision_is_read_in_the_pages_of_the_run_it_was_made_in(
        self, tmp_path: Path
    ) -> None:
        origin = tmp_path / "origin"
        put_page(origin, TH.WIKI)
        carried = dec(field="coordinates", value="37.9756, 23.7214", via=CA.CARRIED,
                      quote="37.9755°N 23.7215°E", origin={"run": str(origin), "via": "counted"})  # fmt: skip
        run = make_run(tmp_path, [carried], A_ID)
        (run / "pages" / f"{Q.url_key(TH.WIKI)}.json").unlink()  # not in the run's own pages
        AD.select(run, seed=1, wiki=None)
        assert AD.read_cells(run / HO.ADV_DIR)[cell_of(field="coordinates")]["quotes"]

    def test_a_json_page_is_read_in_the_narrowest_reading_that_holds_the_quote(
        self, tmp_path: Path
    ) -> None:
        body = json.dumps({"query": {"extract": f"{BUILT} Then it was restored."}})
        run = make_run(tmp_path, [dec()], A_ID)
        Q.store_page(run / "pages", TH.WIKI, status=200, final_url=TH.WIKI,
                     content_type="application/json", body=body.encode(), error="",
                     fetched_at="t")  # fmt: skip
        AD.select(run, seed=1, wiki=None)
        [quote] = AD.read_cells(run / HO.ADV_DIR)[cell_of()]["quotes"]
        assert quote["reading"] == "json text field"
        assert quote["head"].startswith("The Temple of Hephaestus")  # the extract, not the envelope

    def test_a_missing_article_gives_no_lead(self, tmp_path: Path) -> None:
        root = tmp_path / "wc"
        root.mkdir()
        (root / W.INDEX_FILE).write_text(
            json.dumps({"site_id": A_ID, "lang": "en", "title": "T", "file": "t.json"}) + "\n",
            encoding="utf-8",
        )
        (root / "t.json").write_text(
            json.dumps({"lang": "en", "title": "T", "missing": True}), encoding="utf-8"
        )
        assert AD.wiki_lead(A_ID, W.WikiCache(root)) is None

    def test_a_page_that_cannot_be_read_is_refused_by_name(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        Q.store_page(run / "pages", TH.WIKI, status=404, final_url=TH.WIKI,
                     content_type="text/html", body=b"", error="", fetched_at="t")  # fmt: skip
        with pytest.raises(AD.AdversarialError, match="cannot be read"):
            AD.select(run, seed=1, wiki=None)

    def test_a_quote_the_page_no_longer_holds_is_refused_by_name(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec(quote="built by Pericles in 449 BC")], A_ID)
        with pytest.raises(AD.AdversarialError, match="is not in the page"):
            AD.select(run, seed=1, wiki=None)
        assert not (run / HO.ADV_DIR / AD.CELLS_FILE).exists()

    def test_only_a_wd5_run_with_every_field_decided_is_selected_once(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        HO._write_json(run / HO.REASK_FILE, {"after_round": 0, "fields": {A_ID: ["site_type"]}})
        with pytest.raises(AD.AdversarialError, match="still wait for a re-ask"):
            AD.select(run, seed=1, wiki=None)
        HO._write_json(run / HO.REASK_FILE, {"after_round": 0, "fields": {}})
        AD.select(run, seed=1, wiki=None)
        with pytest.raises(AD.AdversarialError, match="selected once"):
            AD.select(run, seed=1, wiki=None)
        other = tmp_path / "other"
        other.mkdir()
        R.write_run(other, R.ONE_FAMILY)
        with pytest.raises(AD.AdversarialError, match="not a wd5 run"):
            AD.select(other, seed=1, wiki=None)

    @pytest.mark.parametrize("share", [0, -0.1, 1.5])
    def test_a_share_outside_zero_and_one_is_refused(self, tmp_path: Path, share: float) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        with pytest.raises(AD.AdversarialError, match="is not in"):
            AD.select(run, seed=1, wiki=None, keep_share=share)

    def test_a_decision_of_a_site_the_run_never_classified_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec(C_ID)], A_ID)
        with pytest.raises(AD.AdversarialError, match="not in CLASSIFIED"):
            AD.select(run, seed=1, wiki=None)


class TestTheQuestion:
    def cell(self, tmp_path: Path, **over: Any) -> dict[str, Any]:
        run = make_run(tmp_path, [dec(**over)], A_ID)
        AD.select(run, seed=1, wiki=None)
        return AD.read_cells(run / HO.ADV_DIR)[cell_of(field=over.get("field", "period_start"))]

    def test_it_shows_the_decision_the_quote_and_the_passage(self, tmp_path: Path) -> None:
        text = AD.render_prompt(self.cell(tmp_path))
        assert "try to break that decision" in text
        assert "- stored point: 37.9755, 23.7215 (latitude, longitude)" in text
        assert "- the researcher decided: replace" in text and '- value: "-449"' in text
        assert "the bucket of the value: 500 BC - 1 AD" in text
        assert BUILT in text and f"### Quote 1 - {TH.WIKI}" in text
        assert "START of THIS site" in text and "BP counts from 1950" in text
        assert '"decision": "...", "value": null' in text

    def test_each_field_has_its_own_criteria(self, tmp_path: Path) -> None:
        for field, word in (("coordinates", "decimal degrees"), ("site_type", "canonical type"),
                            ("source_url", "article's own address")):  # fmt: skip
            assert word in AD.CRITERIA[field]
        point = self.cell(tmp_path, field="coordinates", value="37.9756, 23.7214",
                          quote="37.9755°N 23.7215°E")  # fmt: skip
        assert "position of THIS site's own place" in AD.render_prompt(point)

    def test_a_keep_is_checked_against_the_stored_value(self, tmp_path: Path) -> None:
        text = AD.render_prompt(self.cell(tmp_path, verdict="keep", stored="-449"))
        assert "This is a keep: the stored value stands on the quote(s)" in text

    def test_a_re_ask_says_why_the_last_answer_could_not_be_used(self, tmp_path: Path) -> None:
        cell = self.cell(tmp_path)
        assert "An earlier answer" not in AD.render_prompt(cell)
        text = AD.render_prompt(cell, "the answer was unclear: the page is cut off")
        assert "An earlier answer to this check could not be used: the answer was unclear" in text

    def test_the_prompt_is_a_pure_function_of_the_frozen_cell(self, tmp_path: Path) -> None:
        cell = self.cell(tmp_path)
        assert AD.render_prompt(cell) == AD.render_prompt(json.loads(json.dumps(cell)))

    def test_the_lead_of_the_sites_own_article_is_shown(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        AD.select(run, seed=1, wiki=W.WikiCache(OPS.a_cache(tmp_path / "wc")))
        text = AD.render_prompt(AD.read_cells(run / HO.ADV_DIR)[cell_of()])
        assert "the lead of the site's own Wikipedia article" in text
        assert "https://en.wikipedia.org/wiki/Temple_of_Hephaestus, revision 77" in text

    def test_the_page_a_source_url_value_names_is_shown(self, tmp_path: Path) -> None:
        page = {"problem": None, "unreadable": False, "lang": "en"}
        run = make_run(
            tmp_path,
            [dec(field="source_url", value=TH.WIKI, value_page=page)],
            A_ID,
        )
        AD.select(run, seed=1, wiki=None)
        cell = AD.read_cells(run / HO.ADV_DIR)[cell_of(field="source_url")]
        assert "The page the value names was served" in AD.render_prompt(cell)

    def test_why_the_field_was_asked_is_shown(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        line = HO.read_classified(run)[A_ID]
        line["open"]["period_start"] = {"why": "rule-made", "wd1": None, "made": "by a rule"}
        HO._write_jsonl(run / C.CLASSIFIED_FILE, [line])
        AD.select(run, seed=1, wiki=None)
        text = AD.render_prompt(AD.read_cells(run / HO.ADV_DIR)[cell_of()])
        assert HO.OPEN_TEXT["rule-made"] in text


class TestTheAnswer:
    def parsed(self, text: str, field: str = "period_start") -> tuple[str, str, tuple[Any, ...]]:
        return AD.parse_answer(text, field)

    def test_the_three_verdicts(self) -> None:
        for verdict in AD.VERDICTS:
            assert self.parsed(reply("period_start", verdict))[0] == verdict
        found = self.parsed(reply("period_start", "reject", quotes=[(TH.REGISTER, "a temple")]))
        assert found[2][0].url == TH.REGISTER

    @pytest.mark.parametrize(
        ("text", "said"),
        [
            ("not json", "not one JSON object"),
            (reply("site_type", "confirm"), "not the asked field"),
            (reply("period_start", "maybe"), "is not one of"),
            (reply("period_start", "confirm", "too short"), "shorter than"),
            (reply("period_start", "confirm", quotes=[(TH.WIKI, "x")]), "carries no quote"),
            (reply("period_start", "reject", quotes=[(TH.WIKI, "x")] * 4), "at most 3"),
            (json.dumps({"fields": {"period_start": {"decision": "confirm"}}}), "carries"),
            (
                json.dumps(
                    {
                        "fields": {
                            "period_start": {
                                "decision": "confirm",
                                "value": "-449",
                                "quotes": [],
                                "reasoning": REASON,
                            }
                        }
                    }
                ),
                "value of a check is null",
            ),
        ],
    )
    def test_what_is_not_in_shape_is_refused_by_name(self, text: str, said: str) -> None:
        with pytest.raises(AnswerError, match=said):
            self.parsed(text)


class TestTheRounds:
    @pytest.fixture
    def adv(self, tmp_path: Path) -> Path:
        decisions = [dec(A_ID), dec(B_ID), dec(C_ID)]
        run = make_run(tmp_path, decisions)
        AD.select(run, seed=1, wiki=None)
        return run / HO.ADV_DIR

    def test_one_question_per_cell_in_batches_by_country_and_name(
        self, adv: Path, tmp_path: Path
    ) -> None:
        result = AD.export(adv, tmp_path / "h-r0")
        assert result == {"round": 0, "handoff": result["handoff"], "cells": 3, "batches": 1}
        manifest = OH.manifest(tmp_path / "h-r0")
        assert {m["label"] for m in manifest} == {cell_of(A_ID), cell_of(B_ID), cell_of(C_ID)}
        assert {m["batch_id"] for m in manifest} == {"adv-r0-b0001"}
        assert {m["field"] for m in manifest} == {"period_start"}
        record_ = AD.read_rounds(adv)[0]
        assert record_["model"] == "claude-opus-5-5" and record_["round"] == 0
        assert record_["fields"][cell_of(A_ID)] == ["period_start"]
        with pytest.raises(AD.AdversarialError, match="exported already"):
            AD.export(adv, tmp_path / "h-r0b")

    def test_a_re_ask_needs_a_round_before_it(self, adv: Path, tmp_path: Path) -> None:
        with pytest.raises(AD.AdversarialError, match="nothing was exported"):
            AD.export_reask(adv, tmp_path / "h-r1")

    def test_nothing_is_exported_before_the_cells_are_selected(self, tmp_path: Path) -> None:
        (tmp_path / "adv").mkdir()
        with pytest.raises(AD.AdversarialError, match="run `select` first"):
            AD.export(tmp_path / "adv", tmp_path / "h-r0")

    def test_a_round_needs_a_directory_of_its_own(self, adv: Path, tmp_path: Path) -> None:
        (tmp_path / "busy").mkdir()
        (tmp_path / "busy" / "x").write_text("x", encoding="utf-8")
        with pytest.raises(AD.AdversarialError, match="is not empty"):
            AD.export(adv, tmp_path / "busy")

    def test_nine_cells_are_two_batches(self) -> None:
        cells = [{"cell": f"c{n}", "country": "Greece", "name": f"s{n:02d}"} for n in range(9)]
        assert [len(labels) for _, labels in AD.batches(cells, 0)] == [8, 1]

    def test_the_brief_names_the_role_the_model_and_the_cache(
        self, adv: Path, tmp_path: Path
    ) -> None:
        AD.export(adv, tmp_path / "h-r0")
        text = AD.brief(adv, tmp_path / "h-r0", "adv-r0-b0001")
        assert "--model claude-opus-5-5 --role adversarial" in text
        assert "handoff.py wiki-text --label <site id>" in text and "--stage adv" in text
        assert "adversarial.py check-answer" in text and "3 check question(s)" in text
        with pytest.raises(AD.AdversarialError, match="is no batch"):
            AD.brief(adv, tmp_path / "h-r0", "adv-r0-b0009")

    def test_check_answer_names_the_shape_problem(self, adv: Path, tmp_path: Path) -> None:
        AD.export(adv, tmp_path / "h-r0")
        args = (adv, tmp_path / "h-r0", "adv-r0-b0001", cell_of(A_ID))
        assert AD.check_answer(*args, reply("period_start", "confirm")) == {"ok": True,
                                                                           "problems": {}}  # fmt: skip
        bad = AD.check_answer(*args, reply("period_start", "confirm", "short"))
        assert not bad["ok"] and "shorter than" in bad["problems"]["answer"]
        with pytest.raises(AD.AdversarialError, match="is no question"):
            AD.check_answer(adv, tmp_path / "h-r0", "adv-r0-b0001", "nowhere.period_start", "x")


class TestTheImport:
    @pytest.fixture
    def adv(self, tmp_path: Path) -> Path:
        run = make_run(tmp_path, [dec(A_ID), dec(B_ID), dec(C_ID)])
        AD.select(run, seed=1, wiki=None)
        adv = run / HO.ADV_DIR
        AD.export(adv, tmp_path / "h-r0")
        return adv

    def answer_all(self, tmp_path: Path, verdicts: dict[str, str], **kw: Any) -> None:
        for site, verdict in verdicts.items():
            record(tmp_path / "h-r0", "adv-r0-b0001", cell_of(site),
                   reply("period_start", verdict), **kw)  # fmt: skip

    def imported(self, adv: Path, **kw: Any) -> dict[str, Any]:
        return AD.import_answers(adv, client=TH.pages_client(), pace=0, **kw)

    def test_the_states_follow_the_latest_answer(self, adv: Path, tmp_path: Path) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "reject", C_ID: "unclear"})
        result = self.imported(adv)
        assert result["states"] == {"confirm": 1, "reject": 1, "reask": 1}
        assert result["waiting_for_reask"] == 1
        rows = {r["cell"]: r for r in HO._read_jsonl(adv / AD.VERDICTS_FILE)}
        assert rows[cell_of(A_ID)]["verdict"] == "confirm"
        assert rows[cell_of(A_ID)]["answered_by"] == "adversarial:adv-r0-b0001"
        reask = json.loads((adv / AD.REASK_FILE).read_text(encoding="utf-8"))
        assert reask["after_round"] == 0 and list(reask["cells"]) == [cell_of(C_ID)]

    def test_an_answer_not_in_shape_is_read_as_undecided_not_dropped(
        self, adv: Path, tmp_path: Path
    ) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "confirm"})
        record(tmp_path / "h-r0", "adv-r0-b0001", cell_of(C_ID), '{"fields": {}}')
        result = self.imported(adv)
        assert result["states"] == {"confirm": 2, "reask": 1}
        reask = json.loads((adv / AD.REASK_FILE).read_text(encoding="utf-8"))["cells"]
        assert "malformed answer" in reask[cell_of(C_ID)]

    def test_nothing_is_imported_before_anything_is_exported(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        AD.select(run, seed=1, wiki=None)
        with pytest.raises(AD.AdversarialError, match="nothing was exported"):
            AD.import_answers(run / HO.ADV_DIR, client=TH.pages_client(), pace=0)

    def test_a_manifest_that_is_not_the_rounds_record_is_refused(
        self, adv: Path, tmp_path: Path
    ) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "confirm", C_ID: "confirm"})
        rounds = AD.read_rounds(adv)
        rounds[0]["batches"]["adv-r0-b0001"].pop()
        HO._write_jsonl(adv / AD.ROUNDS_FILE, rounds)
        with pytest.raises(AD.AdversarialError, match="not the round's record"):
            self.imported(adv)

    def test_nothing_is_imported_before_every_answer_is_in(self, adv: Path, tmp_path: Path) -> None:
        record(tmp_path / "h-r0", "adv-r0-b0001", cell_of(A_ID), reply("period_start", "confirm"))
        with pytest.raises(AD.AdversarialError, match="2 missing"):
            self.imported(adv)

    def test_an_answer_recorded_without_the_role_is_refused_by_name(
        self, adv: Path, tmp_path: Path
    ) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "confirm", C_ID: "confirm"}, role=False)
        with pytest.raises(AD.AdversarialError, match="names no adversarial role"):
            self.imported(adv)
        assert not (adv / AD.VERDICTS_FILE).exists()

    def test_an_answer_stamped_with_another_model_is_refused(
        self, adv: Path, tmp_path: Path
    ) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "confirm", C_ID: "confirm"},
                        model=OH.SONNET_MODEL)  # fmt: skip
        with pytest.raises(AD.AdversarialError, match="registered to claude-opus-5-5"):
            self.imported(adv)

    def test_an_exported_prompt_that_changed_is_refused(self, adv: Path, tmp_path: Path) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "confirm", C_ID: "confirm"})
        cells = json.loads((adv / AD.CELLS_FILE).read_text(encoding="utf-8"))
        cells["cells"][0]["name"] = "Hephaisteion"
        (adv / AD.CELLS_FILE).write_text(json.dumps(cells), encoding="utf-8")
        with pytest.raises(AD.AdversarialError, match="not this question's"):
            self.imported(adv)

    def test_a_counter_quote_is_found_in_its_page_or_reported(
        self, adv: Path, tmp_path: Path
    ) -> None:
        good = reply(
            "period_start", "reject", quotes=[(TH.REGISTER, "a temple of the 5th century BC")]
        )
        invented = reply("period_start", "reject", quotes=[(TH.REGISTER, "built by Pericles")])
        record(tmp_path / "h-r0", "adv-r0-b0001", cell_of(A_ID), good)
        record(tmp_path / "h-r0", "adv-r0-b0001", cell_of(B_ID), invented)
        record(tmp_path / "h-r0", "adv-r0-b0001", cell_of(C_ID), reply("period_start", "confirm"))
        result = self.imported(adv)
        assert result["states"] == {"confirm": 1, "reject": 2}  # a reject stays a reject
        assert result["quote_problems"] == [f"{cell_of(B_ID)}: {TH.REGISTER} (not found)"]
        rows = {r["cell"]: r for r in HO._read_jsonl(adv / AD.VERDICTS_FILE)}
        assert rows[cell_of(A_ID)]["quotes"][0]["outcome"] == "found"

    def test_the_import_can_be_repeated(self, adv: Path, tmp_path: Path) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "reject", C_ID: "confirm"})
        first = self.imported(adv)
        assert self.imported(adv) == first

    def test_the_re_ask_goes_to_a_new_agent_and_is_decided_after_one_more_round(
        self, adv: Path, tmp_path: Path
    ) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "confirm", C_ID: "unclear"})
        self.imported(adv)
        result = AD.export_reask(adv, tmp_path / "h-r1")
        assert result == {"round": 1, "handoff": result["handoff"], "cells": 1, "batches": 1}
        prompt = (tmp_path / "h-r1" / OH.manifest(tmp_path / "h-r1")[0]["prompt_path"]).read_text(
            encoding="utf-8"
        )
        assert "An earlier answer to this check could not be used" in prompt
        record(tmp_path / "h-r1", "adv-r1-b0001", cell_of(C_ID), reply("period_start", "unclear"))
        final = self.imported(adv)
        assert final["states"] == {"confirm": 2, "unclear": 1} and final["waiting_for_reask"] == 0
        with pytest.raises(AD.AdversarialError, match="nothing to ask again"):
            AD.export_reask(adv, tmp_path / "h-r2")

    def test_a_re_ask_needs_the_round_before_it_imported(self, adv: Path, tmp_path: Path) -> None:
        with pytest.raises(AD.AdversarialError, match="import round 0 before a re-ask"):
            AD.export_reask(adv, tmp_path / "h-r1")

    def test_a_cell_decided_in_round_one_is_decided(self, adv: Path, tmp_path: Path) -> None:
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "confirm", C_ID: "unclear"})
        self.imported(adv)
        AD.export_reask(adv, tmp_path / "h-r1")
        record(tmp_path / "h-r1", "adv-r1-b0001", cell_of(C_ID), reply("period_start", "reject"))
        assert self.imported(adv)["states"] == {"confirm": 2, "reject": 1}

    def test_the_state_of_a_cell(self) -> None:
        def at(round_: int, verdict: str | None) -> dict[str, Any]:
            return {"round": round_, "verdict": verdict}

        assert AD.state_of([]) == ("pending", None)
        assert AD.state_of([at(0, "confirm")])[0] == "confirm"
        assert AD.state_of([at(0, "unclear")])[0] == "reask"
        assert AD.state_of([at(0, None)])[0] == "reask"
        assert AD.state_of([at(0, "unclear"), at(1, "unclear")])[0] == "unclear"
        assert AD.state_of([at(0, "unclear"), at(1, None)])[0] == "unclear"
        assert AD.state_of([at(0, "unclear"), at(1, "reject")])[0] == "reject"

    def test_the_status_counts_the_states(self, adv: Path, tmp_path: Path) -> None:
        assert AD.status(adv)["states"] == {"pending": 3}
        self.answer_all(tmp_path, {A_ID: "confirm", B_ID: "reject", C_ID: "confirm"})
        self.imported(adv)
        status = AD.status(adv)
        assert status["states"] == {"confirm": 2, "reject": 1} and status["applied"] is False


class TestApply:
    def prepared(self, tmp_path: Path, verdicts: dict[str, str]) -> Path:
        decisions = [dec(A_ID), dec(B_ID), dec(C_ID),
                     dec(A_ID, "site_type", "keep", "Temple", stored="Temple"),
                     dec(B_ID, "site_type", "keep", "Temple", stored="Temple")]  # fmt: skip
        run = make_run(tmp_path, decisions)
        AD.select(run, seed=1, wiki=None, keep_share=0.5)
        adv = run / HO.ADV_DIR
        AD.export(adv, tmp_path / "h-r0")
        for cell in AD.read_cells(adv):
            site, field = cell.split(".")
            verdict = verdicts.get(site if field == "period_start" else "keep", "confirm")
            record(tmp_path / "h-r0", "adv-r0-b0001", cell, reply(field, verdict))
        AD.import_answers(adv, client=TH.pages_client(), pace=0)
        return run

    def test_a_confirm_stands_a_reject_is_unresolved_an_unclear_is_held(
        self, tmp_path: Path
    ) -> None:
        run = self.prepared(tmp_path, {B_ID: "reject"})
        adv = run / HO.ADV_DIR
        assert AD.status(adv)["states"]["confirm"] >= 2
        result = AD.apply(run)
        assert result["reject"] == 1 and result["confirm"] >= 2
        rows = {(d["site_id"], d["field"]): d for d in HO._read_jsonl(run / HO.DECISIONS_FILE)}
        kept = rows[(A_ID, "period_start")]
        assert kept["decision"] == "replace" and kept["adversarial"]["verdict"] == "confirm"
        assert kept["adversarial"]["answered_by"] == "adversarial:adv-r0-b0001"
        rejected = rows[(B_ID, "period_start")]
        assert rejected["decision"] == "unresolved" and rejected["via"] == "adversarial"
        assert rejected["value"] is None and rejected["quotes"] == []
        assert "adversarial reject (round 0" in rejected["reasoning"]
        assert rejected["adversarial"]["original"]["value"] == "-449"
        assert rejected["adversarial"]["original"]["quotes"][0]["outcome"] == "found"

    def test_an_unclear_after_the_last_round_is_held(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {C_ID: "unclear"})
        adv = run / HO.ADV_DIR
        AD.export_reask(adv, tmp_path / "h-r1")
        record(tmp_path / "h-r1", "adv-r1-b0001", cell_of(C_ID), reply("period_start", "unclear"))
        AD.import_answers(adv, client=TH.pages_client(), pace=0)
        assert AD.apply(run)["unclear"] == 1
        rows = {(d["site_id"], d["field"]): d for d in HO._read_jsonl(run / HO.DECISIONS_FILE)}
        held = rows[(C_ID, "period_start")]
        assert held["decision"] == HO.HELD and held["via"] == "adversarial"
        assert "adversarial unclear (round 1" in held["reasoning"]

    def test_the_owner_is_given_every_rejected_and_held_cell(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {B_ID: "reject"})
        AD.apply(run)
        [row] = HO._read_jsonl(run / HO.ADV_DIR / AD.OWNER_FILE)
        assert (
            row["site_id"] == B_ID and row["state"] == "reject" and row["field"] == "period_start"
        )
        assert row["researcher"]["decision"] == "replace" and row["researcher"]["value"] == "-449"
        assert row["researcher_quotes"][0]["source"] == TH.WIKI and row["reason"] == REASON

    def test_the_file_before_is_kept_and_the_new_one_is_pinned(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {})
        before = (run / HO.DECISIONS_FILE).read_bytes()
        AD.apply(run)
        adv = run / HO.ADV_DIR
        assert (adv / AD.PRE_FILE).read_bytes() == before
        applied = json.loads((adv / AD.APPLIED_FILE).read_text(encoding="utf-8"))
        assert applied["decisions_sha256"] == FP._sha256_text(run / HO.DECISIONS_FILE)
        assert applied["pre_sha256"] == FP._sha256_text(adv / AD.PRE_FILE)

    def test_a_decision_nobody_checked_is_left_as_it_was(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {})
        sample = set(AD.read_cells(run / HO.ADV_DIR))
        before = {(d["site_id"], d["field"]): d for d in HO._read_jsonl(run / HO.DECISIONS_FILE)}
        AD.apply(run)
        after = {(d["site_id"], d["field"]): d for d in HO._read_jsonl(run / HO.DECISIONS_FILE)}
        for key, row in before.items():
            if AD.cell_id(*key) not in sample:
                assert after[key] == row

    def test_it_is_applied_once(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {})
        AD.apply(run)
        with pytest.raises(AD.AdversarialError, match="applied once"):
            AD.apply(run)

    def test_a_half_applied_check_is_named(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {})
        (run / HO.ADV_DIR / AD.PRE_FILE).write_text("x", encoding="utf-8")
        with pytest.raises(AD.AdversarialError, match="half-applied"):
            AD.apply(run)

    def test_decisions_that_changed_since_the_selection_are_refused(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {})
        with (run / HO.DECISIONS_FILE).open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with pytest.raises(AD.AdversarialError, match="not the file the cells were selected"):
            AD.apply(run)

    def test_a_cell_without_its_final_verdict_blocks_the_apply(self, tmp_path: Path) -> None:
        run = self.prepared(tmp_path, {C_ID: "unclear"})
        with pytest.raises(AD.AdversarialError, match="no final verdict"):
            AD.apply(run)
        assert not (run / HO.ADV_DIR / AD.PRE_FILE).exists()

    def test_the_apply_needs_the_import(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [dec()], A_ID)
        AD.select(run, seed=1, wiki=None)
        with pytest.raises(AD.AdversarialError, match="import the answers first"):
            AD.apply(run)


class TestWhatThePlanReads:
    def test_a_wave_is_planned_only_from_the_decisions_the_check_was_applied_to(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(FP, "REPO", tmp_path)
        monkeypatch.setattr(HO, "REPO", tmp_path)
        run = make_run(tmp_path, [dec(verdict="unresolved", value=None, quote=BUILT)], A_ID)
        T5.pass_calibrations(tmp_path)
        with pytest.raises(PlanError, match="adv/APPLIED.json|APPLIED.json is missing"):
            FP.build_wave(run, "2026-10-09a")
        T5.pin_adversarial(run)
        with (run / HO.DECISIONS_FILE).open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with pytest.raises(PlanError, match="not the file the adversarial re-check was applied"):
            FP.build_wave(run, "2026-10-09a")

    def test_a_rejected_rule_made_start_is_cleared_to_undated(self) -> None:
        original = dec(verdict="replace")
        rejected = AD._rewritten(original, AD.REJECT, {"round": 0, "answered_by": "adversarial:b",
                                                       "model": OH.OPUS_MODEL, "reasoning": REASON,
                                                       "problem": None, "quotes": []})  # fmt: skip
        cells = FP.site_cells(
            TP.live(period_start=-4000, period_name="4500 - 3000 BC"),
            {"open": {"period_start": {"why": "rule-made"}}},
            {"period_start": {**rejected, "stored": -4000}},
            {}, country_check=TP.AGREES, under=R.RECHECK,
            kinds={"period_start": "rule", "period_name": None},
        )  # fmt: skip
        written = {(v.column, v.new_value) for v in cells if v.ok}
        assert written == {("period_start", None), ("period_name", "Undated")}

    def test_an_unclear_cell_is_held_not_written(self) -> None:
        held = AD._rewritten(dec(), AD.UNCLEAR, {"round": 1, "answered_by": "adversarial:b",
                                                 "model": OH.OPUS_MODEL, "reasoning": REASON,
                                                 "problem": None, "quotes": []})  # fmt: skip
        cells = FP.site_cells(
            TP.live(period_start=-4000, period_name="4500 - 3000 BC"),
            {"open": {"period_start": {"why": "rule-made"}}},
            {"period_start": {**held, "stored": -4000}},
            {}, country_check=TP.AGREES, under=R.RECHECK, kinds={"period_start": "rule"},
        )  # fmt: skip
        assert [v.reason for v in cells if not v.ok] == ["held-unreadable"]
        assert not [v for v in cells if v.ok]

    def test_the_journal_evidence_of_a_written_cell_carries_the_verdict(self) -> None:
        confirmed = {**dec(), "adversarial": {"verdict": "confirm", "round": 0}}
        evidence = FP._decision_evidence(confirmed, R.RECHECK)
        assert evidence[-1]["adversarial"] == {"verdict": "confirm", "round": 0}
        assert "adversarial" not in FP._decision_evidence(dec(), R.RECHECK)[-1]


class TestACarriedWd1Decision:
    """WD1's `DECISIONS.jsonl` rows carry no `model` key: the carried row gets the census's model, and
    the check and the plan read it like any other decision's."""

    def carried_row(self, tmp_path: Path) -> dict[str, Any]:
        site = TC.COAST
        world = TC.World(tmp_path, [TC.wd1_decision(site)], site)
        world.lines(TC.line(site))
        world.census = {("wd1-r1-b0004", f"{site}.answer.json"): "claude-sonnet-5-5"}
        world.carry()
        [row] = CA.read_carried(world.run)
        return row

    def test_the_check_selects_it_and_the_packet_names_the_model(self, tmp_path: Path) -> None:
        row = self.carried_row(tmp_path / "carry")
        run = make_run(tmp_path, [row], row["site_id"])
        put_page(
            Path(row["origin"]["run"]), "https://x.org/a", "The point is 35.156834, 32.788315."
        )
        assert AD.select(run, seed=1, wiki=None)["replace"] == 1
        packet = AD.read_cells(run / HO.ADV_DIR)[AD.cell_id(row["site_id"], "coordinates")]
        assert packet["model"] == "claude-sonnet-5-5" and packet["via"] == CA.CARRIED

    def test_the_plans_evidence_names_the_model(self, tmp_path: Path) -> None:
        row = self.carried_row(tmp_path)
        assert FP._decision_evidence(row, R.RECHECK)[-1]["model"] == "claude-sonnet-5-5"
