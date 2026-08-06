# SPDX-License-Identifier: AGPL-3.0-only
"""Radar review endpoint guards (mocked DB via dependency overrides — no PG)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.jwt_auth import require_founder
from pipeline.database import get_db

# Needs the local Postgres/Redis containers (TestClient startup connects) —
# skipped by the DB-less CI test job (audit P3-13, 2026-08-06).
pytestmark = pytest.mark.integration


class FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping
        for k, v in mapping.items():
            setattr(self, k, v)


ENRICHED_ITEM = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Test Site",
    "corrected_name": None,
    "source": "lyra",
    "enrichment_status": "enriched",
    "promoted_site_id": None,
    "enrichment_data": None,
    "lat": None,  # missing core field
    "lon": None,
    "country": "Turkey",
    "site_type": "settlement",
    "period_name": None,
    "period_start": None,
    "period_end": None,
    "description": "A sufficiently long description for the core fields gate to accept.",
    "wikipedia_url": None,
    "thumbnail_url": None,
    "wikidata_id": None,
}


@pytest.fixture
def founder_client():
    session = MagicMock()
    app.dependency_overrides[require_founder] = lambda: SimpleNamespace(username="tester")
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()


class TestPromoteGuards:
    def test_unknown_contribution_404(self, founder_client):
        client, session = founder_client
        session.execute.return_value.fetchone.return_value = None
        resp = client.post("/api/radar/nope/promote")
        assert resp.status_code == 404

    def test_wrong_status_409(self, founder_client):
        client, session = founder_client
        row = FakeRow({**ENRICHED_ITEM, "enrichment_status": "pending"})
        session.execute.return_value.fetchone.return_value = row
        resp = client.post("/api/radar/x/promote")
        assert resp.status_code == 409
        assert "pending" in resp.json()["detail"]

    def test_already_promoted_409(self, founder_client):
        client, session = founder_client
        row = FakeRow({**ENRICHED_ITEM, "promoted_site_id": "22222222-2222-2222-2222-222222222222"})
        session.execute.return_value.fetchone.return_value = row
        resp = client.post("/api/radar/x/promote")
        assert resp.status_code == 409

    def test_missing_core_fields_422_lists_missing(self, founder_client):
        client, session = founder_client
        session.execute.return_value.fetchone.return_value = FakeRow(ENRICHED_ITEM)
        resp = client.post("/api/radar/x/promote")
        assert resp.status_code == 422
        assert resp.json()["detail"]["missing"] == ["coordinates"]

    def test_overrides_fill_missing_field_passes_gate(self, founder_client):
        # With lat/lon supplied as overrides the gate must pass — request then
        # proceeds into (mocked) inserts, so we assert it's not a 4xx gate error.
        client, session = founder_client
        session.execute.return_value.fetchone.return_value = FakeRow(ENRICHED_ITEM)
        resp = client.post("/api/radar/x/promote", json={"lat": 37.2, "lon": 38.9})
        assert resp.status_code == 200

    def test_invalid_coordinates_rejected_by_validation(self, founder_client):
        client, session = founder_client
        session.execute.return_value.fetchone.return_value = FakeRow(ENRICHED_ITEM)
        resp = client.post("/api/radar/x/promote", json={"lat": 137.2, "lon": 38.9})
        assert resp.status_code == 422


class TestDismissGuards:
    def test_unknown_404(self, founder_client):
        client, session = founder_client
        session.execute.return_value.fetchone.return_value = None
        resp = client.post("/api/radar/nope/dismiss")
        assert resp.status_code == 404

    def test_wrong_status_409(self, founder_client):
        client, session = founder_client
        row = FakeRow({"enrichment_status": "promoted", "enrichment_data": None})
        session.execute.return_value.fetchone.return_value = row
        resp = client.post("/api/radar/x/dismiss")
        assert resp.status_code == 409


class TestMergeGuards:
    def test_target_site_not_found_404(self, founder_client):
        client, session = founder_client
        contrib_result = MagicMock()
        contrib_result.fetchone.return_value = FakeRow(
            {
                "name": "X",
                "corrected_name": None,
                "enrichment_status": "enriched",
                "enrichment_data": None,
            }
        )
        site_result = MagicMock()
        site_result.fetchone.return_value = None
        session.execute.side_effect = [contrib_result, site_result]
        resp = client.post("/api/radar/x/merge", json={"site_id": "y"})
        assert resp.status_code == 404
        assert "Target site" in resp.json()["detail"]

    def test_wrong_status_409(self, founder_client):
        client, session = founder_client
        contrib_result = MagicMock()
        contrib_result.fetchone.return_value = FakeRow(
            {
                "name": "X",
                "corrected_name": None,
                "enrichment_status": "matched",
                "enrichment_data": None,
            }
        )
        session.execute.side_effect = [contrib_result]
        resp = client.post("/api/radar/x/merge", json={"site_id": "y"})
        assert resp.status_code == 409
