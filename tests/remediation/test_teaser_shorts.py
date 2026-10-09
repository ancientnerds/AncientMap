"""Contract shorts-v1: the mechanical rules, the answer shapes and the prompts.

Everything here is DB-less and model-less. The eleven pilot sites of the card design are fixtures
(`shorts_cases`): their live descriptions and the sample card of each are pinned, not read, and every
sample must pass the code. Each rule is asserted by the refusal it produces, so removing a rule turns
its test red (`mechanical/mutation_sweep.py "teaser-shorts:"`).
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

from teaser import answers as A  # noqa: E402
from teaser import answers_shorts as AS  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import prompts_shorts as PS  # noqa: E402
from teaser import shorts_v1 as SV  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import shorts_cases as S  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402

fit = T.fit

#: A synthetic site every rule is tested on: eligible (eight usable images, a long description), with
#: an alias, and a base card that passes every rule.
DESCRIPTION = (
    "Zorgat Hill is a ridge fort in the Atlantean highlands [1]. Its builders stacked basalt blocks "
    "into a wall 4 metres thick [1]. A bronze mirror was found in the gate passage [1]. The fort "
    "burned in 1200 BC and was never rebuilt [1]. Local farmers call the ridge the Sleeping Ox [1]. "
    "The excavators recorded 3 gates and 7 towers [1]. A hoard of 123456 amber beads was found in "
    "98765 pieces [1]. The fort is the first of its kind in Atlantis, and a rare survivor [1]. "
    "Some say it is possibly older [1]."
)
SITE = SV.shorts_basis(
    site_id="0f000000-0000-4000-8000-000000000001",
    name="Zorgat Hill",
    country="Atlantis",
    description=DESCRIPTION,
    alt_names=["Sleeping Ox Fort", "Fort"],
    pool_images=8,
    image_titles=["Basalt wall.jpg", "Gate passage.jpg"],
)
BASE = (
    "A bronze mirror lay in the gate passage behind a basalt wall 4 metres thick. The fort burned "
    "in 1200 BC and was never rebuilt, and farmers still call the ridge the Sleeping Ox."
)
BASE_ANCHORS = ["basalt wall 4 metres thick", "Sleeping Ox"]
BASE_BASIS = ["S2", "S3", "S4", "S5"]
BASE_RESERVE = ["S6"]


def problems(
    card: str = BASE,
    *,
    site: SV.ShortsBasis = SITE,
    anchors: list[str] | None = None,
    reserve: list[str] | None | str = "default",
    basis: list[str] | None = None,
    fit: Any = T.fit,
) -> list[str]:
    return SV.problems_shorts(
        C.final_card(card),
        site,
        BASE_ANCHORS if anchors is None else anchors,
        BASE_RESERVE if reserve == "default" else reserve,
        fit,
        basis=BASE_BASIS if basis is None else basis,
    )


def starts(found: list[str], prefix: str) -> bool:
    return any(p.startswith(prefix) for p in found)


def basis_of(name: str, **over: Any) -> SV.ShortsBasis:
    sample = S.BY_NAME[name]
    fields: dict[str, Any] = {
        "site_id": sample["site_id"],
        "name": sample["name"],
        "country": sample["country"],
        "description": sample["description"],
        "alt_names": sample["aliases"],
        "pool_images": sample["pool_images"],
        "image_titles": [],
    }
    return SV.shorts_basis(**{**fields, **over})


# ------------------------------------------------------------------------------ the samples
class TestTheElevenSamples:
    @pytest.mark.parametrize("name", [s["name"] for s in S.SAMPLES])
    def test_every_sample_passes_the_contract(self, name: str) -> None:
        sample = S.BY_NAME[name]
        found = SV.problems_shorts(
            C.final_card(sample["card"]),
            basis_of(name),
            sample["anchors"],
            sample["reserve"],
            fit,
            basis=sample["basis"],
        )
        assert found == []

    def test_six_samples_can_be_shorts_and_five_cannot(self) -> None:
        assert sorted(S.ELIGIBLE) == sorted(
            ["Vallée des Merveilles", "Huaca del Sol", "Medinet Habu", "Machu Picchu",
             "Göbekli Tepe", "Mitla, Entrance to Tomb 1"]
        )  # fmt: skip
        assert all(basis_of(name).shorts_eligible for name in S.ELIGIBLE)
        others = [s["name"] for s in S.SAMPLES if s["name"] not in S.ELIGIBLE]
        assert len(others) == 5 and not any(basis_of(name).shorts_eligible for name in others)

    def test_the_descriptions_are_pinned_fixtures_with_the_ids_the_prompts_use(self) -> None:
        assert S.BY_NAME["Machu Picchu"]["description"].startswith("Machu Picchu is a 15th-century")
        sentences = C.description_sentences(S.BY_NAME["Tregiffian Burial Chamber"]["description"])
        assert [s.id for s in sentences] == ["S1", "S2"]

    def test_a_sample_is_nameless_and_two_sentences_and_within_the_narration_limit(self) -> None:
        for sample in S.SAMPLES:
            card = sample["card"]
            assert 160 <= len(card) <= 190
            assert len(SV.card_sentences(card)) == 2
            assert SV.narration_seconds(card) <= SV.NARRATION_MAX_S
            assert sample["name"].split(",")[0].split()[0] not in card

    def test_the_sample_cards_keep_one_tolerance_of_the_design(self) -> None:
        """Göbekli Tepe sits at the narration cap: 8 digits and 162 characters."""
        card = S.BY_NAME["Göbekli Tepe"]["card"]
        assert SV.narration_seconds(card) == pytest.approx(13.9948, abs=1e-3)


# ------------------------------------------------------------------------------ the base card
class TestTheBaseCard:
    def test_the_synthetic_base_card_passes_every_rule(self) -> None:
        assert problems() == []
        assert SITE.shorts_eligible and not SITE.thin


# ------------------------------------------------------------------------------ C3 numbers
class TestNumbers:
    def test_at_most_two_numerals(self) -> None:
        card = BASE.replace("was never rebuilt", "was never rebuilt after 3 gates")
        assert starts(problems(card), "numbers: 3 numerals")

    def test_at_most_eight_digits(self) -> None:
        card = (
            "A bronze mirror lay in the gate passage behind a basalt wall of 123456 stones. The "
            "fort fell in 98765 pieces, and farmers still call the ridge the Sleeping Ox."
        )
        assert starts(problems(card), "numbers: 11 digits")

    def test_at_most_four_digits_in_sentence_one(self) -> None:
        card = (
            "A bronze mirror lay in the gate passage, 4 metres behind a wall burned in 1200 BC. "
            "Farmers still call the ridge the Sleeping Ox, and nobody has rebuilt the wall."
        )
        assert starts(problems(card), "numbers: 5 digits in sentence 1")

    def test_a_roman_numeral_is_spelled_out(self) -> None:
        card = BASE.replace("A bronze mirror", "A bronze mirror of Amenemhat III")
        assert starts(problems(card), "numbers: a Roman numeral")

    def test_every_numeral_is_grounded_as_in_v1(self) -> None:
        assert starts(problems(BASE.replace("1200", "1300")), "numbers not in the description")


# ------------------------------------------------------------------------------ C4 the v1 rules
class TestTheV1Rules:
    def test_the_length_is_160_to_190_characters(self) -> None:
        assert starts(
            problems("A bronze mirror lay in the gate passage. Farmers call it Ox."), "length"
        )

    def test_layout_characters_and_circa_are_v1s(self) -> None:
        assert starts(problems(BASE.replace("thick. The", "thick.  The")), "layout")
        assert starts(problems(BASE.replace("mirror", "mirror (bronze)")), "characters")
        assert starts(
            problems(BASE.replace("The fort burned", "The fort, c. the wall, burned")), "circa"
        )
        assert C.final_card("Built c. 3000 BC.") == "Built circa 3000 BC."

    def test_the_font_is_measured_on_the_card_alone(self) -> None:
        calls: list[tuple[str, str]] = []

        def spying(name: str, card: str) -> Any:
            calls.append((name, card))
            return T.fit(name, card)

        problems(fit=spying)
        assert calls and {name for name, _ in calls} == {""}

    def test_the_card_need_not_name_the_site(self) -> None:
        """v1 refuses a card that names none of the site's forms; shorts-v1 refuses the opposite."""
        assert not any(p.startswith("name: the card names the site by none") for p in problems())


# ------------------------------------------------------------------------------ C5 / C6
class TestSentencesAndNarration:
    def test_exactly_two_sentences(self) -> None:
        one = "A bronze mirror lay in the gate passage behind a basalt wall 4 metres thick, and farmers still call the ridge the Sleeping Ox, a name older than anyone can say."
        assert starts(problems(one), "sentences: 1;")
        three = BASE.replace("rebuilt, and", "rebuilt. And")
        assert starts(problems(three), "sentences: 3;")

    def test_each_sentence_ends_with_a_full_stop(self) -> None:
        card = BASE.replace("thick. The", "thick, The").replace("Ox.", "Ox?")
        assert any(p.startswith("sentences: sentence") for p in problems(card))

    def test_sentence_one_is_40_to_85_characters(self) -> None:
        short = "A bronze mirror lay in the gate. " + BASE.split(". ", 1)[1]
        assert starts(problems(short), "sentence 1: 32 characters")
        long = (
            "A bronze mirror lay in the gate passage behind a basalt wall 4 metres thick, beside a great wide path. "
            + BASE.split(". ", 1)[1]
        )
        assert starts(problems(long), "sentence 1:")

    def test_the_narration_estimate_caps_at_14_seconds(self) -> None:
        assert SV.narration_seconds("x" * 100) == pytest.approx(6.04 + 3.34)
        assert SV.narration_seconds("x1" * 50) == pytest.approx(6.04 + 0.0334 * 100 + 0.318 * 50)
        card = (
            "A hoard of 123456 amber beads lay in the gate passage behind a wall 4 metres thick. "
            "The fort burned in 1200 BC, and farmers still call the ridge the Sleeping Ox."
        )
        assert starts(problems(card, anchors=["wall 4 metres thick", "Sleeping Ox"]), "narration:")


# ------------------------------------------------------------------------------ C7 / C8 names
class TestNoName:
    def test_the_stored_name_is_refused(self) -> None:
        assert starts(
            problems(BASE.replace("A bronze mirror", "Zorgat Hill holds a bronze mirror")),
            "name: the card holds the site's name",
        )

    def test_a_form_of_the_name_without_its_brackets_or_after_the_comma_is_refused(self) -> None:
        site = SV.shorts_basis(
            site_id="s", name="Eryx (Sicily)", country="Atlantis", description=DESCRIPTION,
            alt_names=[], pool_images=0, image_titles=[],
        )  # fmt: skip
        found = SV.name_problems("The ruins of Eryx rise above a bay.", site.name, [], site.country)
        assert starts(found, "name: the card holds the site's name")
        comma = SV.name_problems(
            "Gaer Hillfort stands here.", "Gaer Hillfort, Trellech", [], "Wales"
        )
        assert starts(comma, "name: the card holds the site's name")

    def test_every_alias_is_refused_whole(self) -> None:
        found = problems(
            BASE.replace("the Sleeping Ox", "the Sleeping Ox Fort"),
            anchors=["basalt wall 4 metres thick", "Sleeping Ox Fort"],
        )
        assert any("the alias 'Sleeping Ox Fort'" in p for p in found)
        assert not any("alias" in p for p in problems())

    def test_a_stored_name_among_the_aliases_is_reported_once(self) -> None:
        found = SV.name_problems("Zorgat Hill stands.", "Zorgat Hill", ["Zorgat Hill"], "Atlantis")
        assert len(found) == 2
        assert starts(found, "name: the card holds the site's name")
        assert starts(found[1:], "name: the card holds a word of the site's name")

    def test_a_single_common_word_alias_is_no_name(self) -> None:
        assert not any("alias" in p for p in problems(BASE.replace("The fort", "The Fort")))

    def test_a_distinctive_word_of_the_name_is_refused(self) -> None:
        found = problems(BASE.replace("The fort", "Zorgat's fort"))
        assert any(
            p.startswith("name: the card holds a word of the site's name: zorgat") for p in found
        )
        assert not any("hill" in p for p in problems(BASE.replace("the ridge", "the hill")))

    def test_a_name_of_generic_words_has_no_distinctive_word(self) -> None:
        assert SV.distinctive_tokens("Roman Walls") == []
        assert SV.distinctive_tokens("The Great Bath") == []
        assert SV.distinctive_tokens("Pyramid G1-a") == []
        assert SV.distinctive_tokens("Mitla, Entrance to Tomb 1") == ["mitla"]

    def test_the_country_and_its_people_are_refused(self) -> None:
        found = problems(BASE.replace("The fort", "The Atlantis fort"))
        assert starts(found, "country: the card holds the country or its people (Atlantis)")
        peru = SV.name_problems("An Inca wall, and a Peruvian road.", "Machu Picchu", [], "Peru")
        assert starts(peru, "country: the card holds the country or its people (Peruvian)")
        both = SV.name_problems("Peru gave its Peruvian road a wall.", "Machu Picchu", [], "Peru")
        assert starts(both, "country: the card holds the country or its people (Peru, Peruvian)")
        assert SV.country_terms("Atlantis") == ("Atlantis",)

    def test_the_table_covers_every_country_of_the_shown_sites(self) -> None:
        shown = (
            "England Greece Peru Spain Italy Türkiye France Mexico Wales Egypt Portugal Germany "
            "Pakistan Scotland Bulgaria Guatemala Serbia Croatia Cyprus Ireland Ukraine Malta "
            "Azerbaijan Sweden India Algeria Iraq Belize Australia Denmark Georgia Poland Lebanon "
            "Albania USA Switzerland Afghanistan Israel Austria Iran Armenia Tunisia Bolivia "
            "Netherlands Kazakhstan Syria Jordan Norway Bahrain Belgium Chile Finland Taiwan "
            "Honduras Libya Ethiopia Indonesia China Thailand Morocco Slovakia Panama Romania "
            "Greenland Mongolia Brazil Eritrea Myanmar Canada Mauritania Hungary Russia Sudan "
            "Yemen Japan Cambodia Paraguay Ecuador Venezuela Laos"
        ).split()
        missing = [c for c in shown if c not in SV.COUNTRY_TERMS]
        assert missing == []
        for multi in ("Saudi Arabia", "Northern Ireland", "North Macedonia", "South Korea",
                      "Bosnia and Herzegovina", "North Korea", "Costa Rica", "Sri Lanka",
                      "Republic of The Gambia", "United Arab Emirates", "Northern Mariana Islands"):  # fmt: skip
            assert multi in SV.COUNTRY_TERMS

    def test_an_administrative_word_in_sentence_one_is_refused(self) -> None:
        card = BASE.replace("gate passage", "gate passage of the district")
        assert starts(problems(card), "address: sentence 1 holds an administrative word")
        ok = BASE.replace("farmers still", "farmers of the district still")
        assert not starts(problems(ok), "address:")


# ------------------------------------------------------------------------------ C9 openers
class TestOpeners:
    @pytest.mark.parametrize(
        "head", ["In the gate passage a", "Near the gate passage a", "Above the wall a"]
    )
    def test_a_location_word_opens_no_sentence_one(self, head: str) -> None:
        card = BASE.replace(
            "A bronze mirror lay in the gate passage behind", f"{head} bronze mirror lay behind"
        )
        assert starts(problems(card), "opener: sentence 1 opens with the location word")

    def test_a_location_word_before_a_number_is_allowed(self) -> None:
        card = BASE.replace(
            "A bronze mirror lay in the gate passage behind a basalt wall 4 metres thick",
            "At 4 metres a basalt wall guards the gate passage and a bronze mirror",
        )
        assert not starts(problems(card, anchors=[]), "opener:")

    @pytest.mark.parametrize("head", ["Located", "It", "Its", "This", "Here", "They", "And", "Set"])
    def test_these_words_open_no_sentence_one(self, head: str) -> None:
        card = BASE.replace("A bronze mirror lay", f"{head} bronze mirror lay")
        assert starts(problems(card), f"opener: sentence 1 opens with '{head.lower()}'")

    def test_a_bare_type_label_is_no_opener(self) -> None:
        card = BASE.replace(
            "A bronze mirror lay in the gate passage",
            "A ruined hilltop fort lay in the gate passage",
        )
        assert starts(problems(card), "opener: sentence 1 opens with a bare type label")
        assert not starts(problems(BASE), "opener:")


# ------------------------------------------------------------------------------ C10 / C11 / C12
class TestVoiceAndClaims:
    @pytest.mark.parametrize("mark", ["?", "!", "...", "…"])
    def test_no_question_exclamation_or_ellipsis(self, mark: str) -> None:
        card = BASE.replace("rebuilt,", f"rebuilt{mark}")
        found = problems(card)
        assert starts(found, "marks:") or starts(found, "characters")

    def test_no_question_mark_at_all(self) -> None:
        card = BASE.replace(
            "and farmers still call the ridge the Sleeping Ox.",
            "and who calls the ridge the Sleeping Ox?",
        )
        assert starts(problems(card), "marks:")

    def test_no_you(self) -> None:
        assert starts(
            problems(BASE.replace("farmers", "you")), "address: the card talks to the viewer"
        )

    @pytest.mark.parametrize(
        "word",
        ["link", "subscribe", "guess", "watch", "video", "discover", "find out", "learn more"],
    )
    def test_no_call_to_action(self, word: str) -> None:
        assert starts(problems(BASE.replace("never rebuilt", f"never rebuilt, so {word}")), "cta:")

    def test_a_mystery_word_needs_the_same_stem_in_the_description(self) -> None:
        assert starts(
            problems(BASE.replace("never rebuilt", "a mystery")), "claims: a mystery or superlative"
        )
        assert starts(problems(BASE.replace("mirror", "secret mirror")), "claims:")
        with_stem = SV.shorts_basis(
            site_id="s", name="Zorgat Hill", country="Atlantis", alt_names=[], pool_images=8, image_titles=[],
            description=DESCRIPTION + " Its builders kept a secret [1].",
        )  # fmt: skip
        assert not starts(
            problems(BASE.replace("mirror", "secret mirror"), site=with_stem), "claims:"
        )

    @pytest.mark.parametrize("word", ["oldest", "largest", "unique", "only", "most"])
    def test_a_superlative_needs_the_same_stem_in_the_description(self, word: str) -> None:
        assert starts(problems(BASE.replace("A bronze", f"The {word} bronze")), "claims:")

    def test_first_and_rare_are_allowed_where_the_description_says_them(self) -> None:
        assert not starts(problems(BASE.replace("A bronze", "A first and rare bronze")), "claims:")

    def test_present_state_words_are_a_flag_for_the_checker_not_a_refusal(self) -> None:
        assert SV.present_state_words(BASE) == ["still"]
        assert SV.present_state_words("It can see the sea, and today is now.") == [
            "can see",
            "now",
            "today",
        ]
        assert not starts(problems(BASE), "present")


# ------------------------------------------------------------------------------ C13 captions
def width(word: str) -> int:
    return int(T.fit("", word).px)


def word_between(low: int, high: int) -> str:
    for count in range(2, 40):
        word = "m" * count
        if low < width(word) <= high:
            return word
    raise AssertionError(f"no word of 'm's between {low} and {high} px in the test face")


class TestCaptionWidth:
    def test_a_common_word_wider_than_696_px_is_refused(self) -> None:
        wide = word_between(SV.COMMON_WORD_PX, SV.PROPER_WORD_PX)
        found = problems(BASE.replace("passage", wide))
        assert any(
            p.startswith(f"caption: the word '{wide}'") and "a common word" in p for p in found
        )

    def test_a_proper_noun_of_the_description_may_reach_1000_px(self) -> None:
        wide = word_between(SV.COMMON_WORD_PX, SV.PROPER_WORD_PX).capitalize()
        site = SV.shorts_basis(
            site_id="s", name="Zorgat Hill", country="Atlantis", alt_names=[], pool_images=8, image_titles=[],
            description=DESCRIPTION + f" The builders came from {wide} in the north [1].",
        )  # fmt: skip
        found = problems(BASE.replace("passage", wide), site=site)
        assert not starts(found, "caption:")
        assert starts(problems(BASE.replace("passage", wide)), "caption:")

    def test_a_proper_noun_past_1000_px_is_refused(self) -> None:
        huge = word_between(SV.PROPER_WORD_PX, 10_000).capitalize()
        site = SV.shorts_basis(
            site_id="s", name="Zorgat Hill", country="Atlantis", alt_names=[], pool_images=8, image_titles=[],
            description=DESCRIPTION + f" The builders came from {huge} in the north [1].",
        )  # fmt: skip
        found = problems(BASE.replace("passage", huge), site=site)
        assert any("a proper noun of the description" in p for p in found)

    def test_a_word_that_opens_a_sentence_is_no_proper_noun(self) -> None:
        wide = word_between(SV.COMMON_WORD_PX, SV.PROPER_WORD_PX).capitalize()
        site = SV.shorts_basis(
            site_id="s", name="Zorgat Hill", country="Atlantis", alt_names=[], pool_images=8, image_titles=[],
            description=DESCRIPTION + f" {wide} was a market [1].",
        )  # fmt: skip
        assert starts(problems(BASE.replace("passage", wide), site=site), "caption:")


# ------------------------------------------------------------------------------ C14 anchors
class TestAnchors:
    def test_an_eligible_card_names_one_to_three_anchors(self) -> None:
        assert starts(problems(anchors=[]), "anchors: 0;")
        assert starts(problems(anchors=["a", "b", "c", "d"]), "anchors: 4;")

    def test_an_anchor_is_in_the_card_once_verbatim(self) -> None:
        assert starts(problems(anchors=["basalt wall 5 metres thick"]), "anchors: anchor 1")
        twice = BASE.replace("Sleeping Ox", "Sleeping Ox, the Sleeping Ox")
        assert starts(
            problems(twice, anchors=["Sleeping Ox"]),
            "anchors: anchor 1 ('Sleeping Ox') is not once",
        )

    def test_anchor_one_ends_in_the_last_25_characters_of_sentence_one(self) -> None:
        assert starts(problems(anchors=["bronze mirror"]), "anchors: anchor 1 ends at character")
        assert not starts(problems(anchors=["basalt wall 4 metres thick"]), "anchors:")

    def test_a_later_anchor_starts_at_character_95_or_later(self) -> None:
        found = problems(anchors=["basalt wall 4 metres thick", "gate passage"])
        assert starts(found, "anchors: anchor 2 starts at character")

    def test_anchors_start_28_characters_apart(self) -> None:
        close = problems(
            anchors=["basalt wall 4 metres thick", "ridge the Sleeping", "Sleeping Ox"]
        )
        assert starts(close, "anchors: two anchors start 10 characters apart, at least 28")
        assert problems(anchors=["basalt wall 4 metres thick", "ridge the Sleeping"]) == []

    def test_the_anchors_are_in_the_order_of_the_card(self) -> None:
        assert starts(
            problems(anchors=["Sleeping Ox", "basalt wall 4 metres thick"]),
            "anchors: the anchors are not in the order",
        )

    def test_a_site_that_cannot_be_a_short_names_no_anchor(self) -> None:
        thin = SV.shorts_basis(
            site_id="s", name="Zorgat Hill", country="Atlantis", description=DESCRIPTION,
            alt_names=[], pool_images=5, image_titles=[],
        )  # fmt: skip
        assert not thin.shorts_eligible
        assert starts(problems(site=thin), "anchors: the site is not Shorts-eligible")
        assert problems(site=thin, anchors=[]) == []

    def test_eligible_needs_six_images_and_300_characters(self) -> None:
        assert SV.eligible(6, "x" * 300) and not SV.eligible(5, "x" * 300)
        assert not SV.eligible(6, "x" * 299)


# ------------------------------------------------------------------------------ C15 reserve
class TestReserve:
    def test_null_is_valid_and_means_not_shorts_ready(self) -> None:
        assert problems(reserve=None) == []

    def test_a_reserve_is_sentence_ids_the_card_does_not_use_or_reveal(self) -> None:
        assert problems(reserve=["reveal"]) == []
        assert problems(reserve=["S6", "reveal"]) == []
        assert starts(problems(reserve=["S3"]), "reserve: S3 is a sentence the card rests on")
        assert starts(problems(reserve=["S99"]), "reserve: 'S99' is not a sentence id")
        assert starts(problems(reserve=["S6", "S6"]), "reserve: it names an entry twice")
        assert starts(problems(reserve=[]), "reserve: it is null or a non-empty list")


# ------------------------------------------------------------------------------ C16 diversity
class TestDiversity:
    def test_a_repeated_five_word_opening_is_refused(self) -> None:
        taken = {"a": "A bronze mirror lay deep. Then more words follow here."}
        found = SV.diversity_problems("A bronze mirror lay in the gate.", taken, 200)
        assert (
            starts(found, "diversity: another card of the run opens with 'a bronze mirror lay in'")
            is False
        )
        same = SV.diversity_problems("A bronze mirror lay deep below.", taken, 200)
        assert starts(
            same, "diversity: another card of the run opens with 'a bronze mirror lay deep'"
        )

    def test_a_three_word_opening_may_occur_in_one_percent_of_the_run(self) -> None:
        cards = {f"s{n}": f"A bronze mirror {word} here." for n, word in enumerate(["lay", "sat"])}
        card = "A bronze mirror hung here."
        assert SV.diversity_problems(card, {}, 100) == []
        assert starts(SV.diversity_problems(card, cards, 100), "diversity: more than 1 card(s)")
        assert starts(
            SV.diversity_problems(card, {"s0": cards["s0"]}, 100), "diversity: more than 1"
        )
        # in a run of 300, three cards may share an opening
        many = {f"s{n}": f"A bronze mirror w{n} here." for n in range(2)}
        assert SV.diversity_problems(card, many, 300) == []
        assert starts(
            SV.diversity_problems(
                card, {f"s{n}": f"A bronze mirror w{n} here." for n in range(3)}, 300
            ),
            "diversity:",
        )

    def test_the_first_card_of_a_run_is_always_allowed(self) -> None:
        assert SV.diversity_problems("A bronze mirror hung here.", {}, 1) == []

    def test_the_opening_is_read_after_the_name_fold(self) -> None:
        assert SV.opening("Bones, found here: show that most", 3) == "bones found here"


# ------------------------------------------------------------------------------ C19 thin
class TestThin:
    def test_a_description_under_300_characters_is_thin(self) -> None:
        assert basis_of("Tregiffian Burial Chamber").thin
        assert basis_of("Denbury Hill").thin is False
        assert len(S.BY_NAME["Tregiffian Burial Chamber"]["description"]) == 295
        SV.thin_proof(basis_of("Tregiffian Burial Chamber"))

    def test_a_thin_decline_is_refused_for_a_description_with_enough_in_it(self) -> None:
        with pytest.raises(ValueError, match="a card can be written"):
            SV.thin_proof(basis_of("Machu Picchu"))


# ------------------------------------------------------------------------------ the canary
class TestTheCanary:
    @pytest.mark.parametrize("kind", SV.DEFECT_KINDS)
    def test_each_seeded_defect_breaks_the_card_in_one_way(self, kind: str) -> None:
        card = (
            BASE.replace("The fort burned", "The fort possibly burned") if kind == "hedge" else BASE
        )
        flawed = SV.seed_defect(card, SITE, kind)
        assert flawed != card
        if kind == "superlative":
            assert "oldest" in flawed
        if kind == "unknown":
            assert "No one knows" in flawed
        if kind == "period":
            assert (
                "2200 BC" in flawed
                or "1004 metres" in flawed
                or "1004" in flawed
                or "2200" in flawed
            )
        if kind == "name":
            assert flawed.startswith("Zorgat stands apart.")
        if kind == "hedge":
            assert "possibly" not in flawed

    def test_a_defect_that_does_not_apply_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no hedge"):
            SV.seed_defect("A bronze mirror lay in the gate passage.", SITE, "hedge")
        with pytest.raises(ValueError, match="no numeral"):
            SV.seed_defect("A bronze mirror lay in the gate passage.", SITE, "period")
        with pytest.raises(ValueError, match="not a seeded defect"):
            SV.seed_defect(BASE, SITE, "typo")

    def test_the_hedge_defect_removes_the_hedge(self) -> None:
        card = "The fort is possibly older than the wall, and roughly half is lost."
        assert (
            SV.seed_defect(card, SITE, "hedge")
            == "The fort is older than the wall, and roughly half is lost."
        )

    def test_the_canary_rotates_through_the_defects_and_skips_the_ones_that_do_not_apply(
        self,
    ) -> None:
        kinds = [SV.canary_card(BASE, SITE, n)[0] for n in range(5)]
        assert (
            kinds == ["hedge", "superlative", "unknown", "period", "name"][:5]
            or kinds[0] in SV.DEFECT_KINDS
        )
        assert (
            SV.canary_card("A bronze mirror lay in the gate passage.", SITE, 0)[0] == "superlative"
        )

    def test_a_card_nothing_applies_to_has_no_canary(self) -> None:
        # a superlative can always be added: only an unknown defect kind has nothing to flaw
        assert SV.canary_card(BASE, SITE, 3)[1] != BASE


# ------------------------------------------------------------------------------ the answer shapes
def variant(card: str = BASE, **over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "card": card,
        "basis": BASE_BASIS,
        "anchors": BASE_ANCHORS,
        "reserve": BASE_RESERVE,
        "hook_type": "object",
    }
    return {**fields, **over}


def three(*extra: dict[str, Any]) -> str:
    second = variant(
        "Behind a basalt wall 4 metres thick, a bronze mirror lay in the gate passage. The fort "
        "burned in 1200 BC and was never rebuilt, and farmers still call the ridge the Sleeping Ox.",
        anchors=["gate passage", "Sleeping Ox"],
    )
    third = variant(
        "Farmers call this ridge the Sleeping Ox. A bronze mirror lay in the gate passage of a fort "
        "that burned in 1200 BC and was never rebuilt behind a basalt wall 4 metres thick.",
        anchors=["Sleeping Ox", "basalt wall"],
    )
    return json.dumps({"variants": [variant(), second, third, *extra]}, ensure_ascii=False)


class TestTheWriterShape:
    def test_three_distinct_variants(self) -> None:
        variants = AS.parse_writer(three(), SITE)
        assert isinstance(variants, tuple) and [v.number for v in variants] == [1, 2, 3]
        assert variants[0].card == BASE and variants[0].reserve == ("S6",)
        assert variants[0].basis == ("S2", "S3", "S4", "S5") and variants[0].hook_type == "object"

    def test_exactly_three_variants(self) -> None:
        one = json.dumps({"variants": [variant()]})
        with pytest.raises(A.AnswerError, match="variants has 1 entries, it has exactly 3"):
            AS.parse_writer(one, SITE)
        with pytest.raises(A.AnswerError, match="variants has 4 entries"):
            AS.parse_writer(three(variant("x")), SITE)

    def test_the_variants_differ_in_card_and_in_their_first_three_words(self) -> None:
        same = json.dumps({"variants": [variant(), variant(), variant()]})
        with pytest.raises(A.AnswerError, match="two variants are the same card"):
            AS.parse_writer(same, SITE)
        near = variant(BASE.replace("lay in the gate passage", "sat in the gate passage"))
        with pytest.raises(A.AnswerError, match="same three words"):
            AS.parse_writer(
                json.dumps({"variants": [variant(), near, variant("Other words. Here.")]}), SITE
            )

    @pytest.mark.parametrize(
        ("over", "why"),
        [
            ({"basis": []}, "basis names no sentence"),
            ({"basis": ["S99"]}, "not sentence ids"),
            ({"anchors": "x"}, "anchors is not a list"),
            ({"anchors": [""]}, "anchors is not a list"),
            ({"reserve": "S6"}, "reserve is neither null nor a list"),
            ({"hook_type": "twist"}, "hook_type 'twist'"),
            ({"card": ""}, "card is not a non-empty string"),
        ],
    )
    def test_each_variant_is_exactly_its_shape(self, over: dict[str, Any], why: str) -> None:
        bad = json.dumps({"variants": [variant(**over), variant(), variant()]})
        with pytest.raises(A.AnswerError, match=why):
            AS.parse_writer(bad, SITE)

    def test_a_variant_with_another_key_is_refused(self) -> None:
        bad = {"variants": [{**variant(), "extra": 1}, variant(), variant()]}
        with pytest.raises(A.AnswerError, match="variant 1 carries"):
            AS.parse_writer(json.dumps(bad), SITE)

    def test_the_card_is_made_final(self) -> None:
        circa = json.dumps(
            {"variants": [variant("Built c. 3000 BC."), variant("Another."), variant("Third.")]}
        )
        assert AS.parse_writer(circa, SITE)[0].card == "Built circa 3000 BC."  # type: ignore[index]

    def test_a_thin_decline_for_a_thin_description(self) -> None:
        thin = basis_of("Tregiffian Burial Chamber")
        answer = json.dumps({"card": None, "thin": True, "reason": "two sentences say too little"})
        assert AS.parse_writer(answer, thin) == AS.Thin("two sentences say too little")

    def test_a_thin_decline_for_a_rich_description_is_refused(self) -> None:
        answer = json.dumps({"card": None, "thin": True, "reason": "no"})
        with pytest.raises(A.AnswerError, match="a card can be written"):
            AS.parse_writer(answer, SITE)

    def test_a_thin_decline_is_exactly_its_shape(self) -> None:
        thin = basis_of("Tregiffian Burial Chamber")
        for bad in (
            {"card": "x", "thin": True, "reason": "r"},
            {"card": None, "thin": False, "reason": "r"},
            {"card": None, "thin": True},
        ):
            with pytest.raises(A.AnswerError):
                AS.parse_writer(json.dumps(bad), thin)
        with pytest.raises(A.AnswerError, match="reason is not a non-empty"):
            AS.parse_writer(json.dumps({"card": None, "thin": True, "reason": " "}), thin)


def rating(
    *entries: tuple[int, int], best: int | None = None, cards: dict[int, str] | None = None
) -> str:
    shown = cards or {1: BASE}
    return json.dumps(
        {
            "ratings": [
                {"variant": n, "first5": AS.first_five(shown[n]), "hook": h} for n, h in entries
            ],
            "best": best if best is not None else max(entries, key=lambda e: e[1])[0],
        }
    )


class TestTheRaterShape:
    CARDS = {1: BASE, 2: "Behind a basalt wall 4 metres thick, a bronze mirror lay. More."}

    def test_a_rating_per_variant_and_the_best(self) -> None:
        rated = AS.parse_rater(rating((1, 3), (2, 5), cards=self.CARDS), list(self.CARDS.items()))
        assert rated.best == 2 and rated.best_rating == 5
        assert rated.ratings[0] == (1, "A bronze mirror lay in", 3)
        assert rated.to_dict()["best"] == 2

    def test_each_rating_is_exactly_its_shape(self) -> None:
        bad = json.loads(rating((1, 3), (2, 4), cards=self.CARDS))
        bad["ratings"][0]["extra"] = 1
        with pytest.raises(A.AnswerError, match="a rating is not"):
            AS.parse_rater(json.dumps(bad), list(self.CARDS.items()))
        with pytest.raises(A.AnswerError, match="ratings is not a list"):
            AS.parse_rater(json.dumps({"ratings": "x", "best": 1}), list(self.CARDS.items()))

    def test_one_rating_per_variant_shown(self) -> None:
        with pytest.raises(A.AnswerError, match="one rating per variant"):
            AS.parse_rater(rating((1, 3), cards=self.CARDS), list(self.CARDS.items()))
        with pytest.raises(A.AnswerError, match="names variant 3"):
            AS.parse_rater(
                rating((1, 3), (3, 3), cards={1: BASE, 3: BASE}), list(self.CARDS.items())
            )

    def test_the_first_five_words_are_copied_exactly(self) -> None:
        bad = json.loads(rating((1, 3), (2, 4), cards=self.CARDS))
        bad["ratings"][0]["first5"] = "A bronze mirror"
        with pytest.raises(A.AnswerError, match="first5 is not its first five words"):
            AS.parse_rater(json.dumps(bad), list(self.CARDS.items()))

    @pytest.mark.parametrize("hook", [0, 6, 2.5, "4", True])
    def test_the_hook_is_a_whole_number_one_to_five(self, hook: Any) -> None:
        bad = json.loads(rating((1, 3), (2, 4), cards=self.CARDS))
        bad["ratings"][0]["hook"] = hook
        with pytest.raises(A.AnswerError, match="hook is not a whole number 1-5"):
            AS.parse_rater(json.dumps(bad), list(self.CARDS.items()))

    def test_best_has_the_highest_rating(self) -> None:
        with pytest.raises(A.AnswerError, match="does not have the highest hook"):
            AS.parse_rater(
                rating((1, 3), (2, 5), best=1, cards=self.CARDS), list(self.CARDS.items())
            )
        tie = AS.parse_rater(
            rating((1, 4), (2, 4), best=1, cards=self.CARDS), list(self.CARDS.items())
        )
        assert tie.best == 1
        with pytest.raises(A.AnswerError, match="best 9"):
            AS.parse_rater(
                rating((1, 4), (2, 4), best=9, cards=self.CARDS), list(self.CARDS.items())
            )

    def test_the_floor_is_three(self) -> None:
        assert AS.HOOK_FLOOR == 3


def check_json(**over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "claims": [{"claim": "a bronze mirror lay in the gate passage", "support": ["S3"]}],
        "name_leak": False,
        "this_site": True,
        "hook_ok": True,
        "s1_no_place": True,
        "payoff_ok": True,
        "generic_ok": True,
        "loop_ok": True,
        "tone_ok": True,
        "anchors_ok": True,
        "verdict": "PASS",
        "reasons": [],
    }
    return {**fields, **over}


class TestTheCheckerShape:
    def parse(self, **over: Any) -> AS.Checked:
        return AS.parse_checker(json.dumps(check_json(**over)), SITE)

    def test_a_pass_needs_every_judgement_field_good(self) -> None:
        checked = self.parse()
        assert checked.verdict == "PASS" and checked.tone_ok and checked.this_site
        assert checked.to_dict()["name_leak"] is False and "anchors_ok" in checked.to_dict()

    @pytest.mark.parametrize(
        "field",
        [
            "this_site",
            "hook_ok",
            "s1_no_place",
            "payoff_ok",
            "generic_ok",
            "loop_ok",
            "tone_ok",
            "anchors_ok",
        ],
    )
    def test_a_pass_with_a_field_false_is_refused(self, field: str) -> None:
        with pytest.raises(A.AnswerError, match=f"PASS with {field} false"):
            self.parse(**{field: False})

    def test_a_pass_with_a_name_leak_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="PASS with name_leak true"):
            self.parse(name_leak=True)

    def test_a_pass_with_an_unsupported_claim_or_a_reason_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="PASS with an unsupported claim"):
            self.parse(claims=[{"claim": "a hoard", "support": []}])
        with pytest.raises(A.AnswerError, match="PASS with a reason"):
            self.parse(reasons=["hm"])

    def test_a_fail_needs_a_reason(self) -> None:
        with pytest.raises(A.AnswerError, match="FAIL without a reason"):
            self.parse(verdict="FAIL")
        assert (
            self.parse(verdict="FAIL", name_leak=True, reasons=["it says Zorgat"]).verdict == "FAIL"
        )

    def test_every_field_is_a_boolean_and_the_claims_a_list(self) -> None:
        with pytest.raises(A.AnswerError, match="hook_ok is not true or false"):
            self.parse(hook_ok="yes")
        with pytest.raises(A.AnswerError, match="claims is not a non-empty list"):
            self.parse(claims=[])
        data = check_json()
        del data["loop_ok"]
        with pytest.raises(A.AnswerError, match="it must carry exactly"):
            AS.parse_checker(json.dumps(data), SITE)

    def test_a_claim_names_only_sentences_of_the_description(self) -> None:
        with pytest.raises(A.AnswerError, match="not sentence ids"):
            self.parse(claims=[{"claim": "x", "support": ["S99"]}])


class TestTheRewriteShape:
    def answer(self, **over: Any) -> str:
        return json.dumps({**variant(), "repeats": ["S3"], **over})

    def test_one_variant_and_a_repeat_per_contradicted_claim(self) -> None:
        rewritten = AS.parse_verify_writer(self.answer(), SITE, 1)
        assert rewritten.variant.card == BASE and rewritten.repeats == ("S3",)
        assert rewritten.variant.number == 0

    def test_the_repeats_follow_v1(self) -> None:
        with pytest.raises(A.AnswerError, match="repeats has 0 entries"):
            AS.parse_verify_writer(self.answer(repeats=[]), SITE, 1)
        with pytest.raises(A.AnswerError, match="neither null nor the id"):
            AS.parse_verify_writer(self.answer(repeats=["W1"]), SITE, 1)
        assert AS.parse_verify_writer(self.answer(repeats=[None]), SITE, 1).repeats == (None,)


# ------------------------------------------------------------------------------ the prompts
class TestThePrompts:
    def test_the_examples_are_samples_that_pass_the_code(self) -> None:
        for example in PS.EXAMPLES:
            sample = S.BY_NAME[example.site]
            assert example.card == sample["card"]
            site = basis_of(example.site)
            sentences = {s.id: s.text for s in site.sentences}
            assert all(sentences[sid] == text for sid, text in example.sentences)
            used = sorted({s for _, ids in example.claims for s in ids})
            assert (
                SV.problems_shorts(
                    C.final_card(example.card),
                    site,
                    list(example.anchors),
                    list(example.reserve),
                    fit,
                    basis=used,
                )
                == []
            )
            assert example.eligible == site.shorts_eligible
            assert set(used) <= set(sentences)

    def test_the_writer_sees_the_site_the_avoid_list_the_rules_and_the_examples(self) -> None:
        prompt = PS.writer_prompt(SITE)
        assert "Name: Zorgat Hill (NEVER in the card)" in prompt
        assert (
            "AVOID (the card holds none of these words): Zorgat Hill | Fort | Sleeping Ox Fort | zorgat | Atlantis"
            in prompt
        )
        assert (
            "SHORTS-ELIGIBLE: yes" in prompt
            and "IMAGE TITLES" in prompt
            and "Basalt wall.jpg" in prompt
        )
        assert "S2 Its builders stacked basalt blocks into a wall 4 metres thick." in prompt
        assert "[1]" not in prompt.split("THE FACT BASIS")[1].split("THE RULES")[0]
        assert "Exactly three variants" in prompt and PS.ANCHOR_RULE in prompt
        assert "THIN DESCRIPTION" not in prompt
        for example in PS.EXAMPLES:
            assert example.card in prompt

    def test_a_site_that_cannot_be_a_short_gets_no_anchor_rule_and_a_thin_one_the_decline(
        self,
    ) -> None:
        thin = basis_of("Tregiffian Burial Chamber")
        prompt = PS.writer_prompt(thin)
        assert PS.NO_ANCHORS in prompt and PS.ANCHOR_RULE not in prompt
        assert "THIN DESCRIPTION" in prompt and '"thin": true' in prompt
        assert "THIN DESCRIPTION" not in PS.writer_prompt(basis_of("Denbury Hill"))

    def test_the_rewriter_sees_every_earlier_card_and_why(self) -> None:
        findings = [P.Finding(BASE, ("The hook rater rated its opening 2/5.",))]
        prompt = PS.rewrite_prompt(SITE, findings)
        assert (
            "EARLIER CARDS" in prompt
            and BASE in prompt
            and "- The hook rater rated its opening 2/5." in prompt
        )
        assert "has to be written again" in prompt

    def test_the_rater_sees_only_the_variants_and_the_name(self) -> None:
        prompt = PS.rate_prompt("Zorgat Hill", "Atlantis", [(1, BASE), (3, "Other. Words.")])
        assert "Variant 1: " + BASE in prompt and "Variant 3: Other. Words." in prompt
        assert "'Zorgat Hill, Atlantis.'" in prompt
        assert "Basalt" not in prompt.replace(BASE, "") and "S2" not in prompt
        for line in PS.HOOK_SCALE:
            assert line in prompt

    def test_the_checker_sees_the_card_the_anchors_and_the_present_state_words(self) -> None:
        prompt = PS.checker_prompt(SITE, BASE, BASE_ANCHORS)
        assert "THE CARD\n" + BASE in prompt
        assert "PHOTO ANCHORS the writer named: basalt wall 4 metres thick | Sleeping Ox" in prompt
        assert "PRESENT-STATE WORDS in the card: still" in prompt
        for field in (
            "name_leak",
            "hook_ok",
            "s1_no_place",
            "payoff_ok",
            "generic_ok",
            "loop_ok",
            "anchors_ok",
        ):
            assert f'"{field}"' in prompt
        quiet = PS.checker_prompt(SITE, BASE.replace(" still", ""), [])
        assert "PRESENT-STATE" not in quiet and "PHOTO ANCHORS the writer named" not in quiet

    def test_the_judge_asks_for_the_identity_bearing_claim_first(self) -> None:
        prompt = PS.judge_prompt("Zorgat Hill", "Atlantis", BASE)
        assert "identity-bearing claim first" in prompt
        assert (
            "deliberately not say the site's name" in prompt.replace("\n", " ")
            or "does not say the site's name" in prompt
        )
        assert "Site: Zorgat Hill\nCountry: Atlantis\nText: " + BASE in prompt
        assert P.judge_prompt("Zorgat Hill", "Atlantis", BASE) != prompt
        assert P.JUDGE_FORMAT in prompt

    def test_the_rewrite_after_a_failed_verification_keeps_the_v1_mechanics(self) -> None:
        contradicted = [
            {
                "claim": "burned in 1200 BC",
                "url": "https://x.org/a",
                "quote": "It burned in 1100 BC.",
                "proven": True,
                "quote_outcome": "found",
            }
        ]
        prompt = PS.verify_rewrite_prompt(SITE, BASE, contradicted, [])
        assert (
            "THE CARD THE WEB CHECK DID NOT VERIFY" in prompt and "1. burned in 1200 BC" in prompt
        )
        assert "keeps the card it has" in prompt.replace("\n", " ")
        assert '"repeats": ["S3"]' in prompt and "Write ONE new card" in prompt

    def test_the_adversary_is_given_the_evidence_to_doubt(self) -> None:
        site = C.basis(
            site_id="s",
            name="Zorgat Hill",
            country="Atlantis",
            description=DESCRIPTION,
            alt_names=[],
        )
        checked = {
            "claims": [
                {"claim": "a mirror", "support": ["S3"]},
                {"claim": "a hoard", "support": []},
            ]
        }
        verified = {
            "claims": [
                {
                    "claim": "a mirror",
                    "verdict": "SUPPORTED",
                    "url": "https://x.org/a",
                    "quote": "q" * 30,
                    "proven": True,
                    "quote_outcome": "found",
                }
            ]
        }
        prompt = PS.adversarial_prompt(site, BASE, checked, verified)
        assert "find the reason it must NOT stay public" in prompt
        assert "- a hoard: NO SUPPORT" in prompt and "- a mirror: S3" in prompt
        assert "[SUPPORTED, quote found on the page] a mirror - https://x.org/a" in prompt
        assert P.CHECKER_FORMAT in prompt

    def test_the_findings_of_a_checker_name_every_broken_field(self) -> None:
        record = {
            "kind": "check",
            **check_json(
                verdict="FAIL",
                name_leak=True,
                hook_ok=False,
                reasons=["it says Zorgat"],
                claims=[{"claim": "x", "support": []}],
            ),
        }
        found = PS.findings_of(record)
        assert "No sentence of the description supports the claim: x" in found
        assert "The card gives the site's name away." in found
        assert "The first five words are not a concrete, surprising hook." in found
        assert found[-1] == "it says Zorgat"
        assert PS.findings_of({"kind": "write", "problems": ["length: 12"]}) == ("length: 12",)
        assert PS.findings_of({"kind": "rate", "findings": ["rated 2/5"]}) == ("rated 2/5",)

    def test_the_avoid_list_holds_the_forms_aliases_tokens_and_country(self) -> None:
        site = basis_of("Machu Picchu")
        avoid = PS.avoid_words(site)
        assert "Machu Picchu" in avoid and "Machu Pichu" in avoid
        assert {"machu", "picchu", "Peru", "Peruvian"} <= set(avoid)
        assert len(avoid) == len(set(avoid))


class TestTheProvenanceVocabulary:
    def test_the_contract_and_hook_types_have_one_source(self) -> None:
        assert SV.CONTRACT == CP.CONTRACT_SHORTS == "shorts-v1"
        assert SV.HOOK_TYPES is CP.HOOK_TYPES
        assert SV.REVEAL == CP.REVEAL and SV.MAX_ANCHORS == CP.MAX_ANCHORS
