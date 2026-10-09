"""The subtle seeded defects of the checker's calibration (`shorts_v1.seed_subtle`).

Calibration teaser-2026-10-09b/c: `checker_defects` was 30 of 30 for both models because 11 of its
defects were an appended superlative and one a removed hedge, while both models pass real cards that
drop 'largely', widen 'many' to all, drop the saga's attribution or give an original height as the
current one. Each subtle kind changes the one word the claim hangs on and nothing else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from teaser import calibrate as K  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import shorts_v1 as SV  # noqa: E402

SITE = C.basis(
    site_id="0a000000-0000-4000-8000-000000000001",
    name="Zorgat Hill",
    country="Atlantis",
    description="Zorgat Hill is a ridge fort [1].",
    alt_names=[],
)

CASES = {
    "qualifier": (
        "The fort was largely rebuilt in stone. A mirror lay in the gate.",
        "The fort was rebuilt in stone. A mirror lay in the gate.",
        "The fort was rebuilt in stone.",
    ),
    "quantifier": (
        "Many coins lay in the hoard. The pot was plain.",
        "All coins lay in the hoard. The pot was plain.",
        "All coins lay in the hoard.",
    ),
    "attribution": (
        "According to the saga, the broch was besieged. The wall still stands.",
        "The broch was besieged. The wall still stands.",
        "The broch was besieged.",
    ),
    "original": (
        "The pyramid originally stood 62 metres high. Its core is mud brick.",
        "The pyramid stood 62 metres high. Its core is mud brick.",
        "The pyramid stood 62 metres high.",
    ),
    "scope": (
        "It is the largest standing stone in Ireland. Wind howls here.",
        "It is the largest standing stone. Wind howls here.",
        "It is the largest standing stone.",
    ),
}


class TestEachSubtleKindChangesOneWordAndNothingElse:
    @pytest.mark.parametrize("kind", sorted(CASES))
    def test_the_flaw_is_the_one_change(self, kind: str) -> None:
        card, flawed, sentence = CASES[kind]
        seeded = SV.seed_subtle(card, kind)
        assert (seeded.kind, seeded.subtle) == (kind, True)
        assert seeded.card == flawed
        assert seeded.sentence == sentence
        assert seeded.witness

    def test_a_find_gets_a_place_the_description_never_gave(self) -> None:
        seeded = SV.seed_subtle("A bone needle was found. A kiln was dug nearby.", "findspot")
        assert seeded.card == (
            "A bone needle was found. A kiln was dug nearby. "
            "The finds came from beneath the eastern wall."
        )
        assert seeded.sentence == "The finds came from beneath the eastern wall."
        assert seeded.witness == ("beneath", "eastern wall")

    def test_a_card_that_already_has_the_place_is_not_given_it_twice(self) -> None:
        with pytest.raises(ValueError, match="no find in the card"):
            SV.seed_subtle(
                "A needle was found beneath the eastern wall. A kiln was dug nearby.", "findspot"
            )

    @pytest.mark.parametrize(
        ("card", "flawed", "dropped"),
        [
            (
                "Over 80 men and women lay in one chamber.",
                "80 men and women lay in one chamber.",
                "over",
            ),
            (
                "Bones of up to twenty people were found.",
                "Bones of twenty people were found.",
                "up to",
            ),
            (
                "Around 4,300 dwellings stood in a valley.",
                "4,300 dwellings stood in a valley.",
                "around",
            ),
            ("It grew to more than 10,000 drawings.", "It grew to 10,000 drawings.", "more than"),
        ],
    )
    def test_a_bound_on_a_number_is_a_qualifier_too(
        self, card: str, flawed: str, dropped: str
    ) -> None:
        seeded = SV.seed_subtle(card, "qualifier")
        assert seeded.card == flawed and seeded.witness == (dropped,)

    def test_over_a_bay_is_no_bound(self) -> None:
        with pytest.raises(ValueError, match="no qualifier"):
            SV.seed_subtle("A cliff stands over a bay.", "qualifier")

    def test_a_name_in_the_subject_is_no_attribution(self) -> None:
        with pytest.raises(ValueError, match="no attribution"):
            SV.seed_subtle("Homer names this town in his Catalogue of Ships.", "attribution")

    @pytest.mark.parametrize(
        ("kind", "card"),
        [
            ("qualifier", "The fort burned. A mirror lay in the gate."),
            ("quantifier", "The fort burned. A mirror lay in the gate."),
            ("attribution", "The fort burned. A mirror lay in the gate."),
            ("original", "The fort burned. A mirror lay in the gate."),
            ("scope", "The fort burned. It is the largest fort."),
            ("findspot", "The fort burned. A mirror lay in the gate."),
        ],
    )
    def test_a_card_without_the_word_to_flaw_is_refused(self, kind: str, card: str) -> None:
        with pytest.raises(ValueError, match="no "):
            SV.seed_subtle(card, kind)

    def test_an_unknown_kind_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a subtle defect"):
            SV.seed_subtle("The fort burned.", "typo")

    def test_a_dropped_first_word_keeps_its_capital(self) -> None:
        seeded = SV.seed_subtle("Largely rebuilt, the fort stands. A mirror lay here.", "qualifier")
        assert seeded.card.startswith("Rebuilt, the fort stands.")

    def test_the_flawed_sentence_is_the_one_that_changed(self) -> None:
        seeded = SV.seed_subtle(
            "A mirror lay in the gate. The fort was mostly rebuilt in stone.", "qualifier"
        )
        assert seeded.sentence == "The fort was rebuilt in stone."


class TestTheRotation:
    CARD = "Many coins lay in the hoard, according to the saga. It is the largest hoard in Wales."

    def test_the_subtle_kinds_come_first_in_a_rotation_from_the_index(self) -> None:
        kinds = [SV.seeded_defect(self.CARD, SITE, n).kind for n in range(6)]
        # qualifier and original do not apply to the card: the rotation moves on to the next kind
        assert kinds == ["quantifier", "quantifier", "attribution", "scope", "scope", "quantifier"]
        assert all(SV.seeded_defect(self.CARD, SITE, n).subtle for n in range(6))

    def test_a_card_no_subtle_kind_applies_to_gets_a_blunt_defect_reported_as_blunt(self) -> None:
        seeded = SV.seeded_defect("A bronze mirror lay in the gate passage.", SITE, 0)
        assert seeded.subtle is False and seeded.kind in SV.DEFECT_KINDS
        assert seeded.witness == ()
        assert seeded.sentence

    def test_the_production_canary_is_unchanged(self) -> None:
        kinds = {SV.canary_card(self.CARD, SITE, n)[0] for n in range(5)}
        assert kinds <= set(SV.DEFECT_KINDS)
        assert set(SV.SUBTLE_KINDS).isdisjoint(SV.DEFECT_KINDS)


# ------------------------------------------------------------------------------ naming the claim
def case(sentence: str, witness: list[str]) -> dict[str, object]:
    return {"recorded": {"sentence": sentence, "witness": witness, "defect": "qualifier"}}


class TestNamingTheClaim:
    SENTENCE = "The fort was rebuilt in stone."

    def check(self, claims: list[tuple[str, list[str]]], reasons: list[str]) -> dict[str, object]:
        return {
            "claims": [{"claim": c, "support": s} for c, s in claims],
            "reasons": reasons,
            "verdict": "FAIL",
        }

    def test_an_unsupported_claim_that_is_the_flawed_sentence_names_it(self) -> None:
        check = self.check([("The fort was rebuilt in stone", [])], ["No."])
        assert K.names_the_claim(check, case(self.SENTENCE, ["largely"]))

    def test_a_reason_that_quotes_the_dropped_word_beside_the_sentence_names_it(self) -> None:
        check = self.check([("x", ["S1"])], ["The card drops 'largely' from the rebuilt fort."])
        assert K.names_the_claim(check, case(self.SENTENCE, ["largely"]))

    def test_the_dropped_word_alone_names_nothing(self) -> None:
        check = self.check([("x", ["S1"])], ["Largely a matter of taste."])
        assert not K.names_the_claim(check, case(self.SENTENCE, ["largely"]))

    def test_a_fail_for_another_reason_catches_no_subtle_defect(self) -> None:
        check = self.check([("A mirror lay in the gate", [])], ["The hook is weak."])
        assert not K.names_the_claim(check, case(self.SENTENCE, ["largely"]))

    def test_a_supported_claim_is_not_a_finding(self) -> None:
        check = self.check([("The fort was rebuilt in stone", ["S1"])], ["Tone."])
        assert not K.names_the_claim(check, case(self.SENTENCE, ["largely"]))

    def test_a_witness_inside_another_word_names_nothing(self) -> None:
        check = self.check([("x", ["S1"])], ["The small fort stands."])
        assert not K.names_the_claim(check, case("It was all rebuilt.", ["all"]))

    def test_a_witness_word_alone_in_an_unrelated_reason_names_nothing(self) -> None:
        # "all" is a witness word and a content word of the flawed sentence: it cannot be the other word
        flawed = "All coins were struck in the town."
        check = self.check([("x", ["S1"])], ["The tone is flat overall, all in all."])
        assert not K.names_the_claim(check, case(flawed, ["all"]))
        named = self.check(
            [("x", ["S1"])], ["The card says all of it, but not every coin was struck."]
        )
        assert K.names_the_claim(named, case(flawed, ["all"]))

    def test_the_words_of_a_multi_word_witness_are_not_the_other_word(self) -> None:
        flawed = "Beneath the eastern wall of the old house lay a bronze coin."
        check = self.check(
            [("x", ["S1"])],
            ["The hook is weak: beneath a dull opening, the eastern wall is only a background."],
        )
        assert not K.names_the_claim(check, case(flawed, ["beneath", "eastern wall"]))
