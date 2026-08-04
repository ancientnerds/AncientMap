"""Feeder wiring — the nightly thinking pass fires Mon–Thu only (spec §3)."""

from datetime import UTC, datetime

from pipeline.lyra.curator import thinking_pass_due


def test_weekend_nights_never_think():
    # Fri–Sun nights belong to the research runs (weekend batch gate).
    for day in (7, 8, 9):  # Fri, Sat, Sun 2026-08
        assert thinking_pass_due(datetime(2026, 8, day, 3, 0, tzinfo=UTC), None) is False
