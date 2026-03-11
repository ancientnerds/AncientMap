# Research: Live Webcams at Archaeological Sites -- API & Programmatic Access

**Date:** 2026-03-09
**Status:** Complete

---

## Executive Summary

There is **one clear winner** for programmatic webcam integration: the **Windy Webcams API (v3)**. It is the only major webcam aggregator with a well-documented, free-tier REST API that supports geographic proximity searches -- making it ideal for querying webcams near known archaeological site coordinates. Beyond Windy, **Skyline Webcams** has the richest collection of cameras specifically at archaeological/heritage sites but lacks a public API (access requires reverse-engineering). The **NPS API** provides a dedicated `/webcams` endpoint for US national parks. **YouTube Data API v3** can find live streams at archaeological sites via keyword search.

---

## 1. Windy Webcams API (v3) -- RECOMMENDED PRIMARY SOURCE

**Website:** https://api.windy.com/webcams
**API Docs:** https://api.windy.com/webcams/api/v3/docs
**Status:** Active, well-documented, free tier available

### API Details

| Property | Value |
|----------|-------|
| Base URL | `https://api.windy.com/webcams/api/v3/webcams` |
| Auth | Header: `x-windy-api-key: YOUR_KEY` |
| Free tier | Yes (sign up at api.windy.com/webcams) |
| Paid tier | EUR 9,990/year (professional) |
| Database size | ~70,000+ webcams globally |
| Rate limits | Not explicitly published; free tier has offset cap of 1,000 |

### Key Endpoints

```
GET /webcams/api/v3/webcams              -- List webcams with filters
GET /webcams/api/v3/webcams/{webcamId}   -- Single webcam details
GET /webcams/api/v3/categories           -- List all categories
GET /webcams/api/v3/countries            -- Countries list
GET /webcams/api/v3/regions              -- Regions list
GET /webcams/api/v3/map/clusters         -- Map-optimized clusters
```

### Geographic Filtering (KEY FEATURE for archaeological sites)

**Nearby search** (best for us -- query by site coordinates):
```
GET /webcams/api/v3/webcams?nearby={lat},{lon},{radius_km}
```
- Max radius: 250km
- Example for Colosseum: `?nearby=41.8902,12.4922,2`

**Bounding box**:
```
GET /webcams/api/v3/webcams?bbox={north},{east},{south},{west}
```

### Available Categories (18 total)

airport, beach, building, city, coast, forest, indoor, lake, landscape, meteo, mountain, observatory, port, river, sportArea, square, traffic, village

**Note:** There is NO "archaeological" or "heritage" category. The approach is to use `nearby` with known site coordinates and optionally filter by `building`, `city`, or `landscape`.

### Include Parameters

```
?include=categories,images,location,player,urls
```

### Image URL Behavior

- Free tier: image URLs expire after **10 minutes** (token-secured)
- Professional tier: 24-hour expiry
- Must re-call the API on each page load to get fresh image URLs
- Free tier provides **low resolution** images only

### Response JSON Structure

```json
{
  "webcams": [
    {
      "webcamId": "1234567890",
      "status": "active",
      "title": "Rome - Colosseum",
      "viewCount": 50000,
      "lastUpdatedOn": "2026-03-09T12:00:00Z",
      "categories": [{"id": "building", "name": "Building"}],
      "location": {
        "city": {"name": "Rome"},
        "region": {"name": "Lazio"},
        "country": {"name": "Italy", "code": "IT"},
        "continent": {"name": "Europe", "code": "EU"},
        "latitude": 41.8902,
        "longitude": 12.4922
      },
      "images": {
        "current": {"icon": "...", "thumbnail": "...", "preview": "...", "toenail": "..."},
        "daylight": {"icon": "...", "thumbnail": "...", "preview": "...", "toenail": "..."}
      },
      "player": {
        "day": {"embed": "...", "link": "..."},
        "month": {"embed": "...", "link": "..."},
        "year": {"embed": "...", "link": "..."},
        "lifetime": {"embed": "...", "link": "..."}
      },
      "urls": {
        "detail": "https://www.windy.com/webcams/1234567890",
        "edit": "...",
        "provider": "..."
      }
    }
  ]
}
```

### Integration Strategy for AncientMap

For each site in `unified_sites`, query:
```
GET /webcams/api/v3/webcams?nearby={lat},{lon},5&include=images,location,player,urls&limit=10
```
This finds up to 10 webcams within 5km of each archaeological site. Cache results and re-fetch image URLs on page load (due to 10-min expiry).

### Attribution Requirement

Free tier requires crediting Windy as the image provider.

---

## 2. Skyline Webcams -- RICHEST ARCHAEOLOGICAL CONTENT (No Public API)

**Website:** https://www.skylinewebcams.com
**Status:** Active, extensive heritage coverage, but NO public API

### Archaeological/Heritage Sites Covered

Skyline Webcams has a dedicated **UNESCO World Heritage** category with 130+ cameras. Archaeological sites specifically include:

**Direct archaeological sites:**
- Colosseum, Rome (multiple angles)
- Acropolis / Parthenon, Athens (multiple angles)
- Petra -- The Treasury, Jordan
- Petra -- Visitor Center, Jordan
- Pyramids of Giza (multiple angles)
- Pyramids of Giza & Sphinx
- Temple Mount / Dome of the Rock, Jerusalem
- Western Wall, Jerusalem
- Largo di Torre Argentina (Roman temples), Rome
- Archaeological digs of Crustumerium, Rome
- Archaeological digs of Pyrgi (Etruscan), Lazio
- Machu Picchu / Aguas Calientes, Peru
- Easter Island, Chile
- Cappadocia -- Uchisar, Turkey
- Meteora, Greece
- Mount Athos, Greece
- Rhodes -- Ancient Ialysos, Kamiros
- Delos, Greece
- Paestum (Greek temples), Italy
- Castel Sant'Angelo, Rome
- Matera -- Sasso Caveoso (ancient cave dwellings)

**Cities with major archaeological significance:**
- Roman Forum area (multiple cameras)
- Athens panorama (Acropolis visible)
- Jerusalem panorama
- Rhodes Old Town (multiple cameras)
- Cusco, Peru (Plaza Mayor)

### URL Structure

```
https://www.skylinewebcams.com/en/webcam/{country}/{region}/{city}/{camera-slug}.html
```

Category pages:
```
https://www.skylinewebcams.com/en/live-cams-category/unesco-cams.html
```

### Programmatic Access (Reverse-Engineered)

**Static thumbnail** (refreshes every ~5 minutes):
```
https://cdn.skylinewebcams.com/live{camera_id}.jpg
https://cdn.skylinewebcams.com/{camera_id}.jpg  (offline fallback)
```

**Photo endpoint:**
```
https://photo.skylinewebcams.com/pht.php?pid={camera_id}&l=en
```

**HLS live stream** (requires session token):
```
https://hd-auth.skylinewebcams.com/live.m3u8?a={session_token}
```
- The `session_token` is extracted from page JavaScript (variable `livee.m3u8?a=<token>`)
- Requires `Origin: https://www.skylinewebcams.com` header
- Tokens rotate; not suitable for stable API integration

### Embed Options

- **Live video embed:** Restricted to webcam HOST only
- **5-minute photogram embed:** Available to anyone via "Embed" sharing button
- Embed code uses iframe from `embed.skylinewebcams.com`

### Practical Integration Approach

1. Maintain a **static mapping** of camera slugs to archaeological site IDs
2. Use CDN thumbnail URLs for preview images (refreshed every 5 min)
3. Link to the full Skyline Webcams page for live video
4. This is NOT an API approach; it requires manual curation

### Home Assistant Integration Reference

The [timmaurice/skyline-webcams](https://github.com/timmaurice/skyline-webcams) GitHub project demonstrates dynamic stream extraction from Skyline Webcams pages, parsing JavaScript to find current HLS stream URLs.

---

## 3. NPS (National Park Service) API -- US ARCHAEOLOGICAL SITES

**Website:** https://developer.nps.gov
**API Docs:** https://www.nps.gov/subjects/developer/api-documentation.htm
**Status:** Active, free, has `/webcams` endpoint

### API Details

| Property | Value |
|----------|-------|
| Base URL | `https://developer.nps.gov/api/v1/` |
| Auth | Query param: `api_key=YOUR_KEY` |
| Free tier | Yes (register at developer.nps.gov) |
| Rate limit | 1,000 requests/hour |
| Total webcams | ~290 across all NPS units |

### Webcam Endpoint

```
GET /api/v1/webcams?parkCode={code}&api_key=YOUR_KEY
GET /api/v1/webcams?limit=50&start=0&api_key=YOUR_KEY
```

### Response Structure

```json
{
  "total": "290",
  "data": [
    {
      "id": "...",
      "url": "https://www.nps.gov/...",
      "title": "Spruce Tree House Webcam",
      "description": "...",
      "images": [{"url": "https://www.nps.gov/common/uploads/webcam/ID.jpg", ...}],
      "relatedParks": [{"parkCode": "meve", "fullName": "Mesa Verde National Park", ...}],
      "status": "Active",
      "isStreaming": false,
      "tags": ["archaeology", "cliff dwelling"],
      "latitude": 37.1838,
      "longitude": -108.4887
    }
  ]
}
```

### Key Characteristics

- These are **static images that auto-refresh** (typically every 60 seconds), NOT video streams
- `isStreaming` is `false` for virtually all webcams
- Images served from NPS servers with predictable URL patterns
- Park codes for archaeological sites: `meve` (Mesa Verde), `chcu` (Chaco Culture), `band` (Bandelier), `casa` (Casa Grande Ruins), etc.

### Relevant Archaeological Park Codes

| Park Code | Site | Type |
|-----------|------|------|
| meve | Mesa Verde | Cliff dwellings |
| chcu | Chaco Culture | Great houses |
| band | Bandelier | Pueblo ruins |
| casa | Casa Grande Ruins | Hohokam |
| gicl | Gila Cliff Dwellings | Mogollon |
| azru | Aztec Ruins | Ancestral Pueblo |
| moca | Montezuma Castle | Sinagua |
| tuzi | Tuzigoot | Sinagua |
| wupa | Wupatki | Multiple cultures |

**Note:** Not all parks have webcams. Mesa Verde confirmed to have at least one (Spruce Tree House).

---

## 4. YouTube Data API v3 -- SEARCH FOR LIVE STREAMS

**Website:** https://developers.google.com/youtube/v3
**Status:** Active, free tier with quota

### Approach

Search for live streams at archaeological sites using keyword queries:

```
GET https://www.googleapis.com/youtube/v3/search
  ?part=snippet
  &q=Colosseum+live+webcam
  &type=video
  &eventType=live
  &key=YOUR_KEY
```

### API Details

| Property | Value |
|----------|-------|
| Auth | API key (for search) |
| Free tier | Yes (10,000 quota units/day) |
| Cost per search | 100 quota units |
| Max searches/day | ~100 on free tier |
| Embed | Standard YouTube iframe embed |

### Thumbnail URL Pattern

```
https://img.youtube.com/vi/{VIDEO_ID}/maxresdefault.jpg
https://img.youtube.com/vi/{VIDEO_ID}/hqdefault.jpg
```

### Embed Pattern

```html
<iframe src="https://www.youtube.com/embed/{VIDEO_ID}?autoplay=1" ...></iframe>
```

### Limitations

- Live streams come and go; not guaranteed to be running
- Search results are not curated -- may return unrelated content
- 100 queries/day limit on free tier is low for scanning many sites
- Better as a supplementary source rather than primary

### Practical Approach

Run a periodic batch job (daily) to search for live streams near known archaeological sites, cache results, and display when available.

---

## 5. EarthCam -- COMMERCIAL ONLY (No Free API)

**Website:** https://www.earthcam.com (public cams) / https://www.earthcam.net (enterprise)
**API Docs:** https://www.earthcam.net/api/ (marketing page only)
**Status:** Active, but enterprise/commercial API only

### Key Facts

- EarthCam has a REST API with embed players, archive access, AI analytics
- API access requires **direct contact** with EarthCam sales team
- No public documentation; only a marketing page describing capabilities
- The "Broadway Media Player" widget has 720+ customization options
- Primarily targeted at construction monitoring, not tourism/heritage
- Their public website (earthcam.com) shows some tourism cams but without API access
- **Cost:** Undisclosed, expected to be significant (enterprise pricing)

### Archaeological Coverage

EarthCam's public website has some historical/tourism cameras but the selection is limited compared to Skyline Webcams. No specific archaeological site category exists.

**Verdict:** Not viable for free/open-source integration.

---

## 6. earthTV -- LIMITED ACCESS

**Website:** https://www.earthtv.com
**Status:** Active but no public API

### Coverage

earthTV has webcams at some notable locations including:
- Athens Acropolis (from COCO-MAT Hotel)
- Various European cities

### Access

- No documented public API
- Embed options not publicly available
- Content appears to require licensing agreements
- Smaller network than Skyline Webcams or Windy

**Verdict:** Not suitable for programmatic integration.

---

## 7. Other Aggregators & Directories

### WebcamTaxi (webcamtaxi.com)
- Curated directory of webcams organized by country/region
- Has a "Museums" category and coverage in archaeologically-rich regions
- **No public API**
- Links to third-party streams (YouTube, Skyline, etc.)

### WorldCam (worldcam.eu)
- Webcam aggregator with map interface
- Appears to have some JSON data endpoints
- Coverage of archaeological sites (Colosseum, Giza, Acropolis, etc.)
- **No documented public API**

### GOandROAM (goandroam.com)
- Specifically has a "World Heritage" webcam category
- 2,000+ webcams sorted by country and type
- **No public API**

### WhatsUpCams (whatsupcams.com)
- Has webcams at Pyramids of Giza, Rome, Venice, etc.
- Offers embed capability
- **No documented API**

### Insecam (insecam.org)
- Directory of unsecured surveillance cameras (~2,000+)
- Can browse by country/city
- **Ethical concerns** -- cameras are unsecured, not intentionally public
- Extremely unlikely to have curated archaeological coverage
- **Not recommended for this use case**

### Stonehenge Skyscape (stonehengeskyscape.co.uk)
- Official English Heritage webcam at Stonehenge
- Shows sky/sun alignment from within the stone circle
- Appears to be a standalone webapp, no API
- Could potentially be iframe-embedded

### acropolis.gr
- Official Acropolis webcam
- No documented API or embed code
- Powered by "Hop in Sightseeing"

---

## 8. Government/Institutional Cameras

### US National Park Service
See Section 3 above. The NPS API is the only government source with a proper API endpoint for webcams.

### Italian Ministry of Culture
- No centralized webcam system found for Italian archaeological parks
- Individual parks may partner with Skyline Webcams (e.g., Crustumerium, Pyrgi)
- The Parco Archeologico di Pompei does NOT appear to run its own public webcam

### Greek Archaeological Service
- No centralized webcam system
- The official acropolis.gr site has a webcam but no API
- Coverage is primarily through third-party services (Skyline, earthTV)

### Jordanian Tourism
- Petra webcams are provided by Skyline Webcams, not the Jordanian government

---

## 9. Recommended Integration Architecture for AncientMap

### Tier 1: Windy API (Primary, Automated)

```
For each site in unified_sites:
  1. Query Windy API: nearby={lat},{lon},5km
  2. Cache webcam IDs and metadata in DB
  3. On frontend load, fetch fresh image URLs (10-min expiry)
  4. Display thumbnail + link to Windy player
```

**Advantages:** Automated discovery, geographic search, proper API
**Disadvantages:** No archaeological category; many results will be unrelated; low-res images on free tier

### Tier 2: Curated Skyline Webcams (Manual, High Quality)

```
Maintain a mapping table:
  site_id (unified_sites) -> skyline_webcam_slug -> camera_id

For each mapped site:
  1. Show CDN thumbnail: cdn.skylinewebcams.com/live{id}.jpg
  2. Link to full page: skylinewebcams.com/en/webcam/{slug}.html
```

**Advantages:** Best quality, best archaeological coverage, direct relevance
**Disadvantages:** Manual curation, no API, thumbnails may break if IDs change

### Tier 3: NPS Webcams (US Sites Only)

```
For US archaeological parks:
  1. Query NPS API by parkCode
  2. Cache image URLs (refresh every 60s)
  3. Show static snapshot with link to NPS page
```

### Tier 4: YouTube Live (Supplementary)

```
Periodic batch job (daily):
  1. Search YouTube for live streams at top sites
  2. Cache video IDs that are currently live
  3. Show YouTube thumbnail + embed on site detail page
```

### Proposed Database Table

```sql
CREATE TABLE site_webcams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID REFERENCES unified_sites(id) ON DELETE SET NULL,
    source TEXT NOT NULL,          -- 'windy', 'skyline', 'nps', 'youtube', 'custom'
    external_id TEXT NOT NULL,     -- webcam/video ID on the source platform
    title TEXT,
    thumbnail_url TEXT,            -- may be ephemeral (Windy)
    player_url TEXT,               -- link to watch live
    embed_url TEXT,                -- embeddable URL if available
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    distance_km DOUBLE PRECISION,  -- distance from site
    is_active BOOLEAN DEFAULT true,
    last_checked TIMESTAMPTZ,
    metadata JSONB,                -- source-specific extra data
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_site_webcams_site ON site_webcams(site_id);
CREATE INDEX idx_site_webcams_source ON site_webcams(source);
CREATE UNIQUE INDEX idx_site_webcams_unique ON site_webcams(source, external_id);
```

---

## 10. Coverage Matrix -- Major Archaeological Sites

| Site | Windy Nearby | Skyline | NPS | YouTube | Notes |
|------|-------------|---------|-----|---------|-------|
| Colosseum, Rome | Likely | YES (multiple) | -- | Likely | Best: Skyline |
| Acropolis, Athens | Likely | YES (multiple) | -- | Likely | Also: earthTV, acropolis.gr |
| Petra, Jordan | Possible | YES (2 cams) | -- | Unlikely | Skyline is only reliable source |
| Pyramids of Giza | Possible | YES (3+ cams) | -- | Possible | Also: WhatsUpCams |
| Machu Picchu | Possible | YES (1 cam) | -- | Unlikely | Aguas Calientes view |
| Stonehenge | Possible | Not found | -- | Unlikely | English Heritage has own cam |
| Roman Forum | Likely | YES (nearby) | -- | Likely | Largo di Torre Argentina |
| Pompeii | Possible | Nearby (Vesuvius) | -- | Unlikely | No direct Pompeii excavation cam |
| Western Wall, Jerusalem | Likely | YES | -- | Likely | |
| Temple Mount, Jerusalem | Likely | YES | -- | Likely | |
| Mesa Verde, US | Possible | No | YES | Unlikely | NPS webcam at Spruce Tree House |
| Chaco Canyon, US | Possible | No | Possible | Unlikely | Check NPS |
| Easter Island | Unlikely | YES | -- | Unlikely | Remote; Skyline has one cam |
| Cappadocia | Possible | YES | -- | Possible | Uchisar view |
| Meteora | Possible | YES | -- | Possible | |
| Delos, Greece | Unlikely | Possible | -- | Unlikely | Small island |
| Angkor Wat | Unlikely | Not found | -- | Possible | Limited webcam coverage |
| Chichen Itza | Unlikely | Not found | -- | Unlikely | No known webcams |
| Teotihuacan | Unlikely | Not found | -- | Unlikely | No known webcams |
| Baalbek | Unlikely | Not found | -- | Unlikely | No known webcams |
| Karnak/Luxor | Possible | Not found | -- | Possible | Some Egypt webcams exist |

---

## 11. API Keys & Setup

### Windy Webcams API
1. Go to https://api.windy.com/webcams
2. Click "Get API Key" (free tier)
3. Use header: `x-windy-api-key: YOUR_KEY`

### NPS API
1. Go to https://developer.nps.gov
2. Register for free API key
3. Use query param: `?api_key=YOUR_KEY`
4. Rate limit: 1,000 req/hour

### YouTube Data API v3
1. Go to https://console.cloud.google.com
2. Enable YouTube Data API v3
3. Create API key
4. 10,000 quota units/day (search costs 100 units each)

---

## Sources

- Windy Webcams API Docs: https://api.windy.com/webcams/api/v3/docs
- Windy Webcams Pricing: https://api.windy.com/webcams
- Windy Community Forums: https://community.windy.com/category/31/webcams-api
- EarthCam API (marketing): https://www.earthcam.net/api/
- Skyline Webcams FAQ: https://www.skylinewebcams.com/en/support/faq.html
- Skyline UNESCO Category: https://www.skylinewebcams.com/en/live-cams-category/unesco-cams.html
- NPS Developer Resources: https://www.nps.gov/subjects/developer/
- NPS API Guides: https://www.nps.gov/subjects/developer/guides.htm
- Mesa Verde Webcams: https://www.nps.gov/meve/learn/photosmultimedia/webcam.htm
- YouTube Data API: https://developers.google.com/youtube/v3
- YouTube Search API: https://developers.google.com/youtube/v3/docs/search
- Skyline Webcams HA Integration: https://github.com/timmaurice/skyline-webcams
- yt-dlp Skyline extractor issues: https://github.com/yt-dlp/yt-dlp/issues/7115
- GOandROAM Heritage Webcams: https://www.goandroam.com/webcams/cams:worldheritage
- English Heritage Stonehenge Skyscape: https://www.english-heritage.org.uk/visit/places/stonehenge/things-to-do/stone-circle/skyscape/
- Acropolis.gr Live Webcam: https://www.acropolis.gr/live-web-camera.php
- earthTV Athens Acropolis: https://www.earthtv.com/en/webcam/athens-acropolis
- Windy MCP Server (reference): https://github.com/Cyreslab-AI/windy-webcams-mcp-server
