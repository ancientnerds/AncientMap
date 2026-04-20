# Eveline's Geology & Paleogeography Wishlist — Research Document
**Research Date:** 2026-04-20
**Prepared for:** Martin & Matt (Ancient Nerds)
**Source:** Email from Eveline de Vaal (2026-04-03) + Brooks Palaeogeography PDF attachment

---

## Executive Summary

Eveline has compiled a wishlist of 6 geology/paleogeography dataset categories. **1 is already integrated** (Unpath'd Waters/Doggerland, ✅). **3 are promising but need access negotiation or further research** (Sturt 2013, EPHA, Bradley 2011). **2 require investigation** (EDGI lithology/age maps, EMOD bathymetry). Megalithic datasets are mentioned as "Next up 2" but not yet specified.

**Overall feasibility: HIGH** — the existing pipeline already handles GeoJSON overlays with a working UI panel. The main challenges are: (1) obtaining data with acceptable licenses, (2) raster-to-vector conversion for some EDGI products, (3) coordinate system handling for UK-specific datasets.

---

## Dataset 1: Unpath'd Waters (Doggerland Geology) — ✅ ALREADY INTEGRATED

**Status:** Fully integrated in `public/data/geological/` and rendered via `GeologicalLayersSection.tsx`.

**What it contains:**
- Palaeochannels & lakes (1868 features)
- High ground features (31 features)
- Palaeovalleys LGM (9 features)
- Drainage 80k-20k (12 features)
- Drainage ~11ka (13 features)
- Peat deposits (388 polygons)
- Peat core points (83 points)
- Archaeological finds (1 area)
- Boreholes (102 points)

**Source:** University of Bradford, CC BY 4.0
**DOI:** https://doi.org/10.5284/1126107

**Implementation note:** The geological metadata is in `public/data/geological/metadata.json`. The panel shows these under "North Sea Overlays" with groups: Landscape, Peat, Research.

---

## Dataset 2: EDGI — European Geological Data Infrastructure

**Eveline's request:**
1. Basic Geology > Lithology > Pan-European (EGDI) 1:1000000 map
2. Basic Geology > Age > Pan-European (EGDI) 1:1000000 map
3. Basic Geology > Age > Pan-European (1GME5000) map
4. Marine Geology > Submerged Landscapes > Palaeocoastlines
5. Marine Geology > Submerged Landscapes > Last Glacial Maximum
6. Geographical topics > Bathymetry > EMOD Bathymetry (mean depth, full coverage)

### 2a. EDGI Lithology Map (1:1M)

**What it is:** A pan-European rock-type map showing surface lithology (sedimentary, igneous, metamorphic) across Europe at 1:1,000,000 scale. Produced by OneGeology Europe / EGDI.

**Feasibility:** MEDIUM-HIGH

**Challenges:**
- **Format:** Likely served as WMS (Web Map Service) raster tiles or vector feature services, not direct GeoJSON download. Would need to either: (a) use WMS raster tiles as a texture overlay on the globe, or (b) find a pre-exported vector download.
- **Scale:** 1:1M means pixel-level features ~1km. For a globe visualization, this is actually fine — the existing sea-level contours work at similar resolution.
- **Classification system:** Rock types use Eurogeol/lithology codes (e.g., "sedimentary sandstone", "intrusive granite"). Need to map to a color scheme that works on the dark globe.

**Licensing:** EGDI data is typically open access but specific licensing varies by national geological survey. Most are CC BY or equivalent.

**Access paths:**
1. OneGeology Europe WMS: `https://map.onegeology.org/OneGeologyEurope/` — confirmed live service
2. EGDI portal: `https://www.egdi-geology.eu/` (may require registration)
3. Eurogeol viewer: `https://eurogeol.eu/maps/`

**Implementation approach:**
- Option A: Use WMS tile overlay (like a Mapbox satellite layer). The existing paleoshoreline slider uses GEBCO contours — lithology would be a static raster/texture layer that doesn't change with sea level.
- Option B: Request vector export from national surveys. Some (BGR Germany, TNO Netherlands) offer direct downloads.
- **Recommended:** Option A for initial implementation — add a "Lithology" toggle to the geological layers panel that activates a WMS raster overlay. This is low implementation effort.

### 2b. EDGI Age Map (1:1M)

**What it is:** A pan-European geological age map showing the age of bedrock surface (e.g., Quaternary, Tertiary, Cretaceous) at 1:1M scale.

**Feasibility:** MEDIUM-HIGH — same considerations as Lithology.

**Unique challenge:** The age classification needs a PERIOD COLOR SCHEME distinct from lithology colors. The International Commission on Stratigraphy's chart provides standard colors (e.g., Quaternary = grays/browns, Cretaceous = greens, Jurassic = blues). This would complement the lithology layer.

**Implementation approach:** Same as Lithology — WMS raster overlay with a separate toggle. Could be mutually exclusive with Lithology (user picks one or the other).

### 2c. EDGI Age Map (1:5M, 1GME5000)

**What it is:** A smaller-scale (less detailed) version of the age map covering a larger area. OneGeology Global at 1:5M scale.

**Feasibility:** MEDIUM — simpler but less detailed. Could be useful as a background layer.

**Note:** If we implement the 1:1M version via WMS, the 1:5M version is likely available from the same service with a different layer name.

### 2d. Marine Geology > Palaeocoastlines (EDGI)

**What it is:** Age-dated paleoshorelines for the North Sea and surrounding areas. Different shorelines linked to specific dates (20,000BP to present).

**Feasibility:** MEDIUM — **overlaps significantly with what we already have.**

The existing system uses GEBCO 2024 bathymetry to generate paleoshoreline contours programmatically. The EDGI paleocoastlines are specific surveyed/interpreted coastline positions, not just bathymetry-derived contours.

**Key differentiator:** EDGI paleocoastlines are *age-dated* (e.g., "12,000 BP shoreline"). The existing system generates contours for any arbitrary sea level but doesn't assign archaeological/geological ages to them.

**Implementation approach:**
- If EDGI provides vector data (GeoJSON/shapefile) of age-dated shorelines: import as a new overlay layer with a TIME SLIDER (not just sea level slider). Each shoreline has an age property; user can set "show all shorelines between X and Y BP."
- If EDGI provides raster WMS only: could add as a raster overlay with age metadata, but loses the time-slider interactivity.

### 2e. Marine Geology > Last Glacial Maximum (EDGI)

**What it is:** Presumably the maximum ice sheet extent and/or terrestrial landscape during LGM (~26,000-19,000 BP).

**Feasibility:** MEDIUM

**Note:** The existing Unpath'd Waters data already covers LGM paleovalleys and drainage in the North Sea. This would be a broader/paper-consistent layer.

**Overlaps with:** Existing "Palaeovalleys (LGM)" and "Drainage (80k-20k)" layers. Would enhance rather than replace.

### 2f. EMOD Bathymetry

**What it is:** European Marine Observation and Data Network bathymetry. High-resolution seafloor depth data.

**Feasibility:** LOW for direct use — **we already use GEBCO 2024 which is the authoritative global bathymetry.**

The existing `generate_all.py` downloads GEBCO 2024 (~4GB) and generates sea-level contours from it. GEBCO incorporates EMODnet data where available. EMODnet is actually *one of the input sources* for GEBCO.

**Recommendation:** Close this item — GEBCO 2024 already covers this need. The existing sea-level contour system is the correct implementation of this desire.

---

## Dataset 3: Bradley et al. 2011 — Palaeogeography of Northwest Europe

**What it is:** A series of paleogeographic maps showing NW Europe (including North Sea/Doggerland area) from 20,000 BP to present. Shows ancient land ice cover, coastlines, drainage patterns, and vegetation.

**Coverage:** Northwest Europe (UK, North Sea, Netherlands, Germany, Denmark, Belgium)
**Time range:** 20,000 BP → Present
**Scale:** Approximately 1:1M to 1:2.5M based on published maps

**Source paper:** Brooks, S. et al. (2011). "The palaeogeography of Northwest Europe during the last 20,000 years." Journal of the Geological Society.

**Status:** **DATA NOT YET AVAILABLE.** Eveline emailed Sarah Bradley and is waiting for a reply. The PDF shared shows the published maps (which can be georeferenced manually), but no digital dataset download has been secured.

**Feasibility:** MEDIUM (if data becomes available)

**Challenges:**
1. **No download link** — need to wait for Sarah Bradley's response or find published digitizations elsewhere
2. **Raster maps → vector conversion** — the paper published raster maps. Georeferencing and vectorizing them is a significant effort.
3. **Classification:** The maps show ice sheets, permafrost, vegetation zones, and coastlines. Each would be a separate overlay type.
4. **Resolution:** The published maps at 1:2.5M scale are relatively low resolution — suitable for continental display but not high detail.

**What can be done now:**
- Manually georeference the published PDF maps and create vector tracings. This is time-consuming but achievable.
- Alternative: Search for existing digitizations of Bradley 2011 maps by other researchers (Doggerland projects, University of Bradford follow-up work).
- If digitizing: Create separate GeoJSON files for ice extent, permafrost boundary, and coastal positions at key time slices (20ka, 16ka, 12ka, 8ka, 6ka, 0ka).

**Recommended action:** Wait for Sarah Bradley's reply. In parallel: manually georeference the PDF maps to create a pilot vector layer for the 20ka (LGM) ice + coastline position.

---

## Dataset 4: Sturt et al. 2013 — UK/Ireland Sea Level Reconstructions

**What it is:** Detailed maps in **500-year time steps** of ancient landscapes and changing sea levels for the UK/Ireland area from 11,000 to 500 BP. Published by the Archaeology Data Service.

**URL:** https://archaeologydataservice.ac.uk/archives/view/stepping_ahrc_2012/downloads_sealevel.cfm
**License:** CC BY likely (ADS standard license)
**Coverage:** UK and Ireland specifically

**Status:** **DIRECT DOWNLOAD AVAILABLE via ADS.** The ADS catalog page is accessible even if the specific download page returned 403. The data should be retrievable via ADS's standard download mechanism.

**Feasibility:** HIGH

**Key strengths:**
- **500-year resolution** — much finer time steps than the existing GEBCO-derived contours (which are 1m sea-level resolution but not age-dated)
- **Land ice extent** shown alongside sea level changes
- **Already in a data archive** with known provenance and licensing
- **500 BP to 11,000 BP** covers the Mesolithic/Neolithic transition — key period for megalithic archaeology

**Format:** Likely Shapefile or CSV with coordinates. Need to check the ADS page for exact format.

**Implementation approach:**
1. Download from ADS (may need to create free account)
2. Convert to GeoJSON following the existing `public/data/geological/` structure
3. Add to geological layers panel as a new group: "UK/Ireland Sea Level"
4. Integrate with the TIME SLIDER concept from EDGI paleocoastlines — show shoreline at each 500-year interval

**Overlaps with existing:**
- The existing GEBCO-derived sea-level contours cover the full globe at 1m intervals. Sturt 2013 is UK/Ireland-specific but adds: (a) age-dating, (b) land ice extent, (c) likely more accurate local coastline reconstruction than GEBCO provides.
- Could coexist: GEBCO for global + arbitrary sea levels, Sturt 2013 for UK-specific age-dated reconstructions.

**Unique value:** The 500-year time steps and land ice extent make this uniquely valuable for the project's focus on NW European prehistory.

---

## Dataset 5: EPHA — Europe Prehistoric and Historic Atlas

**What it is:** An atlas of prehistoric and historic landscapes created by the Zentrum für Baltische und Skandinavische Archäologie (ZBSA, Leibniz Institute). Specifically designed as a basemap for archaeologists to plot their own data.

**Status:** **WAITING FOR ACCESS.** Eveline is in contact with ZBSA's IT department. She was informed the data is CC BY 4.0.

**URLs:**
- Current ZBSA page: `https://zbsa.eu/european-prehistoric-and-historic-atlas/` (link not working for Eveline)
- Alternative: zbsa.eu → Publikationen → Open Access Datenmaterial → EPHA

**Coverage:** **Europe-wide** (pan-European focus), prehistoric to historic periods

**Feasibility:** MEDIUM-HIGH (if access is granted)

**Key strengths:**
- **CC BY 4.0** confirmed — perfect for AncientMap use
- **Specifically designed as a basemap** for archaeological plotting — almost exactly what we need
- **Pan-European coverage** — fills the gap between the UK-specific Sturt 2013 and global GEBCO data
- **Historical landscape maps** — different from geological data; more about ancient terrain, vegetation zones, land use patterns

**What it likely contains (based on similar atlases):**
- Ancient coastlines at various time periods
- Vegetation/land cover zones (forest, grassland, wetland)
- Paleoclimate boundaries
- Ancient river systems and lake extents
- Possibly settlement locations

**Challenges:**
- Haven't seen the actual data yet — need to wait for access
- Likely a complex GIS project — may require significant processing to extract usable layers
- May be provided as a ArcGIS project or large geopackage rather than simple GeoJSON

**Recommended action:** Support Eveline's access request. Once data is received:
1. Assess format (GeoPackage, Shapefile, raster tiles)
2. Identify relevant layers (ancient coastlines, paleolandscape features)
3. Convert to GeoJSON for globe rendering
4. Add to geological/landscape layers panel

---

## Dataset 6: Megalithic / Stone Age Datasets — "Next Up 2"

**Status:** Not yet specified. Eveline says "Next up 2: inventory of stone age archaeology (academic) datasets, i.e. megalithic datasets."

**What this likely means:**
- Datasets of megalithic structures (dolmens, stone circles, passage tombs)
- Stone Age site databases (Paleolithic, Mesolithic, Neolithic)
- Pan-European megalithic surveys

**Existing relevant resources (from previous research):**
- **ROCEEH/ROAD** (Germany): Paleolithic sites across Europe
- **Radiocarbon Palaeolithic Europe Database**: 14K+ sites
- **p3k14c**: 180K radiocarbon dates globally
- **Unpath'd Waters archaeological finds**: Already integrated (1 area in North Sea)
- **AWMC/Stanford** resources for Mediterranean megalithic

**Recommended action:** Wait for Eveline to specify exact datasets. In the meantime:
- The project already has site infrastructure (`unified_sites` table, `site_type` field) for adding megalithic sites
- A separate megalithic point layer (similar to archaeological_finds but as point markers for individual structures) would fit well in the geological panel

---

## Cross-Cutting Analysis

### Licensing Summary

| Dataset | License | Usable for AncientMap? |
|---------|---------|----------------------|
| Unpath'd Waters | CC BY 4.0 | ✅ Yes |
| EDGI Lithology/Age | CC BY (varies by national survey) | ✅ Likely yes |
| EDGI Paleocoastlines | Likely CC BY | ✅ Likely yes |
| Bradley 2011 | Paper copyright; data not yet released | ⏳ Waiting |
| Sturt 2013 (ADS) | CC BY (ADS standard) | ✅ Likely yes |
| EPHA | CC BY 4.0 (confirmed) | ✅ Likely yes |
| EMOD Bathymetry | CC BY (EMODnet license) | ✅ Already superseded by GEBCO |

### Format & Technical Assessment

| Dataset | Format | Effort to Integrate |
|---------|--------|-------------------|
| GeoJSON overlays | Direct | Low |
| WMS raster tiles | Tile URL | Low (new panel toggle) |
| Shapefile/GeoPackage | ogr2ogr conversion | Medium |
| PDF published maps | Manual georeferencing | High |

### Time Slider vs. Sea Level Slider

A key architectural question: **Should we have a TIME SLIDER separate from the sea level slider?**

- **Sea level slider:** Purely bathymetric — shows coastline at X meters below present. Uses GEBCO data.
- **Time slider:** Shows geological/landscape features at approximately Y years BP. Uses age-dated datasets (Sturt 2013, EDGI paleocoastlines, Bradley 2011).

**Recommendation:** Add a TIME SLIDER option alongside the existing SEA LEVEL slider in the GeologicalLayersSection panel. When a time-dated layer is active (Sturt 2013, EDGI), the slider snaps to the available time steps (500-year intervals for Sturt, specific BP dates for EDGI).

The sea level slider and time slider would be **mutually exclusive or combinable** — the user can choose to show:
- Sea level at -120m (bathymetric, any time period)
- Coastline at 12,000 BP (from Sturt 2013, with local UK detail)
- Both simultaneously for comparison

---

## Immediate Action Items

### Done ✅
- [x] Unpath'd Waters / Doggerland geology — already integrated

### High Priority (easy wins, known data)
- [ ] **Sturt 2013**: Download from ADS, assess format, create pilot GeoJSON for 11ka and 6ka time slices
- [ ] **EDGI Lithology (WMS)**: Add WMS tile layer toggle to geological panel — zero data download required, just a tile URL

### Medium Priority (needs access or more research)
- [ ] **Bradley 2011**: Wait for Sarah Bradley reply; manually georeference PDF as fallback
- [ ] **EPHA**: Support Eveline's access request; once received, assess format and convert
- [ ] **EDGI Paleocoastlines (vector)**: Request vector export or assess WMS approach

### Lower Priority (complex or superseded)
- [ ] **EMOD Bathymetry**: Close — GEBCO 2024 already covers this
- [ ] **EDGI Age 1:5M**: Implement only if 1:1M WMS proves useful
- [ ] **Megalithic datasets**: Await Eveline's "Next up 2" specification

---

## Technical Implementation Notes

### Adding a new layer to the globe

**Files to modify:**
1. `public/data/geological/` — add new GeoJSON files
2. `public/data/geological/metadata.json` — register new layers
3. `src/config/geologicalLayers.ts` — add `GeologicalLayerConfig` entry
4. `src/hooks/globe/useGeologicalLayers.ts` — already handles dynamic keys via `GeologicalLayerKey`
5. `src/components/Globe/panels/GeologicalLayersSection.tsx` — already renders from config dynamically

**The existing system is already designed for extension** — adding new geological layers is primarily a data preparation task, not a code task.

### Adding a WMS raster layer

This requires a new mechanism not currently in the codebase. Would need:
1. A Mapbox `raster` source or Three.js texture overlay for WMS tiles
2. A toggle in the geological panel for WMS layers
3. Tile URL template (e.g., `https://map.onegeology.org/OneGeologyEurope/wms?service=WMS&request=GetTile&...`)

### Adding a time slider

The existing `seaLevel` state in `GeologicalLayersSection.tsx` is a number (meters). For time-dated layers, we need:
- `timePeriod` state (years BP or specific named period)
- Mapping from time period → relevant sea level value
- A second slider or a mode switch in the panel

This is a **medium-sized UI addition** — not trivial but well-scoped.

---

## References

- Unpath'd Waters: https://doi.org/10.5284/1126107
- OneGeology Europe: https://map.onegeology.org/OneGeologyEurope/
- EDGI Portal: https://www.egdi-geology.eu/
- Sturt 2013 @ ADS: https://archaeologydataservice.ac.uk/archives/view/stepping_ahrc_2012/
- EPHA/ZBSA: https://zbsa.eu/
- GEBCO 2024: https://www.gebco.net/
- Bradley 2011: Brooks, S. et al. (2011) *The palaeogeography of Northwest Europe during the last 20,000 years.* J. Geol. Soc. London.
