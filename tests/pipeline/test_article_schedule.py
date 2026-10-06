"""The journal runs Monday 06:00 UTC and covers the week that just ended.

Moved off Sunday 20:00 UTC on 2026-09-13: the MiniMax weekly budget resets
Monday 00:00 UTC, so the Sunday slot ran on the week's leftovers (1% that day)
and a quota trough there silently skipped a whole journal — the Sunday-only
window closes at midnight and nothing retries it.

The pairing is what matters: firing on Monday while still computing the
*current* week would write a journal about the six hours since midnight.

Since 2026-10-06 the window stays open for JOURNAL_GRACE_HOURS (48 h) instead of
closing on Monday night. A run takes hours and every deploy kills it, so a
Monday-only window loses the week whenever the last attempt dies after midnight
— on 2026-10-05 the 06:41 UTC deploy on Tuesday killed attempt 4 of 3 and no
fourth try ever happened. What stops the retries is the attempt budget in
journal_attempts, not the hour.
"""

from datetime import UTC, date, datetime, timedelta

from pipeline.lyra.article_generator import (
    JOURNAL_GRACE_HOURS,
    _get_completed_week_range,
    journal_slot,
    journal_week_key,
    should_generate_article,
)


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

    def test_tuesday_morning_still_fires(self):
        # The 2026-10-05 run died at 06:41 UTC on Tuesday. Under the old
        # Monday-only window that ended the week.
        assert should_generate_article(datetime(2026, 9, 15, 7, 0, tzinfo=UTC))

    def test_window_closes_after_the_grace_hours(self):
        slot = journal_slot(datetime(2026, 9, 14, 6, 0, tzinfo=UTC))
        assert should_generate_article(slot + timedelta(hours=JOURNAL_GRACE_HOURS - 1))
        assert not should_generate_article(slot + timedelta(hours=JOURNAL_GRACE_HOURS))

    def test_friday_does_not_fire(self):
        # Still inside the calendar week, but past the grace hours.
        assert not should_generate_article(datetime(2026, 9, 18, 6, 0, tzinfo=UTC))

    def test_next_monday_reopens_the_window(self):
        assert should_generate_article(datetime(2026, 9, 21, 6, 0, tzinfo=UTC))


class TestJournalSlotAndWeekKey:
    def test_slot_is_this_monday_six(self):
        assert journal_slot(datetime(2026, 9, 16, 13, 37, tzinfo=UTC)) == datetime(
            2026, 9, 14, 6, 0, tzinfo=UTC
        )

    def test_week_key_is_the_covered_week_not_the_run_week(self):
        # Run on Monday 2026-09-14 → writes about the week of 09-07. A Tuesday
        # retry must spend the SAME budget, so the key must not move.
        assert journal_week_key(datetime(2026, 9, 14, 6, 0, tzinfo=UTC)) == date(2026, 9, 7)
        assert journal_week_key(datetime(2026, 9, 15, 9, 0, tzinfo=UTC)) == date(2026, 9, 7)


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
