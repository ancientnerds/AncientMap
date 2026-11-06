"""D70: the dating extractor (`scripts/remediation/fields/dating.py`) and its sources.

DB-less and offline. The sentences are the scout's (D70_EXTRACTOR_DESIGN.md section 2, the 20-site
feasibility sample of 2026-11-05) or shaped like them: every trap the design names has a test - a
number with a unit, the abbreviations that break a naive splitter, a park's founding in P571, "pre-
Inca", a hedge, a collective entity, a date that belongs to a sub-site - and so do the decision
rule (D70, O1: the earliest start of the highest tier, the range in the evidence; the D58 window),
the run's files, the quote check, the cells shown before a wave (D71, O3), the harvest's new
sources and the lane's wiring (rule, population, plan, lane).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from census.fetch import Fetcher  # noqa: E402
from fields import dating as X  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402
from mechanical import lane as LANE  # noqa: E402

SITE = "11111111-0000-4000-8000-000000000001"
#: The switches as DEV round 1 shipped them (2026-11-06): tiers 1 and 2, no range written.
SHIPPED = {"tiers": [1, 2], "write_ranges": False}
AS_SHIPPED = json.loads(json.dumps(X.CONFIG))  # read before any test patches it


@pytest.fixture(autouse=True)
def every_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """The readers and the decision are tested with every tier on; the shipped switches have a
    test of their own (`TestDevRoundOne.test_the_shipped_switches`)."""
    monkeypatch.setitem(X.CONFIG, "tiers", [1, 2, 3, 4, 5, 6])


def cands(
    sentence: str,
    names: list[str],
    *,
    lang: str = "en",
    context: bool = False,
    doc: bool = False,
) -> X.Found:
    return X.sentence_candidates(
        sentence, lang=lang, forms=X.name_forms(names), context_named=context, tier=2,
        source="enwiki prose", url="https://en.wikipedia.org/w/index.php?title=T&oldid=1",
        revision=1, sentence_id="s", anchored_doc=doc,
    )  # fmt: skip


def starts(found: X.Found) -> list[tuple[str, int]]:
    return [(c.kind, c.start) for c in found.candidates]


def reasons(found: X.Found) -> list[str]:
    return [n.reason for n in found.notes]


# ------------------------------------------------------------------------------ the readers
class TestNumbersThatAreNoYears:
    @pytest.mark.parametrize(
        "sentence",
        [
            "Moel y Gest rises to 263 m above the sea and was built over a long time.",
            "Winsford had 1,200 ewes and 300 cows and was settled by farmers.",
            "The walls of Cranon were built 150 metres long.",
            "Cranon lay 100 stadia from Larissa and was founded by the Thessalians.",
            "Alpha was built with 1,500 tonnes of stone.",
            # a date preposition before the number, a unit after it: a measure, not a year
            "Alpha was built in 400 m of solid rock.",
            "Alpha was settled by 1200 people.",
        ],
    )
    def test_a_number_with_a_unit_or_without_a_marker_is_no_start(self, sentence: str) -> None:
        names = ["Moel y Gest", "Winsford", "Cranon", "Alpha"]
        assert starts(cands(sentence, names)) == []

    def test_an_unmarked_year_needs_a_date_preposition(self) -> None:
        assert starts(cands("Alpha was built in 1200 by the Chimu.", ["Alpha"])) == [("year", 1200)]
        assert starts(cands("Alpha was built with 1200 stones.", ["Alpha"])) == []

    def test_a_start_after_1500_is_dropped(self) -> None:
        assert starts(cands("Alpha was built in 1820 by the parish.", ["Alpha"])) == []
        assert starts(cands("Alpha was founded in AD 1550.", ["Alpha"])) == []


class TestTheSentenceSplitter:
    def test_the_abbreviations_of_the_design_do_not_break_a_sentence(self) -> None:
        text = (
            "Alabanda was ruled by the tyrant Aridolis (r. 486–465 BC). Later it grew. "
            "Die Stadt entstand im 5. Jahrhundert v. Chr. und wuchs. "
            "Naselje je osnovano 400. pr. Kr. na rijeci. Founded c. 300 B.C. The city grew."
        )
        assert X.split_sentences(text) == [
            "Alabanda was ruled by the tyrant Aridolis (r. 486–465 BC).",
            "Later it grew.",
            "Die Stadt entstand im 5. Jahrhundert v. Chr. und wuchs.",
            "Naselje je osnovano 400. pr. Kr. na rijeci.",
            "Founded c. 300 B.C.",
            "The city grew.",
        ]

    def test_an_era_marker_ends_a_sentence(self) -> None:
        assert X.split_sentences("Um 500 v. Chr. Die Stadt wuchs.") == [
            "Um 500 v. Chr.",
            "Die Stadt wuchs.",
        ]


class TestCuesAndVetoes:
    def test_the_nearest_cue_decides_whose_date_it_is(self) -> None:
        found = cands("It was founded in 700 BC and destroyed in 200 BC.", ["Alpha"], context=True)
        assert starts(found) == [("year", -700)]

    def test_an_event_date_is_no_start(self) -> None:
        assert starts(cands("Alpha was excavated in the 5th century BC layers.", ["Alpha"])) == []
        assert starts(cands("Alabanda was ruled by Aridolis (r. 486–465 BC).", ["Alabanda"])) == []
        assert starts(cands("Cranon is first mentioned in 648 BCE.", ["Cranon"])) == []

    def test_a_refounding_is_an_event(self) -> None:
        found = cands("Sisak was settled in the 4th century BC and refounded in AD 35.", ["Sisak"])
        assert starts(found) == [("century", -400)]

    @pytest.mark.parametrize(
        ("sentence", "lang"),
        [
            ("Moel y Gest's hillfort shows some resemblance to Early Iron Age forts.", "en"),
            ("Waqrapukara is said to be an Inca sanctuary built in 1450.", "en"),
            ("Alpha was possibly founded in the 3rd century BC.", "en"),
            ("Alpha wurde wahrscheinlich im 3. Jahrhundert v. Chr. gegründet.", "de"),
            ("Alpha a peut-être été fondée au IIIe siècle av. J.-C.", "fr"),
        ],
    )
    def test_a_hedge_abstains_rather_than_lowers(self, sentence: str, lang: str) -> None:
        found = cands(sentence, ["Moel y Gest", "Waqrapukara", "Alpha"], lang=lang)
        assert starts(found) == [] and reasons(found) == ["hedged"]

    def test_a_range_in_one_statement_is_one_start(self) -> None:
        found = cands("Palazzo a Mare was built by Augustus, dating from about 27 to 37 A.D.",
                      ["Palazzo a Mare"])  # fmt: skip
        assert starts(found) == [("year", 27)]
        assert found.candidates[0].hi == 37

    def test_two_starts_of_one_sentence_in_two_buckets_abstain(self) -> None:
        found = cands("Alpha was settled in the Neolithic, around 5000 BC, and founded as a "
                      "colony in 600 BC.", ["Alpha"])  # fmt: skip
        assert starts(found) == [] and reasons(found) == [X.TWO_STARTS]


class TestTheAnchor:
    def test_a_sentence_that_does_not_name_the_site_is_not_its(self) -> None:
        found = cands("The site was built in the 2nd century BC.", ["Alpha"])
        assert starts(found) == [] and reasons(found) == ["no-anchor"]

    def test_a_deictic_counts_in_a_paragraph_that_named_the_site(self) -> None:
        assert starts(cands("The site was built in the 2nd century BC.", ["Alpha"],
                            context=True)) == [("century", -200)]  # fmt: skip

    def test_a_sub_site_s_date_is_not_the_site_s(self) -> None:
        # Adullam Grove Nature Reserve: "10th century BCE" belongs to Horvat Midras
        found = cands("Horvat Midras dates to the 10th century BCE.",
                      ["Adullam Grove Nature Reserve"], context=True)  # fmt: skip
        assert starts(found) == []
        # Hundersingen: the Heuneburg nearby, "600 to 400 B.C."
        found = cands("The Heuneburg, a hillfort near Hundersingen, was occupied from 600 to "
                      "400 B.C.", ["Hundersingen"])  # fmt: skip
        assert starts(found) == [] and reasons(found) == ["other-subject: Heuneburg"]

    def test_a_sentence_s_first_capital_alone_is_no_other_subject(self) -> None:
        found = cands("Excavations showed that Tell Foo was founded in 3000 BC.", ["Tell Foo"])
        assert starts(found) == [("year", -3000)]

    def test_other_language_prose_reads_its_own_cues(self) -> None:
        # Siscia: the Croatian article (scout sample), "its urban settlement ... 4th century BC"
        found = cands("Tragovi njegove urbane naseljenosti mogu se pratiti sve do 4. stoljeća "
                      "prije Krista.", ["Sisak", "Siscia"], lang="hr", context=True)  # fmt: skip
        assert starts(found) == [("century", -400)]
        assert found.candidates[0].quote.startswith("Tragovi njegove")

    def test_a_bp_age_needs_a_start_cue(self) -> None:
        # Kirkdale Cave: the age of the fauna, not of the site's use
        assert starts(cands("Kirkdale Cave held fossils 130–115,000 years ago.",
                            ["Kirkdale Cave"])) == []  # fmt: skip
        found = cands("Alpha was occupied 12,000 years ago.", ["Alpha"])
        assert [c.kind for c in found.candidates] == [X.BP]


class TestPeriodWords:
    def test_a_period_word_is_a_start(self) -> None:
        assert starts(cands("Alpha is an Iron Age hillfort.", ["Alpha"])) == [("period", -800)]
        found = cands("Marcinków contains Paleolithic industrial sites.", ["Marcinków"])
        assert starts(found) == [("period", -3000000)]

    def test_pre_inca_is_no_inca_and_the_site_s_own_name_is_no_period(self) -> None:
        assert starts(cands("Inca Uyo was used in pre-Inca times.", ["Inca Uyo"])) == []
        assert starts(cands("Inca Uyo is an Inca site.", ["Inca Uyo"])) == [("period", 1438)]

    def test_compounds_and_negations_are_no_periods(self) -> None:
        assert starts(cands("Alpha has a Roman Catholic chapel.", ["Alpha"])) == []
        assert starts(cands("Alpha is not Roman but older.", ["Alpha"])) == []

    def test_a_find_s_period_is_not_the_site_s(self) -> None:
        assert starts(cands("Roman coins were found at Alpha.", ["Alpha"])) == []

    def test_a_geological_age_the_vocabulary_lacks_and_a_broad_word_date_nothing(self) -> None:
        # Pilares do Lena: "Cambrian period" (and its P571 1995 is a park's founding)
        assert starts(cands("Pilares do Lena are rocks of the Cambrian period.",
                            ["Pilares do Lena"])) == []  # fmt: skip
        assert starts(cands("Alpha is a prehistoric site.", ["Alpha"])) == []

    def test_a_stated_year_beats_a_period_word_in_the_same_sentence(self) -> None:
        found = cands("Alpha, a Roman fort, was built in 79 AD.", ["Alpha"])
        assert starts(found) == [("year", 79)]


class TestTheSections:
    def test_only_the_lead_and_the_reading_sections_are_read(self) -> None:
        text = (
            "Alpha is a hillfort.\n\n== History ==\nAlpha was built in 300 BC.\n"
            "=== Later use ===\nIt was rebuilt.\n== Tourism ==\nAlpha was built in 1990.\n"
            "== Geschichte ==\nAlpha wurde 200 v. Chr. errichtet.\n"
        )
        read = [(section, para) for section, _lead, para in X.readable_paragraphs(text)]
        assert read == [
            ("", "Alpha is a hillfort."),
            ("History", "Alpha was built in 300 BC."),
            ("Later use", "It was rebuilt."),
            ("Geschichte", "Alpha wurde 200 v. Chr. errichtet."),
        ]

    def test_from_prose_carries_the_paragraph_s_anchor(self) -> None:
        text = "Alpha is a hillfort in Wales.\n== History ==\nAlpha was a hillfort. It was built in 300 BC.\n"
        found = X.from_prose(text, lang="en", forms=X.name_forms(["Alpha"]), tier=2,
                             source="enwiki prose", url="u", revision=1)  # fmt: skip
        assert starts(found) == [("year", -300)]
        assert found.candidates[0].quote == "It was built in 300 BC."


# ------------------------------------------------------------------------------ the infobox
WIKITEXT = """{{Short description|x}}
{{Infobox ancient site
| name = Alpha
| built = c. 3000 BC<ref>{{cite web|url=x}}</ref>
| abandoned = 1200 BC
| epochs = [[Bronze Age]], [[Iron Age]]
| map = {{Location map|x}}
}}
'''Alpha''' is ...
"""


class TestTheInfobox:
    def test_the_start_fields_are_read_and_quoted_as_printed(self) -> None:
        params = X.infobox_params(WIKITEXT)
        assert [(name, raw) for _box, name, raw in params] == [
            ("built", "| built = c. 3000 BC<ref>{{cite web|url=x}}</ref>"),
            ("epochs", "| epochs = [[Bronze Age]], [[Iron Age]]"),
        ]
        found = X.from_infobox(WIKITEXT, url="u&action=raw", revision=5)
        # "Bronze Age, Iron Age": a list of periods in two buckets is a history, not a start
        assert sorted(starts(found)) == [("year", -3000)]
        assert reasons(found) == [X.SEVERAL_PERIODS]
        assert {c.tier for c in found.candidates} == {1}

    def test_a_date_field_reads_an_unmarked_year_and_templates(self) -> None:
        text = "{{Infobox historic site\n| built = {{circa|1250}}\n}}"
        assert starts(X.from_infobox(text, url="u", revision=1)) == [("year", 1250)]
        text = "{{Infobox ancient site\n| founded = {{BCE|500}}\n}}"
        assert starts(X.from_infobox(text, url="u", revision=1)) == [("year", -500)]

    def test_another_infobox_s_fields_are_not_read(self) -> None:
        assert X.infobox_params("{{Infobox person\n| born = 300 BC\n}}") == []


# ------------------------------------------------------------------------------ Wikidata, Pleiades
def time_claim(prop: str, time: str, precision: int) -> dict[str, Any]:
    return {prop: [{"rank": "normal", "mainsnak": {"datavalue": {"value": {
        "time": time, "precision": precision}}}}]}  # fmt: skip


def item_claim(prop: str, *ids: str) -> dict[str, Any]:
    return {prop: [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": i}}}} for i in ids]}


class TestWikidata:
    def test_wikidata_time_reads_the_precision(self) -> None:
        assert X.wikidata_time({"time": "-0750-00-00T00:00:00Z", "precision": 9}) == (-750, -750)
        assert X.wikidata_time({"time": "-0800-00-00T00:00:00Z", "precision": 7}) == (-800, -701)
        assert X.wikidata_time({"time": "+1401-00-00T00:00:00Z", "precision": 7}) == (1401, 1500)
        assert X.wikidata_time({"time": "-3000-00-00T00:00:00Z", "precision": 6}) == (-3000, -2001)
        assert X.wikidata_time({"time": "-10000-00-00T00:00:00Z", "precision": 4}) is None

    def test_a_park_s_founding_is_no_start(self) -> None:
        # Pilares do Lena: P571 1995 is the park's - P31 vetoes it, and so would the year cap
        entity = {"lastrevid": 9, "claims": {**time_claim("P571", "-0500-00-00T00:00:00Z", 9),
                                             **item_claim("P31", "Q1")}}  # fmt: skip
        found = X.from_wikidata("Q5", entity, classes={"Q1": {"label": "natural park"}}, item_labels={})
        assert found.candidates == [] and "modern founding" in found.notes[0].reason

    def test_an_ancient_site_s_inception_period_and_construction_are_read(self) -> None:
        claims = {
            **time_claim("P571", "-0750-00-00T00:00:00Z", 9),
            **item_claim("P31", "Q2"),
            **item_claim("P2348", "Q11764"),
            "P793": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": "Q385378"}}},
                      "qualifiers": {"P585": [{"datavalue": {"value": {
                          "time": "-0600-00-00T00:00:00Z", "precision": 9}}}]}}],
        }  # fmt: skip
        found = X.from_wikidata(
            "Q5", {"lastrevid": 9, "claims": claims},
            classes={"Q2": {"label": "archaeological site"}},
            item_labels={"Q11764": {"label": "Iron Age"}, "Q385378": {"label": "construction"}},
        )  # fmt: skip
        assert sorted(starts(found)) == [("period", -800), ("wikidata", -750), ("wikidata", -600)]
        assert {c.url for c in found.candidates} == {
            "https://www.wikidata.org/w/index.php?title=Q5&oldid=9"
        }

    def test_a_collective_entity_is_named_by_its_classes(self) -> None:
        assert X.collective_reason(["village"]) == "P31 village"
        assert X.collective_reason(["nature reserve"]) == "P31 nature reserve"
        assert X.collective_reason(["village", "archaeological site"]) is None
        assert X.collective_reason(["hillfort"]) is None


class TestPleiades:
    ROW = {"id": "123", "modified": "2025", "minDate": "-750", "timePeriodsKeys": "archaic,roman",
           "description": "An ancient city founded in the 6th century BC."}  # fmt: skip

    def test_the_description_is_anchored_and_min_date_is_the_weakest(self) -> None:
        found = X.from_pleiades(self.ROW, forms=X.name_forms(["Alpha"]))
        assert sorted(starts(found)) == [("century", -600), ("pleiades", -750)]
        weakest = [c for c in found.candidates if c.kind == X.PLEIADES][0]
        assert weakest.quote == "timePeriodsKeys: archaic,roman"
        assert weakest.url == "https://pleiades.stoa.org/places/123"


# ------------------------------------------------------------------------------ the decision
def cand(start: int, tier: int, kind: str = X.YEAR, sentence: str = "s") -> X.Candidate:
    return X.Candidate(start, start, start, kind, tier, X.TIERS[tier], f"u{tier}", f"q{start}",
                       1, "built", "", sentence)  # fmt: skip


SPAIN = {"site_id": SITE, "name": "Alpha", "lat": 42.0, "lon": -4.5, "country": "Spain"}


class TestTheDecision:
    def test_the_earliest_start_of_the_highest_tier_is_written(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(X.CONFIG, "write_ranges", True)
        found = X.Found([cand(-200, 2), cand(-300, 2), cand(-900, 3), cand(-50, 5)])
        decision = X.decide(SPAIN, found)
        assert (decision.kind, decision.start, decision.tier) == (X.RANGE, -300, 2)
        assert (decision.lo, decision.hi) == (-900, -50)

    def test_one_bucket_is_single(self) -> None:
        decision = X.decide(SPAIN, X.Found([cand(-450, 2), cand(-400, 5)]))
        assert (decision.kind, decision.start) == (X.SINGLE, -450)

    def test_abstentions_say_why(self) -> None:
        assert X.decide(SPAIN, X.Found(), has_source=False).reason == X.NO_SOURCE
        hedged = X.Found(notes=[X.Note(2, "u", "q", "hedged")])
        assert X.decide(SPAIN, hedged).reason == X.HEDGED_ONLY
        assert X.decide(SPAIN, X.Found([cand(-300, 2)]), collective="P31 village").reason == (
            f"{X.COLLECTIVE}: P31 village"
        )
        ambiguous = X.Found([cand(-300, 3)], [X.Note(2, "u", "q", X.TWO_STARTS)])
        assert X.decide(SPAIN, ambiguous).reason == X.TWO_STARTS
        # a two-starts sentence in a tier below the deciding one does not stop it
        lower = X.Found([cand(-300, 2)], [X.Note(4, "u", "q", X.TWO_STARTS)])
        assert X.decide(SPAIN, lower).kind == X.SINGLE

    def test_pleiades_min_date_alone_is_not_written(self) -> None:
        decision = X.decide(SPAIN, X.Found([cand(-750, 6, X.PLEIADES)]))
        assert decision.kind == X.ABSTAIN and decision.reason.startswith(X.SOLO_REFUSED)

    def test_a_period_word_alone_follows_its_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        found = X.Found([cand(-800, 2, X.PERIOD)])
        assert X.decide(SPAIN, found).kind == X.SINGLE
        monkeypatch.setitem(X.CONFIG, "solo", {"period": False, "pleiades": False})
        assert X.decide(SPAIN, found).reason.startswith(X.SOLO_REFUSED)

    def test_a_switched_off_tier_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(X.CONFIG, "tiers", [1, 2, 3, 5, 6])
        assert X.decide(SPAIN, X.Found([cand(-300, 4)])).reason == X.NO_CANDIDATE

    def test_a_start_outside_the_d58_window_is_held_for_the_owner(self) -> None:
        decision = X.decide(SPAIN, X.Found([cand(800, 2)]))
        assert decision.kind == X.SCOPE_HOLD and "D58 window" in decision.reason
        peru = {**SPAIN, "lat": -13.5, "lon": -72.0, "country": "Peru"}
        assert X.decide(peru, X.Found([cand(1450, 2)])).kind == X.SINGLE

    def test_a_label_borderline_start_is_held_too(self) -> None:
        israel = {**SPAIN, "lat": 31.7, "lon": 35.2, "country": "Israel"}
        assert X.decide(israel, X.Found([cand(800, 2)])).kind == X.SCOPE_HOLD


class TestTheRow:
    def test_a_written_start_is_a_replace_with_every_candidate_quoted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(X.CONFIG, "write_ranges", True)
        decision = X.decide(SPAIN, X.Found([cand(-200, 2), cand(-900, 3)]))
        row = X.decision_row(SPAIN, decision, "abc123def456")
        assert (row["decision"], row["value"], row["stored"], row["via"]) == (
            "replace", "-200", None, "extracted"
        )
        assert row["answered_by"] == "extractor:dating@abc123def456" and row["model"] is None
        assert [q["quote"] for q in row["quotes"]] == ["q-200", "q-900"]
        assert row["extract"]["kind"] == X.RANGE and row["extract"]["lo"] == -900

    def test_an_abstention_is_unresolved_with_its_reason(self) -> None:
        row = X.decision_row(SPAIN, X.decide(SPAIN, X.Found()), "s")
        assert row["decision"] == "unresolved" and row["value"] is None
        assert X.NO_CANDIDATE in row["reasoning"]


# ------------------------------------------------------------------------------ the run's files
def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class FakeLoaded:
    def __init__(self, decisions: dict[str, X.Decision]) -> None:
        self.decisions = decisions
        self.sites = {sid: {**SPAIN, "site_id": sid} for sid in decisions}
        self.sources = X.Sources(Path("h"), Path("w"), Path("f"), Path("p"))

    def decide(self, site_id: str, **_: Any) -> X.Decision:
        return self.decisions[site_id]


def extract_run(tmp_path: Path) -> tuple[Path, list[str]]:
    run = tmp_path / "wd5x"
    R.write_run(run, R.EXTRACT, built_at="t")
    ids = [f"{SITE[:-1]}{n}" for n in range(1, 4)]
    write_jsonl(run / "CLASSIFIED.jsonl", [{"site_id": i, "asked": ["period_start"]} for i in ids])
    return run, ids


class TestTheRun:
    def test_it_writes_the_lane_s_files(self, tmp_path: Path) -> None:
        run, ids = extract_run(tmp_path)
        loaded = FakeLoaded({
            ids[0]: X.decide(SPAIN | {"site_id": ids[0]}, X.Found([cand(-300, 2)])),
            ids[1]: X.decide(SPAIN | {"site_id": ids[1]}, X.Found()),
            ids[2]: X.decide(SPAIN | {"site_id": ids[2]}, X.Found([cand(900, 2)])),
        })  # fmt: skip
        result = X.run(run, loaded, collectives={})  # type: ignore[arg-type]
        assert result["written"] == 1
        rows = [json.loads(r) for r in (run / X.DECISIONS_FILE).read_text().splitlines()]
        assert [r["decision"] for r in rows] == ["replace", "unresolved", "unresolved"]
        assert json.loads((run / X.REASK_FILE).read_text()) == {"fields": {}}
        assert [json.loads(r)["site_id"] for r in (run / X.REST_FILE).read_text().splitlines()] == [ids[1]]
        assert [json.loads(r)["start"] for r in (run / X.SCOPE_FILE).read_text().splitlines()] == [900]
        extract = json.loads((run / X.EXTRACT_FILE).read_text())
        assert extract["code"] == X.code_hashes() and set(extract["code"]) >= {"CONFIG"}
        with pytest.raises(X.DatingError, match="runs once"):
            X.run(run, loaded, collectives={})  # type: ignore[arg-type]

    def test_it_refuses_a_run_of_another_rule(self, tmp_path: Path) -> None:
        R.write_run(tmp_path, R.RECHECK)
        with pytest.raises(X.DatingError, match="extract rule"):
            X.run(tmp_path, FakeLoaded({}), collectives={})  # type: ignore[arg-type]


class TestVerify:
    def test_a_decisive_quote_not_found_withdraws_the_start(self, tmp_path: Path) -> None:
        run, ids = extract_run(tmp_path)
        good = X.Candidate(-300, -300, -300, X.YEAR, 2, "enwiki prose", "https://a/1",
                           "Alpha was built in 300 BC.", 1, "built", "")  # fmt: skip
        bad = X.Candidate(-300, -300, -300, X.YEAR, 2, "enwiki prose", "https://a/2",
                          "Beta was built in 300 BC.", 1, "built", "")  # fmt: skip
        loaded = FakeLoaded({
            ids[0]: X.decide(SPAIN | {"site_id": ids[0]}, X.Found([good])),
            ids[1]: X.decide(SPAIN | {"site_id": ids[1]}, X.Found([bad])),
            ids[2]: X.decide(SPAIN | {"site_id": ids[2]}, X.Found()),
        })  # fmt: skip
        X.run(run, loaded, collectives={})  # type: ignore[arg-type]
        pages = {"https://a/1": ("text/html", b"<p>Alpha was built in 300 BC.[3]</p>"),
                 "https://a/2": ("text/html", b"<p>Something else.</p>")}  # fmt: skip
        result = X.verify(run, pages.__getitem__)
        rows = [json.loads(r) for r in (run / X.DECISIONS_FILE).read_text().splitlines()]
        assert [r["decision"] for r in rows] == ["replace", "unresolved", "unresolved"]
        assert rows[0]["quotes"][0]["outcome"] == "found"
        assert rows[1]["extract"]["unverified_value"] == "-300"
        assert result["written"] == 1
        with pytest.raises(X.DatingError, match="verified once"):
            X.verify(run, pages.__getitem__)

    def test_a_wikidata_claim_is_read_in_the_entity_of_its_revision(self) -> None:
        quote = {"source": "https://www.wikidata.org/w/index.php?title=Q5&oldid=9", "tier": 5,
                 "kind": X.WIKIDATA, "quote": "P571: -0750-00-00T00:00:00Z (precision 9)"}  # fmt: skip
        asked: list[str] = []

        def fetch(url: str) -> Any:
            asked.append(url)
            return {"entities": {"Q5": {"claims": {"P571": [{"time": "-0750-00-00T00:00:00Z"}]}}}}

        assert X.verify_quote(quote, fetch) == "found"
        assert asked == ["https://www.wikidata.org/wiki/Special:EntityData/Q5.json?revision=9"]

    def test_the_fetcher_refuses_a_pace_below_a_second(self, tmp_path: Path) -> None:
        with pytest.raises(X.DatingError, match="once a second"):
            X.http_fetcher(tmp_path, pace=0.5)


class TestShown:
    def _verified_run(self, tmp_path: Path, written: int) -> Path:
        run = tmp_path / "run"
        run.mkdir()
        rows = []
        for n in range(written):
            sid = f"{n:08d}-0000-4000-8000-000000000000"
            kind = X.RANGE if n % 3 == 0 else X.SINGLE
            rows.append({"site_id": sid, "name": f"S{n}", "decision": "replace", "value": "-300",
                         "quotes": [{"kind": X.PERIOD if n % 3 == 1 else X.YEAR, "outcome": "found",
                                     "detail": "d", "source": "u", "quote": "q"}],
                         "extract": {"kind": kind, "tier": 1 + n % 5, "lo": -300, "hi": -300}})  # fmt: skip
        write_jsonl(run / X.DECISIONS_FILE, rows)
        X._write_json(run / X.VERIFIED_FILE, {"decisions_sha256": X._sha256(run / X.DECISIONS_FILE),
                                              "written": written})  # fmt: skip
        return run

    def test_thirty_cells_over_represent_ranges_and_period_words(self, tmp_path: Path) -> None:
        run = self._verified_run(tmp_path, 120)
        assert X.show(run, 30, seed=7) == {"shown": 30, "of": 120}
        shown = json.loads((run / X.SHOW_JSON).read_text())["cells"]
        rows = {json.loads(r)["site_id"]: json.loads(r) for r in (run / X.DECISIONS_FILE).read_text().splitlines()}
        assert sum(rows[s]["extract"]["kind"] == X.RANGE for s in shown) >= 10
        assert (run / X.SHOW_MD).read_text(encoding="utf-8").startswith("# D70 extractor")

    def test_shown_records_the_three_checks_and_the_go(self, tmp_path: Path) -> None:
        run = self._verified_run(tmp_path, 60)
        X.show(run, 30, seed=1)
        cells = json.loads((run / X.SHOW_JSON).read_text())["cells"]
        checks = tmp_path / "checks.jsonl"

        def line(sid: str, wrong: int) -> dict[str, Any]:
            verdicts = ["wrong"] * wrong + ["right"] * (3 - wrong)
            return {"site_id": sid, "verdicts": [
                {"model": m, "verdict": v, "reason": "r"}
                for m, v in zip(("claude-opus-5-5", "claude-opus-5-5", "claude-sonnet-5-5"),
                                verdicts, strict=True)]}  # fmt: skip

        write_jsonl(checks, [line(s, 2 if i == 0 else 1 if i == 1 else 0) for i, s in enumerate(cells)])
        result = X.shown(run, checks, "owner AFK, autonomous mandate 2026-11-05")
        assert result == {"n": 30, "wrong": 1, "go": True}
        write_jsonl(checks, [line(s, 2 if i < 2 else 0) for i, s in enumerate(cells)])
        assert X.shown(run, checks, "o")["go"] is False

    def test_a_check_by_another_model_is_refused(self, tmp_path: Path) -> None:
        run = self._verified_run(tmp_path, 40)
        X.show(run, 30, seed=1)
        cells = json.loads((run / X.SHOW_JSON).read_text())["cells"]
        checks = tmp_path / "checks.jsonl"
        write_jsonl(checks, [{"site_id": s, "verdicts": [
            {"model": "MiniMax-M3.1-Flash", "verdict": "right", "reason": ""}]} for s in cells])  # fmt: skip
        with pytest.raises(X.DatingError, match="may not answer"):
            X.shown(run, checks, "o")


# ------------------------------------------------------------------------------ the harvest
def fetcher(tmp_path: Path, handle: Any) -> Fetcher:
    return Fetcher(tmp_path / "cache", workers=1, transport=httpx.MockTransport(handle),
                   user_agent=H.USER_AGENT)  # fmt: skip


class TestTheHarvestSources:
    def test_wikitext_is_fetched_by_revision_fifty_at_a_time(self, tmp_path: Path) -> None:
        asked: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            asked.append(request)
            revids = request.url.params["revids"].split("|")
            pages = [{"title": f"T{r}", "revisions": [{"revid": int(r), "slots": {"main": {
                "content": f"text {r}"}}}]} for r in revids if r != "7"]  # fmt: skip
            return httpx.Response(200, json={"query": {"pages": pages,
                                                       "badrevids": {"7": {"revid": 7}}}})  # fmt: skip

        pages = [("en", n) for n in range(1, 61)]
        slept: list[float] = []
        with fetcher(tmp_path, handle) as net:
            result = H.fetch_wikitext(net, tmp_path, pages, sleep=slept.append, pace=1.0)
        assert result == {"revisions": 60, "requests": 2} and slept == [1.0]
        assert asked[0].url.params["rvslots"] == "main"
        assert H.load_wikitext(tmp_path, "en", 1) == "text 1"
        assert H.load_wikitext(tmp_path, "en", 7) is None
        with pytest.raises(H.HarvestError, match="fetch-dating"):
            H.load_wikitext(tmp_path, "en", 99)

    def test_the_other_wikipedias_are_asked_one_by_one_and_never_faster(self, tmp_path: Path) -> None:
        entity = {"sitelinks": {"enwiki": {"title": "Sisak"}, "hrwiki": {"title": "Sisak"},
                                "dewiki": {"title": "Sisak"}, "zhwiki": {"title": "x"}}}  # fmt: skip
        H._write_json(H.entity_path(tmp_path, "Q1"), entity)
        asked: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.host)
            return httpx.Response(200, json={"query": {"pages": [{"title": "Sisak", "lastrevid": 5,
                                                                  "extract": "== Povijest ==\nx"}]}})  # fmt: skip

        with fetcher(tmp_path, handle) as net:
            with pytest.raises(H.HarvestError, match="once a second"):
                H.fetch_wikis(net, tmp_path, ["Q1"], pace=0.2)
            H.fetch_wikis(net, tmp_path, ["Q1"], skip={"Q1": frozenset({"de"})}, sleep=lambda _: None)
        assert asked == ["hr.wikipedia.org"]
        assert [lang for lang, _ in H.load_wikis(tmp_path, "Q1", entity, skip=frozenset({"de"}))] == ["hr"]
        with pytest.raises(H.HarvestError, match="fetch-dating"):
            H.load_wikis(tmp_path, "Q1", entity)

    def test_cited_pages_keep_the_forbidden_families_and_wikipedia_out(self, tmp_path: Path) -> None:
        run = tmp_path / "wd5"
        (run / "pages").mkdir(parents=True)
        urls = {"https://vici.org/vici/1": "a", "https://www.wikiwand.com/en/X": "b",
                "https://en.wikipedia.org/wiki/X": "c", "https://dead.example/x": "d"}  # fmt: skip
        index = []
        for url, key in urls.items():
            (run / "pages" / f"{key}.body").write_bytes(b"<p>Alpha was built in 300 BC.</p>")
            index.append({"url": url, "key": key, "status": 404 if "dead" in url else 200,
                          "content_type": "text/html"})  # fmt: skip
        write_jsonl(run / "PAGES.jsonl", index)
        write_jsonl(run / "DECISIONS.jsonl", [{"site_id": SITE, "field": "period_start",
                                              "quotes": [{"source": u} for u in urls]}])  # fmt: skip
        refs = H.cited_page_refs(tmp_path)
        assert [r["url"] for r in refs[SITE]] == ["https://vici.org/vici/1"]
        assert H.page_text(refs[SITE][0]) == "Alpha was built in 300 BC."


# ------------------------------------------------------------------------------ the lane's wiring
class TestTheWiring:
    def test_the_rule_fills_never_clears_and_asks_no_agent(self) -> None:
        assert R.BY_STAGE["wd5x"] is R.EXTRACT and R.EXTRACT.name in R.MACHINE_RULES
        assert R.EXTRACT.fill_only and not R.EXTRACT.clearable and not R.EXTRACT.recheck
        assert R.EXTRACT.forbidden_families == R.FORBIDDEN_FAMILIES

    def test_the_lane_has_its_own_stamp_test_id_and_directory(self) -> None:
        lane = LANE.fields_lane("2026-11-10", 1, "wd5x")
        assert lane.name == "fields-wd5x-2026-11-10-s001"
        assert lane.test_id == "WD5X/dating-extractor" and lane.confidence == "one_source"
        assert lane.out_dir_name == "fields/wd5x/write/2026-11-10/s001"
        assert LANE.resolve_lane("fields-wd5x-2026-11-10-s002").run_stamp == "2026-11-10_fields-wd5x-s002"
        assert LANE.fields_lane("2026-11-10", 1, "wd5").test_id == "WD5/structured-fields"

    def test_the_population_asks_the_listed_site_s_start_alone(self) -> None:
        opened = POP.extract_fields("undated on 2026-11-05")
        assert list(opened) == ["period_start"] and opened["period_start"]["why"] == POP.WHY_EMPTY
        assert POP.extract_fields(None) == {}

    def test_an_extract_run_is_built_from_sites_only(self, tmp_path: Path) -> None:
        wd1 = POP.Wd1((), (), [], {}, {}) if hasattr(POP, "Wd1") else None
        with pytest.raises(POP.PopulationError, match="built from --sites"):
            POP.build(tmp_path, tmp_path, table={}, wd1=wd1, stage="wd5x")  # type: ignore[arg-type]
        with pytest.raises(POP.PopulationError, match="built from --sites"):
            POP.build(tmp_path, tmp_path, table={}, wd1=wd1, stage="wd3", listed={"a": "b"})  # type: ignore[arg-type]

    def test_the_handoff_refuses_an_extract_run(self, tmp_path: Path) -> None:
        from fields import handoff as HO

        R.write_run(tmp_path, R.EXTRACT)
        with pytest.raises(HO.HandoffStepError, match="asks no agent"):
            HO._refuse_machine_rule(tmp_path, R.read_rule(tmp_path))


# ------------------------------------------------------------------------------ one site, end to end
class TestOneSiteEndToEnd:
    """Every tier read from files laid out as the harvest, the Wikipedia cache and the Pleiades
    table lay them out (`Sources.load`, `_Loaded.decide`)."""

    def _sources(self, tmp_path: Path) -> X.Sources:
        harvest, cache, fields = tmp_path / "harvest", tmp_path / "wiki_cache", tmp_path / "fields"
        for d in (harvest, cache / "en", fields):
            d.mkdir(parents=True)
        line = {"site_id": SITE, "name": "Siscia", "country": "Croatia", "lat": 45.48,
                "lon": 16.37, "qid": "Q1", "enwiki_title": "Sisak", "source_url": None}  # fmt: skip
        write_jsonl(harvest / H.SITES_FILE, [line])
        entity = {
            "lastrevid": 77,
            "labels": {"hr": {"value": "Sisak"}},
            "aliases": {"la": [{"value": "Siscia"}]},
            "sitelinks": {"enwiki": {"title": "Sisak"}, "hrwiki": {"title": "Sisak"}},
            "claims": {**item_claim("P31", "Q2"),
                       "P1584": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "123"}}}]},
        }  # fmt: skip
        H._write_json(H.entity_path(harvest, "Q1"), entity)
        H._write_json(harvest / H.CLASSES_FILE, {"Q2": {"label": "archaeological site", "p279": []}})
        H._write_json(harvest / H.ITEM_LABELS_FILE, {})
        H._write_json(H.wikitext_path(harvest, "en", 10),
                      {"lang": "en", "revid": 10, "wikitext": "{{Infobox ancient site\n| built = 35 BC\n}}"})  # fmt: skip
        H._write_json(H.wikis_path(harvest, "hr", "Q1"),
                      {"lang": "hr", "title": "Sisak", "revid": 55, "missing": False,
                       "text": "Sisak je grad.\n== Povijest ==\nSisak je star. Tragovi njegove "
                               "urbane naseljenosti "
                               "mogu se pratiti sve do 4. stoljeća prije Krista.\n"})  # fmt: skip
        write_jsonl(cache / "INDEX.jsonl",
                    [{"site_id": SITE, "lang": "en", "title": "Sisak", "file": "en/a.json"}])
        (cache / "en" / "a.json").write_text(json.dumps({
            "lang": "en", "title": "Sisak", "resolved_title": "Sisak", "revid": 10,
            "text": "Sisak is a city in Croatia.\n== History ==\nThe mint of Siscia was opened "
                    "between 262 and 383 AD.\n"}), encoding="utf-8")  # fmt: skip
        csv = tmp_path / "pleiades.csv"
        csv.write_text("id,description,minDate,timePeriodsKeys,modified\n"
                       "123,A Roman town.,-30,roman,2024\n", encoding="utf-8")  # fmt: skip
        return X.Sources(harvest, cache, fields, csv)

    def test_every_tier_is_read_and_the_infobox_decides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(X.CONFIG, "write_ranges", True)
        loaded = self._sources(tmp_path).load()
        found, collective, has_source = loaded.found(SITE)
        assert collective is None and has_source
        tiers = sorted({(c.tier, c.kind, c.start) for c in found.candidates})
        # the hr deictic ("njegove", its) stands in a paragraph that named Sisak; Pleiades'
        # description is about the place, so its "Roman" is read too
        assert tiers == [(1, "year", -35), (3, "century", -400), (6, "period", 43),
                         (6, "pleiades", -30)]  # fmt: skip
        decision = loaded.decide(SITE)
        assert (decision.kind, decision.start, decision.tier) == (X.RANGE, -35, 1)
        assert decision.decisive is not None
        assert decision.decisive.url == (
            "https://en.wikipedia.org/w/index.php?title=Sisak&oldid=10&action=raw"
        )
        assert decision.decisive.quote == "| built = 35 BC"
        # the range of the candidates: -400 (hr) .. 43 (Pleiades' "Roman"); its minDate is evidence
        assert (decision.lo, decision.hi) == (-400, 43)

    def test_a_missing_fetch_stops_the_extractor(self, tmp_path: Path) -> None:
        sources = self._sources(tmp_path)
        H.wikis_path(sources.harvest, "hr", "Q1").unlink()
        with pytest.raises(H.HarvestError, match="fetch-dating"):
            sources.load().found(SITE)

    def test_the_collective_list_overrides(self, tmp_path: Path) -> None:
        loaded = self._sources(tmp_path).load()
        decision = loaded.decide(SITE, collectives={SITE: "X8: a collective entity"})
        assert decision.kind == X.ABSTAIN and "X8" in decision.reason


class TestTheExtractPopulation:
    """`population.py build --stage wd5x --sites UNDATED.jsonl`: the listed undated sites, each asked
    `period_start` alone; a dated one is refused before anything is written."""

    def _prepare(self, tmp_path: Path, **stored: Any) -> tuple[Path, Path]:
        from tests.remediation.test_fields_wd5 import TestTheRecheckRun

        stored.setdefault("period_start", None)
        stored.setdefault("period_name", "Undated")
        return TestTheRecheckRun().prepare(tmp_path, [], **stored)

    def _build(self, root: Path, out: Path, listed: dict[str, str]) -> dict[str, Any]:
        from tests.remediation import test_fields_wd3 as TW
        from tests.remediation.test_fields_classify import TABLE

        return POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd5x", listed=listed)

    def test_the_listed_undated_site_is_asked_its_start(self, tmp_path: Path) -> None:
        from fields import classify as C

        from tests.remediation.test_fields_wd5 import SITE_ID

        root, out = self._prepare(tmp_path)
        counts = self._build(root, out, {SITE_ID: "undated on 2026-11-05"})
        line = json.loads((out / C.CLASSIFIED_FILE).read_text(encoding="utf-8"))
        assert line["asked"] == ["period_start"]
        assert line["open"]["period_start"]["why"] == POP.WHY_EMPTY
        assert counts["population"]["why"] == {"period_start:empty": 1}
        assert R.read_rule(out) is R.EXTRACT
        run = json.loads((out / R.RUN_FILE).read_text(encoding="utf-8"))
        assert run["listed"] == {SITE_ID: "undated on 2026-11-05"}

    def test_a_dated_listed_site_is_refused(self, tmp_path: Path) -> None:
        from tests.remediation.test_fields_wd5 import SITE_ID

        root, out = self._prepare(tmp_path, period_start=-700, period_name="1500 - 500 BC")
        with pytest.raises(POP.PopulationError, match="holds period_start -700 now"):
            self._build(root, out, {SITE_ID: "r"})
        assert not (out / R.RUN_FILE).exists()


class TestThePlanCells:
    """`plan.site_cells` under the extract rule: an empty start is filled with its label; nothing
    else is touched."""

    LIVE = {"site_id": SITE, "name": "Alpha", "source_id": "ancient_nerds", "scope_status": None,
            "country": "Spain", "lat_text": "42.0", "lon_text": "-4.5", "geom_text": None,
            "geom_is_point": True, "period_start": None, "period_end": None,
            "period_name": "Undated", "site_type": None, "source_url": None}  # fmt: skip
    LINE = {"open": {"period_start": {"why": "empty", "wd1": None, "made": "undated"}}}

    def _cells(self, row: dict[str, Any], live: dict[str, Any] | None = None) -> list[Any]:
        from fields import plan as PLAN

        return PLAN.site_cells(live or self.LIVE, self.LINE, {"period_start": row}, {},
                               country_check=lambda *a: {"agrees": True}, under=R.EXTRACT)  # fmt: skip

    def test_a_written_start_comes_with_its_label(self) -> None:
        decision = X.decision_row(SPAIN, X.decide(SPAIN, X.Found([cand(-300, 2)])), "s")
        cells = self._cells(decision)
        assert [(v.column, v.old_value, v.new_value, v.ok) for v in cells] == [
            ("period_start", None, "-300", True),
            ("period_name", "Undated", "500 BC - 1 AD", True),
        ]
        assert cells[0].rule == "wd5x-replace" and cells[0].evidence[0]["quote"] == "q-300"

    def test_an_abstention_writes_nothing_and_a_dated_site_is_never_overwritten(self) -> None:
        abstained = X.decision_row(SPAIN, X.decide(SPAIN, X.Found()), "s")
        assert [v.reason for v in self._cells(abstained)] == ["field-unresolved"]
        decision = X.decision_row(SPAIN, X.decide(SPAIN, X.Found([cand(-300, 2)])), "s")
        moved = self._cells(decision, {**self.LIVE, "period_start": -500})
        assert [v.reason for v in moved] == ["moved-since-classification"]


class TestFetchDating:
    def test_it_fetches_the_listed_sites_sources_and_records_each_step(self, tmp_path: Path) -> None:
        line = {"site_id": SITE, "name": "Sisak", "country": "Croatia", "lat": 45.48, "lon": 16.37,
                "qid": "Q1", "enwiki_title": "Sisak", "source_url": None}  # fmt: skip
        write_jsonl(tmp_path / H.SITES_FILE, [line])
        H._write_json(tmp_path / H.META_FILE, {"steps": {}})
        H._write_json(H.entity_path(tmp_path, "Q1"), {
            "sitelinks": {"enwiki": {"title": "Sisak"}, "hrwiki": {"title": "Sisak"}},
            "claims": item_claim("P2348", "Q11764")})  # fmt: skip

        class Cache:
            def pages(self, site_id: str) -> list[dict[str, Any]]:
                return [{"lang": "en", "title": "Sisak", "revid": 10}] if site_id == SITE else []

        hosts: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            params = request.url.params
            if request.url.host == "www.wikidata.org":
                return httpx.Response(200, json={"entities": {"Q11764": {
                    "labels": {"en": {"value": "Iron Age"}}}}})  # fmt: skip
            if "revids" in params:
                return httpx.Response(200, json={"query": {"pages": [{"title": "Sisak", "revisions": [
                    {"revid": 10, "slots": {"main": {"content": "{{Infobox}}"}}}]}]}})  # fmt: skip
            return httpx.Response(200, json={"query": {"pages": [{"title": "Sisak", "lastrevid": 5,
                                                                  "extract": "x"}]}})  # fmt: skip

        with fetcher(tmp_path, handle) as net:
            result = H.fetch_dating(tmp_path, net=net, site_ids=[SITE], wiki_cache=Cache(),
                                    sleep=lambda _: None)  # fmt: skip
        assert hosts == ["www.wikidata.org", "en.wikipedia.org", "hr.wikipedia.org"]
        assert result["wikitext"] == {"revisions": 1, "requests": 1}
        assert H._read_json(tmp_path / H.ITEM_LABELS_FILE) == {"Q11764": {"label": "Iron Age"}}
        steps = H._read_json(tmp_path / H.META_FILE)["steps"]
        assert set(steps) == {"dating_item_labels", "dating_wikitext", "dating_wikis"}
        with pytest.raises(H.HarvestError, match="not in"):
            H.fetch_dating(tmp_path, net=net, site_ids=["nope"], wiki_cache=Cache())


# ------------------------------------------------------------------------------ DEV round 1
class TestDevRoundOne:
    """The rules DEV round 1 (2026-11-06, gold round-01's DEV and dev-hard sites only) added: each
    from a DEV error, none from the sealed gold."""

    def test_a_period_word_is_read_in_english_only(self) -> None:
        found = cands("Midas Anıtı, Han ilçesinin Yazılıkaya Mahallesi'ndeki anıt.", ["Midas Anıtı"],
                      lang="tr")  # fmt: skip
        assert starts(found) == []

    def test_a_list_of_periods_in_two_buckets_is_no_start(self) -> None:
        found = cands("Pen y Gaer is a Bronze Age and Iron Age hillfort in Wales.", ["Pen y Gaer"])
        assert starts(found) == [] and reasons(found) == [X.SEVERAL_PERIODS]

    def test_a_period_word_governed_by_an_event_cue_is_no_start(self) -> None:
        found = cands("Hormiguero was a Mayan city at its peak in the Late Classic Period.",
                      ["Hormiguero"])  # fmt: skip
        assert starts(found) == [] and reasons(found)[0].startswith("event-cue")

    def test_a_period_word_inside_a_given_name_dates_nothing(self) -> None:
        found = cands("Pachataka, commonly known as the Inca Gallows, is an archaeological site.",
                      ["Pachataka"])  # fmt: skip
        assert starts(found) == []

    @pytest.mark.parametrize(
        ("sentence", "names", "lang"),
        [
            ("Previous to the year 408 BCE, when the city of Rhodes was built, Lindus formed a "
             "little state by itself.", ["Lindus"], "en"),
            ("Ialisos estaba al sudoeste de la ciudad de Rodas, que fue fundada en el 408 a. C.",
             ["Ialisos"], "es"),
        ],
    )  # fmt: skip
    def test_a_start_cue_of_another_named_place_is_not_the_site_s(
        self, sentence: str, names: list[str], lang: str
    ) -> None:
        found = cands(sentence, names, lang=lang)
        assert starts(found) == []
        assert any(r.startswith(("cue-of-other", "other-subject")) for r in reasons(found))

    def test_the_builder_is_no_other_subject(self) -> None:
        found = cands("Palazzo a Mare was built by Augustus in 27 BC.", ["Palazzo a Mare"])
        assert starts(found) == [("year", -27)]

    def test_a_count_of_things_is_no_year(self) -> None:
        found = cands("The Trialeti petroglyphs include about 100 images, carved on basalt.",
                      ["Trialeti petroglyphs"])  # fmt: skip
        assert starts(found) == []

    def test_a_round_year_on_a_bucket_edge_decides_nothing(self) -> None:
        decision = X.decide(SPAIN, X.Found([cand(-3000, 1)]))
        assert decision.kind == X.ABSTAIN and X.BUCKET_EDGE in [n.reason for n in decision.notes]
        assert X.decide(SPAIN, X.Found([cand(-2900, 1)])).start == -2900

    def test_a_range_is_not_written_by_default(self) -> None:
        decision = X.decide(SPAIN, X.Found([cand(-200, 2), cand(-900, 2)]))
        assert decision.kind == X.ABSTAIN and decision.reason.startswith(X.SOURCES_DISAGREE)

    def test_a_period_s_own_article_is_no_site_article(self) -> None:
        assert X.is_period_name("Iron Age") and X.is_period_name("Hellenistic")
        assert not X.is_period_name("Yarrows Broch")

    def test_the_shipped_switches(self) -> None:
        assert {k: AS_SHIPPED[k] for k in SHIPPED} == SHIPPED
        assert AS_SHIPPED["solo"] == {"period": True, "pleiades": False}

    def test_a_disabled_tier_is_not_read(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        loaded = TestOneSiteEndToEnd()._sources(tmp_path).load()
        for wikis in (tmp_path / "harvest" / "wikis").glob("*/*.json"):
            wikis.unlink()  # tier 3's extracts never fetched: read, they would stop the extractor
        monkeypatch.setitem(X.CONFIG, "tiers", [1, 2])
        found, _collective, _has = loaded.found(SITE)
        assert {c.tier for c in found.candidates} <= {1, 2}
