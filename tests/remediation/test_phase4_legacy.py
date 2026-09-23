"""Lane L (WB-D3): does held March-LLM text get truthful 'generated' provenance, and nothing else?

The rule (design entry [6], production_write row group L and licensing_and_ai_act): a held site
whose description differs from the pre-March snapshot `d4526691` gets `_description_provenance
{v:1, lane:'L', ai:'generated', ...}`; one whose text equals the snapshot gets no claim and is listed
for HUMAN_ONLY; so does a site with no description. A site Phase 4 wrote is not touched, and a
provenance that is already there is never overwritten. The mutation cases are in
`scripts/remediation/phase3/mutation_sweep.py` (`PHASE4_WRITE_MUTATIONS`, "p4 legacy4").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from phase4 import legacy4 as L  # noqa: E402

from tests.remediation import phase4_write_fixtures as FX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4, M  # noqa: E402

#: production_write, row group L - the literals are the design's, not the module's.
LEGACY_AI_SYSTEM = "2026-03 enrichment chain (LLM; model per site not recorded)"
LEGACY_BASIS = "description differs from pre-March snapshot d4526691 (plan section 15.3)"


def test_a_held_text_that_differs_from_the_snapshot_is_marked_generated() -> None:
    site = FX.plan_site(description="The March chain's text.", snapshot="The older text.")
    legacy = L.legacy_provenance(site)
    assert legacy is not None
    assert legacy.to_dict() == {
        "v": 1,
        "lane": "L",
        "ai": "generated",
        "ai_system": LEGACY_AI_SYSTEM,
        "basis": LEGACY_BASIS,
        "desc_sha256": M.text_sha256("The March chain's text."),
    }


def test_a_text_the_snapshot_holds_as_null_was_written_after_it() -> None:
    """The site is in d4526691 with no description there: the text it carries now was written
    after the snapshot, which is the claim's basis."""
    site = FX.plan_site(description="Added in March.", snapshot=None, in_snapshot=True)
    assert L.legacy_provenance(site) is not None and L.no_claim_reason(site) is None


def test_a_site_the_snapshot_does_not_have_gets_no_claim_and_is_listed() -> None:
    """A site created after 2026-03-04 is not in d4526691 at all (8 curated sites, 7 of them from
    2026-04-24): there is nothing to compare its text with, so nothing proves the March chain wrote
    it - it gets no claim, under its own reason, never the 'differs from the snapshot' basis."""
    site = FX.plan_site(description="Added in April.", snapshot=None, in_snapshot=False)
    assert L.legacy_provenance(site) is None
    assert L.no_claim_reason(site) is L.NoClaim.NOT_IN_SNAPSHOT
    assert L.unclaimed([site]) == [L.Unclaimed(FX.SITE_A, FX.TITLE, L.NoClaim.NOT_IN_SNAPSHOT)]


def test_a_site_the_snapshot_does_not_have_and_without_text_has_nothing_to_mark() -> None:
    site = FX.plan_site(description=None, snapshot=None, in_snapshot=False)
    assert L.no_claim_reason(site) is L.NoClaim.NO_DESCRIPTION


def test_a_held_text_equal_to_the_snapshot_gets_no_claim_and_is_listed() -> None:
    site = FX.plan_site(description="The same text.", snapshot="The same text.")
    assert L.legacy_provenance(site) is None
    assert L.no_claim_reason(site) is L.NoClaim.SAME_AS_SNAPSHOT
    assert L.unclaimed([site]) == [L.Unclaimed(FX.SITE_A, FX.TITLE, L.NoClaim.SAME_AS_SNAPSHOT)]


def test_a_site_without_a_description_has_nothing_to_mark() -> None:
    site = FX.plan_site(description=None, snapshot=None)
    assert L.legacy_provenance(site) is None
    assert L.no_claim_reason(site) is L.NoClaim.NO_DESCRIPTION


def test_the_held_set_is_every_plan_site_production_does_not_show_as_written() -> None:
    sites = [FX.plan_site(), FX.plan_site(FX.SITE_B), FX.plan_site(FX.SITE_C)]
    held = L.held_sites(sites, written=[FX.SITE_B])
    assert [site.site_id for site in held] == [FX.SITE_A, FX.SITE_C]


def _batch(tmp_path: Path, sites, holds=()):
    return W4.load_batch(
        FX.write_batch(
            tmp_path,
            sites=sites,
            holds=list(holds)
            or [
                M.Hold(
                    site_id=s.site_id,
                    scope=M.HoldScope.SITE,
                    reason=M.HoldReason.NO_SOURCE,
                    detail="lane 0",
                )
                for s in sites
            ],
        )
    )


def test_the_l_rows_add_the_provenance_and_leave_every_other_key(tmp_path: Path) -> None:
    site = FX.plan_site(raw_data={"description_citations": [{"n": 1}], "title_es": "x"})
    plan = W4.plan_legacy(_batch(tmp_path, [site]), written=[])
    (row,) = plan.rows
    assert (row.column, row.test_id, row.group) == ("raw_data", "P4/legacy-provenance", W4.Group.L)
    assert row.change_key.startswith("phase4l:")
    new = json.loads(row.new_value)
    assert new["description_citations"] == [{"n": 1}] and new["title_es"] == "x"
    assert new[M.PROVENANCE_KEY]["lane"] == "L" and new[M.PROVENANCE_KEY]["ai"] == "generated"
    assert (
        row.evidence["snapshot"] == "d4526691" and row.evidence["holds"][0]["reason"] == "no-source"
    )
    assert plan.batch_id == "p4l-0003"


def test_a_site_phase4_wrote_is_not_touched(tmp_path: Path) -> None:
    plan = W4.plan_legacy(_batch(tmp_path, [FX.plan_site()]), written=[FX.SITE_A])
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_WRITTEN


def test_an_unprovable_text_is_refused_and_listed_for_human_only(tmp_path: Path) -> None:
    site = FX.plan_site(description="Same.", snapshot="Same.")
    plan = W4.plan_legacy(_batch(tmp_path, [site]), written=[])
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_NO_CLAIM
    assert [u.reason for u in plan.unclaimed] == [L.NoClaim.SAME_AS_SNAPSHOT]


def test_a_site_absent_from_the_snapshot_is_refused_and_listed_for_human_only(
    tmp_path: Path,
) -> None:
    site = FX.plan_site(description="Added in April.", snapshot=None, in_snapshot=False)
    plan = W4.plan_legacy(_batch(tmp_path, [site]), written=[])
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_NO_CLAIM
    assert [u.reason for u in plan.unclaimed] == [L.NoClaim.NOT_IN_SNAPSHOT]
    assert "not-in-snapshot" in plan.refusals[0].detail


def test_a_provenance_that_is_already_there_is_never_overwritten(tmp_path: Path) -> None:
    marked = FX.plan_site(raw_data={M.PROVENANCE_KEY: {"lane": "L"}})
    plan = W4.plan_legacy(_batch(tmp_path, [marked]), written=[])
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_MARKED


def test_an_l_row_is_written_and_holds_the_description_invariant(tmp_path: Path) -> None:
    plan = W4.plan_legacy(_batch(tmp_path, [FX.plan_site()]), written=[])
    chunk = W4.chunk_for(plan)
    out = tmp_path / "apply" / plan.batch_id
    W4.write_plan_files(out, plan, chunk)
    db = FX.FakeDb({FX.SITE_A: FX.Site(raw_data=json.loads(json.dumps(FX.OLD_RAW)))})
    outcome = W4.apply_chunk(chunk, out=out, rehearse=False, runner=db)
    assert outcome.ok and db.journal[0]["run_stamp"] == "phase4l:p4l-0003:chunk-0001"
    assert db.sites[FX.SITE_A].raw_data[M.PROVENANCE_KEY]["desc_sha256"] == M.text_sha256(
        FX.OLD_DESCRIPTION
    )
