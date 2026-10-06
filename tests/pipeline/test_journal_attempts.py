"""The journal's attempt budget lives in the database, not in the orchestrator's memory.

On 2026-10-05 the journal for the week of 2026-09-28 never appeared: eight
deploys that Monday each restarted the container, each restart reset the
in-memory counter to "attempt 1/3", and the 06:41 UTC deploy on Tuesday killed
the run that had reached 13 of 14 clusters. The counter is a row now, so a
restart continues the budget instead of refunding it.
"""

from datetime import UTC, date, datetime, timedelta

from pipeline.lyra import journal_attempts as ja


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """Enough of a connection for claim_attempt/finish_week to run unchanged."""

    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, stmt, params=None):
        params = params or {}
        sql = str(stmt).lstrip().upper()
        if sql.startswith("SELECT"):
            return _Result(self._db.rows.get(params.get("week_start")))
        if "max_attempts" in params:  # finish_week
            self._db.rows[params["week_start"]] = (params["max_attempts"], self._db.now)
        else:  # claim_attempt
            previous = self._db.rows.get(params["week_start"], (0, None))
            self._db.rows[params["week_start"]] = (previous[0] + 1, self._db.now)
        return _Result(None)

    def commit(self):
        return None


class FakeDB:
    """A container restart is a new connection over the same rows."""

    def __init__(self, now):
        self.rows: dict[date, tuple[int, datetime | None]] = {}
        self.now = now

    def connect(self):
        return _FakeConn(self)


MONDAY = date(2026, 9, 7)
SLOT = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)


class TestMayAttempt:
    def test_first_attempt_is_allowed(self):
        assert ja.may_attempt(0, None, SLOT)

    def test_budget_is_finite(self):
        assert ja.may_attempt(ja.MAX_ATTEMPTS - 1, None, SLOT)
        assert not ja.may_attempt(ja.MAX_ATTEMPTS, None, SLOT)
        assert not ja.may_attempt(ja.MAX_ATTEMPTS + 1, None, SLOT)

    def test_spacing_between_two_attempts(self):
        just_inside = SLOT - timedelta(seconds=ja.RETRY_INTERVAL_S - 1)
        exactly_enough = SLOT - timedelta(seconds=ja.RETRY_INTERVAL_S)
        assert not ja.may_attempt(1, just_inside, SLOT)
        assert ja.may_attempt(1, exactly_enough, SLOT)


class TestClaimAttempt:
    def test_claims_and_counts(self):
        db = FakeDB(SLOT)
        assert ja.claim_attempt(MONDAY, now=SLOT, connect=db.connect)
        assert ja.spent_attempts(MONDAY, connect=db.connect) == 1

    def test_fourth_attempt_is_refused(self):
        db = FakeDB(SLOT)
        for attempt in range(ja.MAX_ATTEMPTS):
            db.now = SLOT + timedelta(hours=attempt * 2)
            assert ja.claim_attempt(MONDAY, now=db.now, connect=db.connect)
        db.now = SLOT + timedelta(days=1)
        assert not ja.claim_attempt(MONDAY, now=db.now, connect=db.connect)
        assert ja.spent_attempts(MONDAY, connect=db.connect) == ja.MAX_ATTEMPTS

    def test_a_restart_does_not_refund_the_budget(self):
        # The 2026-10-05 property: every claim opens its own connection — the
        # restart is the new object, the rows are what survives. The budget must
        # keep counting instead of starting over at attempt 1.
        db = FakeDB(SLOT)
        for expected in range(1, ja.MAX_ATTEMPTS + 1):
            db.now = SLOT + timedelta(hours=expected * 3)
            assert ja.claim_attempt(MONDAY, now=db.now, connect=db.connect)
            assert ja.spent_attempts(MONDAY, connect=db.connect) == expected
        db.now = SLOT + timedelta(hours=48)
        assert not ja.claim_attempt(MONDAY, now=db.now, connect=db.connect)

    def test_a_crash_still_costs_its_attempt(self):
        # The attempt is spent BEFORE the run, so a run killed mid-flight has
        # already counted against the week — and the retry that follows is
        # attempt 2, not a fresh budget.
        db = FakeDB(SLOT)
        ja.claim_attempt(MONDAY, now=SLOT, connect=db.connect)  # ... and then it crashed

        assert ja.spent_attempts(MONDAY, connect=db.connect) == 1
        db.now = SLOT + timedelta(hours=2)
        assert ja.claim_attempt(MONDAY, now=db.now, connect=db.connect)
        assert ja.spent_attempts(MONDAY, connect=db.connect) == 2

    def test_each_week_has_its_own_budget(self):
        db = FakeDB(SLOT)
        for attempt in range(ja.MAX_ATTEMPTS):
            db.now = SLOT + timedelta(hours=attempt * 2)
            ja.claim_attempt(MONDAY, now=db.now, connect=db.connect)
        assert ja.spent_attempts(MONDAY, connect=db.connect) == ja.MAX_ATTEMPTS
        assert ja.spent_attempts(date(2026, 9, 14), connect=db.connect) == 0

    def test_last_attempt_at_is_recorded(self):
        db = FakeDB(SLOT)
        ja.claim_attempt(MONDAY, now=SLOT, connect=db.connect)
        assert ja.last_attempt_at(MONDAY, connect=db.connect) == SLOT


class TestFinishWeek:
    def test_a_written_journal_spends_the_rest_of_the_budget(self):
        db = FakeDB(SLOT)
        ja.claim_attempt(MONDAY, now=SLOT, connect=db.connect)
        ja.finish_week(MONDAY, connect=db.connect)

        # Without this the loop would keep claiming attempts of a week whose
        # journal is already in the database.
        db.now = SLOT + timedelta(hours=1)
        assert not ja.claim_attempt(MONDAY, now=db.now, connect=db.connect)


class TestRefusalIsLoggedOnce:
    """The orchestrator asks every 60 s. A spent budget said so every 60 s too,
    until it filled the log for two days (seen 2026-10-06, 22:20-23:00 UTC)."""

    def test_a_spent_budget_is_announced_once_per_process(self, monkeypatch, caplog):
        monkeypatch.setattr(ja, "_spent_budget_logged", set())
        db = FakeDB(SLOT)
        db.rows[MONDAY] = (ja.MAX_ATTEMPTS, SLOT)

        with caplog.at_level("INFO"):
            for minute in range(1, 61):
                assert not ja.claim_attempt(
                    MONDAY, now=SLOT + timedelta(minutes=minute), connect=db.connect
                )

        announced = [r for r in caplog.records if "budget" in r.message]
        assert len(announced) == 1
        assert str(MONDAY) in announced[0].message

    def test_the_retry_spacing_is_not_announced_at_all(self, monkeypatch, caplog):
        monkeypatch.setattr(ja, "_spent_budget_logged", set())
        db = FakeDB(SLOT)
        ja.claim_attempt(MONDAY, now=SLOT, connect=db.connect)

        with caplog.at_level("INFO"):
            # Ten minutes later: inside the 30-minute spacing.
            assert not ja.claim_attempt(
                MONDAY, now=SLOT + timedelta(minutes=10), connect=db.connect
            )

        assert [r for r in caplog.records if "retry spacing" in r.message] == []
        assert [r for r in caplog.records if r.levelname == "INFO"] == []

    def test_a_new_process_announces_it_again(self, monkeypatch):
        # A restart is the moment where the owner looks, so it repeats itself.
        monkeypatch.setattr(ja, "_spent_budget_logged", set())
        db = FakeDB(SLOT)
        db.rows[MONDAY] = (ja.MAX_ATTEMPTS, SLOT)

        assert not ja.claim_attempt(MONDAY, now=SLOT, connect=db.connect)
        assert MONDAY in ja._spent_budget_logged


class TestBudgetSurvivesADeployDay:
    def test_three_attempts_were_not_enough_on_2026_10_06(self):
        # Measured that evening: three deploys between 19:00 and 22:20 UTC, each
        # killing a run and spending an attempt, and the week had none left.
        assert ja.MAX_ATTEMPTS > 3
