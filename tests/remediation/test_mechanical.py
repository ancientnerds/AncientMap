"""Do the mechanical country repairs fire, refuse, and render a statement worth running?

The write is 35 conditional UPDATEs against production, so the interesting mistakes are not
exceptions but a plan that is *wrong and happy*: a value derived from the proposal instead of from
the sources, a compound reduced to the wrong part, a territory promoted to a country, a refusal
turned into a write, a statement that is not one transaction, an APPLY.sql without its rollback.
Each guard below has a test that fails when the guard is removed, which is what "mutation-proven"
means here: the test asserts the *refusal*, so deleting the check turns it red.

`build_plan` and `classify` are pure functions of their arguments (no snapshot, no cache read, no
database, no clock), so these tests drive them with hand-built rows and the real vocabularies -
`COUNTRY_CODES`, `NAME_TO_ISO` and Natural Earth are read from the repository, never re-typed, so a
change in either vocabulary fails here rather than in production. Only the atlas needs the census
cache; that class is skipped with its reason when the dataset is absent.
"""

from __future__ import annotations

import json
import re
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
from mechanical import plan as P  # noqa: E402

SITE_GEORGIA = "0060e6c0-8388-4762-bf51-9a3f88807899"  # Nekresi, Georgia
SITE_CHILE = "2dab79e8-1ece-4f9b-beb3-a91573d545c3"  # Ahu Akivi, Easter Island
#: Real coordinates from the production rows, so the geography fixtures are measurements.
GEORGIA_POINT = (41.97197497123162, 45.76774281018119)
CHILE_POINT = (-27.114327221940712, -109.39286467595336)

NE_SHAPEFILE = (
    REPO / "output" / "remediation" / "cache" / "naturalearth" / "ne_10m_admin_0_countries.shp"
)
DELIVERED_PLAN = REPO / "output" / "remediation" / "mechanical" / "PLAN.jsonl"

needs_dataset = pytest.mark.skipif(
    not NE_SHAPEFILE.exists(),
    reason=f"Natural Earth cache not present ({NE_SHAPEFILE}); run plan.py --collect",
)
needs_deliverable = pytest.mark.skipif(
    not DELIVERED_PLAN.exists(), reason=f"{DELIVERED_PLAN} not built yet"
)


@pytest.fixture(scope="module")
def vocabulary() -> tuple[dict[str, str], Any]:
    """The real `COUNTRY_CODES` and `normalize_country`, as `plan.py` reads them."""
    return P._vocabulary()


@needs_dataset
@pytest.fixture(scope="module")
def atlas() -> Any:
    return P._atlas()[0]


@pytest.fixture
def witness_countries() -> dict[str, dict[str, Any]]:
    return {
        "Q230": {"label": "Georgia", "p297": "GE"},
        "Q298": {"label": "Chile", "p297": "CL"},
        "Q30": {"label": "United States", "p297": "US"},
        "Q15180": {"label": "Soviet Union", "p297": "SU"},
        "Q19083": {"label": "Kingdom of Iberia", "p297": None},
    }


def claim(qid: str, rank: str = "normal", start: str | None = None, end: str | None = None) -> dict:
    return {"id": qid, "rank": rank, "start": start, "end": end}


def witness(p17: list[dict], countries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"p17": p17, "countries": countries, "fetched_at": "2026-09-21T00:00:00+00:00"}


def finding(
    stored: str = "Georgia (country)",
    proposed: str = "Georgia",
    *,
    site_id: str = SITE_GEORGIA,
    applicable: bool = True,
    test_id: str = "T05/disambiguated",
) -> P.Finding:
    return P.Finding(
        site_id=site_id,
        test_id=test_id,
        applicable=applicable,
        current_value=stored,
        proposed_value=proposed,
        confidence="authoritative",
        severity="severe",
        note="the parenthetical is a disambiguation hint",
    )


def site(
    stored: str = "Georgia (country)",
    *,
    site_id: str = SITE_GEORGIA,
    name: str = "Nekresi",
    point: tuple[float, float] = GEORGIA_POINT,
    source_id: str = P.CURATED_SOURCE,
) -> P.Site:
    return P.Site(
        site_id=site_id,
        name=name,
        country=stored,
        lat=point[0],
        lon=point[1],
        source_id=source_id,
    )


def decide(
    vocabulary: tuple[dict[str, str], Any],
    atlas: Any,
    *,
    find: P.Finding | None = None,
    row: P.Site | None = None,
    snapshot_country: str | None = None,
    anchor: P.Anchor | None = None,
    witness_payload: dict[str, Any] | None = None,
    phase3: bool = False,
) -> P.Verdict:
    codes, normalize = vocabulary
    find = find or finding()
    row = row or site()
    return P.classify(
        find,
        row,
        snapshot_country=snapshot_country if snapshot_country is not None else row.country,
        phase3=phase3,
        codes=codes,
        normalize=normalize,
        atlas=atlas,
        anchor=anchor,
        witness=witness_payload,
        retrieved_at="2026-09-20T18:41:24+00:00",
    )


# ------------------------------------------------------------------------------ the reduction
class TestReduceValue:
    def test_hint_is_a_note_not_a_name(self, vocabulary: tuple[dict[str, str], Any]) -> None:
        """The hint rule never touches the atlas, so a featureless stand-in is enough here."""
        codes, normalize = vocabulary
        assert P.reduce_value("Georgia (country)", codes, normalize, _StubAtlas()) == (
            "Georgia",
            "disambiguation-hint",
        )

    @needs_dataset
    def test_compound_reduces_to_the_state_not_the_territory(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        assert P.reduce_value("Chile, Easter Island", codes, normalize, atlas) == (
            "Chile",
            "compound-label-country-part",
        )

    @needs_dataset
    def test_both_vocabularies_know_the_territory_as_chile(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        """Why the third party is needed: the project's own maps answer `CL` for the territory.

        Without this, `Chile, Easter Island` would look like two known countries and the tie
        would be decided by nothing at all.
        """
        codes, normalize = vocabulary
        assert P._iso("Easter Island", normalize) == "CL"
        assert codes.get("Easter Island") == "CL"
        assert P.names_a_country(atlas, "Easter Island") is False
        assert P.names_a_country(atlas, "Chile") is True

    @needs_dataset
    def test_two_candidate_countries_refuse(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        assert P.reduce_value("Chile, Argentina", codes, normalize, atlas) is None

    @needs_dataset
    def test_an_empty_part_refuses(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        assert P.reduce_value("Chile, ", codes, normalize, atlas) is None

    @needs_dataset
    def test_a_bare_country_has_no_rule(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        assert P.reduce_value("Georgia", codes, normalize, atlas) is None

    @needs_dataset
    def test_the_hint_alone_is_not_a_name(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        assert P.reduce_value("State (country)", codes, normalize, atlas) is None

    @needs_dataset
    def test_a_not_a_country_value_has_no_rule(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        assert P.reduce_value("Baltic Sea", codes, normalize, atlas) is None


class _StubAtlas:
    """`names_a_country` reads only `.features`, and the hint rule reads nothing at all."""

    features: list[Any] = []


# ---------------------------------------------------------------------------- single witnesses
class TestWikidataWitness:
    def test_a_preferred_value_that_contradicts_refuses(
        self, witness_countries: dict[str, dict[str, Any]]
    ) -> None:
        ok, note, _ = P.check_wikidata(
            P.Anchor("Q495", "test"), witness([claim("Q30", "preferred")], witness_countries), "GE"
        )
        assert ok is False
        assert "United States" in note

    def test_history_beside_a_preferred_country_is_not_a_contradiction(
        self, witness_countries: dict[str, dict[str, Any]]
    ) -> None:
        """Kutaisi's shape: Georgia preferred since 1991, the Soviet Union normal until then."""
        ok, note, evidence = P.check_wikidata(
            P.Anchor("Q172415", "test"),
            witness(
                [
                    claim("Q230", "preferred", "1991-04-09"),
                    claim("Q15180", "normal", "1922-12-30", "1991-04-09"),
                ],
                witness_countries,
            ),
            "GE",
        )
        assert ok is True and note == ""
        assert evidence is not None and "history (normal rank)" in evidence["quote"]
        assert "Soviet Union" in evidence["quote"]

    def test_a_normal_value_alone_is_decisive(
        self, witness_countries: dict[str, dict[str, Any]]
    ) -> None:
        ok, _, evidence = P.check_wikidata(
            P.Anchor("Q1", "test"), witness([claim("Q230")], witness_countries), "GE"
        )
        assert ok is True and evidence is not None and "only" in evidence["quote"]

    def test_a_normal_value_alone_that_contradicts_refuses(
        self, witness_countries: dict[str, dict[str, Any]]
    ) -> None:
        ok, note, _ = P.check_wikidata(
            P.Anchor("Q1", "test"), witness([claim("Q30")], witness_countries), "GE"
        )
        assert ok is False and "US" in note

    def test_no_p17_is_a_gap_not_a_failure(
        self, witness_countries: dict[str, dict[str, Any]]
    ) -> None:
        ok, note, evidence = P.check_wikidata(
            P.Anchor("Q12866025", "test"), witness([], witness_countries), "GE"
        )
        assert ok is None and evidence is None and "states no P17" in note

    def test_a_preferred_value_without_p297_neither_matches_nor_contradicts(
        self, witness_countries: dict[str, dict[str, Any]]
    ) -> None:
        ok, note, _ = P.check_wikidata(
            P.Anchor("Q2026789", "test"),
            witness([claim("Q31354462", "normal"), claim("Q230", "preferred")], witness_countries),
            "GE",
        )
        assert ok is True and note == ""


# --------------------------------------------------------------------------------- the decision
@needs_dataset
class TestClassify:
    def test_the_happy_path_writes_the_canonical_value(
        self,
        vocabulary: tuple[dict[str, str], Any],
        atlas: Any,
        witness_countries: dict[str, dict[str, Any]],
    ) -> None:
        verdict = decide(
            vocabulary,
            atlas,
            anchor=P.Anchor("Q995736", "test"),
            witness_payload=witness([claim("Q230")], witness_countries),
        )
        assert verdict.ok and verdict.new_value == "Georgia"
        assert verdict.reason == ""
        sources = [e["source"] for e in verdict.evidence]
        assert any(s.startswith("pipeline/utils/country_lookup.py") for s in sources)
        assert any(s.startswith("ancient-nerds-map/") for s in sources)
        assert any(s.startswith("naturalearth:") for s in sources)
        assert any(s.startswith("wikidata:") for s in sources)

    def test_a_review_finding_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        verdict = decide(
            vocabulary, atlas, find=finding("USA", "", applicable=False, test_id="T05/spelling")
        )
        assert not verdict.ok and verdict.reason == "finding-not-applicable"

    def test_a_row_of_another_source_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        verdict = decide(vocabulary, atlas, row=site(source_id="lyra"))
        assert not verdict.ok and verdict.reason == "row-not-in-curated-source"

    def test_a_snapshot_value_the_database_no_longer_holds_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        verdict = decide(vocabulary, atlas, snapshot_country="Georgia")
        assert not verdict.ok and verdict.reason == "snapshot-live-mismatch"

    def test_a_stale_finding_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        stale = finding()
        object.__setattr__(stale, "current_value", "Georgia")
        verdict = decide(vocabulary, atlas, find=stale)
        assert not verdict.ok and verdict.reason == "finding-stale"

    def test_a_canonical_form_that_disagrees_with_the_proposal_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(P, "canonicalize_country_display_name", lambda name: "Sakartvelo")
        verdict = decide(vocabulary, atlas)
        assert not verdict.ok and verdict.reason == "canonicalisation-differs-from-proposal"

    def test_a_write_that_would_change_the_iso_code_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        """Only reachable with two vocabularies that disagree - which is the point of the check."""
        codes, normalize = vocabulary
        monkeypatch_free = lambda value: "US" if value == "Georgia" else normalize(value)  # noqa: E731
        verdict = P.classify(
            finding(),
            site(),
            snapshot_country="Georgia (country)",
            phase3=False,
            codes=codes,
            normalize=monkeypatch_free,
            atlas=atlas,
            anchor=None,
            witness=None,
            retrieved_at=None,
        )
        assert not verdict.ok and verdict.reason == "iso-unchanged-check-failed"

    def test_a_frontend_map_that_carries_another_code_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        without_georgia = {**codes, "Georgia": "US"}
        verdict = P.classify(
            finding(),
            site(),
            snapshot_country="Georgia (country)",
            phase3=False,
            codes=without_georgia,
            normalize=normalize,
            atlas=atlas,
            anchor=None,
            witness=None,
            retrieved_at=None,
        )
        assert not verdict.ok and verdict.reason == "not-a-country-code"

    def test_a_point_in_another_country_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        verdict = decide(vocabulary, atlas, row=site(point=CHILE_POINT))
        assert not verdict.ok and verdict.reason == "geography-contradicts"
        assert "outside" in verdict.note

    def test_a_territory_point_is_inside_its_state(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        """Easter Island is 3,500 km from mainland Chile and still in its polygon."""
        verdict = decide(
            vocabulary,
            atlas,
            find=finding(
                "Chile, Easter Island", "Chile", site_id=SITE_CHILE, test_id="T05/compound"
            ),
            row=site(
                "Chile, Easter Island", site_id=SITE_CHILE, name="Ahu Akivi", point=CHILE_POINT
            ),
        )
        assert verdict.ok and verdict.new_value == "Chile"
        assert verdict.rule == "compound-label-country-part"

    def test_an_external_contradiction_refuses(
        self,
        vocabulary: tuple[dict[str, str], Any],
        atlas: Any,
        witness_countries: dict[str, dict[str, Any]],
    ) -> None:
        verdict = decide(
            vocabulary,
            atlas,
            anchor=P.Anchor("Q995736", "test"),
            witness_payload=witness([claim("Q30", "preferred")], witness_countries),
        )
        assert not verdict.ok and verdict.reason == "wikidata-contradicts"

    def test_a_missing_external_witness_is_recorded_not_fatal(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        verdict = decide(vocabulary, atlas, anchor=None)
        assert verdict.ok and "no external witness" in verdict.note

    def test_a_value_the_census_would_flag_again_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(P, "_is_canonical", lambda *a, **k: False)
        verdict = decide(vocabulary, atlas)
        assert not verdict.ok and verdict.reason == "not-a-fixed-point"

    def test_a_bare_country_name_is_refused_before_anything_else(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        """`Georgia` is not a candidate: there is no hint to strip and no second part."""
        verdict = decide(
            vocabulary,
            atlas,
            find=finding("Georgia", "Georgia", test_id="T05/x"),
            row=site("Georgia"),
        )
        assert not verdict.ok and verdict.reason == "no-reduction-rule"

    def test_a_reduction_that_changes_nothing_is_refused(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rule that returns the value already stored is not a repair."""
        monkeypatch.setattr(P, "reduce_value", lambda *a, **k: ("Georgia (country)", "no-op"))
        monkeypatch.setattr(
            P, "canonicalize_country_display_name", lambda name: "Georgia (country)"
        )
        verdict = decide(vocabulary, atlas, find=finding("Georgia (country)", "Georgia (country)"))
        assert not verdict.ok and verdict.reason == "already-the-value"


class TestLegibility:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Georgia", None),
            (" Georgia", "leading or trailing whitespace"),
            ("e\u0301ire", "not NFC-normalised"),
            ("X" * 101, "101 characters, longer than the column"),
            ("Geor\rgia", "control characters"),
        ],
    )
    def test_only_writable_strings_pass(self, value: str, expected: str | None) -> None:
        assert P._legible(value) == expected


# ------------------------------------------------------------------------------- the assembly
@needs_dataset
class TestBuildPlan:
    def test_the_plan_is_a_partition_of_the_candidates(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        codes, normalize = vocabulary
        findings = [
            finding(),
            finding("Chile, Easter Island", "Chile", site_id=SITE_CHILE, test_id="T05/compound"),
            finding(
                "USA",
                "",
                site_id="33333333-3333-3333-3333-333333333333",
                applicable=False,
                test_id="T05/spelling",
            ),
        ]
        rows = {
            SITE_GEORGIA: site(),
            SITE_CHILE: site("Chile, Easter Island", site_id=SITE_CHILE, point=CHILE_POINT),
        }
        plan = P.build_plan(
            findings,
            rows,
            snapshot_countries={
                SITE_GEORGIA: "Georgia (country)",
                SITE_CHILE: "Chile, Easter Island",
            },
            phase3_sites={SITE_CHILE},
            codes=codes,
            normalize=normalize,
            atlas=atlas,
            anchors={SITE_GEORGIA: P.Anchor("Q995736", "test")},
            witnesses={
                SITE_GEORGIA: witness([claim("Q230")], {"Q230": {"label": "Georgia", "p297": "GE"}})
            },
            retrieved_at=None,
            built_at="2026-09-21T00:00:00+00:00",
        )
        assert len(plan.changes) == 2 and len(plan.skipped) == 1
        assert plan.skipped[0].reason == "finding-not-applicable"
        assert {c.site_id for c in plan.changes}.isdisjoint({s.site_id for s in plan.skipped})
        assert plan.counters["changes_on_phase3_sites"] == 1
        assert all(c.evidence for c in plan.changes)

    def test_a_phase3_site_is_written_and_flagged(
        self, vocabulary: tuple[dict[str, str], Any], atlas: Any
    ) -> None:
        """The supervisor's decision: a Phase 3 site is written here *and* stays in that worklist."""
        codes, normalize = vocabulary
        plan = P.build_plan(
            [finding()],
            {SITE_GEORGIA: site()},
            snapshot_countries={SITE_GEORGIA: "Georgia (country)"},
            phase3_sites={SITE_GEORGIA},
            codes=codes,
            normalize=normalize,
            atlas=atlas,
            anchors={},
            witnesses={},
            retrieved_at=None,
            built_at="2026-09-21T00:00:00+00:00",
        )
        assert plan.changes[0].phase3 is True
        assert plan.counters["changes_on_phase3_sites"] == 1


# ------------------------------------------------------------------------------- the statement
def insertion_rows(sql: str) -> list[str]:
    """The plan rows the statement's temp table is filled with - one tuple per write."""
    block = sql.split("INSERT INTO _country_plan", 1)[1].split("\n;\n", 1)[0]
    return [line for line in block.splitlines() if line.strip().startswith("('")]


def record(**over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": SITE_GEORGIA,
        "site_name": "Nekresi",
        "old_value": "Georgia (country)",
        "new_value": "Georgia",
        "rule": "disambiguation-hint",
        "condition": f"id = {SITE_GEORGIA} AND country IS NOT DISTINCT FROM 'Georgia (country)'",
        "reason": "country-canonical: 'Georgia (country)' -> 'Georgia' (ISO GE)",
        "evidence": ({"source": "test", "quote": "x"},),
    }
    base.update(over)
    return A.ChangeRecord(**base)


def second(**over: Any) -> A.ChangeRecord:
    return record(
        site_id=SITE_CHILE,
        site_name="Ahu Akivi",
        old_value="Chile, Easter Island",
        new_value="Chile",
        rule="compound-label-country-part",
        **over,
    )


class TestRenderTransaction:
    def test_every_row_carries_its_old_and_new_value(self) -> None:
        """One call site, one plan row per write: the journal is written by the loop, per row."""
        sql = A.render_transaction([record(), second()], site_ids={SITE_GEORGIA, SITE_CHILE})
        for r in (record(), second()):
            assert f"'{r.old_value}'" in sql and f"'{r.new_value}'" in sql
        assert sql.count("apply_remediation_change(") == 1
        assert len(insertion_rows(sql)) == 2
        assert "FOR r IN SELECT" in sql and "FROM _country_plan" in sql

    def test_one_transaction_and_no_delete(self) -> None:
        sql = A.render_transaction([record()], site_ids={SITE_GEORGIA})
        assert sql.count("BEGIN;") == 1 and sql.count("\nCOMMIT;\n") == 1
        assert "DELETE" not in sql.upper() and "TRUNCATE" not in sql.upper()
        assert "\\set ON_ERROR_STOP on" in sql

    def test_the_scope_guard_names_the_curated_source(self) -> None:
        sql = A.render_transaction([record()], site_ids={SITE_GEORGIA})
        assert "u.source_id <> 'ancient_nerds'" in sql
        assert "are not ancient_nerds sites" in sql

    def test_the_journal_is_reconciled_inside_the_transaction(self) -> None:
        sql = A.render_transaction([record()], site_ids={SITE_GEORGIA})
        assert "remediation_change_log l" in sql
        assert P.RUN_STAMP in sql and P.TEST_ID in sql
        assert "outside unified_sites.country" in sql

    def test_an_empty_plan_is_refused(self) -> None:
        with pytest.raises(P.PlanError):
            A.render_transaction([], site_ids=set())
        with pytest.raises(P.PlanError):
            A.render_transaction([], site_ids=set(), validate=False)

    def test_the_conditional_write_uses_the_planned_old_value(self) -> None:
        """The old value reaches the database through the loop body, not through the plan file."""
        sql = A.render_transaction([record()], site_ids={SITE_GEORGIA})
        body = sql.split("FOR r IN SELECT", 1)[1].split("END LOOP;", 1)[0]
        assert "r.old_value, r.new_value," in body
        assert "r.site_id::text," in body
        assert "r.evidence, r.site_id);" in body

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"site_id": "not-a-uuid"}, "not a UUID"),
            ({"old_value": ""}, "no old value"),
            ({"new_value": ""}, "no new value"),
            ({"new_value": "Georgia (country)"}, "not a change"),
            ({"new_value": "X" * 101}, "the column holds 100"),
            ({"evidence": ()}, "not auditable"),
        ],
    )
    def test_the_plan_side_mirror_refuses_a_corrupt_record(
        self, change: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(P.PlanError, match=message):
            A.validate_records([record(**change)])

    def test_the_same_site_twice_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="appears twice"):
            A.validate_records([record(), record()])

    def test_a_foreign_source_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="writes 'ancient_nerds' only"):
            A.render_transaction([record()], site_ids={SITE_GEORGIA}, source="lyra")

    def test_the_rehearsal_is_the_same_statement_rolled_back(self) -> None:
        sql = A.render_transaction([record(), second()], site_ids={SITE_GEORGIA, SITE_CHILE})
        rehearsal = A.rehearse(sql)
        assert rehearsal.startswith(sql.partition("\nCOMMIT;\n")[0])
        assert "\nROLLBACK;\n" in rehearsal and "\nCOMMIT;\n" not in rehearsal
        assert "temp table _country_plan left behind" in rehearsal

    def test_a_statement_without_a_commit_cannot_be_rehearsed(self) -> None:
        with pytest.raises(P.PlanError, match="no COMMIT"):
            A.rehearse("BEGIN;\nSELECT 1;\n")

    def test_the_rollback_swaps_the_values_and_its_run_stamp(self) -> None:
        rollback = [replace(record(), old_value="Georgia", new_value="Georgia (country)")]
        sql = A.render_transaction(
            rollback, run_stamp=P.ROLLBACK_RUN_STAMP, site_ids={SITE_GEORGIA}
        )
        assert "'Georgia'" in sql and "'Georgia (country)'" in sql
        assert P.ROLLBACK_RUN_STAMP in sql and f"'{P.RUN_STAMP}'" not in sql

    def test_emit_refuses_when_the_rollback_does_not_exist(self, tmp_path: Path) -> None:
        """The order is the rule: ROLLBACK.sql is written before APPLY.sql, never after."""
        with pytest.raises(P.PlanError, match="rollback is written before the apply"):
            A.emit([record()], tmp_path)

    def test_emit_writes_the_apply_next_to_an_existing_rollback(self, tmp_path: Path) -> None:
        (tmp_path / "ROLLBACK.sql").write_text("-- reversal\n", encoding="utf-8")
        A.emit([record()], tmp_path)
        assert (
            (tmp_path / "APPLY.sql")
            .read_text(encoding="utf-8")
            .startswith("-- Generated by scripts/remediation/mechanical/apply.py")
        )


class TestReadBackStatements:
    """The statements that report on the write must name the write they report on."""

    def test_no_statement_reaches_the_database_with_a_placeholder(self) -> None:
        statements = {
            "VERIFY_SQL": A.VERIFY_SQL,
            "PRIMITIVE_CHECK_SQL": A.PRIMITIVE_CHECK_SQL,
            "POST_COMMIT_READS": A.POST_COMMIT_READS.format(
                run_stamp="'x'", test_id="'y'", source="'z'"
            ),
            "REHEARSAL_READS": A.REHEARSAL_READS.format(run_stamp="'x'", source="'z'"),
        }
        for name, sql in statements.items():
            assert not re.search(r"\{[A-Za-z_]+\}", sql), name

    def test_the_rollback_rehearsal_refuses_without_a_reversal(self, tmp_path: Any) -> None:
        with pytest.raises(P.PlanError, match="no reversal to rehearse"):
            A.cmd_rehearse_rollback([], tmp_path)

    def test_the_rollback_rehearsal_reads_name_the_planned_rows(self) -> None:
        sql = A.ROLLBACK_REHEARSAL_READS.format(
            rollback_stamp="'x'", source="'y'", ids=f"'{SITE_GEORGIA}'::uuid"
        )
        assert not re.search(r"\{[A-Za-z_]+\}", sql)
        assert f"'{SITE_GEORGIA}'::uuid" in sql

    def test_the_verify_statement_names_the_run_it_reads_back(self) -> None:
        """A stamp that never reaches the SQL matches no row - and a count of 0 reads as clean."""
        assert f"'{P.RUN_STAMP}'" in A.VERIFY_SQL
        assert f"'{A.TEST_ID}'" in A.VERIFY_SQL
        assert f"'{P.ROLLBACK_RUN_STAMP}'" in A.VERIFY_SQL


class TestRecordRoundTrip:
    def test_load_records_reads_what_write_plan_jsonl_wrote(self, tmp_path: Path) -> None:
        change = P.Verdict(
            site_id=SITE_GEORGIA,
            site_name="Nekresi",
            ok=True,
            old_value="Georgia (country)",
            new_value="Georgia",
            rule="disambiguation-hint",
            reason="",
            note="disambiguation-hint: 'Georgia (country)' -> 'Georgia' (ISO GE)",
            phase3=False,
            finding_test_id="T05/disambiguated",
            evidence=({"source": "test", "quote": "x"},),
        )
        plan = P.Plan(changes=(change,), skipped=(), built_at="2026-09-21T00:00:00+00:00")
        P.write_plan_jsonl(plan, tmp_path / "PLAN.jsonl")
        records = A.load_records(tmp_path / "PLAN.jsonl")
        assert len(records) == 1
        loaded = records[0]
        assert (loaded.old_value, loaded.new_value) == ("Georgia (country)", "Georgia")
        A.validate_records(records)
        sql = A.render_transaction(records, site_ids={r.site_id for r in records})
        assert "'Georgia (country)'" in sql


@needs_deliverable
class TestTheDeliveredPlan:
    def test_the_delivered_plan_validates_and_has_the_agreed_size(self) -> None:
        records = A.load_records(DELIVERED_PLAN)
        A.validate_records(records)
        assert len(records) == 35
        assert {r.new_value for r in records} == {"Georgia", "Chile"}
        assert sum(1 for r in records if r.phase3) == 8

    def test_the_delivered_rollback_reverses_every_row_of_the_delivered_plan(self) -> None:
        records = A.load_records(DELIVERED_PLAN)
        rollback = (DELIVERED_PLAN.parent / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert P.ROLLBACK_RUN_STAMP in rollback
        assert len(insertion_rows(rollback)) == len(records)
        for r in records:
            assert f"'{r.new_value}'" in rollback and f"'{r.old_value}'" in rollback

    def test_every_written_row_names_a_census_finding_and_an_old_value(self) -> None:
        for line in DELIVERED_PLAN.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            assert payload["finding_test_id"] in {"T05/disambiguated", "T05/compound"}
            assert payload["old_value"] != payload["new_value"]
            assert payload["source_id"] == P.CURATED_SOURCE
            assert payload["run_stamp"] == P.RUN_STAMP
            sources = {e["source"] for e in payload["evidence"]}
            assert any(s.startswith("pipeline/utils/country_lookup.py") for s in sources)
            assert any(s.startswith("ancient-nerds-map/") for s in sources)
            assert any(s.startswith("naturalearth:") for s in sources)
