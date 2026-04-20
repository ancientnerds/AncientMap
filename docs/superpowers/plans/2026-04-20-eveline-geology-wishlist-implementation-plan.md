# Eveline's Geology Wishlist — Implementation Plan
**Plan Date:** 2026-04-20
**Based on:** Research document `2026-04-20-eveline-geology-wishlist-research.md`

---

## Overview

Implement geological and paleogeographic data layers from Eveline's wishlist. The existing globe infrastructure already supports GeoJSON overlays via `GeologicalLayersSection.tsx` — extending it is primarily a data preparation task. Three categories of work: (A) Sturt 2013 data prep + integration, (B) EDGI WMS layer, (C) time slider UI enhancement.

---

## Phase 1: Sturt 2013 — UK/Ireland Sea Level Reconstruction [HIGH PRIORITY]

### Step 1.1: Download data from ADS
- [ ] Navigate to: https://archaeologydataservice.ac.uk/archives/view/stepping_ahrc_2012/downloads_sealevel.cfm
- [ ] Create free ADS account if needed (standard procedure)
- [ ] Download all available files (likely Shapefile or CSV)
- [ ] Record exact citation and license for metadata.json
- [ ] Place raw files in `pipeline/raw/sturt_2013/`

### Step 1.2: Assess format and content
- [ ] Identify all time-step files (should be 22 time steps from 11,000 to 500 BP at 500-year intervals)
- [ ] Identify what each file contains (shoreline polygons? ice extent? both?)
- [ ] Check coordinate reference system (likely ETRS89 / British National Grid — needs transformation to WGS84)
- [ ] Use `ogrinfo` or GeoPandas to inspect attribute schemas

### Step 1.3: Convert to GeoJSON
- [ ] Write a conversion script in `pipeline/converters/sturt_2013_converter.py`
  - Use `ogr2ogr` or GeoPandas to reproject to WGS84 (EPSG:4326)
  - Export each time step as a separate GeoJSON file
  - File naming: `sturt_2013_{year}bp.geojson` (e.g., `sturt_2013_11000bp.geojson`)
  - Include properties: `{"year_bp": 11000, "source": "Sturt et al. 2013", "license": "CC BY 4.0"}`
- [ ] Run conversion for all 22 time steps
- [ ] Validate each file: open in QGIS or check with `python -c "import geojson; geojson.load(open('file'))"`

### Step 1.4: Register in geological metadata
- [ ] Create `public/data/geological/sturt_2013_metadata.json` with per-time-step file references
- [ ] Update `public/data/geological/metadata.json` to include Sturt 2013 as a new data source

### Step 1.5: Add to globe config
- [ ] In `src/config/geologicalLayers.ts`, add a new group: `Sturt2013TimeStep`
- [ ] Add a single layer key `sturt2013TimeSlice` that handles the active time slice
- [ ] Register in `GEOLOGICAL_GROUPS` under a new group label: "UK Sea Level (Sturt 2013)"

### Step 1.6: Panel UI — time step selector
- [ ] In `GeologicalLayersSection.tsx`, add a time-step selector below the existing layer toggles
- [ ] Dropdown or button strip showing: 11000, 10500, 10000, ... 500 BP
- [ ] On selection, load the corresponding GeoJSON file
- [ ] Show the selected time slice on the globe (shoreline polygon + ice extent)
- [ ] Add description text: "500-year resolution sea level reconstructions for UK/Ireland (Sturt et al. 2013, CC BY 4.0)"

### Step 1.7: Combine with sea level slider
- [ ] Add a mode toggle: "Use GEBCO bathymetric contours" vs "Use Sturt 2013 age-dated reconstructions"
- [ ] When Sturt mode is active, disable or dim the sea level slider
- [ ] Show both layers simultaneously if desired (Sturt shoreline + GEBCO for surrounding areas)

---

## Phase 2: EDGI WMS Lithology Layer [MEDIUM PRIORITY]

### Step 2.1: Identify WMS endpoint
- [ ] Visit https://map.onegeology.org/OneGeologyEurope/
- [ ] Find the WMS endpoint URL for the Lithology (OneGeology Europe) layer
- [ ] Test with `GetCapabilities` request to confirm the service URL
- [ ] Document: WMS version, available layers, tile size, projection

### Step 2.2: Add WMS raster source to Mapbox globe
- [ ] Check current Mapbox configuration in `src/services/MapboxGlobeService.ts`
- [ ] If using Mapbox: Add a new `RasterTileSource` for the EDGI WMS endpoint
- [ ] If using Three.js: Create a texture loader for WMS tiles (or XYZ proxy)
- [ ] Confirm CORS support from the WMS server

### Step 2.3: UI toggle for lithology layer
- [ ] Add toggle in `GeologicalLayersSection.tsx` under a new group: "Pan-European Geology (EDGI)"
- [ ] Toggle should: activate the WMS raster overlay with lithology colors
- [ ] Add opacity slider (0-100%) since the raster may obscure terrain
- [ ] Add description: "Pan-European surface lithology from OneGeology Europe (EDGI), scale 1:1M"

### Step 2.4: EDGI Age map (optional extension)
- [ ] Same steps as 2.1-2.3 with the Age layer endpoint
- [ ] Option: make Lithology and Age mutually exclusive toggles (only one at a time)

---

## Phase 3: EDGI Age-Dated Paleocoastlines [MEDIUM PRIORITY]

### Step 3.1: Investigate EDGI marine geology layers
- [ ] Query OneGeology Europe WMS for layers matching "paleocoastline" or "submerged landscapes"
- [ ] Check if the WMS provides age-dated features or just static polygons
- [ ] If vector data exists: request as GeoJSON or use `ogr2ogr` to download via WFS
- [ ] If only WMS raster: assess whether age labels can be derived from layer metadata

### Step 3.2: If vector data is available
- [ ] Download paleocoastline features as GeoJSON
- [ ] Each feature should have an `age_bp` or `age_range` property
- [ ] Integrate as a new layer in the geological panel with time-filtering UI
- [ ] Same time-slider approach as Sturt 2013

### Step 3.3: If only WMS raster
- [ ] Consider adding as a static raster overlay with a description note
- [ ] Alternatively: skip this and focus on Sturt 2013 which is higher resolution and already vector

---

## Phase 4: EPHA — European Prehistoric and Historic Atlas [MEDIUM PRIORITY, BLOCKED ON ACCESS]

### Step 4.1: Await Eveline's access grant from ZBSA
- [ ] This step is blocked until ZBSA IT department grants access
- [ ] Once access is granted, download the dataset
- [ ] Assess format: likely ArcGIS Geopackage or complex shapefile collection

### Step 4.2: Format assessment
- [ ] Identify which layers are useful for the globe:
  - Ancient coastline positions
  - Paleolandscape features (rivers, lakes, wetlands)
  - Vegetation/land cover zones
  - Settlement/burial site locations
- [ ] Determine which layers are raster vs vector
- [ ] Check coordinate reference system

### Step 4.3: Convert and integrate
- [ ] Write converter in `pipeline/converters/eph_a_converter.py`
- [ ] Export relevant layers as GeoJSON
- [ ] Register in `public/data/geological/metadata.json`
- [ ] Add to geological panel with appropriate grouping

---

## Phase 5: Bradley 2011 — Await Data Availability [LOW-MEDIUM PRIORITY, BLOCKED]

### Step 5.1: Wait for Sarah Bradley's reply
- [ ] If digital data is provided: follow same conversion process as Sturt 2013
- [ ] If data is NOT provided: manual georeferencing fallback (see 5.2)

### Step 5.2: Manual georeferencing fallback
- [ ] Use QGIS to georeference the PDF published maps
- [ ] Digitize key features: LGM coastline, ice sheet boundary, permafrost limit
- [ ] Focus on 4-6 key time slices: 20ka, 16ka, 12ka, 8ka, 6ka, 0ka
- [ ] Export as GeoJSON and integrate

---

## Phase 6: EMOD Bathymetry [CLOSE — ALREADY IMPLEMENTED]

### Step 6.1: Confirm closure
- [ ] Note in project documentation that EMOD Bathymetry is already covered by GEBCO 2024
- [ ] GEBCO incorporates EMODnet data sources and is the authoritative global product
- [ ] Close this item with a documentation note

---

## Technical Architecture Decisions

### Layer Classification System

The geological panel should support **three layer types**:

| Layer Type | Rendering | Examples |
|-----------|-----------|---------|
| **Vector overlay** | GeoJSON features drawn on globe surface | Palaeochannels, Sturt 2013 shorelines, boreholes |
| **WMS raster** | Tile texture mapped to globe | EDGI Lithology, EDGI Age |
| **Contour lines** | Line geometry from elevation data | Existing GEBCO sea-level contours |

The UI should visually distinguish these three types (different icons or section headers).

### Time vs. Sea Level

Two separate controls:
- **Sea Level Slider:** Changes the GEBCO contour level (any integer from -150m to +50m). Active when using bathymetric contours.
- **Time Step Selector:** Snaps to discrete time periods from age-dated datasets (Sturt 2013: 500-year intervals; EDGI: specific BP dates). Active when using historical reconstructions.

These should be in separate UI sections with a clear mode indicator.

### Color Schemes for New Layers

**EDGI Lithology colors** — should follow geological convention:
- Sedimentary rocks: warm earth tones (browns, tan)
- Igneous rocks: cool grays/reds
- Metamorphic rocks: varied (often purple/green shades)
- Quaternary deposits: yellows/light browns

**Sturt 2013 ice extent** —冰川 blue-white gradient, distinct from existing blue water/green land

**Bradley 2011 ice** — same冰川 convention

---

## File Changes Summary

### New Files to Create
```
public/data/geological/sturt_2013_11000bp.geojson   (×22 time slices)
public/data/geological/sturt_2013_metadata.json
public/data/geological/eph_a_*.geojson              (if/when EPHA arrives)
pipeline/converters/sturt_2013_converter.py
pipeline/converters/eph_a_converter.py              (if/when EPHA arrives)
docs/geology/sturt_2013_citation.txt
```

### Files to Modify
```
public/data/geological/metadata.json                — add Sturt 2013, EPHA sources
src/config/geologicalLayers.ts                     — add new layer keys
src/components/Globe/panels/GeologicalLayersSection.tsx  — time step UI
src/hooks/globe/useGeologicalLayers.ts             — likely no change needed
src/services/MapboxGlobeService.ts                  — WMS raster source (EDGI)
```

### No Code Changes Needed For
- EMOD Bathymetry (already implemented via GEBCO)
- Bradley 2011 (blocked on data availability; no partial implementation worthwhile)

---

## Milestones

| Milestone | Contents | Dependencies |
|-----------|----------|-------------|
| M1: Sturt 2013 data prep | 22 GeoJSON time slices ready in `public/data/geological/` | ADS download |
| M2: Sturt 2013 UI | Time-step selector in panel, shoreline rendering on globe | M1 |
| M3: EDGI WMS Lithology | Raster overlay toggle in panel | OneGeology WMS endpoint |
| M4: EPHA integration | Converted GeoJSON layers, panel integration | ZBSA access grant |
| M5: Bradley 2011 | Vector layers for 4+ time slices | Sarah Bradley data or manual georeference |

---

## Effort Estimates

| Task | Estimated Effort | Notes |
|------|----------------|-------|
| Sturt 2013 data prep + integration | 4-6 hours | 22 files; straightforward conversion |
| Sturt 2013 UI (time slider) | 2-3 hours | New UI component in existing panel |
| EDGI WMS Lithology | 3-4 hours | New rendering mechanism for rasters |
| EDGI Age-dated paleocoastlines | 2-4 hours | Depends on WMS/WFS data availability |
| EPHA | 4-8 hours once data arrives | Format could be complex |
| Bradley 2011 manual georeference | 6-10 hours | 4-6 maps to georeference and digitize |

---

## Risks & Open Questions

1. **Sturt 2013 ADS access:** May require registration or institutional login. Have fallback plan to request data via academic channels.

2. **EDGI WMS performance:** WMS raster tiles for all of Europe at 1:1M could be large. May need to limit to visible globe area or use a tile cache.

3. **Coordinate systems:** UK data from ADS may use ETRS89/British National Grid. Must reproject to WGS84 before GeoJSON export.

4. **Time slider UX complexity:** Adding time-based filtering to an already complex panel increases cognitive load. Need to design the mode switching clearly.

5. **EPHA data format:** Could be a large ArcGIS file geodatabase requiring Esri tools to read. May need to request a simpler format (GeoJSON) from ZBSA.

6. **Bradley 2011 ice sheet representation:** The paper's ice sheet maps are regional (NW Europe). Need to decide whether to show only the UK area or attempt a full coverage reconstruction.
