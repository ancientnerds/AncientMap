# API Documentation

Base URL: `http://localhost:8000/api` (development)

## Overview

The Ancient Nerds Map API provides access to 800K+ archaeological sites with
spatial queries, filtering, and AI-powered search capabilities.

## Authentication

Most endpoints are public. AI chat features require PIN-based authentication.

## Endpoints

### Sites

#### GET /api/sites/all

Get all sites as compact JSON for globe rendering.

**Query Parameters:**
| Parameter   | Type     | Default | Description                    |
|-------------|----------|---------|--------------------------------|
| source      | string[] | all     | Filter by source IDs           |
| site_type   | string   | all     | Filter by site type            |
| period_max  | int      | all     | Maximum period year            |
| skip        | int      | 0       | Pagination offset              |
| limit       | int      | 50000   | Max results (capped at 1M)     |

**Response:**
```json
{
  "count": 50000,
  "sites": [
    {
      "id": "uuid",
      "n": "Site Name",
      "la": 41.9028,
      "lo": 12.4964,
      "s": "pleiades",
      "t": "settlement",
      "p": -500,
      "pn": "500 BC - 1 AD",
      "d": "Description...",
      "i": "https://image.url/thumb.jpg",
      "c": "Italy",
      "u": "https://source.url"
    }
  ],
  "dataSource": "postgres"
}
```

**Field Abbreviations:**
- `n`: name
- `la`: latitude
- `lo`: longitude
- `s`: source_id
- `t`: site_type
- `p`: period_start (year)
- `pn`: period_name
- `d`: description
- `i`: image URL
- `c`: country
- `u`: source URL

---

#### GET /api/sites/viewport

Get sites within a bounding box.

**Query Parameters:**
| Parameter | Type     | Required | Description          |
|-----------|----------|----------|----------------------|
| min_lat   | float    | Yes      | Minimum latitude     |
| max_lat   | float    | Yes      | Maximum latitude     |
| min_lon   | float    | Yes      | Minimum longitude    |
| max_lon   | float    | Yes      | Maximum longitude    |
| source    | string[] | No       | Filter by source IDs |
| limit     | int      | No       | Max results (50000)  |

---

#### GET /api/sites/clustered

Get sites clustered by H3 hexagons.

**Query Parameters:**
| Parameter  | Type     | Default | Description                |
|------------|----------|---------|----------------------------|
| resolution | int      | 3       | H3 resolution (0-7)        |
| source     | string[] | all     | Filter by source IDs       |

**Response:**
```json
{
  "resolution": 3,
  "cluster_count": 1234,
  "clusters": [
    {
      "la": 41.9,
      "lo": 12.5,
      "c": 150,
      "s": "pleiades"
    }
  ]
}
```

---

#### GET /api/sites/{site_id}

Get full details for a single site.

**Response:**
```json
{
  "id": "uuid",
  "sourceId": "pleiades",
  "sourceRecordId": "123456",
  "name": "Roma",
  "lat": 41.9028,
  "lon": 12.4964,
  "type": "settlement",
  "periodStart": -753,
  "periodEnd": 476,
  "periodName": "Iron Age - Late Antiquity",
  "country": "Italy",
  "description": "Capital of the Roman Empire...",
  "thumbnailUrl": "https://...",
  "sourceUrl": "https://pleiades.stoa.org/places/...",
  "rawData": { ... }
}
```

---

#### PUT /api/sites/{site_id}

Update a site's details (requires authentication).

**Request Body:**
```json
{
  "title": "Updated Name",
  "location": "Rome, Italy",
  "category": "settlement",
  "period": "500 BC - 1 AD",
  "description": "Updated description...",
  "sourceUrl": "https://example.com",
  "coordinates": [12.4964, 41.9028]
}
```

---

### Sources

#### GET /api/sources

Get all available data sources.

**Response:**
```json
{
  "sources": [
    {
      "id": "pleiades",
      "name": "Pleiades",
      "description": "Ancient Mediterranean gazetteer",
      "count": 38000,
      "license": "CC-BY 3.0"
    }
  ]
}
```

---

### AI Chat

#### POST /api/ai/verify

Verify PIN and create session.

**Request Body:**
```json
{
  "pin": "1234",
  "turnstile_token": "cloudflare-token..."
}
```

**Response:**
```json
{
  "verified": true,
  "session_token": "abc123...",
  "expires_in": 3600,
  "connected": true,
  "users_connected": 1
}
```

**Error Responses:**
- `invalid_pin`: PIN not recognized
- `ip_locked`: Too many failed attempts
- `captcha_failed`: Turnstile verification failed

---

#### GET /api/ai/stream

Stream chat response using Server-Sent Events.

**Query Parameters:**
| Parameter     | Type   | Required | Description                     |
|---------------|--------|----------|---------------------------------|
| session_token | string | Yes      | Token from /verify              |
| message       | string | Yes      | User's question (1-2000 chars)  |
| sources       | string | No       | Comma-separated source IDs      |
| mode          | string | No       | "chat" or "research"            |

**SSE Events:**

```
event: queued
data: {"position": 2}

event: processing
data: {"status": "starting"}

event: token
data: {"content": "The "}

event: sites
data: {"sites": [{"id": "...", "name": "...", "lat": 41.9, "lon": 12.5}]}

event: done
data: {"metadata": {"model": "qwen2.5:3b", "mode": "chat"}}

event: error
data: {"error": "Error message"}
```

---

#### POST /api/ai/disconnect

Disconnect user and free up slot.

**Query Parameters:**
| Parameter     | Type   | Required | Description        |
|---------------|--------|----------|--------------------|
| session_token | string | Yes      | Token from /verify |

---

#### GET /api/ai/access-status

Get current access control status.

**Response:**
```json
{
  "connected_users": 3,
  "pins_in_use": 3,
  "queue_length": 1,
  "inference_active": true
}
```

---

#### GET /api/ai/modes

Get available AI modes.

**Response:**
```json
{
  "chat": {
    "name": "Chat",
    "description": "Fast responses",
    "model": "qwen2.5:3b",
    "max_tokens": 500
  },
  "research": {
    "name": "Research",
    "description": "Detailed analysis",
    "model": "qwen2.5:7b",
    "max_tokens": 2000
  }
}
```

---

#### GET /api/ai/health

Check AI service health.

**Response:**
```json
{
  "status": "healthy",
  "vector_store": {
    "status": "connected",
    "collections": 5
  },
  "llm": {
    "status": "connected",
    "model": "qwen2.5:3b"
  }
}
```

---

### Statistics

#### GET /api/stats

Get database statistics (cached 5 minutes).

**Response:**
```json
{
  "total_sites": 800000,
  "by_source": {
    "pleiades": 38000,
    "dare": 15000,
    "unesco": 1200
  }
}
```

---

### Contributions

#### GET /api/contributions

Get user contributions.

#### POST /api/contributions

Submit a new site contribution.

---

### Open Graph

#### GET /api/og/{site_id}

Get Open Graph metadata for social sharing.

---

### Sitemap

#### GET /api/sitemap/index.xml

Get XML sitemap index.

#### GET /api/sitemap/sites-{page}.xml

Get paginated site URLs for search engines.

---

### Street View

#### GET /api/streetview/check

Check if Street View is available for coordinates.

**Query Parameters:**
| Parameter | Type  | Required | Description |
|-----------|-------|----------|-------------|
| lat       | float | Yes      | Latitude    |
| lon       | float | Yes      | Longitude   |

---

## Rate Limiting

| Tier       | Requests/Day |
|------------|--------------|
| Anonymous  | 100          |
| Free       | 1,000        |
| Pro        | 50,000       |
| Enterprise | Unlimited    |

Rate limit headers are included in responses:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error description"
}
```

| Status Code | Description              |
|-------------|--------------------------|
| 400         | Bad request              |
| 401         | Unauthorized             |
| 403         | Forbidden                |
| 404         | Not found                |
| 429         | Rate limit exceeded      |
| 500         | Internal server error    |
| 503         | Service unavailable      |

---

## CORS

The API allows requests from configured origins:
- `http://localhost:5173` (Vite dev)
- `http://localhost:3000`

Production origins should be configured in `.env`.
