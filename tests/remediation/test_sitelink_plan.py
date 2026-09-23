"""The sitelink lane's plan builder (`output/remediation/tools/sitelink_plan.py`): which UNVERIFIABLE
fields are still open, which item a site is given, which of its other-language articles are read,
and the records the fetch stage buys them through.

No test here reads production, Pi or the network: the mass run, the export, the census and every
lookup answer are small fabricated files and fetchers in the shape the real ones had on 2026-09-23.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

REPO = Path(__file__).resolve().parents[2]
for path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import gap_plan as G  # noqa: E402
import lanes  # noqa: E402
import qid_repair  # noqa: E402
import sitelink_plan as SL  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402

A = "aaaaaaaa-0000-4000-8000-00000000000a"
B = "aaaaaaaa-0000-4000-8000-00000000000b"


def _wave3(rule: str, name: str | None = None) -> qid_repair.Site:
    return next(
        site
        for site in qid_repair.WAVE3_SITES
        if site.rule == rule and (name is None or site.name == name)
    )


# ── the item a site is given ──────────────────────────────────────────────────────────────────


def test_every_wave_of_the_reviewed_repair_is_read() -> None:
    ids = [site.site_id for site in SL.REPAIRS]
    assert len(ids) == len(set(ids))
    for wave in qid_repair.WAVES.values():
        assert set(wave.sites) <= set(SL.REPAIRS), wave.number


def test_a_link_wave_three_found_right_is_given_although_the_classifier_suspected_it() -> None:
    """Psychro Cave's Q1643807 met Q2 (shared) until wave 2 repaired the Idaean Cave; wave 3's
    research reads it as right, and that verdict is the answer to the classifier's suspicion."""
    right = _wave3("link-right", "Psychro Cave")
    suspect = {right.site_id: (right.old_qid, "Q2")}
    assert SL.item_for(right.site_id, right.old_qid, shared={}, suspect=suspect) == (
        right.old_qid,
        None,
    )


def test_a_suspect_link_no_wave_answered_stays_withheld() -> None:
    suspect = {A: ("Q42", "Q1")}
    kept, why = SL.item_for(A, "Q42", shared={}, suspect=suspect)
    assert kept is None and "marks this link suspect (Q1" in str(why)
    # a suspicion about another item than the one production carries now says nothing about it
    assert SL.item_for(A, "Q43", shared={}, suspect=suspect) == ("Q43", None)


def test_a_type_link_and_a_duplicate_of_wave_three_are_withheld_by_the_repair() -> None:
    keep_type = _wave3("keep-type", "Nuraghes of Sardinia")
    suspect = {keep_type.site_id: (keep_type.old_qid, "Q1")}
    kept, why = SL.item_for(keep_type.site_id, keep_type.old_qid, shared={}, suspect=suspect)
    assert kept is None and "a type the record stands for" in str(why)
    duplicate = _wave3("duplicate-candidate")
    kept, why = SL.item_for(duplicate.site_id, duplicate.old_qid, shared={}, suspect={})
    assert kept is None and "duplicate candidate" in str(why)
