"""Lane WB, the handoff side: the card contract, the answer shapes, the prompts and the run.

Everything here is DB-less and model-less: production is a fixture export, the answering agents are
answers written through `opus_handoff.write_answer`, the brand fonts are `phase4_cases`'
`fake_card_fit`, the web is an `httpx.MockTransport`. Each rule is asserted by the refusal it
produces, so removing it turns its test red (`mechanical/mutation_sweep.py "teaser:"`).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
import research_web  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from teaser import answers as A  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import run as R  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation.phase4_cases import CAPTION_FACE  # noqa: E402


def basis(site_id: str = T.SKARA, alt_names: list[str] | None = None) -> C.Basis:
    return C.basis(
        site_id=site_id,
        name=T.NAMES[site_id],
        country=T.COUNTRIES[site_id],
        description=T.DESCRIPTIONS[site_id],
        alt_names=alt_names or [],
    )


# ------------------------------------------------------------------------------ the fact basis
class TestTheFactBasis:
    def test_sentences_are_numbered_without_their_markers(self) -> None:
        sentences = C.description_sentences(T.DESCRIPTIONS[T.SKARA])
        assert [s.id for s in sentences] == ["S1", "S2", "S3", "S4", "S5", "S6"]
        assert sentences[0].text.endswith("Mainland, Orkney.")
        assert not any("[" in s.text for s in sentences)

    def test_a_circa_date_does_not_end_a_sentence(self) -> None:
        sentences = C.description_sentences("It was built c. 3000 BC by farmers [2, 3]. It fell.")
        assert [s.text for s in sentences] == ["It was built c. 3000 BC by farmers.", "It fell."]

    def test_each_line_is_split_on_its_own(self) -> None:
        sentences = C.description_sentences("A mound.\n\nA ditch [4-6]. A bank.")
        assert [s.text for s in sentences] == ["A mound.", "A ditch.", "A bank."]

    def test_a_site_without_a_description_has_no_basis(self) -> None:
        with pytest.raises(ValueError, match="no published description"):
            C.basis(site_id=T.EMPTY, name="X", country="Y", description="  ", alt_names=[])


class TestTheNameForms:
    def test_a_bracketed_disambiguator_is_no_form(self) -> None:
        forms = C.name_forms("Eryx (Sicily)", [], "Eryx was a city in Sicily.")
        assert forms == ("Eryx (Sicily)", "Eryx")

    def test_a_bracket_in_the_middle_is_taken_out(self) -> None:
        forms = C.name_forms("Quesera (Cheeseboard) de Zonzamas", [], "text")
        assert "Quesera de Zonzamas" in forms

    def test_the_part_before_the_first_comma_is_a_form(self) -> None:
        assert "Gaer Hillfort" in C.name_forms("Gaer Hillfort, Trellech", [], "text")

    def test_slash_and_dash_parts_are_forms_and_a_leading_the_goes(self) -> None:
        forms = C.name_forms("The Black Pyramid- Pyramid of Amenemhat III (Dahshur)", [], "text")
        assert {"The Black Pyramid", "Black Pyramid", "Pyramid of Amenemhat III"} <= set(forms)
        slash = C.name_forms("Medicine Wheel/Medicine Mountain National Historic Landmark", [], "t")
        assert "Medicine Wheel" in slash

    def test_an_alias_counts_only_where_the_description_uses_it(self) -> None:
        site = T.DESCRIPTIONS[T.SACSAY]
        assert "Saksaywaman" in C.name_forms("Sacsayhuamán", ["Saksaywaman"], site)
        assert "Sacsahuaman" not in C.name_forms("Sacsayhuamán", ["Sacsahuaman"], site)

    def test_a_short_derived_form_is_dropped_but_a_short_name_stays(self) -> None:
        assert C.name_forms("Ur", [], "Ur was a city.") == ("Ur",)
        assert "Ab" not in C.name_forms("Ab, Somewhere Long", [], "text")


# ------------------------------------------------------------------------------ the mechanical checks
def problems(card: str, site_id: str = T.SKARA, fit: Any = T.fit) -> list[str]:
    return C.problems(C.final_card(card), basis(site_id), fit=fit)


def padded(card: str) -> str:
    """`card` grown past the floor with words that claim nothing."""
    while len(card) < C.MIN_CHARS:
        card = card[:-1] + ", and more stone walls."
    return card


#: The one-word and hyphenated names whose caption word is wider than the frame at the caption
#: size, measured on the live WB mass run (Orbitron 700 at 92 px: 1,001 to 1,409 px); the first
#: two are one name, as stored and transliterated. `La Chapelle-aux-Saints` (its word
#: `Chapelle-aux-Saints`, 1,075 px) stalled run wb-ws-2026-09-27-02 the same way.
LONG_NAMES = (
    "Sammallahdenmäki",
    "Sammallahdenmaeki",
    "Hohlenstein-Stadel",
    "Saint-Pierre-aux-Nonnains",
    "Sainte-Colombe-sur-Seine",
    "Mecklenburg-Vorpommern",
    "Strubben-Kniphorstbos",
    "La Chapelle-aux-Saints",
)
#: Wider than the frame at the caption size in the tests' face (Pillow's own), fits smaller.
LONG_NAME = "Mecklenburg-Vorpommern"
#: Wider than the frame even at the smallest caption size, in any of the faces.
OVERLONG_NAME = "Mecklenburg-Vorpommern-Sainte-Colombe-sur-Seine"


def long_name_card(name: str) -> tuple[C.Basis, str]:
    """A site called `name` and a card that passes every other check and names it."""
    site = C.basis(
        site_id=T.SKARA,
        name=name,
        country="X",
        description=f"{name} is an ancient site of earth and stone.",
        alt_names=[],
    )
    return site, padded(f"{name} rises from the fields, a place of earth and stone.")


class TestTheMechanicalChecks:
    @pytest.mark.parametrize("site_id", [T.SKARA, T.NEWGRANGE, T.STONEHENGE, T.SACSAY])
    def test_the_good_cards_pass(self, site_id: str) -> None:
        assert problems(T.GOOD[site_id], site_id) == []

    def test_the_length_is_160_to_190_characters(self) -> None:
        assert any(p.startswith("length") for p in problems("Skara Brae lies on Orkney."))
        too_long = T.GOOD[T.SKARA][:-1] + ", beside the Bay of Skaill on the west coast of Orkney."
        assert len(too_long) > C.MAX_CHARS
        assert any(p.startswith("length") for p in problems(too_long))

    def test_the_length_is_measured_after_the_spoken_edit(self) -> None:
        assert C.final_card("Built c. 3180 BC.") == "Built circa 3180 BC."

    def test_layout_and_ending(self) -> None:
        good = T.GOOD[T.SKARA]
        assert any(p.startswith("layout") for p in problems(good.replace(", a ", ",  a ")))
        assert any(p.startswith("layout") for p in problems(" " + good[1:]))
        assert any(p.startswith("ending") for p in problems(good[:-1] + ","))
        assert any(p.startswith("ending") for p in problems(good[:-1] + "!"))
        assert not any(p.startswith("ending") for p in problems(good[:-1] + "?"))

    def test_at_most_two_sentences(self) -> None:
        card = "Skara Brae lies on Orkney. A storm found it. It was lived in from roughly 3180 BC."
        assert any(p.startswith("sentences") for p in problems(padded(card)))

    def test_at_most_one_short_question(self) -> None:
        two = T.GOOD[T.SKARA][:120] + "? Who? Why?"
        assert any(p.startswith("questions") for p in problems(two))
        long_q = (
            "Skara Brae lies on Orkney, stone houses in the sand dunes. What did the people who "
            "lived in them from roughly 3180 BC to around 2500 BC see from their doors at dawn?"
        )
        assert C.MIN_CHARS <= len(long_q) <= C.MAX_CHARS
        assert any(p.startswith("question:") for p in problems(long_q))

    @pytest.mark.parametrize(
        "bad", ["(", "[1]", "🗿", "²", "©", "!", "#", "*", "→", "×", "+", "=", "~", "|", "±"]
    )
    def test_brackets_markers_emojis_and_symbols_are_refused(self, bad: str) -> None:
        card = T.GOOD[T.SKARA].replace("Neolithic", f"Neolithic{bad}")
        assert any(p.startswith("characters") for p in problems(card))

    def test_a_zero_width_joiner_is_refused(self) -> None:
        card = T.GOOD[T.SKARA].replace("Neolithic", "Neo" + chr(0x200D) + "lithic")
        assert any(p.startswith("characters") for p in problems(card))

    def test_a_bare_circa_is_refused(self) -> None:
        card = T.GOOD[T.SKARA].replace("lived in from", "c. the end, lived in from")
        assert any(p.startswith("circa") for p in problems(card))

    def test_every_numeral_is_grounded_in_the_description(self) -> None:
        computed = T.GOOD[T.SKARA].replace("3180 BC to around 2500 BC", "5,000 years ago, 2500 BC")
        found = problems(computed)
        assert any(p.startswith("numbers not in the description: 5000") for p in found)
        assert problems(T.GOOD[T.SKARA].replace("3180", "3,180")) == []

    def test_a_numeral_of_the_name_is_grounded(self) -> None:
        site = C.basis(
            site_id=T.SKARA, name="Mound 72", country="X", description="A mound.", alt_names=[]
        )
        card = padded("Mound 72 rises from the fields, a mound of earth and stone.")
        assert not any(p.startswith("numbers") for p in C.problems(card, site, fit=T.fit))

    def test_the_card_names_the_site(self) -> None:
        card = T.GOOD[T.SKARA].replace("Skara Brae", "this village")
        assert any(p.startswith("name") for p in problems(card))
        accented = T.GOOD[T.SACSAY].replace("Sacsayhuamán", "Sacsayhuaman")
        assert problems(accented, T.SACSAY) == []

    def test_the_shorts_font_and_frame(self) -> None:
        def missing(name: str, card: str) -> Any:
            return dataclasses.replace(T.fit(name, card), missing=("ʿ",))

        def wide(name: str, card: str) -> Any:
            return dataclasses.replace(
                T.fit(name, card), drawn_px=C.V.MAX_CAPTION_PX + 1, drawn="X"
            )

        assert any(p.startswith("font") for p in problems(T.GOOD[T.SKARA], fit=missing))
        assert any(p.startswith("caption") for p in problems(T.GOOD[T.SKARA], fit=wide))

    def test_a_word_too_wide_at_the_caption_size_is_drawn_smaller_and_passes(self) -> None:
        site, card = long_name_card(LONG_NAME)
        assert T.fit(site.name, card).px > C.V.MAX_CAPTION_PX  # the check refused it at 92 px
        assert C.problems(card, site, fit=T.fit) == []

    def test_a_word_wider_than_the_frame_at_the_floor_is_refused(self) -> None:
        site, card = long_name_card(OVERLONG_NAME)
        drawn_px = T.fit(site.name, card).drawn_px
        assert drawn_px > C.V.MAX_CAPTION_PX
        assert C.problems(card, site, fit=T.fit) == [
            f"caption: the word {OVERLONG_NAME!r} is {drawn_px} px wide even at the smallest "
            f"caption size ({C.CAPTION_MIN_SIZE} px font), wider than the frame "
            f"({C.V.MAX_CAPTION_PX} px)"
        ]

    def test_card_fit_measures_each_word_as_the_short_draws_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`verify4.card_fit` itself, with Pillow's own face as the heading font (the brand fonts
        are gitignored): the width at the caption size for V10, the drawn width for the contract."""
        font = tmp_path / "face.ttf"
        font.write_bytes(CAPTION_FACE.font_bytes)
        monkeypatch.setattr(C.V.shorts_brand, "heading_font", lambda text: font)
        monkeypatch.setattr(C.V.shorts_brand, "font_cmap", lambda path: set(range(0x180)))
        site, card = long_name_card(LONG_NAME)
        fit = C.V.card_fit(site.name, card)
        assert (fit.widest, fit.drawn) == (LONG_NAME, LONG_NAME)
        assert fit.drawn_px <= C.V.MAX_CAPTION_PX < fit.px

    def test_the_long_names_of_the_mass_run_pass_with_the_brand_fonts(self) -> None:
        """The names that stalled the writer batches of runs wb-ws-2026-09-27-01, -02 and -04
        (1,001-1,409 px at 92 px in Orbitron 700), measured with the real brand fonts by
        `verify4.card_fit`. One test for all of them, so a machine without the fonts (CI) reports
        one skip, not one per name."""
        fonts = [C.V.shorts_brand.FONT_DIR / file for file in C.V.shorts_brand.FONTS]
        if not all(path.exists() for path in fonts):
            pytest.skip("the brand fonts (video-assets/fonts, gitignored) are not on this machine")
        pytest.importorskip("fontTools", reason="fontTools reads the brand fonts' cmap")
        for name in LONG_NAMES:
            site, card = long_name_card(name)
            fit = C.V.card_fit(site.name, card)
            assert fit.px > C.V.MAX_CAPTION_PX >= fit.drawn_px, (name, fit)
            assert C.problems(card, site, fit=C.V.card_fit) == [], name


class TestTheUndrawableProof:
    """A site every name form of which holds a glyph the shorts font cannot draw gets no card - and
    only the font check itself, the `fit` the contract measures every card with, says so."""

    def test_a_site_whose_every_name_form_holds_an_undrawable_glyph_is_proved(self) -> None:
        site = basis(T.JABAL)
        assert site.forms == ("Jabal al-ʿHayn",)
        assert C.undrawable_proof(site, fit=T.fit) == {"Jabal al-ʿHayn": ("ʿ",)}
        assert C.undrawable_reason({"Jabal al-ʿHayn": ("ʿ",)}) == (
            "no card can be written: every name form contains a glyph the shorts font cannot "
            "draw - 'Jabal al-ʿHayn' ('ʿ')"
        )

    def test_no_card_can_pass_the_contract_for_such_a_site(self) -> None:
        """The premise: a card with the name fails the font check, one without it the name check."""
        site = basis(T.JABAL)
        named = padded("Jabal al-ʿHayn is an outcrop of red sandstone, a place of petroglyphs.")
        assert any(p.startswith("font") for p in C.problems(named, site, fit=T.fit))
        unnamed = padded("A red sandstone outcrop in Saudi Arabia carries petroglyphs.")
        assert any(p.startswith("name") for p in C.problems(unnamed, site, fit=T.fit))

    def test_a_site_with_a_name_form_the_font_can_draw_is_refused(self) -> None:
        with pytest.raises(ValueError, match="a card can be written: .*'Skara Brae'"):
            C.undrawable_proof(basis(T.SKARA), fit=T.fit)

    def test_one_drawable_form_among_undrawable_ones_is_enough_to_refuse(self) -> None:
        site = C.basis(
            site_id=T.SKARA,
            name="Qasr al-Farafra",
            country="Egypt",
            description="Qasr al-Farafra, also Qasr ʿFarafra, is a fortress.",
            alt_names=["Qasr ʿFarafra"],
        )
        assert site.forms == ("Qasr al-Farafra", "Qasr ʿFarafra")
        with pytest.raises(ValueError, match="'Qasr al-Farafra'") as refused:
            C.undrawable_proof(site, fit=T.fit)
        assert "ʿ" not in str(refused.value)

    def test_the_stored_name_is_drawn_with_every_card_so_its_glyphs_count_in_every_form(
        self,
    ) -> None:
        """A plain alias cannot save a card: the short draws the stored name with it (`fit(name,
        card)`), so the font check refuses the alias-only card for the stored name's glyph."""
        site = C.basis(
            site_id=T.JABAL,
            name="Jabal al-ʿHayn",
            country="Saudi Arabia",
            description="Jabal al-Hayn, also called Jabal al-ʿHayn, is a hill of red sandstone.",
            alt_names=["Jabal al-Hayn"],
        )
        assert site.forms == ("Jabal al-ʿHayn", "Jabal al-Hayn")
        assert C.undrawable_proof(site, fit=T.fit) == {
            "Jabal al-ʿHayn": ("ʿ",),
            "Jabal al-Hayn": ("ʿ",),
        }
        alias_card = padded("Jabal al-Hayn is a hill of red sandstone, a place of petroglyphs.")
        assert any(p.startswith("font") for p in C.problems(alias_card, site, fit=T.fit))

    def test_it_is_the_fit_the_contract_is_given_that_decides(self) -> None:
        def draws_everything(name: str, card: str) -> Any:
            return dataclasses.replace(T.fit(name, card), missing=())

        def draws_nothing(name: str, card: str) -> Any:
            return dataclasses.replace(T.fit(name, card), missing=("S",))

        with pytest.raises(ValueError, match="a card can be written"):
            C.undrawable_proof(basis(T.JABAL), fit=draws_everything)
        assert C.undrawable_proof(basis(T.SKARA), fit=draws_nothing) == {"Skara Brae": ("S",)}


class TestTheExamples:
    @pytest.mark.parametrize("example", P.EXAMPLES, ids=lambda e: e.site)
    def test_every_example_passes_the_contract_on_its_site_s_description(self, example) -> None:
        site_id = T.SITE_OF[example.site]
        assert (T.COUNTRIES[site_id], T.GOOD[site_id]) == (example.country, example.card)
        assert C.problems(example.card, basis(site_id), fit=T.fit) == []

    @pytest.mark.parametrize("example", P.EXAMPLES, ids=lambda e: e.site)
    def test_an_example_shows_its_description_s_own_sentences_by_id(self, example) -> None:
        numbered = {s.id: s.text for s in basis(T.SITE_OF[example.site]).sentences}
        assert all(numbered[sid] == text for sid, text in example.sentences)

    @pytest.mark.parametrize("example", P.EXAMPLES, ids=lambda e: e.site)
    def test_every_claim_of_an_example_names_a_sentence_it_shows(self, example) -> None:
        own = {sid for sid, _text in example.sentences}
        assert all(ids and set(ids) <= own for _claim, ids in example.claims)


# ------------------------------------------------------------------------------ the answer shapes
class TestTheWriterAnswer:
    def test_a_card_and_its_basis(self) -> None:
        written = A.parse_writer(T.writer_answer("Built c. 3180 BC.", ["S3"]), basis())
        assert written.card == "Built circa 3180 BC." and written.basis == ("S3",)

    @pytest.mark.parametrize(
        ("text", "why"),
        [
            ("```json\n{}\n```", "one JSON object"),
            ('{"card": "x"}', "exactly"),
            ('{"card": "x", "basis": ["S1"], "note": 1}', "exactly"),
            ('{"card": " ", "basis": ["S1"]}', "card is not"),
            ('{"card": "x", "basis": []}', "no sentence"),
            ('{"card": "x", "basis": ["S99"]}', "not sentence ids"),
            ('{"card": "x", "basis": ["S1", "S1"]}', "twice"),
        ],
    )
    def test_anything_else_is_refused(self, text: str, why: str) -> None:
        with pytest.raises(A.AnswerError, match=why):
            A.parse_writer(text, basis())

    def test_a_site_no_card_can_be_written_for_is_declined(self) -> None:
        assert A.parse_writer(T.DECLINE, basis(T.JABAL)) == A.Declined()

    @pytest.mark.parametrize(
        ("text", "why"),
        [
            ('{"card": "x", "basis": [], "undrawable": true}', "cannot be written is exactly"),
            ('{"card": null, "basis": ["S1"], "undrawable": true}', "cannot be written is exactly"),
            ('{"card": null, "basis": [], "undrawable": false}', "cannot be written is exactly"),
            ('{"card": null, "basis": [], "undrawable": 1}', "cannot be written is exactly"),
            ('{"card": null, "basis": []}', "card is not"),
            ('{"card": null, "undrawable": true}', "exactly"),
        ],
    )
    def test_the_decline_is_exactly_its_shape(self, text: str, why: str) -> None:
        with pytest.raises(A.AnswerError, match=why):
            A.parse_writer(text, basis(T.JABAL))

    def test_the_rewrite_after_a_failed_verification_never_declines(self) -> None:
        """Its card passed the name and font checks already: a name form can be drawn."""
        with pytest.raises(A.AnswerError, match="exactly"):
            A.parse_verify_writer(T.DECLINE, basis(T.JABAL), 0)
        assert R.VERIFY_REWRITE not in R.DECLINING_STAGES
        assert R.DECLINING_STAGES == ("write", "rewrite1", "rewrite2")


class TestTheCheckerAnswer:
    def test_a_pass(self) -> None:
        checked = A.parse_checker(T.checker_answer(), basis())
        assert checked.verdict == A.PASSED and checked.claims == (
            ("the site's main facts", ("S1",)),
        )

    def test_a_pass_with_an_unsupported_claim_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="unsupported claim"):
            A.parse_checker(T.checker_answer(claims=[("the oldest", [])]), basis())

    @pytest.mark.parametrize("flag", ["tone_ok", "this_site"])
    def test_a_pass_with_a_broken_rule_is_refused(self, flag: str) -> None:
        with pytest.raises(A.AnswerError, match="tone_ok or this_site"):
            A.parse_checker(T.checker_answer(**{flag: False}), basis())

    def test_a_pass_with_a_reason_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="PASS with a reason"):
            A.parse_checker(T.checker_answer(reasons=["too flat"]), basis())

    def test_a_fail_needs_a_reason(self) -> None:
        with pytest.raises(A.AnswerError, match="FAIL without a reason"):
            A.parse_checker(T.checker_answer(verdict="FAIL"), basis())
        failed = A.parse_checker(
            T.checker_answer(verdict="FAIL", claims=[("the oldest", [])], reasons=["No."]), basis()
        )
        assert failed.verdict == A.FAILED

    @pytest.mark.parametrize(
        ("change", "why"),
        [
            ({"claims": []}, "non-empty list"),
            ({"claims": [{"claim": "x", "support": ["S9"]}]}, "not sentence ids"),
            ({"verdict": "MAYBE"}, "PASS or FAIL"),
            ({"tone_ok": "yes"}, "true or false"),
            ({"reasons": "none"}, "not a list"),
        ],
    )
    def test_anything_else_is_refused(self, change: dict[str, Any], why: str) -> None:
        data = {**json.loads(T.checker_answer()), **change}
        with pytest.raises(A.AnswerError, match=why):
            A.parse_checker(json.dumps(data), basis())


class TestTheJudgeAnswer:
    QUOTE = "occupied from roughly 3180 BC to around 2500 BC"

    def _answer(self, **over: Any) -> str:
        claim = {
            "claim": "c",
            "verdict": "SUPPORTED",
            "url": "https://x.org/a",
            "quote": self.QUOTE,
        }
        return json.dumps({"claims": [{**claim, **over}]})

    def test_a_supported_and_an_unverifiable_claim(self) -> None:
        assert A.parse_judge(self._answer())[0].url == "https://x.org/a"
        judged = A.parse_judge(self._answer(verdict="UNVERIFIABLE", url=None, quote=None))
        assert judged[0].verdict == "UNVERIFIABLE"

    @pytest.mark.parametrize(
        ("over", "why"),
        [
            ({"verdict": "UNVERIFIABLE"}, "carries no url"),
            ({"quote": None}, "quote is not"),
            ({"quote": "short"}, "at least 20"),
            ({"url": "ftp://x"}, "http"),
            ({"verdict": "TRUE"}, "one of"),
        ],
    )
    def test_anything_else_is_refused(self, over: dict[str, Any], why: str) -> None:
        with pytest.raises(A.AnswerError, match=why):
            A.parse_judge(self._answer(**over))


# ------------------------------------------------------------------------------ the prompts
class TestThePrompts:
    def test_the_writer_sees_the_sentences_the_forms_the_rules_and_the_examples(self) -> None:
        prompt = P.writer_prompt(basis())
        assert "S3 The site was occupied from roughly 3180 BC" in prompt
        assert "NAME FORMS (the card must contain one of these, exactly): Skara Brae" in prompt
        assert "160-190 characters" in prompt and "Storm" not in prompt.split("THE RULES")[0]
        assert all(example.card in prompt for example in P.EXAMPLES)
        assert '{"card": "<the card>", "basis": ["S1", "S3"]}' in prompt

    def test_the_rewriter_sees_every_earlier_card_and_why(self) -> None:
        prompt = P.rewrite_prompt(basis(), [P.Finding("An old card.", ("No sentence says X.",))])
        assert "Card 1 (12 characters): An old card." in prompt
        assert "- No sentence says X." in prompt

    def test_the_checker_sees_the_card_and_the_sentences_but_no_writer(self) -> None:
        prompt = P.checker_prompt(basis(), T.GOOD[T.SKARA])
        assert T.GOOD[T.SKARA] in prompt and "S6 The buildings follow" in prompt
        assert '"verdict": "PASS"' in prompt and "basis" not in prompt

    def test_the_judge_sees_only_the_card(self) -> None:
        prompt = P.judge_prompt("Skara Brae", "Scotland", T.GOOD[T.SKARA])
        assert T.GOOD[T.SKARA] in prompt and "Bay of Skaill" not in prompt
        assert "ancientnerds.com" in prompt and "403" in prompt
        assert "nor an AI aggregator or a copy of Wikipedia" in prompt

    def test_the_findings_of_a_check_name_every_unsupported_claim(self) -> None:
        record = {
            "kind": "check",
            "claims": [
                {"claim": "the oldest", "support": []},
                {"claim": "on Orkney", "support": ["S1"]},
            ],
            "tone_ok": False,
            "this_site": True,
            "reasons": ["Too flat."],
        }
        findings = P.findings_of(record)
        assert findings[0] == "No sentence of the description supports the claim: the oldest"
        assert len(findings) == 3 and findings[-1] == "Too flat."


# ------------------------------------------------------------------------------ select
class TestTheSelection:
    def test_who_is_a_candidate(self) -> None:
        reasons = {r["site_id"]: R.classify(r)[0] for r in T.production_rows()}
        assert reasons == {
            T.SKARA: None,
            T.NEWGRANGE: None,
            T.STONEHENGE: None,
            T.SACSAY: None,
            T.MARCH: R.NOT_FINAL,
            T.EMPTY: R.NO_DESCRIPTION,
            T.RETIRED_SITE: R.RETIRED,
        }

    def test_a_description_its_provenance_does_not_hash_is_not_final(self) -> None:
        assert R.classify(T.row(T.SKARA, provenance_desc_sha256="0" * 64))[0] == R.NOT_FINAL

    @pytest.mark.parametrize("lane", ["L", None])
    def test_a_sentence_checked_text_is_a_basis_while_its_check_hashes_it(self, lane) -> None:
        digest = T.sha(T.DESCRIPTIONS[T.MARCH])
        checked = T.row(T.MARCH, lane=lane, check_desc_sha256=digest)
        assert R.classify(checked) == (None, "")
        assert R.basis_of(checked) == R.SENTENCE_CHECKED
        moved = T.row(T.MARCH, lane=lane, check_desc_sha256="0" * 64)
        assert R.classify(moved)[0] == R.NOT_FINAL

    def test_a_phase4_lane_is_named_before_a_sentence_check(self) -> None:
        digest = T.sha(T.DESCRIPTIONS[T.SKARA])
        assert R.basis_of(T.row(T.SKARA, check_desc_sha256=digest)) == "W"
        stale_w = T.row(T.SKARA, provenance_desc_sha256="0" * 64, check_desc_sha256=digest)
        assert R.basis_of(stale_w) == R.SENTENCE_CHECKED

    def test_the_run_records_each_candidate_s_basis(self, tmp_path: Path) -> None:
        checked = T.row(T.MARCH, lane="L", check_desc_sha256=T.sha(T.DESCRIPTIONS[T.MARCH]))
        rows = [checked if r["site_id"] == T.MARCH else r for r in T.production_rows()]
        run = make_run(tmp_path, rows)
        record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        assert record["basis"] == {"W": 4, "WC": 1}
        assert record["basis_asked"] is None
        sites = {s["site_id"]: s["basis"] for s in R.read_jsonl(run / "SITES.jsonl")}
        assert sites[T.MARCH] == "WC"

    def test_a_site_without_a_card_row_is_listed(self) -> None:
        assert R.classify(T.row(T.SKARA, has_card_row=False))[0] == R.NO_CARD_ROW

    def test_a_live_teaser_is_current_and_a_stale_one_a_candidate(self) -> None:
        live = T.row(T.SKARA, card=T.GOOD[T.SKARA], card_provenance=T.teaser(T.SKARA))
        assert R.classify(live)[0] == R.CURRENT
        stale = T.row(
            T.SKARA, card=T.GOOD[T.SKARA], card_provenance=T.teaser(T.SKARA, description="old")
        )
        assert R.classify(stale)[0] is None

    def test_a_site_asked_before_is_asked_again_only_after_its_description_moved(self) -> None:
        rows = T.production_rows()
        asked = {T.SKARA: T.sha(T.DESCRIPTIONS[T.SKARA]), T.NEWGRANGE: T.sha("an older text")}
        chosen = R.select_rows(rows, earlier=asked, sites=None, pilot=None)
        assert [s["site_id"] for s in chosen.sites] == sorted([T.NEWGRANGE, T.STONEHENGE, T.SACSAY])
        assert {r["site_id"]: r["reason"] for r in chosen.listed}[T.SKARA] == R.ASKED_BEFORE

    def test_a_pilot_is_a_seeded_draw(self) -> None:
        rows = T.production_rows()
        first = R.select_rows(rows, earlier={}, sites=None, pilot=(2, 7))
        again = R.select_rows(rows, earlier={}, sites=None, pilot=(2, 7))
        assert [s["site_id"] for s in first.sites] == [s["site_id"] for s in again.sites]
        assert len(first.sites) == 2
        assert sum(r["reason"] == R.NOT_DRAWN for r in first.listed) == 2
        with pytest.raises(R.RunError, match="a pilot of 9"):
            R.select_rows(rows, earlier={}, sites=None, pilot=(9, 7))

    def test_a_sites_file_restricts_and_names_only_curated_sites(self) -> None:
        rows = T.production_rows()
        chosen = R.select_rows(rows, earlier={}, sites={T.SKARA}, pilot=None)
        assert [s["site_id"] for s in chosen.sites] == [T.SKARA]
        with pytest.raises(R.RunError, match="no curated site"):
            R.select_rows(rows, earlier={}, sites={"f" * 8}, pilot=None)

    def test_a_run_can_ask_one_basis_only(self) -> None:
        """The pilot of the sentence-checked March texts (basis WC) draws from them alone: the
        first pilot's candidates are Wikipedia-assembled (W/S), which WC texts are not."""
        checked = T.row(T.MARCH, lane="L", check_desc_sha256=T.sha(T.DESCRIPTIONS[T.MARCH]))
        rows = [checked if r["site_id"] == T.MARCH else r for r in T.production_rows()]
        chosen = R.select_rows(rows, earlier={}, sites=None, pilot=None, basis={"WC"})
        assert [s["site_id"] for s in chosen.sites] == [T.MARCH]
        other = {r["site_id"] for r in chosen.listed if r["reason"] == R.OTHER_BASIS}
        assert other == {T.SKARA, T.NEWGRANGE, T.STONEHENGE, T.SACSAY}
        drawn = R.select_rows(rows, earlier={}, sites=None, pilot=(1, 7), basis={"WC"})
        assert [s["site_id"] for s in drawn.sites] == [T.MARCH]
        both = R.select_rows(rows, earlier={}, sites=None, pilot=None, basis={"W", "WC"})
        assert len(both.sites) == 5


# ------------------------------------------------------------------------------ the run
def make_run(tmp_path: Path, rows: list[dict[str, Any]] | None = None) -> Path:
    run = tmp_path / "runs" / "wb-test"
    export = T.tagged({"site": rows if rows is not None else T.production_rows()})

    def read(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(export, encoding="utf-8", newline="\n")

    R.select(run, read=read, sites_file=None, pilot=None, exclude=[])
    return run


def answer_all(
    run: Path,
    stage: str,
    handoff: Path,
    answers: dict[str, str],
    by: str = "",
    model: str = OH.OPUS_MODEL,
) -> None:
    record = R._round(run, stage)
    assert record is not None
    for batch_id, members in record["batches"].items():
        for site_id in members:
            OH.write_answer(
                handoff,
                model=model,
                batch_id=batch_id,
                stage=stage,
                label=site_id,
                text=answers[site_id],
                answered_by=by or R.agent_name(batch_id),
            )


def step(
    run: Path,
    tmp_path: Path,
    stage: str,
    answers: dict[str, str],
    by: str = "",
    model: str = OH.OPUS_MODEL,
) -> dict:
    handoff = tmp_path / f"handoff-{stage}"
    exported = R.export_stage(run, stage, handoff)
    if exported["questions"]:
        answer_all(run, stage, handoff, answers, by, model)
        if stage in R.VERIFY_STAGES:
            return R.import_stage(run, stage, fit=T.fit, client=judge_client(), pace=0)
        return R.import_stage(run, stage, fit=T.fit)
    return exported


GOOD_WRITES = {site: T.writer_answer(card) for site, card in T.GOOD.items()}
PASSES = dict.fromkeys(T.GOOD, T.checker_answer())
#: A verifier's answer that proves the card: its one claim SUPPORTED by a quote the page holds.
VERIFIES = dict.fromkeys(T.GOOD, T.judge_answer())


class TestTheRun:
    def test_select_fixes_the_candidates_once(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        assert record["sites"] == 4
        assert record["listed"] == {"no-description": 1, "not-final": 1, "retired": 1}
        with pytest.raises(R.RunError, match="selected already"):
            make_run(tmp_path)

    def test_a_changed_sites_file_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        path = run / "SITES.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace("Orkney", "Shetland"), "utf-8")
        with pytest.raises(R.RunError, match="not the file RUN.json pins"):
            R.bases(run)

    def test_all_accepted_in_the_first_round(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        assert step(run, tmp_path, "write", GOOD_WRITES)["mechanical_failures"] == 0
        assert step(run, tmp_path, "check", PASSES)["verdicts"] == {"PASS": 4}
        assert step(run, tmp_path, "rewrite1", {})["questions"] == 0
        assert step(run, tmp_path, "verify", VERIFIES)["verdicts"] == {"VERIFIED": 4}
        assert step(run, tmp_path, "rewrite-v", {})["questions"] == 0
        R.outcomes(run)
        rows = R.read_outcomes(run)
        accepted = [r for r in rows if r["status"] == R.ACCEPTED]
        assert len(accepted) == 4
        for row in accepted:
            provenance = CP.validate(row["provenance"])
            assert CP.describes(provenance, T.GOOD[row["site_id"]])
            assert provenance["desc_sha256"] == T.sha(T.DESCRIPTIONS[row["site_id"]])
            assert provenance["check"]["by"].startswith("teaser-check-")
            # `outcome_rows` derives the disclosure from the models that answered (owner decision
            # D6, 2026-10-08): every answer here was Opus's, so Haiku is not named
            assert provenance["ai_system"] == M.AI_SYSTEM_CLAUDE
            assert provenance["verify"] == {
                "verdict": "VERIFIED",
                "stage": "verify",
                "by": "teaser-verify-001",
                "at": row["verifications"][0]["answered_at"],
                "claims": 1,
                "unproven": 0,
                "text_sha256": T.sha(T.GOOD[row["site_id"]]),
            }
            assert provenance["web_facts"] == []
            assert row["verification"] == R.VERIFIED
        cleared = [r for r in rows if r["status"] == R.CLEARED]
        assert [(r["site_id"], r["reason"]) for r in cleared] == [(T.EMPTY, R.NO_DESCRIPTION)]
        assert cleared[0]["verification"] is None

    def test_every_stage_record_names_the_stamp_of_the_model_that_answered(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES, model=OH.SONNET_MODEL)
        step(run, tmp_path, "check", PASSES, model=OH.HAIKU_MODEL)
        records = R.stage_records(run)
        assert {r["model"] for r in records["write"].values()} == {OH.SONNET_MODEL}
        assert {r["model"] for r in records["check"].values()} == {OH.HAIKU_MODEL}

    @pytest.mark.parametrize(
        ("write", "check", "verify", "expected"),
        [
            (OH.SONNET_MODEL, OH.OPUS_MODEL, OH.HAIKU_MODEL, M.AI_SYSTEM_CLAUDE_HAIKU),
            (OH.MINIMAX_MODEL, OH.OPUS_MODEL, OH.OPUS_MODEL, M.AI_SYSTEM),
            (OH.OPUS_MODEL, OH.MINIMAX_MODEL, OH.OPUS_MODEL, M.AI_SYSTEM),
            (OH.OPUS_MODEL, OH.OPUS_MODEL, OH.MINIMAX_MODEL, M.AI_SYSTEM),
        ],
    )
    def test_the_disclosure_follows_the_models_that_wrote_checked_and_verified_the_card(
        self, tmp_path: Path, write: str, check: str, verify: str, expected: str
    ) -> None:
        """Owner decision D6: a card rests on its writer, its accepting check and its verification.
        All Claude's: the Claude-only string. Any MiniMax stamp among them: the combined one."""
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES, model=write)
        step(run, tmp_path, "check", PASSES, model=check)
        step(run, tmp_path, "rewrite1", {})
        step(run, tmp_path, "verify", VERIFIES, model=verify)
        step(run, tmp_path, "rewrite-v", {})
        R.outcomes(run)
        accepted = [r for r in R.read_outcomes(run) if r["status"] == R.ACCEPTED]
        assert len(accepted) == 4
        assert {r["provenance"]["ai_system"] for r in accepted} == {expected}
        assert expected in M.AI_SYSTEMS

    def test_a_record_imported_before_the_stamp_was_kept_cannot_be_disclosed(
        self, tmp_path: Path
    ) -> None:
        """A stage file without `model` (a run imported before 2026-10-08) names no model to derive
        the disclosure from, and the disclosure is never guessed."""
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES)
        step(run, tmp_path, "check", PASSES)
        step(run, tmp_path, "rewrite1", {})
        step(run, tmp_path, "verify", VERIFIES)
        step(run, tmp_path, "rewrite-v", {})
        path = run / "STAGE-check.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            del row["model"]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        with pytest.raises(R.RunError, match="model"):
            R.outcomes(run)

    def test_a_blank_description_clears_the_card_on_the_text_as_it_was_read(
        self, tmp_path: Path
    ) -> None:
        rows = [
            T.row(T.EMPTY, description="  ", lane=None, provenance_desc_sha256=None)
            if r["site_id"] == T.EMPTY
            else r
            for r in T.production_rows()
        ]
        run = make_run(tmp_path, rows)
        step(run, tmp_path, "write", GOOD_WRITES)
        step(run, tmp_path, "check", PASSES)
        step(run, tmp_path, "verify", VERIFIES)
        R.outcomes(run)
        empty = next(r for r in R.read_outcomes(run) if r["site_id"] == T.EMPTY)
        assert (empty["status"], empty["reason"]) == (R.CLEARED, R.NO_DESCRIPTION)
        assert empty["desc_sha256"] == T.sha("  ")

    def test_a_card_that_fails_goes_to_a_rewrite_with_its_findings(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        writes = {**GOOD_WRITES, T.SKARA: T.writer_answer("Skara Brae lies on Orkney.")}
        assert step(run, tmp_path, "write", writes)["mechanical_failures"] == 1
        checks = {
            **PASSES,
            T.NEWGRANGE: T.checker_answer(
                "FAIL", [("the oldest tomb", [])], ["No sentence says it is the oldest."]
            ),
        }
        step(run, tmp_path, "check", checks)
        R.export_stage(run, "rewrite1", tmp_path / "handoff-rewrite1")
        prompts = {
            line["label"]: (tmp_path / "handoff-rewrite1" / line["prompt_path"]).read_text("utf-8")
            for line in OH.manifest(tmp_path / "handoff-rewrite1")
        }
        assert set(prompts) == {T.SKARA, T.NEWGRANGE}
        assert "length: 26 characters" in prompts[T.SKARA]
        assert (
            "No sentence of the description supports the claim: the oldest tomb"
            in prompts[T.NEWGRANGE]
        )
        # the two accepted cards wait for their web verification, which follows every check round
        assert R.status(run)["states"] == {"due rewrite1": 2, "due verify": 2}

    def test_two_failed_rewrites_clear_the_card(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        bad = T.writer_answer("Skara Brae lies on Orkney.")
        step(run, tmp_path, "write", {**GOOD_WRITES, T.SKARA: bad})
        step(run, tmp_path, "check", PASSES)
        step(run, tmp_path, "rewrite1", {T.SKARA: bad})
        assert step(run, tmp_path, "check1", {})["questions"] == 0
        step(run, tmp_path, "rewrite2", {T.SKARA: T.writer_answer(T.GOOD[T.SKARA])})
        fail = T.checker_answer("FAIL", [("x", [])], ["Unsupported."])
        step(run, tmp_path, "check2", {T.SKARA: fail})
        step(run, tmp_path, "verify", VERIFIES)
        R.outcomes(run)
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        assert skara["status"] == R.CLEARED and skara["reason"] == "failed-after-two-rewrites"
        assert skara["attempts"] == 3 and skara["provenance"] is None

    def test_an_earlier_stage_must_be_imported_before_the_next_is_asked(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path)
        R.export_stage(run, "write", tmp_path / "h-write")
        with pytest.raises(R.RunError, match="wait for their import"):
            R.export_stage(run, "check", tmp_path / "h-check")
        with pytest.raises(R.RunError, match="exported already"):
            R.export_stage(run, "write", tmp_path / "h-write-2")

    def test_a_checker_that_wrote_the_card_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES)
        with pytest.raises(R.RunError, match="wrote or checked this site before"):
            step(run, tmp_path, "check", PASSES, by="teaser-write-001")

    def test_a_malformed_answer_is_refused_at_import(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        with pytest.raises(R.RunError, match="malformed answer"):
            step(run, tmp_path, "write", {**GOOD_WRITES, T.SKARA: '{"card": "x"}'})

    def test_an_answer_to_another_prompt_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        answer_all(run, "write", handoff, GOOD_WRITES)
        line = next(line for line in OH.manifest(handoff) if line["label"] == T.SKARA)
        prompt = handoff / line["prompt_path"]
        prompt.write_text(prompt.read_text("utf-8") + " ", encoding="utf-8")
        with pytest.raises(R.RunError, match="validated"):
            R.import_stage(run, "write", fit=T.fit)

    def test_a_question_the_run_would_now_ask_differently_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The prompts changed between export and import (a rule edited mid-round): the import
        rebuilds each question and refuses the answers to the old one."""
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        answer_all(run, "write", handoff, GOOD_WRITES)
        monkeypatch.setattr(P, "RULES", (*P.RULES, "A rule added after the export."))
        with pytest.raises(R.RunError, match="not this question's"):
            R.import_stage(run, "write", fit=T.fit)

    def test_an_import_is_the_same_when_run_again(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES)
        first = (run / "STAGE-write.jsonl").read_bytes()
        step(run, tmp_path, "check", PASSES)
        R.import_stage(run, "write", fit=T.fit)
        assert (run / "STAGE-write.jsonl").read_bytes() == first

    def test_outcomes_wait_for_every_site(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES)
        with pytest.raises(R.RunError, match="still due"):
            R.outcomes(run)

    def test_check_answer_shows_the_writer_the_problems(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        batch = next(iter(R._round(run, "write")["batches"]))
        bad = R.check_answer(
            run, handoff, batch, T.SKARA, T.writer_answer("Skara Brae."), fit=T.fit
        )
        assert not bad["ok"] and bad["problems"][0].startswith("length")
        good = R.check_answer(run, handoff, batch, T.SKARA, GOOD_WRITES[T.SKARA], fit=T.fit)
        assert good["ok"] and good["length"] == len(T.GOOD[T.SKARA])
        shape = R.check_answer(run, handoff, batch, T.SKARA, "{}", fit=T.fit)
        assert not shape["ok"]
        with pytest.raises(R.RunError, match="no question"):
            R.check_answer(run, handoff, batch, T.MARCH, "{}", fit=T.fit)

    def test_the_brief_names_the_batch_its_scratch_and_its_agent(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        text = R.brief(run, handoff, "write-001")
        assert "writer write-001" in text and "--answered-by teaser-write-001" in text
        # The brief offers every model id the recorder accepts, built from NEW_ANSWER_MODELS: an
        # agent names the model it runs as (owner decision 2026-10-01), and the list may not be
        # narrower than the models in use (MiniMax joined 2026-10-03, this lane still offered only
        # the two Claude ids on 2026-10-07 and told an agent to stamp a model that wrote nothing).
        # Owner decision D6 (2026-10-08): Claude only again, with Haiku; MiniMax is not offered.
        assert all(model_id in text for model_id in OH.NEW_ANSWER_MODELS)
        assert "claude-haiku-5-5" in text and "MiniMax" not in text
        assert text.count("Opus") == 0  # the answering agents are not Opus ones
        assert "handoff-write-scratch/write-001/<label>.json" in text
        assert "no web research" in text
        assert 'Skip every question whose "answer_path"' in text
        # independence is the orchestrator's rule (module doc): the brief makes a reused agent stop
        assert "answered no other batch of lane WB" in text and "stop now and say so" in text
        with pytest.raises(R.RunError, match="no batch"):
            R.brief(run, handoff, "write-009")


# ------------------------------------------------------------------------------ an undrawable name
PROOF = {"Jabal al-ʿHayn": ["ʿ"]}
#: A writer's card for Jabal al-ʿHayn: it names the site, so only the font check refuses it.
JABAL_CARD = padded("Jabal al-ʿHayn is an outcrop of red sandstone, a place of petroglyphs.")


def undrawable_run(tmp_path: Path) -> Path:
    """A run of Skara Brae (a card can be written) and Jabal al-ʿHayn (none can)."""
    return make_run(tmp_path, [T.row(T.SKARA), T.row(T.JABAL)])


class TestAnUndrawableName:
    def test_the_decline_is_accepted_for_the_site_and_refused_for_another(
        self, tmp_path: Path
    ) -> None:
        run = undrawable_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        batch = next(iter(R._round(run, "write")["batches"]))
        accepted = R.check_answer(run, handoff, batch, T.JABAL, T.DECLINE, fit=T.fit)
        assert accepted == {"ok": True, "problems": [], "card": None, "undrawable": PROOF}
        refused = R.check_answer(run, handoff, batch, T.SKARA, T.DECLINE, fit=T.fit)
        assert refused["ok"] is False
        assert "a card can be written: these name forms can be drawn" in refused["problems"][0]
        assert "'Skara Brae'" in refused["problems"][0]
        card = R.check_answer(run, handoff, batch, T.JABAL, T.writer_answer(JABAL_CARD), fit=T.fit)
        assert card["ok"] is False and any(p.startswith("font") for p in card["problems"])

    def test_the_import_records_the_proof_and_refuses_a_decline_the_contract_does_not_prove(
        self, tmp_path: Path
    ) -> None:
        run = undrawable_run(tmp_path)
        imported = step(run, tmp_path, "write", {T.SKARA: GOOD_WRITES[T.SKARA], T.JABAL: T.DECLINE})
        assert imported == {
            "stage": "write",
            "answers": 2,
            "mechanical_failures": 0,
            "undrawable": 1,
        }
        record = R.stage_records(run)["write"][T.JABAL]
        assert (record["kind"], record["card"], record["written"], record["basis"]) == (
            "write",
            None,
            None,
            [],
        )
        assert (record["problems"], record["undrawable"]) == ([], PROOF)
        other = tmp_path / "second"
        second = undrawable_run(other)
        with pytest.raises(R.RunError, match="malformed answer .*a card can be written"):
            step(second, other, "write", {T.SKARA: T.DECLINE, T.JABAL: T.DECLINE})

    def test_a_declined_site_is_cleared_and_no_later_stage_asks_it(self, tmp_path: Path) -> None:
        run = undrawable_run(tmp_path)
        step(run, tmp_path, "write", {T.SKARA: GOOD_WRITES[T.SKARA], T.JABAL: T.DECLINE})
        assert R.status(run)["states"] == {"cleared": 1, "due check": 1}
        step(run, tmp_path, "check", PASSES)
        assert step(run, tmp_path, "rewrite1", {})["questions"] == 0
        step(run, tmp_path, "verify", VERIFIES)
        assert step(run, tmp_path, "rewrite-v", {})["questions"] == 0
        rounds = R.read_rounds(run)
        assert [r["stage"] for r in rounds] == ["write", "check", "verify"]
        assert [T.JABAL in m for r in rounds for m in r["batches"].values()] == [True, False, False]
        assert R.outcomes(run)["counts"] == {"accepted": 1, "cleared name-undrawable": 1}
        rows = {r["site_id"]: r for r in R.read_outcomes(run)}
        jabal = rows[T.JABAL]
        assert (jabal["status"], jabal["reason"]) == (R.CLEARED, R.NAME_UNDRAWABLE)
        assert (jabal["card"], jabal["writer"], jabal["provenance"]) == (None, None, None)
        assert (jabal["attempts"], jabal["verification"], jabal["verifications"]) == (0, None, [])
        assert jabal["findings"] == [
            {"card": None, "reasons": [C.undrawable_reason({"Jabal al-ʿHayn": ("ʿ",)})]}
        ]
        assert rows[T.SKARA]["status"] == R.ACCEPTED

    def test_a_site_that_failed_a_card_may_still_be_declined_in_its_rewrite(
        self, tmp_path: Path
    ) -> None:
        run = undrawable_run(tmp_path)
        written = step(
            run, tmp_path, "write", {**GOOD_WRITES, T.JABAL: T.writer_answer(JABAL_CARD)}
        )
        assert written["mechanical_failures"] == 1
        step(run, tmp_path, "check", PASSES)
        assert step(run, tmp_path, "rewrite1", {T.JABAL: T.DECLINE})["undrawable"] == 1
        assert step(run, tmp_path, "check1", {})["questions"] == 0
        step(run, tmp_path, "verify", VERIFIES)
        R.outcomes(run)
        jabal = next(r for r in R.read_outcomes(run) if r["site_id"] == T.JABAL)
        assert (jabal["status"], jabal["reason"]) == (R.CLEARED, R.NAME_UNDRAWABLE)
        assert jabal["attempts"] == 1
        assert [f["card"] for f in jabal["findings"]] == [JABAL_CARD, None]
        assert jabal["findings"][0]["reasons"][0].startswith("font")

    def test_the_question_does_not_offer_the_decline_only_the_brief_does(
        self, tmp_path: Path
    ) -> None:
        """An export's prompts are pinned by sha256: offering the option in them would make every
        answer to an already exported question stale. The brief is the agent's instruction."""
        site = basis(T.JABAL)
        assert "undrawable" not in P.writer_prompt(site)
        assert "undrawable" not in P.rewrite_prompt(site, [P.Finding("A card.", ("No.",))])
        run = undrawable_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        text = R.brief(run, handoff, "write-001")
        assert '{"card": null, "basis": [], "undrawable": true}' in text
        assert "never for a site with a name form the font can draw" in text
        check_handoff = tmp_path / "handoff-check"
        answer_all(run, "write", handoff, {T.SKARA: GOOD_WRITES[T.SKARA], T.JABAL: T.DECLINE})
        R.import_stage(run, "write", fit=T.fit)
        R.export_stage(run, "check", check_handoff)
        assert "undrawable" not in R.brief(run, check_handoff, "check-001")


# ------------------------------------------------------------------------------ the web (a mock)
PAGE = "https://example.org/skara-brae"
PAGE_TEXT = b"<html><body><p>The site was occupied from roughly 3180 BC to around 2500 BC.</p></body></html>"
#: A register that refuses automated readers (as Historic England does): its quote cannot be proven.
REFUSING = "https://register.example/skara-brae"
#: A page that contradicts the card's storm claim, and a Wikipedia mirror serving the same text.
CONTRA = "https://en.wikipedia.org/wiki/Skara_Brae"
MIRROR = "https://www.wikiwand.com/en/Skara_Brae"
CONTRA_QUOTE = "A storm in the winter of 1850 stripped the grass from a large mound."
CONTRA_TEXT = f"<html><body><p>{CONTRA_QUOTE}</p></body></html>".encode()
#: An AI aggregator (lane WC's source rule refuses it) serving the very text of PAGE.
AGGREGATOR = "https://aroundus.com/p/skara-brae"


def judge_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        html = {"Content-Type": "text/html"}
        if str(request.url) in (PAGE, AGGREGATOR):
            return httpx.Response(200, headers=html, content=PAGE_TEXT)
        if str(request.url) in (CONTRA, MIRROR):
            return httpx.Response(200, headers=html, content=CONTRA_TEXT)
        if str(request.url) == REFUSING:
            return httpx.Response(403, content=b"forbidden")
        return httpx.Response(404, content=b"no")

    return httpx.Client(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------------------ the verification
def proven(verdict: str = "SUPPORTED") -> dict[str, Any]:
    return {"claim": "c", "verdict": verdict, "url": PAGE, "quote": "q", "proven": True}


def unproven(verdict: str = "UNVERIFIABLE") -> dict[str, Any]:
    return {"claim": "u", "verdict": verdict, "url": None, "quote": None, "proven": False}


class TestTheVerifiedRule:
    """CARD_DESCRIPTIONS.md 2.1: VERIFIED only without a contradiction, with at most one claim
    without a proving quote, and never the central (first) claim."""

    def test_a_card_whose_every_claim_is_proven_is_verified(self) -> None:
        assert R.card_verification([proven(), proven(), proven()]) == R.VERIFIED

    def test_one_unproven_claim_beside_a_proven_central_one_is_allowed(self) -> None:
        assert R.card_verification([proven(), unproven(), proven()]) == R.VERIFIED
        not_found = {**proven(), "proven": False}  # SUPPORTED, but the page lacks the quote
        assert R.card_verification([proven(), not_found]) == R.VERIFIED

    def test_the_central_claim_is_never_unproven(self) -> None:
        assert R.card_verification([unproven(), proven(), proven()]) == R.UNPROVEN

    def test_two_unproven_claims_are_too_many(self) -> None:
        assert CP.MAX_UNPROVEN_CLAIMS == 1
        claims = [proven(), unproven(), unproven(), proven(), proven(), proven()]
        assert R.card_verification(claims) == R.UNPROVEN

    def test_a_quote_the_page_does_not_hold_proves_nothing(self) -> None:
        not_found = {**proven(), "proven": False}  # SUPPORTED, but the machine found no quote
        assert R.card_verification([proven(), not_found, not_found]) == R.UNPROVEN
        assert R.card_verification([not_found, proven()]) == R.UNPROVEN

    def test_a_contradiction_proven_or_not_is_contradicted(self) -> None:
        assert R.card_verification([proven(), proven("CONTRADICTED")]) == R.CONTRADICTED
        refused = {**proven("CONTRADICTED"), "proven": False}  # a 403 page, a mis-copied quote
        assert R.card_verification([proven(), proven(), refused]) == R.CONTRADICTED

    def test_the_findings_of_a_verification_name_what_failed(self) -> None:
        record = {
            "kind": "verify",
            "claims": [
                {**proven("CONTRADICTED"), "claim": "found in 1850", "quote": "in 1851"},
                proven(),
                unproven(),
            ],
        }
        assert P.findings_of(record) == (
            f'The web check contradicts: found in 1850 ({PAGE}: "in 1851")',
            "The web check could not prove: u",
        )


STORM = "a storm laid bare stone structures in the sand dunes"
#: The rewrite after the storm claim was contradicted: the correction rests on web fact W1.
REWRITTEN = (
    "In the winter of 1850 a storm stripped the grass from a large mound on Orkney: beneath lay "
    "Skara Brae, a Neolithic village of hearths, beds and dressers, lived in from roughly 3180 BC."
)


def contradicted_answer() -> str:
    """The first verifier: the storm claim contradicted on Wikipedia (proven), on a mirror (never a
    source: not fetched, not proven) and on a register that refused the machine (not proven)."""
    return T.judge_answer(
        T.judged_claim(),
        T.judged_claim("CONTRADICTED", CONTRA_QUOTE, CONTRA, STORM),
        T.judged_claim("CONTRADICTED", CONTRA_QUOTE, MIRROR, "the storm claim, on a mirror"),
        T.judged_claim(
            "CONTRADICTED", "Skara Brae was dug out of the dunes by hand.", REFUSING, "the dunes"
        ),
    )


def rewrite_answer(
    card: str = REWRITTEN,
    repeats: list[str | None] | None = None,
    basis_ids: tuple[str, ...] = ("S1", "S3", "S6", "W1"),
) -> str:
    return json.dumps(
        {
            "card": card,
            "basis": list(basis_ids),
            "repeats": ["S2", None, "S2"] if repeats is None else repeats,
        }
    )


W1_PASS = T.checker_answer(claims=[("a storm in 1850 revealed it", ["W1"]), ("Neolithic", ["S1"])])
#: The second verifier of the rewrite: both claims W1_PASS's checker listed, proven.
VERIFIES_REWRITTEN = T.judge_answer(T.judged_claim(), T.judged_claim(claim="a Neolithic village"))
#: The one site of `chain`, the records of a card verified, contradicted, rewritten, verified again.
CHAINED = "site-1"


def chain(other: dict[str, str] | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Every stage's record of CHAINED: each judgement of the card its writer's record holds, except
    the stages `other` gives another card."""
    first, second = "the first card", "the rewritten card"
    supported = {**proven(), "quote_outcome": "found"}
    rows = {
        "write": {"card": first, "problems": []},
        "check": {"card": first, "verdict": "PASS"},
        "verify": {
            "kind": "verify",
            "card": first,
            "verdict": R.CONTRADICTED,
            "claims": [supported, {**supported, "verdict": "CONTRADICTED"}],
        },
        "rewrite-v": {"card": second, "problems": []},
        "check-v": {"card": second, "verdict": "PASS"},
        "verify2": {"kind": "verify", "card": second, "verdict": R.VERIFIED, "claims": [supported]},
    }
    records: dict[str, dict[str, dict[str, Any]]] = {stage: {} for stage in R.STAGES}
    for stage, row in rows.items():
        card = (other or {}).get(stage, row["card"])
        records[stage][CHAINED] = {"site_id": CHAINED, "stage": stage, **row, "card": card}
    return records


class TestTheVerification:
    def _checked(self, tmp_path: Path) -> Path:
        run = make_run(tmp_path, [T.row(T.SKARA), T.row(T.NEWGRANGE)])
        step(run, tmp_path, "write", GOOD_WRITES)
        step(run, tmp_path, "check", PASSES)
        return run

    def _contradicted(self, tmp_path: Path) -> Path:
        run = self._checked(tmp_path)
        verdicts = step(run, tmp_path, "verify", {**VERIFIES, T.SKARA: contradicted_answer()})
        assert verdicts["verdicts"] == {"CONTRADICTED": 1, "VERIFIED": 1}
        return run

    def _prompt(self, tmp_path: Path, stage: str) -> str:
        handoff = tmp_path / f"handoff-{stage}"
        line = next(line for line in OH.manifest(handoff) if line["label"] == T.SKARA)
        return (handoff / line["prompt_path"]).read_text(encoding="utf-8")

    def test_every_accepted_card_is_asked_five_to_a_batch(self) -> None:
        due = {f"site-{n:02d}": R.Progress(R.DUE, "verify") for n in range(7)}
        groups = R._batches("verify", due)
        assert [(batch, len(members)) for batch, members in groups] == [
            ("verify-001", 5),
            ("verify-002", 2),
        ]

    def test_the_verifier_sees_only_the_card_and_every_quote_is_checked(
        self, tmp_path: Path
    ) -> None:
        run = self._contradicted(tmp_path)
        prompt = self._prompt(tmp_path, "verify")
        assert prompt == P.judge_prompt("Skara Brae", "Scotland", T.GOOD[T.SKARA])
        record = {r["site_id"]: r for r in R.read_jsonl(run / "STAGE-verify.jsonl")}[T.SKARA]
        outcomes = [(c["verdict"], c["quote_outcome"], c["proven"]) for c in record["claims"]]
        assert outcomes == [
            ("SUPPORTED", "found", True),
            ("CONTRADICTED", "found", True),
            ("CONTRADICTED", f"source refused: {R.url_problem(MIRROR)}", False),
            ("CONTRADICTED", "fetch failed", False),
        ]
        assert record["verdict"] == R.CONTRADICTED and record["unproven"] == 3
        assert R.status(run)["states"] == {"accepted": 1, "due rewrite-v": 1}

    def test_a_contradicted_card_is_rewritten_with_the_pages_and_quotes(
        self, tmp_path: Path
    ) -> None:
        run = self._contradicted(tmp_path)
        R.export_stage(run, "rewrite-v", tmp_path / "handoff-rewrite-v")
        prompt = self._prompt(tmp_path, "rewrite-v")
        assert (
            f"THE CARD THE WEB CHECK DID NOT VERIFY ({len(T.GOOD[T.SKARA])} characters)" in prompt
        )
        assert f'1. {STORM}\n   page: {CONTRA}\n   quote: "{CONTRA_QUOTE}"' in prompt
        assert "(the machine found this quote on the page)" in prompt
        assert "could not confirm this quote on the page: fetch failed" in prompt
        assert "could not confirm this quote on the page: source refused: " in prompt
        # a web fact: only a proven contradiction - its page admitted by lane WC's source rule
        assert f'W1 "{CONTRA_QUOTE}" - {CONTRA}' in prompt and "W2" not in prompt
        assert '"repeats": ["S3"]' in prompt and "When in doubt, drop the claim" in prompt
        # the identity is never corrected from the web: a page may describe a namesake
        assert "is never corrected from a web fact" in prompt

    def test_the_web_facts_are_the_proven_contradictions_beyond_the_central_claim(self) -> None:
        """A proven contradiction is a web fact - but never one of the central claim (what the site
        is, and where): a page that says the site is something else may describe a namesake."""
        claims = [
            {**proven("CONTRADICTED"), "url": CONTRA, "quote": "zero"},
            {**proven("CONTRADICTED"), "url": CONTRA, "quote": "one"},
            {**proven("CONTRADICTED"), "url": REFUSING, "quote": "three", "proven": False},
            {**proven(), "url": PAGE, "quote": "five"},
            {**proven("CONTRADICTED"), "url": PAGE, "quote": "six"},
        ]
        facts = R.web_facts({"claims": claims})
        assert facts == (
            R.C.WebFact("W1", CONTRA, "one"),
            R.C.WebFact("W2", PAGE, "six"),
        )

    def test_a_quote_on_a_page_the_source_rule_refuses_proves_nothing(self, tmp_path: Path) -> None:
        """An AI aggregator or a Wikipedia mirror may repeat the very text under test (this
        project's, or Wikipedia's wrong sentence): lane WC's source rule refuses it, so its quote
        proves nothing - found on the page or not - and the page is never fetched."""
        run = self._checked(tmp_path)
        answer = T.judge_answer(
            T.judged_claim(url=AGGREGATOR), T.judged_claim(url=MIRROR, claim="from 3180 BC")
        )
        verdicts = step(run, tmp_path, "verify", {**VERIFIES, T.SKARA: answer})["verdicts"]
        assert verdicts == {"UNPROVEN": 1, "VERIFIED": 1}
        record = {r["site_id"]: r for r in R.read_jsonl(run / "STAGE-verify.jsonl")}[T.SKARA]
        assert [(c["quote_outcome"], c["proven"]) for c in record["claims"]] == [
            (f"source refused: {R.url_problem(AGGREGATOR)}", False),
            (f"source refused: {R.url_problem(MIRROR)}", False),
        ]
        kept = {json.loads(p.read_text("utf-8"))["url"] for p in (run / "pages").glob("*.json")}
        assert kept == {PAGE}

    def test_the_rewrite_names_the_sentence_each_contradicted_claim_repeats(
        self, tmp_path: Path
    ) -> None:
        site = basis().with_web([R.C.WebFact("W1", CONTRA, CONTRA_QUOTE)])
        written = A.parse_verify_writer(rewrite_answer(repeats=["S2"]), site, 1)
        assert written.repeats == ("S2",) and "W1" in written.basis
        for repeats, why in (
            (["S2", None], "one per contradicted claim"),
            (["W1"], "neither null nor the id of a sentence"),
            (["S99"], "neither null nor the id of a sentence"),
        ):
            with pytest.raises(A.AnswerError, match=why):
                A.parse_verify_writer(rewrite_answer(repeats=repeats), site, 1)
        with pytest.raises(A.AnswerError, match="exactly"):
            A.parse_verify_writer(T.writer_answer(REWRITTEN), site, 1)

    def test_a_correction_rests_on_its_web_fact_and_the_fact_basis_records_it(
        self, tmp_path: Path
    ) -> None:
        run = self._contradicted(tmp_path)
        written = step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        assert written["mechanical_failures"] == 0  # 1850 is grounded by W1 alone
        assert "1850" not in T.DESCRIPTIONS[T.SKARA]
        R.export_stage(run, "check-v", tmp_path / "handoff-check-v")
        prompt = self._prompt(tmp_path, "check-v")
        assert REWRITTEN in prompt and f'W1 "{CONTRA_QUOTE}" - {CONTRA}' in prompt
        assert "only if that fact's page is a reputable source" in prompt
        assert "makes this_site false" in prompt
        answer_all(run, "check-v", tmp_path / "handoff-check-v", {T.SKARA: W1_PASS})
        assert R.import_stage(run, "check-v", fit=T.fit)["verdicts"] == {"PASS": 1}
        verified = step(run, tmp_path, "verify2", {T.SKARA: VERIFIES_REWRITTEN})
        assert verified["verdicts"] == {"VERIFIED": 1}
        result = R.outcomes(run)
        assert result["counts"] == {"accepted": 2} and result["description_defects"] == 2
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        provenance = CP.validate(skara["provenance"])
        assert (skara["card"], skara["attempts"]) == (REWRITTEN, 2)
        assert (provenance["check"]["stage"], provenance["verify"]["stage"]) == (
            "check-v",
            "verify2",
        )
        assert provenance["verify"]["by"] == "teaser-verify2-001"
        assert provenance["verify"]["text_sha256"] == T.sha(REWRITTEN)
        assert provenance["web_facts"] == [{"id": "W1", "url": CONTRA, "quote": CONTRA_QUOTE}]
        assert [v["stage"] for v in skara["verifications"]] == ["verify", "verify2"]
        assert skara["findings"][0]["reasons"][0].startswith("The web check contradicts: ")

    def test_each_mapped_contradiction_is_a_description_defect_for_its_lane(
        self, tmp_path: Path
    ) -> None:
        run = self._contradicted(tmp_path)
        step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        step(run, tmp_path, "check-v", {T.SKARA: W1_PASS})
        step(run, tmp_path, "verify2", {T.SKARA: VERIFIES_REWRITTEN})
        R.outcomes(run)
        defects = R.read_jsonl(run / "DESCRIPTION_DEFECTS.jsonl")
        # three contradicted claims: two repeat S2, one repeats no sentence (not the text's fault)
        assert [(d["sentence"], d["url"], d["proven"]) for d in defects] == [
            (2, CONTRA, True),
            (2, REFUSING, False),
        ]
        first = defects[0]
        assert (first["stage"], first["candidates"]) == ("verify", ["S2"])
        assert first["sentence_text"] == basis().sentences[1].text
        assert (first["basis"], first["owner_lane"]) == ("W", "WA")
        assert (first["claim"], first["quote"]) == (STORM, CONTRA_QUOTE)
        assert (first["verifier"], first["mapped_by"]) == (
            "teaser-verify-001",
            "teaser-rewrite-v-001",
        )
        assert first["desc_sha256"] == T.sha(T.DESCRIPTIONS[T.SKARA])
        report = (run / "OUTCOMES.md").read_text(encoding="utf-8")
        assert "description sentences the web contradicts: 2" in report
        assert f"CONTRADICTED: {STORM} - {CONTRA} (found)" in report
        assert "| site | status | verification | card |" in report

    def test_a_sentence_checked_text_s_defect_is_lane_wc_s(self) -> None:
        assert R.OWNER_LANE == {"R": "WA", "S": "WA", "T": "WA", "W": "WA", "WC": "WC"}

    def test_still_contradicted_after_the_rewrite_the_site_gets_no_card(
        self, tmp_path: Path
    ) -> None:
        run = self._contradicted(tmp_path)
        step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        step(run, tmp_path, "check-v", {T.SKARA: W1_PASS})
        again = T.judge_answer(T.judged_claim(), T.judged_claim("CONTRADICTED", claim="1850"))
        step(run, tmp_path, "verify2", {T.SKARA: again})
        R.outcomes(run)
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        assert (skara["status"], skara["reason"]) == (R.CLEARED, R.CONTRADICTED_AFTER_VERIFY)
        assert (skara["card"], skara["provenance"]) == (None, None)
        assert skara["verification"] == R.CONTRADICTED and len(skara["verifications"]) == 2
        # the second verifier's contradiction rests on the sentences check-v found (S1 here): a
        # description defect whose sentence no writer named - the repair gets the candidates
        defects = R.read_jsonl(run / "DESCRIPTION_DEFECTS.jsonl")
        assert [(d["stage"], d["sentence"], d["candidates"], d["mapped_by"]) for d in defects] == [
            ("verify", 2, ["S2"], "teaser-rewrite-v-001"),
            ("verify", 2, ["S2"], "teaser-rewrite-v-001"),
            ("verify2", None, ["S1"], None),
        ]
        last = defects[-1]
        assert (last["claim"], last["url"], last["proven"]) == ("1850", PAGE, True)
        assert (last["verifier"], last["sentence_text"]) == ("teaser-verify2-001", None)

    def test_a_second_contradiction_of_a_card_on_web_facts_alone_is_no_defect(
        self, tmp_path: Path
    ) -> None:
        """A rewrite whose every claim rests on a web fact says nothing of the description: the
        second verifier's contradiction of it is a dispute between pages, not a defect."""
        run = self._contradicted(tmp_path)
        step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        web_only = T.checker_answer(claims=[("a storm in 1850 revealed it", ["W1"])])
        step(run, tmp_path, "check-v", {T.SKARA: web_only})
        again = T.judge_answer(T.judged_claim(), T.judged_claim("CONTRADICTED", claim="1850"))
        step(run, tmp_path, "verify2", {T.SKARA: again})
        R.outcomes(run)
        defects = R.read_jsonl(run / "DESCRIPTION_DEFECTS.jsonl")
        assert [d["stage"] for d in defects] == ["verify", "verify"]

    def test_the_rewrite_and_its_check_keep_the_web_facts_they_were_asked_with(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The web facts a rewrite and its check were shown are recorded with them; the provenance
        records those, and a code change between the imports that would offer others (renumbered W
        ids, a fact the checker never saw under its id) is refused, not written."""
        run = self._contradicted(tmp_path)
        step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        step(run, tmp_path, "check-v", {T.SKARA: W1_PASS})
        step(run, tmp_path, "verify2", {T.SKARA: VERIFIES_REWRITTEN})
        fact = {"id": "W1", "url": CONTRA, "quote": CONTRA_QUOTE}
        for stage in ("rewrite-v", "check-v"):
            record = {r["site_id"]: r for r in R.read_jsonl(run / f"STAGE-{stage}.jsonl")}
            assert record[T.SKARA]["web_facts"] == [fact]
        monkeypatch.setattr(R, "web_facts", lambda verified: ())
        with pytest.raises(R.RunError, match="STAGE-check-v was asked with web facts"):
            R.outcomes(run)

    def test_the_state_is_the_one_card_every_judgement_judged(self) -> None:
        state = R.progress(CHAINED, chain())
        assert (state.status, state.card) == (R.ACCEPTED, "the rewritten card")

    @pytest.mark.parametrize(
        ("stage", "writer"),
        [
            ("check", "write"),
            ("verify", "write"),
            ("check-v", "rewrite-v"),
            ("verify2", "rewrite-v"),
        ],
    )
    def test_a_judgement_of_another_card_is_refused(self, stage: str, writer: str) -> None:
        """A check or verification of another text than its writer's record holds (a stage
        imported again with other answers, a file edited by hand) never counts for the card."""
        with pytest.raises(
            R.RunError, match=f"STAGE-{stage} judged another card than STAGE-{writer}"
        ):
            R.progress(CHAINED, chain({stage: "another card"}))

    def test_a_stage_imported_again_with_another_card_is_refused(self, tmp_path: Path) -> None:
        """The runbook's recovery for a malformed answer - delete it, have it answered again - must
        not swap a rewrite after its check and its verification: the import refuses a card the later
        stages did not judge, and writes nothing."""
        run = self._contradicted(tmp_path)
        step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        step(run, tmp_path, "check-v", {T.SKARA: W1_PASS})
        step(run, tmp_path, "verify2", {T.SKARA: VERIFIES_REWRITTEN})
        before = (run / "STAGE-rewrite-v.jsonl").read_bytes()
        handoff = tmp_path / "handoff-rewrite-v"
        line = next(line for line in OH.manifest(handoff) if line["label"] == T.SKARA)
        (handoff / line["answer_path"]).unlink()
        OH.write_answer(
            handoff, model=OH.OPUS_MODEL, batch_id=line["batch_id"], stage="rewrite-v", label=T.SKARA,
            text=rewrite_answer(T.GOOD[T.SKARA], basis_ids=("S1", "S2", "S3", "S6")),
            answered_by=R.agent_name(line["batch_id"]),
        )  # fmt: skip
        with pytest.raises(R.RunError, match="STAGE-check-v judged another card"):
            R.import_stage(run, "rewrite-v", fit=T.fit)
        assert (run / "STAGE-rewrite-v.jsonl").read_bytes() == before
        R.outcomes(run)
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        assert skara["card"] == REWRITTEN

    def test_unproven_twice_the_site_gets_no_card(self, tmp_path: Path) -> None:
        run = self._checked(tmp_path)
        vague = T.judge_answer(
            T.judged_claim(),
            T.judged_claim("UNVERIFIABLE", None, None, "hearths"),
            T.judged_claim("UNVERIFIABLE", None, None, "dressers"),
        )
        assert step(run, tmp_path, "verify", {**VERIFIES, T.SKARA: vague})["verdicts"] == {
            "UNPROVEN": 1,
            "VERIFIED": 1,
        }
        R.export_stage(run, "rewrite-v", tmp_path / "handoff-rewrite-v")
        prompt = self._prompt(tmp_path, "rewrite-v")
        assert "CONTRADICTED - a page says otherwise:\n(none)" in prompt
        assert "- hearths\n- dressers" in prompt and "WEB FACTS" not in prompt
        with_web_fact = rewrite_answer(T.GOOD[T.SKARA], [])  # there is no web fact to rest on
        assert (
            "not sentence ids"
            in R.check_answer(
                run,
                tmp_path / "handoff-rewrite-v",
                "rewrite-v-001",
                T.SKARA,
                with_web_fact,
                fit=T.fit,
            )["problems"][0]
        )
        answer_all(
            run, "rewrite-v", tmp_path / "handoff-rewrite-v",
            {T.SKARA: rewrite_answer(T.GOOD[T.SKARA], [], ("S2", "S3"))},
        )  # fmt: skip
        R.import_stage(run, "rewrite-v", fit=T.fit)
        step(run, tmp_path, "check-v", {T.SKARA: PASSES[T.SKARA]})
        step(run, tmp_path, "verify2", {T.SKARA: vague})
        R.outcomes(run)
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        assert (skara["status"], skara["reason"]) == (R.CLEARED, R.UNPROVEN_AFTER_VERIFY)
        assert R.read_jsonl(run / "DESCRIPTION_DEFECTS.jsonl") == []

    def test_a_rewrite_the_checker_fails_clears_the_site(self, tmp_path: Path) -> None:
        run = self._contradicted(tmp_path)
        step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        fail = T.checker_answer("FAIL", [("1850", [])], ["W1 is not on a reputable page."])
        step(run, tmp_path, "check-v", {T.SKARA: fail})
        assert step(run, tmp_path, "verify2", {})["questions"] == 0
        R.outcomes(run)
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        assert (skara["status"], skara["reason"]) == (R.CLEARED, R.FAILED_VERIFY_REWRITE)

    def test_a_rewrite_that_fails_the_mechanical_checks_clears_the_site(
        self, tmp_path: Path
    ) -> None:
        run = self._contradicted(tmp_path)
        written = step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer("Skara Brae.")})
        assert written["mechanical_failures"] == 1
        assert step(run, tmp_path, "check-v", {})["questions"] == 0
        assert R.status(run)["states"] == {"accepted": 1, "cleared": 1}
        R.outcomes(run)
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        assert skara["reason"] == R.FAILED_VERIFY_REWRITE and skara["attempts"] == 2

    def test_a_number_only_a_web_fact_gives_is_refused_without_it(self) -> None:
        assert any(
            p.startswith("numbers not in the description: 1850") for p in problems(REWRITTEN)
        )
        with_fact = basis().with_web([R.C.WebFact("W1", CONTRA, CONTRA_QUOTE)])
        assert C.problems(REWRITTEN, with_fact, fit=T.fit) == []

    def test_a_verifier_who_wrote_or_checked_the_card_is_refused(self, tmp_path: Path) -> None:
        run = self._checked(tmp_path)
        with pytest.raises(R.RunError, match="wrote or checked this site before"):
            step(run, tmp_path, "verify", VERIFIES, by="teaser-check-001")

    def test_the_second_verifier_is_a_new_one(self, tmp_path: Path) -> None:
        run = self._contradicted(tmp_path)
        step(run, tmp_path, "rewrite-v", {T.SKARA: rewrite_answer()})
        step(run, tmp_path, "check-v", {T.SKARA: W1_PASS})
        with pytest.raises(R.RunError, match="wrote or checked this site before"):
            step(run, tmp_path, "verify2", {T.SKARA: VERIFIES_REWRITTEN}, by="teaser-verify-001")

    def test_a_verifier_who_lists_fewer_claims_than_the_checker_is_refused(
        self, tmp_path: Path
    ) -> None:
        """A verifier that lists only the central claim would VERIFY a card whose other claims
        nobody researched: it lists at least as many claims as the check that accepted the card
        (another agent's count - the verifier learns only the number, from `check-answer`)."""
        run = make_run(tmp_path, [T.row(T.SKARA)])
        step(run, tmp_path, "write", {T.SKARA: GOOD_WRITES[T.SKARA]})
        three = T.checker_answer(
            claims=[("on Orkney", ["S1"]), ("a Neolithic village", ["S1"]), ("3180 BC", ["S3"])]
        )
        step(run, tmp_path, "check", {T.SKARA: three})
        handoff = tmp_path / "handoff-verify"
        R.export_stage(run, "verify", handoff)
        shown = R.check_answer(run, handoff, "verify-001", T.SKARA, T.judge_answer(), fit=T.fit)
        assert not shown["ok"]
        assert shown["problems"] == [
            "the answer lists 1 claim(s); the card makes at least 3 (another agent's count): list "
            "every claim of the text, each fact on its own"
        ]
        all_three = T.judge_answer(*(T.judged_claim(claim=f"claim {n}") for n in range(3)))
        assert R.check_answer(run, handoff, "verify-001", T.SKARA, all_three, fit=T.fit)["ok"]
        answer_all(run, "verify", handoff, {T.SKARA: T.judge_answer()})
        with pytest.raises(R.RunError, match="lists 1 claim"):
            R.import_stage(run, "verify", fit=T.fit, client=judge_client(), pace=0)

    def test_a_fetch_that_failed_for_a_passing_reason_is_tried_again(self, tmp_path: Path) -> None:
        """No answer, a 429 or a 5xx may pass: such a page is fetched again at the next import (a
        404 is the page's answer and is kept), and the import names every page still failing so it
        can be run again before the next stage is exported."""
        calls: Counter[str] = Counter()
        down = "https://down.example/skara-brae"
        gone = "https://gone.example/newgrange"
        unreachable = "https://unreachable.example/newgrange"

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            calls[url] += 1
            if url == unreachable:
                raise httpx.ConnectError("no route to host", request=request)
            if url == PAGE and calls[url] == 1:
                return httpx.Response(429, content=b"slow down")
            if url == PAGE:
                return httpx.Response(200, headers={"Content-Type": "text/html"}, content=PAGE_TEXT)
            if url == down:
                return httpx.Response(503, content=b"down")
            return httpx.Response(404, content=b"no")

        run = self._checked(tmp_path)
        handoff = tmp_path / "handoff-verify"
        R.export_stage(run, "verify", handoff)
        answers = {
            T.SKARA: T.judge_answer(T.judged_claim(), T.judged_claim(url=down, claim="x")),
            T.NEWGRANGE: T.judge_answer(
                T.judged_claim(url=gone), T.judged_claim(url=unreachable, claim="y")
            ),
        }
        answer_all(run, "verify", handoff, answers)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        first = R.import_stage(run, "verify", fit=T.fit, client=client, pace=0)
        assert first["verdicts"] == {"UNPROVEN": 2}
        assert first["transient_failures"] == [down, PAGE, unreachable]
        again = R.import_stage(run, "verify", fit=T.fit, client=client, pace=0)
        assert again["verdicts"] == {"UNPROVEN": 1, "VERIFIED": 1}
        assert again["transient_failures"] == [down, unreachable]
        assert calls == {PAGE: 2, down: 2, unreachable: 2, gone: 1}

    def test_the_verify_stages_wait_for_every_check(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [T.row(T.SKARA), T.row(T.NEWGRANGE)])
        step(run, tmp_path, "write", {**GOOD_WRITES, T.SKARA: T.writer_answer("Skara Brae.")})
        step(run, tmp_path, "check", PASSES)
        with pytest.raises(R.RunError, match="wait for their import"):
            R.export_stage(run, "verify", tmp_path / "h-verify")

    def test_check_answer_takes_a_verifier_s_shape_only(self, tmp_path: Path) -> None:
        run = self._checked(tmp_path)
        handoff = tmp_path / "handoff-verify"
        R.export_stage(run, "verify", handoff)
        good = R.check_answer(run, handoff, "verify-001", T.SKARA, T.judge_answer(), fit=T.fit)
        assert good == {"ok": True, "problems": []}
        bad = R.check_answer(run, handoff, "verify-001", T.SKARA, '{"claims": []}', fit=T.fit)
        assert not bad["ok"]

    def test_the_brief_of_a_verifier(self, tmp_path: Path) -> None:
        run = self._checked(tmp_path)
        handoff = tmp_path / "handoff-verify"
        R.export_stage(run, "verify", handoff)
        text = R.brief(run, handoff, "verify-001")
        assert "verifier verify-001" in text and "sources on the web" in text
        assert "--answered-by teaser-verify-001" in text and "verified or judged" in text
        assert all(model_id in text for model_id in OH.NEW_ANSWER_MODELS)

    def test_the_judge_lists_the_central_claim_first(self) -> None:
        prompt = P.judge_prompt("Skara Brae", "Scotland", T.GOOD[T.SKARA])
        assert "List every claim of the text, the central claim first" in prompt


# ------------------------------------------------------------------------------ the pilot judge


def claim(
    verdict: str = "SUPPORTED",
    quote: str = "occupied from roughly 3180 BC to around 2500 BC",
    url: str = PAGE,
) -> dict[str, Any]:
    return {
        "claim": "lived in from roughly 3180 BC",
        "verdict": verdict,
        "url": url,
        "quote": quote,
    }


def judged(
    verdict: str = "SUPPORTED", quote: str = "occupied from roughly 3180 BC to around 2500 BC"
) -> str:
    return json.dumps({"claims": [claim(verdict, quote)]})


class TestThePilotJudge:
    def _accepted_run(self, tmp_path: Path, check: str = PASSES[T.SKARA]) -> Path:
        run = make_run(tmp_path, [T.row(T.SKARA)])
        step(run, tmp_path, "write", {T.SKARA: GOOD_WRITES[T.SKARA]})
        step(run, tmp_path, "check", {T.SKARA: check})
        claims = len(json.loads(check)["claims"])
        verifies = T.judge_answer(*(T.judged_claim(claim=f"claim {n}") for n in range(claims)))
        step(run, tmp_path, "verify", {T.SKARA: verifies})
        R.outcomes(run)
        return run

    def _judge(self, run: Path, tmp_path: Path, text: str, by: str = "") -> dict[str, Any]:
        handoff = tmp_path / "handoff-judge"
        R.export_judge(run, handoff)
        OH.write_answer(
            handoff, model=OH.OPUS_MODEL, batch_id="judge-001", stage=R.JUDGE_STAGE, label=T.SKARA, text=text,
            answered_by=by or "teaser-judge-001",
        )  # fmt: skip
        return R.import_judge(run, client=judge_client(), pace=0)

    def test_a_quoted_support_passes(self, tmp_path: Path) -> None:
        result = self._judge(self._accepted_run(tmp_path), tmp_path, judged())
        assert result["pilot"] == "PASS" and result["supported"] == 1

    def test_a_proven_contradiction_fails_the_pilot(self, tmp_path: Path) -> None:
        result = self._judge(self._accepted_run(tmp_path), tmp_path, judged("CONTRADICTED"))
        assert result["pilot"] == "FAIL" and result["wrong_cards"] == [T.SKARA]
        assert (result["contradicted"], result["contradicted_unproven"]) == (1, 0)

    def test_an_unproven_contradiction_fails_the_pilot(self, tmp_path: Path) -> None:
        """A contradiction on a page that refused the machine (403) is still a contradiction: the
        pilot fails, even though its one unproven claim of 11 stays under the 10 % share."""
        claims = [claim() for _ in range(10)]
        claims.append(
            claim("CONTRADICTED", "Skara Brae was occupied from about 4000 BC.", REFUSING)
        )
        run = self._accepted_run(tmp_path)
        result = self._judge(run, tmp_path, json.dumps({"claims": claims}))
        assert (result["contradicted"], result["contradicted_unproven"]) == (0, 1)
        assert result["unproven_share"] <= R.PILOT_MAX_UNPROVEN_SHARE
        assert result["pilot"] == "FAIL" and result["disputed_cards"] == [T.SKARA]
        report = (run / "JUDGE.md").read_text(encoding="utf-8")
        head, _, body = report.partition("## Every contradiction")
        assert "1 contradicted without a proving quote" in head
        assert f"CONTRADICTED (not proven): lived in from roughly 3180 BC - {REFUSING}" in body

    def test_a_quote_the_page_does_not_hold_proves_nothing(self, tmp_path: Path) -> None:
        text = judged(quote="occupied from roughly 4000 BC to around 2500 BC")
        result = self._judge(self._accepted_run(tmp_path), tmp_path, text)
        assert result["unproven"] == 1 and result["pilot"] == "FAIL"

    def test_a_judge_who_lists_fewer_claims_than_the_checker_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The pilot's judge, like every verifier, covers at least the accepting check's claims."""
        two = T.checker_answer(claims=[("on Orkney", ["S1"]), ("3180 BC", ["S3"])])
        run = self._accepted_run(tmp_path, two)
        handoff = tmp_path / "handoff-judge"
        with pytest.raises(R.RunError, match="lists 1 claim"):
            self._judge(run, tmp_path, judged())
        shown = R.check_answer(run, handoff, "judge-001", T.SKARA, judged(), fit=T.fit)
        assert not shown["ok"] and "the card makes at least 2" in shown["problems"][0]

    def test_a_judge_who_worked_on_the_card_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(R.RunError, match="answered a question of this run"):
            self._judge(self._accepted_run(tmp_path), tmp_path, judged(), by="teaser-check-001")

    def test_the_pilot_s_judge_is_no_verifier_of_the_run(self, tmp_path: Path) -> None:
        """The gate is a fresh judge's: not the verifier of this card, nor of any other - the
        judge of Skara Brae is refused for having verified Newgrange."""
        run = make_run(tmp_path, [T.row(T.SKARA), T.row(T.NEWGRANGE)])
        step(run, tmp_path, "write", GOOD_WRITES)
        step(run, tmp_path, "check", PASSES)
        handoff = tmp_path / "handoff-verify"
        R.export_stage(run, "verify", handoff)
        for site_id, name in ((T.SKARA, "teaser-verify-a"), (T.NEWGRANGE, "teaser-verify-b")):
            OH.write_answer(
                handoff, model=OH.OPUS_MODEL, batch_id="verify-001", stage="verify", label=site_id,
                text=T.judge_answer(), answered_by=name,
            )  # fmt: skip
        R.import_stage(run, "verify", fit=T.fit, client=judge_client(), pace=0)
        R.outcomes(run)
        judge = tmp_path / "handoff-judge"
        R.export_judge(run, judge)
        for site_id in (T.SKARA, T.NEWGRANGE):
            OH.write_answer(
                judge, model=OH.OPUS_MODEL, batch_id="judge-001", stage=R.JUDGE_STAGE, label=site_id, text=judged(),
                answered_by="teaser-verify-b",
            )  # fmt: skip
        with pytest.raises(R.RunError, match=f"{T.SKARA}: the judge teaser-verify-b"):
            R.import_judge(run, client=judge_client(), pace=0)

    def test_the_import_asks_the_web_without_personal_data(self) -> None:
        with R.judge_client() as client:
            agent = client.headers["User-Agent"]
            timeout = client.timeout
        assert agent == research_web.USER_AGENT and "@" not in agent
        with R.Q.http_client() as audit:
            assert audit.timeout == timeout and audit.follow_redirects
