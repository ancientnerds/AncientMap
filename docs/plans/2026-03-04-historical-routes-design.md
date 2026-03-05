# Historical Routes & Roads Panel — Design

## Goal

Add a toggleable "Historical Routes" panel (like Empire Borders) to the globe, showing ancient trade routes and road networks with individual per-route toggles, grouped by source.

## Time Period Filter

- Rest of world: routes active before 500 AD only
- Americas: routes active before 1500 AD only

## Data Sources

### 1. Existing `trade_routes.geojson` (expand from 14 → 21 routes)

Already in `public/data/layers/`, 425 KB. Currently unused by the globe UI.

**Existing routes (14):**
| Route | Era | Type |
|-------|-----|------|
| Silk Road (Northern) | 130 BC – 500 AD | land |
| Silk Road (Southern) | 130 BC – 500 AD | land |
| Amber Road | 1600 BC – 500 AD | land |
| Incense Route | 7th c. BC – 2nd c. AD | land |
| Trans-Saharan (Western) | 500 BC – 500 AD | land |
| Spice Route (Maritime) | 3rd c. BC – 500 AD | sea |
| Tin Route | 2000 BC – 500 BC | sea |
| Royal Road (Persian) | 500 BC – 330 BC | land |
| Via Maris | Bronze Age – Roman | land |
| King's Highway | Bronze Age – Roman | land |
| Inca Road (Qhapaq Ñan) | 1400s AD | land |
| Maya Trade Route (Coastal) | 250 – 900 AD | sea |
| Maya Trade Route (Inland) | 250 – 900 AD | land |
| Chaco Roads | 850 – 1250 AD | land |

**New routes to add (7):**
| Route | Era | Type | Source |
|-------|-----|------|--------|
| Maritime Silk Road | 2nd c. BC – 500 AD | sea | Created from historical coordinates |
| Phoenician Sea Routes | 1500 BC – 300 BC | sea | Created from historical coordinates |
| Lapis Lazuli Route | 3000 BC – 500 BC | land | Created from historical coordinates |
| Egyptian Route to Punt | 2500 BC – 1100 BC | sea | Created from historical coordinates |
| Via Regia | Bronze Age – Roman | land | Created from historical coordinates |
| Salt Road (Saharan) | Bronze Age – Roman | land | Created from historical coordinates |
| Grand Trunk Road | 3rd c. BC – 500 AD | land | Created from historical coordinates |

### 2. AWMC Roads (download from GitHub)

Source: https://github.com/AWMC/geodata — `Cultural-Data/roads/roads.geojson`
License: ODbL (Open Database License) — safe for use with attribution
Content: 3,166 Roman road segments, 68 named roads (Via Appia, Via Egnatia, etc.), 88K coordinate points
Stored as: `public/data/layers/awmc_roads.geojson`

## UI Design

### Toggle Entry Point

In `HistoricalLayersSection`, add a checkbox toggle for "Historical Routes" (like Empire Borders toggle). Checking it opens a floating panel.

### Historical Routes Panel (new component)

Mirrors `EmpireBordersPanel` structure:
- Header with "Historical Routes" title + close button
- Resize handle for vertical resizing
- All/None/Invert quick action buttons
- Scrollable list with two collapsible groups:

**Group 1: "Ancient Trade Routes"** (21 individual toggles)
- Each route gets: checkbox, color dot, name, loading indicator
- Distinct color per route

**Group 2: "Roman Roads (AWMC)"** (single bulk toggle)
- One checkbox that loads/unloads the entire AWMC road network
- Too many segments (3,166) for individual toggles

### Colors

Each route gets a unique color for visual distinction on the globe. Route colors defined in `routeData.ts`.

## Architecture

### Config: `src/config/routeData.ts`

Route definitions: id, name, group, color (hex number), type (land/sea), era string.
Groups: `ROUTE_GROUPS` array and `ROUTES` array (like `EMPIRES` and `EMPIRE_REGIONS`).

### Panel: `src/components/Globe/panels/HistoricalRoutesPanel.tsx`

Floating panel component, same pattern as `EmpireBordersPanel`.
Props: isOpen, onClose, height, onHeightChange, visibleRoutes (Set<string>), onToggleRoute, loadingRoutes (Set<string>), expandedGroups (Set<string>), onToggleGroup.

### Rendering

Routes rendered as Three.js `Line` objects using `LineBasicMaterial` at radius 1.002 (same as other vector layers). Loaded on-demand when toggled. GeoJSON fetched, parsed, converted to 3D lines on the globe surface.

Reuses existing vector layer line rendering logic from `useVectorLayers` / Globe.tsx `processGeoJSON`.

### State (in Globe.tsx)

- `routesPanelOpen: boolean` — panel visibility
- `visibleRoutes: Set<string>` — which routes are toggled on
- `loadingRoutes: Set<string>` — routes currently being fetched/processed
- `routeObjects: Record<string, THREE.Object3D[]>` — rendered route line objects
- `expandedRouteGroups: Set<string>` — which groups are expanded in the panel
- `routesPanelHeight: number` — resizable panel height

### Cleanup: Remove broken `romanRoads`

- Remove `romanRoads` from `LAYER_CONFIG` in `vectorLayers.ts`
- Remove from `VectorLayerVisibility` type
- Remove from `DEFAULT_VISIBILITY` in `useVectorLayers.ts`

## Files to Create/Modify

### New files
- `src/config/routeData.ts`
- `src/components/Globe/panels/HistoricalRoutesPanel.tsx`
- `scripts/create_additional_routes.py` (one-time script to generate 7 new routes)
- `public/data/layers/awmc_roads.geojson` (downloaded)

### Modified files
- `src/config/vectorLayers.ts` — remove `romanRoads`
- `src/hooks/globe/useVectorLayers.ts` — remove `romanRoads` from defaults
- `src/components/Globe/panels/HistoricalLayersSection.tsx` — add routes toggle
- `src/components/Globe/panels/index.ts` — export new panel
- `src/components/Globe.tsx` — wire up routes state, panel, rendering
- `public/data/layers/trade_routes.geojson` — add 7 new routes

## Licensing

| Source | License | Attribution Required |
|--------|---------|---------------------|
| trade_routes.geojson (our data) | N/A (custom created) | No |
| AWMC roads | ODbL | Yes — "Data from Ancient World Mapping Center, UNC Chapel Hill" |
| Additional routes | Custom created from historical coordinates | No |
