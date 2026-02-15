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
| limit       | int      | 50000   | Max results (capped at 50K)    |

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

### Lyra AI Chat

Lyra is an AI research assistant powered by MiniMax M2.5. It uses a tool-based agent
architecture with site search, news lookup, and map navigation capabilities. Responses are
streamed via Server-Sent Events (SSE) with a 5-minute maximum connection duration.

#### POST /api/lyra/chat

Chat with Lyra. Requires Cloudflare Turnstile token. Rate limited to 20 requests/hour/IP.

**Request Body:**
```json
{
  "message": "Tell me about Göbekli Tepe",
  "turnstile_token": "cloudflare-token...",
  "context_type": "global",
  "context_id": null,
  "context_year": null,
  "history": [],
  "images": []
}
```

| Field           | Type         | Constraints       | Description                                    |
|-----------------|--------------|-------------------|------------------------------------------------|
| message         | string       | 1-4000 chars      | User's question                                |
| turnstile_token | string       | required          | Cloudflare Turnstile verification token        |
| context_type    | string       | default: "global" | Where chat was opened: global, site, empire, news |
| context_id      | string\|null | max 100 chars     | UUID of site, empire polity ID, or news item   |
| context_year    | int\|null    |                   | Year for empire context                        |
| history         | list\|null   | max 50 items      | Conversation history [{role, content}]         |
| images          | list\|null   | max 5 items       | Base64 images [{data: "data:image/..."}]       |

**SSE Events:**

```
event: token
data: {"type": "token", "content": "Göbekli Tepe is a "}

event: sites
data: {"type": "sites", "sites": [{"id": "...", "name": "Göbekli Tepe", "lat": 37.22, "lon": 38.92}]}

event: news
data: {"type": "news", "items": [...]}

event: done
data: {"type": "done"}

event: error
data: {"type": "error", "error": "Response time limit reached"}
```

**Error Responses:**
- `403`: Turnstile verification failed
- `429`: Rate limit exceeded (20/hour)

---

#### POST /api/lyra/admin

Admin chat with Lyra. No Turnstile or rate limit. Requires `Authorization: Bearer <LYRA_ADMIN_KEY>`.

Same request body as `/lyra/chat` minus `turnstile_token`.

**Error Responses:**
- `401`: Missing Authorization header
- `403`: Invalid admin key
- `503`: LYRA_ADMIN_KEY not configured

---

#### POST /api/lyra/admin/verify

Lightweight key verification (no LLM call). Used by frontend auth gate.

**Headers:** `Authorization: Bearer <LYRA_ADMIN_KEY>`

**Response:** `{"verified": true}`

---

### Lyra Radar

The Radar shows archaeological sites discovered by the Lyra pipeline that aren't yet in the main database.

#### GET /api/radar/

Get radar items (paginated, cached 5 minutes).

**Query Parameters:**
| Parameter | Type   | Default   | Description                    |
|-----------|--------|-----------|--------------------------------|
| page      | int    | 1         | Page number                    |
| per_page  | int    | 20        | Items per page (max 50)        |
| status    | string | all       | Filter: enriched, promoted, pending |
| sort      | string | score     | Sort by: score, name, mentions |

---

#### GET /api/radar/stats

Get radar statistics (counts by status, recent promotions).

---

#### POST /api/radar/cache-bust

Invalidate radar cache. Called by pipeline after processing.

**Headers:** `Authorization: Bearer <LYRA_ADMIN_KEY>` (required; returns 503 if key not configured)

---

### News Feed

#### GET /api/news/feed

Get curated archaeological news posts.

**Query Parameters:**
| Parameter | Type     | Default | Description                       |
|-----------|----------|---------|-----------------------------------|
| limit     | int      | 20      | Max items                         |
| offset    | int      | 0       | Pagination offset                 |
| category  | string   | all     | Filter by news_category           |
| site_id   | string   | null    | Filter by linked site UUID        |

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

| Endpoint           | Limit              | Window | Mechanism        |
|--------------------|--------------------|--------|------------------|
| POST /lyra/chat    | 20 requests        | 1 hour | Per-IP in-memory |
| POST /lyra/admin   | Unlimited          | -      | Bearer token auth|
| GET /sites/all     | No explicit limit  | -      | Response cached  |
| GET /radar/        | No explicit limit  | -      | Response cached  |

The Lyra chat rate limit is configurable via the `LYRA_RATE_LIMIT` environment variable.

SSE streams have a maximum duration of 5 minutes. Connections exceeding this receive
an error event and are terminated.

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
