"""Tests for the 6h batch-pacing gate in api.services.theo_worker.

Batch tasks (is_batch=TRUE) may start at most once per THEO_MIN_TASK_INTERVAL_S,
measured start-to-start against the most recent started_at of ANY task. UI
submissions bypass the gate entirely — that routing lives in the claim SQL; the
pure open/closed decision lives in _batch_gate_open and is tested here.
"""

from api.services import theo_worker as tw
from api.services.theo_config import DEFERRED_MAX_AGE_HOURS, THEO_MIN_TASK_INTERVAL_S


def test_gate_open_when_no_prior_start():
    """First-ever task: nothing has started yet, gate must be open."""
    assert tw._batch_gate_open(None, 21600) is True


def test_gate_closed_when_last_start_younger_than_interval():
    assert tw._batch_gate_open(21599.0, 21600) is False


def test_gate_open_at_exact_interval():
    assert tw._batch_gate_open(21600.0, 21600) is True


def test_gate_open_when_last_start_much_older():
    assert tw._batch_gate_open(100000.0, 21600) is True


def test_default_interval_is_six_hours():
    assert THEO_MIN_TASK_INTERVAL_S == 6 * 3600


def test_deferred_max_age_survives_at_least_two_pacing_slots():
    """A quota-deferred batch row must not be reaped by cleanup_stale_deferred
    before the pacing gate can possibly grant it a retry slot (plus headroom
    for a weekly-quota trough)."""
    assert DEFERRED_MAX_AGE_HOURS * 3600 >= 2 * THEO_MIN_TASK_INTERVAL_S
