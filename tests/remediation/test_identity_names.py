"""D23 names: the defects of a stored name, a repair that is an attested form, a spoken name by rule."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from identity import names_triage as N  # noqa: E402

from tests.remediation.identity_fixtures import (  # noqa: E402
    entity,
    export_of,
    ext,
    site,
    store_of,
)

GREEK_KAPPA = "\u039a"


def spoken(name: str, *forms: tuple[str, str]) -> dict:
    return N.spoken_record(site(name=name), list(forms))


class TestTheDefects:
    def test_a_clean_english_name_has_none(self) -> None:
        assert N.defects_of("Temple of Apollo") == []

    def test_a_comma_qualifier_is_a_defect(self) -> None:
        assert N.defects_of("Tiverton, Devon") == ["comma_qualifier"]

    def test_a_parenthesis_is_a_defect(self) -> None:
        assert N.defects_of("Black Mountain (Pima County)") == ["parenthesis"]

    def test_a_digit_is_a_defect(self) -> None:
        assert N.defects_of("Areni-1 Cave") == ["digit"]

    def test_a_foreign_prefix_is_a_defect(self) -> None:
        assert N.defects_of("Dolmen de Menga") == ["foreign_prefix"]
        assert N.defects_of("Templo del Sol") == ["foreign_prefix"]

    def test_a_name_longer_than_forty_characters_is_long(self) -> None:
        assert "long" in N.defects_of("Cathedral and Churches of Echmiatsin and Zvartnots")
        assert "long" not in N.defects_of("x" * 40)

    def test_a_name_in_capitals_is_a_defect_but_a_short_one_is_not(self) -> None:
        assert "all_caps" in N.defects_of("TEMPLE OF APOLLO")
        assert "all_caps" not in N.defects_of("UR")

    def test_a_double_space_and_a_zero_width_character_are_whitespace_artifacts(self) -> None:
        assert N.defects_of("Hadrian  Wall") == ["whitespace_artifact"]
        assert N.defects_of("Hadrian\u200b Wall") == ["whitespace_artifact"]
        assert N.defects_of(" Wall") == ["whitespace_artifact"]

    def test_a_greek_letter_inside_a_latin_word_is_a_mixed_script(self) -> None:
        name = f"{GREEK_KAPPA}ourion Ancient Amphitheatre"
        assert "mixed_script" in N.defects_of(name)
        assert "nonlatin_script" in N.defects_of(name)

    def test_a_modifier_letter_is_neither_mixed_nor_non_latin(self) -> None:
        assert N.defects_of("Q\u02bcumarkaj") == []

    def test_a_name_in_another_script_is_non_latin(self) -> None:
        assert N.defects_of("\u0391\u03b8\u03ae\u03bd\u03b1") == ["nonlatin_script"]

    def test_mojibake_is_a_defect(self) -> None:
        assert "mojibake" in N.defects_of("Ch\u00c3\u00a2teau")


class TestTheNoteOnTheLabel:
    def test_a_name_with_no_word_of_the_label_differs(self) -> None:
        assert N.differs_from_label("Quesera de Zonzamas", "Cheeseboard", [])

    def test_a_name_that_is_an_english_form_does_not(self) -> None:
        assert not N.differs_from_label("Cheese Board", "Cheeseboard", ["Cheese Board"])

    def test_a_name_with_most_words_in_common_does_not(self) -> None:
        assert not N.differs_from_label("Temple of Apollo Delphi", "Temple of Apollo", [])

    def test_an_item_without_a_label_has_nothing_to_differ_from(self) -> None:
        assert not N.differs_from_label("Anything", None, [])


class TestTheSuggestion:
    forms = [("Tiverton", "label"), ("Kourion", "alias"), ("Theatre of Kourion", "enwiki_title")]

    def test_a_comma_qualifier_is_dropped_when_what_is_left_is_attested(self) -> None:
        got = N.suggestion("Tiverton, Devon", self.forms)
        assert got == {"kind": "attested_form", "value": "Tiverton", "source": "label"}

    def test_it_is_not_suggested_when_what_is_left_is_not_attested(self) -> None:
        assert N.suggestion("Pumamarka, Urubamba", self.forms) is None

    def test_a_homoglyph_is_repaired_only_to_an_attested_form(self) -> None:
        got = N.suggestion(f"{GREEK_KAPPA}ourion", self.forms)
        assert got == {"kind": "homoglyph", "value": "Kourion", "source": "alias"}
        assert N.suggestion(f"{GREEK_KAPPA}ouriom", self.forms) is None

    def test_a_double_space_is_collapsed_when_the_result_is_attested(self) -> None:
        got = N.suggestion("Theatre  of Kourion", self.forms)
        assert got is not None and got["kind"] == "whitespace"

    def test_a_name_that_is_already_attested_needs_no_suggestion(self) -> None:
        assert N.suggestion("Tiverton", self.forms) is None

    def test_a_title_is_a_name_without_underscores_and_disambiguator(self) -> None:
        assert N.title_form("Temple_of_Apollo_(Delphi)") == "Temple of Apollo"

    def test_a_defective_site_is_flagged_for_a_model_only_without_a_suggestion(self) -> None:
        defective = site(name="Pumamarka, Urubamba")
        record = N.triage_record(defective, "Pumamarka", [], [])
        assert record is not None and record["needs_model"] is False  # label is attested
        record = N.triage_record(defective, "Other", [], [])
        assert record["needs_model"] is True and record["suggestion"] is None
        assert N.triage_record(site(name="Clean Name"), None, [], []) is None

    def test_a_site_with_only_a_comma_is_comma_only(self) -> None:
        record = N.triage_record(site(name="Foo, Bar"), None, [], [])
        assert record["severity"] == "comma_only"
        record = N.triage_record(site(name="Foo, Bar 2"), None, [], [])
        assert record["severity"] == "hard"


class TestTheSpokenName:
    def test_a_clean_name_is_spoken_as_it_is(self) -> None:
        got = spoken("Temple of Apollo")
        assert got["spoken"] == "Temple of Apollo" and got["source"] == "name"
        assert got["needs_model"] is False and got["steps"] == []

    def test_a_qualifier_after_a_comma_is_dropped(self) -> None:
        got = spoken("Temple of Mercury, Puy de Dome")
        assert got["spoken"] == "Temple of Mercury" and got["steps"] == ["qualifier"]

    def test_a_parenthesis_is_dropped(self) -> None:
        assert spoken("Black Mountain (Pima County)")["spoken"] == "Black Mountain"

    def test_a_trailing_arabic_numeral_is_dropped(self) -> None:
        got = spoken("Plain of Jars Site 3")
        assert got["spoken"] == "Plain of Jars Site" and "numeral" in got["steps"]

    def test_a_regnal_numeral_is_part_of_the_name(self) -> None:
        assert spoken("Tomb of Artaxerxes III")["spoken"] == "Tomb of Artaxerxes III"

    def test_a_shorter_attested_form_without_a_place_word_wins(self) -> None:
        got = spoken("Kimsbury Hill Fort", ("Kimsbury Hill", "alias"))
        assert got["spoken"] == "Kimsbury Hill" and got["source"] == "alias"

    def test_a_shorter_form_that_leaves_out_a_place_word_is_refused(self) -> None:
        got = spoken("Mortuary Temple of Khufu", ("mortuary temple", "label"))
        assert got["spoken"] == "Mortuary Temple of Khufu"

    def test_a_form_that_adds_a_word_is_refused(self) -> None:
        got = spoken("Lescudjack Hill Fort", ("Hill Castle", "alias"))
        assert got["spoken"] == "Lescudjack Hill Fort"

    def test_the_kind_of_the_thing_is_not_its_distinctive_word(self) -> None:
        got = spoken("Dolmen de Menga", ("Menga", "label"))
        assert got["spoken"] == "Menga" and got["source"] == "label"

    def test_a_form_without_the_names_distinctive_word_does_not_stand_for_it(self) -> None:
        got = spoken("Castillo de Almodovar", ("Castillo", "alias"))
        assert got["needs_model"] is True

    def test_a_form_that_shares_too_few_words_does_not_stand_for_it(self) -> None:
        got = spoken(
            "Castillo de Almodovar Viejo", ("Almodovar Fortress Walls Gate Towers", "alias")
        )
        assert got["needs_model"] is True

    def test_a_form_that_adds_a_word_while_dropping_a_kind_is_refused(self) -> None:
        got = spoken("Oddendale Stone Circle", ("Oddendale Park Circle", "alias"))
        assert got["spoken"] == "Oddendale Stone Circle"

    def test_a_name_in_another_script_is_not_spoken_by_rule(self) -> None:
        got = spoken("Αθήνα")
        assert got["needs_model"] is True and got["reasons"] == ["nonlatin_script"]

    def test_a_mixed_script_name_is_not_spoken_by_rule(self) -> None:
        got = spoken(f"{GREEK_KAPPA}ourion")
        assert got["reasons"] == ["nonlatin_script", "mixed_script"]

    def test_a_foreign_prefix_is_not_spoken_by_rule(self) -> None:
        got = spoken("Dolmen de Menga")
        assert got["needs_model"] is True and got["spoken"] is None
        assert got["reasons"] == ["foreign_prefix"]

    def test_a_foreign_prefix_is_spoken_when_an_attested_form_stands_for_it(self) -> None:
        got = spoken("Dolmen de Menga", ("Menga Dolmen", "alias"))
        assert got["spoken"] == "Menga Dolmen" and got["source"] == "alias"

    def test_a_form_with_a_different_distinctive_word_does_not_stand_for_it(self) -> None:
        got = spoken("Templos de Tarxien", ("Hagar Qim", "alias"))
        assert got["needs_model"] is True

    def test_a_name_with_a_digit_inside_needs_a_model(self) -> None:
        got = spoken("Areni-1 Cave")
        assert got["needs_model"] is True and got["reasons"] == ["digit"]

    def test_a_name_over_forty_characters_needs_a_model(self) -> None:
        got = spoken("Cathedral and Churches of Echmiatsin and the Archaeological Site")
        assert got["needs_model"] is True and "too_long" in got["reasons"]

    def test_a_name_of_one_generic_word_needs_a_model(self) -> None:
        got = spoken("Tumulus 4")
        assert got["needs_model"] is True and "generic_only" in got["reasons"]

    def test_a_name_that_is_too_short_needs_a_model(self) -> None:
        got = spoken("Ur")
        assert got["needs_model"] is True and got["reasons"] == ["too_short"]

    def test_a_form_in_capitals_is_not_spoken(self) -> None:
        got = spoken("Dolmen de Menga", ("MENGA DOLMEN", "alias"))
        assert got["needs_model"] is True

    def test_the_shortest_of_several_forms_wins(self) -> None:
        got = spoken(
            "The Ancient City of Pergamon",
            ("Ancient City of Pergamon", "alias"),
            ("Pergamon", "label"),
        )
        assert got["spoken"] == "Pergamon"


class TestTheBuild:
    def test_the_forms_come_from_the_item_the_names_table_and_the_article(self, tmp_path) -> None:
        defective = site(name="Pumamarka, Urubamba")
        store = store_of(
            tmp_path,
            {"Q1": entity("Q1", label="Pumamarka", aliases=("Puma Marka",))},
            {},
        )
        exported = export_of(
            [defective, site(name="Clean Name")],
            ext_ids=[
                ext(defective["id"], "wikidata_qid", "Q1"),
                ext(defective["id"], "enwiki_title", "Pumamarka_(Urubamba)"),
            ],
            names=[
                {
                    "site_id": defective["id"],
                    "name": "Pumamarca",
                    "name_type": "wikidata_alias",
                    "language_code": "en",
                },
                {
                    "site_id": defective["id"],
                    "name": "Pumamarka Site",
                    "name_type": "label",
                    "language_code": None,
                },
            ],
        )
        triage, spoken_rows, counts = N.build(exported, store)
        assert [r["name"] for r in triage] == ["Pumamarka, Urubamba"]
        assert triage[0]["suggestion"]["value"] == "Pumamarka"
        assert triage[0]["aliases"] == ["Pumamarca", "Puma Marka"]
        assert counts["defective"] == 1 and counts["defective_suggested"] == 1
        assert len(spoken_rows) == 2 and counts["spoken_by_rule"] == 2
        # the site's own label row is an attested form of the name, not an English alias
        forms = next(r for r in spoken_rows if r["id"] == defective["id"])["attested"]
        assert "Pumamarka Site" in forms

    def test_a_missing_item_is_counted_and_the_name_is_still_triaged(self, tmp_path) -> None:
        s = site(name="Foo, Bar")
        triage, _, counts = N.build(
            export_of([s], ext_ids=[ext(s["id"], "wikidata_qid", "Q9")]), store_of(tmp_path, {}, {})
        )
        assert counts["entity_missing"] == 1 and len(triage) == 1

    def test_the_hard_defects_come_before_the_comma_only_ones(self, tmp_path) -> None:
        a, b = site(name="Aaa, Bbb"), site(name="Zzz 9")
        triage, _, _ = N.build(export_of([a, b]), store_of(tmp_path, {}, {}))
        assert [r["name"] for r in triage] == ["Zzz 9", "Aaa, Bbb"]
