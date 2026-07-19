# Radar Promotion Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Founder review workflow for Radar candidates — approve with inline edits (relaxed core-fields gate), reject (dismiss), merge into existing sites — plus a tightened auto-promote gate (score 100 + high AI confidence).

**Architecture:** All backend changes live in `api/routes/radar.py` (new pure gate helpers + 2 new endpoints + extended promote) and `pipeline/lyra/site_identifier.py`/`config.py` (auto-promote gate). Frontend adds two modal components and an actions row on the existing Radar cards. No DB migration — `dismissed` is a new string value in the existing `enrichment_status` column.

**Tech Stack:** FastAPI + raw SQL (existing pattern in radar.py), pytest, React/TypeScript (Vite), existing founder JWT auth.

**Spec:** `docs/superpowers/specs/2026-07-19-radar-promotion-upgrade-design.md`

**Key facts for implementers (verified against code/prod 2026-07-19):**
- Manual promote today requires `_compute_display_score() == 100` — this is what we relax.
- Pipeline auto-promote today is `contribution.score >= min_score_for_promotion` with default **55** (`pipeline/lyra/config.py:175`); 250 enriched prod rows pass all its guards and would bulk-promote on their next re-mention. We raise the default to 100 and add a confidence gate.
- Founder reject must use a NEW status `dismissed`, NOT `rejected` — the identifier work query (`site_identifier.py:231`) re-enriches `rejected` rows. `dismissed` is not in that list, so no pipeline change is needed for exclusion.
- Tests run on sqlite in-memory (`tests/conftest.py`) — endpoint tests needing PG are skipped in this repo (see `tests/api/test_sites.py` `requires_db` pattern). Therefore we TDD the pure gate/override helpers and the `_maybe_promote` early-return gates, not full endpoint round-trips.
- CI does not run pytest (lint/security/docker only) — run tests locally.
- `require_founder` yields a `DiscordUser` with `.username` (`pipeline/database.py:1125`).

---

### Task 1: Pure gate helpers in radar.py (TDD)

**Files:**
- Modify: `api/routes/radar.py` (add helpers near `_compute_display_score`, ~line 105)
- Create: `tests/api/test_radar_gates.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_radar_gates.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for radar promotion gate helpers (pure functions, no DB)."""

from api.routes.radar import _apply_overrides, _missing_core_fields


COMPLETE_ITEM = {
    "lat": 37.2231,
    "lon": 38.9225,
    "country": "Turkey",
    "site_type": "settlement",
    "description": "A pre-pottery neolithic settlement with carved orthostats and communal buildings.",
}


class TestMissingCoreFields:
    def test_complete_item_has_no_missing_fields(self):
        assert _missing_core_fields(COMPLETE_ITEM) == []

    def test_missing_coordinates(self):
        item = {**COMPLETE_ITEM, "lat": None}
        assert _missing_core_fields(item) == ["coordinates"]
        item = {**COMPLETE_ITEM, "lon": None}
        assert _missing_core_fields(item) == ["coordinates"]

    def test_missing_country(self):
        assert _missing_core_fields({**COMPLETE_ITEM, "country": None}) == ["country"]
        assert _missing_core_fields({**COMPLETE_ITEM, "country": ""}) == ["country"]

    def test_missing_site_type(self):
        assert _missing_core_fields({**COMPLETE_ITEM, "site_type": None}) == ["site_type"]

    def test_short_description(self):
        assert _missing_core_fields({**COMPLETE_ITEM, "description": "Too short."}) == ["description"]
        assert _missing_core_fields({**COMPLETE_ITEM, "description": None}) == ["description"]

    def test_all_missing(self):
        assert _missing_core_fields({}) == ["coordinates", "country", "site_type", "description"]

    def test_wikipedia_thumbnail_qid_not_required(self):
        # The old 100%-score gate required these — the new gate must not.
        item = {**COMPLETE_ITEM, "wikipedia_url": None, "thumbnail_url": None, "wikidata_id": None}
        assert _missing_core_fields(item) == []


class TestApplyOverrides:
    def test_override_fills_missing_field(self):
        item = {**COMPLETE_ITEM, "country": None}
        merged = _apply_overrides(item, {"country": "Turkey"})
        assert merged["country"] == "Turkey"
        assert _missing_core_fields(merged) == []

    def test_override_replaces_existing_field(self):
        merged = _apply_overrides(COMPLETE_ITEM, {"lat": 40.0, "lon": 41.0})
        assert merged["lat"] == 40.0
        assert merged["lon"] == 41.0

    def test_none_values_in_overrides_are_ignored(self):
        merged = _apply_overrides(COMPLETE_ITEM, {"country": None, "lat": None})
        assert merged["country"] == "Turkey"
        assert merged["lat"] == 37.2231

    def test_original_dict_not_mutated(self):
        item = {**COMPLETE_ITEM}
        _apply_overrides(item, {"country": "Syria"})
        assert item["country"] == "Turkey"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_radar_gates.py -v`
Expected: FAIL with `ImportError: cannot import name '_apply_overrides'`

- [ ] **Step 3: Implement the helpers**

In `api/routes/radar.py`, directly after `_compute_display_score` (ends line 125), add:

```python
def _missing_core_fields(item: dict) -> list[str]:
    """Fields required for manual promotion. Wikipedia/thumbnail/QID are score
    bonuses, not blockers — newly discovered sites rarely have them."""
    missing = []
    if item.get("lat") is None or item.get("lon") is None:
        missing.append("coordinates")
    if not item.get("country"):
        missing.append("country")
    if not item.get("site_type"):
        missing.append("site_type")
    if len(item.get("description") or "") < 50:
        missing.append("description")
    return missing


def _apply_overrides(item: dict, overrides: dict) -> dict:
    """Merge founder-supplied field overrides onto a contribution dict.

    Returns a new dict; None values in overrides are ignored (field not sent).
    """
    merged = dict(item)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_radar_gates.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add api/routes/radar.py tests/api/test_radar_gates.py
git commit -m "feat(radar): core-fields gate helpers for relaxed promotion"
```

---

### Task 2: Extend promote endpoint — overrides + relaxed gate + audit

**Files:**
- Modify: `api/routes/radar.py` (`promote_to_db`, lines 655–781; imports line 8–19; `_find_nearest_an_sites_batch` lines 166–224)

- [ ] **Step 1: Add imports and the overrides model**

At the top of `api/routes/radar.py`, extend imports (line 8–13 area):

```python
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
```

After the `_apply_overrides` helper from Task 1, add:

```python
class PromoteOverrides(BaseModel):
    """Founder-supplied field fixes applied at promotion time only.

    Never persisted onto the un-promoted contribution — that would be
    clobbered by the next enrichment pass when the facts hash changes.
    """

    name: str | None = Field(None, min_length=2, max_length=500)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    country: str | None = Field(None, max_length=100)
    site_type: str | None = Field(None, max_length=100)
    period_name: str | None = Field(None, max_length=100)
    period_start: int | None = None
    period_end: int | None = None
    description: str | None = None


def _review_entry(action: str, username: str, **extra) -> dict:
    return {
        "action": action,
        "user": username,
        "at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
```

- [ ] **Step 2: Rewrite the promote endpoint body**

Replace the whole `promote_to_db` function (lines 655–781) with:

```python
@router.post("/{contribution_id}/promote")
async def promote_to_db(
    contribution_id: str,
    overrides: PromoteOverrides | None = None,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Promote an enriched radar item into unified_sites (founders only).

    Requires core fields (coords, country, site_type, description >= 50 chars)
    after applying optional founder overrides. Wikipedia/thumbnail/QID are
    score bonuses, not blockers.
    """

    # Fetch the contribution
    row = db.execute(
        text("SELECT * FROM user_contributions WHERE id = :id"),
        {"id": contribution_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contribution not found")

    item = dict(row._mapping)

    # Must be enriched
    if item.get("enrichment_status") != "enriched":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot promote: status is '{item.get('enrichment_status')}', expected 'enriched'",
        )

    # Must not already be promoted
    if item.get("promoted_site_id") is not None:
        raise HTTPException(status_code=409, detail="Already promoted")

    override_dict = overrides.model_dump(exclude_none=True) if overrides else {}
    effective = _apply_overrides(item, override_dict)

    missing = _missing_core_fields(effective)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Missing core fields: {', '.join(missing)}",
                "missing": missing,
            },
        )

    display_name = (
        override_dict.get("name") or effective.get("corrected_name") or effective["name"]
    )

    # Determine source_id for the new unified_sites row
    source_id = "lyra" if effective.get("source") == "lyra" else "ancient_nerds_community"

    # Compute period_name from period_start if available
    period_name = effective.get("period_name")
    if effective.get("period_start") is not None:
        period_name = categorize_period(effective["period_start"])

    new_site_id = uuid.uuid4()
    name_norm = normalize_name(display_name)

    # INSERT into unified_sites
    db.execute(
        text("""
        INSERT INTO unified_sites (
            id, source_id, source_record_id, name, name_normalized,
            lat, lon, geom,
            site_type, period_start, period_end, period_name,
            country, description, thumbnail_url, source_url,
            edited_by
        ) VALUES (
            :id, :source_id, :source_record_id, :name, :name_normalized,
            :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
            :site_type, :period_start, :period_end, :period_name,
            :country, :description, :thumbnail_url, :source_url,
            'radar_promote'
        )
    """),
        {
            "id": new_site_id,
            "source_id": source_id,
            "source_record_id": str(item["id"]),
            "name": display_name,
            "name_normalized": name_norm,
            "lat": effective["lat"],
            "lon": effective["lon"],
            "site_type": effective.get("site_type"),
            "period_start": effective.get("period_start"),
            "period_end": effective.get("period_end"),
            "period_name": period_name,
            "country": effective.get("country"),
            "description": effective.get("description"),
            "thumbnail_url": effective.get("thumbnail_url"),
            "source_url": effective.get("wikipedia_url"),
        },
    )

    # INSERT into unified_site_names for trigram search
    db.execute(
        text("""
        INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
        VALUES (:site_id, :name, :name_normalized, 'label')
    """),
        {
            "site_id": new_site_id,
            "name": display_name,
            "name_normalized": name_norm,
        },
    )

    # UPDATE the contribution: status + audit entry (overrides recorded, not applied)
    enrichment_data = dict(item.get("enrichment_data") or {})
    enrichment_data["review"] = _review_entry(
        "promote", user.username, overrides=override_dict, site_id=str(new_site_id)
    )
    db.execute(
        text("""
        UPDATE user_contributions
        SET enrichment_status = 'promoted', promoted_site_id = :site_id,
            enrichment_data = CAST(:ed AS JSONB)
        WHERE id = :id
    """),
        {"site_id": new_site_id, "id": contribution_id, "ed": json.dumps(enrichment_data)},
    )

    db.commit()

    # Bust caches
    cache_delete_pattern("radar:*")
    cache_delete_pattern("sites:*")

    return {"success": True, "site_id": str(new_site_id)}
```

Note: `_user` is renamed to `user` because the audit entry needs `.username`. `_compute_display_score` stays (still used by `/list` and map SQL mirrors) but is no longer called in promote.

- [ ] **Step 3: Add site_id to nearby_an_site (needed by the merge picker)**

In `_find_nearest_an_sites_batch` (line 197–224): add `us.id::text AS an_site_id,` to the SELECT list right after `c.idx,`, and change the result dict to:

```python
        result[item_id] = {
            "site_id": row.an_site_id,
            "name": row.name,
            "distance_km": round(row.dist_km, 1),
        }
```

- [ ] **Step 4: Expose period_end in the list endpoint (the approve modal edits it)**

The `/list` response currently omits `period_end`. In `get_radar`:
- In the `contrib` CTE column list, after `uc.period_start,` add `uc.period_end,`
- In the outer SELECT, after `c.period_start,` add `c.period_end,`
- In `_row_to_item`, after `"period_start": row.period_start,` add `"period_end": row.period_end,`

- [ ] **Step 5: Run existing tests + lint**

Run: `python -m pytest tests/api/test_radar_gates.py tests/api -v` and `ruff check api/routes/radar.py`
Expected: tests pass, no new lint errors

- [ ] **Step 6: Commit**

```bash
git add api/routes/radar.py
git commit -m "feat(radar): promote with founder overrides, core-fields gate, audit entry"
```

---

### Task 3: Dismiss endpoint

**Files:**
- Modify: `api/routes/radar.py` (add after `promote_to_db`)

- [ ] **Step 1: Add the endpoint**

```python
@router.post("/{contribution_id}/dismiss")
async def dismiss_contribution(
    contribution_id: str,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Founder-reject a radar candidate (founders only).

    Uses status 'dismissed' (NOT 'rejected') — the enrichment pipeline
    re-processes 'rejected' rows each cycle, which would resurrect the card.
    'dismissed' is excluded from the pipeline work query.
    """
    row = db.execute(
        text("SELECT enrichment_status, enrichment_data FROM user_contributions WHERE id = :id"),
        {"id": contribution_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contribution not found")

    if row.enrichment_status != "enriched":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot dismiss: status is '{row.enrichment_status}', expected 'enriched'",
        )

    enrichment_data = dict(row.enrichment_data or {})
    enrichment_data["review"] = _review_entry("dismiss", user.username)
    db.execute(
        text("""
        UPDATE user_contributions
        SET enrichment_status = 'dismissed', enrichment_data = CAST(:ed AS JSONB)
        WHERE id = :id
    """),
        {"id": contribution_id, "ed": json.dumps(enrichment_data)},
    )
    db.commit()

    cache_delete_pattern("radar:*")
    return {"success": True}
```

- [ ] **Step 2: Make the list filter treat dismissed like rejected**

In `get_radar` (line 334–335), change:

```python
    elif status == "rejected":
        status_clause = "uc.enrichment_status = 'rejected'"
```

to:

```python
    elif status == "rejected":
        status_clause = "uc.enrichment_status IN ('rejected', 'dismissed')"
```

(The default `all` clause and `/map`/`/stats` need no change — they only exclude `failed`/`not_a_site`/`matched`, and `dismissed` should behave exactly like `rejected` there: visible, counted.)

- [ ] **Step 3: Run lint + tests**

Run: `ruff check api/routes/radar.py && python -m pytest tests/api -v`
Expected: pass

- [ ] **Step 4: Commit**

```bash
git add api/routes/radar.py
git commit -m "feat(radar): dismiss endpoint — founder reject with pipeline-safe status"
```

---

### Task 4: Merge endpoint

**Files:**
- Modify: `api/routes/radar.py` (add after `dismiss_contribution`)

- [ ] **Step 1: Add the endpoint**

```python
class MergeRequest(BaseModel):
    site_id: str


@router.post("/{contribution_id}/merge")
async def merge_into_site(
    contribution_id: str,
    body: MergeRequest,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Merge a radar candidate into an existing unified_sites row (founders only).

    Stores the candidate's name(s) as aliases so future news mentions match
    the existing site directly and this card never regenerates.
    """
    row = db.execute(
        text("""
        SELECT name, corrected_name, enrichment_status, enrichment_data
        FROM user_contributions WHERE id = :id
    """),
        {"id": contribution_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contribution not found")

    if row.enrichment_status != "enriched":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot merge: status is '{row.enrichment_status}', expected 'enriched'",
        )

    site = db.execute(
        text("SELECT id, name FROM unified_sites WHERE id = :sid"),
        {"sid": body.site_id},
    ).fetchone()
    if not site:
        raise HTTPException(status_code=404, detail="Target site not found")

    # Store candidate name(s) as aliases (idempotent per normalized name)
    aliases = {row.name}
    if row.corrected_name:
        aliases.add(row.corrected_name)
    for alias in aliases:
        alias_norm = normalize_name(alias)
        if not alias_norm:
            continue
        db.execute(
            text("""
            INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
            SELECT :site_id, :name, :name_normalized, 'alias'
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_site_names
                WHERE site_id = :site_id AND name_normalized = :name_normalized
            )
        """),
            {"site_id": body.site_id, "name": alias, "name_normalized": alias_norm},
        )

    enrichment_data = dict(row.enrichment_data or {})
    enrichment_data["review"] = _review_entry(
        "merge", user.username, site_id=body.site_id, site_name=site.name
    )
    db.execute(
        text("""
        UPDATE user_contributions
        SET enrichment_status = 'matched', enrichment_data = CAST(:ed AS JSONB)
        WHERE id = :id
    """),
        {"id": contribution_id, "ed": json.dumps(enrichment_data)},
    )
    db.commit()

    cache_delete_pattern("radar:*")
    return {"success": True, "site_id": body.site_id, "site_name": site.name}
```

- [ ] **Step 2: Run lint + tests**

Run: `ruff check api/routes/radar.py && python -m pytest tests/api -v`
Expected: pass

- [ ] **Step 3: Commit**

```bash
git add api/routes/radar.py
git commit -m "feat(radar): merge endpoint — alias candidate into existing site"
```

---

### Task 4b: Endpoint guard tests (mocked DB, no PG needed)

**Files:**
- Create: `tests/api/test_radar_review_endpoints.py`

These test the 404/409/422 guard paths, which all raise BEFORE any DB write or
cache call — so a MagicMock session via FastAPI dependency overrides is enough.
Success paths touch PG-specific SQL and Redis cache and are covered by the
live smoke test instead (Task 10).

- [ ] **Step 1: Write the tests**

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Radar review endpoint guards (mocked DB via dependency overrides — no PG)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.jwt_auth import require_founder
from pipeline.database import get_db


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
        # proceeds into (mocked) inserts, so we just assert it's not a 4xx gate error.
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
            {"name": "X", "corrected_name": None, "enrichment_status": "enriched", "enrichment_data": None}
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
            {"name": "X", "corrected_name": None, "enrichment_status": "matched", "enrichment_data": None}
        )
        session.execute.side_effect = [contrib_result]
        resp = client.post("/api/radar/x/merge", json={"site_id": "y"})
        assert resp.status_code == 409
```

Note on `test_overrides_fill_missing_field_passes_gate`: the success path runs
`cache_delete_pattern` — if that fails against the test environment (no Redis),
check how `api/cache.py` behaves with `TESTING=true`; if it raises, drop that
single test rather than mocking half the endpoint (the gate-pass behavior is
already covered by `tests/api/test_radar_gates.py`).

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/api/test_radar_review_endpoints.py -v`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_radar_review_endpoints.py
git commit -m "test(radar): guard tests for promote/dismiss/merge endpoints"
```

---

### Task 5: Tighten pipeline auto-promote (TDD)

**Files:**
- Modify: `pipeline/lyra/config.py:175`
- Modify: `pipeline/lyra/site_identifier.py` (`_maybe_promote`, line 2368)
- Create: `tests/pipeline/test_radar_auto_promote.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/pipeline/test_radar_auto_promote.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Auto-promote gate: score 100 + high AI confidence required."""

from unittest.mock import MagicMock, patch

from pipeline.database import UserContribution
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.site_identifier import _maybe_promote


def _contribution(score=100, confidence="high", lat=37.0, lon=38.0):
    c = UserContribution(name="Test Site", source="lyra")
    c.score = score
    c.lat = lat
    c.lon = lon
    c.enrichment_data = {"identification": {"confidence": confidence}}
    return c


def test_default_promotion_threshold_is_100():
    assert LyraSettings().min_score_for_promotion == 100


@patch("pipeline.lyra.site_identifier.passes_date_cutoff")
def test_below_threshold_returns_early(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(score=99), "Test Site", settings)
    mock_cutoff.assert_not_called()


@patch("pipeline.lyra.site_identifier.passes_date_cutoff")
def test_medium_confidence_returns_early(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(confidence="medium"), "Test Site", settings)
    mock_cutoff.assert_not_called()


@patch("pipeline.lyra.site_identifier.passes_date_cutoff")
def test_missing_confidence_returns_early(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    contribution = _contribution()
    contribution.enrichment_data = {}
    _maybe_promote(session, contribution, "Test Site", settings)
    mock_cutoff.assert_not_called()


@patch("pipeline.lyra.site_identifier.passes_date_cutoff", return_value=False)
def test_high_confidence_and_score_100_proceeds_to_cutoff(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(), "Test Site", settings)
    mock_cutoff.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_radar_auto_promote.py -v`
Expected: `test_default_promotion_threshold_is_100` FAILS (55 != 100); `test_medium_confidence_returns_early` and `test_missing_confidence_returns_early` FAIL (cutoff called)

- [ ] **Step 3: Implement**

`pipeline/lyra/config.py:175`, change:

```python
    min_score_for_promotion: int = 55
```

to:

```python
    # 100 = auto-promote only perfect candidates; everything else goes through
    # the founder review queue on the Radar page (2026-07-19 promotion upgrade)
    min_score_for_promotion: int = 100
```

`pipeline/lyra/site_identifier.py`, in `_maybe_promote` (line 2374), after the score check and before the coords check, add:

```python
    identification = (contribution.enrichment_data or {}).get("identification", {})
    confidence = identification.get("confidence")
    if confidence != "high":
        logger.info(
            f"  [{contribution.name}] Skipping auto-promotion — "
            f"AI confidence is '{confidence}', founder review required"
        )
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/pipeline/test_radar_auto_promote.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/config.py pipeline/lyra/site_identifier.py tests/pipeline/test_radar_auto_promote.py
git commit -m "feat(lyra): auto-promote requires score 100 + high AI confidence"
```

---

### Task 6: Frontend — types, StatusPill, API handlers

**Files:**
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.tsx`

- [ ] **Step 1: Extend types**

Line 84, change `nearby_an_site` to include the site id (backend Task 2 Step 3):

```typescript
  nearby_an_site: { site_id: string; name: string; distance_km: number } | null
```

In the `RadarItem` interface, after `period_start: number | null` (line 64), add the field exposed by Task 2 Step 4:

```typescript
  period_end: number | null
```

- [ ] **Step 2: StatusPill handles 'dismissed' and 'matched'**

In `StatusPill` (line 119), add cases before `default`:

```typescript
    case 'dismissed':
      label = 'Dismissed'
      cls = 'lyra-status-rejected'
      hint = 'Dismissed by founder review'
      break
    case 'matched':
      label = 'Matched'
      cls = 'lyra-status-added'
      hint = 'Merged into an existing database site'
      break
```

- [ ] **Step 3: Map filter treats dismissed like rejected**

In `mapFilterFn` (line 667–673), replace the body with:

```typescript
  const mapFilterFn = useCallback((item: RadarMapItem) => {
    if (statusFilter === 'all') return true
    if (statusFilter === 'rejected') {
      return item.enrichment_status === 'rejected' || item.enrichment_status === 'dismissed'
    }
    const mapped = statusFilter === 'added' ? 'promoted' : statusFilter
    return item.enrichment_status === mapped
  }, [statusFilter])
```

- [ ] **Step 4: Replace handlePromote with three handlers**

Replace `handlePromote` (lines 675–694) with:

```typescript
  const authPost = useCallback(async (path: string, body?: unknown): Promise<Response> => {
    return fetch(`${config.api.baseUrl}${path}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
  }, [token])

  const handleApprove = useCallback(async (itemId: string, overrides: Record<string, unknown>): Promise<string | null> => {
    if (!token) return 'Not authenticated'
    try {
      const resp = await authPost(`/radar/${itemId}/promote`, Object.keys(overrides).length ? overrides : undefined)
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
        const detail = data.detail
        return typeof detail === 'object' && detail?.message ? detail.message : String(detail || resp.statusText)
      }
      setItems(prev => prev.map(it =>
        it.id === itemId ? { ...it, enrichment_status: 'promoted', ...overrides } : it
      ))
      return null
    } catch (e) {
      return e instanceof Error ? e.message : 'Network error'
    }
  }, [token, authPost])

  const handleDismiss = useCallback(async (itemId: string) => {
    if (!token) return
    try {
      const resp = await authPost(`/radar/${itemId}/dismiss`)
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
        alert(`Dismiss failed: ${data.detail || resp.statusText}`)
        return
      }
      setItems(prev => prev.map(it =>
        it.id === itemId ? { ...it, enrichment_status: 'dismissed' } : it
      ))
    } catch (e) {
      alert(`Dismiss failed: ${e instanceof Error ? e.message : 'Network error'}`)
    }
  }, [token, authPost])

  const handleMerge = useCallback(async (itemId: string, siteId: string): Promise<string | null> => {
    if (!token) return 'Not authenticated'
    try {
      const resp = await authPost(`/radar/${itemId}/merge`, { site_id: siteId })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
        return String(data.detail || resp.statusText)
      }
      setItems(prev => prev.map(it =>
        it.id === itemId ? { ...it, enrichment_status: 'matched' } : it
      ))
      return null
    } catch (e) {
      return e instanceof Error ? e.message : 'Network error'
    }
  }, [token, authPost])
```

(Approve/merge return an error string or null so the modals can display failures inline; dismiss keeps the existing `alert` pattern since it has no modal.)

- [ ] **Step 5: Typecheck**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: errors ONLY about unused handlers (wired in Task 8) and the not-yet-updated RadarCard props — acceptable mid-stack; fix anything else.

- [ ] **Step 6: Commit**

```bash
git add ancient-nerds-map/src/pages/LyraRadarPage.tsx
git commit -m "feat(radar-ui): status pills + approve/dismiss/merge API handlers"
```

---

### Task 7: Frontend — Approve and Merge modals

**Files:**
- Create: `ancient-nerds-map/src/components/RadarReviewModals.tsx`

One file for both modals — they share the overlay/form styling and are only used by the Radar page.

- [ ] **Step 1: Create the component file**

```typescript
/**
 * Founder review modals for the Lyra Radar page.
 *
 * ApproveModal: edit/complete promotable fields, submit as overrides to
 * POST /radar/{id}/promote. Overrides are applied at promotion time only.
 * MergeModal: pick an existing site (nearby suggestion or name search),
 * submit to POST /radar/{id}/merge.
 */

import { useState, useEffect, useCallback } from 'react'
import { config } from '../config'

export interface ApproveFields {
  display_name: string
  lat: number | null
  lon: number | null
  country: string | null
  site_type: string | null
  period_name: string | null
  period_start: number | null
  period_end: number | null
  description: string | null
  nearby_an_site: { site_id: string; name: string; distance_km: number } | null
}

interface ApproveModalProps {
  item: ApproveFields & { id: string }
  onSubmit: (overrides: Record<string, unknown>) => Promise<string | null>
  onClose: () => void
}

const CORE_HINT = 'Required for promotion'

export function ApproveModal({ item, onSubmit, onClose }: ApproveModalProps) {
  const [name, setName] = useState(item.display_name)
  const [lat, setLat] = useState(item.lat != null ? String(item.lat) : '')
  const [lon, setLon] = useState(item.lon != null ? String(item.lon) : '')
  const [country, setCountry] = useState(item.country ?? '')
  const [siteType, setSiteType] = useState(item.site_type ?? '')
  const [periodStart, setPeriodStart] = useState(item.period_start != null ? String(item.period_start) : '')
  const [periodEnd, setPeriodEnd] = useState(item.period_end != null ? String(item.period_end) : '')
  const [description, setDescription] = useState(item.description ?? '')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const latNum = lat.trim() === '' ? null : Number(lat)
  const lonNum = lon.trim() === '' ? null : Number(lon)
  const coordsInvalid = (latNum != null && (isNaN(latNum) || latNum < -90 || latNum > 90))
    || (lonNum != null && (isNaN(lonNum) || lonNum < -180 || lonNum > 180))

  const missingCoords = latNum == null || lonNum == null
  const missingCountry = country.trim() === ''
  const missingType = siteType.trim() === ''
  const missingDesc = description.trim().length < 50
  const canSubmit = !missingCoords && !coordsInvalid && !missingCountry && !missingType && !missingDesc && !submitting

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    // Send only fields that differ from the item (server merges over stored values)
    const overrides: Record<string, unknown> = {}
    if (name.trim() && name.trim() !== item.display_name) overrides.name = name.trim()
    if (latNum != null && latNum !== item.lat) overrides.lat = latNum
    if (lonNum != null && lonNum !== item.lon) overrides.lon = lonNum
    if (country.trim() && country.trim() !== (item.country ?? '')) overrides.country = country.trim()
    if (siteType.trim() && siteType.trim() !== (item.site_type ?? '')) overrides.site_type = siteType.trim()
    if (periodStart.trim() !== '' && Number(periodStart) !== item.period_start) overrides.period_start = Number(periodStart)
    if (periodEnd.trim() !== '' && Number(periodEnd) !== item.period_end) overrides.period_end = Number(periodEnd)
    if (description.trim() && description.trim() !== (item.description ?? '')) overrides.description = description.trim()
    const err = await onSubmit(overrides)
    setSubmitting(false)
    if (err) {
      setError(err)
    } else {
      onClose()
    }
  }

  return (
    <div className="radar-modal-overlay" onClick={onClose}>
      <div className="radar-modal" onClick={e => e.stopPropagation()}>
        <h3 className="radar-modal-title">Approve &amp; add to database</h3>
        {item.nearby_an_site && (
          <div className="radar-modal-warning">
            &#9888; Near existing AN site: {item.nearby_an_site.name} ({item.nearby_an_site.distance_km} km).
            Consider Merge instead if this is the same site.
          </div>
        )}
        <label className="radar-modal-label">Name
          <input className="radar-modal-input" value={name} onChange={e => setName(e.target.value)} />
        </label>
        <div className="radar-modal-row">
          <label className={`radar-modal-label ${missingCoords || coordsInvalid ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Latitude *
            <input className="radar-modal-input" value={lat} onChange={e => setLat(e.target.value)} inputMode="decimal" />
          </label>
          <label className={`radar-modal-label ${missingCoords || coordsInvalid ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Longitude *
            <input className="radar-modal-input" value={lon} onChange={e => setLon(e.target.value)} inputMode="decimal" />
          </label>
        </div>
        <div className="radar-modal-row">
          <label className={`radar-modal-label ${missingCountry ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Country *
            <input className="radar-modal-input" value={country} onChange={e => setCountry(e.target.value)} />
          </label>
          <label className={`radar-modal-label ${missingType ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Site type *
            <input className="radar-modal-input" value={siteType} onChange={e => setSiteType(e.target.value)} placeholder="settlement, temple, tomb…" />
          </label>
        </div>
        <div className="radar-modal-row">
          <label className="radar-modal-label">Period start (year, neg. = BCE)
            <input className="radar-modal-input" value={periodStart} onChange={e => setPeriodStart(e.target.value)} inputMode="numeric" />
          </label>
          <label className="radar-modal-label">Period end
            <input className="radar-modal-input" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)} inputMode="numeric" />
          </label>
        </div>
        <label className={`radar-modal-label ${missingDesc ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
          Description * ({description.trim().length}/50 min)
          <textarea className="radar-modal-textarea" rows={4} value={description} onChange={e => setDescription(e.target.value)} />
        </label>
        {error && <div className="radar-modal-error">{error}</div>}
        <div className="radar-modal-actions">
          <button className="radar-modal-btn radar-modal-cancel" onClick={onClose}>Cancel</button>
          <button className="radar-modal-btn radar-modal-confirm" disabled={!canSubmit} onClick={submit}>
            {submitting ? 'Adding…' : 'Add to database'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface SearchResult {
  id: string
  n: string
  s: string
  c?: string
}

interface MergeModalProps {
  itemName: string
  nearbyAnSite: { site_id: string; name: string; distance_km: number } | null
  onMerge: (siteId: string) => Promise<string | null>
  onClose: () => void
}

export function MergeModal({ itemName, nearbyAnSite, onMerge, onClose }: MergeModalProps) {
  const [query, setQuery] = useState(itemName)
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submittingId, setSubmittingId] = useState<string | null>(null)

  const search = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults([])
      return
    }
    setSearching(true)
    try {
      const resp = await fetch(`${config.api.baseUrl}/sites/search?q=${encodeURIComponent(q.trim())}&limit=8`)
      if (resp.ok) {
        const data = await resp.json()
        setResults(data.sites ?? [])
      }
    } finally {
      setSearching(false)
    }
  }, [])

  useEffect(() => {
    const t = window.setTimeout(() => { void search(query) }, 300)
    return () => window.clearTimeout(t)
  }, [query, search])

  const pick = async (siteId: string) => {
    setSubmittingId(siteId)
    setError(null)
    const err = await onMerge(siteId)
    setSubmittingId(null)
    if (err) {
      setError(err)
    } else {
      onClose()
    }
  }

  return (
    <div className="radar-modal-overlay" onClick={onClose}>
      <div className="radar-modal" onClick={e => e.stopPropagation()}>
        <h3 className="radar-modal-title">Merge into existing site</h3>
        <p className="radar-modal-hint">
          "{itemName}" becomes an alias of the selected site — future news mentions
          will match it directly and this card will not come back.
        </p>
        {nearbyAnSite && (
          <button
            className="radar-merge-result radar-merge-nearby"
            disabled={submittingId !== null}
            onClick={() => pick(nearbyAnSite.site_id)}
          >
            <span className="radar-merge-name">{nearbyAnSite.name}</span>
            <span className="radar-merge-meta">AN Originals · {nearbyAnSite.distance_km} km away</span>
          </button>
        )}
        <input
          className="radar-modal-input"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search existing sites…"
        />
        {searching && <div className="radar-modal-hint">Searching…</div>}
        {results.filter(r => r.id !== nearbyAnSite?.site_id).map(r => (
          <button
            key={r.id}
            className="radar-merge-result"
            disabled={submittingId !== null}
            onClick={() => pick(r.id)}
          >
            <span className="radar-merge-name">{r.n}</span>
            <span className="radar-merge-meta">{r.s}{r.c ? ` · ${r.c}` : ''}</span>
          </button>
        ))}
        {error && <div className="radar-modal-error">{error}</div>}
        <div className="radar-modal-actions">
          <button className="radar-modal-btn radar-modal-cancel" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: no errors in the new file (unused-export warnings acceptable until Task 8)

- [ ] **Step 3: Commit**

```bash
git add ancient-nerds-map/src/components/RadarReviewModals.tsx
git commit -m "feat(radar-ui): approve and merge review modals"
```

---

### Task 8: Frontend — wire actions row into RadarCard

**Files:**
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.tsx` (RadarCard line 296, promote block lines 448–456, grid render ~line 1010)

- [ ] **Step 1: Update RadarCard props and add modal/confirm state**

Change the signature (line 296) to:

```typescript
function RadarCard({ item, onViewSite, onApprove, onDismiss, onMerge }: {
  item: RadarItem
  onViewSite?: (site: SiteData) => void
  onApprove?: (id: string, overrides: Record<string, unknown>) => Promise<string | null>
  onDismiss?: (id: string) => void
  onMerge?: (id: string, siteId: string) => Promise<string | null>
}) {
  const [factsExpanded, setFactsExpanded] = useState(false)
  const [videosExpanded, setVideosExpanded] = useState(false)
  const [sourcesExpanded, setSourcesExpanded] = useState(false)
  const [showApprove, setShowApprove] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [confirmDismiss, setConfirmDismiss] = useState(false)
```

Add the import at the top of the file (after line 27):

```typescript
import { ApproveModal, MergeModal } from '../components/RadarReviewModals'
```

- [ ] **Step 2: Replace the promote button block (lines 448–456)**

```typescript
      {/* 8a. Founder review actions — any enriched item */}
      {item.enrichment_status === 'enriched' && onApprove && onDismiss && onMerge && (
        <div className="radar-review-actions">
          <button className="lyra-promote-btn" onClick={() => setShowApprove(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            Approve
          </button>
          <button className="radar-merge-btn" onClick={() => setShowMerge(true)}>
            Merge
          </button>
          {confirmDismiss ? (
            <button
              className="radar-dismiss-btn radar-dismiss-confirm"
              onClick={() => { setConfirmDismiss(false); onDismiss(item.id) }}
              onBlur={() => setConfirmDismiss(false)}
            >
              Confirm reject?
            </button>
          ) : (
            <button className="radar-dismiss-btn" onClick={() => setConfirmDismiss(true)}>
              Reject
            </button>
          )}
        </div>
      )}
      {showApprove && onApprove && (
        <ApproveModal
          item={item}
          onSubmit={(overrides) => onApprove(item.id, overrides)}
          onClose={() => setShowApprove(false)}
        />
      )}
      {showMerge && onMerge && (
        <MergeModal
          itemName={item.display_name}
          nearbyAnSite={item.nearby_an_site}
          onMerge={(siteId) => onMerge(item.id, siteId)}
          onClose={() => setShowMerge(false)}
        />
      )}
```

- [ ] **Step 3: Update the grid render call (~line 1010)**

Change:

```typescript
                               onPromote={isFounder ? handlePromote : undefined} />
```

to:

```typescript
                               onApprove={isFounder ? handleApprove : undefined}
                               onDismiss={isFounder ? handleDismiss : undefined}
                               onMerge={isFounder ? handleMerge : undefined} />
```

- [ ] **Step 4: Typecheck + build**

Run: `cd ancient-nerds-map && npx tsc --noEmit && npm run build`
Expected: clean typecheck, successful build

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/pages/LyraRadarPage.tsx
git commit -m "feat(radar-ui): founder review actions on radar cards"
```

---

### Task 9: CSS for actions row and modals

**Files:**
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.css` (append; reuse existing variable conventions — check how `.lyra-promote-btn` is styled there and match)

- [ ] **Step 1: Append styles**

```css
/* ── Founder review actions (2026-07 promotion upgrade) ───────────── */
.radar-review-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.radar-review-actions .lyra-promote-btn {
  margin-top: 0;
  flex: 1;
}

.radar-merge-btn,
.radar-dismiss-btn {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.radar-merge-btn:hover {
  border-color: rgba(120, 180, 255, 0.6);
  background: rgba(120, 180, 255, 0.12);
}

.radar-dismiss-btn:hover {
  border-color: rgba(255, 100, 100, 0.6);
  background: rgba(255, 100, 100, 0.12);
}

.radar-dismiss-confirm {
  border-color: rgba(255, 100, 100, 0.8);
  background: rgba(255, 100, 100, 0.2);
  color: #ff8a8a;
}

.radar-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.radar-modal {
  background: #16181d;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 20px;
  width: min(480px, 92vw);
  max-height: 88vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.radar-modal-title {
  margin: 0;
  font-size: 16px;
  color: #fff;
}

.radar-modal-hint {
  margin: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}

.radar-modal-warning {
  font-size: 12px;
  color: #ffc76e;
  background: rgba(255, 199, 110, 0.1);
  border: 1px solid rgba(255, 199, 110, 0.3);
  border-radius: 6px;
  padding: 8px 10px;
}

.radar-modal-row {
  display: flex;
  gap: 10px;
}

.radar-modal-row .radar-modal-label {
  flex: 1;
}

.radar-modal-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.radar-modal-input,
.radar-modal-textarea {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  color: #fff;
  padding: 7px 10px;
  font-size: 13px;
  font-family: inherit;
}

.radar-field-missing .radar-modal-input,
.radar-field-missing .radar-modal-textarea {
  border-color: rgba(255, 100, 100, 0.7);
}

.radar-modal-error {
  font-size: 12px;
  color: #ff8a8a;
}

.radar-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.radar-modal-btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.radar-modal-cancel {
  background: transparent;
  color: rgba(255, 255, 255, 0.7);
}

.radar-modal-confirm {
  background: var(--primary-red, #c02023);
  border-color: transparent;
  color: #fff;
}

.radar-modal-confirm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.radar-merge-result {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.04);
  color: #fff;
  cursor: pointer;
  text-align: left;
  font-size: 13px;
}

.radar-merge-result:hover {
  border-color: rgba(120, 180, 255, 0.6);
  background: rgba(120, 180, 255, 0.1);
}

.radar-merge-nearby {
  border-color: rgba(255, 199, 110, 0.5);
}

.radar-merge-meta {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
  white-space: nowrap;
}
```

Before committing: open `LyraRadarPage.css`, check how `.lyra-promote-btn` is defined, and adjust the new styles' colors/radii to match the page's existing conventions if they differ from the above.

- [ ] **Step 2: Build**

Run: `cd ancient-nerds-map && npm run build`
Expected: success

- [ ] **Step 3: Commit**

```bash
git add ancient-nerds-map/src/pages/LyraRadarPage.css
git commit -m "feat(radar-ui): styles for review actions and modals"
```

---

### Task 10: Full verification

- [ ] **Step 1: Full backend test suite**

Run: `python -m pytest tests/ -v --timeout=120 -x -q`
Expected: all pass (same set that passed before this work, plus the new test files)

- [ ] **Step 2: Lint both stacks**

Run: `ruff check api/ pipeline/ tests/` and `cd ancient-nerds-map && npm run lint` (if a lint script exists; otherwise `npx tsc --noEmit`)
Expected: clean

- [ ] **Step 3: Live-PG integration smoke (best effort, local docker compose)**

The guard tests mock the DB; this step exercises the REAL SQL (JSONB cast,
`ST_SetSRID`, alias inserts) against local PostGIS:

1. `docker compose up -d db redis` and wait for healthy.
2. Inspect the local DB: `docker compose exec db psql -U ancient_map -d ancient_map -c "\d user_contributions"`. If the local volume has no schema, create it from the ORM (`python -c "from pipeline.database import create_all_tables; create_all_tables()"` with `DATABASE_URL` pointed at localhost) — but note `unified_sites.geom` and the PostGIS extension must exist for promote; if the ORM cannot create them, STOP and record the smoke as not-run rather than faking it.
3. With `DATABASE_URL=postgresql://ancient_map:<pw from .env>@localhost:5432/ancient_map`, run a throwaway script that: overrides `require_founder` on the app, inserts one `user_contributions` row (`source='lyra'`, `enrichment_status='enriched'`, coords/country/type/description set, name `'__radar_smoke__'`), then via `TestClient`: promote with an override, assert 200 + row in `unified_sites`; insert a second candidate and dismiss it, assert status `dismissed`; insert a third and merge it into the just-promoted site, assert alias row in `unified_site_names` and status `matched`. Finally DELETE all `'__radar_smoke__%'` rows from `user_contributions`, `unified_site_names`, `unified_sites` (targeted deletes only — NEVER truncate/cascade).
4. Record pass/fail honestly in the final report.

- [ ] **Step 4: Spec cross-check**

Re-read `docs/superpowers/specs/2026-07-19-radar-promotion-upgrade-design.md` section by section and confirm each requirement maps to shipped code. Fix anything missed.

- [ ] **Step 5: Verify no unrelated files staged**

`git status` — the user's pre-existing uncommitted changes (`ancient-nerds-map/src/utils/exportFormats.ts`, `api/routes/sites.py`, untracked `scripts/*theo*` files) must NOT be committed.
