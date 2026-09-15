# SPDX-License-Identifier: AGPL-3.0-only
"""Structural guarantees of the proposals review API (no DB).

- Every human decision on a proposal that came from the radar backlog is
  mirrored onto its user_contributions row, so the radar tab never shows a
  card the founder already decided in the proposals queue.
- A candidate name enters unified_site_names only on a human decision
  (approve / merge / same-as), never from the pipeline.
- Reject mirrors as 'dismissed', not 'rejected' — the radar pipeline
  re-processes 'rejected' rows and would resurrect the card.
"""

import inspect

from api.routes import proposals
from pipeline.lyra.site_key import site_key_sql


def test_approve_mirrors_promoted_and_writes_aliases():
    src = inspect.getsource(proposals.approve_proposal)
    assert 'enrichment_status="promoted"' in src
    assert "_insert_alias(db, site_id, alias)" in src


def test_merge_into_site_mirrors_matched():
    src = inspect.getsource(proposals.merge_proposal)
    assert 'enrichment_status="matched"' in src


def test_reject_mirrors_dismissed_never_rejected():
    src = inspect.getsource(proposals.reject_proposal)
    assert 'enrichment_status="dismissed"' in src
    assert 'enrichment_status="rejected"' not in src


def test_same_as_moves_evidence_and_closes_the_other_card():
    src = inspect.getsource(proposals.same_as)
    assert "INSERT INTO site_proposal_evidence" in src
    assert "DELETE FROM site_proposal_evidence WHERE proposal_id = :gone" in src
    assert '"merged"' in src
    assert "merged_into_proposal" in src


def test_alias_insert_uses_the_db_key():
    src = inspect.getsource(proposals._insert_alias)
    assert 'site_key_sql(":name")' in src  # computed in SQL, never a Python key
    assert "'alias'" in src
    assert site_key_sql(":name") == "left(lower(unaccent(:name)), 500)"


def test_pipeline_never_writes_aliases():
    """Only a founder decision (same-as) may fill site_proposals.aliases."""
    from pipeline.lyra.prospector import pipeline, propose

    for module in (propose, pipeline):
        src = inspect.getsource(module)
        assert '"aliases"' not in src, module.__name__  # no column write in any field dict
        assert "aliases =" not in src, module.__name__
        assert "SET aliases" not in src, module.__name__


def test_queue_demotes_prior_machine_verdicts():
    assert "(p.prior_verdict IS NOT NULL) ASC" in proposals._ORDER
