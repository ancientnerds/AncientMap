"""The phase-3 question texts are frozen, and this file is what makes "frozen" a fact.

`AUDIT_LOG.md` records the discover question as frozen at round 5: every answer of the mass run - 24,255
of them - was bought with exactly these words, and the search lane (block A3) reruns the finder on the
undecided fields with *more evidence*, never with a different question. A reworded question would mix
two conventions into one answer store and make the rerun's verdicts incomparable with the ones it
completes. Until 2026-09-22 nothing enforced that rule: no test pinned the texts, and the CI prompt
guard covers only `pipeline/lyra/prompts/*.txt`.

**A failure here is a stop sign, not a chore.** It means a question the audit's answers were bought
with has changed. The fix is to revert the wording. Updating a hash below to make this file green is
the one edit it exists to prevent; a genuinely new question needs a new run directory, a new answer
store and a decision recorded in `AUDIT_LOG.md` - and then a new pin, with that decision cited here.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402

#: sha256 of the UTF-8 bytes, measured 2026-09-22 on commit 7fbc646 (the code the mass run used).
FROZEN = {
    "discover_stage.QUESTION_TEMPLATE": (
        "82ef29e2db82bbbc05631a0dc100f62e410b4cc7fd95d8531572c3ec4e482633"
    ),
    "discover_stage.FIELD_CLAUSE": (
        "988d0d9ab751767b5b79be8cce7f4cb63b201ead6d8ff78c94509646af1896fa"
    ),
    "model_stage.REVIEWER_QUESTION": (
        "5c79d977e73f354c2a35fdb48ef759e82fa20979bf1df1651ec7e621d10c790b"
    ),
    "model_stage.PARTIAL_EVIDENCE_NOTE": (
        "8c5bfd52b929a834303c79a99067162c01c972287f5b560b9001d89123ee31fe"
    ),
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _texts() -> dict[str, str]:
    return {
        "discover_stage.QUESTION_TEMPLATE": DS.QUESTION_TEMPLATE,
        # The clauses are one dict; sorted keys make its bytes independent of insertion order, so
        # only a change of a word (or of a field) moves the hash.
        "discover_stage.FIELD_CLAUSE": json.dumps(DS.FIELD_CLAUSE, sort_keys=True),
        "model_stage.REVIEWER_QUESTION": MS.REVIEWER_QUESTION,
        "model_stage.PARTIAL_EVIDENCE_NOTE": MS.PARTIAL_EVIDENCE_NOTE,
    }


def test_the_question_texts_are_byte_identical_to_the_ones_the_mass_run_was_asked_with() -> None:
    measured = {name: _sha256(text) for name, text in _texts().items()}
    changed = sorted(name for name, digest in FROZEN.items() if measured[name] != digest)
    assert not changed, (
        f"frozen question text changed: {changed}. Revert the wording - see this module's "
        "docstring before touching a hash"
    )


def test_the_pin_covers_every_frozen_text_and_is_not_trivially_satisfied() -> None:
    """A pin over an empty string, or over one text twice, would pass without pinning anything."""
    texts = _texts()
    assert set(texts) == set(FROZEN)
    assert all(len(text) > 200 for text in texts.values())
    assert len(set(FROZEN.values())) == len(FROZEN)
