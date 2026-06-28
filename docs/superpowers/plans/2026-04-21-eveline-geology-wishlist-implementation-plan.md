# Plan: Eveline's Geology Wishlist — Clean Implementation

## Context

Eveline de Vaal provided a geology/paleogeography data wishlist. One dataset (Unpath'd Waters / Doggerland) is already integrated. Four datasets need integration (Sturt 2013, EDGI WMS Lithology, EPHA, Bradley 2011). The existing pipeline and frontend were built for static GeoJSON overlays — adding time-series data (Sturt 2013 has 22 time slices) requires extending the layer config to support temporal layers cleanly.

Goals: (1) integrate Sturt 2013 fully, (2) add EDGI WMS lithology, (3) build a unified extensible layer registry so future datasets (EPHA, Bradley) slot in without spaghetti code, (4) do not break any existing functionality.

---

## Critical Files

| File | Role |
|------|------|
| `ancient-nerds-map/src/config/geologicalLayers.ts` | Single source of truth for all geological layer definitions |
| `ancient-nerds-map/src/hooks/globe/useGeologicalLayers.ts` | Visibility state + time-step state |
| `ancient-nerds-map/src/components/Globe/panels/GeologicalLayersSection.tsx` | Renders the geological panel UI |
| `ancient-nerds-map/src/components/Globe/rendering/geologicalLayerLoader.ts` | Loads GeoJSON and renders as Three.js Line geometry |
| `ancient-nerds-map/src/components/Globe.tsx` | Wires geological layer visibility → loader; syncs to Mapbox |
| `pipeline/geological_layers/process_ads_north_sea.py` | **Reference pattern** for converter scripts |
| `public/data/geological/metadata.json` | Frontend metadata (source, layers, feature counts) |
| `public/data/geological/*.geojson` | Static GeoJSON overlay files |

---

## Architecture: Unified Layer Registry

Currently `GEOLOGICAL_LAYER_CONFIG` mixes layer definitions with style/color info. The new design separates:

- **`LAYER_SOURCES`**: data source registry (name, license, citation, DOI) — the authoritative record of where data comes from
- **`LAYER_DEFINITIONS`**: data layer definitions (source ID, files, temporal info, group, description) — what the pipeline produces
- **`LAYER_STYLES`**: visual config (color, radius) — what the UI needs to render

This separation means: adding a new source only requires adding its entries to `LAYER_SOURCES`, updating `metadata.json`, and registering layer keys. Style changes never touch data config. Each dataset maps to one entry in `LAYER_SOURCES`, and multiple layer keys can belong to the same source.

```typescript
// NEW: Source registry
export interface LayerSource {
  sourceId: string          // 'unpathd_waters', 'sturt_2013', 'eph_a', 'edgi'
  sourceName: string        // Display name
  license: string
  citation: string
  doi?: string
}

// NEW: Time-step descriptor (for temporal layers)
export interface TimeStep {
  file: string              // filename relative to /data/geological/ (without .geojson)
  year: number             // years BP
  label: string             // '11,000 BP' or 'LGM (~20ka)'
}

// UPDATED: GeologicalLayerConfig
export interface GeologicalLayerConfig {
  sourceId: string
  file: string              // base GeoJSON filename (without .geojson) or first time-step file
  timeSteps?: TimeStep[]    // if present, this is a temporal layer group
  label: string
  description: string
  group: GeologicalLayerGroup | 'SeaLevel' | 'PanEuropean'
  color: number
  radius: number
}
```

`getGeologicalLayerUrl(key, timeStepIndex?)` returns the appropriate URL:
- Static layer → `/data/geological/{file}.geojson`
- Temporal layer → `/data/geological/{timeSteps[timeStepIndex].file}.geojson`

---

## Phase 1: Frontend — Time-Series Layer Support

### 1.1 `src/config/geologicalLayers.ts`

**Changes:**
1. Add `LayerSource` interface and `LAYER_SOURCES: Record<string, LayerSource>` registry
2. Add `TimeStep` interface
3. Update `GeologicalLayerConfig` to include `sourceId: string` and optional `timeSteps: TimeStep[]`
4. `getGeologicalLayerUrl(key, timeStepIndex?)` — when `timeSteps` is set and `timeStepIndex !== undefined`, return the time-step file URL; otherwise fall back to `file`
5. Add `sourceId: 'unpathd_waters'` to existing 9 layers
6. No changes to `GeologicalLayerKey`, `GeologicalLayerVisibility`, or `GEOLOGICAL_GROUPS` types — those derive from the config and work as-is

### 1.2 `src/hooks/globe/useGeologicalLayers.ts`

**Changes:**
1. Add `currentTimeStep: Record<string, number>` — maps layer key → active time step index, default `0`
2. Add `setCurrentTimeStep(key: GeologicalLayerKey, index: number) => void` callback
3. No changes to `hasVisibleGeologicalLayers`

### 1.3 `src/components/Globe/rendering/geologicalLayerLoader.ts`

**Changes:**
1. Update `loadGeologicalLayer(key, ctx, timeStepIndex?: number)` to accept optional time step index
2. When `timeStepIndex !== undefined`, call `getGeologicalLayerUrl(key, timeStepIndex)` instead of `getGeologicalLayerUrl(key)`
3. All other geometry-processing code is unchanged — already geometry-type-generic

### 1.4 `src/components/Globe.tsx`

**Changes:**
1. `useEffect` watching `geologicalLayers` (line ~2091) also watches `currentTimeStep`:
   ```typescript
   }, [geologicalLayers, currentTimeStep, buildGeologicalCtx])
   ```
2. On layer load: `loadGeologicalLayerImpl(key, ctx, currentTimeStep[key])` — pass the active time step index
3. Mapbox sync effect (line ~2304): already reads `geologicalGeoJSONRef` by key, works unchanged since the cache key is URL-based
4. Pass `currentTimeStep` and `setCurrentTimeStep` to `GeologicalLayersSection`

### 1.5 `src/components/Globe/panels/GeologicalLayersSection.tsx`

**Changes:**
1. Accept `currentTimeStep: Record<string, number>` and `onTimeStepChange` from props
2. In the layer toggle rendering, detect temporal layers:
   ```typescript
   const cfg = GEOLOGICAL_LAYER_CONFIG[layerKey]
   const hasTimeSteps = cfg.timeSteps != null && cfg.timeSteps.length > 0
   ```
3. When `hasTimeSteps && geologicalLayers[layerKey]`:
   - Render a horizontal button strip inside the expanded group showing each time step year
   - Highlight the active time step button
   - On click: call `onTimeStepChange(layerKey, index)`
4. When `!hasTimeSteps`: existing checkbox behavior unchanged
5. No structural rewrites — conditional rendering inside the existing expanded-group loop

### 1.6 `public/data/geological/metadata.json`

**Changes:**
1. Add `sources` array with both `unpathd_waters` and `sturt_2013` entries
2. Add Sturt 2013 layer entry:
   ```json
   "sturt_2013": {
     "sourceId": "sturt_2013",
     "file": "sturt_2013_11000bp",
     "timeSteps": [
       { "file": "sturt_2013_11000bp", "year": 11000, "label": "11,000 BP" },
       { "file": "sturt_2013_10500bp", "year": 10500, "label": "10,500 BP" },
       ...
       { "file": "sturt_2013_500bp",   "year": 500,   "label": "500 BP" }
     ],
     "label": "UK Sea Level (Sturt 2013)",
     "group": "SeaLevel",
     "description": "500-year resolution sea level reconstructions for UK and Ireland (Sturt et al. 2013)"
   }
   ```

---

## Phase 2: Pipeline — Sturt 2013 Converter

**Pattern reference:** `pipeline/geological_layers/process_ads_north_sea.py` — same download → geopandas → GeoJSON → metadata pattern, adapted for Sturt 2013's multi-time-step structure.

**New file:** `pipeline/geological_layers/process_sturt_2013.py`

```python
"""
Download and convert Sturt et al. 2013 sea level reconstructions (ADS).
Source: Archaeology Data Service, CC BY
URL: https://archaeologydataservice.ac.uk/archives/view/stepping_ahrc_2012/

Time steps: 22 maps from 11,000 to 500 BP at 500-year intervals.
Each time step = one GeoJSON output file.
"""

BASE_URL = "https://archaeologydataservice.ac.uk/catalogue/adsdata/..."

LAYERS = {
    "sturt_2013_coastline": {
        "zip": "...",                          # actual zipname TBD after ADS inspection
        "output_prefix": "sturt_2013",
        "time_steps": [
            {"year": 11000, "file": "sturt_2013_11000bp"},
            {"year": 10500, "file": "sturt_2013_10500bp"},
            # ... 20 more at 500-year intervals
            {"year": 500,   "file": "sturt_2013_500bp"},
        ],
        "group": "SeaLevel",
        "color": "#3B82F6",
        "label": "UK Coastline Reconstructions",
        "description": "Ancient coastline positions at 500-year intervals (Sturt et al. 2013)",
    },
    "sturt_2013_ice": {
        "zip": "...",                          # separate ice extent shapefile if available
        "output_prefix": "sturt_2013_ice",
        "time_steps": [...],                   # same time steps, ice extent polygons
        "group": "SeaLevel",
        "color": "#BFDBFE",
        "label": "Land Ice Extent",
        "description": "Estimated land ice coverage at each time step",
    },
}
```

**Converter steps:**
1. Download zipped shapefile from ADS
2. Inspect attribute table to find the age/year column — use `geopandas` to examine
3. For each `time_step` in `LAYERS`:
   - Filter features by matching age column
   - Reproject to EPSG:4326 if needed
   - Simplify geometry (tolerance 0.001°)
   - Strip all properties, write compact GeoJSON
4. Generate `metadata.json` with all time steps and source citation
5. Run: `python -m pipeline.geological_layers.process_sturt_2013`

**After running:**
- 22+ new GeoJSON files in `public/data/geological/`
- `public/data/geological/metadata.json` updated with Sturt 2013 source

**Register in `geologicalLayers.ts`:**
```typescript
sturt2013Coastline: {
  sourceId: 'sturt_2013',
  file: 'sturt_2013_11000bp',
  timeSteps: [
    { file: 'sturt_2013_11000bp', year: 11000, label: '11,000 BP' },
    { file: 'sturt_2013_10500bp', year: 10500, label: '10,500 BP' },
    // ...
    { file: 'sturt_2013_500bp',   year: 500,   label: '500 BP' },
  ],
  label: 'UK Sea Level (Sturt 2013)',
  description: '500-year resolution sea level reconstructions for UK and Ireland',
  group: 'SeaLevel',
  color: 0x3B82F6,
  radius: 1.002,
},
sturt2013Ice: {
  sourceId: 'sturt_2013',
  file: 'sturt_2013_ice_11000bp',
  timeSteps: [...same time steps...],
  label: 'Land Ice Extent',
  description: 'Land ice coverage at each time step',
  group: 'SeaLevel',
  color: 0xBFDBFE,
  radius: 1.002,
},
```

---

## Phase 3: EDGI WMS Lithology

**Approach:** Static raster fallback (simpler than live WMS). Export a single low-resolution version of the OneGeology Europe lithology map as a static GeoTIFF/texture.

**Why not live WMS:** The codebase has no WMS infrastructure. Building live WMS tile fetching + Mapbox raster source + coordinate reprojection is a significant new subsystem. The static approach gives 90% of the value at 10% of the complexity.

### 3.1 Pre-export the lithology texture
1. Use QGIS or Python (`rasterio`) to download/clip the OneGeology Europe WMS at low resolution (~1km per pixel)
2. Export as GeoTIFF or PNG with world file for georeferencing
3. Place in `public/data/geological/edgi_lithology.tif`

### 3.2 Add to frontend config
**New file:** `src/config/lithologyTexture.ts`
```typescript
export const LITHOLOGY_TEXTURE_CONFIG = {
  sourceId: 'edgi',
  file: 'edgi_lithology',
  label: 'Pan-European Lithology (EDGI)',
  description: 'Surface rock type from OneGeology Europe 1:1M',
  group: 'PanEuropean',
  // Raster layers use opacity, not a single color
  defaultOpacity: 0.7,
  baseUrl: '/data/geological/',
}
```

**`geologicalLayers.ts`:** Add EDGI entry with `layerType: 'raster'`:
```typescript
edgiLithology: {
  sourceId: 'edgi',
  layerType: 'raster',
  file: 'edgi_lithology',
  label: 'Pan-European Lithology (EDGI)',
  description: 'Surface rock type from OneGeology Europe 1:1M',
  group: 'PanEuropean',
  color: 0x888888,
  radius: 1.001,
  defaultOpacity: 0.7,
},
```

### 3.3 Rendering
The existing `geologicalLayerLoader.ts` handles only `THREE.Line` vector rendering. Raster texture rendering already exists in the globe's basemap system. Adding lithology texture requires:
1. In `sceneInit.ts` or a new `lithologyTextureLoader.ts`: create a `THREE.Texture` from the image file, apply as a second layer on the globe sphere with `MeshBasicMaterial` or custom shader
2. Toggle opacity via a uniform in the shader
3. In `GeologicalLayersSection.tsx`: show an opacity slider instead of a color indicator for raster layers

**Simplified implementation path:** If the texture approach is too complex, an even simpler fallback: add the lithology as a Mapbox `raster` source with the static file URL (no WMS involved). Mapbox GL JS handles the texture correctly.

### 3.4 Panel UI for raster layers
In `GeologicalLayersSection.tsx`, when `layerType === 'raster'`:
- Render a toggle without color indicator
- Show an opacity slider (0.0–1.0) below the toggle
- Show a brief description that it's a raster texture overlay

---

## Phase 4: EPHA — Once Access Is Granted

**Blocked** on ZBSA IT department granting access.

When data arrives:
1. Inspect format (likely ArcGIS Geopackage or shapefile collection)
2. Write `pipeline/geological_layers/process_eph_a.py` following the `process_ads_north_sea.py` pattern
3. Identify useful layers: ancient coastlines, paleolandscape features (rivers, lakes, wetlands)
4. Export as GeoJSON, update `LAYER_SOURCES` and `GEOLOGICAL_LAYER_CONFIG` in `geologicalLayers.ts`
5. Update `public/data/geological/metadata.json`
6. No frontend code changes beyond registering the new layer keys — the temporal layer mechanism from Phase 1 handles any time-series layers EPHA might have

---

## Phase 5: Bradley 2011 — If/When Data Is Available

**Blocked** on Sarah Bradley's reply.

If digital data is provided: write `pipeline/geological_layers/process_bradley_2011.py` following the same pattern.
If no data arrives: manual QGIS georeferencing of the PDF published maps (lowest priority, do only if other items are complete).

---

## Files Summary

### New Files
| File | Purpose |
|------|---------|
| `pipeline/geological_layers/process_sturt_2013.py` | Sturt 2013 ADS shapefile → 22 GeoJSON time slice files |
| `public/data/geological/sturt_2013_11000bp.geojson` | ×22 time slice GeoJSONs (sturt_2013_500bp through sturt_2013_11000bp) |
| `public/data/geological/edgi_lithology.*` | Static lithology texture (GeoTIFF/PNG + world file) |
| `src/config/lithologyTexture.ts` | Lithology raster layer configuration |

### Modified Files
| File | Changes |
|------|---------|
| `src/config/geologicalLayers.ts` | `LayerSource`, `TimeStep` interfaces; `LAYER_SOURCES` registry; `sourceId` on all configs; optional `timeSteps`, `layerType: 'vector'|'raster'`, `defaultOpacity` fields; `getGeologicalLayerUrl(key, timeStepIndex?)` updated |
| `src/hooks/globe/useGeologicalLayers.ts` | `currentTimeStep` state; `setCurrentTimeStep` callback |
| `src/components/Globe/rendering/geologicalLayerLoader.ts` | `loadGeologicalLayer(key, ctx, timeStepIndex?)` accepts optional time step index |
| `src/components/Globe.tsx` | `useEffect` watches `currentTimeStep`; passes new props to panel |
| `src/components/Globe/panels/GeologicalLayersSection.tsx` | Time-step button strip for temporal layers; opacity slider for raster layers |
| `public/data/geological/metadata.json` | Sturt 2013 source + layer entries |

---

## Verification

1. **Run Sturt 2013 converter:** `python -m pipeline.geological_layers.process_sturt_2013 --no-download`
2. **Check output files:** `ls public/data/geological/sturt_2013_*.geojson` — should be 22+ files
3. **Start dev server:** `cd ancient-nerds-map && npm run dev`
4. **Open globe:** Navigate to the globe, open Filter panel → Geological Layers
5. **Toggle Sturt 2013 layer:** Appears in a new "Sea Level" group with a time-step selector showing 22 buttons
6. **Click time steps:** Globe updates to show that coastline reconstruction
7. **Toggle EDGI lithology:** Raster texture overlay appears on the globe with opacity slider
8. **Verify no regressions:** Existing 9 Unpath'd Waters layers still work — toggle each one individually
9. **Mapbox sync:** When zoomed in and Mapbox active, geological layers appear in Mapbox view
10. **Build:** `npm run build` completes without TypeScript errors
