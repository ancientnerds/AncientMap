"""The census checks. One module per check, one question per module.

Contract (see `census/run.py`):

    TEST_ID, NAME, DIMENSION       metadata for the report
    applies_to(site, ctx) -> bool  optional; which sites this check covers
    collect(ctx) -> None           optional; the ONLY part allowed to touch the network
    run(ctx) -> list[Finding]      the check itself, pure over snapshot + cache

Rules that hold for every module here:

* Never invent data. An unmappable value becomes `Proposal.REVIEW`, not a guess.
* Network failures raise. Reporting "no findings" because a request failed turns
  "could not check" into "checked and clean", which is the one thing this census
  must never do.
* Every proposed value must survive the producers that run on container restart
  (`pipeline/lyra/orchestrator.py::_run_migrations`, `api/main.py` startup). A fix
  that a reboot silently reverts is not a fix - see `t04_site_type` for the invariant
  that enforces this for `site_type`.
"""
