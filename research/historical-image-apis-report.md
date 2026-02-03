# Comprehensive Report: Image APIs and Sources for Historical Sites and Archaeological Locations

**Date:** January 30, 2026
**Purpose:** Research compilation for AncientMap interactive historical map application

---

## Executive Summary

This report identifies and evaluates over 30 image sources and APIs suitable for displaying photos of historical sites, archaeological locations, ancient monuments, and heritage locations. The sources are categorized by type, with detailed information on API availability, pricing, rate limits, coverage quality, and integration considerations.

**Key Findings:**
- **Best free options for historical coverage:** Wikimedia Commons, Europeana, Smithsonian Open Access, Metropolitan Museum of Art
- **Best for location-based queries:** Wikimedia Commons GeoSearch, Flickr, Mapillary
- **Best for cultural heritage depth:** Europeana, DPLA, ARIADNE, Getty Open Content
- **Best for ease of integration:** Unsplash, Pexels, Pixabay (general stock), Met Museum API

---

## 1. Free/Open Image APIs and Sources

### 1.1 Wikimedia Commons (MediaWiki API)

**URL:** https://commons.wikimedia.org/
**API Documentation:** https://commons.wikimedia.org/wiki/Commons:API

**API Availability:** Yes, Free
**Authentication:** None required for read operations; User-Agent header recommended

**Key Features:**
- **GeoSearch API** for location-based queries
- Over 100 million media files
- Excellent coverage of historical sites worldwide
- Multiple image resolutions available

**Rate Limits:**
- No hard speed limit on read requests
- Recommended: Make requests in series, not parallel
- Use batch requests with pipe character (|) for efficiency
- Bot/Admin accounts have no rate limits

**Query by Location:**
```
https://commons.wikimedia.org/w/api.php?action=query&list=geosearch&gscoord=LAT|LON&gsradius=500&gsnamespace=6&gsprimary=all&format=json
```

**Query with Thumbnails:**
```
https://commons.wikimedia.org/w/api.php?action=query&generator=geosearch&ggsprimary=all&ggsnamespace=6&ggsradius=500&ggscoord=51.5|11.95&prop=imageinfo&iiprop=url&iiurlwidth=200&format=json
```

**Coverage Quality:** Excellent for historical sites, especially well-documented locations
**Licensing:** Various Creative Commons licenses, check per image

---

### 1.2 Unsplash API

**URL:** https://unsplash.com/developers
**API Documentation:** https://unsplash.com/documentation

**API Availability:** Yes, Free with limits
**Authentication:** API key required

**Rate Limits:**
- **Demo:** 50 requests/hour
- **Production:** 5,000 requests/hour (requires approval)
- Image file requests (images.unsplash.com) do not count against limit

**Terms of Use:**
- Must attribute Unsplash and photographer
- Must hotlink images (use returned URLs)
- Must trigger download tracking endpoint when user selects image
- Dynamic image URLs via Imgix for resizing/cropping

**Query by Keyword:**
```
GET https://api.unsplash.com/search/photos?query=ancient+ruins&client_id=YOUR_KEY
```

**Coverage Quality:** Good general coverage, less specialized for archaeology
**Licensing:** Unsplash License (free for commercial and non-commercial use)

---

### 1.3 Pexels API

**URL:** https://www.pexels.com/api/
**API Documentation:** https://www.pexels.com/api/documentation/

**API Availability:** Yes, Free
**Authentication:** API key required

**Rate Limits:**
- **Default:** 200 requests/hour, 20,000 requests/month
- **Unlimited:** Available free with proper attribution (requires approval)
- Maximum 80 results per request

**Terms of Use:**
- Must show prominent link to Pexels
- Credit photographers when possible
- Format: "Photo by John Doe on Pexels"

**Query Example:**
```
GET https://api.pexels.com/v1/search?query=archaeological+site&per_page=15
Authorization: YOUR_API_KEY
```

**Coverage Quality:** Moderate for historical sites, better for general landmarks
**Licensing:** Pexels License (free for all purposes)

---

### 1.4 Pixabay API

**URL:** https://pixabay.com/api/docs/
**API Documentation:** https://pixabay.com/api/docs/

**API Availability:** Yes, Free
**Authentication:** API key required

**Rate Limits:**
- 100 requests per 60 seconds per API key
- Results must be cached for 24 hours
- Higher limits available upon request with proper implementation

**Terms of Use:**
- No permanent hotlinking (must download to own server)
- Must show attribution to Pixabay
- No mass automated downloads

**Query Example:**
```
GET https://pixabay.com/api/?key=YOUR_KEY&q=ancient+monument&category=places&image_type=photo
```

**Categories Available:** places, travel, buildings (relevant for historical sites)

**Coverage Quality:** Good stock photography, 20,000+ historical site images
**Licensing:** Pixabay License (free for commercial use, no attribution required)

---

### 1.5 Flickr API

**URL:** https://www.flickr.com/services/api/
**API Documentation:** https://www.flickr.com/services/api/flickr.photos.search.html

**API Availability:** Yes, Free
**Authentication:** API key required, OAuth for write operations

**Rate Limits:**
- 3,600 queries per hour per API key
- Geo queries return max 250 results per page
- Geo queries require limiting agent (tag, date, etc.)

**Key Methods for Historical Sites:**

**Search by Bounding Box:**
```
flickr.photos.search
&bbox=min_lon,min_lat,max_lon,max_lat
&has_geo=1
```

**Search by Coordinates:**
```
flickr.photos.geo.photosForLocation
&lat=LATITUDE&lon=LONGITUDE&accuracy=16
```

**Accuracy Levels:** 1 (World) to 16 (Street level)

**Terms of Use:**
- Free accounts: Original/large images (>1024px) restricted via API
- SSL required
- Must authenticate users via Flickr (no password handling)

**Coverage Quality:** Excellent user-contributed content, strong archaeological coverage
**Licensing:** Various (check per photo), many CC-licensed

---

### 1.6 Google Places Photos API

**URL:** https://developers.google.com/maps/documentation/places/web-service/place-photos
**API Documentation:** https://developers.google.com/maps/documentation/places/web-service/usage-and-billing

**API Availability:** Yes, Paid (with free tier)
**Authentication:** API key required

**Pricing:**
- $200 monthly free credit
- Pay-as-you-go after credit exhausted
- Photo requests have separate SKU pricing

**Rate Limits:**
- Per API method per project
- Contact support for quota increases
- Load photos on demand to avoid HTTP 429

**Query Process:**
1. Get place ID via Place Search
2. Get photo references via Place Details
3. Fetch photos using photo reference

**Request Format:**
```
https://places.googleapis.com/v1/NAME/media?key=API_KEY&maxHeightPx=400&maxWidthPx=400
```

**Coverage Quality:** Excellent for tourist locations and landmarks
**Licensing:** Google Terms of Service, attribution required

---

### 1.7 Openverse (Creative Commons Search)

**URL:** https://openverse.org/
**API Documentation:** https://docs.openverse.org/

**API Availability:** Yes, Free
**Authentication:** Optional (rate limits differ)

**Coverage:**
- 800+ million images and audio tracks
- Aggregates from Smithsonian, Cleveland Museum, NASA, NYPL, and more
- All content is CC-licensed or public domain

**Key Features:**
- Filter by license type
- One-click attribution generation
- Multiple source aggregation

**Query Example:**
```
GET https://api.openverse.org/v1/images/?q=archaeological+site
```

**Coverage Quality:** Very good aggregated coverage from cultural institutions
**Licensing:** Various CC licenses and public domain

---

## 2. Cultural Heritage and Museum APIs

### 2.1 Europeana API

**URL:** https://www.europeana.eu/en
**API Documentation:** https://apis.europeana.eu/en

**API Availability:** Yes, Free
**Authentication:** API key required (free registration)

**APIs Available:**
- **Search API:** Search across all metadata
- **Record API:** Direct access to item metadata and media
- **Entity API:** Search named entities (people, places, time periods)
- **IIIF APIs:** Image interoperability framework access

**Coverage:**
- 50+ million cultural heritage items
- 4,000+ cultural institutions across Europe
- Books, paintings, 3D objects, audiovisual material
- Strong archaeological and monument coverage

**Query by Location:**
```
GET https://api.europeana.eu/record/v2/search.json?wskey=YOUR_KEY&query=*&qf=pl_wgs84_pos_lat:[41 TO 42]&qf=pl_wgs84_pos_long:[12 TO 13]
```

**3D Content:** 3D-ICONS project includes digitized architectural and archaeological masterpieces

**Coverage Quality:** Excellent for European cultural heritage
**Licensing:** Various (indicated per item), many CC-licensed

---

### 2.2 Digital Public Library of America (DPLA) API

**URL:** https://dp.la/
**API Documentation:** https://pro.dp.la/developers/api-codex

**API Availability:** Yes, Free
**Authentication:** API key required

**Base URL:** https://api.dp.la/v2

**Resource Types:**
- Items (books, photographs, videos, etc.)
- Collections (logical groupings)

**Coverage:**
- Aggregates from US libraries, archives, and museums
- Metadata with links to original sources
- Includes photographs, images, texts, sounds

**Query Example:**
```
GET https://api.dp.la/v2/items?q=archaeological+site&api_key=YOUR_KEY
```

**Bulk Download:** Available for analytics and research

**Coverage Quality:** Good US-focused cultural heritage
**Licensing:** Metadata freely reusable, check individual items for media rights

---

### 2.3 Smithsonian Open Access API

**URL:** https://www.si.edu/openaccess
**API Documentation:** https://www.si.edu/openaccess/devtools

**API Availability:** Yes, Free
**Authentication:** API key via api.data.gov

**Coverage:**
- 5.1+ million 2D and 3D digital items
- 21 museums, 9 research centers
- 2.8+ million CC0 images (no restrictions)
- Archaeological, anthropological, and historical collections

**Data Access:**
- API via api.data.gov
- GitHub repository with JSON data
- 11+ million metadata records

**Query Example:**
```
GET https://api.si.edu/openaccess/api/v1.0/search?q=archaeology&api_key=YOUR_KEY
```

**Coverage Quality:** Excellent breadth across disciplines
**Licensing:** CC0 (public domain) for designated images

---

### 2.4 Metropolitan Museum of Art API

**URL:** https://metmuseum.github.io/
**API Documentation:** https://metmuseum.github.io/

**API Availability:** Yes, Free
**Authentication:** None required

**Endpoints:**
- `/objects` - All object IDs
- `/objects/[id]` - Single object details
- `/departments` - Department listing
- `/search` - Keyword search

**Coverage:**
- 470,000+ artworks
- 406,000+ images
- Strong antiquities and archaeological collections

**Response Fields:**
- `primaryImage` - Full resolution URL
- `primaryImageSmall` - Web-optimized URL
- `additionalImages` - Array of additional images

**Query Examples:**
```
GET https://collectionapi.metmuseum.org/public/collection/v1/search?q=egyptian+tomb
GET https://collectionapi.metmuseum.org/public/collection/v1/objects/[objectID]
```

**Coverage Quality:** Excellent for ancient civilizations and art
**Licensing:** CC0 for public domain works

---

### 2.5 Getty Open Content / Getty API

**URL:** https://www.getty.edu/projects/open-content-program/
**API Documentation:** https://data.getty.edu/

**API Availability:** Yes, Free
**Authentication:** Varies by API

**Open Content Program:**
- 160,000+ images of public domain artwork
- Greek and Roman antiquities
- Illuminated manuscripts
- 19th-century photographs
- Maps and prints

**APIs Available:**
- Getty Vocabularies (AAT, TGN, ULAN)
- Museum Collection API
- Research Institute data

**Coverage Quality:** Excellent for classical antiquities
**Licensing:** CC0 for public domain works

---

### 2.6 Cleveland Museum of Art Open Access API

**URL:** https://openaccess-api.clevelandart.org/
**API Documentation:** https://www.clevelandart.org/open-access-api

**API Availability:** Yes, Free
**Authentication:** None required

**Coverage:**
- 64,000+ artwork records
- 37,000+ images
- 36+ metadata fields per work
- Full-sized, uncompressed images available

**Data Formats:**
- REST API
- JSON download via GitHub
- CSV download available

**Usage Statistics (2024):**
- 6 million views on Collection Online
- 47 million API downloads
- 300+ million views on Wikimedia

**Coverage Quality:** Strong ancient art collection
**Licensing:** CC0 (public domain)

---

### 2.7 Harvard Art Museums API

**URL:** https://harvardartmuseums.org/collections/api
**API Documentation:** https://github.com/harvardartmuseums/api-docs

**API Availability:** Yes, Free
**Authentication:** API key required

**Rate Limits:**
- 2,500 requests per day

**Resources:**
- Objects
- People
- Exhibitions
- Publications
- Galleries

**Search Parameters:**
- Century, Classification, Culture
- Medium, Provenance, Creditline
- Keyword search across multiple fields

**Coverage Quality:** Good ancient and archaeological artifacts
**Licensing:** Various (check per object)

---

### 2.8 Rijksmuseum API

**URL:** https://data.rijksmuseum.nl/
**API Documentation:** https://data.rijksmuseum.nl/docs/api/

**API Availability:** Yes, Free
**Authentication:** API key via Rijksstudio account

**Coverage:**
- 600,000+ descriptions
- Hundreds of thousands of photographs
- OAI-PMH API available

**Features:**
- Search by color
- Filter by year, medium, artist
- Up to 10,000 results per query

**Note:** Legacy Collection API deprecated; use new Search API

**Coverage Quality:** Dutch Golden Age focus, some archaeological content
**Licensing:** Various (indicated per item)

---

### 2.9 Victoria and Albert Museum API

**URL:** https://developers.vam.ac.uk/
**API Documentation:** https://api.vam.ac.uk/docs

**API Availability:** Yes, Free
**Authentication:** None required

**Coverage:**
- 1+ million collection records
- 500,000+ images
- IIIF-compliant image access
- 470,000 IIIF manifests

**Image API (IIIF):**
```
https://framemark.vam.ac.uk/collections/IMAGE_ID/full/!100,100/0/default.jpg
```

**Features:**
- Custom image sizes/rotations
- Filter for objects with images: `images_exist=1`
- High-resolution images up to 2500px

**Coverage Quality:** Strong decorative arts and historical objects
**Licensing:** V&A Terms (Section 9), many openly licensed

---

### 2.10 Cooper Hewitt Smithsonian Design Museum API

**URL:** https://collection.cooperhewitt.org/api/
**API Documentation:** https://collection.cooperhewitt.org/api/methods/

**API Availability:** Yes, Free
**Authentication:** OAuth access token required

**Coverage:**
- 215,000+ objects
- 19,000+ creators
- 30 centuries of design
- Egyptian faience to contemporary

**Key Methods:**
- `cooperhewitt.objects.getInfo` - Object details
- `cooperhewitt.objects.getImages` - Object images
- `cooperhewitt.search.collection` - Search by color, type, etc.
- `cooperhewitt.objects.getRandom` - Random object

**Coverage Quality:** Design-focused, some archaeological objects
**Licensing:** CC0 for metadata, check images

---

## 3. Geographic/Travel Image Sources

### 3.1 Google Street View API

**URL:** https://developers.google.com/maps/documentation/streetview
**API Documentation:** https://developers.google.com/streetview

**API Availability:** Yes, Paid (with free tier)
**Authentication:** API key required

**Features:**
- Interactive 360-degree panoramas
- Static Street View images
- User-contributed photo spheres
- Special collections (museums, heritage sites)

**Metadata API (Free):**
```
GET https://maps.googleapis.com/maps/api/streetview/metadata?location=LAT,LON&key=YOUR_KEY
```

**Limitation:** No programmatic access to historical imagery (only current images)

**Coverage Quality:** Excellent for accessible sites
**Licensing:** Google Terms of Service

---

### 3.2 Mapillary API

**URL:** https://www.mapillary.com/developer/api-documentation
**API Documentation:** https://www.mapillary.com/developer/api-documentation

**API Availability:** Yes, Free
**Authentication:** Client token required

**Rate Limits:**
- Entity APIs: 60,000 requests/minute/app
- Search APIs: 10,000 requests/minute/app
- Tiles: 50,000 requests/day

**Coverage:**
- Crowdsourced street-level imagery
- Tours of ancient sites (Teotihuacan, Pompeii, etc.)
- CC-BY-SA licensed images

**Integration Options:**
- MapillaryJS (JavaScript library)
- Python SDK
- GIS tool integrations
- Direct API access

**Coverage Quality:** Variable, good for popular archaeological sites
**Licensing:** CC-BY-SA 4.0

---

### 3.3 KartaView (formerly OpenStreetCam)

**URL:** https://kartaview.org/
**API Documentation:** https://api.openstreetcam.org/api/doc.html

**API Availability:** Yes, Free
**Authentication:** Required for uploads

**Features:**
- Free and open street-level imagery
- OpenStreetMap integration
- Sequence-based organization
- JOSM editor plugin

**Query by Bounding Box:**
```
GET https://api.openstreetcam.org/1.0/list/photos?bbTopLeft=LAT,LON&bbBottomRight=LAT,LON
```

**Coverage Quality:** Limited compared to Mapillary, community-driven
**Licensing:** CC-BY-SA 4.0

---

### 3.4 TripAdvisor Content API

**URL:** https://developer-tripadvisor.com/content-api/
**API Documentation:** https://tripadvisor-content-api.readme.io/

**API Availability:** Yes, Partner-only (not public)
**Authentication:** Partner key required

**Features:**
- Location photos (up to 5 high-quality per location)
- Reviews and ratings
- Attractions categorized including "Historical & Heritage Tours"

**Limitations:**
- Not publicly available
- Requires partnership agreement
- Limited free access

**Coverage Quality:** Good tourist destination coverage
**Licensing:** TripAdvisor Terms

---

## 4. Specialized Historical/Archaeological Sources

### 4.1 ARIADNE Portal

**URL:** https://ariadne-infrastructure.eu/
**API Documentation:** Contact via portal

**API Availability:** Research infrastructure (SPARQL, various APIs)
**Authentication:** Varies

**Coverage:**
- 3.8+ million archaeological resources
- 40+ data publishers
- European archaeological datasets
- CIDOC-CRM ontology-based

**Features:**
- GraphDB knowledge base
- Virtual Research Environments
- Analytics Lab
- PeriodO and Getty AAT integration

**Coverage Quality:** Excellent for European archaeological data
**Licensing:** Various (per contributing institution)

---

### 4.2 Pleiades Ancient World Gazetteer

**URL:** https://pleiades.stoa.org/
**API Documentation:** https://api.pleiades.stoa.org/

**API Availability:** Yes, Free
**Authentication:** None required

**Coverage:**
- 36,000+ ancient places
- Greek and Roman world (expanding)
- Places, locations, names, connections

**API Endpoints:**
```
# Single place
GET http://pleiades.stoa.org/places/{pid}/json

# Status/counts
GET http://api.pleiades.stoa.org/status
```

**Data Format:** GeoJSON feature collections

**Note:** Primarily a gazetteer (location data), not an image repository. Links to external image sources.

**Coverage Quality:** Authoritative ancient world locations
**Licensing:** CC-BY 3.0

---

### 4.3 Pelagios Commons / Peripleo

**URL:** http://commons.pelagios.org/
**API Documentation:** Deprecated, but standards remain

**API Availability:** Limited (project evolved)
**Authentication:** None

**Features:**
- Linked Open Data for ancient world
- Open Annotation ontology
- Pleiades URI integration
- Cross-resource discovery

**Peripleo API (Deprecated):**
- Search by keyword, place, space, time
- CORS and JSONP support
- Paginated results (default 20 per page)

**Coverage Quality:** Linking resource, not primary image source
**Licensing:** Various (per linked resource)

---

### 4.4 Archaeological Data Service (UK)

**URL:** https://archaeologydataservice.ac.uk/
**API Documentation:** API in development (2026)

**API Availability:** Limited/In Development
**Authentication:** TBD

**Coverage:**
- 1.3+ million metadata records (British Isles)
- 50,000+ unpublished fieldwork reports
- 1,500+ data-rich archives
- Images, databases, maps, aerial photographs

**Current Access:**
- ArchSearch catalogue
- WebGIS interfaces
- Web services for Heritage Gateway

**Coverage Quality:** Excellent for UK archaeology
**Licensing:** Various (per archive)

---

### 4.5 The Digital Archaeological Record (tDAR)

**URL:** https://core.tdar.org/
**API Availability:** Limited public access

**Coverage:**
- Archaeological and historic preservation information
- Documents, datasets, images
- Primarily North American focus

**Coverage Quality:** Good for academic archaeology
**Licensing:** Various (per contributor)

---

### 4.6 EAMENA Database

**URL:** https://eamena.org/database
**API Availability:** Limited (Arches 7 platform)

**Coverage:**
- Endangered Archaeology in Middle East & North Africa
- Satellite imagery analysis
- Site and landscape documentation

**Coverage Quality:** Specialized regional focus
**Licensing:** Research use

---

## 5. IIIF-Compliant Collections

The International Image Interoperability Framework (IIIF) provides standardized access across many institutions:

### Institutions with IIIF Support:
- Art Institute of Chicago
- British Library
- Carnegie Museum of Art
- Cooper Hewitt Smithsonian
- Getty Trust
- Harvard Art Museums
- National Gallery of Art
- Victoria and Albert Museum
- Yale Center for British Art

### IIIF Benefits:
- Consistent image URL patterns
- Dynamic sizing/cropping
- Cross-repository comparison
- Rich manifest metadata

### Basic IIIF Image URL:
```
{scheme}://{server}/{prefix}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
```

---

## 6. Summary Comparison Table

| Source | Free API | Auth Required | Rate Limit | Historical Coverage | Location Query |
|--------|----------|---------------|------------|---------------------|----------------|
| Wikimedia Commons | Yes | No | Generous | Excellent | Yes (GeoSearch) |
| Unsplash | Yes | Yes | 50-5000/hr | Good | No |
| Pexels | Yes | Yes | 200/hr | Moderate | No |
| Pixabay | Yes | Yes | 100/min | Good | No |
| Flickr | Yes | Yes | 3600/hr | Excellent | Yes |
| Google Places | Paid | Yes | Per-project | Excellent | Yes |
| Europeana | Yes | Yes | Per-project | Excellent | Yes |
| DPLA | Yes | Yes | Not specified | Good | Limited |
| Smithsonian | Yes | Yes | Per-project | Excellent | Limited |
| Met Museum | Yes | No | Not specified | Excellent | No |
| Getty | Yes | Varies | Not specified | Excellent | Limited |
| Cleveland Museum | Yes | No | Not specified | Good | No |
| Harvard Museums | Yes | Yes | 2500/day | Good | No |
| V&A | Yes | No | Not specified | Good | Limited |
| Mapillary | Yes | Yes | 60000/min | Variable | Yes |
| Pleiades | Yes | No | Not specified | Location data only | Yes |
| ARIADNE | Research | Varies | Varies | Excellent | Yes |

---

## 7. Implementation Recommendations

### For AncientMap Application:

**Primary Recommendations:**

1. **Wikimedia Commons** - Best free option with location-based queries
   - Use GeoSearch API for sites near coordinates
   - Excellent historical coverage
   - No authentication required

2. **Europeana** - Best for European cultural heritage
   - Strong archaeological content
   - IIIF support
   - Free API key

3. **Metropolitan Museum of Art** - Best for ancient civilizations
   - No authentication needed
   - CC0 licensing
   - Excellent Egyptian, Greek, Roman collections

4. **Flickr** - Best for user-contributed content
   - Strong geo-tagging capabilities
   - Diverse perspectives
   - Good rate limits

**Secondary Recommendations:**

5. **Smithsonian Open Access** - Broad coverage
6. **Getty Open Content** - Classical antiquities
7. **Mapillary** - Street-level imagery of sites

### Implementation Strategy:

1. **Tiered Approach:**
   - First: Check Wikimedia Commons by coordinates
   - Second: Search Europeana by site name/period
   - Third: Fallback to museum APIs by culture/period
   - Fourth: Stock photo APIs as last resort

2. **Caching:**
   - Cache API responses per site
   - Respect rate limits
   - Pre-fetch popular sites

3. **Attribution:**
   - Build attribution component
   - Store license info with images
   - Support various CC requirements

---

## 8. Sources

### Free/Open Image APIs:
- [Wikimedia Commons API](https://commons.wikimedia.org/wiki/Commons:API)
- [Wikimedia Commons GeoSearch](https://commons.wikimedia.org/wiki/Commons:Search_by_location)
- [Unsplash API Documentation](https://unsplash.com/documentation)
- [Unsplash API Guidelines](https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines)
- [Pexels API Documentation](https://www.pexels.com/api/documentation/)
- [Pixabay API Documentation](https://pixabay.com/api/docs/)
- [Flickr API](https://www.flickr.com/services/api/)
- [Flickr Geo Search](https://www.flickr.com/services/api/flickr.photos.geo.photosForLocation.html)
- [Google Places Photos API](https://developers.google.com/maps/documentation/places/web-service/place-photos)
- [Openverse](https://openverse.org/)

### Cultural Heritage APIs:
- [Europeana APIs](https://apis.europeana.eu/en)
- [DPLA API](https://pro.dp.la/developers/api-codex)
- [Smithsonian Open Access](https://www.si.edu/openaccess)
- [Metropolitan Museum of Art API](https://metmuseum.github.io/)
- [Getty Open Content](https://www.getty.edu/projects/open-content-program/)
- [Getty Open Data and APIs](https://www.getty.edu/projects/open-data-apis/)
- [Cleveland Museum of Art API](https://openaccess-api.clevelandart.org/)
- [Harvard Art Museums API](https://harvardartmuseums.org/collections/api)
- [Rijksmuseum API](https://data.rijksmuseum.nl/)
- [Victoria and Albert Museum API](https://developers.vam.ac.uk/)
- [Cooper Hewitt API](https://collection.cooperhewitt.org/api/)

### Geographic/Street-Level Sources:
- [Google Street View API](https://developers.google.com/maps/documentation/streetview)
- [Mapillary API](https://www.mapillary.com/developer/api-documentation)
- [KartaView](https://kartaview.org/)
- [KartaView Wiki](https://wiki.openstreetmap.org/wiki/KartaView)
- [TripAdvisor Content API](https://developer-tripadvisor.com/content-api/)

### Archaeological/Specialized Sources:
- [ARIADNE Infrastructure](https://ariadne-infrastructure.eu/)
- [Pleiades Gazetteer](https://pleiades.stoa.org/)
- [Pleiades API](https://api.pleiades.stoa.org/)
- [Pelagios Commons](http://commons.pelagios.org/)
- [Archaeological Data Service](https://archaeologydataservice.ac.uk/)
- [tDAR Digital Archaeological Record](https://core.tdar.org/)
- [EAMENA Database](https://eamena.org/database)

### Standards and Frameworks:
- [IIIF International Image Interoperability Framework](https://iiif.io/)
- [IIIF Museums Community](https://iiif.io/community/groups/museums/)
- [Wikimedia API Rate Limits](https://api.wikimedia.org/wiki/Rate_limits)
- [MediaWiki API Etiquette](https://www.mediawiki.org/wiki/API:Etiquette)

### University Resources:
- [Brown University Archaeology Image Resources](https://libguides.brown.edu/archaeology/imageresources)
- [UCLA Ancient Near East Image Resources](https://guides.library.ucla.edu/c.php?g=180188&p=1188454)
- [University of Michigan Digital Artifacts](https://guides.lib.umich.edu/c.php?g=282827&p=1884557)

---

*Report compiled January 30, 2026 for AncientMap historical mapping application*
