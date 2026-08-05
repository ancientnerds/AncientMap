"""Injector root-cause fix — reference nodes promote to frontier on collision
(2026-08-04, quality-review finding).

Before this fix, `ON CONFLICT (kind, norm_label) DO UPDATE` only accumulated
`source_signal` and never touched `status`. Because the full-project ingest
wrote ALL 5,307 site nodes as status='reference', an injected site
(Epic/Legendary via inject_from_sites, radar via inject_from_radar) collided
with its reference row and stayed 'reference' forever — 0 of 5,307 site
nodes were ever researchable, and the graph-miner's bridged population
(graph_miner.py, spec §2) could never grow. This locks the fix at the
SQL-statement level: there is no local DB to exercise ON CONFLICT against,
so text assertions on the INSERT statement are the right granularity here
(same pattern as tests/pipeline/test_thinking_log.py's fake session).
"""

from types import SimpleNamespace

from pipeline.lyra.graph_injectors import _insert_frontier


class _FakeInjectorSession:
    """Captures the executed statement; .execute(...).fetchone() is configurable."""

    def __init__(self, is_new=True):
        self.executed = []
        self._is_new = is_new

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        is_new = self._is_new

        class _R:
            def fetchone(inner):
                return SimpleNamespace(is_new=is_new)

        return _R()


def test_insert_frontier_promotes_reference_to_frontier_only():
    session = _FakeInjectorSession()
    _insert_frontier(session, "Nan Madol", "site", 2.0, kind="site", site_id="abc")
    stmt, params = session.executed[0]
    assert "WHEN research_nodes.status = 'reference' THEN 'frontier'" in stmt
    assert "ELSE research_nodes.status" in stmt  # frontier/researching/explored untouched


def test_insert_frontier_coalesces_site_id_without_overwriting():
    session = _FakeInjectorSession()
    _insert_frontier(session, "Nan Madol", "site", 2.0, kind="site", site_id="abc")
    stmt, params = session.executed[0]
    assert "site_id = COALESCE(research_nodes.site_id, excluded.site_id)" in stmt


def test_insert_frontier_still_accumulates_source_signal():
    session = _FakeInjectorSession()
    _insert_frontier(session, "Nan Madol", "site", 2.0, kind="site", site_id="abc")
    stmt, params = session.executed[0]
    assert "research_nodes.source_signal + excluded.source_signal" in stmt


def test_insert_frontier_caps_accumulated_signal_at_500():
    # Follow-up-Ticket 2: unbounded accumulation hit source_signal 1180+ on
    # the live graph (+120/day) — LEAST(..., 500.0) bounds the top while
    # leaving ordering among moderate signals intact.
    session = _FakeInjectorSession()
    _insert_frontier(session, "Nan Madol", "site", 2.0, kind="site", site_id="abc")
    stmt, params = session.executed[0]
    assert "source_signal = LEAST(" in stmt
    assert "research_nodes.source_signal + excluded.source_signal, 500.0" in stmt


def test_insert_frontier_returns_is_new_flag():
    session_new = _FakeInjectorSession(is_new=True)
    assert _insert_frontier(session_new, "Some Site", "story", 1.0) is True

    session_existing = _FakeInjectorSession(is_new=False)
    assert _insert_frontier(session_existing, "Some Site", "story", 1.0) is False


def test_insert_frontier_rejects_junk_and_short_labels_without_hitting_sql():
    session = _FakeInjectorSession()
    assert _insert_frontier(session, "null", "story", 1.0) is False
    assert _insert_frontier(session, "abc", "story", 1.0) is False  # < 4 chars
    assert session.executed == []  # rejected labels never reach the DB
