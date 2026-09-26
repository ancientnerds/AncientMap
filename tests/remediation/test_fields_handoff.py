"""WD1's Opus handoff (`scripts/remediation/fields/handoff.py`): export, brief, check, import.

Offline: the quoted pages come from an `httpx.MockTransport`, the Wikipedia API from a census
`Fetcher` over one. What is pinned: one question per flagged site with exactly its flagged fields; a
prompt changed after the export is refused; a field counts only with every quote found; a re-ask
goes to a new agent with the fields still open; after the last round a clearable field is cleared
and a point is held.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from census.fetch import Fetcher  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402

A_ID = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
B_ID = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
WIKI = "https://en.wikipedia.org/wiki/Temple_of_Hephaestus"
REGISTER = "https://www.odysseus.culture.gr/h/2/eh255.jsp?obj_id=912"
PAGES = {
    WIKI: "<html><body><p>The Temple of Hephaestus was built in 449 BC. It is a Doric temple."
    "</p><p>37.9755°N 23.7215°E</p></body></html>",
    REGISTER: "<html><body><p>Hephaisteion, a temple of the 5th century BC.</p>"
    "<p>37.9756, 23.7214</p></body></html>",
}


def status(value: Any, state: str = C.MISSING, **evidence: Any) -> dict[str, Any]:
    return {"status": state, "reason": "no dated start", "stored": value, "evidence": evidence,
            "flags": []}  # fmt: skip


def classified_line(site_id: str, name: str, country: str, asked: list[str]) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "name": name,
        "country": country,
        "qid": "Q1",
        "enwiki": name,
        "scope_status": None,
        "identity": {"doubt": False, "containers": []},
        "period_name": {"stored": "500 BC - 1 AD", "bucket_of_stored_start": "500 BC - 1 AD"},
        "period_end": None,
        "fields": {
            "coordinates": status("37.9755, 23.7215", C.CONFIRMED, witnesses=[]),
            "period_start": status(-449, dates=[]),
            "site_type": status("Temple", C.CONFIRMED, classes=[]),
            "source_url": status(
                WIKI, C.CONFIRMED, kind="wikipedia", lang="en", resolved_title=name
            ),  # fmt: skip
        },
        "asked": asked,
    }


@pytest.fixture
def run(tmp_path: Path) -> Path:
    out = tmp_path / "run"
    out.mkdir()
    lines = [
        classified_line(A_ID, "Temple of Hephaestus", "Greece", ["period_start"]),
        classified_line(B_ID, "Nea Paphos", "Cyprus", []),
    ]
    (out / C.CLASSIFIED_FILE).write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    return out


def pages_client() -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in PAGES:
            return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"},
                                  content=PAGES[url].encode("utf-8"))  # fmt: skip
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)


def api(tmp_path: Path) -> Fetcher:
    def handle(request: httpx.Request) -> httpx.Response:
        title = dict(request.url.params)["titles"]
        page = {"title": title, "pageprops": {"wikibase_item": "Q1"}}
        return httpx.Response(200, json={"query": {"pages": [page]}})

    return Fetcher(tmp_path / "api", workers=1, transport=httpx.MockTransport(handle))


def answer(**fields: Any) -> str:
    return json.dumps({"fields": fields})


KEEP = {
    "decision": "keep",
    "value": "-449",
    "quotes": [
        {"url": WIKI, "quote": "The Temple of Hephaestus was built in 449 BC."},
        {"url": REGISTER, "quote": "a temple of the 5th century BC"},
    ],
    "reasoning": "Both date the temple to the mid-5th century BC.",
}


def record(handoff: Path, batch: str, label: str, text: str) -> None:
    OH.write_answer(handoff, batch_id=batch, stage=HO.STAGE, label=label, text=text,
                    answered_by=batch)  # fmt: skip


class TestTheExport:
    def test_one_question_per_flagged_site_with_its_fields(self, run: Path, tmp_path: Path) -> None:
        result = HO.export(run, tmp_path / "h-r0")
        assert result == {"round": 0, "handoff": result["handoff"], "sites": 1, "fields": 1,
                          "batches": 1}  # fmt: skip
        manifest = OH.manifest(tmp_path / "h-r0")
        assert [(m["batch_id"], m["label"], m["field"]) for m in manifest] == [
            ("wd1-r0-b0001", A_ID, "period_start")
        ]
        prompt = (tmp_path / "h-r0" / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
        assert "### period_start" in prompt and "### site_type" not in prompt
        assert "Temple of Hephaestus" in prompt and '"period_start"' in prompt
        with pytest.raises(HO.HandoffStepError, match="already"):
            HO.export(run, tmp_path / "h-r0b")

    def test_a_round_needs_a_directory_of_its_own(self, run: Path, tmp_path: Path) -> None:
        (tmp_path / "busy").mkdir()
        (tmp_path / "busy" / "x").write_text("x", encoding="utf-8")
        with pytest.raises(HO.HandoffStepError, match="is not empty"):
            HO.export(run, tmp_path / "busy")

    def test_batches_follow_country_and_name(self) -> None:
        classified = {
            f"s{i}": {"country": country, "name": name}
            for i, (country, name) in enumerate([("Peru", "b"), ("Greece", "z"), ("Greece", "a")])
        }
        batches = HO.batches(list(classified), classified, 1)
        assert batches == [("wd1-r1-b0001", ["s2", "s1", "s0"])]

    def test_the_prompt_is_a_pure_function_of_the_line(self, run: Path) -> None:
        line = HO.read_classified(run)[A_ID]
        assert HO.render_prompt(line, ["period_start"]) == HO.render_prompt(line, ["period_start"])
        with pytest.raises(HO.HandoffStepError, match="at least one field"):
            HO.render_prompt(line, [])

    def test_a_flag_and_an_empty_field_are_shown(self, run: Path) -> None:
        line = HO.read_classified(run)[A_ID]
        line["fields"]["site_type"]["flags"] = ["acceptance stage 1: judged WRONG: a stoa"]
        line["fields"]["source_url"]["stored"] = None
        prompt = HO.render_prompt(line, ["site_type", "source_url"])
        assert "An earlier reading found this field wrong" in prompt
        assert "  - acceptance stage 1: judged WRONG: a stoa" in prompt
        assert prompt.count("The field is empty, so keep is no answer") == 1
        stacked = HO.read_classified(run)[A_ID]
        stacked["fields"]["coordinates"]["evidence"]["stacked"] = 3
        shown = HO.render_prompt(stacked, ["coordinates"])
        assert "3 other site(s) of the database hold exactly the stored point" in shown

    def test_the_brief_names_the_batch_s_own_files(self, run: Path, tmp_path: Path) -> None:
        HO.export(run, tmp_path / "h-r0")
        text = HO.brief(run, tmp_path / "h-r0", "wd1-r0-b0001")
        assert "h-r0-scratch/wd1-r0-b0001/<label>.json" in text
        assert "--answered-by wd1-r0-b0001" in text and "check-answer" in text
        with pytest.raises(HO.HandoffStepError, match="is no batch"):
            HO.brief(run, tmp_path / "h-r0", "wd1-r0-b0009")


class TestCheckAnswer:
    def test_shape_problems_are_named_per_field(self, run: Path, tmp_path: Path) -> None:
        HO.export(run, tmp_path / "h-r0")
        good = HO.check_answer(
            run, tmp_path / "h-r0", "wd1-r0-b0001", A_ID, answer(period_start=KEEP)
        )
        assert good == {"ok": True, "problems": {}}
        wrong = HO.check_answer(run, tmp_path / "h-r0", "wd1-r0-b0001", A_ID,
                                answer(period_start={**KEEP, "value": "-900"}))  # fmt: skip
        assert not wrong["ok"] and "that is replace" in wrong["problems"]["period_start"]
        broken = HO.check_answer(run, tmp_path / "h-r0", "wd1-r0-b0001", A_ID, "not json")
        assert "answer" in broken["problems"]


class TestTheImport:
    def test_a_found_answer_counts_and_is_decided(self, run: Path, tmp_path: Path) -> None:
        handoff = tmp_path / "h-r0"
        HO.export(run, handoff)
        record(handoff, "wd1-r0-b0001", A_ID, answer(period_start=KEEP))
        result = HO.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)
        assert result["counted"] == 1 and result["waiting_sites"] == 0
        decision = HO._read_jsonl(run / HO.DECISIONS_FILE)[0]
        assert decision["decision"] == "keep" and decision["via"] == HO.COUNTED
        assert {q["outcome"] for q in decision["quotes"]} == {"found"}

    def test_a_quote_not_on_its_page_is_asked_again(self, run: Path, tmp_path: Path) -> None:
        handoff = tmp_path / "h-r0"
        HO.export(run, handoff)
        invented = {**KEEP, "quotes": [KEEP["quotes"][0],
                                       {"url": REGISTER, "quote": "built by Pericles in 449 BC"}]}  # fmt: skip
        record(handoff, "wd1-r0-b0001", A_ID, answer(period_start=invented))
        result = HO.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)
        assert result["counted"] == 0 and result["waiting_fields"] == 1
        assert result["not_counted"] == {"quote not found": 1}
        reask = HO.export_reask(run, tmp_path / "h-r1")
        assert reask["round"] == 1 and reask["sites"] == 1
        assert OH.manifest(tmp_path / "h-r1")[0]["batch_id"] == "wd1-r1-b0001"

    def test_an_edited_prompt_is_refused_at_import(self, run: Path, tmp_path: Path) -> None:
        handoff = tmp_path / "h-r0"
        HO.export(run, handoff)
        record(handoff, "wd1-r0-b0001", A_ID, answer(period_start=KEEP))
        lines = HO.read_classified(run)
        lines[A_ID]["name"] = "Hephaisteion"
        (run / C.CLASSIFIED_FILE).write_text(
            "".join(json.dumps(v) + "\n" for v in lines.values()), encoding="utf-8"
        )
        with pytest.raises(HO.HandoffStepError, match="not this question's"):
            HO.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)

    def test_nothing_is_imported_before_every_answer_is_in(self, run: Path, tmp_path: Path) -> None:
        HO.export(run, tmp_path / "h-r0")
        with pytest.raises(HO.HandoffStepError, match="1 missing"):
            HO.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)

    def test_after_the_last_round_a_field_is_cleared_and_a_point_held(
        self, run: Path, tmp_path: Path
    ) -> None:
        lines = HO.read_classified(run)
        lines[A_ID]["asked"] = ["coordinates", "period_start"]
        (run / C.CLASSIFIED_FILE).write_text(
            "".join(json.dumps(v) + "\n" for v in lines.values()), encoding="utf-8"
        )
        bad = answer(coordinates={"decision": "keep", "value": "37.9755, 23.7215", "quotes": [],
                                  "reasoning": "x"},
                     period_start={**KEEP, "value": "-900"})  # fmt: skip
        HO.export(run, tmp_path / "h-r0")
        for number in range(HO.MAX_ROUND + 1):
            handoff = tmp_path / f"h-r{number}"
            if number:
                HO.export_reask(run, handoff)
            record(handoff, f"wd1-r{number}-b0001", A_ID, bad)
            HO.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)
        decisions = {d["field"]: d for d in HO._read_jsonl(run / HO.DECISIONS_FILE)}
        assert decisions["coordinates"]["decision"] == "unresolved"
        assert decisions["period_start"]["decision"] == "clear"
        assert {d["via"] for d in decisions.values()} == {HO.EXHAUSTED}
        with pytest.raises(HO.HandoffStepError, match="nothing to ask again"):
            HO.export_reask(run, tmp_path / "h-r3")

    def test_a_source_url_value_must_be_a_served_article_of_its_own(
        self, run: Path, tmp_path: Path
    ) -> None:
        pages = tmp_path / "pages"
        pages.mkdir()
        from opus_audit import quotes as Q

        Q.store_page(pages, WIKI, status=200, final_url=WIKI, content_type="text/html",
                     body=b"x", error="", fetched_at="t")  # fmt: skip
        assert HO._value_page_problem(WIKI, pages, api(tmp_path)) is None
        Q.store_page(pages, REGISTER, status=200, final_url="https://www.odysseus.culture.gr/",
                     body=b"x", content_type="text/html", error="", fetched_at="t")  # fmt: skip
        assert "redirects to" in str(HO._value_page_problem(REGISTER, pages, None))

        def redirecting(request: httpx.Request) -> httpx.Response:
            title = dict(request.url.params)["titles"]
            return httpx.Response(200, json={"query": {
                "redirects": [{"from": title, "to": "Hephaisteion"}],
                "pages": [{"title": "Hephaisteion"}]}})  # fmt: skip

        net = Fetcher(tmp_path / "api2", workers=1, transport=httpx.MockTransport(redirecting))
        assert "is a redirect" in str(HO._value_page_problem(WIKI, pages, net))
