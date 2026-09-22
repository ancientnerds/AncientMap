"""Does the shape lane undo only phase 3's malformed site_type writes - and nothing else?

Pure tests: rows, journal links and a snapshot mapping in, verdicts out; the canonical list and
`normalize_site_type` are the pipeline's own. Each refusal has a mutation case in
`mechanical/mutation_sweep.py`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402
from mechanical import site_type_shape as S  # noqa: E402

from pipeline.normalizers.site_type import CANONICAL_TYPES  # noqa: E402

DELIVERED = REPO / "output" / "remediation" / "mechanical_site_type" / "PLAN.jsonl"
needs_plan = pytest.mark.skipif(not DELIVERED.exists(), reason=f"{DELIVERED} not built yet")

WITHAM = "c5c5f2da-a5ea-41c6-807d-4c8ad7af03ba"
LINK = P.JournalLink(
    28880, "phase3:batch-0209:chunk-0001", "P3/site_type", "City/town/settlement", "suspect_modern"
)
SNAPSHOT = {WITHAM: "City/town/settlement"}


def row(
    site_type: str | None = "suspect_modern",
    *,
    journal: tuple[P.JournalLink, ...] = (LINK,),
    source_id: str = P.CURATED_SOURCE,
) -> S.Row:
    return S.Row(WITHAM, "Witham Shield", source_id, site_type, journal)


class TestTheShape:
    @pytest.mark.parametrize(
        ("value", "shape"),
        [
            ("suspect_modern", "marker-token"),
            ("Grave (burial site) — not representable", "model-refusal"),
            ("Treasury", None),
            ("Altar", None),
            ("Suspect_modern", None),
        ],
    )
    def test_only_a_marker_or_a_refusal_is_not_a_type(self, value: str, shape: str | None) -> None:
        assert S.not_a_type(value) == shape

    def test_no_canonical_type_has_a_not_a_type_shape(self) -> None:
        """The shape rule may never mistake a real type for a malformed one."""
        assert [t for t in CANONICAL_TYPES if S.not_a_type(t)] == []

    def test_the_sql_residual_uses_the_same_rule(self) -> None:
        predicate = L.SITE_TYPE_SHAPE.post_commit_residual.predicate
        assert P.sql_literal(L.NOT_A_TYPE_MARKER) in predicate
        assert f"ILIKE '%{L.NOT_A_TYPE_PHRASE}%'" in predicate


class TestClassifyShape:
    def test_a_marker_written_by_phase3_is_restored_to_what_it_replaced(self) -> None:
        verdict = S.classify_shape(row(), snapshot=SNAPSHOT)
        assert verdict.ok and verdict.old_value == "suspect_modern"
        assert (
            verdict.new_value == "City/town/settlement" and verdict.rule == "restore-marker-token"
        )
        assert verdict.phase3
        sources = [e["source"] for e in verdict.evidence]
        assert "remediation_change_log:28880" in sources
        assert any(s.startswith("output/remediation/snapshot/") for s in sources)
        assert "pipeline/normalizers/site_type.py:CANONICAL_TYPES" in sources

    def test_a_model_refusal_is_restored(self) -> None:
        refusal = "Grave (burial site) — not representable"
        link = P.JournalLink(
            28606, "phase3:batch-0168", "P3/site_type", "Necropolis/tombs complex", refusal
        )
        verdict = S.classify_shape(
            row(refusal, journal=(link,)), snapshot={WITHAM: "Necropolis/tombs complex"}
        )
        assert verdict.ok and verdict.new_value == "Necropolis/tombs complex"
        assert verdict.rule == "restore-model-refusal"

    def test_a_real_word_outside_the_list_goes_to_review(self) -> None:
        link = P.JournalLink(
            28127, "phase3:batch-0078", "P3/site_type", "Megalithic structures", "Treasury"
        )
        verdict = S.classify_shape(row("Treasury", journal=(link,)), snapshot=SNAPSHOT)
        assert not verdict.ok and verdict.reason == S.REVIEW
        assert verdict.evidence and verdict.evidence[0]["source"] == "remediation_change_log:28127"

    def test_a_value_without_a_journal_row_is_refused(self) -> None:
        """Mookambika's shape: `suspect_modern` from before the remediation - nothing to restore."""
        verdict = S.classify_shape(row(journal=()), snapshot=SNAPSHOT)
        assert not verdict.ok and verdict.reason == "no-journal-row"

    def test_a_value_written_by_another_lane_is_refused(self) -> None:
        other = P.JournalLink(
            1, "2026-09-21_mechanical-country", "T05", "City/town/settlement", "suspect_modern"
        )
        verdict = S.classify_shape(row(journal=(other,)), snapshot=SNAPSHOT)
        assert not verdict.ok and verdict.reason == "not-a-phase3-write"

    def test_a_journal_that_disagrees_with_the_row_is_refused(self) -> None:
        verdict = S.classify_shape(row("other_marker"), snapshot=SNAPSHOT)
        assert not verdict.ok and verdict.reason == "journal-disagrees"

    def test_a_non_canonical_restore_is_refused(self) -> None:
        link = P.JournalLink(2, "phase3:x", "P3/site_type", "Megalith-ish", "suspect_modern")
        verdict = S.classify_shape(row(journal=(link,)), snapshot={WITHAM: "Megalith-ish"})
        assert not verdict.ok and verdict.reason == "restore-not-canonical"

    def test_a_restore_the_boot_normaliser_would_rewrite_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(S, "normalize_site_type", lambda value: "Settlement")
        verdict = S.classify_shape(row(), snapshot=SNAPSHOT)
        assert not verdict.ok and verdict.reason == "restore-not-a-fixed-point"

    def test_a_site_missing_from_the_snapshot_is_refused(self) -> None:
        verdict = S.classify_shape(row(), snapshot={})
        assert not verdict.ok and verdict.reason == "not-in-snapshot"

    def test_a_snapshot_that_disagrees_with_the_journal_is_refused(self) -> None:
        verdict = S.classify_shape(row(), snapshot={WITHAM: "Monument"})
        assert not verdict.ok and verdict.reason == "snapshot-disagrees"

    def test_a_row_of_another_source_is_refused(self) -> None:
        verdict = S.classify_shape(row(source_id="lyra"), snapshot=SNAPSHOT)
        assert not verdict.ok and verdict.reason == "row-not-in-curated-source"

    def test_a_row_without_a_type_is_refused(self) -> None:
        verdict = S.classify_shape(row(None, journal=()), snapshot=SNAPSHOT)
        assert not verdict.ok and verdict.reason == "no-site-type"


class TestBuildShapePlan:
    def test_changes_review_and_refusals_are_disjoint(self) -> None:
        treasury = P.JournalLink(3, "phase3:y", "P3/site_type", "Megalithic structures", "Treasury")
        rows = [
            row(),
            S.Row(
                WITHAM.replace("c5", "d5", 1),
                "Boeotian Treasury",
                P.CURATED_SOURCE,
                "Treasury",
                (treasury,),
            ),
            S.Row(
                WITHAM.replace("c5", "e5", 1), "Mookambika", P.CURATED_SOURCE, "suspect_modern", ()
            ),
        ]
        result = S.build_shape_plan(rows, snapshot=SNAPSHOT, built_at="2026-09-22T00:00:00+00:00")
        assert [c.site_name for c in result.plan.changes] == ["Witham Shield"]
        assert [r.site_name for r in result.review] == ["Boeotian Treasury"]
        assert [s.site_name for s in result.plan.skipped] == ["Mookambika"]
        assert result.counters["rule:restore-marker-token"] == 1
        assert result.plan.lane is L.SITE_TYPE_SHAPE


class TestTheLane:
    def test_the_lane_owns_the_canonical_types(self) -> None:
        assert L.SITE_TYPE_SHAPE.allowed_new_values == tuple(CANONICAL_TYPES)
        assert L.SITE_TYPE_SHAPE.premise_sql is None

    def test_the_statement_writes_site_type_under_its_own_identity(self) -> None:
        record = A.ChangeRecord(
            site_id=WITHAM,
            site_name="Witham Shield",
            old_value="suspect_modern",
            new_value="City/town/settlement",
            rule="restore-marker-token",
            condition="",
            reason="site-type-shape: x",
            evidence=({"source": "test", "quote": "x"},),
        )
        sql = A.render_transaction([record], site_ids={WITHAM}, lane=L.SITE_TYPE_SHAPE)
        assert "'unified_sites', 'site_type', 'id', r.site_id::text," in sql
        assert f"'site-type-shape:{WITHAM}'" in sql and "'P6/site-type-shape'" in sql
        assert "scope guard 4" in sql and "scope guard 5" not in sql
        with pytest.raises(P.PlanError, match="is not a value the site-type-shape lane owns"):
            A.validate_records(
                [A.ChangeRecord(**{**record.__dict__, "new_value": "Treasury"})],
                lane=L.SITE_TYPE_SHAPE,
            )

    def test_the_readback_names_the_run_and_the_residual(self) -> None:
        readback = A.READBACKS[L.SITE_TYPE_SHAPE.name]
        assert f"'{L.SITE_TYPE_SHAPE.run_stamp}'" in readback
        assert L.SITE_TYPE_SHAPE.post_commit_residual.predicate in readback


@needs_plan
class TestTheDeliveredPlan:
    def test_three_restores_of_phase3_writes(self) -> None:
        records = A.load_records(DELIVERED)
        A.validate_records(records, lane=L.SITE_TYPE_SHAPE)
        assert len(records) == 3
        assert all(r.phase3 for r in records)
        assert all(S.not_a_type(r.old_value) for r in records)
        assert all(r.new_value in CANONICAL_TYPES for r in records)
        assert {r.new_value for r in records} == {
            "Monument",
            "Necropolis/tombs complex",
            "City/town/settlement",
        }

    def test_every_record_names_its_journal_row_and_the_snapshot(self) -> None:
        for line in DELIVERED.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            sources = [e["source"] for e in payload["evidence"]]
            assert any(re.match(r"remediation_change_log:\d+$", s) for s in sources)
            assert any(s.startswith("output/remediation/snapshot/") for s in sources)
            assert payload["run_stamp"] == L.SITE_TYPE_SHAPE.run_stamp

    def test_the_rollback_reverses_every_row(self) -> None:
        records = A.load_records(DELIVERED)
        rollback = (DELIVERED.parent / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert f"'{L.SITE_TYPE_SHAPE.rollback_run_stamp}'" in rollback
        for r in records:
            assert f"{P.sql_literal(r.new_value)}, {P.sql_literal(r.old_value)}" in rollback
