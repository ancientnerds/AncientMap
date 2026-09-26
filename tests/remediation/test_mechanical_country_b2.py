"""Does the B2-L country lane write exactly the two decided cells - and refuse everything else?

HUMAN_ONLY_DECISIONS_2026-09-26, B2-L (O9): Achladia `Germany -> Greece`, Delphinion
`Greece -> Türkiye`. `country_b2.classify_b2` decides each row from its live state, the census T05
vocabulary, Natural Earth (injected here as a schematic `geography`, so no geo stack is needed) and
the row's own Wikidata item. Each refusal has a test that fails when its check is removed. The
delivered-plan tests read `output/remediation/mechanical_country_b2/` only.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from mechanical import apply as A  # noqa: E402
from mechanical import country_b2 as B  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402

ACHLADIA = "74145e9b-76a6-48de-a902-08ecb2f1f7bb"
DELPHINION = "6aa4c8de-3794-42fe-b68e-6b6ab77bd8ed"
#: The stored points, read from production 2026-09-26 (read-only).
ACHLADIA_POINT = (35.16680700239597, 26.050032182871053)
DELPHINION_POINT = (37.53012087208033, 27.280715854142734)
DELIVERED = REPO / "output" / "remediation" / "mechanical_country_b2" / "PLAN.jsonl"
needs_plan = pytest.mark.skipif(not DELIVERED.exists(), reason=f"{DELIVERED} not built yet")

#: A schematic atlas: lon/lat boxes, enough to put Crete in Greece and Miletus in Türkiye.
BOXES = {
    "Greece": (34.5, 42.0, 19.0, 26.9),
    "Türkiye": (35.8, 42.2, 26.95, 45.0),
    "Germany": (47.2, 55.1, 5.8, 15.1),
}


def box_geography(country: str, lat: float, lon: float) -> tuple[bool, str, dict[str, Any] | None]:
    south, north, west, east = BOXES[country]
    if south <= lat <= north and west <= lon <= east:
        return True, "", {"source": f"schematic:{country}", "quote": f"({lat}, {lon}) in {country}"}
    return False, f"({lat}, {lon}) is outside the {country} box", None


CODES = {"Greece": "GR", "Türkiye": "TR", "Germany": "DE"}


def normalize(value: str) -> str:
    """`normalize_country`'s shape: the ISO code, or the lowercased value it does not know."""
    return CODES.get(value, value.lower())


@pytest.fixture(scope="module")
def vocabulary() -> tuple[dict[str, str], Any]:
    return P._vocabulary()


def candidate(**change: Any) -> B.Candidate:
    base = B.Candidate(
        site=P.Site(ACHLADIA, "Achladia", "Germany", *ACHLADIA_POINT, "ancient_nerds"),
        decided_old="Germany",
        decided_new="Greece",
        scope_status=None,
        premise=f"{ACHLADIA_POINT[0]},{ACHLADIA_POINT[1]}",
        qid="Q28791168",
    )
    return replace(base, **change)


WITNESSES = {
    "Q28791168": {
        "p17": [{"id": "Q41", "rank": "normal", "start": None, "end": None}],
        "p625": [35.1692, 26.0719],
        "fetched_at": "2026-09-26T00:30:06+00:00",
    },
    "Q2677787": {"p17": [], "p625": None, "fetched_at": "2026-09-26T00:30:06+00:00"},
}
COUNTRIES = {"Q41": {"label": "Greece", "p297": "GR"}, "Q43": {"label": "Turkey", "p297": "TR"}}


def decide(c: B.Candidate, **override: Any) -> P.Verdict:
    kwargs: dict[str, Any] = {
        "codes": CODES,
        "normalize": normalize,
        "witnesses": WITNESSES,
        "countries": COUNTRIES,
        "geography": box_geography,
    }
    kwargs.update(override)
    return B.classify_b2(c, **kwargs)


class TestTheDecision:
    def test_achladia_is_written_with_its_point_as_premise_and_both_witnesses(self) -> None:
        v = decide(candidate())
        assert v.ok, v.note
        assert (v.old_value, v.new_value, v.rule) == ("Germany", "Greece", B.RULE)
        assert v.premise == f"{ACHLADIA_POINT[0]},{ACHLADIA_POINT[1]}"
        sources = [e["source"] for e in v.evidence]
        assert sources[0] == B.DECISION_SOURCE
        assert any(s.endswith(":P625") for s in sources)
        assert any(":P17 -> " in s for s in sources)
        assert "P17 agrees" in v.note and "2005 m away" in v.note

    def test_delphinion_on_a_class_item_rests_on_its_point_as_decided(self) -> None:
        c = candidate(
            site=P.Site(DELPHINION, "Delphinion", "Greece", *DELPHINION_POINT, "ancient_nerds"),
            decided_old="Greece",
            decided_new="Türkiye",
            premise=f"{DELPHINION_POINT[0]},{DELPHINION_POINT[1]}",
            qid="Q2677787",
        )
        v = decide(c)
        assert v.ok, v.note
        assert "Q2677787 states no P17" in v.note
        assert "no (non-deprecated) P625" in v.note
        assert [e["source"] for e in v.evidence] == [B.DECISION_SOURCE, "schematic:Türkiye"]

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"site": P.Site(ACHLADIA, "Achladia", "Germany", 35.1, 26.0, "lyra")},
             "row-not-in-curated-source"),
            ({"scope_status": "retired"}, "retired"),
            ({"site": P.Site(ACHLADIA, "Achladia", "Greece", *ACHLADIA_POINT, "ancient_nerds")},
             "stored-value-moved"),
            ({"premise": None}, "no-point"),
            ({"decided_new": "Hellas"}, "not-canonical"),
            ({"site": P.Site(ACHLADIA, "Achladia", "Germany", 52.5, 13.4, "ancient_nerds")},
             "outside-new-country"),
            ({"qid": "Q999"}, "witness-missing"),
        ],
    )  # fmt: skip
    def test_each_check_refuses_on_its_own(self, change: dict[str, Any], reason: str) -> None:
        v = decide(candidate(**change))
        assert not v.ok and v.reason == reason, v
        assert v.premise is None and v.rule == ""

    def test_a_journal_that_does_not_end_at_the_live_value_refuses(self) -> None:
        link = P.JournalLink(1, "2026-09-21_x", "T05", "Germany", "Deutschland")
        v = decide(candidate(journal=(link,)))
        assert not v.ok and v.reason == "journal-disagrees"

    def test_a_contradicting_p17_refuses(self) -> None:
        witnesses = {
            **WITNESSES,
            "Q28791168": {
                **WITNESSES["Q28791168"],
                "p17": [{"id": "Q43", "rank": "preferred", "start": None, "end": None}],
            },
        }
        v = decide(candidate(), witnesses=witnesses)
        assert not v.ok and v.reason == "wikidata-p17"

    def test_a_p625_in_another_country_refuses(self) -> None:
        witnesses = {**WITNESSES, "Q28791168": {**WITNESSES["Q28791168"], "p625": [52.5, 13.4]}}
        v = decide(candidate(), witnesses=witnesses)
        assert not v.ok and v.reason == "wikidata-p625-elsewhere"

    def test_the_real_vocabulary_knows_both_decided_values(self, vocabulary: Any) -> None:
        """The dataset spells Türkiye (218 curated rows, 0 Turkey, read 2026-09-26)."""
        codes, norm = vocabulary
        v = decide(candidate(), codes=codes, normalize=norm)
        assert v.ok, v.note
        c = candidate(
            site=P.Site(DELPHINION, "Delphinion", "Greece", *DELPHINION_POINT, "ancient_nerds"),
            decided_old="Greece",
            decided_new="Türkiye",
            qid="Q2677787",
        )
        assert decide(c, codes=codes, normalize=norm).ok


class TestThePlan:
    def test_changes_and_refusals_are_counted(self) -> None:
        plan = B.build_b2_plan(
            [candidate(), candidate(scope_status="retired")],
            codes=CODES,
            normalize=normalize,
            witnesses=WITNESSES,
            countries=COUNTRIES,
            geography=box_geography,
            built_at="2026-09-26T00:00:00+00:00",
        )
        assert plan.lane is L.COUNTRY_B2
        assert plan.counters == {"candidates": 2, "changes": 1, "skipped": 1, "skip:retired": 1}

    def test_the_read_asks_for_exactly_the_decided_rows(self) -> None:
        sql = B.candidate_sql()
        assert f"'{ACHLADIA}'" in sql and f"'{DELPHINION}'" in sql
        assert sql.count("-") == sum(site.count("-") for site in (ACHLADIA, DELPHINION))
        assert L.COUNTRY_B2.premise_sql in sql

    def test_the_lane_owns_exactly_the_decided_values(self) -> None:
        assert L.COUNTRY_B2.allowed_new_values == ("Greece", "Türkiye")
        assert {d[0] for d in L.COUNTRY_B2_DECISIONS} == {ACHLADIA, DELPHINION}
        assert L.LANES["country-b2"] is L.COUNTRY_B2
        readback = L.LANE_READBACKS["country-b2"]
        assert f"'{L.COUNTRY_B2.run_stamp}'" in readback and "'Türkiye'" in readback

    def test_the_witnesses_are_asked_without_a_contact_address(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: list[str] = []

        def fake(endpoint: str, params: Any, *, timeout: int = 60, user_agent: str = "") -> Any:
            sent.append(user_agent)
            ids = str(params["ids"]).split("|")
            return {"entities": {q: {"claims": {}} for q in ids}}

        monkeypatch.setattr(P, "get_json", fake)
        out = B.collect_witnesses(["Q2677787"], fetched_at="2026-09-26T00:00:00+00:00")
        assert sent == [B.USER_AGENT] and out["user_agent"] == B.USER_AGENT
        assert "@" not in B.USER_AGENT and out["entities"]["Q2677787"]["p17"] == []


@needs_plan
class TestTheDeliveredPlan:
    def test_two_rows_of_the_decided_shape(self) -> None:
        records = A.load_records(DELIVERED)
        A.validate_records(records, lane=L.COUNTRY_B2)
        got = {(r.site_id, r.old_value, r.new_value) for r in records}
        assert got == {(s, old, new) for s, _name, old, new in L.COUNTRY_B2_DECISIONS}
        premises = {r.site_id: r.premise for r in records}
        assert premises[ACHLADIA] == f"{ACHLADIA_POINT[0]},{ACHLADIA_POINT[1]}"
        assert premises[DELPHINION] == f"{DELPHINION_POINT[0]},{DELPHINION_POINT[1]}"

    def test_the_emitted_statements_are_the_plan_s(self) -> None:
        records = A.load_records(DELIVERED)
        digest = P.plan_sha256(DELIVERED)
        for name, sql in (
            ("APPLY.sql", A.apply_statement(records, L.COUNTRY_B2)),
            ("ROLLBACK.sql", A.rollback_statement(records, L.COUNTRY_B2)),
        ):
            P.verify_pinned(DELIVERED.parent / name, plan_path=DELIVERED, expected=sql)
            text = (DELIVERED.parent / name).read_text(encoding="utf-8")
            assert text.startswith(f"-- plan sha256 {digest}\n")
            assert "scope guard 4" in text and "scope guard 5" in text

    def test_nothing_was_refused(self) -> None:
        assert (DELIVERED.parent / "SKIPPED.jsonl").read_text(encoding="utf-8") == ""
        for line in DELIVERED.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            assert payload["run_stamp"] == L.COUNTRY_B2.run_stamp
            assert payload["evidence"][0]["source"] == B.DECISION_SOURCE
