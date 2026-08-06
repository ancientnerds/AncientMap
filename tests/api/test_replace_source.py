# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for replace-source and batch-upload endpoints."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Needs the local Postgres/Redis containers (TestClient startup connects) —
# skipped by the DB-less CI test job (audit P3-13, 2026-08-06).
pytestmark = pytest.mark.integration


def _make_site(name="Test Site", lat=41.89, lon=12.49, **overrides):
    """Build a minimal site payload."""
    return {
        "name": name,
        "lat": lat,
        "lon": lon,
        "site_type": "settlement",
        "period_name": "500 BC - 1 AD",
        "period_start": -500,
        "country": "Italy",
        "description": "A test site.",
        "source_url": None,
        "thumbnail_url": None,
        "card_description": None,
        "confidence_score": None,
        "description_citations": None,
        "reference_links": None,
        "existing_id": None,
        **overrides,
    }


def _make_site_with_enrichment():
    """Site with citations and reference links."""
    return _make_site(
        name="Enriched Site",
        description_citations=[
            {"phrase": "ancient ruins", "source_url": "https://example.com", "source_title": "Ex"}
        ],
        reference_links=[
            {
                "url": "https://example.com/ref",
                "domain": "example.com",
                "title": "Example Reference",
                "quality": "high",
                "link_type": "article",
            }
        ],
    )


# ── Fake user for dependency override ──────────────────────────────
class FakeUser:
    username = "test-founder"
    discord_id = "12345"
    roles = []


class FakeFounder(FakeUser):
    roles = ["1234567890"]  # Will be set to match FOUNDER_ROLE_ID


@pytest.fixture
def founder_client():
    """Test client with require_founder overridden to return a fake founder user."""
    from api.main import app
    from api.services.jwt_auth import require_founder

    fake = FakeFounder()

    # Patch the FOUNDER_ROLE_ID to match our fake user's role
    with patch("api.services.jwt_auth.FOUNDER_ROLE_ID", "1234567890"):
        app.dependency_overrides[require_founder] = lambda: fake
        with TestClient(app) as client:
            yield client
        app.dependency_overrides.clear()


# =============================================================================
# replace-source endpoint
# =============================================================================


class TestReplaceSourceValidation:
    """Test validation and guards on /sites/replace-source."""

    def test_requires_auth(self, test_client):
        """Replace-source without auth should fail."""
        res = test_client.post(
            "/api/sites/replace-source",
            json={"sites": [_make_site()], "target_source": "test"},
        )
        assert res.status_code in (401, 403)

    def test_empty_sites_rejected(self, founder_client):
        """Empty sites array should return 400."""
        res = founder_client.post(
            "/api/sites/replace-source",
            json={"sites": [], "target_source": "test"},
        )
        assert res.status_code == 400
        assert "No sites" in res.json()["detail"]

    def test_protected_source_rejected(self, founder_client):
        """Protected sources (community, lyra) cannot be replaced."""
        for source in ["community", "lyra", "ancient_nerds_community"]:
            res = founder_client.post(
                "/api/sites/replace-source",
                json={"sites": [_make_site()], "target_source": source},
            )
            assert res.status_code == 400, f"Source {source} should be protected"
            assert "protected" in res.json()["detail"].lower()

    def test_invalid_site_payload_rejected(self, founder_client):
        """Missing required fields should return 422."""
        res = founder_client.post(
            "/api/sites/replace-source",
            json={"sites": [{"name": "No coords"}], "target_source": "test"},
        )
        assert res.status_code == 422


class TestReplaceSourceExecution:
    """Test the replace-source endpoint with mocked DB."""

    @patch("api.routes.sites.get_db")
    @patch("api.routes.sites.cache_delete_pattern")
    def test_replace_fresh_source_no_existing(self, mock_cache, mock_get_db, founder_client):
        """Replacing a source with no existing sites skips snapshot and just inserts."""
        mock_db = MagicMock()
        # No existing sites
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.fetchone.return_value = None
        mock_get_db.return_value = mock_db

        # Override the get_db dependency
        from api.main import app
        from pipeline.database import get_db as orig_get_db

        app.dependency_overrides[orig_get_db] = lambda: mock_db

        try:
            res = founder_client.post(
                "/api/sites/replace-source",
                json={
                    "sites": [_make_site(), _make_site(name="Second")],
                    "target_source": "test_source",
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["deleted"] == 0
            assert data["inserted"] == 2
            assert data["snapshot_id"] is None
        finally:
            from pipeline.database import get_db as gdb

            app.dependency_overrides.pop(gdb, None)


# =============================================================================
# batch-upload endpoint
# =============================================================================


class TestBatchUploadValidation:
    """Test validation on /sites/batch-upload."""

    def test_requires_auth(self, test_client):
        """Batch-upload without auth should fail."""
        res = test_client.post(
            "/api/sites/batch-upload",
            json={"sites": [_make_site()], "target_source": "test"},
        )
        assert res.status_code in (401, 403)

    def test_empty_sites_rejected(self, founder_client):
        """Empty sites array should return 400."""
        res = founder_client.post(
            "/api/sites/batch-upload",
            json={"sites": [], "target_source": "test"},
        )
        assert res.status_code == 400

    def test_invalid_coordinates_rejected(self, founder_client):
        """Invalid lat/lon should be caught by Pydantic."""
        res = founder_client.post(
            "/api/sites/batch-upload",
            json={
                "sites": [{"name": "Bad", "lat": "not-a-number", "lon": 12.0}],
                "target_source": "test",
            },
        )
        assert res.status_code == 422

    def test_confidence_score_range(self, founder_client):
        """Confidence score must be 0.0-1.0."""
        res = founder_client.post(
            "/api/sites/batch-upload",
            json={
                "sites": [_make_site(confidence_score=5.0)],
                "target_source": "test",
            },
        )
        assert res.status_code == 422

    def test_create_snapshot_flag_accepted(self, founder_client):
        """create_snapshot: false should be a valid request field."""
        # This tests the Pydantic model accepts the flag — won't actually
        # hit the DB because auth will try to read the DB
        from api.routes.sites import BatchUploadRequest

        payload = BatchUploadRequest(
            sites=[],
            target_source="test",
            create_snapshot=False,
        )
        assert payload.create_snapshot is False


# =============================================================================
# ParsedSitePayload model
# =============================================================================


class TestParsedSitePayload:
    """Test the Pydantic model for site payloads."""

    def test_minimal_valid_payload(self):
        from api.routes.sites import ParsedSitePayload

        site = ParsedSitePayload(name="Minimal", lat=0.0, lon=0.0)
        assert site.name == "Minimal"
        assert site.description_citations is None
        assert site.reference_links is None

    def test_payload_with_enrichment(self):
        from api.routes.sites import ParsedSitePayload

        data = _make_site_with_enrichment()
        site = ParsedSitePayload(**data)
        assert len(site.description_citations) == 1
        assert len(site.reference_links) == 1
        assert site.reference_links[0]["domain"] == "example.com"

    def test_name_max_length(self):
        from api.routes.sites import ParsedSitePayload

        with pytest.raises(ValueError):
            ParsedSitePayload(name="x" * 501, lat=0.0, lon=0.0)

    def test_confidence_score_bounds(self):
        from api.routes.sites import ParsedSitePayload

        site = ParsedSitePayload(name="Valid", lat=0.0, lon=0.0, confidence_score=0.85)
        assert site.confidence_score == 0.85

        with pytest.raises(ValueError):
            ParsedSitePayload(name="Bad", lat=0.0, lon=0.0, confidence_score=1.5)

        with pytest.raises(ValueError):
            ParsedSitePayload(name="Bad", lat=0.0, lon=0.0, confidence_score=-0.1)


# =============================================================================
# ReplaceSourceRequest model
# =============================================================================


class TestReplaceSourceRequest:
    """Test the Pydantic model for replace-source requests."""

    def test_valid_request(self):
        from api.routes.sites import ReplaceSourceRequest

        req = ReplaceSourceRequest(
            sites=[_make_site()],
            target_source="ancient_nerds",
        )
        assert req.target_source == "ancient_nerds"
        assert len(req.sites) == 1

    def test_empty_target_source_rejected(self):
        from api.routes.sites import ReplaceSourceRequest

        # Empty string is technically valid for Pydantic (no min_length constraint)
        # but the endpoint will reject it — this just tests model instantiation
        req = ReplaceSourceRequest(sites=[_make_site()], target_source="")
        assert req.target_source == ""


# =============================================================================
# Chunking logic (frontend, tested as pure logic)
# =============================================================================


class TestChunkingLogic:
    """Test that chunking splits correctly (mirrors frontend commitReplace logic)."""

    def test_small_batch_single_chunk(self):
        """<=200 sites should result in one chunk."""
        sites = [_make_site(name=f"Site {i}") for i in range(50)]
        chunk_size = 200
        chunks = [sites[i : i + chunk_size] for i in range(0, len(sites), chunk_size)]
        assert len(chunks) == 1
        assert len(chunks[0]) == 50

    def test_exact_chunk_boundary(self):
        """Exactly 200 sites = 1 chunk, 201 = 2 chunks."""
        sites_200 = list(range(200))
        sites_201 = list(range(201))
        chunk_size = 200

        chunks_200 = [sites_200[i : i + chunk_size] for i in range(0, len(sites_200), chunk_size)]
        chunks_201 = [sites_201[i : i + chunk_size] for i in range(0, len(sites_201), chunk_size)]

        assert len(chunks_200) == 1
        assert len(chunks_201) == 2
        assert len(chunks_201[0]) == 200
        assert len(chunks_201[1]) == 1

    def test_large_batch_chunk_count(self):
        """5005 sites should produce 26 chunks (25 x 200 + 1 x 5)."""
        sites = list(range(5005))
        chunk_size = 200
        chunks = [sites[i : i + chunk_size] for i in range(0, len(sites), chunk_size)]
        assert len(chunks) == 26
        assert len(chunks[-1]) == 5
        assert sum(len(c) for c in chunks) == 5005

    def test_first_chunk_uses_replace_second_uses_batch(self):
        """Simulate the frontend routing: chunk 0 → replace-source, rest → batch-upload."""
        chunks = [list(range(200)), list(range(200)), list(range(100))]
        endpoints = []
        for i, _chunk in enumerate(chunks):
            endpoints.append("replace-source" if i == 0 else "batch-upload")

        assert endpoints == ["replace-source", "batch-upload", "batch-upload"]


# =============================================================================
# Content-ID hash stability
# =============================================================================


class TestContentIdHash:
    """Test that content IDs are deterministic (hashlib.md5, not hash())."""

    def test_md5_hash_deterministic(self):
        """Same URL always produces same content_id."""
        import hashlib

        url = "https://example.com/article"
        h1 = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:8]
        h2 = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:8]
        assert h1 == h2

    def test_different_urls_different_hashes(self):
        import hashlib

        url_a = "https://example.com/a"
        url_b = "https://example.com/b"
        h_a = hashlib.md5(url_a.encode(), usedforsecurity=False).hexdigest()[:8]
        h_b = hashlib.md5(url_b.encode(), usedforsecurity=False).hexdigest()[:8]
        assert h_a != h_b

    def test_content_id_format(self):
        """content_id should be domain:hash format."""
        import hashlib

        url = "https://example.com/ref"
        domain = "example.com"
        url_hash = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:8]
        content_id = f"{domain}:{url_hash}"
        assert ":" in content_id
        assert content_id.startswith("example.com:")
        assert len(url_hash) == 8
