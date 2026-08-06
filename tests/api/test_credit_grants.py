"""Unit tests for the monthly-grant cycle logic (audit finding M4, 2026-08-06).

Covers the P14 lifecycle scenarios for the pure helpers — no DB required:
join, active subscription, cancel+rejoin in the same calendar month
(the collision that used to swallow the rejoiner's grant), and repeated
rejoins. `process_credit_grants` itself is exercised against prod via the
CreditGrant unique constraint; these tests pin the decision logic.
"""

from datetime import UTC, datetime

from api.routes.auth import get_eligible_periods, resolve_monthly_grant_period


class TestGetEligiblePeriods:
    def test_fresh_anchor_yields_current_period(self):
        anchor = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
        now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
        assert get_eligible_periods(anchor, now) == ["2026-08"]

    def test_next_period_only_after_anniversary_day(self):
        anchor = datetime(2026, 7, 15, tzinfo=UTC)
        before = datetime(2026, 8, 14, tzinfo=UTC)
        after = datetime(2026, 8, 15, tzinfo=UTC)
        assert get_eligible_periods(anchor, before) == ["2026-07"]
        assert get_eligible_periods(anchor, after) == ["2026-07", "2026-08"]

    def test_accumulation_capped_at_three(self):
        anchor = datetime(2026, 1, 10, tzinfo=UTC)
        now = datetime(2026, 8, 10, tzinfo=UTC)
        periods = get_eligible_periods(anchor, now)
        assert len(periods) == 3
        assert periods == ["2026-06", "2026-07", "2026-08"]

    def test_month_end_anchor_clamps_in_february(self):
        anchor = datetime(2026, 1, 31, tzinfo=UTC)
        feb_27 = datetime(2026, 2, 27, tzinfo=UTC)
        feb_28 = datetime(2026, 2, 28, tzinfo=UTC)
        assert get_eligible_periods(anchor, feb_27) == ["2026-01"]
        assert get_eligible_periods(anchor, feb_28) == ["2026-01", "2026-02"]


class TestResolveMonthlyGrantPeriod:
    ANCHOR = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)

    def test_no_existing_rows_grants_plain_period(self):
        assert resolve_monthly_grant_period("2026-08", self.ANCHOR, []) == "2026-08"

    def test_active_subscription_not_double_granted(self):
        # Grant created AFTER the anchor = same subscription cycle → skip.
        created = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
        assert resolve_monthly_grant_period("2026-08", self.ANCHOR, [created]) is None

    def test_rejoin_same_month_gets_suffixed_period(self):
        # Grant from the PREVIOUS cycle (created before the reset anchor):
        # the rejoiner paid again and must receive a fresh grant.
        old = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
        assert resolve_monthly_grant_period("2026-08", self.ANCHOR, [old]) == "2026-08.1"

    def test_second_rejoin_same_month_increments_suffix(self):
        older = datetime(2026, 8, 3, tzinfo=UTC)
        old = datetime(2026, 8, 12, tzinfo=UTC)
        assert resolve_monthly_grant_period("2026-08", self.ANCHOR, [older, old]) == "2026-08.2"

    def test_naive_db_datetimes_are_treated_as_utc(self):
        # created_at comes back naive from the DB (timestamp without tz).
        old_naive = datetime(2026, 8, 3, 9, 0)
        current_naive = datetime(2026, 8, 21, 9, 0)
        assert resolve_monthly_grant_period("2026-08", self.ANCHOR, [old_naive]) == "2026-08.1"
        assert resolve_monthly_grant_period("2026-08", self.ANCHOR, [current_naive]) is None

    def test_naive_anchor_is_treated_as_utc(self):
        naive_anchor = datetime(2026, 8, 20, 10, 0)
        old = datetime(2026, 8, 3, tzinfo=UTC)
        assert resolve_monthly_grant_period("2026-08", naive_anchor, [old]) == "2026-08.1"
