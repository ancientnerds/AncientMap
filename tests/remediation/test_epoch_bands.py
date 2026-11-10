"""The D136 table `EPOCH_BANDS.md` is written from `pipeline.periods.epoch_band` (owner decision
D136, 2026-11-07): one row per epoch, and the countries whose own start lies in another band."""

from __future__ import annotations

from pipeline import periods as P
from scripts.remediation.fields import epoch_bands as EB


def test_the_table_has_one_row_per_epoch() -> None:
    rows = [line for line in EB.table().splitlines() if line.startswith("| ") and "---" not in line]
    assert len(rows) - 1 == len(P.PERIODS)  # less the header row


def test_a_row_names_its_band_its_edge_and_the_countries_in_another_band() -> None:
    row = next(line for line in EB.table().splitlines() if line.startswith("| bronze age |"))
    assert "| 3000 - 1500 BC | -3000 |" in row
    assert "4500 - 3000 BC: " in row and "greece" in row
    assert "1500 - 500 BC: finland" in row


def test_a_country_in_the_conventional_band_is_not_listed() -> None:
    assert "england" not in str(EB.other_bands("bronze age"))
    assert EB.other_bands("victorian") == {}


def test_a_period_word_that_names_another_thing_is_no_epoch_of_the_site() -> None:
    for text, key in [
        ("There is access to the site and The Drift is part of the Viking Way trail.", "viking"),
        ("Telmessos (Hittite: Kuwalapassa) was a city", "hittite"),
        ("petroglyphs, primarily lines, geometric shapes", "geometric"),
        ("situated in the Chavin de Huantar District", "chavin"),
        ("at the entrance to the old Roman tunnel known as the Crypta Neapolitana", "roman"),
        ("Roman Rig", "roman"),
    ]:
        assert EB.names_another_thing(text, key), text
    for text, key in [
        ("Rockbourne Roman Villa is a Roman villa", "roman"),
        ("Cadbury Castle is an Iron Age Hillfort close to Bickleigh", "iron age"),
        ("a sanctuary of the Geometric period", "geometric"),
    ]:
        assert not EB.names_another_thing(text, key), text


def test_a_generic_article_cached_for_a_site_is_not_its_own() -> None:
    assert not EB.shares_a_word("Hillfort", "Dinas Dinlle")
    assert EB.shares_a_word("Dundon Hill Hillfort", "Compton Dundon")
    assert EB.shares_a_word("Kerzérho", "Alignements de Kerzerho")


# ------------------------------------------------- D137: the reading errors of the spot checks
def test_finds_in_the_area_are_not_the_site_s_epoch() -> None:
    # Sotin (spot check 1): the Copper Age of the area, not of the La Tene settlement
    sentence = ("Archaeological finds speak of life in the Sotin area from the Copper Age to the "
                "Younger Iron Age")  # fmt: skip
    assert EB.sentence_veto(sentence, "copper age") == "area"
    assert EB.sentence_veto("traces in the surroundings of the site from the Neolithic",
                            "neolithic") == "area"  # fmt: skip
    assert EB.sentence_veto("an Iron Age hillfort in the area of the village", "iron age") is None


def test_a_feature_next_to_the_site_is_not_the_site() -> None:
    # Berry Camp (spot check 1): the adjoining field system is prehistoric, the hillfort Iron Age
    sentence = "The hillfort dates to the Iron Age and has an adjoining prehistoric field system."
    assert EB.sentence_veto(sentence, "prehistoric") == "beside"
    assert EB.sentence_veto(sentence, "iron age") is None
    assert EB.sentence_veto("It lies near the Roman fort of Vindolanda.", "roman") == "beside"


def test_a_later_renewal_is_not_the_start() -> None:
    sentence = "The fort was built in the Iron Age and reoccupied in the Roman period."
    assert EB.sentence_veto(sentence, "roman") == "renewal"
    assert EB.sentence_veto(sentence, "iron age") is None
    assert EB.sentence_veto("It was rebuilt in late antiquity.", "late antiquity") == "renewal"


def test_a_site_its_article_calls_renewed_has_no_start_in_its_period_of_use() -> None:
    # Dolno Gradište (spot check 1): P2348 late antiquity, the site "one of those renewed settlements"
    forms = ["Dolno Gradište", "Dolno Gradishte"]
    text = ("This is the period when fortification and restoration of existing defensive walls of "
            "important settlements began. The site of Dolno Gradishte is one of those renewed "
            "settlements.")  # fmt: skip
    assert EB.renewed_site([text], forms)
    assert not EB.renewed_site(["The church was renewed in 1890."], forms)
    assert not EB.renewed_site(["Dolno Gradishte is a hill fort."], forms)


def _hedged(sentence: str) -> bool:
    return " believed " in f" {sentence} " or " si pensa " in f" {sentence.casefold()} "


def test_a_period_word_in_the_name_of_a_site_its_source_calls_older_is_no_start() -> None:
    # Inca Uyo (both spot checks): "important in pre-Inca times"
    lead = ("The site was important in pre-Inca times and described by Pedro Cieza de León who was "
            "told by the locals that nearby village of Chucuito was the oldest site in the region "
            "and continued to be held as a sacred site by the Inca.")  # fmt: skip
    assert EB.name_veto("inca", [lead], hedged=_hedged) == "older-or-later"
    assert EB.name_veto("roman", ["a post-Roman settlement"], hedged=_hedged) == "older-or-later"
    assert EB.name_veto("minoan", ["Modi is a Minoan peak sanctuary."], hedged=_hedged) is None
    assert EB.name_veto("minoan", [], hedged=_hedged) is None  # the name alone still names it


def test_a_hedged_attribution_in_the_only_source_is_no_start() -> None:
    # Bomarzo (spot check 1): the only source hedges the Etruscan builder
    text = ("Dating to the 7th-6th century BC, the pyramid is believed to have served as an "
            "Etruscan sacrificial altar used by haruspices.")  # fmt: skip
    assert EB.name_veto("etruscan", [text], hedged=_hedged) == "hedged"
    assert EB.name_veto("etruscan", [text, "an Etruscan altar"], hedged=_hedged) is None


def test_a_dropped_late_is_read() -> None:
    # La Ribera de Algaida (spot check 1): "occupied during the late Copper Age"
    sentence = ("It has an area of 20 to 30 hectares, and was occupied during the late Copper Age "
                "(from the Argaric culture until the Roman Era).")  # fmt: skip
    assert EB.is_late(sentence, "copper age")
    assert not EB.is_late("a Copper Age settlement", "copper age")
    assert not EB.is_late("in the Late Neolithic", "neolithic")  # a key of its own


def test_a_stated_year_wins_over_the_epoch_start() -> None:
    # D137: the earliest year the site's own source states, not after the epoch's end
    years = [{"years": [401], "sentence": "occupied until the 5th century"},
             {"years": [-300, -100], "sentence": "constructed in the third or 2nd century BCE"}]  # fmt: skip
    assert EB.stated_start(years, "iron age")["year"] == -300
    assert EB.stated_start([{"years": [401], "sentence": "x"}], "iron age") is None
    assert EB.stated_start([], "roman") is None


def test_a_coarse_word_takes_the_band_of_the_site_s_monument_type() -> None:
    site = {"site_type": "Dolmen", "name": "West Lanyon Quoit", "country": "England"}
    band = EB.option("prehistoric", site, "the remains of a prehistoric dolmen")
    assert (band["epoch"], band["band"], band["coarse_word"], band["type_word"]) == (
        "neolithic", "4500 - 3000 BC", "prehistoric", "dolmen")
    site = {"site_type": "Megalithic stones", "name": "Ringmoor", "country": "England"}
    band = EB.option("prehistoric", site, "a prehistoric stone row and cairn circle")
    assert (band["epoch"], band["band"]) == ("bronze age", "3000 - 1500 BC")
    site = {"site_type": "Archaeological site", "name": "Snowden Crags", "country": "England"}
    band = EB.option("prehistoric", site, "a prehistoric archaeological site")
    assert (band["epoch"], band["band"]) == ("prehistoric", "< 4500 BC")
    assert "type_word" not in band
    site = {"site_type": "Fort", "name": "Eggardon Hill", "country": "England"}
    assert EB.option("iron age", site, "a hillfort")["epoch"] == "iron age"


def test_a_late_phase_takes_the_band_of_its_end() -> None:
    site = {"site_type": "City/town/settlement", "name": "La Ribera", "country": "Spain"}
    band = EB.option("copper age", site, "occupied during the late Copper Age")
    assert (band["band"], band["late"]) == ("3000 - 1500 BC", True)


def test_a_place_phrase_naming_where_the_site_lies_is_no_area_veto() -> None:
    # Trialeti: "rock art in the Trialeti area ... from the Mesolithic" is the site's own epoch
    sentence = ("Trialeti petroglyphs is prehistoric rock art in the Trialeti area, in the Tsalka "
                "Municipality, engraved over a number of periods from the Mesolithic to the Middle "
                "Bronze Age.")  # fmt: skip
    assert EB.sentence_veto(sentence, "mesolithic", forms=["Trialeti petroglyphs"]) is None
    # Plataea: the site is named between the finds of the area and its epoch
    sentence = ("From the archaeological finds in the area, it is clear that Ancient Plataea existed "
                "from Mycenaean times (1400-1200 B.C.).")  # fmt: skip
    assert EB.sentence_veto(sentence, "mycenaean", forms=["Ancient Plataea", "Plataea"]) is None
    sentence = ("Archaeological finds speak of life in the Sotin area from the Copper Age to the "
                "Younger Iron Age")  # fmt: skip
    assert EB.sentence_veto(sentence, "copper age", forms=["Sotin"]) == "area"


def test_a_year_of_a_find_or_a_neighbour_is_not_the_site_s() -> None:
    forms = ["Burfa Castle", "Caer y Twr"]
    assert EB.year_veto("Material dating from the 1st and 2nd century CE has been found at the "
                        "site.", forms) == "find"  # fmt: skip
    assert EB.year_veto("Nestled below Caer y Twr is a group of several enclosed huts that also "
                        "date from the 3rd to the 4th centuries.", forms) == "neighbour"  # fmt: skip
    assert EB.year_veto("The main fort was constructed in the 3rd century BCE.", forms) is None


def test_a_number_of_a_measure_is_no_year() -> None:
    sentence = ("The headland is the site of earthwork remains of a 170-metre (560 ft) by 160-metre "
                "(520 ft) cliff castle, dated to the Iron Age.")  # fmt: skip
    assert EB.is_a_measure(sentence, 160)
    assert not EB.is_a_measure("built in 160 AD", 160)


def test_a_tentative_or_debated_date_is_not_stated() -> None:
    for sentence in [
        "Its plan has prompted debate over whether it is Iron Age or Roman, dated tentatively to "
        "the 2nd-1st century BC.",
        "Its construction has not yet been dated with certainty; the construction style would "
        "indicate the 2nd or 3rd century.",
        "Its construction date remains debated.",
    ]:
        assert EB._DOUBT.search(sentence), sentence


def test_the_year_of_a_last_event_is_not_the_start() -> None:
    # Sacul: "The last stela erected in Sacul bears a date corresponding to AD 800."
    assert EB.year_veto("The last stela erected in Sacul bears a date corresponding to AD 800.",
                        ["Sacul"]) == "later-event"  # fmt: skip


def test_a_century_the_sentence_gives_the_site_itself_is_a_stated_year() -> None:
    # Early Roman House (spot check 2): "a 1st-century AD residential structure"
    assert EB.attributive_century("The Early Roman House is a 1st-century AD residential structure "
                                  "within the Paphos Archaeological Park.") == 1  # fmt: skip
    assert EB.attributive_century("It was a 3rd-century BC temple.") == -300
    assert EB.attributive_century("It is a 12th century church.") == 1101
    assert EB.attributive_century("It was rebuilt in the 3rd century.") is None
    assert EB.attributive_century("a 2nd-century coin was found") is None
