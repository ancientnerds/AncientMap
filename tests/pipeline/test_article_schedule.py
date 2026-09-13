"""The journal runs Monday 06:00 UTC and covers the week that just ended.

Moved off Sunday 20:00 UTC on 2026-09-13: the MiniMax weekly budget resets
Monday 00:00 UTC, so the Sunday slot ran on the week's leftovers (1% that day)
and a quota trough there silently skipped a whole journal — the Sunday-only
window closes at midnight and nothing retries it.

The pairing is what matters: firing on Monday while still computing the
*current* week would write a journal about the six hours since midnight.
"""

from datetime import UTC, datetime

from pipeline.lyra.article_generator import _get_completed_week_range, should_generate_article


class TestShouldGenerateArticle:
    def test_monday_six_utc_fires(self):
        assert should_generate_article(datetime(2026, 9, 14, 6, 0, tzinfo=UTC))

    def test_monday_before_six_waits(self):
        # 00:00-06:00 is the quota-reset settling window: Theo's last weekend
        # run may still be crossing the reset on the fresh budget.
        assert not should_generate_article(datetime(2026, 9, 14, 5, 59, tzinfo=UTC))

    def test_window_stays_open_all_monday(self):
        assert should_generate_article(datetime(2026, 9, 14, 23, 59, tzinfo=UTC))

    def test_old_sunday_slot_no_longer_fires(self):
        assert not should_generate_article(datetime(2026, 9, 13, 20, 0, tzinfo=UTC))

    def test_other_days_do_not_fire(self):
        for day in range(15, 20):  # Tue-Sat
            assert not should_generate_article(datetime(2026, 9, day, 6, 0, tzinfo=UTC))


class TestCompletedWeekRange:
    def test_monday_run_covers_previous_week(self):
        start, end = _get_completed_week_range(datetime(2026, 9, 14, 6, 0, tzinfo=UTC))
        assert start == datetime(2026, 9, 7, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2026, 9, 13, 23, 59, 59, tzinfo=UTC)

    def test_range_is_stable_across_the_whole_monday(self):
        early = _get_completed_week_range(datetime(2026, 9, 14, 6, 0, tzinfo=UTC))
        late = _get_completed_week_range(datetime(2026, 9, 14, 23, 30, tzinfo=UTC))
        assert early == late

    def test_sunday_items_are_inside_the_range(self):
        # The old Sunday 20:00 trigger cut off the last four hours of the week.
        _, end = _get_completed_week_range(datetime(2026, 9, 14, 6, 0, tzinfo=UTC))
        assert end > datetime(2026, 9, 13, 22, 0, tzinfo=UTC)

    def test_covered_weeks_do_not_overlap_or_gap(self):
        this_week = _get_completed_week_range(datetime(2026, 9, 14, 6, 0, tzinfo=UTC))
        next_week = _get_completed_week_range(datetime(2026, 9, 21, 6, 0, tzinfo=UTC))
        assert (next_week[0] - this_week[1]).total_seconds() == 1
