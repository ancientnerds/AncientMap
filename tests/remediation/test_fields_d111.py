"""Owner decision D111 (2026-11-06): the D99 pilot dated 7 of 50 sites and 2 of those wrongly.

The researcher's period_start rule and the adversarial check's criteria gain the four D111 rules
(coarse words, the precise epoch, no weak single source, the site's own beginning) for a round or a
cell exported from now on (`period_rule` D111); a D101 round keeps the text it was asked, because
the import renders every prompt again and compares its hash. The second pilot draws 50 new sites.
Offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from fields import adversarial as AD  # noqa: E402
from fields import d99 as D99  # noqa: E402
from fields import handoff as HO  # noqa: E402

from pipeline import periods as P  # noqa: E402
from tests.remediation.test_fields_d99 import TestTheDraw  # noqa: E402

RULE = HO.FIELD_RULES_WD5["period_start"]


class TestTheResearcherRule:
    def test_a_d111_round_is_asked_the_d101_sentence_and_the_d111_rules(self) -> None:
        d101 = HO.period_rule_text(RULE, HO.D101)
        d111 = HO.period_rule_text(RULE, HO.D111)
        assert "Owner decision D111" not in d101
        assert d111 == d101.replace(HO._D101_SENTENCE, HO._D101_SENTENCE + HO._D111_SENTENCE)
        for rule in ('"stone age"', "without lower, middle or upper", "most precise epoch",
                     "cites no publication", "travel, tourism", "THE SITE ITSELF",
                     "Roman road numbering"):  # fmt: skip
            assert rule in d111

    def test_the_coarse_words_it_names_are_the_tables(self) -> None:
        for word in P.COARSE:
            assert f'"{word}"' in HO._D111_SENTENCE
        # the bare Bronze Age is refused where the table needs a sub-phase, as the text says
        assert "bronze age" in P.SUBPHASE_REQUIRED
        for country in ("england", "ireland", "turkiye", "greece", "france", "italy"):
            assert country in P.SUBPHASE_REQUIRED["bronze age"]

    def test_the_new_epochs_are_in_the_list_a_new_round_is_shown(self) -> None:
        d111 = HO.period_rule_text(RULE, HO.D111)
        assert "chimu" in d111 and "late roman" in d111 and "vinca" in d111

    def test_an_unknown_rule_is_still_refused(self) -> None:
        with pytest.raises(HO.HandoffStepError, match="is not 'D101' or 'D111'"):
            HO.period_rule_text(RULE, "D999")

    def test_a_field_without_the_sentence_is_asked_as_before(self) -> None:
        site_type = HO.FIELD_RULES_WD5["site_type"]
        assert HO.period_rule_text(site_type, HO.D111) == site_type


class TestTheAdversarialCriteria:
    def test_a_d111_cell_is_asked_the_d101_clause_and_the_d111_rejections(self) -> None:
        d101 = AD.criteria("period_start", HO.D101)
        d111 = AD.criteria("period_start", HO.D111)
        assert "D111" not in d101
        assert d111 == d101.replace(AD._D101_CLAUSE, AD._D101_CLAUSE + AD._D111_CLAUSE)
        for rule in ("coarse period word", "narrower phase", "cites no publication",
                     "territory, area or town", "only classifies the site"):  # fmt: skip
            assert rule in d111
        # the clause ends the sentence the criteria go on from
        assert "may be older. A hedged date" in d111

    def test_other_fields_and_unknown_rules(self) -> None:
        assert AD.criteria("coordinates", HO.D111) == AD.CRITERIA["coordinates"]
        with pytest.raises(AD.AdversarialError, match="is not 'D101' or 'D111'"):
            AD.criteria("period_start", "D999")


class TestTheSecondDraw:
    def test_an_earlier_pilots_sites_are_never_drawn(self) -> None:
        undated, countries, conflicts = TestTheDraw().sites()
        first = D99.draw(undated, countries, conflicts, 7)
        # 12 per stratum: two left after the first pilot, so the second needs a fresh pool
        more = {**countries, **{f"pe{i:02d}": "Peru" for i in range(12, 24)}}
        more.update({f"en{i:02d}": "England" for i in range(12, 24)})
        more.update({f"gr{i:02d}": "Greece" for i in range(12, 24)})
        more.update({f"ot{i:02d}": "Spain" for i in range(12, 24)})
        more.update({f"cf{i:02d}": "Peru" for i in range(12, 24)})
        wider = frozenset({*conflicts, *(f"cf{i:02d}" for i in range(12, 24))})
        done = frozenset(r["site_id"] for r in first)
        second = D99.draw(sorted(more), more, wider, 7, exclude=done, pilot="D111 pilot 2")
        assert len(second) == 50 and not done & {r["site_id"] for r in second}
        assert all(r["reason"].startswith("D111 pilot 2 (seed 7), stratum ") for r in second)

    def test_the_exclusion_counts_against_a_small_stratum(self) -> None:
        undated, countries, conflicts = TestTheDraw().sites()
        first = frozenset(r["site_id"] for r in D99.draw(undated, countries, conflicts, 7))
        with pytest.raises(D99.D99Error, match="holds 2 site"):
            D99.draw(undated, countries, conflicts, 8, exclude=first)
