"""Migration 0025: the journal of every write the Claude publish path makes."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATH = REPO / "migrations" / "0025_theo_paper_publications.sql"


def _flat() -> str:
    return " ".join(PATH.read_text(encoding="utf-8").split())


def test_it_is_forward_only_and_idempotent():
    sql = PATH.read_text(encoding="utf-8")
    assert sql.lstrip().startswith("-- 0025_theo_paper_publications.sql")
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "CREATE TABLE IF NOT EXISTS theo_paper_publications" in sql


def test_journal_rows_outlive_their_paper():
    assert "request_id UUID REFERENCES research_requests (id) ON DELETE SET NULL" in _flat()


def test_action_vocabulary_hash_shape_and_required_columns():
    flat = _flat()
    assert "CHECK (action IN ('publish', 'correct', 'register_video'))" in flat
    assert "CHECK (bundle_sha256 ~ '^[0-9a-f]{64}$')" in flat
    assert "writer JSONB NOT NULL" in flat
    assert "gates JSONB NOT NULL" in flat
    assert "side_effects JSONB," in flat


def test_artifact_reads_get_their_index():
    flat = _flat()
    assert (
        "CREATE INDEX IF NOT EXISTS idx_research_artifacts_request_kind_created "
        "ON research_artifacts (request_id, kind, created_at DESC)"
    ) in flat


def test_no_other_migration_claims_the_number():
    assert [p.name for p in (REPO / "migrations").glob("0025_*.sql")] == [PATH.name]
