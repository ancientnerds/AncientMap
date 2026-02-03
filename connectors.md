# Best archaeological data sources to replace Smithsonian for site and empire popup content

The optimal strategy for comprehensive archaeological content combines **three to four major aggregators** with **specialized regional databases**. The Metropolitan Museum API, Europeana, and ARIADNE Portal together provide CC0-licensed artifacts, pan-European integration, and archaeology-specific metadata covering **60+ million records**—far exceeding Smithsonian's 5.1 million items while maintaining or improving academic credibility.

## Tier 1: Essential sources with excellent API access

These databases offer the strongest combination of academic rigor, API documentation, licensing, and coverage.

### Metropolitan Museum of Art Open Access

The **gold standard** for museum open access provides **470,000+ artworks** spanning 5,000 years across all geographic regions. The Egyptian, Greek and Roman, Ancient Near Eastern, and Asian art departments contain exceptional archaeological content with excavation provenance data.

**API:** RESTful JSON API at `collectionapi.metmuseum.org`, no key required, 80 requests/second
**Formats:** JSON, CSV bulk download via GitHub
**License:** Creative Commons Zero (CC0)—completely unrestricted commercial/non-commercial use
**Metadata quality:** Excellent—includes geographic provenance (city through locus level), excavation information, periods, dynasties, machine-readable dates, links to Getty AAT/ULAN and Wikidata
**Strengths:** Unparalleled open licensing, robust documentation, comprehensive ancient world collections, **406,000+ high-resolution images**
**Limitations:** Must retrieve images individually rather than bulk download; some older records have sparse metadata

### Europeana Cultural Heritage Platform

Europe's largest cultural aggregator brings together **59+ million items** from 4,000+ institutions across the continent. Content spans books, artworks, photographs, manuscripts, 3D objects, and archaeological materials aggregated from national museums and archives.

**API:** Multiple access methods—Search API, Record API, IIIF APIs, Entity API (people/places/concepts), SPARQL endpoint, OAI-PMH harvesting, Thumbnail API
**Formats:** JSON, JSON-LD, RDF/XML using Europeana Data Model (EDM)
**License:** Per-item rights statements with clear labeling; significant portion CC0 or public domain
**Metadata quality:** Variable by provider but enriched with links to Getty AAT, GeoNames, Wikidata, VIAF, DBPedia
**Strengths:** Massive aggregated collection, multiple APIs for different use cases, IIIF support, multilingual labels, semantic interoperability
**Limitations:** Metadata quality varies by contributing institution; must trace back to original providers for full data on some items

### ARIADNE Portal

The **only archaeology-specific aggregator** at this scale, ARIADNE integrates **3.8+ million archaeological research datasets** from 40+ European institutions. Content includes grey literature, unpublished excavation reports, fieldwork data, 3D models, and environmental archaeology data—materials typically unavailable elsewhere.

**API:** REST API, SPARQL endpoint, Linked Open Data
**Formats:** XML, RDF, CIDOC-CRM compliant with AO-Cat archaeological application profile
**License:** Varies by dataset provider; most openly accessible
**Metadata quality:** High—standardized via CIDOC-CRM mapping, integrated with Getty AAT vocabulary spine
**Coverage:** Pan-European with growing international partners; all periods from Paleolithic to modern
**Strengths:** Purpose-built for archaeology, includes grey literature that commercial publishers miss, virtual research environment tools, 3D visualization services
**Limitations:** Metadata aggregator that links to original repositories; access depends on individual provider policies

### Open Context

The most developer-friendly archaeological data platform publishes **1+ million digital resources** with primary research data—excavation records, artifact analyses, field notes, zooarchaeological data, and 3D models. The **DINAA integration** alone contributes 500,000+ North American site records.

**API:** Full REST API with excellent documentation at `opencontext.org/about/services`, API cookbook with recipes
**Formats:** JSON-LD (Linked Open Data), GeoJSON, CSV
**License:** All content under Creative Commons licenses (typically CC-BY)
**Metadata quality:** Excellent—integrates with Pleiades gazetteer, Encyclopedia of Life, PeriodO for standardized periods; DOIs assigned
**Strengths:** Best API documentation in the field, GeoJSON for direct map integration, peer-reviewed data publishing model, California Digital Library archiving ensures long-term preservation
**Limitations:** One-time publishing fee for data submission; editorial review process means slower additions

---

## Tier 2: Major institutional collections

### British Museum Collection Database

Containing **2+ million database records** from 8 million physical objects, the British Museum offers unparalleled depth in Egyptian, Mesopotamian, Greek, Roman, and British archaeology spanning 2 million years. The **SPARQL endpoint** at `collection.britishmuseum.org` enables complex queries using the CIDOC-CRM semantic model.

**API:** SPARQL endpoint with RDF/XML, Turtle, N-Triples output; REST interface for JSON/CSV
**License:** Non-commercial and research use under British Museum license; commercial image licensing available separately
**Metadata quality:** Very high—250 years of cataloging history, 155,000+ biographical names in thesauri
**Strengths:** Outstanding ancient civilization holdings, semantic web compliant, CIDOC-CRM enables cross-collection interoperability
**Limitations:** More restrictive licensing than Met; SPARQL queries require technical expertise; image licensing is separate and complex

### Getty Research Institute

Beyond the museum's **88,000+ CC0 images**, Getty provides critical infrastructure through its **vocabularies**—the Art & Architecture Thesaurus (57,390+ concepts), Thesaurus of Geographic Names (2 million+ places), and Union List of Artist Names (367,590+ creator records).

**API:** SPARQL endpoint at `vocab.getty.edu`, web services (XML/JSON), OpenRefine reconciliation service
**Formats:** RDF, JSON-LD, N-Triples, Turtle, SKOS
**License:** Open Data Commons Attribution (ODC-By) for vocabularies; CC0 for museum images
**Why essential:** Getty vocabularies serve as the controlled vocabulary backbone for most major archaeological databases—linking terms across Open Context, ARIADNE, British Museum, and others

### Louvre Collections Database

With **500,000+ works** including exceptional Near Eastern, Egyptian, Greek, Etruscan, Roman, and Islamic antiquities, the Louvre provides simple JSON access by appending `.json` to any record URL.

**API:** No formal REST API, but JSON available via URL modification; CSV export; ARK persistent identifiers
**License:** Subject to Terms of Use; commercial use may require permissions
**Strengths:** World-class antiquities from French excavations; direct JSON access without complex authentication
**Limitations:** Primary interface in French; no bulk API

---

## Specialized content sources by type

### Academic papers and scholarly publications

**CORE (COnnecting REpositories)** aggregates **207+ million open access articles** from 10,000+ data providers with a full REST API at `core.ac.uk/services/api`. Free for research, commercial use requires paid subscription. This is the largest OA aggregator with real-time access to metadata and full texts.

**JSTOR** provides authoritative peer-reviewed content including the *American Journal of Archaeology* (since 1885) and *Journal of Archaeological Research*. The **Data for Research platform** (now Constellate) enables text mining with up to 1,000 articles by default; larger requests require contact. Access is subscription-based with pre-1923 US content freely available.

**Internet Archaeology** at `intarch.ac.uk` publishes peer-reviewed digital-native research with integrated multimedia under **CC-BY 3.0**—no article processing charges and full DOI assignment.

### High-quality artifact photographs and imagery

**Wikimedia Commons** hosts **90+ million freely usable media files** including the **1.6 million heritage listings** in its Monuments Database and **614,980+ Portable Antiquities Scheme images**. The MediaWiki API provides robust programmatic access with all files under open licenses (CC-BY, CC-BY-SA, CC0, public domain).

**JSTOR Images** (formerly Artstor) offers millions of scholarly-curated images from 1,500+ institutions. The **Open Artstor** collections under CC0 include Metropolitan Museum, Cleveland Museum, and Te Papa Tongarewa content. Institutional subscription required for full access.

**Google Arts & Culture** partners with 2,000+ museums to provide **gigapixel "Art Camera" images** (up to 7 billion pixels per image) and Street View of galleries. However, there is no official public API—content is designed for consumption rather than integration.

### Historical books, texts, and manuscripts

**HathiTrust Digital Library** contains **19+ million digitized volumes** from 60+ partner research libraries with a Bibliographic API and Data API (page images, OCR, METS metadata). Daily HathiFiles provide tab-delimited metadata for all items. Most content is copyright-restricted; full access requires institutional membership.

**Internet Archive** offers **946+ billion archived web pages** plus millions of texts, books, and media with a **read/write Metadata API**. Many items are public domain with direct downloads available.

**Perseus Digital Library** provides the canonical **Greek and Latin textual corpus**—2,412 works in 3,192 editions with 69.7 million words. The **CTS (Canonical Text Services) API** enables URN-based citation access with TEI XML output. The R package `rperseus` provides convenient access.

**Chinese Text Project (CTEXT)** is the **largest pre-modern Chinese text database** with 30,000+ titles and 5+ billion characters. The JSON API at `ctext.org/tools/api` supports Python wrapper access (`pip install ctext`).

### 3D models and site reconstructions

**Sketchfab Cultural Heritage** hosts thousands of 3D models from museums, universities, and archaeologists with download options in OBJ, GLB, USDZ formats. **CyArk** contributes 217+ museum-grade laser scans of UNESCO sites including Ishtar Gate, Pompeii temples, and Tikal.

**Smithsonian 3D Digitization** at `3d.si.edu` provides **3,989 CC0 3D models** including fossils, artifacts, and spacecraft in multiple formats—though this represents only a fraction of their 157 million objects.

### Historical photographs and maps

**Library of Congress Prints & Photographs Division** contains **15+ million items** with a JSON HTTP API at `loc.gov/pictures/api`. Notable collections include the **Matson Collection (Middle East 1898-1946)**, Civil War photographs, and Historic American Buildings Survey. Most content is public domain.

**U.S. National Archives** provides a **read/write REST API** at `catalog.archives.gov/api/v2/` with millions of photographs and documents. Content is public domain as federal government works with bulk download via AWS Open Data Registry.

**David Rumsey Historical Map Collection** offers **144,000+ high-resolution historical maps** from the 16th-21st centuries with a GIS browser for georeferenced overlay analysis. Free for non-commercial use; permission required for commercial applications.

---

## Regional specialized databases with coordinate data

For map popup integration, these databases provide the essential geographic coordinates and site-level data.

### Mediterranean and Classical world

**Pleiades** is the authoritative ancient places gazetteer with **30,000+ locations** covering the Greek and Roman world (750 BCE–640 CE). The REST API provides daily JSON exports, CSV for GIS, KML/KMZ, RDF/Turtle, and GeoJSON via GitHub. All data is **CC-BY 3.0** with precise coordinate data including accuracy radius in meters. This is the essential linking resource—Pleiades URIs connect Open Context, Pelagios, and World Historical Gazetteer.

**ORBIS** at `orbis.stanford.edu` models Roman transportation with **751 sites** and extensive road/river/sea route networks. It provides unique travel time/cost calculations accounting for seasonal variation.

### Near East and cuneiform studies

**CDLI (Cuneiform Digital Library Initiative)** catalogs **368,735+ tablets** with REST API, SPARQL endpoint, and Linked Open Data output in JSON-LD, RDF, and Turtle. The Python API client at `github.com/cdli-gh/framework-api-client` provides convenient access. Geographic data is limited to site-level provenience.

### Americas

**tDAR** hosts **358,000+ technical reports** with strong North American Southwest coverage. DOI-based citations and some API access available; variable GIS data by contributor.

**FAMSI** provides the definitive Maya resources including the **Kerr Maya Vase Database**, Schele Drawing Archive, and Maya Hieroglyphic Dictionary—essential for Mesoamerican iconography though lacking structured API access.

### Africa and Middle East

**EAMENA** documents **338,000+ Heritage Place records** across the Middle East and North Africa using satellite imagery with full coordinates on the Arches 7 platform. GeoJSON export to Zenodo with DOI citations provides excellent map integration.

**MAEASaM** covers eight African countries from Palaeolithic to 20th century on the same Arches platform—the first systematic pan-African archaeological site database.

### UK and Ireland heritage data

**Historic England NHLE** provides **400,000+ listed buildings and scheduled monuments** with GIS Feature Services via ArcGIS Hub. Download Shapefiles, GeoJSON, CSV under **Open Government Licence**.

**Ireland Sites and Monuments Record** offers **80,000+ archaeological records** with ArcGIS Feature Service REST API and CSV/GeoJSON download under **CC-BY 4.0**—excellent licensing for integration.

**Portable Antiquities Scheme** records **1.6+ million objects** and 600,000+ images of metal-detected finds with REST API and JSON output. Licensed **CC-BY-NC-SA**.

### Epigraphy and numismatics

**Nomisma.org** provides the Linked Open Data standard for numismatics with REST APIs, SPARQL endpoint, and OpenRefine reconciliation. Data is CC-BY with Open Database License for partners.

**Epigraphic Database Heidelberg** contains **81,000+ Latin and Greek inscriptions** with 43,000+ photos in EpiDoc XML, RDF, and GeoJSON under **CC-BY-SA 4.0**. Note: funding ended 2021 and data is no longer actively maintained.

---

## API integration comparison matrix

| Source | Records | API Type | License | GIS Data | Best For |
|--------|---------|----------|---------|----------|----------|
| Metropolitan Museum | 470K+ | REST/JSON | **CC0** | Limited | Artifact images, metadata |
| Europeana | 59M+ | Multiple | Varies | Via providers | European aggregation |
| ARIADNE | 3.8M+ | SPARQL/REST | Varies | Via partners | Archaeological datasets |
| Open Context | 1M+ | **REST** | CC-BY | **GeoJSON** | Primary excavation data |
| British Museum | 2M+ | SPARQL | Non-commercial | Limited | Near East, Egypt, Classical |
| Pleiades | 30K+ | REST | **CC-BY** | **Excellent** | Ancient places gazetteer |
| CDLI | 368K+ | REST/SPARQL | Open | Site-level | Cuneiform texts |
| EAMENA | 338K+ | Arches | Open | **Full coordinates** | MENA heritage sites |
| Historic England | 400K+ | ArcGIS | **OGL** | **Shapefiles** | UK monuments |
| Ireland SMR | 80K+ | ArcGIS | **CC-BY 4.0** | **GeoJSON** | Irish archaeology |
| Wikimedia Commons | 90M+ | MediaWiki | Open licenses | Varies | Images, public domain |
| Library of Congress | 15M+ | REST/JSON | Public domain | Limited | Historical photographs |

## Recommended implementation architecture

**For artifact/object popups:** Query Metropolitan Museum API first (CC0, best documentation), supplement with British Museum SPARQL for items not found, then Europeana as fallback aggregator.

**For site/location data:** Use Pleiades as the primary gazetteer for ancient Mediterranean, linking via URI to Open Context excavation data. For UK/Ireland, use Historic England and Ireland SMR with direct GeoJSON integration. For MENA, query EAMENA Arches database.

**For imagery:** Check Met Open Access images first (CC0), then Wikimedia Commons API for public domain alternatives, then Europeana thumbnails with proper rights attribution.

**For academic context:** Query CORE for open access papers related to sites/periods, link to Perseus for primary Greek/Latin texts, use Getty AAT for standardized terminology across all sources.

**For chronological standardization:** Implement PeriodO at `perio.do` as the period authority—its JSON-LD data provides scholarly definitions of archaeological periods that link with ARIADNE, ADS, and British Museum temporal terminology.

This architecture provides **global coverage** from prehistoric to medieval periods with **academically rigorous data** under **predominantly open licenses**, all accessible via documented APIs suitable for web application integration.