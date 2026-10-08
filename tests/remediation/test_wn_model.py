"""Lane N's provenance record (`model4.WebProvenance`, owner decision "Neu aus Webquellen",
2026-10-01): strict, the new AI system's disclosure, read by `provenance_from_dict` by its lane,
never an assignment of the Phase-4 router, and the writer's check record for a text with no old text.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation",):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402

DIGEST = M.text_sha256("A text.")


def test_the_record_is_exactly_its_six_keys_and_round_trips() -> None:
    record = M.WebProvenance(desc_sha256=DIGEST, ai_system=M.AI_SYSTEM)
    data = record.to_dict()
    assert data == {
        "v": 1, "lane": "N", "ai": "generated", "ai_system": M.AI_SYSTEM,
        "basis": M.WEB_BASIS, "desc_sha256": DIGEST,
    }  # fmt: skip
    assert M.WebProvenance.from_dict(data) == record
    assert M.provenance_from_dict(data) == record
    assert "claims" not in M.WEB_BASIS and "web pages" in M.WEB_BASIS


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"lane": "L"}, "is not N"),
        ({"ai": "selected"}, "is not generated"),
        ({"ai_system": "someone else"}, "ai_system"),
        ({"ai_system": M.AI_SYSTEM + " "}, "ai_system"),  # a member of AI_SYSTEMS byte for byte
        ({"basis": M.LEGACY_BASIS}, "basis"),
        ({"v": 2}, "version"),
        ({"desc_sha256": "x"}, "desc_sha256"),
    ],
)
def test_every_field_of_the_record_is_held(change: dict, message: str) -> None:
    data = {**M.WebProvenance(desc_sha256=DIGEST, ai_system=M.AI_SYSTEM).to_dict(), **change}
    with pytest.raises(ValueError, match=message):
        M.WebProvenance.from_dict(data)


@pytest.mark.parametrize("system", sorted(M.AI_SYSTEMS))
def test_every_disclosure_a_validator_accepts_is_a_valid_web_disclosure(system: str) -> None:
    """Owner decision D6 (2026-10-08): the record checks membership in `AI_SYSTEMS`, not equality
    with `AI_SYSTEM`, so a Claude-only write (`AI_SYSTEM_CLAUDE_HAIKU`) validates and so do the 17+
    WN provenances in production, which carry the combined string."""
    record = M.WebProvenance(desc_sha256=DIGEST, ai_system=system)
    assert M.WebProvenance.from_dict(record.to_dict()) == record


def test_an_unknown_or_missing_key_is_refused() -> None:
    data = M.WebProvenance(desc_sha256=DIGEST, ai_system=M.AI_SYSTEM).to_dict()
    with pytest.raises(ValueError):
        M.WebProvenance.from_dict({**data, "card": None})
    with pytest.raises(ValueError):
        M.WebProvenance.from_dict({k: v for k, v in data.items() if k != "basis"})


def test_the_dispatch_by_lane_reads_each_shape_and_lane_n_is_never_assigned() -> None:
    legacy = M.LegacyProvenance(desc_sha256=DIGEST).to_dict()
    assert isinstance(M.provenance_from_dict(legacy), M.LegacyProvenance)
    assert isinstance(M.provenance_from_dict(M.WebProvenance(desc_sha256=DIGEST, ai_system=M.AI_SYSTEM).to_dict()),
                      M.WebProvenance)  # fmt: skip
    assert M.Lane.N not in M.ASSIGNED_LANES and M.Lane.N not in M.LANE_AI
    assert M.Lane.N not in M.LANE_CHANGES  # no attribution: not a full lane (cli.FULL_LANES)
    with pytest.raises(ValueError, match="expected a JSON object"):
        M.provenance_from_dict("N")


def test_a_site_without_a_description_has_the_empty_text_as_its_checked_hash() -> None:
    """The check record of a text lane WN wrote hashes the empty text as `checked`: there was no
    stored text to check (a blank stored value is hashed as it was stored)."""
    assert WC4.is_empty(None) and WC4.is_empty("") and WC4.is_empty(" \n") and not WC4.is_empty("x")
