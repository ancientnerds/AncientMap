"""Lane WB's write side for contract shorts-v1 and the Claude re-check.

A card of the new contract is nameless and carries a version-3 provenance; a site whose chain failed
keeps its card (owner decision D5); a re-checked card is confirmed or cleared (D10). The planner
(`mechanical/teaser.py`) lists what writes nothing, runs the name rule again against the live name,
and holds a version-3 provenance's `ai_system` to the string derived from its models.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from mechanical import teaser as W  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from teaser import run as R  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation.test_mechanical_teaser import export_for, live, outcome  # noqa: E402

#: A nameless card for Skara Brae, and the version-3 provenance of it.
NAMELESS = (
    "A storm laid bare stone houses in the dunes. Each had a hearth, beds on either side of it and "
    "a dresser facing the door, in a village lived in from roughly 3180 BC."
)
OPUS = OH.OPUS_MODEL
SONNET = OH.SONNET_MODEL
CLAUDE = {"write": OPUS, "rate": OPUS, "check": SONNET, "verify": SONNET}


def v3(models: dict[str, str | None] | None = None, ai_system: str | None = None) -> dict[str, Any]:
    chosen = CLAUDE if models is None else models
    return CP.build_v3(
        run="wb-shorts-test",
        ai_system=ai_system or M.ai_system_for(m for m in chosen.values() if m is not None),
        card=NAMELESS,
        description=T.DESCRIPTIONS[T.SKARA],
        stage="check",
        checker="fact_checker:teaser-check-001",
        checked_at="2026-10-09T12:00:00+00:00",
        claims=[{"claim": "a storm exposed houses", "support": ["S2"]}],
        verify={
            **T.VERIFIED,
            "by": "web_verifier:teaser-verify-001",
            "text_sha256": T.sha(NAMELESS),
        },
        web_facts=[],
        models=chosen,
        hook={"type": "act", "rating": 4, "variant": 1},
        anchors=["stone houses"],
        reserve=["S5"],
        shorts_ready=True,
    )


def shorts_outcome(**over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {"card": NAMELESS, "provenance": v3()}
    return outcome(**{**fields, **over})


class TestTheSpellings:
    def test_the_planner_reads_the_outcome_statuses_in_the_run_cli_s_spelling(self) -> None:
        assert (W.KEPT, W.CONFIRMED) == (R.KEPT, R.CONFIRMED)

    def test_the_reasons_are_documented(self) -> None:
        for reason in (W.KEPT, W.CONFIRMED, W.NAME_CHANGED):
            assert W.REFUSAL_MEANING[reason]


class TestAnOutcomeThatWritesNothing:
    def test_a_site_that_keeps_its_card_is_listed_not_cleared(self) -> None:
        kept = outcome(
            status=W.KEPT, reason="failed-after-two-rewrites", card=None, provenance=None
        )
        decided = W.classify(kept, live(), {}, "wb-test")
        assert decided.reason == W.KEPT and not decided.ok
        assert "keeps its card" in decided.note

    def test_a_thin_decline_keeps_the_card_too(self) -> None:
        kept = outcome(status=W.KEPT, reason="thin-declined", card=None, provenance=None)
        assert W.classify(kept, live(), {}, "wb-test").reason == W.KEPT

    def test_a_confirmed_card_stands(self) -> None:
        confirmed = outcome(status=W.CONFIRMED, reason=None, card="the live card", provenance=None)
        assert W.classify(confirmed, live(), {}, "wb-test").reason == W.CONFIRMED

    def test_a_kept_site_writes_no_clear_row_even_when_its_description_moved(self) -> None:
        kept = outcome(status=W.KEPT, reason="thin-declined", card=None, provenance=None)
        moved = live(description="Another description.")
        assert W.classify(kept, moved, {}, "wb-test").reason == W.KEPT

    def test_a_step_lists_them_beside_the_cards_it_writes(self, tmp_path: Path) -> None:
        kept = outcome(
            T.NEWGRANGE, status=W.KEPT, reason="thin-declined", card=None, provenance=None
        )
        written = shorts_outcome()
        lives = [live(T.SKARA, country="Scotland"), live(T.NEWGRANGE, country="Ireland")]
        root = tmp_path / "mechanical_teaser"
        record = W.plan_step(
            "wb-shorts-test",
            1,
            read=lambda _sql: export_for(lives),
            root=root,
            outcomes=[written, kept],
        )
        assert record["skipped"] == {"kept": 1}
        assert record["card"]["cells"] == 1 and record["prov"]["cells"] == 1


SEEDED_RUN = "wb-cardgap-test"


def recheck_clear(**over: Any) -> dict[str, Any]:
    """A re-check clear: it names the card it judged (`T.OLD_CARD`) and the run that wrote it."""
    fields: dict[str, Any] = {
        "reason": "recheck-contradicted",
        "card": None,
        "provenance": None,
        "seeded_card_sha256": T.sha(T.OLD_CARD),
        "seeded_run": SEEDED_RUN,
    }
    return outcome(status=W.CLEARED, **{**fields, **over})


def seeded_live(**over: Any) -> W.Live:
    """The live site as the re-check run seeded it: `T.OLD_CARD` with a provenance of the gap run."""
    held = live()
    raw = json.loads(held.raw_data or "{}")
    raw["_card_provenance"] = {"run": SEEDED_RUN}
    return replace(held, raw_data=W.reprint(raw), **over)


class TestAFailedReCheckIsAClear:
    def test_a_cleared_recheck_card_is_a_journalled_clear_with_its_reason(self) -> None:
        prov, card = W.classify(recheck_clear(), seeded_live(), {}, "wb-recheck")
        assert (card.old_value, card.new_value) == (T.OLD_CARD, None)
        assert card.rule == "card-clear-recheck-contradicted"
        assert card.note == "card cleared (recheck-contradicted)"
        assert json.loads(prov.new_value)["_description_provenance"]["card"] is None
        assert "_card_provenance" not in json.loads(prov.new_value)

    def test_a_card_written_after_the_seed_is_not_cleared_on_the_old_verdict(self) -> None:
        newer = seeded_live(card=NAMELESS)
        refused = W.classify(recheck_clear(), newer, {}, "wb-recheck")
        assert refused.reason == W.CARD_CHANGED and not refused.ok

    def test_a_card_of_another_run_with_the_same_text_is_not_cleared_either(self) -> None:
        held = seeded_live()
        raw = json.loads(held.raw_data or "{}")
        raw["_card_provenance"] = {"run": "wb-shorts-test"}
        newer = replace(held, raw_data=W.reprint(raw))
        refused = W.classify(recheck_clear(), newer, {}, "wb-recheck")
        assert refused.reason == W.CARD_CHANGED and "wb-cardgap-test" in refused.note

    def test_a_listed_site_without_a_description_pins_the_card_text_only(self) -> None:
        listed = recheck_clear(reason="no-description", seeded_run=None)
        assert W.classify(listed, live(), {}, "wb-recheck")[1].new_value is None
        assert W.classify(listed, live(card=NAMELESS), {}, "wb-recheck").reason == W.CARD_CHANGED

    def test_the_spelling_is_the_run_cli_s(self) -> None:
        assert W.CARD_CHANGED == R.CARD_CHANGED
        assert W.REFUSAL_MEANING[W.CARD_CHANGED]


class TestAVersion3Card:
    def test_it_is_written_with_its_provenance(self) -> None:
        prov, card = W.classify(shorts_outcome(), live(country="Scotland"), {}, "wb-shorts-test")
        written = json.loads(prov.new_value)["_card_provenance"]
        assert written["v"] == 3 and written["contract"] == "shorts-v1"
        assert written["models"] == CLAUDE and written["ai_system"] == M.AI_SYSTEM_CLAUDE
        assert (card.old_value, card.new_value) == (T.OLD_CARD, NAMELESS)
        assert "teaser card, 150 characters" in card.note or "teaser card," in card.note

    @pytest.mark.parametrize(
        "models",
        [
            CLAUDE,
            {**CLAUDE, "check": OH.HAIKU_MODEL},
            {**CLAUDE, "verify": OH.MINIMAX_MODEL},
            dict.fromkeys(CLAUDE, SONNET),
        ],
    )
    def test_its_ai_system_is_derived_from_its_models(self, models: dict[str, str | None]) -> None:
        provenance = v3(models)
        outcome_row = shorts_outcome(provenance=provenance)
        prov, _card = W.classify(outcome_row, live(country="Scotland"), {}, "wb-shorts-test")
        written = json.loads(prov.new_value)["_card_provenance"]
        derived = M.ai_system_for(m for m in models.values() if m is not None)
        assert written["ai_system"] == derived and derived in M.AI_SYSTEMS

    def test_an_ai_system_that_is_not_the_derived_one_is_refused(self) -> None:
        lying = v3(ai_system=M.AI_SYSTEM_OPUS)
        with pytest.raises(ValueError, match="is not the one derived from its models"):
            W.classify(shorts_outcome(provenance=lying), live(country="Scotland"), {}, "wb")
        lying_claude = v3({**CLAUDE, "verify": OH.MINIMAX_MODEL}, ai_system=M.AI_SYSTEM_CLAUDE)
        with pytest.raises(ValueError, match="is not the one derived from its models"):
            W.classify(shorts_outcome(provenance=lying_claude), live(country="Scotland"), {}, "wb")

    def test_a_string_outside_the_known_disclosures_is_still_refused(self) -> None:
        third = v3(ai_system="Claude Opus (Anthropic): test")
        with pytest.raises(ValueError, match="is not one of"):
            W.classify(shorts_outcome(provenance=third), live(country="Scotland"), {}, "wb")


class TestTheNameRuleAgainstTheLiveName:
    def decide(self, **over: Any) -> Any:
        return W.classify(shorts_outcome(), live(country="Scotland", **over), {}, "wb-shorts-test")

    def test_a_clean_card_is_written(self) -> None:
        assert isinstance(self.decide(), tuple)

    def test_a_renamed_site_whose_new_name_is_in_the_card_is_refused(self) -> None:
        decided = self.decide(name="Hearth and Dresser Village")
        assert (
            decided.reason == W.NAME_CHANGED and "word of the site's name: hearth" in decided.note
        )

    def test_an_alias_added_since_is_refused(self) -> None:
        decided = self.decide(alt_names=("Stone houses in the dunes",))
        assert (
            decided.reason == W.NAME_CHANGED and "alias 'Stone houses in the dunes'" in decided.note
        )

    def test_a_country_that_moved_into_the_card_is_refused(self) -> None:
        decided = W.classify(shorts_outcome(), live(country="Dunes"), {}, "wb-shorts-test")
        assert decided.reason == W.NAME_CHANGED and "country" in decided.note

    def test_the_rule_is_run_only_for_version_3(self) -> None:
        """A version-2 card names its site by contract: it is written, whatever the live name."""
        decided = W.classify(outcome(), live(), {}, "wb-test")
        assert isinstance(decided, tuple)

    def test_a_version_3_outcome_needs_the_country_in_the_export(self) -> None:
        with pytest.raises(W.PlanError, match="carries no country"):
            W.classify(shorts_outcome(), live(), {}, "wb-shorts-test")

    def test_a_null_country_in_the_export_is_no_country(self) -> None:
        """SQL NULL read as the text "None" would pass the rule's guard and be compared as a word."""
        export = export_for([replace(live(), country="")]).replace(
            '"country": ""', '"country": null'
        )
        parsed, _journal = W.parse_export(export)
        (site,) = parsed.values()
        assert site.country == ""
        with pytest.raises(W.PlanError, match="carries no country"):
            W.classify(shorts_outcome(), site, {}, "wb-shorts-test")

    def test_the_name_rule_is_run_after_the_description_check(self) -> None:
        decided = W.classify(
            shorts_outcome(), live(country="Scotland", description="Changed."), {}, "wb"
        )
        assert decided.reason == W.STALE_DESCRIPTION


class TestTheRead:
    def test_the_step_reads_the_country_and_every_alias(self) -> None:
        sql = W.site_sql([T.SKARA])
        assert "u.country" in sql and "FROM unified_site_names n WHERE n.site_id = u.id" in sql
        assert "AS alt_names" in sql

    def test_the_export_is_parsed_into_the_live_site(self, tmp_path: Path) -> None:
        text = export_for([live(T.SKARA, country="Scotland", alt_names=("Skerabra",))])
        parsed, _journal = W.parse_export(text)
        site = parsed[T.SKARA]
        assert site.country == "Scotland" and site.alt_names == ("Skerabra",)


class TestTheAcceptanceOfAVersion3Card:
    def test_a_written_version_3_card_is_accepted_like_any_teaser(self) -> None:
        raw = {
            "_description_provenance": {"lane": "W", "desc_sha256": "0" * 64, "card": None},
            CP.CARD_PROVENANCE_KEY: v3(),
        }
        site = live(T.SKARA, country="Scotland", card=NAMELESS, raw_data=json.dumps(raw))
        step = {"step": 1, "sites": [T.SKARA]}
        found = W.deviations(step, [], [], {T.SKARA: site}, [], {T.SKARA: shorts_outcome()})
        assert found == []
        stale = live(T.SKARA, card=NAMELESS, raw_data=json.dumps(raw), description="Edited.")
        again = W.deviations(step, [], [], {T.SKARA: stale}, [], {T.SKARA: shorts_outcome()})
        assert f"{T.SKARA}: the teaser provenance is stale" in again
