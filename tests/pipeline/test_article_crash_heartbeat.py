"""A crashed journal run must leave its error in the heartbeat.

Nothing else did: _write_article_heartbeat writes status="ok" unconditionally
and never touches last_error, so a run that died mid-week left a row that said
"ok" until the next deploy. On 2026-10-05 three attempts died in
_cluster_related_items and the fourth was killed by the 06:41 UTC deploy — the
dashboard showed a healthy pipeline for the whole time.
"""

import pytest

from pipeline.lyra import article_generator as ag


def _fake_settings() -> ag.LyraSettings:
    return ag.LyraSettings(minimax_api_key="k", model_cluster="m")


class TestCrashLeavesAHeartbeat:
    def test_a_crash_is_recorded_before_it_propagates(self, monkeypatch):
        written: list[tuple[dict, float, str | None]] = []

        def boom(*args, **kwargs):
            raise RuntimeError("clustering exploded")

        monkeypatch.setattr(ag, "_generate_weekly_article", boom)
        monkeypatch.setattr(
            ag,
            "_write_final_heartbeat",
            lambda step_data, t0, error=None: written.append((step_data, t0, error)),
        )

        with pytest.raises(RuntimeError, match="clustering exploded"):
            ag.generate_weekly_article(_fake_settings())

        assert len(written) == 1
        assert written[0][2] == "RuntimeError: clustering exploded"

    def test_the_caller_still_sees_the_exception(self, monkeypatch):
        # The orchestrator counts on the exception to log it and skip the run;
        # swallowing it here would hide the failure twice over.
        def boom(*args, **kwargs):
            raise ValueError("nope")

        monkeypatch.setattr(ag, "_generate_weekly_article", boom)
        monkeypatch.setattr(ag, "_write_final_heartbeat", lambda *a, **k: None)

        with pytest.raises(ValueError):
            ag.generate_weekly_article(_fake_settings())

    def test_a_clean_run_writes_no_error(self, monkeypatch):
        written: list[str | None] = []

        monkeypatch.setattr(ag, "_generate_weekly_article", lambda *a, **k: False)
        monkeypatch.setattr(
            ag, "_write_final_heartbeat", lambda step_data, t0, error=None: written.append(error)
        )

        assert ag.generate_weekly_article(_fake_settings()) is False
        assert written == []
