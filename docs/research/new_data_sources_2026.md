# New Data Sources for AncientMap Globe
## Research Date: 2026-03-02

This report identifies 40+ new open data sources for ancient/historical sites with geographic coordinates, organized by priority and region. Sources already in the project are excluded.

---

## HIGH PRIORITY SOURCES

### 1. Vici.org - Archaeological Atlas of Antiquity
- **URL**: https://vici.org/
- **Contains**: Roman-era archaeological sites: settlements, forts, villas, temples, roads, aqueducts, bridges, harbors, mines, amphitheaters. Primarily Greco-Roman but includes some data from India, China, East Africa.
- **Data access**: REST API returning GeoJSON. Also available on Datahub as Linked Open Data.
- **Record count**: ~20,000 locations with ~1,000 road tracings
- **Has coordinates**: Yes (lat/lon in GeoJSON)
- **License**: CC BY-SA 3.0
- **Priority**: HIGH - Excellent Roman-world coverage with a working GeoJSON API, easy to ingest

### 2. Ancient World Mapping Center (AWMC) Geodata
- **URL**: https://github.com/AWMC/geodata
- **Contains**: GeoJSON files of ancient world features: aqueducts, roads, regional names, coastlines, rivers, settlements. Focused on the classical Mediterranean world.
- **Data access**: Direct GeoJSON download from GitHub repository
- **Record count**: Multiple datasets covering the ancient Mediterranean
- **Has coordinates**: Yes (GeoJSON format, WGS84)
- **License**: ODC Open Database License
- **Priority**: HIGH - Clean GeoJSON on GitHub, trivial to ingest. Includes unique data on aqueducts/roads.

### 3. Itiner-e: Roman Roads of the Empire
- **URL**: https://itiner-e.org/ | Zenodo repository
- **Contains**: The most comprehensive dataset of Roman Empire roads ever compiled: 14,769 road segments totaling 299,171 km across ~4 million sq km.
- **Data access**: Download as GeoJSON (78 MB), Shapefile (144 MB), or GeoPackage (34 MB) from Zenodo
- **Record count**: 14,769 road segment records
- **Has coordinates**: Yes (WGS84 EPSG:4326 in GeoJSON)
- **License**: Open access (Scientific Data publication, 2025)
- **Priority**: HIGH - Unique, high-resolution dataset. Roman roads as line features on the globe would be visually stunning.

### 4. National Register of Historic Places (USA)
- **URL**: https://www.nps.gov/subjects/nationalregister/data-downloads.htm
- **Contains**: All nationally protected historic buildings and sites in the USA: archaeological sites, historic districts, buildings, structures, objects. Covers pre-Columbian to 20th century.
- **Data access**: Shapefile and GeoJSON downloads; ArcGIS REST API with JSON/GeoJSON output
- **Record count**: ~95,000+ listed properties with coordinates
- **Has coordinates**: Yes (lat/lon from nomination forms; points for <10 acres, polygons for >10 acres)
- **License**: Public domain (US Government data)
- **Priority**: HIGH - Massive dataset, public domain, fills North America gap. Includes many pre-Columbian and colonial archaeological sites.

### 5. LIST: Latin Inscriptions in Space and Time
- **URL**: https://zenodo.org/record/7870085
- **Contains**: 525,870 Latin inscriptions from the Roman world, aggregated from EDH and EDCS, enriched with 65 attributes including chronology, geography, and inscription type.
- **Data access**: Direct download as GeoJSON and Parquet from Zenodo. Loadable via geopandas.
- **Record count**: 525,870 inscriptions; 511,973 with valid coordinates
- **Has coordinates**: Yes (Latitude/Longitude columns + geometry point in GeoJSON/Parquet)
- **License**: Open access
- **Priority**: HIGH - Half a million georeferenced inscriptions. Unique dataset showing the reach of Roman literacy.

### 6. p3k14c: Global Archaeological Radiocarbon Database
- **URL**: https://www.p3k14c.org/ | https://core.tdar.org/collection/70213/p3k14c-data
- **Contains**: 180,070 radiocarbon dates from archaeological sites worldwide, covering all continents. The largest global compilation of archaeological C14 dates.
- **Data access**: Download from tDAR and GitHub. Available as CSV/data tables.
- **Record count**: 180,070 dates from tens of thousands of sites globally
- **Has coordinates**: Yes (though US/Canada coordinates are obfuscated for site protection)
- **License**: Open access with attribution
- **Priority**: HIGH - Global coverage, massive dataset. Each date represents an archaeological site. Best for non-US/Canada sites where coordinates are precise.

### 7. ROCEEH Out of Africa Database (ROAD)
- **URL**: https://www.roceeh.uni-tuebingen.de/roadweb/
- **Contains**: Paleolithic and early human archaeological sites with cultural, anthropological, environmental, and geographical information. Covers the entire Out of Africa timeframe.
- **Data access**: Open web map (Simple Search), AskROAD query tool, PDF summary sheets. After registration: SQL queries and Map Module. Interoperable export formats.
- **Record count**: 2,300+ localities with 22,000+ assemblages
- **Has coordinates**: Yes
- **License**: Open access (registration required for full access)
- **Priority**: HIGH - Unique prehistoric/paleolithic focus. Fills deep-time archaeology gap.

### 8. Radiocarbon Palaeolithic Europe Database
- **URL**: https://ees.kuleuven.be/en/geography/projects/14c-palaeolithic
- **Contains**: Lower, Middle and Upper Palaeolithic sites across Europe and Siberia, older than 9,500 BP. Includes conventional C14, AMS, TL, OSL, ESR dating.
- **Data access**: Microsoft Access database, Excel files, and Google Earth coordinate files (TXT/KMZ). Available at Mendeley and Zenodo.
- **Record count**: 14,277 site forms with 20,665 radiometric dates (v32, March 2025)
- **Has coordinates**: Yes (most sites have coordinates; KMZ files for Google Earth)
- **License**: Open access
- **Priority**: HIGH - Deep prehistoric focus (Paleolithic). 14K+ sites with coordinates across Europe and Siberia.

### 9. Portable Antiquities Scheme (PAS)
- **URL**: https://finds.org.uk/database
- **Contains**: Archaeological finds discovered by the public across England and Wales. Covers prehistoric through post-medieval periods: coins, brooches, tools, weapons, pottery.
- **Data access**: REST API returning JSON. Source code on GitHub. Bulk export available for registered researchers.
- **Record count**: 1.4+ million recorded items with findspot locations
- **Has coordinates**: Yes (findspot coordinates, with varying precision levels)
- **License**: Open access with some restrictions on precise locations for research use
- **Priority**: HIGH - 1.4M+ records. API exists. Unique find-spot data rather than just site data.

### 10. Canmore (Scotland Historic Environment)
- **URL**: https://canmore.org.uk/ | https://portal.historicenvironment.scot/downloads/canmore
- **Contains**: Scotland's archaeology, buildings, industrial and maritime heritage. From prehistoric to modern.
- **Data access**: ESRI Shapefile download (British National Grid); WMS service available
- **Record count**: ~125,000 sites
- **Has coordinates**: Yes (British National Grid, convertible to WGS84)
- **License**: Open Government Licence
- **Priority**: HIGH - 125K sites with direct shapefile download. Complements Historic England data.

---

## MEDIUM-HIGH PRIORITY SOURCES

### 11. DARMC / Mapping Past Societies (Harvard)
- **URL**: https://darmc.harvard.edu/data-availability
- **Contains**: Roman and medieval world GIS data: cities, roads, shipwrecks, religious sites, economic data. The Roman Road network based on the Barrington Atlas.
- **Data access**: Shapefiles (.shp) and Excel (.xlsx) downloads
- **Record count**: Multiple datasets covering Roman/medieval world
- **Has coordinates**: Yes (GIS shapefiles)
- **License**: Free for scholarly use
- **Priority**: MEDIUM-HIGH - Established scholarly resource, complements DARE/Pleiades.

### 12. World Historical Gazetteer (WHG)
- **URL**: https://whgazetteer.org/
- **Contains**: Historical place records spanning from Bronze Age to 21st century, across all world regions. Includes settlements, buildings, countries, provinces, undersea locations.
- **Data access**: API for programmatic access; download augmented data files with coordinates; Linked Places Format (GeoJSON extension). CC BY 4.0.
- **Record count**: 2+ million place records across 70+ published datasets
- **Has coordinates**: Yes (via reconciliation process and Linked Places Format)
- **License**: CC BY 4.0
- **Priority**: MEDIUM-HIGH - 2M+ records, global coverage, API available. Good aggregation source.

### 13. Mycenaean Atlas Project
- **URL**: https://www.helladic.info/
- **Contains**: Bronze Age sites in the central and eastern Mediterranean: Mycenaean, Early/Middle Bronze Age, Sub-Mycenaean, Geometric period sites.
- **Data access**: CSV downloads for Google Earth import; full database available in PDF on request; online SQL queries
- **Record count**: 5,636 Bronze Age sites (4,300+ named and located)
- **Has coordinates**: Yes (lat/lon pairs, accurate)
- **License**: Open access
- **Priority**: MEDIUM-HIGH - Unique Bronze Age Mediterranean focus with accurate coordinates.

### 14. Coflein (Wales Historic Environment)
- **URL**: https://coflein.gov.uk/ | https://datamap.gov.wales/
- **Contains**: Archaeological sites, monuments, buildings, and maritime sites across Wales. From prehistoric to modern.
- **Data access**: Download from DataMap Wales as terrestrial and maritime datasets. OGL license.
- **Record count**: 110,000+ sites
- **Has coordinates**: Yes
- **License**: Open Government Licence
- **Priority**: MEDIUM-HIGH - 110K+ sites, direct download, complements England/Scotland data.

### 15. NOAA Wrecks and Obstructions Database
- **URL**: https://www.nauticalcharts.noaa.gov/data/wrecks-and-obstructions.html
- **Contains**: Submerged shipwrecks and obstructions within US maritime boundaries. Includes position, description, depth information.
- **Data access**: KML/KMZ, Excel, ArcGIS REST services, OGC WMS. REST endpoint available.
- **Record count**: ~13,000 wrecks + ~6,000 obstructions
- **Has coordinates**: Yes (lat/lon for each feature)
- **License**: Public domain (US Government)
- **Priority**: MEDIUM-HIGH - 13K+ wrecks with coordinates, public domain, easy REST API access.

### 16. TAY Project (Archaeological Settlements of Turkey)
- **URL**: http://tayproject.org/
- **Contains**: All archaeological settlements in Turkey: mounds, monuments, tumuli, cemeteries. From prehistoric to Ottoman. The earliest online GIS project in Turkey.
- **Data access**: Online GIS interface and database queries
- **Record count**: 12,000+ sites with 44,000+ images
- **Has coordinates**: Yes (GIS-integrated)
- **License**: Open access
- **Priority**: MEDIUM-HIGH - 12K+ sites in a key region (Anatolia). Fills Turkey/Near East gap.

### 17. MAEASaM (Mapping Africa's Endangered Archaeological Sites)
- **URL**: https://maeasam.org/database/
- **Contains**: Archaeological sites and monuments across 8+ African countries: Botswana, Ethiopia, Kenya, Mali, Senegal, Sudan, Tanzania, Zimbabwe. Palaeolithic to 20th century.
- **Data access**: Arches-based geospatial database (Phase 2 making it publicly accessible)
- **Record count**: 67,000+ sites documented via satellite + 31,000+ digitized legacy records
- **Has coordinates**: Yes (geospatial database)
- **License**: Open access (Arches platform)
- **Priority**: MEDIUM-HIGH - Fills critical Sub-Saharan Africa gap. 67K+ sites. Database going public in Phase 2.

### 18. LuwianSiteAtlas
- **URL**: https://luwianstudies.org/siteatlas/ | Zenodo
- **Contains**: 483 Bronze Age archaeological sites in western Anatolia (2000-1200 BCE). Each georeferenced with metadata on chronology, function, material culture, mineral resources.
- **Data access**: Zenodo download (open access files); interactive web map (LuwianSiteMap)
- **Record count**: 483 sites
- **Has coordinates**: Yes (WGS 84, precise)
- **License**: Open access (published in Scientific Data, 2025)
- **Priority**: MEDIUM-HIGH - Small but very high quality. Unique Bronze Age Anatolia coverage.

### 19. MAHSA (Mapping Archaeological Heritage in South Asia)
- **URL**: https://databasemahsa.org/ | https://www.mahsa.arch.cam.ac.uk/
- **Contains**: Archaeological and cultural heritage of the Indus River Basin and surrounding areas (Pakistan, India, Afghanistan). Includes location, size, shape, periods of occupation, preservation status.
- **Data access**: Open access Arches geospatial database with web interface
- **Record count**: Growing (project ongoing, funded through 2024+)
- **Has coordinates**: Yes (Arches geospatial platform)
- **License**: Open access
- **Priority**: MEDIUM-HIGH - Fills critical South Asia gap. Indus Valley civilization coverage.

### 20. Digital Archaeological Atlas of the Holy Land (DAAHL)
- **URL**: https://daahl.ucsd.edu/
- **Contains**: Archaeological sites across Israel, Palestine, Jordan, southern Lebanon, Syria, Cyprus, Sinai. From remote prehistory to dissolution of the Ottoman Empire.
- **Data access**: Online database search and GIS mapping tools via Google Maps/Earth
- **Record count**: 27,000+ archaeological sites
- **Has coordinates**: Yes (GIS-integrated)
- **License**: Free access for research
- **Priority**: MEDIUM-HIGH - 27K+ sites in a deeply excavated region. Fills Levant gap.

---

## MEDIUM PRIORITY SOURCES

### 21. Rijksmonumentenregister (Netherlands)
- **URL**: https://linkeddata.cultureelerfgoed.nl/ | https://monumentenregister.cultureelerfgoed.nl/
- **Contains**: All nationally protected monuments in the Netherlands: churches, castles, windmills, historic buildings, archaeological sites.
- **Data access**: SPARQL endpoint (Linked Open Data), REST API with geometric coordinates
- **Record count**: 63,000+ monuments
- **Has coordinates**: Yes (X/Y coordinates in structured format)
- **License**: CC BY 4.0
- **Priority**: MEDIUM - 63K+ records with coordinates and SPARQL/API access. Good European coverage.

### 22. French Monuments Historiques (Base Merimee / data.gouv.fr)
- **URL**: https://data.culture.gouv.fr/ | https://data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2
- **Contains**: French architectural heritage from prehistory to present: civil, religious, military, funeral, industrial, and garden architecture.
- **Data access**: CSV download from data.gouv.fr. API access via regional open data portals. Note: coordinates derived by joining with commune centroids, not per-monument GPS.
- **Record count**: 320,000+ records
- **Has coordinates**: Indirectly (commune-level geocoding, not per-monument)
- **License**: Open Licence (French government)
- **Priority**: MEDIUM - Large dataset but coordinates are commune-level, not precise. Would need geocoding enhancement.

### 23. Archaeological Map of Egypt (CULTNAT)
- **URL**: https://archmap.cultnat.org/
- **Contains**: Archaeological sites across all 27 Egyptian governorates: pyramids, temples, tombs, ancient settlements. Predynastic through Islamic era.
- **Data access**: Web-based interactive GIS map with site browsing. API/download availability unclear.
- **Record count**: 1,180+ documented sites
- **Has coordinates**: Yes (GIS-based with site-level coordinates)
- **License**: Research access (may require scraping or partnership)
- **Priority**: MEDIUM - Unique Egyptian coverage but unclear API. May need web scraping or partnership.

### 24. THANADOS (Early Medieval Cemeteries)
- **URL**: https://thanados.net/
- **Contains**: Early Medieval cemeteries in Austria and neighboring countries. Graves, individuals, finds, osteology data. Built on OpenAtlas.
- **Data access**: API with various output formats (JSON, etc.); raw data download available; CC license
- **Record count**: 563 cemeteries, 5,363 graves, 11,555 finds
- **Has coordinates**: Yes (site-level coordinates via OpenAtlas/API)
- **License**: Creative Commons
- **Priority**: MEDIUM - Small but clean dataset with working API. Unique early medieval focus.

### 25. ArkeoGIS / ArkeOpen
- **URL**: https://arkeogis.org/ | ArkeOpen on NAKALA
- **Contains**: Cross-border, diachronic archaeological and paleoenvironmental data from prehistory to present. Sites, objects, and analyses across European regions.
- **Data access**: Online queries with CSV export; Open Data via ArkeOpen/NAKALA repository (FAIR-compliant)
- **Record count**: Tens of thousands of sites/objects
- **Has coordinates**: Yes (georeferenced sites)
- **License**: FAIR principles, varies by contributing database
- **Priority**: MEDIUM - Aggregator of European archaeological data. Good for filling gaps.

### 26. Bhuvan/SMARAC India Heritage Monuments
- **URL**: https://bhuvan-app1.nrsc.gov.in/culture_monuments/
- **Contains**: All ASI (Archaeological Survey of India) protected monuments across India: temples, forts, mosques, tombs, stupas, caves.
- **Data access**: WMS service (OGC compliant). WFS disabled. GeoRSS XML output available. Manual shapefile extraction per monument.
- **Record count**: 3,600+ ASI-protected monuments
- **Has coordinates**: Yes (via WMS/GeoRSS)
- **License**: Government of India data
- **Priority**: MEDIUM - Fills India gap. 3,600+ major monuments. WMS scraping required since no bulk download.

### 27. Korean Cultural Heritage Open Data
- **URL**: https://www.data.go.kr/en/index.do (search "cultural heritage")
- **Contains**: Korean cultural heritage properties: temples, fortresses, royal tombs, dolmens, pagodas. Covers Three Kingdoms period through Joseon dynasty.
- **Data access**: Open APIs via Korea's national data portal. Search the "Culture" category.
- **Record count**: Thousands (Korea has ~15,000 designated cultural properties)
- **Has coordinates**: Yes (API responses include location data)
- **License**: Korean Open Government License
- **Priority**: MEDIUM - Fills Korea gap. API access available. Needs exploration of specific endpoints.

### 28. ARIADNE Portal
- **URL**: https://portal.ariadne-infrastructure.eu/
- **Contains**: Aggregated archaeological resources from 41 European partners: reports, findings, inscriptions, sites, monuments. Covers all of European archaeology.
- **Data access**: Web portal with search/filter; Linked Open Data; potential API access
- **Record count**: 4+ million archaeological resource records
- **Has coordinates**: Many records have spatial metadata (searchable by location)
- **License**: Varies by contributing institution
- **Priority**: MEDIUM - Massive aggregator but complex to extract coordinates systematically. Best as a meta-source.

### 29. Israel Antiquities Authority (IAA) National Database
- **URL**: https://archives.iaa.org.il/ | https://survey.iaa.org.il/
- **Contains**: 4M+ archaeological records: artifacts, images, 3D models, excavation reports. Interactive geographic search across all Israeli archaeological sites.
- **Data access**: Web-based geographic search. Free registration for deep access. API unclear.
- **Record count**: 3,910,005 records (964K artifacts, 1.2M images, 15K 3D models)
- **Has coordinates**: Yes (geographic rectangle coordinates per site declaration)
- **License**: Free access with registration
- **Priority**: MEDIUM - Massive Israeli archaeology database. Just launched September 2025.

### 30. American Battlefield Protection Program (ABPP)
- **URL**: https://www.nps.gov/orgs/2287/battlefield-boundaries-map.htm
- **Contains**: Revolutionary War, War of 1812, and Civil War battlefields in the United States. Includes site name, code, war, state, acreage.
- **Data access**: ArcGIS Hub with interactive map; polygon boundaries available
- **Record count**: Hundreds of battlefield sites
- **Has coordinates**: Yes (polygon boundaries)
- **License**: Public domain (US Government)
- **Priority**: MEDIUM - Fills US battlefields gap. Public domain. Polygon data for battle boundaries.

### 31. EBIDAT (European Castles Database)
- **URL**: https://www.ebidat.de/
- **Contains**: Castles and fortifications across Europe (focus on German-speaking countries). Records both extant and disappeared sites, including those known only from historical sources.
- **Data access**: Online database search. Maintained by Europaeisches Burgeninstitut.
- **Record count**: Thousands of castle sites across Europe
- **Has coordinates**: Likely (GIS-integrated)
- **License**: Research access
- **Priority**: MEDIUM - European castles coverage. May need scraping or partnership for bulk data.

### 32. Oxford Roman Economy Project: Stone Quarries Gazetteer
- **URL**: https://oxrep.classics.ox.ac.uk/docs/Stone_Quarries_Database.pdf
- **Contains**: Stone quarries used in the Roman world. Coordinates in decimal degrees for mapping and future research.
- **Data access**: PDF gazetteer (can be parsed) with coordinates
- **Record count**: Hundreds of quarry sites
- **Has coordinates**: Yes (decimal degree coordinates)
- **License**: Open access (Oxford publication)
- **Priority**: MEDIUM - Unique ancient quarries dataset. Small but fills a specific niche.

---

## MEDIUM-LOW PRIORITY SOURCES

### 33. Ancient Locations Database
- **URL**: https://www.ancientlocations.net/
- **Contains**: Placemarks of archaeological sites from the ancient world. Global coverage with emphasis on classical antiquity.
- **Data access**: Online database with KML/KMZ export for Google Earth
- **Record count**: 25,307 placemarks (4,235 shown on main site)
- **Has coordinates**: Yes (Google Earth placemarks)
- **License**: Free access
- **Priority**: MEDIUM-LOW - Large placemark collection but may overlap with Pleiades/Wikidata. Useful for gap-filling.

### 34. Peruvian Amazon Archaeological Sites
- **URL**: https://www.nature.com/articles/s41597-021-01067-7 (Scientific Data publication)
- **Contains**: 400+ previously unpublished archaeological sites in the Department of Loreto, Peruvian Amazon. Pre-Columbian occupation.
- **Data access**: Dataset accompanying Scientific Data publication (downloadable)
- **Record count**: 400+ sites
- **Has coordinates**: Yes (geolocation for each site)
- **License**: Open access
- **Priority**: MEDIUM-LOW - Small but fills unique Amazonian gap. Pre-Columbian sites in understudied region.

### 35. Xinjiang Cultural Sites (Paleolithic to Bronze Age)
- **URL**: https://www.nature.com/articles/s41597-022-01306-5
- **Contains**: 1,655 cultural sites from Paleolithic through Bronze Age in Xinjiang, China. Each with calibrated longitude/latitude from satellite imagery.
- **Data access**: Dataset from Scientific Data publication (downloadable)
- **Record count**: 1,655 sites
- **Has coordinates**: Yes (WGS-84, calibrated from satellite imagery)
- **License**: Open access
- **Priority**: MEDIUM-LOW - Fills China gap. Unique coverage of Central Asian archaeology.

### 36. Pacific Archaeology Radiocarbon Database (PARD)
- **URL**: ArcGIS Online
- **Contains**: Radiocarbon data from archaeological sites across Near and Remote Oceania (300+ Pacific islands).
- **Data access**: ArcGIS Online searchable interface with locational navigation
- **Record count**: 17,000+ radiocarbon measurements
- **Has coordinates**: Yes (island-level locations)
- **License**: Research access
- **Priority**: MEDIUM-LOW - Fills Pacific Islands/Oceania gap. 17K measurements but need to extract site-level coordinates.

### 37. Pofatu (Pacific Geochemical Sourcing Database)
- **URL**: https://www.nature.com/articles/s41597-020-0485-8
- **Contains**: Geochemical compositions of archaeological sources and artefacts across the Pacific Islands. Stone tool sourcing data.
- **Data access**: Open-access database (online)
- **Record count**: 7,759 individual samples
- **Has coordinates**: Yes (site/source locations)
- **License**: Open access
- **Priority**: MEDIUM-LOW - Fills Oceania gap. Unique geochemical sourcing perspective.

### 38. IsoArcH (Isotope Archaeology Database)
- **URL**: https://isoarch.org/
- **Contains**: Bioarchaeological isotope data from prehistoric and historical periods worldwide. Organized by archaeological site with chronological and geographic metadata.
- **Data access**: Interactive web query tool with data visualization on ancient world maps
- **Record count**: 40,000+ isotope data points from 500+ archaeological sites
- **Has coordinates**: Yes (per-site geographic coordinates)
- **License**: Free to use, follows FAIR/CARE principles
- **Priority**: MEDIUM-LOW - 500+ sites globally. Unique isotopic data perspective.

### 39. ORBIS (Stanford Roman World Network)
- **URL**: https://orbis.stanford.edu/
- **Contains**: Geospatial network model of the Roman world: 751 sites (cities, ports, mountain passes) with travel routes and cost calculations. Reflects ~200 CE.
- **Data access**: Web interface. Roma Data Pipeline on GitHub aggregates ORBIS + other sources into SQLite with GeoJSON export (35K+ locations, 16.5K+ roads).
- **Record count**: 751 sites in ORBIS; 35,000+ via Roma Data Pipeline aggregation
- **Has coordinates**: Yes
- **License**: Free for academic use; Roma pipeline: open source
- **Priority**: MEDIUM-LOW - Mostly overlaps with Pleiades. The Roma Data Pipeline is more interesting as an aggregated source.

### 40. Peripleo (Pelagios Network)
- **URL**: https://pelagios.org/ | GitHub: pelagios/peripleo
- **Contains**: Linked Open Data browser for historical places, connecting data from British Museum, Portable Antiquities Scheme, Pleiades, and other partners.
- **Data access**: JSON API with CORS/JSONP support. Search by keyword, place, space, time, dataset, object type.
- **Record count**: Aggregates across multiple partner datasets
- **Has coordinates**: Yes (linked geographic data)
- **License**: Open (Linked Open Data)
- **Priority**: MEDIUM-LOW - More of a meta-search/aggregation tool than a primary source. API useful for discovery.

### 41. Archaeology Data Service (ADS, UK)
- **URL**: https://archaeologydataservice.ac.uk/
- **Contains**: 1.3+ million metadata records of British Isles archaeology: fieldwork reports, excavation archives, research projects. 50,000+ unpublished reports.
- **Data access**: OAI-PMH, DataCite API (XML, JSON, JSON-LD). Web form acceptance required.
- **Record count**: 1.3 million metadata records
- **Has coordinates**: Variable (some datasets have coordinates, others are report-level)
- **License**: Open access for teaching/learning/research (not commercial)
- **Priority**: MEDIUM-LOW - Huge archive but heterogeneous. Best for specific dataset extraction.

### 42. Battle Location Dataset (Harvard Dataverse)
- **URL**: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/1KCCX2
- **Contains**: Coordinate-based battlefield locations from militarized interstate disputes. Also see MIDLOC from Correlates of War covering 1816-2010.
- **Data access**: Download from Harvard Dataverse
- **Record count**: Thousands of battle locations
- **Has coordinates**: Yes (lat/lon)
- **License**: Open access (academic)
- **Priority**: MEDIUM-LOW - Historical battlefields with coordinates. Complements ABPP for non-US coverage.

---

## LOWER PRIORITY / WATCH LIST

### 43. DINAA (Digital Index of North American Archaeology)
- **URL**: https://opencontext.org/projects/416a274c-cf88-4471-3e31-93db825e9e4a
- **Contains**: 500,000+ archaeological sites east of the Mississippi River, integrated from state databases.
- **Data access**: Open Context (maps, citations, metadata). **NO coordinates published** - sites assigned to 20km grid cells for protection.
- **Record count**: 500,000+ sites (but no precise locations)
- **Has coordinates**: NO (deliberately obfuscated to 400 sq km cells)
- **License**: Free, no IP restrictions
- **Priority**: LOW - Massive but coordinates are redacted. Could provide approximate/gridded data.

### 44. tDAR (The Digital Archaeological Record)
- **URL**: https://core.tdar.org/
- **Contains**: International digital repository of archaeological records: databases, reports, images, datasets.
- **Data access**: OAI-PMH protocol; first 1000 records downloadable as Excel per search
- **Record count**: Large (repository of many datasets)
- **Has coordinates**: Variable (some datasets have coordinates, but sensitive locations are obfuscated)
- **License**: Open access for metadata
- **Priority**: LOW - Repository rather than single database. Individual datasets may be useful.

### 45. CARD (Canadian Archaeological Radiocarbon Database)
- **URL**: https://www.canadianarchaeology.ca/
- **Contains**: Radiocarbon dates from North American archaeological, paleontological, and geological sites.
- **Data access**: Web interface. Bulk download requires researcher approval. Coordinates restricted at general access level.
- **Record count**: Thousands of dated sites
- **Has coordinates**: Yes, but restricted (precise coordinates only for approved researchers)
- **License**: Restricted access
- **Priority**: LOW - Good North American data but coordinate access requires approval.

### 46. Japan Comprehensive Database of Archaeological Site Reports
- **URL**: https://sitereports.nabunken.go.jp/en
- **Contains**: PDF reports of 34,000+ Japanese archaeological excavation sites. Japan's vast rescue excavation program.
- **Data access**: Full-text search of PDFs. Reports may contain coordinates but not in structured database form.
- **Record count**: 34,000+ site reports
- **Has coordinates**: Indirectly (within report text, not structured)
- **License**: Open access
- **Priority**: LOW - Huge collection but coordinate extraction would require NLP on Japanese PDFs.

### 47. NSW Aboriginal Heritage Information Management System (AHIMS, Australia)
- **URL**: https://www.environment.nsw.gov.au/topics/heritage/search-heritage-databases/aboriginal-heritage-information-management-system
- **Contains**: Aboriginal cultural heritage sites across New South Wales, Australia.
- **Data access**: Search by coordinates, addresses, or shapefiles. Results require formal access approval.
- **Record count**: 100,000+ recorded Aboriginal sites
- **Has coordinates**: Yes (searchable by coordinates)
- **License**: Restricted (precise locations not released without traditional owner permission)
- **Priority**: LOW - Large dataset but access restrictions due to cultural sensitivity.

---

## SUMMARY TABLE

| # | Source | Region | Records | Coords | API/Download | Priority |
|---|--------|--------|---------|--------|--------------|----------|
| 1 | Vici.org | Roman World | 20K | Yes | GeoJSON API | HIGH |
| 2 | AWMC Geodata | Mediterranean | Multi | Yes | GitHub GeoJSON | HIGH |
| 3 | Itiner-e Roman Roads | Roman Empire | 14.8K | Yes | Zenodo GeoJSON | HIGH |
| 4 | NPS NRHP (USA) | North America | 95K+ | Yes | Shapefile/API | HIGH |
| 5 | LIST Inscriptions | Roman World | 512K | Yes | Zenodo GeoJSON | HIGH |
| 6 | p3k14c Radiocarbon | Global | 180K | Partial | tDAR/GitHub | HIGH |
| 7 | ROCEEH/ROAD | Global (Paleo) | 2.3K | Yes | Web + SQL | HIGH |
| 8 | Radiocarbon Paleo EU | Europe/Siberia | 14.3K | Yes | KMZ/Excel | HIGH |
| 9 | PAS Finds | England/Wales | 1.4M | Yes | REST API | HIGH |
| 10 | Canmore Scotland | Scotland | 125K | Yes | Shapefile | HIGH |
| 11 | DARMC (Harvard) | Roman/Medieval | Multi | Yes | Shapefile | MED-HIGH |
| 12 | WHG | Global | 2M+ | Yes | API/Download | MED-HIGH |
| 13 | Mycenaean Atlas | Mediterranean | 5.6K | Yes | CSV | MED-HIGH |
| 14 | Coflein Wales | Wales | 110K | Yes | DataMap Wales | MED-HIGH |
| 15 | NOAA Wrecks | US Waters | 19K | Yes | REST/KML | MED-HIGH |
| 16 | TAY Project Turkey | Turkey | 12K | Yes | Online GIS | MED-HIGH |
| 17 | MAEASaM Africa | Sub-Saharan Africa | 67K+ | Yes | Arches DB | MED-HIGH |
| 18 | LuwianSiteAtlas | W. Anatolia | 483 | Yes | Zenodo | MED-HIGH |
| 19 | MAHSA South Asia | Indus Basin | Growing | Yes | Arches DB | MED-HIGH |
| 20 | DAAHL Holy Land | Levant | 27K | Yes | Web GIS | MED-HIGH |
| 21 | Netherlands RCE | Netherlands | 63K | Yes | SPARQL/API | MEDIUM |
| 22 | France Merimee | France | 320K | Partial | CSV/API | MEDIUM |
| 23 | Egypt CULTNAT | Egypt | 1.2K | Yes | Web GIS | MEDIUM |
| 24 | THANADOS | Austria/Central EU | 563 | Yes | API/JSON | MEDIUM |
| 25 | ArkeoGIS | Europe | 10K+ | Yes | CSV/NAKALA | MEDIUM |
| 26 | Bhuvan India | India | 3.6K | Yes | WMS | MEDIUM |
| 27 | Korean Heritage | Korea | 15K | Yes | API | MEDIUM |
| 28 | ARIADNE Portal | Europe | 4M+ | Partial | LOD/Portal | MEDIUM |
| 29 | Israel IAA | Israel | 4M records | Yes | Web/Reg | MEDIUM |
| 30 | ABPP Battlefields | USA | Hundreds | Yes | ArcGIS | MEDIUM |
| 31 | EBIDAT Castles | Europe | 1000s | Likely | Web DB | MEDIUM |
| 32 | OXREP Quarries | Roman World | Hundreds | Yes | PDF | MEDIUM |

---

## RECOMMENDED IMPLEMENTATION ORDER

### Phase 1: Quick Wins (Easy API/Download, High Value)
1. **Vici.org** - GeoJSON API, 20K Roman sites, trivial to ingest
2. **AWMC Geodata** - GitHub GeoJSON files, just download and parse
3. **Itiner-e** - Zenodo GeoJSON download, Roman roads as line features
4. **NPS NRHP** - Public domain shapefile/GeoJSON, 95K+ US historic sites
5. **LIST Inscriptions** - Zenodo Parquet/GeoJSON, 512K georeferenced inscriptions
6. **Canmore Scotland** - Shapefile download, 125K sites
7. **Coflein Wales** - Download from DataMap Wales, 110K sites

### Phase 2: API Integration (Moderate Effort)
8. **PAS Finds** - REST API, 1.4M records (needs pagination strategy)
9. **NOAA Wrecks** - REST API, 19K wreck sites
10. **World Historical Gazetteer** - API access, 2M+ places
11. **THANADOS** - JSON API, 563 medieval cemeteries
12. **Netherlands RCE** - SPARQL endpoint, 63K monuments

### Phase 3: Data Processing Required
13. **p3k14c Radiocarbon** - Download + filter for non-US/Canada precise coordinates
14. **Radiocarbon Paleo EU** - Parse KMZ/Excel files, 14K Paleolithic sites
15. **ROCEEH/ROAD** - Registration + structured queries
16. **Mycenaean Atlas** - CSV download, 5.6K Bronze Age sites
17. **DARMC** - Shapefile parsing, Roman/medieval datasets

### Phase 4: Regional Gap Filling (More Effort)
18. **TAY Project Turkey** - Scraping/partnership for 12K+ sites
19. **MAEASaM Africa** - Monitor for public database launch
20. **MAHSA South Asia** - Monitor Arches database availability
21. **DAAHL Holy Land** - Web scraping or partnership for 27K sites
22. **Bhuvan India** - WMS/GeoRSS extraction for 3.6K ASI monuments
23. **Korean Heritage** - Explore data.go.kr APIs for cultural properties
24. **Archaeological Map of Egypt** - Web interface exploration

---

## GEOGRAPHIC COVERAGE ANALYSIS

### Well-Covered After Implementation:
- **Mediterranean/Roman World**: Vici.org + AWMC + Itiner-e + LIST + DARMC + Mycenaean Atlas + LuwianSiteAtlas
- **British Isles**: PAS + Canmore + Coflein (+ existing Historic England)
- **North America**: NPS NRHP + NOAA Wrecks + ABPP Battlefields
- **Europe**: Netherlands RCE + France Merimee + EBIDAT + THANADOS + ArkeoGIS
- **Turkey/Near East**: TAY Project + DAAHL + LuwianSiteAtlas

### Partially Covered:
- **South Asia**: MAHSA (Indus Basin) + Bhuvan India (3.6K sites)
- **East Asia**: Korean Heritage + Xinjiang dataset
- **Africa**: MAEASaM (8 countries, 67K+ sites)
- **South America**: Peruvian Amazon sites
- **Pacific/Oceania**: PARD + Pofatu

### Still Weak:
- **China proper** (beyond Xinjiang) - No good open coordinate database found
- **Japan** - Reports exist but no structured coordinate database
- **Southeast Asia** - No single comprehensive open dataset found
- **Central Africa** - Limited coverage even with MAEASaM
- **Pre-Columbian Mesoamerica** - Maya GIS on Data Basin (6K sites, CC BY 3.0) is the best option
