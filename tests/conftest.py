# SPDX-License-Identifier: AGPL-3.0-only
"""Pytest configuration and fixtures for Ancient Nerds Map tests."""

import os
from collections.abc import Generator

import pytest

# Set test environment variables before importing app
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TURNSTILE_SECRET_KEY", "test-secret")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_limiter_pacing: opt out of the pacing stub — for tests that "
        "assert the limiter's own delay/concurrency values",
    )


@pytest.fixture(autouse=True)
def _no_llm_pacing(request):
    """Neutralize MiniMax rate-limiter pacing for the whole test suite.

    The limiter enforces real wall-clock delays (0.5s base, 60s crawl lane,
    freeze windows). Against mocked LLM clients that is pure dead time: the
    first CI run of the backend-tests job (2026-08-06) blew the 90s
    per-test timeout on 20 dispatch tests that pass in milliseconds locally
    when a .env happens to disable crawl pacing. Env vars alone can't fix
    this reliably — the pacing lives in module/instance state — so the
    suite pins it to zero and restores afterwards.
    """
    if request.node.get_closest_marker("real_limiter_pacing"):
        yield
        return

    from pipeline.lyra import minimax_limiter as ml

    saved_crawl = ml._crawl_delay_s
    saved = (ml.limiter._base_delay, ml.limiter._max_delay, ml.limiter._current_delay)
    ml._crawl_delay_s = 0.0
    ml.limiter._base_delay = 0.0
    ml.limiter._max_delay = 0.0
    ml.limiter._current_delay = 0.0
    ml.limiter._frozen_until = 0.0
    try:
        yield
    finally:
        ml._crawl_delay_s = saved_crawl
        ml.limiter._base_delay, ml.limiter._max_delay, ml.limiter._current_delay = saved


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Use asyncio for async tests."""
    return "asyncio"


@pytest.fixture
def test_client() -> Generator:
    """Create a test client for the FastAPI application."""
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def async_client():
    """Create an async test client for async tests."""
    import httpx

    from api.main import app

    return httpx.AsyncClient(app=app, base_url="http://test")


@pytest.fixture
def mock_db_session(mocker):
    """Mock database session for tests that don't need real DB."""
    mock_session = mocker.MagicMock()
    mocker.patch("pipeline.database.get_db", return_value=mock_session)
    return mock_session


@pytest.fixture
def sample_site_data() -> dict:
    """Sample site data for testing."""
    return {
        "id": "test-site-001",
        "name": "Test Archaeological Site",
        "lat": 41.8902,
        "lon": 12.4922,
        "source_id": "test_source",
        "site_type": "settlement",
        "period_start": -500,
        "period_end": 500,
        "period_name": "500 BC - 1 AD",
        "country": "Italy",
        "description": "A test archaeological site for unit testing.",
    }


@pytest.fixture
def sample_sites_list(sample_site_data: dict) -> list:
    """List of sample sites for testing."""
    return [
        sample_site_data,
        {
            **sample_site_data,
            "id": "test-site-002",
            "name": "Second Test Site",
            "lat": 37.9715,
            "lon": 23.7267,
            "country": "Greece",
        },
        {
            **sample_site_data,
            "id": "test-site-003",
            "name": "Third Test Site",
            "lat": 29.9792,
            "lon": 31.1342,
            "country": "Egypt",
        },
    ]
