"""The prospector is wired into the Lyra orchestrator as a daily step."""

from pipeline.lyra import orchestrator
from pipeline.lyra.prospector import run_daily


def test_prospect_step_is_registered_daily():
    module, func, needs_settings, desc = orchestrator.STEPS["prospect"]
    assert (module, func) == ("pipeline.lyra.prospector", "run_daily")
    assert needs_settings is False  # run_daily takes no settings argument
    assert "{n}" in desc
    assert "prospect" in orchestrator.STEP_ORDER
    assert orchestrator.STEP_INTERVALS["prospect"] == 24
    assert "prospect" in orchestrator.STEP_GROUPS["radar"]


def test_run_daily_takes_no_arguments():
    import inspect

    assert list(inspect.signature(run_daily).parameters) == []
