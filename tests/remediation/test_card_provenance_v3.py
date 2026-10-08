"""Card provenance version 3 (contract shorts-v1): the shape, the one builder, the shorts pin.

Version 2 stays valid (the 2,830 live cards); version 3 adds the contract, the models of the four
stages, the hook, the anchors, the reserve and `shorts_ready`. The tests assert each rule by the
refusal it produces, so removing a rule turns its test red.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from pipeline.utils import card_provenance as CP

DESCRIPTION = "Tarxien is a complex of temples on Malta. It dates to 3600 BC."
CARD = "Stone temples rise beside a Maltese town, older than the pyramids of Giza."
OPUS = "anthropic/claude-opus-5-5 (Claude Code agent)"
SONNET = "anthropic/claude-sonnet-5-5 (Claude Code agent)"
AI = "Claude (Anthropic): anthropic/claude-opus-5-5, anthropic/claude-sonnet-5-5"


def v2(**over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "run": "wb-2026-09-26",
        "ai_system": AI,
        "card": CARD,
        "description": DESCRIPTION,
        "stage": "check",
        "checker": "teaser-check-001",
        "checked_at": "2026-09-26T12:00:00+00:00",
        "claims": [{"claim": "temples on Malta", "support": ["S1"]}],
        "verify": {
            "verdict": "VERIFIED",
            "stage": "verify",
            "by": "teaser-verify-001",
            "at": "2026-09-26T13:00:00+00:00",
            "claims": 2,
            "unproven": 0,
            "text_sha256": CP.text_sha256(CARD),
        },
        "web_facts": [],
    }
    return CP.build(**{**fields, **over})


def v3(**over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "run": "wb-shorts-2026-10-09",
        "ai_system": AI,
        "card": CARD,
        "description": DESCRIPTION,
        "stage": "check",
        "checker": "fact_checker:teaser-check-001",
        "checked_at": "2026-10-09T12:00:00+00:00",
        "claims": [{"claim": "temples on Malta", "support": ["S1"]}],
        "verify": {
            "verdict": "VERIFIED",
            "stage": "verify",
            "by": "web_verifier:teaser-verify-001",
            "at": "2026-10-09T13:00:00+00:00",
            "claims": 2,
            "unproven": 0,
            "text_sha256": CP.text_sha256(CARD),
        },
        "web_facts": [],
        "models": {"write": OPUS, "rate": OPUS, "check": SONNET, "verify": SONNET},
        "hook": {"type": "object", "rating": 4, "variant": 2},
        "anchors": ["Stone temples"],
        "reserve": ["S2"],
        "shorts_ready": True,
    }
    return CP.build_v3(**{**fields, **over})


class TestVersionTwoStaysValid:
    def test_a_version_2_provenance_validates_and_builds_as_before(self) -> None:
        built = v2()
        assert built["v"] == 2 and CP.VERSION == 2
        assert CP.validate(copy.deepcopy(built)) == built
        assert set(built) == CP._KEYS

    def test_a_version_2_provenance_is_never_a_shorts_pin(self) -> None:
        """A card that names its site cannot be narrated (owner decision D1)."""
        assert CP.shorts_pin(v2(), DESCRIPTION) is None

    @pytest.mark.parametrize("version", [1, 4, True, None, "3"])
    def test_any_other_version_is_refused(self, version: Any) -> None:
        data = {**v2(), "v": version}
        with pytest.raises(ValueError, match="v is not one of"):
            CP.validate(data)

    def test_a_version_2_provenance_with_a_version_3_key_is_refused(self) -> None:
        with pytest.raises(ValueError, match="carries"):
            CP.validate({**v2(), "hook": {}})

    def test_a_version_3_provenance_without_its_keys_is_refused(self) -> None:
        data = {**v3()}
        del data["reserve"]
        with pytest.raises(ValueError, match="carries"):
            CP.validate(data)


class TestVersionThree:
    def test_the_builder_adds_exactly_the_contract_keys(self) -> None:
        built = v3()
        assert built["v"] == 3 and built["contract"] == "shorts-v1"
        assert set(built) == CP._KEYS_V3
        assert CP.validate(copy.deepcopy(built)) == built
        assert CP.card_provenance_of({CP.CARD_PROVENANCE_KEY: built}) == built

    def test_a_version_3_card_is_described_and_marked_like_any_teaser(self) -> None:
        built = v3()
        assert CP.describes(built, CARD) and CP.card_ai(built, CARD) == CP.AI_GENERATED
        assert CP.stale(built, DESCRIPTION + " Edited.")

    def test_the_contract_is_shorts_v1(self) -> None:
        data = {**v3(), "contract": "shorts-v2"}
        with pytest.raises(ValueError, match="contract 'shorts-v2'"):
            CP.validate(data)

    @pytest.mark.parametrize(
        ("models", "why"),
        [
            ({"write": OPUS, "rate": OPUS, "check": SONNET}, "models is not"),
            ({"write": "", "rate": OPUS, "check": SONNET, "verify": SONNET}, "not a non-empty"),
            ({"write": OPUS, "rate": None, "check": SONNET, "verify": SONNET}, "rate is null"),
            ({"write": None, "rate": OPUS, "check": SONNET, "verify": SONNET}, "write is null"),
        ],
    )
    def test_the_models_of_the_four_stages_are_named(
        self, models: dict[str, Any], why: str
    ) -> None:
        data = {**v3(), "models": models}
        with pytest.raises(ValueError, match=why):
            CP.validate(data)

    @pytest.mark.parametrize(
        ("hook", "why"),
        [
            ({"type": "mystery", "rating": 4, "variant": 2}, "hook.type"),
            ({"type": "object", "rating": 0, "variant": 2}, "hook.rating"),
            ({"type": "object", "rating": 6, "variant": 2}, "hook.rating"),
            ({"type": "object", "rating": True, "variant": 2}, "hook.rating"),
            ({"type": "object", "rating": 4, "variant": 4}, "hook.variant"),
            ({"type": "object", "rating": 4}, "hook is not the hook shape"),
        ],
    )
    def test_the_hook_is_a_declared_type_a_rating_and_a_variant(
        self, hook: dict[str, Any], why: str
    ) -> None:
        data = {**v3(), "hook": hook}
        with pytest.raises(ValueError, match=why):
            CP.validate(data)

    @pytest.mark.parametrize(
        ("anchors", "why"),
        [
            (["a", "b", "c", "d"], "anchors is not"),
            ([" "], "anchors is not"),
            ("a", "anchors is not"),
        ],
    )
    def test_the_anchors_are_at_most_three_phrases(self, anchors: Any, why: str) -> None:
        with pytest.raises(ValueError, match=why):
            CP.validate({**v3(), "anchors": anchors})

    @pytest.mark.parametrize(
        "reserve", [[], ["S0"], ["s2"], ["S2", "S2"], ["Reveal"], "S2", ["S2", 3]]
    )
    def test_the_reserve_is_null_or_sentence_ids_and_reveal(self, reserve: Any) -> None:
        with pytest.raises(ValueError, match="reserve is neither null"):
            CP.validate({**v3(), "reserve": reserve})

    def test_reveal_and_null_are_valid_reserves(self) -> None:
        assert v3(reserve=["reveal"])["reserve"] == ["reveal"]
        assert v3(reserve=None, shorts_ready=False)["reserve"] is None

    def test_shorts_ready_needs_a_reserve_and_an_anchor(self) -> None:
        with pytest.raises(ValueError, match="shorts_ready needs a reserve"):
            v3(reserve=None)
        with pytest.raises(ValueError, match="shorts_ready needs a reserve"):
            v3(anchors=[])
        assert v3(anchors=[], shorts_ready=False)["shorts_ready"] is False
        with pytest.raises(ValueError, match="shorts_ready is not true or false"):
            CP.validate({**v3(), "shorts_ready": 1})


def rewritten(**over: Any) -> dict[str, Any]:
    """The card rewritten after a failed verification: checked at `check-v`, verified at `verify2`."""
    fields: dict[str, Any] = {
        "stage": "check-v",
        "verify": {
            "verdict": "VERIFIED",
            "stage": "verify2",
            "by": "web_verifier:teaser-verify2-001",
            "at": "2026-10-09T15:00:00+00:00",
            "claims": 2,
            "unproven": 0,
            "text_sha256": CP.text_sha256(CARD),
        },
        "models": {"write": OPUS, "rate": None, "check": SONNET, "verify": SONNET},
        "hook": {"type": "act", "rating": None, "variant": None},
    }
    return v3(**{**fields, **over})


class TestTheRewriteAfterAFailedVerification:
    def test_it_is_the_one_card_that_is_not_rated(self) -> None:
        built = rewritten()
        assert built["models"]["rate"] is None
        assert built["hook"] == {"rating": None, "type": "act", "variant": None}

    def test_every_other_card_is_rated(self) -> None:
        with pytest.raises(ValueError, match="models.rate is null"):
            v3(models={"write": OPUS, "rate": None, "check": SONNET, "verify": SONNET})

    def test_the_unrated_card_names_no_rating_and_no_variant(self) -> None:
        with pytest.raises(ValueError, match="hook.rating of a rewrite"):
            rewritten(hook={"type": "act", "rating": 3, "variant": None})
        with pytest.raises(ValueError, match="hook.variant of a rewrite"):
            rewritten(hook={"type": "act", "rating": None, "variant": 1})
        with pytest.raises(ValueError, match="rate is null exactly"):
            rewritten(models={"write": OPUS, "rate": OPUS, "check": SONNET, "verify": SONNET})


class TestTheShortsPin:
    def test_a_shorts_ready_card_is_pinned_while_its_description_is_unchanged(self) -> None:
        built = v3()
        assert CP.shorts_pin(built, DESCRIPTION) == CP.text_sha256(CARD)
        assert CP.shorts_pin(built, DESCRIPTION + " Edited.") is None
        assert CP.shorts_pin(built, None) is None

    def test_a_card_that_is_not_shorts_ready_is_not_pinned(self) -> None:
        assert CP.shorts_pin(v3(anchors=[], shorts_ready=False), DESCRIPTION) is None

    def test_a_pin_is_the_cards_own_hash(self) -> None:
        pin = CP.shorts_pin(v3(), DESCRIPTION)
        assert pin == CP.text_sha256(CARD) and CP.describes(v3(), CARD)
