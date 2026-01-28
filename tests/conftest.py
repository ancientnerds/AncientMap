# SPDX-License-Identifier: MIT
"""Pytest configuration and fixtures for Ancient Nerds Map tests."""

import os
import pytest
from typing import Generator

# Set test environment variables before importing app
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TURNSTILE_SECRET_KEY", "test-secret")


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
