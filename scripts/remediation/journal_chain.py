"""The journal chain of one field: its `remediation_change_log` rows, oldest first.

Every production write of the remediation goes through `apply_remediation_change()`, which journals
the value it replaced and the value it wrote. Read in id order, the rows of one
`(table, column, row)` form a chain, and the chain is only an account of the field while each link
starts where the one before it ended. Two places judge that:

* the mechanical planners (`mechanical/plan.py:journal_break`), before they plan a write on top of
  an earlier one;
* the phase-3 acceptance (`output/remediation/tools/verify_writes.py`), after the writes.

Both use `first_break` below, so the two cannot drift into judging the same chain differently.

`ROLLBACK_SUFFIX` is how every writer names a reversal's run stamp: the write's stamp plus this
suffix (`phase3/write_stage.py:ROLLBACK_KEY_SUFFIX`, `mechanical/lane.py:Lane.rollback_run_stamp`;
the agreement is pinned in `tests/remediation/test_journal_chain.py`).

Standard library only; imported with `scripts/remediation` on `sys.path`.
"""

from __future__ import annotations

from collections.abc import Sequence

ROLLBACK_SUFFIX = "-rollback"


def is_rollback(stamp: str) -> bool:
    """Whether a run stamp names a reversal rather than a write."""
    return stamp.endswith(ROLLBACK_SUFFIX)


def first_break(transitions: Sequence[tuple[object, object]]) -> int | None:
    """The index of the first `(old, new)` link that does not start where the one before it ended.

    `None` when the chain is continuous (an empty or one-link chain always is). The caller reads the
    two links at `index - 1` and `index` to say what broke.
    """
    for index in range(1, len(transitions)):
        if transitions[index][0] != transitions[index - 1][1]:
            return index
    return None
