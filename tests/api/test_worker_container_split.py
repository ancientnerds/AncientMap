# SPDX-License-Identifier: AGPL-3.0-only
"""The research worker owns its own container (2026-08-08).

It used to run as a background task inside the API process, so every API
rebuild killed the run in flight — twice on 2026-08-07, each costing a
multi-hour paper and ~9% of the weekly token budget. These tests pin the
three pieces that keep the split honest; break any one of them and either
two workers race for the same queue, or deploys resume murdering runs.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]


def _compose() -> dict:
    return yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


class TestComposeWiring:
    def test_worker_service_runs_the_worker_entrypoint(self):
        svc = _compose()["services"]["theo-worker"]
        assert svc["command"] == ["python", "scripts/run_theo_worker.py"]
        # Same image as the API: the worker imports api.services.* .
        assert svc["build"]["dockerfile"] == "Dockerfile"

    def test_api_does_not_run_a_second_worker(self):
        """Both loops claiming the same queued rows would double-spend credits."""
        api_env = _compose()["services"]["api"]["environment"]
        assert str(api_env["THEO_WORKER_EXTERNAL"]) == "1"

    def test_worker_reaches_the_services_a_run_needs(self):
        svc = _compose()["services"]["theo-worker"]
        env = svc["environment"]
        assert env["POSTGRES_HOST"] == "db"
        assert env["QDRANT_HOST"] == "qdrant"  # paper indexing
        assert env["REDIS_URL"].startswith("redis://redis")
        assert set(svc["depends_on"]) == {"db", "redis", "qdrant"}


class TestApiRespectsTheFlag:
    def test_lifespan_skips_the_worker_when_external(self):
        main_src = (_ROOT / "api" / "main.py").read_text(encoding="utf-8")
        assert 'os.environ.get("THEO_WORKER_EXTERNAL") == "1"' in main_src
        # The guard must sit before the start call, not after it.
        guard = main_src.index("THEO_WORKER_EXTERNAL")
        start = main_src.index("start_worker as _start_theo")
        assert guard < start


class TestDeploySkipsBusyWorker:
    def test_deploy_checks_for_running_research(self):
        ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "THEO_BUSY=" in ci
        assert "WHERE status = 'running'" in ci

    def test_missing_container_is_created_even_while_busy(self):
        """Otherwise the first deploy after the split leaves Theo with no
        worker at all: the API stopped running one, and the busy-check would
        skip creating the container."""
        ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "THEO_EXISTS=" in ci
        assert 'if [ -z "$THEO_EXISTS" ]; then' in ci

    def test_unknown_busy_state_is_treated_as_busy(self):
        """Fail-safe: if the DB check errors it yields 'unknown', which must
        NOT equal the '0' that permits a rebuild."""
        ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert 'echo "unknown"' in ci
        assert '[ "$THEO_BUSY" = "0" ]' in ci
