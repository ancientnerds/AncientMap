"""Lane WD3 (`scripts/remediation/fields/`): WD1 again under the owner's rule of 2026-10-01.

One source suffices (a verbatim quote found by machine in the fetched page, every field check of
`answers.py` kept), the run is aimed at the fields WD1 left open, the write plan fills and never
clears, and the owner gets the list of what stays open. Offline, like WD1's own tests: the quoted
pages come from an `httpx.MockTransport`, production from a fake reader, the repository root from a
temporary directory. WD1's two-family rule stays the default - its tests run unchanged beside these.
"""

from __future__ import annotations

import hashlib
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
from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import owner_list as OL  # noqa: E402
from fields import plan as FP  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402
from mechanical import apply as MA  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical.plan import PlanError  # noqa: E402

from tests.remediation import test_fields_answers as TA  # noqa: E402
from tests.remediation import test_fields_handoff as TH  # noqa: E402
from tests.remediation import test_fields_plan as TP  # noqa: E402
from tests.remediation.test_fields_classify import SITE, TABLE, TestTheRun  # noqa: E402

ONE = R.ONE_FAMILY
A_ID, B_ID = TH.A_ID, TH.B_ID
WIKI, REGISTER = TH.WIKI, TH.REGISTER
EARLIER = {
    "decision": "clear",
    "via": "counted",
    "run": "output/remediation/fields/wd1",
    "reasoning": "only Wikipedia dates the temple, no second family does",
}


# ------------------------------------------------------------------------------ the rule
class TestTheRule:
    def test_a_run_without_a_file_is_a_wd1_run(self, tmp_path: Path) -> None:
        assert R.read_rule(tmp_path) is R.TWO_FAMILIES
        assert R.TWO_FAMILIES.stage == "wd1" and ONE.stage == "wd3"

    def test_the_rule_is_pinned_in_the_run_s_file(self, tmp_path: Path) -> None:
        R.write_run(tmp_path, ONE, built_at="t")
        assert R.read_rule(tmp_path) is ONE
        with pytest.raises(R.RuleError, match="pins rule 'one-family'"):
            R.write_run(tmp_path, R.TWO_FAMILIES)

    def test_an_unknown_rule_or_a_stage_that_is_not_its_own_is_refused(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / R.RUN_FILE).write_text(
            '{"rule": "any-family", "stage": "wd3"}', encoding="utf-8"
        )
        with pytest.raises(R.RuleError, match="is not one of"):
            R.read_rule(tmp_path)
        (tmp_path / R.RUN_FILE).write_text(
            '{"rule": "one-family", "stage": "wd1"}', encoding="utf-8"
        )
        with pytest.raises(R.RuleError, match="stage 'wd1'"):
            R.read_rule(tmp_path)

    def test_wd3_fills_and_never_clears(self) -> None:
        assert ONE.fill_only and not ONE.clearable
        assert R.TWO_FAMILIES.clearable and not R.TWO_FAMILIES.fill_only
        assert ONE.min_quotes == 1 and ONE.min_families == 1


# ------------------------------------------------------------------------------ the answers
def checked(field: str, answer: dict[str, Any], rule: R.Rule = ONE, **stored: Any) -> Any:
    return A.check_shape(TA.text(**{field: answer}), [field], TA.line(**stored), rule)[field]


class TestOneFamilyAnswers:
    def test_one_quote_from_one_source_suffices(self) -> None:
        one = [(WIKI, "The Temple of Hephaestus was built in 449 BC.")]
        assert checked("period_start", TA.block("keep", "-449", one)).decision == "keep"
        filled = checked("period_start", TA.block("replace", "-449", one), period_start=None)
        assert filled.decision == "replace" and len(filled.quotes) == 1

    def test_wd1_still_asks_for_two_families(self) -> None:
        one = [(WIKI, "The Temple of Hephaestus was built in 449 BC.")]
        problem = checked("period_start", TA.block("keep", "-449", one), R.TWO_FAMILIES)
        assert "two independent source families" in problem

    def test_every_field_check_stays(self) -> None:
        undated = [(WIKI, "a Doric temple")]
        assert "carries no date" in checked("period_start", TA.block("keep", "-449", undated))
        no_word = [(WIKI, "a Doric building")]
        assert "no quote holds a word" in checked("site_type", TA.block("keep", "Temple", no_word))
        far = [(WIKI, "38.1°N 23.7215°E")]
        assert "km from the value" in checked(
            "coordinates", TA.block("keep", "37.9755, 23.7215", far)
        )
        coarse = [(WIKI, "38°N 24°E")]
        assert "too coarse" in checked("coordinates", TA.block("keep", "37.9755, 23.7215", coarse))
        elsewhere = [(REGISTER, "Hephaisteion, a temple")]
        assert "no quote is from the value's own page" in checked(
            "source_url", TA.block("keep", WIKI, elsewhere)
        )

    def test_a_field_nobody_can_source_is_unresolved_never_clear(self) -> None:
        for field in C.FIELDS:
            assert checked(field, TA.block("unresolved", None, [])).decision == "unresolved"
            assert "is not one of" in checked(field, TA.block("clear", None, []))
        # WD1's rule is unchanged: a clear is its answer, an unresolved one only the point's
        assert checked("site_type", TA.block("clear", None, []), R.TWO_FAMILIES).decision == "clear"
        assert "is not one of" in checked(
            "site_type", TA.block("unresolved", None, []), R.TWO_FAMILIES
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://ancientnerds.com/sites/greece/temple-of-hephaestus",
            "https://www.ancientnerds.com/sites/x",
            "https://www.wikiwand.com/en/articles/Temple_of_Hephaestus",
            "https://dbpedia.org/page/Temple_of_Hephaestus",
            "https://web.archive.org/web/2024/https://ancientnerds.com/sites/x",
            "https://web.archive.org/web/2020/ancientnerds.com/sites/greece/temple-of-hephaestus",
            "https://web.archive.org/web/20200101000000id_/www.wikiwand.com/en/Temple",
            "https://archive.ph/AbCd1",
            "https://archive.today/20200101/https://pleiades.stoa.org/places/579885",
            "https://webcache.googleusercontent.com/search?q=cache:pleiades.stoa.org/places/1",
            "https://en-wikipedia-org.translate.goog/wiki/Temple_of_Hephaestus",
            "https://translate.google.com/translate?u=https://pleiades.stoa.org/places/1",
        ],
    )
    def test_the_project_s_own_pages_and_wikipedia_mirrors_are_no_source(self, url: str) -> None:
        quotes = [(url, "The Temple of Hephaestus was built in 449 BC.")]
        problem = checked("period_start", TA.block("keep", "-449", quotes))
        assert "is no source" in problem
        # the same quote from a real source counts, and WD1's rule has no such list
        assert not isinstance(
            checked("period_start", TA.block("keep", "-449", [(WIKI, quotes[0][1])])), str
        )

    def test_a_wayback_copy_counts_as_its_original_with_or_without_a_scheme(self) -> None:
        quotes = [("https://web.archive.org/web/2020/pleiades.stoa.org/places/579885",
                   "The Temple of Hephaestus was built in 449 BC.")]  # fmt: skip
        assert not isinstance(checked("period_start", TA.block("keep", "-449", quotes)), str)
        assert A.family_of(quotes[0][0], ONE) == "stoa.org"
        assert A.family_of(quotes[0][0].replace("pleiades.stoa.org", "https://pleiades.stoa.org"),
                           ONE) == "stoa.org"  # fmt: skip
        # WD1's rule is the acceptance's own reading: a scheme-less copy stays one `archive.org`
        assert A.family_of(quotes[0][0], R.TWO_FAMILIES) == "archive.org"

    def test_a_malformed_text_is_still_not_an_answer(self) -> None:
        with pytest.raises(AnswerError, match="not one JSON object"):
            A.parse("```json\n{}\n```", ["site_type"], ONE)


# ------------------------------------------------------------------------------ the handoff
def wd3_line(site_id: str = A_ID, asked: list[str] | None = None) -> dict[str, Any]:
    line = TH.classified_line(site_id, "Temple of Hephaestus", "Greece", asked or ["period_start"])
    line["fields"]["period_start"]["stored"] = None
    line["fields"]["period_start"]["reason"] = "empty, and the item gives no dated start"
    line["period_name"] = {"stored": None, "bucket_of_stored_start": None}
    line["open"] = {
        field: {"why": "empty", "wd1": EARLIER if field == "period_start" else None}
        for field in line["asked"]
    }
    line["links"] = [
        {"title": "Hephaisteion - Pleiades", "url": "https://pleiades.stoa.org/places/579885",
         "type": "database", "domain": "pleiades.stoa.org", "score": 0.65},
    ]  # fmt: skip
    return line


@pytest.fixture
def run(tmp_path: Path) -> Path:
    out = tmp_path / "run"
    out.mkdir()
    lines = [wd3_line(), wd3_line(B_ID, ["site_type"])]
    lines[1]["name"], lines[1]["country"] = "Nea Paphos", "Cyprus"
    lines[1]["asked"] = []  # asked nothing: no question
    (out / C.CLASSIFIED_FILE).write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    R.write_run(out, ONE)
    return out


def record(handoff: Path, batch: str, label: str, text: str) -> None:
    OH.write_answer(handoff, model=OH.SONNET_MODEL, batch_id=batch, stage="wd3", label=label,
                    text=text, answered_by=batch)  # fmt: skip


ONE_QUOTE = {
    "decision": "replace",
    "value": "-449",
    "quotes": [{"url": WIKI, "quote": "The Temple of Hephaestus was built in 449 BC."}],
    "reasoning": "The English article dates the temple to 449 BC.",
}


class TestTheQuestion:
    def test_it_is_a_pure_function_of_the_line_and_the_rule(self, run: Path) -> None:
        line = HO.read_classified(run)[A_ID]
        prompt = HO.render_prompt(line, ["period_start"], None, ONE)
        assert prompt == HO.render_prompt(line, ["period_start"], None, ONE)
        assert "lane WD3" in prompt and "lane WD1" not in prompt.split("The earlier pass")[0]
        assert "Open because: the field is empty." in prompt
        assert (
            "The earlier pass (lane WD1, two independent source families required) decided clear"
            in prompt
        )
        assert "only Wikipedia dates the temple" in prompt
        assert (
            "[database] Hephaisteion - Pleiades - https://pleiades.stoa.org/places/579885" in prompt
        )
        assert "- stored source_url: " + WIKI in prompt
        assert "One source suffices" in prompt and "answer unresolved" in prompt
        assert "Never use ancientnerds.com" in prompt
        assert "Quotes are checked by machine" in prompt
        for forbidden in ("two independent source families\n", "or clear to leave", "- clear:"):
            assert forbidden not in prompt
        assert "Pages the quote check cannot read" in prompt

    def test_the_question_of_wd1_is_not_changed(self, run: Path) -> None:
        line = HO.read_classified(run)[A_ID]
        wd1 = HO.render_prompt(line, ["period_start"])
        assert wd1 == HO.render_prompt(line, ["period_start"], None, R.TWO_FAMILIES)
        assert "lane WD1" in wd1 and "Open because" not in wd1 and "- clear:" in wd1

    def test_a_site_without_links_says_so_and_a_retry_names_why(self, run: Path) -> None:
        line = HO.read_classified(run)[A_ID]
        line["links"] = []
        prompt = HO.render_prompt(
            line, ["period_start"], {"period_start": "quote not found: x"}, ONE
        )
        assert "pages the site's own page links to: none" in prompt
        assert "An earlier answer to this field did not count: quote not found: x" in prompt
        assert "or answer unresolved when none can be quoted" in prompt

    def test_only_the_first_ten_links_are_listed(self, run: Path) -> None:
        line = HO.read_classified(run)[A_ID]
        line["links"] = [
            {
                "title": f"t{n}",
                "url": f"https://x.example/{n}",
                "type": "article",
                "domain": "x",
                "score": 0.5,
            }
            for n in range(HO.LINKS_SHOWN + 3)
        ]
        prompt = HO.render_prompt(line, ["period_start"], None, ONE)
        assert f"https://x.example/{HO.LINKS_SHOWN - 1}" in prompt
        assert f"https://x.example/{HO.LINKS_SHOWN}\n" not in prompt

    def test_every_open_reason_has_its_words(self) -> None:
        assert set(HO.OPEN_TEXT) == set(POP.WHYS)


class TestTheExportAndTheBrief:
    def test_batches_and_stage_follow_the_run_s_rule(self, run: Path, tmp_path: Path) -> None:
        HO.export(run, tmp_path / "h-r0")
        manifest = OH.manifest(tmp_path / "h-r0")
        assert [(m["batch_id"], m["label"], m["field"]) for m in manifest] == [
            ("wd3-r0-b0001", A_ID, "period_start")
        ]
        prompt = (tmp_path / "h-r0" / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
        assert "lane WD3" in prompt and "### period_start" in prompt

    def test_the_brief_names_the_round_s_model_and_claims_no_other(
        self, run: Path, tmp_path: Path
    ) -> None:
        """The recording command is the only place a model id reaches an answer, so the brief names
        the round's model and nothing else. It used to say "You are Sonnet researcher" and record
        `claude-sonnet-5-5` whatever answered - measured 2026-10-04, that is what put a false
        stamp on eight WD3 answers, and a lane answered by another model would repeat it. The
        default is still the rule's own id, so an unchanged run exports an unchanged brief."""
        HO.export(run, tmp_path / "h-r0")
        text = HO.brief(run, tmp_path / "h-r0", "wd3-r0-b0001")
        assert "You are researcher wd3-r0-b0001 of the WD3 structured-field fill" in text
        assert "--model claude-sonnet-5-5 --text-file" in text and "--stage wd3" in text
        assert "claude-opus-5-5" not in text and 'source is "unresolved"' in text
        assert "Sonnet researcher" not in text
        assert "Never ancientnerds.com" in text
        assert "h-r0-scratch/wd3-r0-b0001/<label>.json" in text

    def test_check_answer_applies_the_rule(self, run: Path, tmp_path: Path) -> None:
        HO.export(run, tmp_path / "h-r0")
        args = (run, tmp_path / "h-r0", "wd3-r0-b0001", A_ID)
        assert HO.check_answer(*args, TA.text(period_start=ONE_QUOTE)) == {
            "ok": True,
            "problems": {},
        }
        cleared = TA.text(period_start=TA.block("clear", None, []))
        assert "is not one of" in HO.check_answer(*args, cleared)["problems"]["period_start"]


class TestTheImport:
    def rounds(self, run: Path, tmp_path: Path, texts: list[str], client: Any) -> None:
        for number, text in enumerate(texts):
            handoff = tmp_path / f"h-r{number}"
            HO.export(run, handoff) if number == 0 else HO.export_reask(run, handoff)
            record(handoff, f"wd3-r{number}-b0001", A_ID, text)
            HO.import_rounds(run, client=client, net=TH.api(tmp_path), pace=0)

    def test_one_found_quote_counts_and_the_model_is_recorded(
        self, run: Path, tmp_path: Path
    ) -> None:
        self.rounds(run, tmp_path, [TA.text(period_start=ONE_QUOTE)], TH.pages_client())
        decision = HO._read_jsonl(run / HO.DECISIONS_FILE)[0]
        assert decision["decision"] == "replace" and decision["via"] == HO.COUNTED
        assert decision["value"] == "-449" and decision["model"] == OH.SONNET_MODEL
        attempt = HO._read_jsonl(run / HO.ATTEMPTS_FILE)[0]
        assert attempt["model"] == OH.SONNET_MODEL and attempt["counted"]

    def test_a_quote_that_is_not_on_its_page_still_does_not_count(
        self, run: Path, tmp_path: Path
    ) -> None:
        invented = {**ONE_QUOTE, "quotes": [{"url": WIKI, "quote": "built by Pericles in 449 BC"}]}
        self.rounds(run, tmp_path, [TA.text(period_start=invented)], TH.pages_client())
        assert HO._read_jsonl(run / HO.DECISIONS_FILE) == []
        assert json.loads((run / HO.REASK_FILE).read_text(encoding="utf-8"))["fields"] == {
            A_ID: ["period_start"]
        }

    def test_an_exhausted_field_is_unresolved_never_cleared(
        self, run: Path, tmp_path: Path
    ) -> None:
        invented = {**ONE_QUOTE, "quotes": [{"url": WIKI, "quote": "built by Pericles in 449 BC"}]}
        bad = TA.text(period_start=invented)
        self.rounds(run, tmp_path, [bad] * (HO.MAX_ROUND + 1), TH.pages_client())
        decision = HO._read_jsonl(run / HO.DECISIONS_FILE)[0]
        assert decision["decision"] == A.UNRESOLVED and decision["via"] == HO.EXHAUSTED
        assert (
            decision["model"] is None and "no counted answer in 3 rounds" in decision["reasoning"]
        )

    def test_pages_the_checker_cannot_read_are_held(self, run: Path, tmp_path: Path) -> None:
        only_register = {**ONE_QUOTE, "quotes": [
            {"url": REGISTER, "quote": "a temple of the 5th century BC"}]}  # fmt: skip
        client = TH.flaky_client({REGISTER: [403]})
        self.rounds(
            run, tmp_path, [TA.text(period_start=only_register)] * (HO.MAX_ROUND + 1), client
        )
        decision = HO._read_jsonl(run / HO.DECISIONS_FILE)[0]
        assert decision["decision"] == HO.HELD and decision["via"] == HO.EXHAUSTED

    def test_a_point_whose_pages_cannot_be_read_is_held_under_wd3_and_unresolved_under_wd1(
        self,
    ) -> None:
        attempt = {"site_id": "s", "field": "coordinates", "round": 2, "counted": False,
                   "unreadable": True, "reason": "fetch failed", "answer": None}  # fmt: skip
        classified = {
            "s": {"name": "n", "fields": {"coordinates": {"status": "MISSING", "stored": "1, 2"}}}
        }
        three = [{**attempt, "round": n} for n in range(3)]
        assert HO._decide(three, classified, [], ONE)[0][0]["decision"] == HO.HELD
        assert HO._decide(three, classified, [], R.TWO_FAMILIES)[0][0]["decision"] == A.UNRESOLVED


class TestThePilot:
    def write(self, run: Path, rows: list[tuple[str, str, str, str]]) -> None:
        run.mkdir(parents=True, exist_ok=True)
        R.write_run(run, ONE)
        sites = {sid: wd3_line(sid) | {"country": country} for sid, country, _, _ in rows}
        (run / C.CLASSIFIED_FILE).write_text(
            "".join(json.dumps(line) + "\n" for line in sites.values()), encoding="utf-8"
        )
        HO._write_jsonl(run / HO.DECISIONS_FILE, [
            {"site_id": sid, "field": "period_start", "decision": d, "via": via}
            for sid, _, d, via in rows
        ])  # fmt: skip
        HO._write_json(run / HO.REASK_FILE, {"after_round": 2, "fields": {}})

    def test_nothing_unsourced_is_a_failure_only_unreadable_pages_are(self, tmp_path: Path) -> None:
        rows = [(f"a{i}", "England", "replace", HO.COUNTED) for i in range(10)]
        rows += [(f"u{i}", "England", A.UNRESOLVED, HO.EXHAUSTED) for i in range(8)]
        rows += [("h0", "England", HO.HELD, HO.EXHAUSTED)]
        self.write(tmp_path / "p", rows)
        report = HO.pilot_report(tmp_path / "p")
        assert report["verdict"] == "PASS"
        assert report["overall"]["unresolved_rate"] == round(8 / 19, 3)
        assert report["gate"]["measure"] == "held_rate"

    def test_an_unresolved_the_agent_answered_outright_is_counted_too(self, tmp_path: Path) -> None:
        rows = [(f"u{i}", "England", A.UNRESOLVED, HO.COUNTED) for i in range(8)]
        rows += [(f"a{i}", "England", "replace", HO.COUNTED) for i in range(2)]
        self.write(tmp_path / "p", rows)
        overall = HO.pilot_report(tmp_path / "p")["overall"]
        assert overall["unresolved"] == 8 and overall["unresolved_rate"] == 0.8
        assert overall["exhausted_unresolved"] == 0

    def test_a_pilot_of_lazy_unresolved_answers_where_a_source_exists_stops(
        self, tmp_path: Path
    ) -> None:
        # every site of `wd3_line` shows a Wikidata item and an English article
        rows = [(f"u{i}", "England", A.UNRESOLVED, HO.COUNTED) for i in range(8)]
        rows += [(f"a{i}", "England", "replace", HO.COUNTED) for i in range(4)]
        self.write(tmp_path / "p", rows)
        report = HO.pilot_report(tmp_path / "p")
        assert report["verdict"] == "STOP"
        assert report["overall"]["hinted_unresolved_rate"] == round(8 / 12, 3)
        assert "answered `unresolved` outright" in report["stopped_by"][0]
        # the same answers on sites without an item or an article are the population, not laziness
        bare = {"country": "England", "qid": None, "enwiki": None}
        HO._write_jsonl(
            tmp_path / "p" / C.CLASSIFIED_FILE, [wd3_line(sid) | bare for sid, *_ in rows]
        )
        assert HO.pilot_report(tmp_path / "p")["verdict"] == "PASS"

    def test_a_checker_that_cannot_read_what_the_agents_cite_stops_the_run(
        self, tmp_path: Path
    ) -> None:
        rows = [(f"a{i}", "England", "replace", HO.COUNTED) for i in range(6)]
        rows += [(f"h{i}", "England", HO.HELD, HO.EXHAUSTED) for i in range(4)]
        self.write(tmp_path / "p", rows)
        report = HO.pilot_report(tmp_path / "p")
        assert report["verdict"] == "STOP"
        assert report["stopped_by"][0].startswith("overall: 4 of 10 fields held as unreadable")


# ------------------------------------------------------------------------------ the population
def wd1(decisions: list[dict[str, Any]], classified: tuple[str, ...] = (SITE,)) -> POP.Wd1:
    return POP.Wd1(
        {(d["site_id"], d["field"]): {"via": "counted", "run": "wd1", "reasoning": "r", **d}
         for d in decisions},
        frozenset(classified),
        frozenset((d["site_id"], d["field"]) for d in decisions if d["decision"] in ("unresolved", "held")),
        ("wd1",),
        ("w",),
    )  # fmt: skip


def stored_row(**over: Any) -> dict[str, Any]:
    row = {"site_id": SITE, "name": "Temple of Hephaestus", "lat_text": "37.9755",
           "lon_text": "23.7215", "period_start": -449, "period_end": None,
           "period_name": "500 BC - 1 AD", "site_type": "Temple",
           "source_url": TH.WIKI, "scope_status": None, **over}  # fmt: skip
    return row


def line_of(**status: str) -> dict[str, Any]:
    return {
        "site_id": SITE,
        "fields": {f: {"status": status.get(f, C.CONFIRMED)} for f in C.FIELDS},
    }


def asked(decisions: list[dict[str, Any]], row: dict[str, Any], **kw: Any) -> dict[str, str]:
    opened, _ = POP.open_fields(line_of(**kw), row, wd1(decisions))
    return {field: info["why"] for field, info in opened.items()}


def d(field: str, decision: str) -> dict[str, Any]:
    return {"site_id": SITE, "field": field, "decision": decision}


def point_write(column: str, value: str, confidence: str = "two_source") -> dict[str, Any]:
    return {"site_id": SITE, "column_name": column, "run_stamp": "2026-09-23_owner-case",
            "confidence": confidence, "new_value": value}  # fmt: skip


class TestTheOpenFields:
    def test_a_field_with_a_sourced_value_is_never_open(self) -> None:
        sourced = [d("coordinates", "keep"), d("period_start", "replace"), d("site_type", "keep")]
        assert asked(sourced, stored_row()) == {}

    def test_an_empty_column_is_open_whatever_wd1_did(self) -> None:
        row = stored_row(period_start=None, site_type="", source_url=None)
        assert asked([d("period_start", "clear")], row) == {
            "period_start": "empty",
            "site_type": "empty",
            "source_url": "empty",
        }

    def test_a_point_wd1_could_not_source_is_open(self) -> None:
        assert asked([d("coordinates", "unresolved")], stored_row()) == {
            "coordinates": "unresolved"
        }
        assert asked([d("coordinates", "held")], stored_row()) == {"coordinates": "unresolved"}

    def test_a_point_a_journalled_lane_sourced_is_not_open_whatever_wd1_decided(self) -> None:
        unresolved = wd1([d("coordinates", "unresolved")])
        for column, written in (("lat", "37.9755"), ("lon", "23.72150")):
            for confidence in ("two_source", "authoritative", "one_source"):
                opened, _ = POP.open_fields(
                    line_of(), stored_row(), unresolved, point_write(column, written, confidence)
                )
                assert opened == {}
        # a write nobody sourced, a point moved since, and a site no lane moved stay open
        for last in (
            point_write("lat", "37.9755", "opus-checked"),
            point_write("lat", "38.1"),
            None,
        ):
            opened, _ = POP.open_fields(line_of(), stored_row(), unresolved, last)
            assert list(opened) == ["coordinates"]

    def test_a_site_wd1_never_saw_is_read_by_the_machine_status(self) -> None:
        opened, _ = POP.open_fields(line_of(coordinates=C.MISSING), stored_row(), wd1([], ()))
        assert {f: i["why"] for f, i in opened.items()} == {"coordinates": "unresolved"}
        confirmed, _ = POP.open_fields(line_of(), stored_row(), wd1([], ()))
        assert confirmed == {}

    def test_a_held_or_cleared_value_that_is_still_stored_has_no_source(self) -> None:
        got = asked(
            [d("site_type", "held"), d("source_url", "clear"), d("period_start", "clear")],
            stored_row(),
        )
        assert got == {"site_type": "held", "source_url": "unsourced", "period_start": "unsourced"}

    def test_a_value_with_a_sourced_decision_that_is_empty_is_listed_and_not_asked(self) -> None:
        opened, wrong = POP.open_fields(
            line_of(), stored_row(period_start=None), wd1([d("period_start", "replace")])
        )
        assert opened == {} and wrong == ["period_start"]

    def test_the_question_shows_what_wd1_decided(self) -> None:
        decision = {**d("period_start", "clear"), "reasoning": "x" * 900}
        opened, _ = POP.open_fields(line_of(), stored_row(period_start=None), wd1([decision]))
        shown = opened["period_start"]["wd1"]
        assert shown["decision"] == "clear" and len(shown["reasoning"]) == POP.WD1_SHOWN_CHARS


class TestWd1sRecords:
    def tree(self, tmp_path: Path, *, accepted: bool = True, held_listed: bool = True,
             deviations: int = 0) -> tuple[list[Path], Path]:  # fmt: skip
        run, waves = tmp_path / "wd1", tmp_path / "wd1" / "write"
        run.mkdir(parents=True)
        HO._write_json(run / "REASK.json", {"after_round": 2, "fields": {}})
        rows = [
            {**d("coordinates", "unresolved"), "via": "counted", "reasoning": "none"},
            {**d("period_start", "keep"), "via": "counted", "reasoning": "two"},
        ]
        HO._write_jsonl(run / "DECISIONS.jsonl", rows)
        HO._write_jsonl(run / C.CLASSIFIED_FILE, [{"site_id": SITE}])
        wave = waves / "2026-09-26b"
        (wave / "s001").mkdir(parents=True)
        HO._write_json(wave / "WAVE.json", {"run": POP._shown(run), "steps": [[SITE]]})
        (wave / "WAVE.sha256").write_text(
            FP._sha256_text(wave / "WAVE.json") + "\n", encoding="utf-8"
        )
        HO._write_jsonl(
            wave / "HELD.jsonl", [{"site_id": SITE, "field": "coordinates"}] * held_listed
        )
        if accepted:
            HO._write_json(wave / "s001" / "ACCEPTED.json", {"deviations": deviations})
        return [run], waves

    def test_decisions_sites_and_held_pairs_are_read(self, tmp_path: Path) -> None:
        records = POP.read_wd1(*self.tree(tmp_path))
        assert set(records.decisions) == {(SITE, "coordinates"), (SITE, "period_start")}
        assert records.classified == {SITE} and records.held == {(SITE, "coordinates")}
        assert records.waves == ("2026-09-26b",)

    def test_a_step_that_is_not_accepted_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(POP.PopulationError, match="not accepted"):
            POP.read_wd1(*self.tree(tmp_path, accepted=False))
        with pytest.raises(POP.PopulationError, match="with deviations"):
            POP.read_wd1(*self.tree(tmp_path / "x", deviations=1))

    def test_a_wd1_run_that_is_not_there_is_refused(self, tmp_path: Path) -> None:
        # WD1's runs are untracked data: they live in the checkout that holds `output/`, and a
        # worktree that has none must be told with `--wd1-dir` instead of a FileNotFoundError
        # traceback from inside the read (measured 2026-10-04, the wd4 build from the worktree).
        runs, waves = self.tree(tmp_path)
        with pytest.raises(POP.PopulationError, match="is not there"):
            POP.read_wd1([tmp_path / "gone", *runs[1:]], waves)

    def test_a_run_whose_held_fields_its_waves_do_not_list_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(POP.PopulationError, match="WD1's records disagree"):
            POP.read_wd1(*self.tree(tmp_path, held_listed=False))

    def test_an_edited_wave_is_refused(self, tmp_path: Path) -> None:
        runs, waves = self.tree(tmp_path)
        HO._write_json(waves / "2026-09-26b" / "WAVE.json", {"run": "x", "steps": []})
        with pytest.raises(POP.PopulationError, match="not the pinned wave"):
            POP.read_wd1(runs, waves)

    def test_a_cell_two_runs_decided_is_refused(self, tmp_path: Path) -> None:
        runs, waves = self.tree(tmp_path)
        with pytest.raises(POP.PopulationError, match="decided by two WD1 runs"):
            POP.read_wd1([*runs, *runs], waves)

    def test_a_run_that_still_waits_for_a_re_ask_is_refused(self, tmp_path: Path) -> None:
        runs, waves = self.tree(tmp_path)
        HO._write_json(runs[0] / "REASK.json", {"after_round": 1, "fields": {SITE: ["site_type"]}})
        with pytest.raises(POP.PopulationError, match="WD1 is not finished"):
            POP.read_wd1(runs, waves)


class TestTheRun:
    fixtures = TestTheRun()

    def prepare(self, tmp_path: Path, **stored: Any) -> tuple[Path, Path]:
        root, out = tmp_path / "h", tmp_path / "o"
        self.fixtures.write_harvest(root)
        self.fixtures.stored(out, **stored)
        links = [{"title": "Pleiades", "url": "https://pleiades.stoa.org/places/1",
                  "type": "database", "domain": "pleiades.stoa.org", "score": 0.7}]  # fmt: skip
        HO._write_jsonl(out / POP.LINKS_FILE, [{"site_id": SITE, "links": links}])
        HO._write_jsonl(out / POP.POINTS_FILE, [])
        return root, out

    def test_a_site_with_an_open_field_gets_exactly_those_fields(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=None, period_name=None)
        counts = POP.build(root, out, table=TABLE, wd1=wd1([d("period_start", "clear")]))
        line = json.loads((out / C.CLASSIFIED_FILE).read_text(encoding="utf-8"))
        assert line["asked"] == ["period_start"]
        assert line["open"]["period_start"]["why"] == "empty"
        assert line["open"]["period_start"]["wd1"]["decision"] == "clear"
        assert line["links"][0]["url"] == "https://pleiades.stoa.org/places/1"
        assert counts["population"]["fields"] == {"period_start": 1}
        assert counts["population"]["why"] == {"period_start:empty": 1}
        assert counts["wd1"]["decisions"] == 1
        assert R.read_rule(out) is ONE

    def test_a_run_is_shown_by_where_it_points(self, tmp_path: Path) -> None:
        """A run's name is what a wave records and what every other tool compares against, so two
        spellings of one directory must be one name. Measured 2026-10-04: `owner_list build
        --final` called with the worktree's junction path answered "1262 field(s) are pending"
        where the real path answered "pending: 0" - the fallback returned the path *as spelled*,
        the waves' accepted steps stayed invisible, and the list looked unfinished."""
        run = tmp_path / "run"
        run.mkdir()
        other = run / ".." / "run"  # the same directory, spelled differently
        for module in (POP, HO, OL):
            assert module._shown(run) == module._shown(other), module.__name__

    def test_a_period_run_pins_its_own_rule(self, tmp_path: Path) -> None:
        # WD4 asks the same question under its own rule (owner decision of 2026-10-04), and a run
        # that pinned WD3's rule could not be asked or written: the stage is in every batch id and
        # in every write lane, so a period run can never write into the finished wd3 run.
        root, out = self.prepare(tmp_path, period_start=None, period_name=None)
        POP.build(root, out, table=TABLE, wd1=wd1([]), stage="wd4")
        assert R.read_rule(out) is R.ONE_FAMILY_PERIOD
        assert json.loads((out / R.RUN_FILE).read_text(encoding="utf-8"))["stage"] == "wd4"

    def test_an_unknown_stage_names_the_known_ones(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=None)
        with pytest.raises(R.RuleError, match="wd7"):
            POP.build(root, out, table=TABLE, wd1=wd1([]), stage="wd7")

    def test_a_site_with_nothing_open_is_not_in_the_run(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path)
        counts = POP.build(root, out, table=TABLE, wd1=wd1([]))
        assert counts["sites"] == 0 and (out / C.CLASSIFIED_FILE).read_text(encoding="utf-8") == ""

    def test_a_retired_site_is_not_in_the_run(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=None, scope_status="retired")
        assert POP.build(root, out, table=TABLE, wd1=wd1([]))["sites"] == 0

    def test_a_run_that_was_asked_is_not_built_again(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=None)
        (out / "ROUNDS.jsonl").write_text("{}\n", encoding="utf-8")
        with pytest.raises(POP.PopulationError, match="a run is built once"):
            POP.build(root, out, table=TABLE, wd1=wd1([]))

    def test_a_run_of_the_other_rule_is_not_rebuilt_as_wd3(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=None)
        (out / R.RUN_FILE).write_text('{"rule": "two-families", "stage": "wd1"}', encoding="utf-8")
        with pytest.raises(R.RuleError, match="pins rule"):
            POP.build(root, out, table=TABLE, wd1=wd1([]))

    def test_the_links_are_refused_when_malformed_or_missing(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=None)
        HO._write_jsonl(out / POP.LINKS_FILE, [{"site_id": SITE, "links": [{"url": "x"}]}])
        with pytest.raises(POP.PopulationError, match="a link carries"):
            POP.build(root, out, table=TABLE, wd1=wd1([]))
        (out / POP.LINKS_FILE).unlink()
        with pytest.raises(POP.PopulationError, match="run `population.py export` first"):
            POP.build(root, out, table=TABLE, wd1=wd1([]))

    def test_a_pilot_and_the_rest_are_disjoint(self, tmp_path: Path) -> None:
        root, pilot = self.prepare(tmp_path, period_start=None)
        POP.build(root, pilot, table=TABLE, wd1=wd1([]), pilot=(1, 7))
        assert json.loads((pilot / R.RUN_FILE).read_text(encoding="utf-8"))["pilot"] == {
            "size": 1,
            "seed": 7,
        }
        rest = tmp_path / "rest"
        for name in (C.STORED_FILE, C.SEEDS_FILE, POP.LINKS_FILE, POP.POINTS_FILE):
            (rest / name).parent.mkdir(exist_ok=True)
            (rest / name).write_bytes((pilot / name).read_bytes())
        counts = POP.build(root, rest, table=TABLE, wd1=wd1([]), without=pilot)
        assert counts["sites"] == 0

    def test_the_export_writes_the_five_files(self, tmp_path: Path) -> None:
        def reader(sql: str) -> list[dict[str, Any]]:
            if "site_content_links" in sql:
                return [{"site_id": SITE, "links": []}]
            if "jsonb_array_elements" in sql:  # who made each value (wd5)
                return [{**point_write("lat", "37.9755"), "rule_made": False, "minimax": False,
                         "withdrawn": False, "note": None}]  # fmt: skip
            if "remediation_change_log" in sql:
                return [point_write("lat", "37.9755")]
            return [stored_row()]

        result = POP.export(tmp_path / "o", reader=reader)
        assert result == {"stored": 1, "links": 1, "points": 1, "made": 1}
        assert (tmp_path / "o" / C.SEEDS_FILE).read_text(encoding="utf-8") == ""
        assert POP.read_links(tmp_path / "o") == {SITE: []}
        assert POP.read_points(tmp_path / "o")[SITE]["new_value"] == "37.9755"

    def test_the_points_are_refused_when_malformed_or_missing(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=None)
        HO._write_jsonl(out / POP.POINTS_FILE, [{"site_id": SITE}])
        with pytest.raises(POP.PopulationError, match="a row carries"):
            POP.build(root, out, table=TABLE, wd1=wd1([]))
        (out / POP.POINTS_FILE).unlink()
        with pytest.raises(POP.PopulationError, match="run `population.py export` first"):
            POP.build(root, out, table=TABLE, wd1=wd1([]))

    def test_a_point_a_journalled_lane_sourced_is_left_out_and_listed(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path)
        HO._write_jsonl(out / POP.POINTS_FILE, [point_write("lon", "23.7215")])
        held = wd1([d("coordinates", "unresolved")])
        counts = POP.build(root, out, table=TABLE, wd1=held)
        assert counts["sites"] == 0
        assert counts["population"]["journal_sourced_points"] == {SITE: "2026-09-23_owner-case"}


# ------------------------------------------------------------------------------ the write plan
def under_wd3(decisions: list[dict[str, Any]], row: dict[str, Any] | None = None,
              open_: dict[str, Any] | None = None, **kw: Any) -> list[Any]:  # fmt: skip
    line = {"open": open_ if open_ is not None else {d["field"]: {} for d in decisions}}
    return FP.site_cells(
        row or TP.live(), line, {d["field"]: d for d in decisions}, kw.pop("journals", {}),
        country_check=TP.AGREES, under=ONE, **kw,
    )  # fmt: skip


def wd3_decision(field: str, verdict: str, value: Any, stored: Any) -> dict[str, Any]:
    return {**TP.decision(field, verdict, value, stored), "model": OH.SONNET_MODEL}


class TestFillOnly:
    def test_an_empty_start_is_filled_with_its_label(self) -> None:
        row = TP.live(period_start=None, period_name=None)
        out = under_wd3([wd3_decision("period_start", "replace", "-2500", None)], row)
        assert TP.written(out) == {
            "period_start": (None, "-2500"),
            "period_name": (None, "3000 - 1500 BC"),
        }
        assert {v.rule for v in out if v.ok} == {"wd3-replace", "wd3-derive-period-name"}
        assert out[0].finding_test_id == "WD3/period_start"
        # every written cell shows who answered - the derived label too, beside its derivation
        for v in out:
            assert [e["model"] for e in v.evidence if "model" in e] == [OH.SONNET_MODEL]

    def test_a_field_the_question_did_not_name_open_is_never_replaced(self) -> None:
        out = under_wd3([wd3_decision("site_type", "replace", "Temple", "City")], open_={})
        assert TP.written(out) == {} and [v.reason for v in out] == ["not-an-open-field"]
        point = under_wd3(
            [wd3_decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")], open_={}
        )
        assert TP.written(point) == {} and point[0].reason == "not-an-open-field"

    def test_a_stored_value_is_never_replaced_only_an_empty_field_is_filled(self) -> None:
        for field, value, stored in (
            ("period_start", "-2500", -700), ("site_type", "Temple", "City"),
            ("source_url", "https://en.wikipedia.org/wiki/Other", "https://x.org/a"),
        ):  # fmt: skip
            row = TP.live(**{field: stored})
            out = under_wd3([wd3_decision(field, "replace", value, stored)], row)
            assert TP.written(out) == {} and [v.reason for v in out] == ["not-empty"]
            assert value in out[0].note and out[0].new_value == value
        # an empty string is empty: filled
        row = TP.live(site_type="")
        out = under_wd3([wd3_decision("site_type", "replace", "Temple", "")], row)
        assert TP.written(out) == {"site_type": ("", "Temple")}
        # a keep on a held value writes nothing and is no refusal
        assert under_wd3([wd3_decision("site_type", "keep", "City", "City")]) == []

    def test_a_clear_is_refused(self) -> None:
        out = under_wd3([wd3_decision("period_start", "clear", None, -700)])
        assert TP.written(out) == {} and [v.reason for v in out] == ["never-clears"]

    def test_an_unresolved_field_of_any_kind_is_listed_and_not_written(self) -> None:
        for field, stored in (("period_start", -700), ("site_type", "City"), ("source_url", "u")):
            out = under_wd3([wd3_decision(field, "unresolved", None, stored)])
            assert TP.written(out) == {} and [v.reason for v in out] == ["field-unresolved"]
        point = under_wd3([wd3_decision("coordinates", "unresolved", None, "35.1, 33.4")])
        assert [v.reason for v in point] == ["coordinates-unresolved"]

    def test_a_label_that_disagrees_with_its_start_is_not_rewritten(self) -> None:
        # WD1's plan repairs such a label on every site of its wave; WD3 fills and nothing else
        assert under_wd3([], TP.live(period_name="1 - 500 AD")) == []
        assert TP.written(TP.cells([], row=TP.live(period_name="1 - 500 AD"))) != {}

    def test_an_unreadable_decision_keeps_its_field_and_a_replace_elsewhere_still_writes(
        self,
    ) -> None:
        decisions = [wd3_decision("site_type", "replace", "Temple", None),
                     wd3_decision("source_url", "unresolved", None, None)]  # fmt: skip
        out = under_wd3(decisions, TP.live(site_type=None, source_url=None))
        assert TP.written(out) == {"site_type": (None, "Temple")}

    def test_a_replaced_point_still_never_crosses_a_border(self) -> None:
        out = FP.site_cells(
            TP.live(), {"open": {"coordinates": {}}},
            {"coordinates": wd3_decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")}, {},
            country_check=TP.ELSEWHERE, under=ONE)  # fmt: skip
        assert TP.written(out) == {} and out[0].reason == "country-changes"

    def test_a_site_with_only_a_keep_has_no_cell(self) -> None:
        assert under_wd3([wd3_decision("period_start", "keep", "-700", -700)]) == []


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(FP, "REPO", tmp_path)
    monkeypatch.setattr(MA, "REPO", tmp_path)
    monkeypatch.setattr(HO, "REPO", tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    R.write_run(run, ONE)
    line = {
        "site_id": TP.SITE,
        "name": "Corycus",
        "period_name": {"stored": None, "bucket_of_stored_start": None},
        "asked": ["site_type"],
        "open": {"site_type": {"why": "empty", "wd1": None}},
    }
    off = {**line, "site_id": TP.OTHER, "asked": [], "open": {},
           "period_name": {"stored": "1 - 500 AD", "bucket_of_stored_start": "1500 - 500 BC"}}  # fmt: skip
    (run / C.CLASSIFIED_FILE).write_text(
        json.dumps(line) + "\n" + json.dumps(off) + "\n", encoding="utf-8"
    )
    HO._write_jsonl(run / HO.DECISIONS_FILE, [wd3_decision("site_type", "replace", "Temple", None)])
    HO._write_json(run / HO.REASK_FILE, {"after_round": 0, "fields": {}})
    return tmp_path


def read_empty(sql: str) -> list[dict[str, Any]]:
    if "remediation_change_log" in sql:
        return []
    return [TP.live(site_type=None)]


def step(wave: str = "2026-10-02a", number: int = 1) -> dict[str, Any]:
    return FP.build_step(wave, number, reader=read_empty, country_check=TP.AGREES,
                         frontend=lambda y: FP.categorize_period(y), stage="wd3")  # fmt: skip


class TestTheWaveAndTheLane:
    def test_the_wave_lives_under_wd3_and_pins_its_rule(self, repo: Path) -> None:
        result = FP.build_wave(repo / "run", "2026-10-02a")
        assert result == {"wave": "2026-10-02a", "sites": 1, "steps": 1, "held": 0}
        record = FP.read_wave("2026-10-02a", "wd3")
        assert record["rule"] == "one-family" and record["stage"] == "wd3"
        assert (
            FP.wave_dir("2026-10-02a", "wd3")
            == repo / "output/remediation/fields/wd3/write/2026-10-02a"
        )
        with pytest.raises(PlanError, match="is missing"):
            FP.read_wave("2026-10-02a")  # no WD1 wave of that label

    def test_a_site_whose_only_flaw_is_its_label_is_no_wave_site(self, repo: Path) -> None:
        # OTHER's label is not the bucket of its start (WD1's wave would repair it): WD3 fills only.
        # OTHER has a decision (a keep), so the plan asks whether its label alone makes it a site
        decisions = HO._read_jsonl(repo / "run" / HO.DECISIONS_FILE)
        keep = {**wd3_decision("site_type", "keep", "City", "City"), "site_id": TP.OTHER}
        HO._write_jsonl(repo / "run" / HO.DECISIONS_FILE, [*decisions, keep])
        FP.build_wave(repo / "run", "2026-10-02a")
        assert FP.read_wave("2026-10-02a", "wd3")["steps"] == [[TP.SITE]]

    def test_a_clear_decision_refuses_the_wave(self, repo: Path) -> None:
        HO._write_jsonl(
            repo / "run" / HO.DECISIONS_FILE, [TP.decision("site_type", "clear", None, "City")]
        )
        with pytest.raises(PlanError, match="never clears"):
            FP.build_wave(repo / "run", "2026-10-02a")

    def test_a_step_is_a_wd3_lane_with_its_own_stamp_and_directory(self, repo: Path) -> None:
        FP.build_wave(repo / "run", "2026-10-02a")
        result = step()
        assert result["cells"] == 1 and result["cells:site_type"] == 1
        out = FP.step_dir("2026-10-02a", 1, "wd3")
        records = MA.load_records(out / "PLAN.jsonl")
        assert [(r.column, r.old_value, r.new_value) for r in records] == [
            ("site_type", None, "Temple")
        ]
        assert out == repo / "output/remediation/fields/wd3/write/2026-10-02a/s001"
        undo = (out / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert "2026-10-02a_fields-wd3-s001-rollback" in undo
        assert "fields-wd1" not in undo

    def test_a_wave_is_not_read_as_the_other_stage(self, repo: Path) -> None:
        FP.build_wave(repo / "run", "2026-10-02a")
        record = FP.read_wave("2026-10-02a", "wd3")
        with pytest.raises(PlanError, match="was planned under one-family"):
            FP.wave_rule(record, "wd1")

    def test_the_hand_off_names_the_wd3_decision(self, repo: Path) -> None:
        HO._write_jsonl(repo / "run" / HO.DECISIONS_FILE, [
            {**wd3_decision("source_url", "replace", "https://en.wikipedia.org/wiki/Corycus", None),
             "value_page": {"lang": "en", "resolved_title": "Corycus", "wikibase_item": "Q9"}}
        ])  # fmt: skip
        line = HO.read_classified(repo / "run")
        line[TP.SITE]["open"] = {"source_url": {"why": "empty", "wd1": None}}
        line[TP.SITE]["asked"] = ["source_url"]
        (repo / "run" / C.CLASSIFIED_FILE).write_text(
            "".join(json.dumps(v) + "\n" for v in line.values()), encoding="utf-8"
        )
        FP.build_wave(repo / "run", "2026-10-02a")
        FP.build_step(
            "2026-10-02a",
            1,
            reader=lambda sql: [] if "change_log" in sql else [TP.live(source_url=None)],
            country_check=TP.AGREES,
            frontend=lambda y: FP.categorize_period(y),
            stage="wd3",
        )
        out = FP.step_dir("2026-10-02a", 1, "wd3")
        MA.emit(MA.load_records(out / "PLAN.jsonl"), out, FP.fields_lane("2026-10-02a", 1, "wd3"),
                plan_path=out / "PLAN.jsonl")  # fmt: skip
        counts = [["planned cells holding their new value", "1"], ["journal rows for the stamp", "1"],
                  ["journal rows matching a planned cell exactly", "1"],
                  ["journal rows of another stamp on a planned cell since", "0"]]  # fmt: skip
        FP.accept("2026-10-02a", 1, read_rows=lambda sql: counts, stage="wd3")
        result = FP.handoff("2026-10-02a", "wd3")
        assert result["source_urls"][0]["wikibase_item"] == "Q9"


class TestTheLaneDefinition:
    def test_the_two_stages_never_share_a_stamp_a_table_or_a_directory(self) -> None:
        one, three = L.fields_lane("2026-10-02", 1, "wd1"), L.fields_lane("2026-10-02", 1, "wd3")
        assert three.name == "fields-wd3-2026-10-02-s001" and three.key_prefix == three.name
        assert three.run_stamp == "2026-10-02_fields-wd3-s001"
        assert three.test_id == "WD3/structured-fields" and three.label == "WD3 field correction"
        assert three.confidence == "one_source" and one.confidence == "two_source"
        assert three.out_dir_name == "fields/wd3/write/2026-10-02/s001"
        assert three.plan_table == "_fields_wd3_plan" and one.plan_table == "_fields_wd1_plan"
        for field in ("run_stamp", "out_dir_name", "plan_table", "test_id", "key_prefix", "label"):
            assert getattr(one, field) != getattr(three, field)
        assert three.cells == one.cells and three.site_invariants == one.site_invariants

    def test_wd4_writes_through_the_same_cells_under_a_lane_of_its_own(self) -> None:
        """Lane WD4 (owner decision 2026-10-04, "eine benannte Periode ist ein Wert") asks WD3's
        question on a stage of its own, so its steps write through the same cells, guards and
        invariants - and under a stamp, a plan table, a directory and a test id of their own, so no
        step of one lane can be mistaken for a step of another. Measured 2026-10-04: `fields_lane`
        knew only wd1 and wd3, so a wd4 wave could not be planned or written at all."""
        three, four = L.fields_lane("2026-10-04a", 1, "wd3"), L.fields_lane("2026-10-04a", 1, "wd4")
        assert four.name == "fields-wd4-2026-10-04a-s001" and four.key_prefix == four.name
        assert four.run_stamp == "2026-10-04a_fields-wd4-s001"
        assert four.test_id == "WD4/structured-fields" and four.label == "WD4 field correction"
        assert four.confidence == "one_source"  # one quote of one family, WD3's discipline
        assert four.out_dir_name == "fields/wd4/write/2026-10-04a/s001"
        assert four.plan_table == "_fields_wd4_plan" and three.plan_table == "_fields_wd3_plan"
        for field in ("run_stamp", "out_dir_name", "plan_table", "test_id", "key_prefix", "label"):
            assert getattr(four, field) != getattr(three, field)
        assert four.cells == three.cells and four.site_invariants == three.site_invariants

    def test_a_lane_name_resolves_to_its_own_stage(self) -> None:
        assert L.resolve_lane("fields-wd3-2026-10-02b-s012") == L.fields_lane(
            "2026-10-02b", 12, "wd3"
        )
        assert L.resolve_lane("fields-wd1-2026-09-27-s001") == L.fields_lane("2026-09-27", 1)
        assert MA.readback_for(L.fields_lane("2026-10-02", 1, "wd3")) == L.fields_readback(
            L.fields_lane("2026-10-02", 1, "wd3")
        )

    @pytest.mark.parametrize(
        "name", ["fields-wd2-2026-10-02-s001", "fields-wd3-2026-10-02-s1", "fields-wd3-x-s001"]
    )
    def test_another_stage_or_a_malformed_name_is_no_lane(self, name: str) -> None:
        with pytest.raises(KeyError):
            L.resolve_lane(name)

    def test_a_step_is_planned_and_rendered_with_wd3_s_notice(self) -> None:
        lane = L.fields_lane("2026-10-02", 1, "wd3")
        records = [MA.ChangeRecord(
            site_id=TP.SITE, site_name="a site", old_value=None, new_value="Temple", rule="wd3-replace",
            condition="x", reason="fields-wd3 (wd3-replace)", evidence=({"source": "t", "quote": "x"},),
            column="site_type")]  # fmt: skip
        sql = MA.render_transaction(records, site_ids={TP.SITE}, lane=lane)
        assert "WD3 field correction:" in sql and "2026-10-02_fields-wd3-s001" in sql
        assert "one_source" in sql

    def test_wd1_s_lane_is_unchanged(self) -> None:
        lane = L.fields_lane("2026-09-27", 1)
        assert lane.run_stamp == "2026-09-27_fields-wd1-s001" and lane.confidence == "two_source"
        assert L.FIELDS_ROOTS["wd1"] == "fields/wd1/write"


# ------------------------------------------------------------------------------ the owner's list
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class TestTheOwnerList:
    S = [f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 7)]

    def build_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rule: R.Rule = ONE
    ) -> tuple[Path, Path]:
        run, waves = tmp_path / "wd3", tmp_path / "wd3" / "write"
        run.mkdir()
        R.write_run(run, rule)
        s = self.S
        spec = [  # site, asked field, decision, open why
            (s[0], "period_start", "replace", "empty"),
            (s[1], "site_type", "unresolved", "empty"),
            (s[2], "source_url", "replace", "empty"),
            (s[3], "coordinates", "held", "unresolved"),
            (s[4], "period_start", None, "empty"),
            (s[5], "site_type", "keep", "held"),
        ]
        lines, decisions = [], []
        for number, (site, field, verdict, why) in enumerate(spec):
            lines.append({"site_id": site, "name": f"Site {number}", "country": "Peru", "asked": [field],
                          "fields": {field: {"stored": None}}, "open": {field: {"why": why, "wd1": None}}})  # fmt: skip
            if verdict:
                decisions.append({"site_id": site, "field": field, "decision": verdict, "asked": 3,
                                  "reasoning": f"{verdict} reasoning", "via": "counted"})  # fmt: skip
        HO._write_jsonl(run / C.CLASSIFIED_FILE, lines)
        HO._write_jsonl(run / "DECISIONS.jsonl", decisions)
        wave = waves / "2026-10-02a"
        step = wave / "s001"
        step.mkdir(parents=True)
        HO._write_json(wave / "WAVE.json", {"run": POP._shown(run), "steps": [[s[0], s[2]]]})
        (wave / "WAVE.sha256").write_text(sha(wave / "WAVE.json") + "\n", encoding="utf-8")
        HO._write_jsonl(step / "PLAN.jsonl", [
            {"site_id": s[0], "column": "period_start", "new_value": "-2500", "rule": "wd3-replace",
             "evidence": []},
            {"site_id": s[0], "column": "period_name", "new_value": "3000 - 1500 BC",
             "rule": "wd3-derive-period-name", "evidence": []},
        ])  # fmt: skip
        HO._write_jsonl(step / "SKIPPED.jsonl", [{"site_id": s[2], "column": "source_url",
                                                  "reason": "moved-since-classification", "note": "holds 'x'"}])  # fmt: skip
        HO._write_json(step / "ACCEPTED.json", {"deviations": 0})
        return run, waves

    def test_what_stays_open_is_listed_with_its_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run, waves = self.build_files(tmp_path, monkeypatch)
        result = OL.build([run], waves)
        states = {(r["site_id"], r["field"]): r["state"] for r in result["rows"]}
        assert states == {
            (self.S[1], "site_type"): "unresolved",
            (self.S[2], "source_url"): "refused",
            (self.S[3], "coordinates"): "held",
            (self.S[4], "period_start"): "pending",
        }
        assert result["counts"]["period_start"] == {"filled": 1, "pending": 1}
        assert result["counts"]["site_type"] == {"sourced": 1, "unresolved": 1}
        refused = next(r for r in result["rows"] if r["state"] == "refused")
        assert refused["reason"] == "moved-since-classification: holds 'x'"

    def test_the_list_is_written_and_final_only_without_pending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run, waves = self.build_files(tmp_path, monkeypatch)
        with pytest.raises(OL.OwnerListError, match="1 field"):
            OL.write([run], waves, tmp_path / "out", final=True)
        summary = OL.write([run], waves, tmp_path / "out", final=False)
        assert summary["listed"] == 4 and summary["pending"] == 1
        text = (tmp_path / "out" / OL.OWNER_MD).read_text(encoding="utf-8")
        assert (
            "no source could be found: 1" in text
            and "Site 1" in text
            and "unresolved reasoning" in text
        )
        assert "a sourced value the write plan refused: 1" in text
        rows = HO._read_jsonl(tmp_path / "out" / OL.OWNER_JSONL)
        assert len(rows) == 4 and rows[0]["field"] == "coordinates"

    def test_a_step_that_is_not_accepted_is_not_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run, waves = self.build_files(tmp_path, monkeypatch)
        (waves / "2026-10-02a" / "s001" / "ACCEPTED.json").unlink()
        counts = OL.build([run], waves)["counts"]
        assert counts["period_start"] == {"pending": 2}

    def test_a_replace_that_a_settled_wave_neither_wrote_nor_refused_is_listed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run, waves = self.build_files(tmp_path, monkeypatch)
        (waves / "2026-10-02a" / "s001" / "SKIPPED.jsonl").write_text("", encoding="utf-8")
        states = {r["site_id"]: r["state"] for r in OL.build([run], waves)["rows"]}
        assert states[self.S[2]] == "no-write"

    def test_only_a_wd3_or_wd4_run_has_an_owner_list(self, tmp_path: Path) -> None:
        run = tmp_path / "wd1"
        run.mkdir()
        with pytest.raises(OL.OwnerListError, match="not a WD3, WD4 or wd5 run"):
            OL.build([run], tmp_path / "none")

    def test_a_period_run_has_an_owner_list_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WD4 asks WD3's question under its own rule (owner decision of 2026-10-04), so its run
        needs the same list: the runbook's step 17 is the tool that says a lane is finished, and it
        answered "is not a WD3 run" for the wd4 run whose last wave was already written."""
        run, waves = self.build_files(tmp_path, monkeypatch, rule=R.ONE_FAMILY_PERIOD)
        result = OL.build([run], waves)
        assert result["counts"]["period_start"] == {"filled": 1, "pending": 1}
        states = {(r["site_id"], r["field"]): r["state"] for r in result["rows"]}
        assert states[(self.S[2], "source_url")] == "refused"


class TestTheRunsRoundsAreItsPopulation:
    """A run classifies every site it can and then puts a part of that population to the model.

    WD4 measured on its own files, 2026-10-04: 2,636 classified sites, 3,551 classified
    questions, and **144 sites / 260 questions** put to the model over three rounds (round 1 and 2
    re-asked 13 of them). Every one of the 260 decisions lies inside the asked set. The other
    2,092 sites are not open questions of that run - they are not its work - and counting them as
    `pending` is what kept `owner_list --final` refusing after the run was finished.

    `ROUNDS.jsonl` is written when a round is exported, before any answer exists, so the list can
    read what the run asked without ever hiding a question it did put.
    """

    S = [f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 5)]

    def build_files(self, tmp_path: Path) -> tuple[Path, Path]:
        run, waves = tmp_path / "wd3", tmp_path / "wd3" / "write"
        run.mkdir()
        R.write_run(run, ONE)
        s = self.S
        spec = [  # site, asked field, decision
            (s[0], "period_start", "replace"),
            (s[1], "site_type", "unresolved"),
            (s[2], "coordinates", None),
            (s[3], "source_url", "keep"),
        ]
        lines, decisions = [], []
        for number, (site, field, verdict) in enumerate(spec):
            lines.append(
                {
                    "site_id": site,
                    "name": f"Site {number}",
                    "country": "Peru",
                    "asked": [field],
                    "fields": {field: {"stored": None}},
                    "open": {field: {"why": "empty", "wd1": None}},
                }
            )
            if verdict:
                decisions.append(
                    {
                        "site_id": site,
                        "field": field,
                        "decision": verdict,
                        "asked": 3,
                        "reasoning": f"{verdict} reasoning",
                        "via": "counted",
                    }
                )
        HO._write_jsonl(run / C.CLASSIFIED_FILE, lines)
        HO._write_jsonl(run / "DECISIONS.jsonl", decisions)
        wave = waves / "2026-10-02a"
        step = wave / "s001"
        step.mkdir(parents=True)
        HO._write_json(wave / "WAVE.json", {"run": POP._shown(run), "steps": [[s[0]]]})
        (wave / "WAVE.sha256").write_text(sha(wave / "WAVE.json") + "\n", encoding="utf-8")
        HO._write_jsonl(step / "PLAN.jsonl", [{"site_id": s[0], "column": "period_start",
                                               "new_value": "-2500", "rule": "wd3-replace",
                                               "evidence": []}])  # fmt: skip
        HO._write_jsonl(step / "SKIPPED.jsonl", [])
        HO._write_json(step / "ACCEPTED.json", {"deviations": 0})
        return run, waves

    def test_a_field_the_run_never_asked_is_not_a_question_of_it(self, tmp_path: Path) -> None:
        run, waves = self.build_files(tmp_path)
        HO._write_jsonl(
            run / OL.ROUNDS_FILE, [{"round": 0, "fields": {self.S[0]: ["period_start"]}}]
        )
        result = OL.build([run], waves)
        assert result["counts"]["period_start"] == {"filled": 1}
        assert result["counts"]["site_type"] == {}, "never asked, so never a question of this run"
        assert result["population"] == {"classified": 4, "asked": 1}

    def test_a_site_asked_in_a_later_round_stays_pending_until_answered(
        self, tmp_path: Path
    ) -> None:
        run, waves = self.build_files(tmp_path)
        HO._write_jsonl(
            run / OL.ROUNDS_FILE,
            [
                {"round": 0, "fields": {self.S[0]: ["period_start"]}},
                {"round": 1, "fields": {self.S[1]: ["site_type"], self.S[2]: ["coordinates"]}},
            ],
        )
        result = OL.build([run], waves)
        assert result["counts"]["period_start"] == {"filled": 1}
        assert result["counts"]["site_type"] == {"unresolved": 1}
        assert result["counts"]["coordinates"] == {"pending": 1}
        assert result["population"] == {"classified": 4, "asked": 3}
        with pytest.raises(OL.OwnerListError, match="1 field"):
            OL.write([run], waves, tmp_path / "out", final=True)

    def test_a_run_whose_questions_were_all_answered_is_final(self, tmp_path: Path) -> None:
        run, waves = self.build_files(tmp_path)
        HO._write_jsonl(
            run / OL.ROUNDS_FILE,
            [
                {"round": 0, "fields": {self.S[0]: ["period_start"], self.S[1]: ["site_type"]}},
                {"round": 1, "fields": {self.S[1]: ["site_type"]}},
            ],
        )
        summary = OL.write([run], waves, tmp_path / "out", final=True)
        assert summary["pending"] == 0 and summary["listed"] == 1
        assert summary["population"] == {"classified": 4, "asked": 2}
        text = (tmp_path / "out" / OL.OWNER_MD).read_text(encoding="utf-8")
        assert "2 of 4 classified questions" in text

    def test_each_run_reads_the_waves_of_its_own_lane(self, tmp_path: Path) -> None:
        """Two runs, two lanes, two wave roots - and one list.

        `--waves` named a single directory, so a list over WD3 and WD4 read WD3's waves and saw
        WD4's as never written: 65 questions that were decided *and* written came out as `pending`
        (measured 2026-10-04, after the rounds cut the population to 3,823 of 7,114). Each run
        says which lane it is (its rule's stage) and its waves live under that lane, so the list
        reads `fields/<stage>/write` per run; `--waves` stays as the override it was.
        """
        base = tmp_path / "output" / "remediation"
        monkey = pytest.MonkeyPatch()
        monkey.setattr(OL, "waves_root", lambda stage: base / "fields" / stage / "write")
        try:
            runs = []
            for stage, rule in (("wd3", ONE), ("wd4", R.ONE_FAMILY_PERIOD)):
                run = base / "fields" / stage
                (run / "write").mkdir(parents=True)
                R.write_run(run, rule)
                site = f"00000000-0000-4000-8000-00000000000{len(runs) + 1}"
                HO._write_jsonl(
                    run / C.CLASSIFIED_FILE,
                    [
                        {
                            "site_id": site,
                            "name": f"{stage} site",
                            "country": "Peru",
                            "asked": ["period_start"],
                            "fields": {"period_start": {"stored": None}},
                            "open": {"period_start": {"why": "empty", "wd1": None}},
                        }
                    ],
                )
                HO._write_jsonl(
                    run / "DECISIONS.jsonl",
                    [
                        {
                            "site_id": site,
                            "field": "period_start",
                            "decision": "replace",
                            "asked": 1,
                            "reasoning": "a source says so",
                            "via": "counted",
                        }
                    ],
                )
                HO._write_jsonl(
                    run / OL.ROUNDS_FILE, [{"round": 0, "fields": {site: ["period_start"]}}]
                )
                wave = run / "write" / "2026-10-04"
                step = wave / "s001"
                step.mkdir(parents=True)
                HO._write_json(
                    wave / "WAVE.json",
                    {"run": POP._shown(run), "steps": [[site]], "stage": stage, "rule": rule.name},
                )
                (wave / "WAVE.sha256").write_text(sha(wave / "WAVE.json") + "\n", encoding="utf-8")
                HO._write_jsonl(
                    step / "PLAN.jsonl",
                    [
                        {
                            "site_id": site,
                            "column": "period_start",
                            "new_value": "-2500",
                            "rule": "wd3-replace",
                            "evidence": [],
                        },
                        {
                            "site_id": site,
                            "column": "period_name",
                            "new_value": "3000 - 1500 BC",
                            "rule": "wd3-derive-period-name",
                            "evidence": [],
                        },
                    ],
                )
                HO._write_jsonl(step / "SKIPPED.jsonl", [])
                HO._write_json(step / "ACCEPTED.json", {"deviations": 0})
                runs.append(run)
            summary = OL.write(runs, None, tmp_path / "out", final=True)
        finally:
            monkey.undo()
        assert summary["pending"] == 0 and summary["listed"] == 0
        assert summary["population"] == {"classified": 2, "asked": 2}


# ------------------------------------------------------------------------------ the scripts
class TestTheScripts:
    def test_the_wave_script_drives_wd3_lanes_only(self) -> None:
        text = (REPO / "output/remediation/orchestration/wd3_wave.sh").read_text(encoding="utf-8")
        assert "fields-wd3-$W-s$S" in text and "fields/wd3/write" in text
        assert text.count("--stage wd3") >= 4  # step, nothing-to-write accept, accept, status
        assert "fields-wd1" not in text and "fields/wd1" not in text
        for mode in ("emit", "verify", "rehearse", "probe-guards", "apply", "rehearse-rollback"):
            assert mode in text
        assert "emit verify rehearse probe-guards apply verify rehearse-rollback" in text

    def test_the_agents_of_the_pool_are_sonnet_and_record_their_model(self) -> None:
        text = (REPO / "output/remediation/orchestration/wd3-handoff-pool.js").read_text(
            encoding="utf-8"
        )
        assert "model: 'sonnet'" in text and "--model claude-sonnet-5-5" in text
        assert "WD1" not in text.replace("WD1's", "")
