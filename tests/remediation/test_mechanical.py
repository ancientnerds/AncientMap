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

import hashlib
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
from mechanical import lane as L  # noqa: E402
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


@pytest.fixture(scope="module")
def atlas() -> Any:
    # A mark on a fixture never applied (and is an error since pytest 9.1), so the skip that
    # `needs_dataset` describes has to happen here, for every test that asks for the atlas.
    if not NE_SHAPEFILE.exists():
        pytest.skip(f"Natural Earth cache not present ({NE_SHAPEFILE}); run plan.py --collect")
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


def delivered(
    directory: Path, rows: list[A.ChangeRecord] | None = None
) -> tuple[list[A.ChangeRecord], Path]:
    """A plan written the way the planners write it, with its pinned reversal next to it."""
    changes = tuple(
        P.Verdict(
            site_id=r.site_id,
            site_name=r.site_name,
            ok=True,
            old_value=r.old_value,
            new_value=r.new_value,
            rule=r.rule,
            reason="",
            note=f"{r.old_value!r} -> {r.new_value!r}",
            phase3=False,
            finding_test_id="T05/disambiguated",
            evidence=r.evidence,
        )
        for r in (rows or [record(), second()])
    )
    plan = P.Plan(changes=changes, skipped=(), built_at="2026-09-22T00:00:00+00:00")
    plan_path = directory / "PLAN.jsonl"
    P.write_plan_jsonl(plan, plan_path)
    P.write_rollback_sql(plan, directory / "ROLLBACK.sql", plan_path=plan_path)
    return A.load_records(plan_path), plan_path


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
        # The guard still names the curated source, but the name reaches the operator as a RAISE
        # argument and no longer as text spliced into the message. That is the point of the change:
        # a name written into the message literal only parses while the name happens to contain no
        # quote, which is a property of today's value and not of this code. This assertion was
        # rewritten from the old expectation "are not ancient_nerds sites", which held only because
        # the name was spliced in; asserting it again would re-assert the defect. Asking for both
        # halves - the placeholder in the message, the name kept out of it - is strictly stronger
        # than the old expectation, which could not tell the two apart.
        assert "RAISE EXCEPTION 'country repair: % planned row(s) are not % sites'" in sql
        assert "are not ancient_nerds sites" not in sql

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
            A.emit([record()], tmp_path, plan_path=tmp_path / "PLAN.jsonl")

    def test_emit_writes_the_apply_next_to_an_existing_rollback(self, tmp_path: Path) -> None:
        """Rewritten 2026-09-22 (SECURITY 3 / B7): the old test put `-- reversal` into ROLLBACK.sql
        and expected the emit to accept it - an undo that reverses nothing, tied to no plan. Now the
        rollback must be this plan's pinned reversal, and the apply carries the plan's digest as its
        first line, above the generated statement."""
        records, plan_path = delivered(tmp_path)
        A.emit(records, tmp_path, plan_path=plan_path)
        text = (tmp_path / "APPLY.sql").read_text(encoding="utf-8")
        first, _, body = text.partition("\n")
        assert first == f"-- plan sha256 {P.plan_sha256(plan_path)}"
        assert body.startswith("-- Generated by scripts/remediation/mechanical/apply.py")
        assert body == A.apply_statement(records, L.T05)


class TestReadBackStatements:
    """The statements that report on the write must name the write they report on."""

    def test_no_statement_reaches_the_database_with_a_placeholder(self) -> None:
        """Every lane's statements, formatted the way the commands format them.

        Extended 2026-09-22 from T05's four statements to every lane's: the templates are shared,
        so a placeholder a new field forgot would reach production in some lane's statement.
        """
        statements = {
            "VERIFY_SQL": A.VERIFY_SQL,
            "PRIMITIVE_CHECK_SQL": A.PRIMITIVE_CHECK_SQL,
        }
        for name, lane in L.LANES.items():
            statements[f"{name}: readback"] = A.READBACKS[name]
            statements[f"{name}: post-commit"] = A.post_commit_reads(lane, run_stamp="x")
            statements[f"{name}: rehearsal"] = A.rehearsal_reads(lane, run_stamp="x")
            statements[f"{name}: rollback rehearsal"] = A.rollback_rehearsal_reads([record()], lane)
        for name, sql in statements.items():
            assert not re.search(r"\{[A-Za-z_]+\}", sql), name
        assert set(A.READBACKS) == set(L.LANES), "every lane needs its read-only verification"

    def test_the_rollback_rehearsal_refuses_without_a_reversal(self, tmp_path: Any) -> None:
        with pytest.raises(P.PlanError, match="no reversal to rehearse"):
            A.cmd_rehearse_rollback([], tmp_path, plan_path=tmp_path / "PLAN.jsonl")

    def test_a_rollback_without_a_commit_cannot_be_rehearsed(self, tmp_path: Path) -> None:
        """Swapping COMMIT for ROLLBACK needs a COMMIT to swap: without one, the "rehearsal" would
        be the file itself, and whatever it does would be kept. Raised before any psql call."""
        (tmp_path / "ROLLBACK.sql").write_text("BEGIN;\nSELECT 1;\n", encoding="utf-8")
        with pytest.raises(P.PlanError, match="no COMMIT"):
            A.cmd_rehearse_rollback([record()], tmp_path, plan_path=tmp_path / "PLAN.jsonl")

    def test_the_rollback_rehearsal_reads_name_the_planned_rows(self) -> None:
        """Each planned row is read against the value *that row* was given - rewritten from the
        T05 form `country IN ('Georgia', 'Chile')`, which any row holding either value satisfied
        and which no lane with a derived value (period_name) could have spelled out in advance."""
        sql = A.rollback_rehearsal_reads([record(), second()])
        assert not re.search(r"\{[A-Za-z_]+\}", sql)
        assert f"('{SITE_GEORGIA}'::uuid, 'Georgia')" in sql
        assert f"('{SITE_CHILE}'::uuid, 'Chile')" in sql
        assert "u.country IS NOT DISTINCT FROM p.written" in sql
        assert f"'{P.ROLLBACK_RUN_STAMP}'" in sql

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

    def test_t05_rendering_is_unchanged_by_the_lane_refactor(self) -> None:
        """The lane refactor must not touch a single byte of the statement T05 wrote with.

        The digests were measured on 2026-09-22 from the code *before* the refactor, rendering the
        delivered `PLAN.jsonl` - not from the delivered `APPLY.sql`/`ROLLBACK.sql`, which differ
        from today's rendering by one reworded comment in scope guard 1 (the statements are the
        same). `load_records` reads text mode, so the digest is the same on an LF and a CRLF
        checkout of the plan (both measured).
        """
        records = A.load_records(DELIVERED_PLAN)
        site_ids = {r.site_id for r in records}
        apply_sql = A.render_transaction(records, run_stamp=P.RUN_STAMP, site_ids=site_ids)
        rollback_sql = P.render_rollback_sql(records, site_ids=site_ids)
        assert _sha(apply_sql) == T05_APPLY_SHA256
        assert _sha(rollback_sql) == T05_ROLLBACK_SHA256
        assert _sha(A.VERIFY_SQL) == T05_VERIFY_SHA256
        # the lane defaults are T05's, so an explicit lane renders the same bytes
        explicit = A.render_transaction(records, site_ids=site_ids, lane=L.T05)
        assert _sha(explicit) == T05_APPLY_SHA256


#: sha256 of T05's statements as the pre-refactor code rendered them from the delivered plan.
T05_APPLY_SHA256 = "f27845273ff0b34a458036e9ee4fcbe3e97ea4a53d08340c205ea66c3667f2ff"
T05_ROLLBACK_SHA256 = "832b7b6a55558d67c4ea202ca27938698a02e73a0deae8ac552e62b915b875d1"
T05_VERIFY_SHA256 = "a3f1d62426db68f055185bbbbffd86cb7876a25b282a77afe40347162f0f9007"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------- the lanes
SITE_BOA = "037e3715-f5f7-4345-8216-8aa26f404009"  # Boa Island, stored 'Ireland', lies in NI
SITE_GIANTS_RING = "e0d56737-6459-4329-9ef5-1a46e8d75f10"  # stored 'United Kingdom' by phase 3


def uk_record(**over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": SITE_BOA,
        "site_name": "Boa Island",
        "old_value": "Ireland",
        "new_value": "Northern Ireland",
        "rule": "geo-unit",
        "condition": f"id = {SITE_BOA} AND country IS NOT DISTINCT FROM 'Ireland'",
        "reason": "country-uk-part (geo-unit): 'Ireland' -> 'Northern Ireland'",
        "evidence": ({"source": "test", "quote": "x"},),
        "premise": "54.5168,-7.8333",
    }
    base.update(over)
    return A.ChangeRecord(**base)


def uk_second(**over: Any) -> A.ChangeRecord:
    return uk_record(
        site_id=SITE_GIANTS_RING,
        site_name="Giant's Ring",
        old_value="United Kingdom",
        premise="54.5541,-5.9496",
        **over,
    )


class TestTheLanes:
    def test_the_uk_statement_carries_its_own_journal_identity_and_none_of_t05s(self) -> None:
        sql = A.render_transaction(
            [uk_record(), uk_second()], site_ids={SITE_BOA, SITE_GIANTS_RING}, lane=L.UK_PARTS
        )
        assert f"'{L.UK_PARTS.run_stamp}'" in sql and f"'{L.UK_PARTS.test_id}'" in sql
        assert f"'country-uk-part:{SITE_BOA}'" in sql
        assert P.RUN_STAMP not in sql and P.TEST_ID not in sql
        assert "country-canonical" not in sql and "_country_plan" not in sql
        assert sql.count("apply_remediation_change(") == 1
        assert "'unified_sites', 'country', 'id', r.site_id::text," in sql

    def test_the_fourth_guard_is_rendered_only_for_a_lane_that_owns_its_values(self) -> None:
        uk = A.render_transaction([uk_record()], site_ids={SITE_BOA}, lane=L.UK_PARTS)
        assert "scope guard 4" in uk
        assert (
            "WHERE p.new_value NOT IN ('England', 'Northern Ireland', 'Scotland', 'Wales');" in uk
        )
        assert "write a value this lane does not own" in uk
        t05 = A.render_transaction([record()], site_ids={SITE_GEORGIA})
        assert "scope guard 4" not in t05 and "does not own" not in t05

    def test_the_fifth_guard_conditions_the_write_on_its_premise(self) -> None:
        uk = A.render_transaction([uk_record()], site_ids={SITE_BOA}, lane=L.UK_PARTS)
        assert "scope guard 5" in uk
        assert f"WHERE ({L.UK_PARTS.premise_sql}) IS DISTINCT FROM p.premise;" in uk
        assert "    premise     TEXT NOT NULL," in uk
        assert "'54.5168,-7.8333'" in uk
        t05 = A.render_transaction([record()], site_ids={SITE_GEORGIA})
        assert "scope guard 5" not in t05 and "premise" not in t05

    def test_the_uk_reversal_undoes_only_values_the_lane_owns(self) -> None:
        sql = P.render_rollback_sql(
            [uk_record(), uk_second()], site_ids={SITE_BOA, SITE_GIANTS_RING}, lane=L.UK_PARTS
        )
        assert f"'{L.UK_PARTS.rollback_run_stamp}'" in sql
        assert L.UK_PARTS.rollback_run_stamp.endswith("-rollback")
        assert f"'country-uk-part-rollback:{SITE_BOA}'" in sql
        assert (
            "WHERE p.old_value NOT IN ('England', 'Northern Ireland', 'Scotland', 'Wales');" in sql
        )
        assert "undo a value this lane does not own" in sql
        assert "'54.5168,-7.8333'" in sql, "the reversal is conditioned on the same premise"

    @pytest.mark.parametrize("value", ["United Kingdom", "Georgia", "Ireland"])
    def test_the_plan_side_mirror_refuses_a_value_the_lane_does_not_own(self, value: str) -> None:
        corrupt = uk_record(old_value="Isle of Man", new_value=value)
        with pytest.raises(P.PlanError, match="is not a value the uk-parts lane owns"):
            A.validate_records([corrupt], lane=L.UK_PARTS)

    def test_a_reversal_that_undoes_a_value_the_lane_never_wrote_is_refused(self) -> None:
        reversed_ = replace(uk_record(), old_value="Georgia", new_value="Ireland")
        with pytest.raises(P.PlanError, match="'Georgia' is not a value the uk-parts lane owns"):
            A.validate_records([reversed_], lane=L.UK_PARTS, rollback=True)
        A.validate_records(
            [replace(uk_record(), old_value="Northern Ireland", new_value="Ireland")],
            lane=L.UK_PARTS,
            rollback=True,
        )

    def test_a_lane_with_a_premise_refuses_a_record_without_one(self) -> None:
        with pytest.raises(P.PlanError, match="carries no premise"):
            A.validate_records([uk_record(premise=None)], lane=L.UK_PARTS)

    def test_a_lane_without_a_premise_refuses_one_it_would_not_check(self) -> None:
        with pytest.raises(P.PlanError, match="checks no premise"):
            A.validate_records([record(premise="41.9,45.7")])

    def test_the_column_width_is_the_lane_s(self) -> None:
        narrow = replace(L.UK_PARTS, name="narrow", max_chars=10, allowed_new_values=())
        with pytest.raises(P.PlanError, match="the column holds 10"):
            A.validate_records([uk_record()], lane=narrow)
        sql = A.render_transaction([uk_record(new_value="Wales")], site_ids={SITE_BOA}, lane=narrow)
        assert "OR length(p.new_value) > 10;" in sql

    def test_the_uk_read_statements_name_the_uk_run(self) -> None:
        readback = A.READBACKS[L.UK_PARTS.name]
        assert f"'{L.UK_PARTS.run_stamp}'" in readback
        assert f"'{L.UK_PARTS.rollback_run_stamp}'" in readback
        assert f"'{L.UK_PARTS.test_id}'" in readback
        assert "'Northern Ireland'" in readback and "civilization" in readback
        assert P.RUN_STAMP not in readback

    def test_the_uk_rehearsal_reads_its_own_temp_table_and_residual(self) -> None:
        sql = A.render_transaction([uk_record()], site_ids={SITE_BOA}, lane=L.UK_PARTS)
        rehearsal = A.rehearse(sql, lane=L.UK_PARTS)
        assert "to_regclass('pg_temp._uk_part_plan')" in rehearsal
        assert "country IN ('United Kingdom', 'UK', 'Great Britain')" in rehearsal
        assert f"'{L.UK_PARTS.run_stamp}'" in rehearsal.split("\nROLLBACK;\n", 1)[1]

    def test_every_rendered_guard_has_its_probe(self) -> None:
        foreign = {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Somewhere",
            "value": "Scotland",
            "premise": "56.0,-3.0",
        }
        uk = {suffix for suffix, _, _ in A.probe_cases([uk_record()], L.UK_PARTS, foreign)}
        assert {"guard4-not-owned", "guard5-premise"} <= uk
        t05 = {suffix for suffix, _, _ in A.probe_cases([record()], L.T05, foreign)}
        assert "guard4-not-owned" not in t05 and "guard5-premise" not in t05
        assert {"guard1-other-source", "guard2-no-op", "guard2-too-long"} <= t05

    def test_the_probes_read_the_foreign_row_whole_even_with_a_pipe_in_its_name(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Unaligned psql separates fields with `|`: a name holding one would have shifted the
        foreign row's value and premise into the wrong fields of the guard-1 probe."""
        foreign = {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Broch | Dun",
            "value": "Scotland",
            "premise": "58.1,-3.9",
        }
        monkeypatch.setattr(A, "psql_json_reader", lambda: lambda sql: [foreign])
        sent: list[str] = []

        def refuse_every_probe(sql: str, *, rows: bool = False, check: bool = True, **_: Any):
            sent.append(sql)
            if rows:
                return _done("0\n")
            return _done("", returncode=3) if "RAISE" not in sql else _done("ERROR: x\n", 3)

        monkeypatch.setattr(A, "run_psql", refuse_every_probe)
        assert A.cmd_probe_guards([uk_record()], Path("."), L.UK_PARTS) == 0
        guard1 = next(s for s in sent if "guard1-other-source" in s)
        assert (
            "'11111111-1111-1111-1111-111111111111'::uuid, 'Scotland', 'Northern Ireland'" in guard1
        )
        assert "'58.1,-3.9'" in guard1
        assert "guard 5" in capsys.readouterr().out

    def test_the_uk_rollback_rehearsal_reads_each_row_against_its_part(self) -> None:
        """Each planned row is checked against the unit *it* was given - a set of the four parts
        would pass with any row holding any part."""
        sql = A.rollback_rehearsal_reads([uk_record(), uk_second(new_value="England")], L.UK_PARTS)
        assert f"('{SITE_BOA}'::uuid, 'Northern Ireland')" in sql
        assert f"('{SITE_GIANTS_RING}'::uuid, 'England')" in sql
        assert f"'{L.UK_PARTS.rollback_run_stamp}'" in sql
        assert "to_regclass('pg_temp._uk_part_plan')" in sql

    @pytest.mark.parametrize("name", sorted(L.LANES))
    def test_every_lane_has_its_own_identity(self, name: str) -> None:
        """Two lanes sharing a stamp, a key prefix, a temp table or a directory would read each
        other's rows back as their own."""
        lane = L.LANES[name]
        others = [other for other in L.LANES.values() if other is not lane]
        for attribute in ("run_stamp", "key_prefix", "plan_table", "out_dir_name", "test_id"):
            assert getattr(lane, attribute) not in {getattr(o, attribute) for o in others}, (
                attribute
            )

    def test_an_unknown_lane_is_refused_by_the_cli(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            A.main(["--lane", "atlantis", "--verify"])
        assert "invalid choice" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("column", "country; DROP TABLE x", "not a plain column name"),
            ("plan_table", "plan", "temp-table name"),
            ("label", "it's", "RAISE message"),
            ("label", "100%", "RAISE message"),
            ("key_prefix", "a:b", "change_key prefix"),
            ("max_chars", 0, "must be positive"),
            ("run_stamp", "", "journal identity"),
            ("allowed_new_values", ("X" * 101,), "cannot be written"),
        ],
    )
    def test_a_lane_that_would_splice_something_unsafe_into_sql_is_refused(
        self, field: str, value: Any, message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            replace(L.UK_PARTS, **{field: value})


# ------------------------------------------------ [H] SECURITY 3 / BACKEND B7: the pin
def _no_psql(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("a refused statement must not reach psql")


class TestThePin:
    """`--apply` sends the file on disk only while it is still the plan's own statement."""

    def test_the_apply_is_pinned_to_the_plan_and_verifies(self, tmp_path: Path) -> None:
        records, plan_path = delivered(tmp_path)
        A.emit(records, tmp_path, plan_path=plan_path)
        text = P.verify_pinned(
            tmp_path / "APPLY.sql", plan_path=plan_path, expected=A.apply_statement(records, L.T05)
        )
        assert text.startswith(f"-- plan sha256 {P.plan_sha256(plan_path)}\n")

    def test_a_plan_changed_after_the_emit_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, plan_path = delivered(tmp_path)
        A.emit(records, tmp_path, plan_path=plan_path)
        # the plan is re-built after the emit: one row fewer
        delivered(tmp_path, [record()])
        monkeypatch.setattr(A, "run_psql", _no_psql)
        stale = A.load_records(plan_path)
        for command in (A.cmd_apply, A.cmd_rehearse):
            with pytest.raises(
                P.PlanError, match="the plan changed after the statement was emitted"
            ):
                command(stale, tmp_path, plan_path=plan_path)

    def test_an_apply_without_a_pin_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, plan_path = delivered(tmp_path)
        (tmp_path / "APPLY.sql").write_text(A.apply_statement(records, L.T05), encoding="utf-8")
        monkeypatch.setattr(A, "run_psql", _no_psql)
        with pytest.raises(P.PlanError, match="carries no '-- plan sha256' pin"):
            A.cmd_apply(records, tmp_path, plan_path=plan_path)

    def test_a_hand_edited_apply_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, plan_path = delivered(tmp_path)
        A.emit(records, tmp_path, plan_path=plan_path)
        path = tmp_path / "APPLY.sql"
        path.write_text(
            path.read_text(encoding="utf-8").replace("'Georgia'", "'Armenia'"), encoding="utf-8"
        )
        monkeypatch.setattr(A, "run_psql", _no_psql)
        with pytest.raises(P.PlanError, match="edited after the emit"):
            A.cmd_apply(records, tmp_path, plan_path=plan_path)

    def test_two_pins_are_refused(self, tmp_path: Path) -> None:
        records, plan_path = delivered(tmp_path)
        A.emit(records, tmp_path, plan_path=plan_path)
        path = tmp_path / "APPLY.sql"
        path.write_text(path.read_text(encoding="utf-8") * 2, encoding="utf-8")
        with pytest.raises(P.PlanError, match="2 pins"):
            P.verify_pinned(path, plan_path=plan_path, expected=A.apply_statement(records, L.T05))

    def test_a_missing_apply_is_refused(self, tmp_path: Path) -> None:
        records, plan_path = delivered(tmp_path)
        with pytest.raises(P.PlanError, match="emit it from the plan first"):
            A.cmd_apply(records, tmp_path, plan_path=plan_path)

    def test_emit_refuses_the_rollback_of_another_plan(self, tmp_path: Path) -> None:
        records, plan_path = delivered(tmp_path)
        other = tmp_path / "other"
        other.mkdir()
        delivered(other, [record()])
        (tmp_path / "ROLLBACK.sql").write_bytes((other / "ROLLBACK.sql").read_bytes())
        with pytest.raises(P.PlanError, match="rendered from plan sha256"):
            A.emit(records, tmp_path, plan_path=plan_path)

    def test_emit_refuses_a_hand_edited_rollback(self, tmp_path: Path) -> None:
        records, plan_path = delivered(tmp_path)
        path = tmp_path / "ROLLBACK.sql"
        path.write_text(
            path.read_text(encoding="utf-8").replace("COMMIT;", "COMMIT; -- ok"), encoding="utf-8"
        )
        with pytest.raises(P.PlanError, match="edited after the emit"):
            A.emit(records, tmp_path, plan_path=plan_path)

    def test_the_rollback_rehearsal_refuses_a_rollback_of_another_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records, plan_path = delivered(tmp_path)
        delivered(tmp_path, [record()])  # the plan moved on; ROLLBACK.sql now reverses the new one
        monkeypatch.setattr(A, "run_psql", _no_psql)
        with pytest.raises(P.PlanError, match="edited after the emit"):
            A.cmd_rehearse_rollback(records, tmp_path, plan_path=plan_path)

    def test_a_missing_plan_cannot_pin_anything(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="no plan to pin a statement to"):
            P.plan_sha256(tmp_path / "PLAN.jsonl")

    def test_the_digest_is_the_same_on_a_crlf_checkout(self, tmp_path: Path) -> None:
        """`core.autocrlf=true` checks a committed plan out with CRLF; the pin must still hold."""
        lf, crlf = tmp_path / "lf.jsonl", tmp_path / "crlf.jsonl"
        lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
        crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
        assert P.plan_sha256(lf) == P.plan_sha256(crlf)
        assert P.plan_sha256(lf) == hashlib.sha256(b'{"a": 1}\n{"b": 2}\n').hexdigest()

    def test_the_cli_never_re_emits_before_it_sends(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """A re-emit on `--apply` would overwrite a hand-edited file with a fresh render and send
        that - the file a reviewer checked is the one that must be refused or sent."""
        records, plan_path = delivered(tmp_path)
        A.emit(records, tmp_path, plan_path=plan_path)
        path = tmp_path / "APPLY.sql"
        edited = path.read_text(encoding="utf-8").replace("'Georgia'", "'Armenia'")
        path.write_text(edited, encoding="utf-8")
        monkeypatch.setattr(A, "run_psql", _no_psql)
        code = A.main(["--apply", "--plan", str(plan_path), "--out", str(tmp_path)])
        assert code == A.EXIT_REFUSED
        assert "REFUSED" in capsys.readouterr().err
        assert path.read_text(encoding="utf-8") == edited


NEW_LANES = [
    name
    for name in sorted(L.LANES)
    if name != L.T05.name and (A.lane_dir(L.LANES[name]) / "PLAN.jsonl").exists()
]


class TestTheDeliveredLanes:
    """The committed statements of the lanes not yet applied are exactly what `--emit` renders."""

    def test_every_new_lane_has_a_delivered_plan(self) -> None:
        assert sorted(NEW_LANES) == sorted(n for n in L.LANES if n != L.T05.name)

    @pytest.mark.parametrize("name", NEW_LANES)
    def test_the_committed_statements_are_the_plan_s_own(self, name: str) -> None:
        lane = L.LANES[name]
        directory = A.lane_dir(lane)
        plan_path = directory / "PLAN.jsonl"
        records = A.load_records(plan_path)
        A.validate_records(records, lane=lane)
        P.verify_pinned(
            directory / "APPLY.sql", plan_path=plan_path, expected=A.apply_statement(records, lane)
        )
        P.verify_pinned(
            directory / "ROLLBACK.sql",
            plan_path=plan_path,
            expected=A.rollback_statement(records, lane),
        )

    @pytest.mark.parametrize("name", NEW_LANES)
    def test_the_cli_re_emits_the_committed_apply_byte_for_byte(
        self, name: str, tmp_path: Path
    ) -> None:
        """What the orchestrator's `--emit` will write is what is committed: no surprise diff."""
        lane = L.LANES[name]
        directory = A.lane_dir(lane)
        for file in ("PLAN.jsonl", "ROLLBACK.sql"):
            (tmp_path / file).write_text(
                (directory / file).read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
            )
        code = A.main(
            [
                "--lane",
                name,
                "--emit",
                "--plan",
                str(tmp_path / "PLAN.jsonl"),
                "--out",
                str(tmp_path),
            ]
        )
        assert code == A.EXIT_OK
        assert (tmp_path / "APPLY.sql").read_text(encoding="utf-8") == (
            directory / "APPLY.sql"
        ).read_text(encoding="utf-8")


@needs_deliverable
class TestTheDeliveredT05Pin:
    def test_the_delivered_rollback_is_pinned_to_the_delivered_plan(self) -> None:
        records = A.load_records(DELIVERED_PLAN)
        P.verify_pinned(
            DELIVERED_PLAN.parent / "ROLLBACK.sql",
            plan_path=DELIVERED_PLAN,
            expected=A.rollback_statement(records, L.T05),
        )

    def test_the_delivered_apply_cannot_be_sent_again(self) -> None:
        """The historical APPLY.sql is the statement that wrote the 35 rows, kept as it ran - with
        no pin, which is exactly what `--apply` now refuses."""
        records = A.load_records(DELIVERED_PLAN)
        with pytest.raises(P.PlanError, match="carries no"):
            P.verify_pinned(
                DELIVERED_PLAN.parent / "APPLY.sql",
                plan_path=DELIVERED_PLAN,
                expected=A.apply_statement(records, L.T05),
            )


# ------------------------------------ [H] SECURITY 3 / BACKEND B7: after a lost answer
class FakeProduction:
    """Answers the SQL `cmd_apply` sends, and refuses anything else - a stand-in that cannot be
    satisfied by a statement the real path would not send."""

    def __init__(self, counts: list[Any], write: Any, planned: int) -> None:
        self.counts = list(counts)
        self.write = write
        self.planned = planned
        self.sent: list[str] = []

    def run_psql(self, sql: str, *, rows: bool = False, check: bool = True, **_: Any) -> Any:
        self.sent.append(sql)
        if sql.startswith("SELECT count(*) FROM remediation_change_log WHERE run_stamp = "):
            answer = self.counts.pop(0)
            if isinstance(answer, BaseException):
                raise answer
            return _done(f"{answer}\n")
        if sql.startswith("-- plan sha256 "):
            if isinstance(self.write, BaseException):
                raise self.write
            return _done("", returncode=self.write)
        if sql.startswith("WITH planned(site_id, new_value)"):
            n = self.planned
            return _done(
                f"journal rows for this run stamp|{n}\n"
                f"planned rows now holding the planned new value|{n}\n"
                "planned rows with no journal row for this run stamp|0\n"
                "journal rows for this run outside unified_sites.country|0\n"
            )
        if sql is A.VERIFY_SQL:
            return _done("")
        raise AssertionError(f"unexpected statement: {sql[:80]!r}")


def _done(stdout: str, returncode: int = 0) -> Any:
    import subprocess

    return subprocess.CompletedProcess(
        args=["psql"], returncode=returncode, stdout=stdout, stderr=""
    )


@pytest.fixture
def applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    records, plan_path = delivered(tmp_path)
    A.emit(records, tmp_path, plan_path=plan_path)
    monkeypatch.setattr(A, "verify_interests", lambda *a, **k: "")

    def run(counts: list[Any], write: Any) -> tuple[Any, FakeProduction]:
        fake = FakeProduction(counts, write, len(records))
        monkeypatch.setattr(A, "run_psql", fake.run_psql)
        return lambda: A.cmd_apply(records, tmp_path, plan_path=plan_path), fake

    return run


class TestTheCommitState:
    def test_a_timeout_after_the_commit_is_reported_as_committed(
        self, applied: Any, capsys: pytest.CaptureFixture
    ) -> None:
        go, _ = applied([0, 2], prod_outcome_unknown())
        assert go() == A.EXIT_COMMITTED_UNCLEAN
        out = capsys.readouterr().out
        assert "COMMITTED: psql timed out" in out and "APPLY LANDED" in out

    def test_a_timeout_before_the_commit_is_reported_as_not_committed(
        self, applied: Any, capsys: pytest.CaptureFixture
    ) -> None:
        go, _ = applied([0, 0], prod_outcome_unknown())
        assert go() == A.EXIT_NOT_COMMITTED
        assert "NOT COMMITTED: psql timed out" in capsys.readouterr().out

    def test_a_failed_exit_is_settled_from_the_journal(
        self, applied: Any, capsys: pytest.CaptureFixture
    ) -> None:
        """psql exits 3 when a post-commit read fails - after the COMMIT went through."""
        go, _ = applied([0, 2], 3)
        assert go() == A.EXIT_COMMITTED_UNCLEAN
        assert "COMMITTED: psql exited 3" in capsys.readouterr().out
        go, _ = applied([0, 0], 3)
        assert go() == A.EXIT_NOT_COMMITTED

    def test_an_unreadable_journal_is_an_unknown_outcome_with_the_query_to_run(
        self, applied: Any
    ) -> None:
        go, _ = applied([0, prod_outcome_unknown()], prod_outcome_unknown())
        with pytest.raises(A.OutcomeUnknown, match="Before any retry run: SELECT count"):
            go()

    def test_a_journal_read_that_fails_is_an_unknown_outcome(self, applied: Any) -> None:
        go, _ = applied([0, P.PlanError("psql exited 255")], 3)
        with pytest.raises(A.OutcomeUnknown, match="could not be read either"):
            go()

    def test_a_partial_journal_is_an_unknown_outcome(self, applied: Any) -> None:
        go, _ = applied([0, 1], prod_outcome_unknown())
        with pytest.raises(A.OutcomeUnknown, match="1 of 2 rows"):
            go()

    def test_a_clean_apply_is_asserted_from_the_read_back(
        self, applied: Any, capsys: pytest.CaptureFixture
    ) -> None:
        go, fake = applied([0], 0)
        assert go() == A.EXIT_OK
        assert "APPLY OK" in capsys.readouterr().out
        assert any(s.startswith("-- plan sha256 ") for s in fake.sent)

    def test_a_stamp_that_already_journals_rows_is_never_applied_again(self, applied: Any) -> None:
        go, fake = applied([2], 0)
        with pytest.raises(P.PlanError, match="never apply twice"):
            go()
        assert not any(s.startswith("-- plan sha256 ") for s in fake.sent)

    def test_a_journal_count_of_the_wrong_shape_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(A, "read_rows", lambda sql: [])
        with pytest.raises(P.PlanError, match="came back as"):
            A.journal_count("x")

    def test_main_reports_an_unknown_outcome_with_its_own_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        def boom(*args: Any, **kwargs: Any) -> int:
            raise A.OutcomeUnknown("psql did not answer within 900s")

        monkeypatch.setattr(A, "run", boom)
        assert A.main(["--verify"]) == A.EXIT_UNKNOWN
        err = capsys.readouterr().err
        assert "OUTCOME UNKNOWN" in err and "REFUSED" not in err


def prod_outcome_unknown() -> Any:
    return A.OutcomeUnknown("psql did not answer within 900s: UNKNOWN")
