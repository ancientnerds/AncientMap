"""Regression: the convergence orchestrator must fail (not "complete") a run
whose assembled paper is empty/near-empty.

2026-06-16 incident: a run hit MiniMax Token-Plan exhaustion (429) during the
writing stages, returned an 89-char paper, and the worker saved it as
`completed` at quality 73. The empty-paper guard converts that to a failure
with an actionable reason so credits are released and the user sees WHY.
"""

from __future__ import annotations

from pipeline.lyra.convergence_orchestrator import (
    _MIN_PUBLISHABLE_PAPER_CHARS,
    _empty_paper_error,
)


def test_real_paper_passes() -> None:
    assert _empty_paper_error("x" * (_MIN_PUBLISHABLE_PAPER_CHARS + 1)) is None


def test_empty_paper_fails() -> None:
    reason = _empty_paper_error("")
    assert reason is not None
    assert "0 chars" in reason


def test_none_paper_fails() -> None:
    assert _empty_paper_error(None) is not None


def test_whitespace_only_fails() -> None:
    # The 89-char "paper" was effectively a stub; whitespace must not pass either.
    assert _empty_paper_error("   \n\t  ") is not None


def test_stub_paper_below_threshold_fails() -> None:
    reason = _empty_paper_error("Stonehenge is old." * 5)  # ~90 chars
    assert reason is not None
    assert str(_MIN_PUBLISHABLE_PAPER_CHARS) in reason
