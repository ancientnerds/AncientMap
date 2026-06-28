# Research & Academic Search API Landscape (April 2026)

Comprehensive analysis of free-tier REST APIs for an archaeological/historical research pipeline.

---

## 1. ACADEMIC PAPER DATABASES

### 1.1 Semantic Scholar Academic Graph API
- **URL**: https://www.semanticscholar.org/product/api
- **What it searches**: 200M+ scholarly papers, authors, citations, references
- **Free tier**: No API key required for basic access (5,000 req/5min shared pool). Free API key available for higher sustained limits.
- **API key needed**: No (for basic), yes for higher rate limits (free key via form)
- **Response format**: JSON -- paperId, title, abstract, authors, year, citationCount, referenceCount, fieldsOfStudy, externalIds (DOI, ArXiv, PubMed), openAccessPdf URL, tldr (AI summary)
- **Archaeology relevance**: HIGH. Covers archaeology, anthropology, geology, history of science. AI-powered relevance ranking helps surface niche papers.
- **Rate limits**: Unauthenticated: 5,000 req/5min (shared). Authenticated (free key): ~100 req/sec dedicated.
- **Notable limitations**: Some endpoints limited to 10,000 results max. No full-text search (title/abstract only). TLDR not available for all papers.

### 1.2 OpenAlex API
- **URL**: https://openalex.org / https://developers.openalex.org
- **What it searches**: 250M+ academic works, authors, sources, institutions, concepts
- **Free tier**: $1/day free credit with API key. Singleton requests free, list endpoints $0.0001, search $0.001 each.
- **API key needed**: Yes (free, 30-second signup)
- **Response format**: JSON -- id, title, abstract_inverted_index, doi, publication_date, cited_by_count, concepts, host_venue, open_access status, authorships
- **Archaeology relevance**: VERY HIGH. Replaces Microsoft Academic. Excellent concept tagging, institution linking. Strong coverage of humanities/social sciences.
- **Rate limits**: $1/day = ~1,000 search queries or 10,000 list queries. Max 100 req/sec. Academic researchers can request free higher limits.
- **Notable limitations**: Abstracts stored as inverted index (requires reconstruction). Credit-based system since Feb 2026 replaced old unlimited model.

### 1.3 CORE (COnnecting REpositories) API
- **URL**: https://core.ac.uk/services/api
- **What it searches**: 300M+ metadata records, 40M+ full-text open access papers from 10,000+ repositories
- **Free tier**: Free API key required (instant registration)
- **API key needed**: Yes (free)
- **Response format**: JSON -- id, title, authors, abstract, downloadUrl, fullText (for OA papers), year, doi, repositories, language
- **Archaeology relevance**: HIGH. Aggregates institutional repositories worldwide where grey literature and archaeological reports are often deposited.
- **Rate limits**: Single search: 5-10 req/10sec depending on endpoint. Batch search: 1 req/10sec. Higher rates available on request.
- **Notable limitations**: Slow rate limits for batch operations. Full text only available for open access papers. Some metadata incomplete.

### 1.4 Crossref REST API
- **URL**: https://api.crossref.org
- **What it searches**: 160M+ DOI metadata records -- journal articles, books, conference proceedings, datasets
- **Free tier**: Completely free, no key required
- **API key needed**: No. Including mailto= parameter gets "polite pool" access (recommended).
- **Response format**: JSON -- DOI, title, author, container-title (journal), published-date, abstract (when deposited), reference list, is-referenced-by-count, license, subject
- **Archaeology relevance**: HIGH. Comprehensive coverage of published archaeological journals. Abstract availability depends on publisher deposit.
- **Rate limits (post-Dec 2025)**:
  - Public pool: single record 5 req/sec (1 concurrent), list queries 1 req/sec (1 concurrent)
  - Polite pool (add mailto): single record 10 req/sec (3 concurrent), list queries 3 req/sec (3 concurrent)
- **Notable limitations**: Not all publishers deposit abstracts. No full-text access. Rate limits reduced Dec 2025.

### 1.5 Scopus / Elsevier API
- **URL**: https://dev.elsevier.com
- **What it searches**: 94M+ records -- Scopus abstract/citation database, ScienceDirect full-text
- **Free tier**: Free for non-commercial academic use (institutional affiliation required). Non-subscribers get limited BASIC view.
- **API key needed**: Yes (free registration)
- **Response format**: JSON/XML -- dc:title, dc:creator, prism:publicationName, abstract, citedby-count, affiliation, subject-area, doi
- **Archaeology relevance**: HIGH. Strong coverage of archaeology, anthropology, earth sciences journals. Excellent citation data.
- **Rate limits**: 20,000 requests per 7-day window (per API). Throttling varies by endpoint.
- **Notable limitations**: Full access requires institutional subscription. Non-subscribers only get basic metadata. Not truly "open" data.

### 1.6 Dimensions.ai API
- **URL**: https://www.dimensions.ai / https://ds.digital-science.com/NoCostAgreement
- **What it searches**: 106M+ publications, 1.2B+ citations, grants, patents, clinical trials, datasets, policy documents
- **Free tier**: Free for non-commercial research (application required). Also free web search without account.
- **API key needed**: Yes (application process)
- **Response format**: JSON via DSL (Dimensions Search Language) -- title, abstract, doi, year, journal, authors, citations_count, field_of_research, open_access
- **Archaeology relevance**: HIGH. Covers publications plus grants and policy documents (useful for heritage policy research). AI natural language query beta in 2025.
- **Rate limits**: Varies by agreement. Free tier is rate-limited but generous for research.
- **Notable limitations**: API access requires approval application. Uses proprietary DSL query language (not standard REST query params). Commercial use requires paid license.

### 1.7 Lens.org
- **URL**: https://www.lens.org / https://about.lens.org/lens-apis/
- **What it searches**: 200M+ scholarly records + patent data. Combines Microsoft Academic, PubMed, Crossref, Unpaywall.
- **Free tier**: Free web search/export (up to 50K records). API: 14-day trial for non-commercial use.
- **API key needed**: Yes (trial application required)
- **Response format**: JSON -- title, abstract, authors, date_published, source, doi, pmid, citations, fields_of_study, open_access
- **Archaeology relevance**: MEDIUM-HIGH. Unique patent-to-scholarly linking. Good for materials science / archaeological chemistry crossover.
- **Rate limits**: Trial: 14 days, limited requests. Sustained API access is paid.
- **Notable limitations**: API trial is only 14 days. Sustained free access limited to web interface only. Not ideal for automated pipeline.

---

## 2. GENERAL WEB SEARCH APIs

### 2.1 Brave Search API
- **URL**: https://brave.com/search/api/
- **What it searches**: Independent web index of 30B+ pages (not Google/Bing proxy)
- **Free tier**: $5/month credits for existing users (~1,000 searches). New users since Feb 2026: no genuinely free tier, but $5 monthly credit applied.
- **API key needed**: Yes
- **Response format**: JSON -- title, url, description, page_age, thumbnail, extra_snippets, deep_results
- **Archaeology relevance**: MEDIUM-HIGH. Independent index means different results than Google. Good for finding institutional pages, heritage sites, museum collections.
- **Rate limits**: 50 req/sec. ~1,000 queries/month on credits.
- **Notable limitations**: Free tier effectively killed Feb 2026. $5/1000 requests for overage. Not the cheapest for high volume.

### 2.2 Serper API
- **URL**: https://serper.dev
- **What it searches**: Google SERP results (organic, knowledge panels, PAA, snippets)
- **Free tier**: 2,500 free queries (one-time, not monthly)
- **API key needed**: Yes
- **Response format**: JSON -- title, link, snippet, position, sitelinks, knowledgeGraph, peopleAlsoAsk
- **Archaeology relevance**: MEDIUM. Real Google results useful for finding primary sources, news, institutional content.
- **Rate limits**: Up to 300 req/sec. 2,500 free queries then $50/month for 50K.
- **Notable limitations**: Free queries are one-time allocation, not recurring. Scraping Google TOS gray area.

### 2.3 SerpAPI
- **URL**: https://serpapi.com
- **What it searches**: Google, Google Scholar, Google News, Bing, Yahoo, and 15+ other engines
- **Free tier**: 250 searches/month (recurring). All endpoints included.
- **API key needed**: Yes
- **Response format**: JSON -- varies by engine. Scholar returns title, link, snippet, publication_info, cited_by, related_articles
- **Archaeology relevance**: HIGH. Google Scholar endpoint is uniquely valuable -- searches academic papers with Google's ranking. Cached searches are free.
- **Rate limits**: 250/month free. Best effort speed only on free tier.
- **Notable limitations**: 250/month is tight for production. Paid plans start $25/month. Proxy-based scraping.

### 2.4 Tavily Search API
- **URL**: https://tavily.com
- **What it searches**: Web search optimized for AI/RAG applications. Returns clean, relevant content.
- **Free tier**: 1,000 credits/month (no credit card required). Basic search = 1 credit, advanced = 2 credits.
- **API key needed**: Yes
- **Response format**: JSON -- title, url, content (cleaned/extracted), score, raw_content
- **Archaeology relevance**: MEDIUM. AI-optimized relevance is useful. Content extraction saves a scraping step.
- **Rate limits**: 1,000 credits/month free. Research API uses 4-250 credits per request.
- **Notable limitations**: Credits consumed fast with advanced search. Research mode very expensive in credits. Variable cost makes budgeting difficult.

### 2.5 Exa.ai
- **URL**: https://exa.ai
- **What it searches**: Semantic/neural web search using embeddings. Finds conceptually similar content.
- **Free tier**: $10 free credits (no expiration, no CC required) = ~2,000 searches
- **API key needed**: Yes
- **Response format**: JSON -- url, title, text (extracted content), score, publishedDate, author. Contents for 10 results per request included free.
- **Archaeology relevance**: HIGH. Semantic search excels at finding conceptually related academic and institutional content that keyword search misses.
- **Rate limits**: 2,000 searches on free credits. Search: $7/1000 req. Exa Deep: $12/1000 req.
- **Notable limitations**: Credits are one-time, not recurring. After $10 used, pay-as-you-go only. Neural search can drift from intent.

### 2.6 SearchApi.io
- **URL**: https://www.searchapi.io
- **What it searches**: Google, Google Scholar, Google News, Bing, Baidu, YouTube, and more
- **Free tier**: 100 free requests (one-time). No CC required.
- **API key needed**: Yes
- **Response format**: JSON -- structured SERP data including organic_results, knowledge_graph, scholar results (title, link, snippet, publication_info)
- **Archaeology relevance**: MEDIUM-HIGH. Google Scholar endpoint available. Multiple engines in one API.
- **Rate limits**: 100 free requests one-time. Paid from $40/month.
- **Notable limitations**: Tiny free allocation. Primarily useful for testing before committing to paid plan.

### 2.7 Google Custom Search JSON API
- **URL**: https://developers.google.com/custom-search/v1/overview
- **What it searches**: Google web search results
- **Free tier**: 100 queries/day free for existing customers
- **API key needed**: Yes (Google Cloud API key + Custom Search Engine ID)
- **Response format**: JSON -- title, link, snippet, pagemap, htmlSnippet, displayLink
- **Archaeology relevance**: HIGH (it's Google). But restricted.
- **Rate limits**: 100/day free. $5/1000 queries up to 10K/day max.
- **Notable limitations**: NOT AVAILABLE FOR NEW CUSTOMERS. Sunsetting January 1, 2027. "Search entire web" option removed March 2026. Only existing users can access.

### 2.8 SearXNG (Self-Hosted)
- **URL**: https://github.com/searxng/searxng
- **What it searches**: Meta-search aggregator for 70+ engines (Google, Bing, DuckDuckGo, etc.)
- **Free tier**: Completely free (open source, self-hosted)
- **API key needed**: No (self-hosted, you control it)
- **Response format**: JSON/XML output supported. Returns title, url, content, engine, score, category
- **Archaeology relevance**: HIGH. Aggregates results from many engines. Can target academic engines specifically. Full control over which engines to query.
- **Rate limits**: Self-hosted = no limits from SearXNG itself. Rate limits of underlying engines still apply.
- **Notable limitations**: Requires hosting infrastructure (Docker, ~0.5GB RAM). Must manage upstream engine rate limits. Results quality depends on engine selection and configuration.

---

## 3. SPECIALIZED SEARCH

### 3.1 Internet Archive API
- **URL**: https://archive.org/developers/index-apis.html
- **What it searches**: 800B+ web pages (Wayback Machine), books, audio, video, software, images
- **Free tier**: Completely free
- **API key needed**: No
- **Response format**: JSON -- varies by API. Search returns identifier, title, description, mediatype, date, downloads, subject
- **Archaeology relevance**: VERY HIGH. Historical web snapshots of archaeological sites/databases that no longer exist. Digitized books on archaeology. Open library of academic texts.
- **Rate limits**: No hard daily cap. Be considerate (no more than 15 concurrent requests recommended).
- **Notable limitations**: Wayback Machine availability varies. Full-text search quality is lower than purpose-built academic search. Metadata can be inconsistent.

### 3.2 Internet Archive Scholar (Fatcat)
- **URL**: https://scholar.archive.org / https://fatcat.wiki
- **What it searches**: 25M+ open access research papers preserved in the Internet Archive
- **Free tier**: Completely free. Open source.
- **API key needed**: No
- **Response format**: JSON (Fatcat API) -- work, release (title, abstract, doi, container, date), file (sha1, urls, mimetype), creator
- **Archaeology relevance**: HIGH. Focuses on long-tail open access papers that other indexes miss. Excellent for finding freely available full-text PDFs.
- **Rate limits**: Public API, no documented hard limits. Bulk data dumps available.
- **Notable limitations**: Smaller corpus than Semantic Scholar/OpenAlex. Search interface less sophisticated. Focus is on preservation, not discovery.

### 3.3 DOAJ (Directory of Open Access Journals) API
- **URL**: https://doaj.org/api/docs
- **What it searches**: 21,480+ open access journals, 11M+ articles across all disciplines
- **Free tier**: Completely free. All data freely available.
- **API key needed**: No (recommended for higher limits)
- **Response format**: JSON -- bibjson (title, abstract, journal, author, year, doi, keywords, subject), links to full text
- **Archaeology relevance**: MEDIUM-HIGH. Many archaeological journals are OA. DOAJ verifies journal quality (no predatory journals).
- **Rate limits**: 1,000 records per search query maximum.
- **Notable limitations**: Only indexes open access journals (not all archaeology journals). Search limited to 1,000 records per query. No citation data.

### 3.4 BASE (Bielefeld Academic Search Engine) API
- **URL**: https://api.base-search.net
- **What it searches**: 400M+ documents from 12,000+ content providers (institutional repositories, OA journals)
- **Free tier**: Free API key via application form
- **API key needed**: Yes (free, requires application)
- **Response format**: JSON/XML -- dctitle, dccreator, dcdate, dcidentifier, dcdescription, dctype, dclink
- **Archaeology relevance**: HIGH. Excellent for grey literature, institutional repository content (archaeological reports, theses, conference papers).
- **Rate limits**: Not publicly documented. IP whitelisting or API key required.
- **Notable limitations**: API key requires application and approval. Documentation less polished than competitors. Some metadata inconsistency across repositories.

---

## 4. NEWS / MEDIA APIs

### 4.1 NewsAPI.org
- **URL**: https://newsapi.org
- **What it searches**: 80,000+ news sources worldwide. Headlines and article metadata.
- **Free tier**: 100 requests/day (Developer plan). Development/testing only.
- **API key needed**: Yes (free signup)
- **Response format**: JSON -- source, author, title, description, url, urlToImage, publishedAt, content (first 200 chars)
- **Archaeology relevance**: MEDIUM. Good for finding archaeological discovery news. Keyword search for "archaeology", "excavation", "ancient" etc.
- **Rate limits**: 100 req/day free. Articles delayed 24 hours.
- **Notable limitations**: Free tier development-only (cannot use in production). 24-hour article delay. Content truncated to 200 chars. No historical archive on free tier.

### 4.2 GNews API
- **URL**: https://gnews.io
- **What it searches**: 60,000+ news sources in 22 languages. Current and historical articles.
- **Free tier**: 100 requests/day (non-commercial use only)
- **API key needed**: Yes (free signup)
- **Response format**: JSON -- title, description, content, url, image, publishedAt, source (name, url)
- **Archaeology relevance**: MEDIUM. Multi-language support useful for international archaeological discoveries. Historical article search available.
- **Rate limits**: 100 req/day free, max 1 req/sec. No email support on free tier.
- **Notable limitations**: Free tier non-commercial only. Full article content not available on free tier. Daily limit is restrictive.

### 4.3 NewsData.io
- **URL**: https://newsdata.io
- **What it searches**: 87,287+ sources across 206 countries in 89 languages, 18 categories
- **Free tier**: 200 API credits/day (each returns 10 articles). Commercial use allowed.
- **API key needed**: Yes (free signup)
- **Response format**: JSON -- title, link, description, content (paid), source_id, pubDate, country, category, language, image_url
- **Archaeology relevance**: MEDIUM. Broad international coverage useful for global archaeological news. Category filtering helps narrow results.
- **Rate limits**: 200 credits/day free. 12-hour article delay. 100-char keyword limit on free tier.
- **Notable limitations**: Full content only on paid plans. 12-hour delay. Short keyword search limit.

---

## 5. OPEN DATA / KNOWLEDGE BASES

### 5.1 Wikidata SPARQL API
- **URL**: https://query.wikidata.org
- **What it searches**: Structured knowledge graph of all Wikipedia entities and beyond. 100M+ items.
- **Free tier**: Completely free
- **API key needed**: No
- **Response format**: JSON, XML, CSV, TSV via SPARQL queries. Returns any requested properties (coordinates, dates, identifiers, descriptions).
- **Archaeology relevance**: VERY HIGH. Archaeological sites (Q839954), historical periods, artifacts, civilizations all extensively cataloged with coordinates, dates, and cross-references. Dedicated scholarly articles endpoint at query-scholarly.wikidata.org.
- **Rate limits**: No hard documented limits. Queries timeout after 60 seconds. Concurrent query limits exist but generous.
- **Notable limitations**: Requires SPARQL knowledge. Complex query language. Data quality varies (community-maintained). Query timeouts on expensive joins.

### 5.2 DBpedia SPARQL API
- **URL**: https://dbpedia.org/sparql
- **What it searches**: Structured data extracted from Wikipedia infoboxes. Entities, relationships, categories.
- **Free tier**: Completely free
- **API key needed**: No
- **Response format**: JSON-LD, RDF/XML, Turtle, CSV via SPARQL. Returns structured entity data, properties, relationships.
- **Archaeology relevance**: HIGH. Archaeological sites, historical figures, ancient civilizations extracted from Wikipedia with typed relationships and categories.
- **Rate limits**: Public endpoint with no documented hard limits. Fair use expected.
- **Notable limitations**: Requires SPARQL. Data quality depends on Wikipedia infobox completeness. Less comprehensive than Wikidata for scholarly metadata. Can lag behind Wikipedia updates.

### 5.3 Wikipedia / MediaWiki API
- **URL**: https://en.wikipedia.org/w/api.php
- **What it searches**: All Wikipedia content -- articles, categories, images, revision history
- **Free tier**: Completely free
- **API key needed**: No
- **Response format**: JSON -- title, pageid, extract (text), thumbnail, categories, links, coordinates, fullurl
- **Archaeology relevance**: VERY HIGH. Wikipedia is often the first comprehensive source for archaeological sites, periods, and discoveries. Coordinates available for geotagged articles.
- **Rate limits**: No hard read limit (be considerate). Action limits: 200 req/sec guideline. List results capped at 500/query.
- **Notable limitations**: Content is encyclopedia-level, not primary research. Must identify User-Agent header. Content can be inaccurate (community-edited).

### 5.4 GeoNames API
- **URL**: https://www.geonames.org/export/web-services.html
- **What it searches**: 10M+ geographical names and features. Populated places, terrain, administrative regions.
- **Free tier**: Free registration required
- **API key needed**: Yes (free username registration)
- **Response format**: JSON/XML -- geonameId, name, lat, lng, countryCode, population, elevation, featureCode, adminName
- **Archaeology relevance**: MEDIUM. Useful for geocoding archaeological site names and finding nearby modern place references. 5.5M alternate names for cross-referencing.
- **Rate limits**: Limited on free tier (exact numbers not publicly documented, ~1000/hour estimated). Premium available.
- **Notable limitations**: Limited for ancient/historical place names (use Pleiades for that). Rate limits not well documented. Premium features cost.

### 5.5 OpenStreetMap / Overpass API
- **URL**: https://overpass-api.de/api/ + https://wiki.openstreetmap.org/wiki/OpenHistoricalMap/Overpass
- **What it searches**: All OSM geographic data. OpenHistoricalMap variant for historical periods.
- **Free tier**: Completely free
- **API key needed**: No
- **Response format**: JSON (or XML). Returns nodes/ways/relations with tags: name, historic=*, archaeological_site=*, heritage=*, period, wikipedia link
- **Archaeology relevance**: HIGH. OSM tags `historic=archaeological_site`, `historic=ruins`, `archaeological_site=*` contain thousands of tagged sites with coordinates. OpenHistoricalMap adds temporal querying.
- **Rate limits**: Fair use. Queries limited by timeout (180s default). Multiple public instances available.
- **Notable limitations**: Requires Overpass QL query language. Data completeness varies by region. Historical data coverage spotty. Results can be large.

---

## 6. GOVERNMENT / INSTITUTIONAL

### 6.1 Europeana Search API
- **URL**: https://api.europeana.eu
- **What it searches**: Millions of cultural heritage items from 4,000+ European institutions (museums, archives, libraries)
- **Free tier**: Completely free. All read APIs free forever.
- **API key needed**: Yes (free, via Europeana account since May 2025)
- **Response format**: JSON-LD -- title, description, dcCreator, dcDate, type, provider, dataProvider, edmPreview (thumbnail), edmIsShownAt (source URL), dcSubject, dctermsProvenance
- **Archaeology relevance**: VERY HIGH. Major archaeological museums, national archives, and heritage institutions contribute. Rich metadata about artifacts, excavation records, historical documents.
- **Rate limits**: No limitations on read APIs.
- **Notable limitations**: Metadata quality varies by contributing institution. Full objects hosted by source institutions, not Europeana. Some records minimal.

### 6.2 U.S. National Archives (NARA) Catalog API
- **URL**: https://www.archives.gov/research/catalog/help/api
- **What it searches**: All NARA catalog records -- archival descriptions, digital objects, authority records, OCR text
- **Free tier**: Free. No key needed for basic searching.
- **API key needed**: No (for search). Key available on request for higher limits.
- **Response format**: JSON -- title, description, creator, date, type, objects (digital media), authority records, tags, transcriptions
- **Archaeology relevance**: MEDIUM. Useful for U.S. government archaeological survey records, Bureau of Land Management reports, Antiquities Act documentation.
- **Rate limits**: 10,000 queries/month per API key.
- **Notable limitations**: U.S.-focused. Much content is not digitized. OCR quality varies. Primarily administrative records rather than research papers.

### 6.3 Library of Congress API
- **URL**: https://www.loc.gov/apis/
- **What it searches**: LOC digital collections -- books, photos, maps, manuscripts, newspapers, videos, audio
- **Free tier**: Completely free. No authentication required.
- **API key needed**: No
- **Response format**: JSON/YAML -- title, contributor, date, subject, description, location (coordinates when available), url, image_url, online_format
- **Archaeology relevance**: HIGH. Chronicling America newspapers (historical archaeological news), maps, photographs, manuscript collections. Particularly strong for American archaeology/anthropology history.
- **Rate limits**: No documented hard limits. Be respectful.
- **Notable limitations**: U.S.-centric. Search relevance can be noisy. Not all items are digitized.

### 6.4 Smithsonian Open Access API
- **URL**: https://www.si.edu/openaccess/devtools
- **What it searches**: 5.1M+ 2D/3D digital items from 21 museums, 9 research centers, libraries, archives
- **Free tier**: Completely free (CC0 license)
- **API key needed**: Yes (free, via api.data.gov registration)
- **Response format**: JSON -- title, topic, date, place, objectType, physicalDescription, identifier, online_media (images, 3D models)
- **Archaeology relevance**: VERY HIGH. National Museum of Natural History, National Museum of the American Indian, and other Smithsonian facilities hold major archaeological collections. 11M+ metadata records.
- **Rate limits**: Standard api.data.gov limits (default 1,000 req/hour per key).
- **Notable limitations**: Search relevance can be poor for complex queries. Data completeness varies across museums. 3D objects may require specialized rendering.

### 6.5 Metropolitan Museum of Art Collection API
- **URL**: https://metmuseum.github.io
- **What it searches**: 470,000+ artworks in the Met collection. Ancient art, armor, Egyptian, Greek/Roman, Medieval collections.
- **Free tier**: Completely free (CC0 for public domain images)
- **API key needed**: No
- **Response format**: JSON -- objectID, title, artistDisplayName, objectDate, period, culture, medium, dimensions, geography (country, city, excavation), primaryImage, GalleryNumber, department
- **Archaeology relevance**: VERY HIGH. Egyptian Art, Greek and Roman Art, Ancient Near Eastern Art, Arms and Armor departments. Geography field includes excavation/findspot data.
- **Rate limits**: 80 requests per second.
- **Notable limitations**: Met collection only (one museum). No scholarly paper metadata. Image quality varies. Some objects lack detailed metadata.

### 6.6 Rijksmuseum Data API
- **URL**: https://data.rijksmuseum.nl
- **What it searches**: 500,000+ art historical objects, photographs, library catalog
- **Free tier**: Completely free
- **API key needed**: Yes (instant via Rijksstudio account)
- **Response format**: JSON-LD/JSON -- title, description, principalMaker, dating, physicalMedium, webImage, classification, dimensions, objectTypes
- **Archaeology relevance**: MEDIUM. Primarily Dutch/European art. Some archaeological objects, antiquities.
- **Rate limits**: Not publicly documented.
- **Notable limitations**: Legacy API being deprecated. New Linked Open Data APIs replacing older REST endpoints. Primarily art rather than archaeology.

### 6.7 Historic England / Heritage Gateway
- **URL**: https://www.api.gov.uk/he/ / https://www.heritagegateway.org.uk
- **What it searches**: National Heritage List for England (NHLE), Historic Environment Records, listed buildings, scheduled monuments
- **Free tier**: Completely free (Open Government Licence)
- **API key needed**: No for data downloads. API specifics vary.
- **Response format**: GIS shapefiles, JSON, CSV -- monument records, coordinates, period, type, designation
- **Archaeology relevance**: VERY HIGH (for UK). Comprehensive database of scheduled monuments, registered battlefields, protected wrecks. Directly relevant to British archaeology.
- **Rate limits**: Not documented. Download-based for bulk data.
- **Notable limitations**: UK-only. Heritage Gateway cross-searches 60+ resources but does not have a single REST API. Data access varies by local authority.

### 6.8 Portable Antiquities Scheme (PAS) Database
- **URL**: https://finds.org.uk / https://github.com/findsorguk
- **What it searches**: 1.4M+ archaeological objects found by the public in England and Wales
- **Free tier**: Completely free
- **API key needed**: No for search. Some features require registration.
- **Response format**: JSON -- objectType, broadperiod, description, finder, findSpot (parish/county, some coordinates), material, weight, dimensions
- **Archaeology relevance**: EXTREMELY HIGH. Direct archaeological find data. Metal detector finds, fieldwalking results. Location, period, object type all searchable.
- **Rate limits**: Not documented.
- **Notable limitations**: England and Wales only. Exact findspot coordinates restricted for some records (to prevent looting). Open source but community-maintained.

---

## 7. PREPRINT / OPEN ACCESS

### 7.1 arXiv API
- **URL**: https://info.arxiv.org/help/api/
- **What it searches**: Hundreds of thousands of e-prints in physics, mathematics, CS, quantitative biology, statistics, electrical engineering, economics
- **Free tier**: Completely free. No authentication.
- **API key needed**: No
- **Response format**: Atom XML -- id, title, summary (abstract), author, published, updated, category, doi, comment, journal_ref, link (PDF)
- **Archaeology relevance**: LOW-MEDIUM. Relevant only for computational archaeology, remote sensing in archaeology, archaeoastronomy, geological dating methods. No humanities/social science coverage.
- **Rate limits**: 1 request every 3 seconds. Max 30,000 results per query (in pages of 2000). No daily cap.
- **Notable limitations**: No archaeology/history/humanities categories. Atom XML format (not JSON). Results ordered by submission date, not relevance.

### 7.2 Zenodo API
- **URL**: https://developers.zenodo.org
- **What it searches**: Open access research data, papers, software, presentations from all disciplines. Built by CERN + OpenAIRE.
- **Free tier**: Completely free
- **API key needed**: Optional (higher page sizes with token)
- **Response format**: JSON -- metadata (title, description, creators, doi, publication_date, keywords, access_right, resource_type, related_identifiers), files, links
- **Archaeology relevance**: HIGH. Many archaeological datasets, field reports, and supplementary materials deposited here. "Communities" feature groups related archaeology content.
- **Rate limits (since Nov 2025)**: 30 requests/minute (both anonymous and authenticated). Anonymous: max 25 results/page. Authenticated: max 100 results/page.
- **Notable limitations**: Rate limits tightened Nov 2025 due to aggressive harvesting. Not a discovery engine -- best for known deposits or community browsing.

### 7.3 OpenAIRE Graph API
- **URL**: https://graph.openaire.eu/docs/apis/
- **What it searches**: Pan-European aggregation of research outputs -- publications, datasets, software linked to projects, organizations, funders
- **Free tier**: Completely free (CC-BY or CC-0)
- **API key needed**: No
- **Response format**: JSON -- title, authors, dateofacceptance, publisher, journal, description, subjects, bestaccessright, pid (DOI, etc.), links to datasets/projects
- **Archaeology relevance**: HIGH. European research funding linkage is valuable. Connects publications to EU-funded archaeology projects. Good for grey literature discovery.
- **Rate limits**: Not publicly specified. New Graph API launched 2025 replacing Search API.
- **Notable limitations**: Primarily European focus. API documentation still maturing post-2025 migration.

### 7.4 PubMed / NCBI Entrez E-utilities
- **URL**: https://www.ncbi.nlm.nih.gov/home/develop/api/
- **What it searches**: 36M+ citations in PubMed (biomedical literature). PMC full-text, GenBank, other NCBI databases.
- **Free tier**: Completely free
- **API key needed**: Optional. Without key: 3 req/sec. With free key: 10 req/sec.
- **Response format**: XML (primary), JSON supported for some endpoints -- PMID, title, abstract, authors, journal, pubdate, mesh terms, doi, pmc_id
- **Archaeology relevance**: MEDIUM. Relevant for bioarchaeology, paleopathology, ancient DNA, forensic anthropology, archaeobotany, zooarchaeology. MeSH term "Archaeology" exists.
- **Rate limits**: 3 req/sec unauthenticated, 10 req/sec with free API key. No daily cap.
- **Notable limitations**: Biomedical focus. Returns XML by default. Only useful for biology-adjacent archaeology subfields.

---

## 8. CITATION / REFERENCE TOOLS

### 8.1 DOI Content Negotiation (doi.org)
- **URL**: https://citation.doi.org/docs.html
- **What it searches**: Resolves any DOI to structured metadata via HTTP content negotiation
- **Free tier**: Completely free
- **API key needed**: No
- **Response format**: Varies by Accept header -- Citeproc JSON, BibTeX, RDF/XML, formatted citations (1000+ CSL styles). Request via: `Accept: application/citeproc+json` to `https://doi.org/10.xxxx/xxxxx`
- **Archaeology relevance**: HIGH. Universal metadata retrieval for any DOI-registered archaeological paper. Supports Crossref, DataCite, mEDRA DOIs.
- **Rate limits**: Not documented. High availability service.
- **Notable limitations**: Single-record lookups only (no search). Requires knowing the DOI. Response completeness depends on publisher metadata deposit.

### 8.2 Unpaywall API
- **URL**: https://api.unpaywall.org
- **What it searches**: Open access status and free PDF locations for 30M+ articles. Checks 50,000+ OA sources.
- **Free tier**: Completely free (email as parameter)
- **API key needed**: No (just include email as query parameter)
- **Response format**: JSON -- doi, title, is_oa, best_oa_location (url, url_for_pdf, host_type, license, version), oa_status, publisher, journal_name
- **Archaeology relevance**: HIGH. Critical for finding free full-text versions of paywalled archaeology papers. Complements any DOI-based search.
- **Rate limits**: 100,000 calls/day. Database snapshot available for bulk use.
- **Notable limitations**: DOI-based lookup only (no keyword search). Must know the DOI first. Only finds legal OA copies.

### 8.3 OpenCitations API
- **URL**: https://api.opencitations.net
- **What it searches**: 624M+ bibliographic citations (DOI-to-DOI citation links from Crossref)
- **Free tier**: Completely free (open data)
- **API key needed**: No
- **Response format**: JSON or CSV -- citing DOI, cited DOI, creation date, journal_sc (self-citation flag), author_sc. Also via SPARQL.
- **Archaeology relevance**: HIGH. Citation network analysis for archaeological literature. Find which papers cite a seminal work. Build citation graphs for research topics.
- **Rate limits**: Not documented. SPARQL endpoint available for complex queries.
- **Notable limitations**: Only DOI-to-DOI citations (no coverage for non-DOI works). Coverage depends on Crossref reference deposits. No keyword search.

### 8.4 DataCite REST API
- **URL**: https://api.datacite.org
- **What it searches**: DOI metadata for research datasets, software, reports (primarily non-journal outputs)
- **Free tier**: Completely free. No authentication.
- **API key needed**: No
- **Response format**: JSON:API -- attributes (doi, titles, creators, descriptions, dates, subjects, types, relatedIdentifiers, geoLocations, rightsList)
- **Archaeology relevance**: HIGH. Archaeological datasets, field recordings, GIS data, 3D scans often registered with DataCite DOIs. geoLocations field contains site coordinates.
- **Rate limits**: No hard limits currently imposed.
- **Notable limitations**: Only indexes DataCite-registered DOIs (datasets, not journal articles). Smaller corpus than Crossref. Metadata quality varies.

### 8.5 ORCID Public API
- **URL**: https://info.orcid.org/what-is-orcid/services/public-api/
- **What it searches**: Researcher profiles -- publications, affiliations, funding, peer review activities
- **Free tier**: Completely free
- **API key needed**: Yes (free OAuth registration)
- **Response format**: JSON/XML -- orcid-identifier, personal-info, activities (works with title, doi, type, journal), affiliations, funding
- **Archaeology relevance**: MEDIUM. Look up archaeologists' publication lists. Find co-author networks. Verify researcher credentials.
- **Rate limits**: Not explicitly documented for public API. Fair use.
- **Notable limitations**: Only profiles that researchers have self-populated. Not a search engine -- must know the researcher. Metadata imported from other sources (quality varies).

---

## 9. ARCHAEOLOGY-SPECIFIC RESOURCES

### 9.1 Pleiades Gazetteer
- **URL**: https://pleiades.stoa.org
- **What it searches**: Community-built gazetteer of ancient places. Authoritative coordinates and metadata for ancient world locations.
- **Free tier**: Completely free (CC-BY)
- **API key needed**: No
- **Response format**: JSON-LD, CSV, KML, RDF -- id, title, description, names (ancient and modern), locations (lat/lon, precision), connectsWith, timeperiods, placeTypes, references
- **Archaeology relevance**: EXTREMELY HIGH. Purpose-built for ancient world research. Authoritative place identification used by major academic projects. Extensive coverage of Greek, Roman, and expanding other periods.
- **Rate limits**: Daily bulk exports available. Individual lookups via URL. No documented rate limits.
- **Notable limitations**: Strongest for Greek and Roman world (expanding). Community-maintained (can have gaps). No full REST search endpoint -- primarily individual record lookups and bulk downloads.

### 9.2 Peripleo / Pelagios Network
- **URL**: https://pelagios.org / https://github.com/pelagios/peripleo
- **What it searches**: Linked open data from archaeological datasets, gazetteers, museum collections (British Museum, Pleiades, etc.)
- **Free tier**: Completely free
- **API key needed**: No
- **Response format**: JSON -- items (artifacts, texts, photos), places (gazetteer URIs), datasets. Searchable by keyword, place, space, time, dataset, object type.
- **Archaeology relevance**: EXTREMELY HIGH. Purpose-built for ancient world data discovery. Links artifacts to places to time periods across multiple institutional datasets.
- **Rate limits**: Not documented. CORS and JSONP supported.
- **Notable limitations**: Original Peripleo is deprecated (see GitHub). Peripleo-lite is newer but lighter. Data depends on partner contributions. Not all ancient world data is linked yet.

### 9.3 Open Context
- **URL**: https://opencontext.org/about/services
- **What it searches**: Archaeological and related research data -- excavation data, images, field notes, 3D models, maps
- **Free tier**: Completely free (CC licenses)
- **API key needed**: No
- **Response format**: JSON-LD -- context, label, slug, category, project, geojson (coordinates), time ranges, observation data, links
- **Archaeology relevance**: EXTREMELY HIGH. Purpose-built as an archaeological data publisher. Primary field data from real excavations. Peer-reviewed editorial oversight.
- **Rate limits**: Not documented. Generous for research use.
- **Notable limitations**: Curated collection (not comprehensive). Smaller scale than generalist databases. Focus on primary data, not published papers.

### 9.4 tDAR (The Digital Archaeological Record)
- **URL**: https://core.tdar.org
- **What it searches**: Online archive for archaeological and historic preservation information
- **Free tier**: Free search access
- **API key needed**: Unknown (limited API documentation)
- **Response format**: Search interface returns structured results. API documentation limited.
- **Archaeology relevance**: EXTREMELY HIGH. Purpose-built archaeological archive. Grey literature, CRM reports, datasets, GIS files.
- **Notable limitations**: API documentation sparse. May require institutional access for some features. U.S.-focused.

### 9.5 Getty Vocabularies (AAT, TGN, ULAN)
- **URL**: https://www.getty.edu/research/tools/vocabularies/
- **What it searches**: Art & Architecture Thesaurus (AAT), Thesaurus of Geographic Names (TGN), Union List of Artist Names (ULAN)
- **Free tier**: Completely free (ODC-By license)
- **API key needed**: No
- **Response format**: XML (Web Services), SPARQL, JSON-LD. Returns term IDs, preferred/alternate names, hierarchies, scope notes, relationships.
- **Archaeology relevance**: VERY HIGH. AAT contains authoritative terms for archaeological materials, techniques, object types. TGN has historical place names. Essential for metadata standardization.
- **Rate limits**: Not documented.
- **Notable limitations**: XML Web Services being retired end of 2025. Transitioning to SPARQL/LOD endpoints. Not a search engine -- a controlled vocabulary/thesaurus.

---

## SUMMARY: TOP RECOMMENDATIONS BY USE CASE

### For finding scholarly papers about archaeology:
1. **OpenAlex** -- Best overall coverage + structured data + generous free tier
2. **Semantic Scholar** -- Best AI-powered relevance + abstracts + no key needed
3. **CORE** -- Best for grey literature / institutional repository content
4. **Crossref** -- Best for DOI metadata / journal article discovery

### For web search (finding institutional pages, reports, news):
1. **SearXNG** (self-hosted) -- Unlimited, free, aggregates 70+ engines
2. **Brave Search** -- Independent index, but free tier effectively dead
3. **Tavily** -- Best for AI/RAG integration with content extraction
4. **SerpAPI** -- Best for Google Scholar results (250/month free)

### For open access full text:
1. **Unpaywall** -- Find free PDFs for any DOI (100K/day)
2. **CORE** -- 40M+ full-text papers directly
3. **Internet Archive Scholar** -- 25M+ preserved papers
4. **DOAJ** -- Verified open access journals only

### For archaeological site/artifact data:
1. **Pleiades** -- Authoritative ancient place gazetteer
2. **Open Context** -- Primary excavation data
3. **Wikidata SPARQL** -- Structured archaeological site data with coordinates
4. **Europeana** -- European cultural heritage collections
5. **Portable Antiquities Scheme** -- 1.4M+ finds (UK)
6. **Smithsonian Open Access** -- Major archaeological collections

### For news about discoveries:
1. **NewsData.io** -- Best free tier for commercial use (200 credits/day)
2. **GNews** -- 100 req/day, multi-language
3. **NewsAPI.org** -- 100 req/day, development-only

### For citation analysis:
1. **OpenCitations** -- 624M+ open citation links
2. **Crossref** -- Reference lists in metadata
3. **Semantic Scholar** -- Citation counts + citation graph API
4. **OpenAlex** -- Citation counts + concept linkage

---

## IMPLEMENTATION PRIORITY FOR ANCIENTMAP PIPELINE

Based on the pipeline's needs (finding quality sources about archaeological sites, historical places, geological features):

| Priority | API | Why | Integration Effort |
|----------|-----|-----|-------------------|
| P0 | OpenAlex | 250M works, free, excellent metadata | Low (REST + JSON) |
| P0 | Semantic Scholar | AI-ranked results, no key needed | Low (REST + JSON) |
| P0 | Wikidata SPARQL | Site coordinates + structured data | Medium (SPARQL) |
| P1 | Crossref | DOI resolution, reference data | Low (REST + JSON) |
| P1 | Unpaywall | Find free full-text for DOIs | Low (REST + JSON) |
| P1 | Europeana | European heritage collections | Low (REST + JSON) |
| P1 | Pleiades | Ancient place authority data | Low (JSON-LD/CSV) |
| P2 | CORE | Grey literature, repository content | Low (REST + JSON) |
| P2 | Smithsonian | Archaeological collections | Low (REST + JSON) |
| P2 | Internet Archive | Historical documents, books | Low (REST + JSON) |
| P2 | OpenCitations | Citation networks | Low (REST + JSON) |
| P3 | SearXNG | Web search backup (self-hosted) | Medium (Docker) |
| P3 | SerpAPI | Google Scholar (250/month) | Low (REST + JSON) |
| P3 | NewsData.io | Discovery news | Low (REST + JSON) |
| P3 | Open Context | Primary excavation data | Low (JSON-LD) |

---

*Research conducted April 4, 2026. API pricing and availability subject to change.*
