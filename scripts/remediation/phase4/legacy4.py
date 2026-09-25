"""Lane L: truthful 'generated' provenance for the held sites whose text the March LLM chain wrote.

Design entry [6], production_write, row group L, and licensing_and_ai_act ("Legacy lane L"). Work
item WB-D3. A site Phase 4 does not write keeps its stored description. Where that description
differs from the one in the pre-March snapshot `d4526691`, the March enrichment chain (an LLM, model
per site not recorded) wrote it, and it must not stay live unmarked: its `raw_data` gains
`_description_provenance` `{v:1, lane:'L', ai:'generated', ...}` (`model4.LegacyProvenance`),
which the API and the pages render as the existing AI footnote. The held sites are every curated
site whose description Phase 4 did not write - inside the owner's defect scope or not (owner
decision 2026-09-24, "Alle kennzeichnen": Phases 4/5 write only the defect scope, and every March
text outside it stays live, so it is marked like any other).

Where the held description is byte for byte the snapshot's, nothing proves where it came from, so
nothing is claimed: the site gets no row and is listed for `HUMAN_ONLY.md` (the closing report counts
them). The same holds for a site the snapshot does not have at all (`PlanSite.in_snapshot` false: 8
curated sites were created after 2026-03-04, 7 of them on 2026-04-24): its text has nothing to
differ from, and claiming the March chain for a site that did not exist then would be a false
disclosure. A held site without a description has no text to mark. Each is listed under its own
reason, so the counts never merge.

This module decides; `phase4/write4.py` turns a decision into a journalled row (test_id
`P4/legacy-provenance`, change-key lane `phase4l`) and renders the transaction. Pure: no file, no
database.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase4 import model4 as M  # noqa: E402

#: The snapshot the comparison is made against (plan section 15.3): the last commit before the
#: March enrichment chain rewrote the descriptions.
SNAPSHOT = "d4526691"

#: Lane L's own plan (`plan4.py legacy`, owner decision 2026-09-24): every curated site of one
#: read-only production read, not a Phase-4 run's batches. Each of its batches carries this in its
#: `pass` field - a P4 plan's batches carry none, so one is never read as the other - and they are
#: numbered from `FIRST_BATCH`: past every P4 plan batch (the unscoped plan ends at p4-0334, the
#: scoped mass run at p4-0115), so no L write batch (`p4l-NNNN`) or journal stamp names a P4 plan
#: batch or a per-run L plan rendered before the decision.
PLAN_MARK = "phase4-legacy"
FIRST_BATCH = 1001


class NoClaim(StrEnum):
    """Why a held site gets no legacy provenance. Each is listed for HUMAN_ONLY, never written."""

    SAME_AS_SNAPSHOT = "same-as-snapshot"  #: the text is the pre-March one: no provable origin
    NOT_IN_SNAPSHOT = "not-in-snapshot"  #: created after d4526691: nothing to compare with
    NO_DESCRIPTION = "no-description"  #: nothing is published, so there is nothing to mark


def legacy_provenance(site: M.PlanSite) -> M.LegacyProvenance | None:
    """The lane-L provenance of one held site, or `None` when no claim can be made.

    `None` when the stored description equals the snapshot's (no claim: its origin is unprovable),
    when the site is not in the snapshot at all (nothing to compare with), or when there is no
    stored description (nothing to mark); `no_claim_reason` says which. A description that differs
    from the snapshot's - including a text where the snapshot's row holds none - was written after
    it, by the March chain, and is marked 'generated'.
    """
    text = site.description
    if text is None or not site.in_snapshot or text == site.snapshot_description:
        return None
    return M.LegacyProvenance(desc_sha256=M.text_sha256(text))


def no_claim_reason(site: M.PlanSite) -> NoClaim | None:
    """Why `legacy_provenance` makes no claim for this site, or `None` when it makes one. Derived
    from `legacy_provenance` itself, so the list and the rows cannot disagree about a site."""
    if site.description is None:
        return NoClaim.NO_DESCRIPTION
    if legacy_provenance(site) is None:
        return NoClaim.SAME_AS_SNAPSHOT if site.in_snapshot else NoClaim.NOT_IN_SNAPSHOT
    return None


@dataclass(frozen=True)
class Unclaimed:
    """One held site that gets no legacy provenance, and why: a line of the HUMAN_ONLY list."""

    site_id: str
    name: str
    reason: NoClaim


def held_sites(sites: Iterable[M.PlanSite], *, written: Iterable[str]) -> list[M.PlanSite]:
    """The plan's sites that Phase 4 did not write, in plan order.

    `written` is what production says, not what a local file says: the site ids whose `raw_data`
    carries a full (W/S/T/R) provenance (`write_gate4.written_sites`). A site a revert took back is
    held again, which is exactly what its description then is.
    """
    done = set(written)
    return [site for site in sites if site.site_id not in done]


def unclaimed(sites: Iterable[M.PlanSite]) -> list[Unclaimed]:
    """The held sites `legacy_provenance` makes no claim for, with the reason, in plan order."""
    listed: list[Unclaimed] = []
    for site in sites:
        reason = no_claim_reason(site)
        if reason is not None:
            listed.append(Unclaimed(site_id=site.site_id, name=site.name, reason=reason))
    return listed
