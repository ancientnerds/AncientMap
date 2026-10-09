"""Lane wd5, the operator's side of the round (`handoff.py`, `wiki.py`): what a run needs besides its
questions - the original import's claims, the cached Wikipedia text the agents read first, the
decisions carried in from the refused points, and the role every answer must be recorded under.

Offline: the quoted pages come from an `httpx.MockTransport`, the cache and the runs from
temporary directories.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from fields import carry as CA  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import rule as R  # noqa: E402
from fields import wiki as W  # noqa: E402

from tests.remediation import test_fields_handoff as TH  # noqa: E402
from tests.remediation import test_fields_wd3 as TW  # noqa: E402

A_ID, B_ID = TH.A_ID, TH.B_ID
REPLACE = {
    "decision": "replace",
    "value": "-449",
    "quotes": [{"url": TH.WIKI, "quote": "The Temple of Hephaestus was built in 449 BC."}],
    "reasoning": "The article dates the temple to 449 BC.",
}
STAGE = R.RECHECK.stage


def wd5_run(tmp_path: Path, *lines: dict[str, Any], rule: R.Rule = R.RECHECK) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    HO._write_jsonl(run / C.CLASSIFIED_FILE, lines or [TW.wd3_line()])
    R.write_run(run, rule)
    return run


def record(handoff: Path, label: str, text: str, *, by: str = "field_researcher:wd5-r0-b0001",
           model: str = OH.SONNET_MODEL, batch: str = "wd5-r0-b0001") -> None:  # fmt: skip
    OH.write_answer(handoff, batch_id=batch, stage=STAGE, label=label, text=text,
                    answered_by=by, model=model)  # fmt: skip


def answer(**fields: Any) -> str:
    return json.dumps({"fields": fields})


def hint_row(site: str = A_ID, **over: str | None) -> dict[str, Any]:
    row = {"site_id": site, "name": "Temple", "source_url": TH.WIKI, "match": "url",
           "title": "Temple of Hephaestus", "year": "", "period": "1 - 500 AD",
           "category": "Temple"}  # fmt: skip
    return {**row, **over}


class TestTheHintsOfTheOriginalImport:
    def test_they_are_copied_byte_for_byte_and_the_coverage_is_counted(
        self, tmp_path: Path
    ) -> None:
        run = wd5_run(tmp_path, TW.wd3_line(), TW.wd3_line(B_ID))
        source = tmp_path / "ORIGINAL_PERIODS.jsonl"
        HO._write_jsonl(source, [hint_row(), hint_row("someone-else")])
        result = HO.copy_hints(run, source)
        assert result == {"hints": 2, "period_questions": 2, "period_questions_with_a_hint": 1}
        assert (run / HO.HINTS_FILE).read_bytes() == source.read_bytes()
        assert set(HO.read_hints(run)) == {A_ID, "someone-else"}

    def test_the_question_then_shows_the_claim(self, tmp_path: Path) -> None:
        run = wd5_run(tmp_path)
        source = tmp_path / "h.jsonl"
        HO._write_jsonl(source, [hint_row(year="800 BC")])
        HO.copy_hints(run, source)
        HO.export(run, tmp_path / "h-r0")
        prompt = (tmp_path / "h-r0" / OH.manifest(tmp_path / "h-r0")[0]["prompt_path"]).read_text(
            encoding="utf-8"
        )
        assert 'Year "800 BC", Period "1 - 500 AD"' in prompt

    def test_a_run_whose_rule_shows_no_hint_takes_none(self, tmp_path: Path) -> None:
        run = wd5_run(tmp_path, rule=R.ONE_FAMILY)
        source = tmp_path / "h.jsonl"
        HO._write_jsonl(source, [hint_row()])
        with pytest.raises(HO.HandoffStepError, match="shows no original-import claim"):
            HO.copy_hints(run, source)
        assert not (run / HO.HINTS_FILE).exists()

    def test_a_run_copies_once_and_never_after_its_first_question(self, tmp_path: Path) -> None:
        run = wd5_run(tmp_path)
        source = tmp_path / "h.jsonl"
        HO._write_jsonl(source, [hint_row()])
        HO.copy_hints(run, source)
        with pytest.raises(HO.HandoffStepError, match="copied once"):
            HO.copy_hints(run, source)
        late = tmp_path / "late"
        late.mkdir()
        run2 = wd5_run(late)
        HO.export(run2, late / "h-r0")
        with pytest.raises(HO.HandoffStepError, match="exported a round"):
            HO.copy_hints(run2, source)

    def test_a_source_that_is_no_hint_file_is_refused_before_anything_is_copied(
        self, tmp_path: Path
    ) -> None:
        run = wd5_run(tmp_path)
        source = tmp_path / "h.jsonl"
        HO._write_jsonl(source, [{"site_id": A_ID}])
        with pytest.raises(HO.HandoffStepError, match="not .*site_id"):
            HO.copy_hints(run, source)
        assert not (run / HO.HINTS_FILE).exists()


# ------------------------------------------------------------------------------ the cache
def a_cache(root: Path) -> Path:
    (root / "en").mkdir(parents=True)
    page = {"lang": "en", "title": "Temple of Hephaestus", "resolved_title": "Temple of Hephaestus",
            "revid": 77, "text": "The Temple of Hephaestus was built in 449 BC."}  # fmt: skip
    (root / "en" / "abc.json").write_text(json.dumps(page), encoding="utf-8")
    index = [{"site_id": A_ID, "lang": "en", "title": "Temple of Hephaestus",
              "file": "en\\abc.json"}]  # fmt: skip
    (root / W.INDEX_FILE).write_text(json.dumps(index[0]) + "\n", encoding="utf-8")
    return root


class TestTheCachedWikipedia:
    def test_a_sites_cached_article_is_printed_with_its_own_url(self, tmp_path: Path) -> None:
        pages = W.WikiCache(a_cache(tmp_path / "wc")).pages(A_ID)
        text = W.render(A_ID, pages)
        assert "# en.wikipedia.org: Temple of Hephaestus (revision 77)" in text
        assert "URL: https://en.wikipedia.org/wiki/Temple_of_Hephaestus" in text
        assert "was built in 449 BC." in text

    def test_the_url_is_percent_encoded_as_the_address_bar_copies_it(self) -> None:
        page = {"lang": "de", "title": "Göbekli Tepe", "resolved_title": "Göbekli Tepe"}
        assert W.article_url(page) == "https://de.wikipedia.org/wiki/G%C3%B6bekli_Tepe"

    def test_a_site_the_cache_never_held_has_no_page_and_the_agent_is_told(
        self, tmp_path: Path
    ) -> None:
        cache = W.WikiCache(a_cache(tmp_path / "wc"))
        assert cache.pages(B_ID) == []
        assert "No cached Wikipedia page" in W.render(B_ID, [])

    def test_a_missing_article_is_said_to_be_missing_not_empty(self) -> None:
        page = {"lang": "en", "title": "Nowhere", "missing": True}
        assert "(the article does not exist)" in W.render(A_ID, [page])

    def test_an_index_line_whose_file_is_not_on_disk_is_refused(self, tmp_path: Path) -> None:
        root = a_cache(tmp_path / "wc")
        (root / "en" / "abc.json").unlink()
        with pytest.raises(W.WikiCacheError, match="not on disk"):
            W.WikiCache(root).pages(A_ID)

    def test_a_malformed_index_line_is_refused(self, tmp_path: Path) -> None:
        root = a_cache(tmp_path / "wc")
        (root / W.INDEX_FILE).write_text('{"site_id": "x"}\n', encoding="utf-8")
        with pytest.raises(W.WikiCacheError, match="a line carries"):
            W.WikiCache(root)

    def test_the_command_prints_the_article(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = a_cache(tmp_path / "wc")
        assert HO.main(["wiki-text", "--label", A_ID, "--cache", str(root)]) == 0
        assert "was built in 449 BC." in capsys.readouterr().out

    def test_the_command_refuses_where_there_is_no_cache(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert HO.main(["wiki-text", "--label", A_ID, "--cache", str(tmp_path / "none")]) == 1
        assert "cache is not built" in capsys.readouterr().err


class TestTheBrief:
    def test_it_sends_the_agent_to_the_cache_and_records_under_the_role(
        self, tmp_path: Path
    ) -> None:
        run = wd5_run(tmp_path)
        HO.export(run, tmp_path / "h-r0")
        text = HO.brief(run, tmp_path / "h-r0", "wd5-r0-b0001")
        assert "handoff.py wiki-text --label <label>" in text
        assert "--model claude-sonnet-5-5 --role field_researcher" in text
        assert "403 and 429 are a throttle, never a finding" in text

    def test_the_older_lanes_briefs_name_no_role_and_no_cache(self, tmp_path: Path) -> None:
        run = wd5_run(tmp_path, rule=R.ONE_FAMILY_PERIOD)
        HO.export(run, tmp_path / "h-r0")
        text = HO.brief(run, tmp_path / "h-r0", "wd4-r0-b0001")
        assert "--role" not in text and "wiki-text" not in text
        assert "--model claude-sonnet-5-5 --text-file" in text


# ------------------------------------------------------------------------------ carried cells
def carry_into(run: Path, tmp_path: Path, site: str = A_ID, field: str = "coordinates") -> None:
    """A CARRIED.jsonl and its pin, as `carry-points` writes them, for one cell."""
    row = {
        "site_id": site, "name": "Temple of Hephaestus", "field": field, "status": "MISSING",
        "stored": "37.9755, 23.7215", "asked": 1, "decision": "replace", "value": "37.9756, 23.7214",
        "via": CA.CARRIED, "round": 1, "counted_rounds": [1], "answered_by": "wd1-r1-b0004",
        "model": None, "reasoning": "r", "value_page": None,
        "quotes": [{"source": TH.WIKI, "quote": "37.9755°N 23.7215°E", "outcome": "found"}],
        "origin": {"run": "fields/wd1", "via": "counted"},
    }  # fmt: skip
    HO._write_jsonl(run / CA.CARRIED_FILE, [row])
    meta = {"carried_sha256": CA._sha256_text(run / CA.CARRIED_FILE)}
    (run / CA.CARRIED_META).write_text(json.dumps(meta), encoding="utf-8")


def two_field_run(tmp_path: Path) -> Path:
    line = TW.wd3_line(asked=["coordinates", "period_start"])
    line["open"]["coordinates"] = {"why": "unsourced-point", "wd1": None}
    return wd5_run(tmp_path, line)


class TestCarriedCells:
    def test_a_carried_cell_is_not_asked_and_its_siblings_are(self, tmp_path: Path) -> None:
        run = two_field_run(tmp_path)
        carry_into(run, tmp_path)
        result = HO.export(run, tmp_path / "h-r0")
        assert result["sites"] == 1 and result["fields"] == 1
        [line] = OH.manifest(tmp_path / "h-r0")
        assert line["field"] == "period_start"
        assert HO.read_rounds(run)[0]["fields"] == {A_ID: ["period_start"]}

    def test_a_site_whose_only_open_field_is_carried_asks_nothing(self, tmp_path: Path) -> None:
        line = TW.wd3_line(asked=["coordinates"])
        line["open"] = {"coordinates": {"why": "unsourced-point", "wd1": None}}
        run = wd5_run(tmp_path, line, TW.wd3_line(B_ID))
        carry_into(run, tmp_path)
        result = HO.export(run, tmp_path / "h-r0")
        assert result["sites"] == 1
        assert [m["label"] for m in OH.manifest(tmp_path / "h-r0")] == [B_ID]

    def test_the_import_writes_the_carried_decision_beside_the_answered_ones(
        self, tmp_path: Path
    ) -> None:
        run = two_field_run(tmp_path)
        carry_into(run, tmp_path)
        HO.export(run, tmp_path / "h-r0")
        record(tmp_path / "h-r0", A_ID, answer(period_start=REPLACE))
        result = HO.import_rounds(run, client=TH.pages_client(), net=TH.api(tmp_path), pace=0)
        assert result["carried"] == 1 and result["counted"] == 1
        decisions = HO._read_jsonl(run / HO.DECISIONS_FILE)
        assert [(d["field"], d["via"]) for d in decisions] == [
            ("coordinates", "carried"),
            ("period_start", "counted"),
        ]
        assert HO.status(run)["decisions"] == {
            "coordinates:replace:carried": 1,
            "period_start:replace:counted": 1,
        }

    def test_a_carried_cell_that_was_asked_as_well_is_refused(self, tmp_path: Path) -> None:
        run = two_field_run(tmp_path)
        HO.export(run, tmp_path / "h-r0")  # both fields are asked
        carry_into(run, tmp_path)  # and now the point is carried too
        both = answer(
            period_start=REPLACE,
            coordinates={"decision": "unresolved", "value": None, "quotes": [], "reasoning": "x"},
        )
        record(tmp_path / "h-r0", A_ID, both)
        with pytest.raises(HO.HandoffStepError, match="asked as well"):
            HO.import_rounds(run, client=TH.pages_client(), net=TH.api(tmp_path), pace=0)
        assert not (run / HO.DECISIONS_FILE).exists()

    def test_an_edited_carried_file_is_refused_at_the_export(self, tmp_path: Path) -> None:
        run = two_field_run(tmp_path)
        carry_into(run, tmp_path)
        (run / CA.CARRIED_FILE).write_text("{}\n", encoding="utf-8")
        with pytest.raises(CA.CarryError, match="was edited"):
            HO.export(run, tmp_path / "h-r0")

    def test_the_owner_list_counts_a_carried_cell_among_the_cells_the_run_asked(
        self, tmp_path: Path
    ) -> None:
        from fields import owner_list as OL

        run = two_field_run(tmp_path)
        carry_into(run, tmp_path)
        HO.export(run, tmp_path / "h-r0")
        assert OL.asked_by_rounds(run) == {(A_ID, "coordinates"), (A_ID, "period_start")}
        quiet = tmp_path / "quiet"
        quiet.mkdir()
        assert OL.asked_by_rounds(quiet) is None  # a run without rounds is its whole classification


# ------------------------------------------------------------------------------ the role
class TestTheRoleOfTheAnswers:
    def imported(self, tmp_path: Path, **given: Any) -> None:
        run = wd5_run(tmp_path)
        HO.export(run, tmp_path / "h-r0")
        record(tmp_path / "h-r0", A_ID, answer(period_start=REPLACE), **given)
        HO.import_rounds(run, client=TH.pages_client(), net=TH.api(tmp_path), pace=0)

    def test_an_answer_recorded_under_the_role_with_its_model_counts(self, tmp_path: Path) -> None:
        self.imported(tmp_path)
        [attempt] = HO._read_jsonl(tmp_path / "run" / HO.ATTEMPTS_FILE)
        assert attempt["counted"] and attempt["answered_by"].startswith("field_researcher:")

    def test_an_answer_recorded_without_a_role_is_refused_by_name(self, tmp_path: Path) -> None:
        with pytest.raises(HO.HandoffStepError, match="names no field_researcher role"):
            self.imported(tmp_path, by="wd5-r0-b0001")
        assert not (tmp_path / "run" / HO.DECISIONS_FILE).exists()

    def test_an_answer_of_another_role_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(HO.HandoffStepError, match="names no field_researcher role"):
            self.imported(tmp_path, by="adversarial:wd5-r0-b0001")

    def test_an_answer_whose_stamp_is_not_the_roles_model_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(HO.HandoffStepError, match="registered to claude-sonnet-5-5"):
            self.imported(tmp_path, model=OH.HAIKU_MODEL)

    def test_the_older_rules_take_the_answers_they_always_took(self, tmp_path: Path) -> None:
        run = wd5_run(tmp_path, rule=R.ONE_FAMILY_PERIOD)
        HO.export(run, tmp_path / "h-r0")
        # an answer recorded under a role is as good for a rule that has none as one without
        OH.write_answer(tmp_path / "h-r0", batch_id="wd4-r0-b0001", stage="wd4", label=A_ID,
                        text=answer(period_start=REPLACE), answered_by="field_researcher:b",
                        model=OH.SONNET_MODEL)  # fmt: skip
        result = HO.import_rounds(run, client=TH.pages_client(), net=TH.api(tmp_path), pace=0)
        assert result["counted"] == 1


class TestTheSelectedReCheck:
    def test_an_import_cannot_change_the_decisions_the_check_was_asked_of(
        self, tmp_path: Path
    ) -> None:
        run = wd5_run(tmp_path)
        HO.export(run, tmp_path / "h-r0")
        record(tmp_path / "h-r0", A_ID, answer(period_start=REPLACE))
        (run / HO.ADV_SELECTED).parent.mkdir()
        (run / HO.ADV_SELECTED).write_text("{}", encoding="utf-8")
        with pytest.raises(HO.HandoffStepError, match="drop its verdicts"):
            HO.import_rounds(run, client=TH.pages_client(), net=TH.api(tmp_path), pace=0)


class TestTheWaveScript:
    SCRIPT = REPO / "scripts" / "remediation" / "wd5_wave.sh"

    def test_it_runs_the_wd5_lane_and_no_other(self) -> None:
        text = self.SCRIPT.read_text(encoding="utf-8")
        assert "fields-wd5-$W-s$S" in text and "output/remediation/fields/wd5/write" in text
        commands = re.findall(r"plan\.py (step|accept|status|wave)([^\n]*)", text)
        assert {name for name, _ in commands} == {"step", "accept", "status", "wave"}
        assert all("--stage wd5" in rest for name, rest in commands if name != "wave")
        assert "wd3" not in text.replace("wd3_wave.sh", "")
        for mode in ("emit", "verify", "rehearse", "probe-guards", "apply", "rehearse-rollback"):
            assert mode in text

    def test_it_is_valid_shell_with_unix_line_endings(self) -> None:
        assert b"\r\n" not in self.SCRIPT.read_bytes()
        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("no bash on this machine")
        done = subprocess.run([bash, "-n", str(self.SCRIPT)], capture_output=True, check=False)
        assert done.returncode == 0, done.stderr.decode()
