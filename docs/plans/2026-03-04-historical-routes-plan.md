# Historical Routes & Roads Panel — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a toggleable "Historical Routes" panel (like Empire Borders) showing ancient trade routes and Roman roads with individual per-route toggles, grouped by source.

**Architecture:** New `routeData.ts` config defines routes with colors/groups. A `useHistoricalRoutes` hook manages visibility/loading state. A `HistoricalRoutesPanel` component (floating, resizable, like `EmpireBordersPanel`) renders grouped toggles. Route GeoJSON is fetched on-demand and rendered as Three.js lines using the same `latLngTo3D` + `createFrontLineMaterial` pipeline as vector layers.

**Tech Stack:** TypeScript, React, Three.js, GeoJSON

---

### Task 1: Remove broken `romanRoads` from vector layers

**Files:**
- Modify: `ancient-nerds-map/src/config/vectorLayers.ts:70-92`
- Modify: `ancient-nerds-map/src/hooks/globe/useVectorLayers.ts:48-57`

**Step 1: Remove `romanRoads` from `LAYER_CONFIG`**

In `ancient-nerds-map/src/config/vectorLayers.ts`, delete lines 70-78 (the `romanRoads` entry) and remove `romanRoads: boolean` from `VectorLayerVisibility` (line 91).

**Step 2: Remove `romanRoads` from `DEFAULT_VISIBILITY`**

In `ancient-nerds-map/src/hooks/globe/useVectorLayers.ts`, remove `romanRoads: false` from `DEFAULT_VISIBILITY` (line 56).

**Step 3: Verify build**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean compile (no errors). If there are references to `romanRoads` elsewhere, fix them too.

**Step 4: Commit**

```bash
git add ancient-nerds-map/src/config/vectorLayers.ts ancient-nerds-map/src/hooks/globe/useVectorLayers.ts
git commit -m "chore: remove broken romanRoads from vector layers (no data file existed)"
```

---

### Task 2: Download AWMC roads GeoJSON

**Files:**
- Create: `ancient-nerds-map/public/data/layers/awmc_roads.geojson`

**Step 1: Download the file**

```bash
curl -sL "https://raw.githubusercontent.com/AWMC/geodata/master/Cultural-Data/roads/roads.geojson" -o ancient-nerds-map/public/data/layers/awmc_roads.geojson
```

**Step 2: Verify file integrity**

```bash
cd C:/PythonProjects/AncientMap && .venv/Scripts/python -c "
import json
with open('ancient-nerds-map/public/data/layers/awmc_roads.geojson') as f:
    data = json.load(f)
print(f'Features: {len(data[\"features\"])}')
print(f'Valid GeoJSON: True')
"
```
Expected: ~3166 features, valid GeoJSON.

**Step 3: Commit**

```bash
git add ancient-nerds-map/public/data/layers/awmc_roads.geojson
git commit -m "data: add AWMC Roman roads GeoJSON (ODbL licensed, 3166 segments)"
```

---

### Task 3: Add 7 new routes to `trade_routes.geojson`

**Files:**
- Modify: `ancient-nerds-map/public/data/layers/trade_routes.geojson`

**Step 1: Create a Python script to generate the new routes**

Create `scripts/add_trade_routes.py` that:
1. Reads existing `trade_routes.geojson`
2. Appends 7 new route features with historically accurate coordinates:
   - **Maritime Silk Road** (sea, 2nd c. BC – 500 AD): Guangzhou → Vietnam → Malacca → Sri Lanka → India → Persian Gulf → Red Sea → Egypt
   - **Phoenician Sea Routes** (sea, 1500 BC – 300 BC): Tyre → Cyprus → Crete → Sicily → Carthage → Sardinia → Iberia → Cadiz
   - **Lapis Lazuli Route** (land, 3000 BC – 500 BC): Badakhshan (Afghanistan) → Mesopotamia → Egypt
   - **Egyptian Route to Punt** (sea, 2500 BC – 1100 BC): Egyptian Red Sea ports → Horn of Africa coast
   - **Via Regia** (land, Bronze Age – Roman): Frankfurt → Leipzig → Wroclaw → Krakow → Lviv → Kyiv
   - **Salt Road** (land, Bronze Age – Roman): Saharan salt mines → Timbuktu → Niger River cities
   - **Grand Trunk Road** (land, 3rd c. BC – 500 AD): Pataliputra → Varanasi → Delhi → Lahore → Peshawar → Kabul
3. Writes back to `trade_routes.geojson`

Each route should have 100-400 coordinate points following realistic geography (following coastlines for sea routes, river valleys/mountain passes for land routes).

**Step 2: Run the script**

```bash
cd C:/PythonProjects/AncientMap && .venv/Scripts/python scripts/add_trade_routes.py
```

**Step 3: Verify**

```bash
.venv/Scripts/python -c "
import json
with open('ancient-nerds-map/public/data/layers/trade_routes.geojson') as f:
    data = json.load(f)
print(f'Total routes: {len(data[\"features\"])}')
for f in data['features']:
    print(f'  {f[\"properties\"][\"name\"]} ({f[\"properties\"].get(\"type\",\"?\")})')
"
```
Expected: 21 total routes.

**Step 4: Commit**

```bash
git add ancient-nerds-map/public/data/layers/trade_routes.geojson scripts/add_trade_routes.py
git commit -m "data: add 7 new ancient trade routes (Maritime Silk Road, Phoenician, etc.)"
```

---

### Task 4: Create `routeData.ts` config

**Files:**
- Create: `ancient-nerds-map/src/config/routeData.ts`

**Step 1: Create the route config file**

This defines all routes with their IDs, display names, colors, groups, and types. The IDs must match the `name` property in `trade_routes.geojson` features.

```typescript
/**
 * Historical route configuration
 * Defines trade routes and road networks for the Historical Routes panel
 */

export interface RouteConfig {
  id: string           // Matches "name" property in GeoJSON
  name: string         // Display name
  group: string        // Group name for panel UI
  color: number        // Hex color for rendering
  type: 'land' | 'sea' // Route type
  era: string          // Display era string
}

export const ROUTE_GROUPS = [
  'Ancient Trade Routes',
  'Roman Roads (AWMC)'
] as const

export type RouteGroup = typeof ROUTE_GROUPS[number]

export const ROUTES: RouteConfig[] = [
  // === Ancient Trade Routes (from trade_routes.geojson) ===
  // Land routes
  { id: 'Silk Road (Northern Route)', name: 'Silk Road (Northern)', group: 'Ancient Trade Routes', color: 0xFFD700, type: 'land', era: '130 BC – 500 AD' },
  { id: 'Silk Road (Southern Route)', name: 'Silk Road (Southern)', group: 'Ancient Trade Routes', color: 0xFFC125, type: 'land', era: '130 BC – 500 AD' },
  { id: 'Amber Road', name: 'Amber Road', group: 'Ancient Trade Routes', color: 0xFFBF00, type: 'land', era: '1600 BC – 500 AD' },
  { id: 'Incense Route', name: 'Incense Route', group: 'Ancient Trade Routes', color: 0xE6BE8A, type: 'land', era: '7th c. BC – 2nd c. AD' },
  { id: 'Trans-Saharan Route (Western)', name: 'Trans-Saharan Route', group: 'Ancient Trade Routes', color: 0xC19A6B, type: 'land', era: '500 BC – 500 AD' },
  { id: 'Royal Road (Persian)', name: 'Royal Road (Persian)', group: 'Ancient Trade Routes', color: 0xB8860B, type: 'land', era: '500 BC – 330 BC' },
  { id: 'Via Maris', name: 'Via Maris', group: 'Ancient Trade Routes', color: 0xCD853F, type: 'land', era: 'Bronze Age – Roman' },
  { id: "King's Highway", name: "King's Highway", group: 'Ancient Trade Routes', color: 0xD2691E, type: 'land', era: 'Bronze Age – Roman' },
  { id: 'Inca Road (Qhapaq Ñan) - Main North-South', name: 'Inca Road (Qhapaq Ñan)', group: 'Ancient Trade Routes', color: 0x8B4513, type: 'land', era: '1400s AD' },
  { id: 'Maya Trade Route (Inland)', name: 'Maya Trade Route (Inland)', group: 'Ancient Trade Routes', color: 0x228B22, type: 'land', era: '250 – 900 AD' },
  { id: 'Chaco Roads', name: 'Chaco Roads', group: 'Ancient Trade Routes', color: 0xA0522D, type: 'land', era: '850 – 1250 AD' },
  { id: 'Lapis Lazuli Route', name: 'Lapis Lazuli Route', group: 'Ancient Trade Routes', color: 0x26619C, type: 'land', era: '3000 BC – 500 BC' },
  { id: 'Via Regia', name: 'Via Regia', group: 'Ancient Trade Routes', color: 0x8B0000, type: 'land', era: 'Bronze Age – Roman' },
  { id: 'Salt Road', name: 'Salt Road', group: 'Ancient Trade Routes', color: 0xDEB887, type: 'land', era: 'Bronze Age – Roman' },
  { id: 'Grand Trunk Road', name: 'Grand Trunk Road', group: 'Ancient Trade Routes', color: 0x556B2F, type: 'land', era: '3rd c. BC – 500 AD' },
  // Sea routes
  { id: 'Spice Route (Maritime)', name: 'Spice Route (Maritime)', group: 'Ancient Trade Routes', color: 0xFF6347, type: 'sea', era: '3rd c. BC – 500 AD' },
  { id: 'Tin Route', name: 'Tin Route', group: 'Ancient Trade Routes', color: 0x708090, type: 'sea', era: '2000 BC – 500 BC' },
  { id: 'Maya Trade Route (Coastal)', name: 'Maya Trade Route (Coastal)', group: 'Ancient Trade Routes', color: 0x2E8B57, type: 'sea', era: '250 – 900 AD' },
  { id: 'Maritime Silk Road', name: 'Maritime Silk Road', group: 'Ancient Trade Routes', color: 0x4169E1, type: 'sea', era: '2nd c. BC – 500 AD' },
  { id: 'Phoenician Sea Routes', name: 'Phoenician Sea Routes', group: 'Ancient Trade Routes', color: 0x800080, type: 'sea', era: '1500 BC – 300 BC' },
  { id: 'Egyptian Route to Punt', name: 'Egyptian Route to Punt', group: 'Ancient Trade Routes', color: 0xDAA520, type: 'sea', era: '2500 BC – 1100 BC' },

  // === Roman Roads (AWMC) — single bulk entry ===
  // This is NOT a route from trade_routes.geojson — it loads awmc_roads.geojson separately
]

// Special constant for the AWMC roads layer (loaded from separate file)
export const AWMC_ROADS_CONFIG = {
  id: 'awmc_roads',
  name: 'Roman Roads (AWMC)',
  group: 'Roman Roads (AWMC)' as RouteGroup,
  color: 0xDAA520,  // Goldenrod
  era: '300 BC – 400 AD',
  file: '/data/layers/awmc_roads.geojson',
  attribution: 'Data from Ancient World Mapping Center, UNC Chapel Hill (ODbL)'
}

export function getRoutesByGroup(group: RouteGroup): RouteConfig[] {
  return ROUTES.filter(r => r.group === group)
}

export function getRouteById(id: string): RouteConfig | undefined {
  return ROUTES.find(r => r.id === id)
}
```

**Step 2: Verify build**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean compile.

**Step 3: Commit**

```bash
git add ancient-nerds-map/src/config/routeData.ts
git commit -m "feat: add routeData.ts config for 21 trade routes + AWMC roads"
```

---

### Task 5: Create `useHistoricalRoutes` hook

**Files:**
- Create: `ancient-nerds-map/src/hooks/globe/useHistoricalRoutes.ts`
- Modify: `ancient-nerds-map/src/hooks/globe/index.ts`

**Step 1: Create the hook**

```typescript
/**
 * useHistoricalRoutes - Historical route visibility and panel state
 * Manages which routes are toggled on, loading state, and panel UI state
 */

import { useState, useRef } from 'react'

export function useHistoricalRoutes() {
  // Panel state
  const [routesPanelOpen, setRoutesPanelOpen] = useState(false)
  const [routesPanelHeight, setRoutesPanelHeight] = useState(350)

  // Route visibility
  const [visibleRoutes, setVisibleRoutes] = useState<Set<string>>(new Set())
  const visibleRoutesRef = useRef<Set<string>>(new Set())

  // Loading state
  const [loadingRoutes, setLoadingRoutes] = useState<Set<string>>(new Set())

  // Group expansion UI
  const [expandedRouteGroups, setExpandedRouteGroups] = useState<Set<string>>(new Set(['Ancient Trade Routes']))

  // Sync ref
  visibleRoutesRef.current = visibleRoutes

  return {
    routesPanelOpen, setRoutesPanelOpen,
    routesPanelHeight, setRoutesPanelHeight,
    visibleRoutes, setVisibleRoutes, visibleRoutesRef,
    loadingRoutes, setLoadingRoutes,
    expandedRouteGroups, setExpandedRouteGroups,
  }
}
```

**Step 2: Export from index.ts**

Add to `ancient-nerds-map/src/hooks/globe/index.ts` in the "Medium complexity hooks" section:
```typescript
export { useHistoricalRoutes } from './useHistoricalRoutes'
```

**Step 3: Verify build**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean compile.

**Step 4: Commit**

```bash
git add ancient-nerds-map/src/hooks/globe/useHistoricalRoutes.ts ancient-nerds-map/src/hooks/globe/index.ts
git commit -m "feat: add useHistoricalRoutes hook for route visibility state"
```

---

### Task 6: Create `HistoricalRoutesPanel` component

**Files:**
- Create: `ancient-nerds-map/src/components/Globe/panels/HistoricalRoutesPanel.tsx`
- Modify: `ancient-nerds-map/src/components/Globe/panels/index.ts`

**Step 1: Create the panel component**

Model after `EmpireBordersPanel.tsx` (same structure: header, close btn, resize handle, scrollable list with collapsible groups). Key differences from Empire Borders:
- No year sliders (routes don't have temporal snapshots)
- Two groups: "Ancient Trade Routes" (21 individual toggles), "Roman Roads (AWMC)" (1 bulk toggle)
- Each route shows a color dot + name + era + loading indicator
- All/None/Invert quick buttons

```typescript
/**
 * HistoricalRoutesPanel - Floating panel for historical route toggles
 * Similar to EmpireBordersPanel but simpler (no year sliders)
 */

import { ROUTES, ROUTE_GROUPS, AWMC_ROADS_CONFIG, type RouteGroup } from '../../../config/routeData'

interface HistoricalRoutesPanelProps {
  isOpen: boolean
  onClose: () => void
  height: number
  onHeightChange: (height: number) => void

  visibleRoutes: Set<string>
  onToggleRoute: (routeId: string) => void
  loadingRoutes: Set<string>

  expandedGroups: Set<string>
  onToggleGroup: (group: string) => void
}

export function HistoricalRoutesPanel({
  isOpen,
  onClose,
  height,
  onHeightChange,
  visibleRoutes,
  onToggleRoute,
  loadingRoutes,
  expandedGroups,
  onToggleGroup,
}: HistoricalRoutesPanelProps) {
  if (!isOpen) return null

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    const startY = e.clientY
    const startHeight = height
    const onMove = (e: MouseEvent) => {
      const deltaY = startY - e.clientY
      onHeightChange(Math.max(150, Math.min(600, startHeight + deltaY)))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  const allRouteIds = [...ROUTES.map(r => r.id), AWMC_ROADS_CONFIG.id]

  return (
    <div className="empire-borders-window" style={{ height }}>
      <div className="empire-borders-header">
        <div className="panel-label">Historical Routes</div>
        <button className="panel-close-btn" onClick={onClose} title="Close">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      {/* Quick actions */}
      <div className="empire-options-row">
        <div className="empire-quick-btns">
          <button className="filter-btn" onClick={() => {
            allRouteIds.forEach(id => { if (!visibleRoutes.has(id)) onToggleRoute(id) })
          }}>All</button>
          <button className="filter-btn" onClick={() => {
            allRouteIds.forEach(id => { if (visibleRoutes.has(id)) onToggleRoute(id) })
          }}>None</button>
          <button className="filter-btn" onClick={() => {
            allRouteIds.forEach(id => onToggleRoute(id))
          }}>Invert</button>
        </div>
      </div>

      <div className="empire-borders-resize-handle" onMouseDown={handleResizeStart} />

      <div className="empire-borders-list">
        {ROUTE_GROUPS.map(group => (
          <div key={group} className="empire-region-compact">
            <div className="region-header-compact" onClick={() => onToggleGroup(group)}>
              <span className="region-chevron">{expandedGroups.has(group) ? '−' : '+'}</span>
              <span>{group}</span>
            </div>
            {expandedGroups.has(group) && (
              <div className="empire-list-compact">
                {group === 'Roman Roads (AWMC)' ? (
                  /* AWMC roads: single bulk toggle */
                  <label className={`empire-row-inline ${visibleRoutes.has(AWMC_ROADS_CONFIG.id) ? 'active' : ''}`}>
                    <input
                      type="checkbox"
                      checked={visibleRoutes.has(AWMC_ROADS_CONFIG.id)}
                      onChange={() => onToggleRoute(AWMC_ROADS_CONFIG.id)}
                    />
                    <span
                      className="empire-color-dot"
                      style={{ backgroundColor: `#${AWMC_ROADS_CONFIG.color.toString(16).padStart(6, '0')}` }}
                    />
                    <span className="empire-name-truncated" title={`${AWMC_ROADS_CONFIG.name} (${AWMC_ROADS_CONFIG.era})`}>
                      {AWMC_ROADS_CONFIG.name}
                    </span>
                    {loadingRoutes.has(AWMC_ROADS_CONFIG.id) && <span className="loading-dots">...</span>}
                  </label>
                ) : (
                  /* Trade routes: individual toggles */
                  ROUTES.filter(r => r.group === group).map(route => (
                    <label key={route.id} className={`empire-row-inline ${visibleRoutes.has(route.id) ? 'active' : ''}`}>
                      <input
                        type="checkbox"
                        checked={visibleRoutes.has(route.id)}
                        onChange={() => onToggleRoute(route.id)}
                      />
                      <span
                        className="empire-color-dot"
                        style={{ backgroundColor: `#${route.color.toString(16).padStart(6, '0')}` }}
                      />
                      <span className="empire-name-truncated" title={`${route.name} (${route.era})`}>
                        {route.name}
                      </span>
                      {loadingRoutes.has(route.id) && <span className="loading-dots">...</span>}
                    </label>
                  ))
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
```

**Step 2: Export from panel index**

Add to `ancient-nerds-map/src/components/Globe/panels/index.ts`:
```typescript
export { HistoricalRoutesPanel } from './HistoricalRoutesPanel'
```

**Step 3: Verify build**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean compile.

**Step 4: Commit**

```bash
git add ancient-nerds-map/src/components/Globe/panels/HistoricalRoutesPanel.tsx ancient-nerds-map/src/components/Globe/panels/index.ts
git commit -m "feat: add HistoricalRoutesPanel component with grouped route toggles"
```

---

### Task 7: Add "Historical Routes" toggle to `HistoricalLayersSection`

**Files:**
- Modify: `ancient-nerds-map/src/components/Globe/panels/HistoricalLayersSection.tsx`

**Step 1: Add props for routes toggle**

Add to `HistoricalLayersSectionProps`:
```typescript
  // Historical Routes toggle
  hasVisibleRoutes: boolean
  onHistoricalRoutesToggle: () => void
```

Add to destructured props:
```typescript
  hasVisibleRoutes,
  onHistoricalRoutesToggle,
```

**Step 2: Add toggle JSX after Empire Borders toggle**

After the Empire Borders `</label>` (line 172), add:
```tsx
      {/* Historical Routes toggle */}
      <label className="layer-toggle">
        <input
          type="checkbox"
          checked={hasVisibleRoutes}
          onChange={onHistoricalRoutesToggle}
        />
        <span
          className="layer-color-indicator"
          style={{ backgroundColor: '#DAA520' }}
        />
        <span className="layer-label">Historical Routes</span>
      </label>
```

**Step 3: Verify build**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Will fail because Globe.tsx doesn't pass the new props yet — that's Task 8.

**Step 4: Commit**

```bash
git add ancient-nerds-map/src/components/Globe/panels/HistoricalLayersSection.tsx
git commit -m "feat: add Historical Routes toggle to HistoricalLayersSection"
```

---

### Task 8: Wire everything up in `Globe.tsx`

This is the main integration task. We need to:
1. Import the new hook, panel, and config
2. Add route loading/unloading logic (fetch GeoJSON, create Three.js lines)
3. Pass props to HistoricalLayersSection and HistoricalRoutesPanel
4. Handle route toggle (load/unload GeoJSON, create/remove lines)

**Files:**
- Modify: `ancient-nerds-map/src/components/Globe.tsx`

**Step 1: Add imports**

Near other imports at top of Globe.tsx, add:
```typescript
import { ROUTES, AWMC_ROADS_CONFIG, getRouteById } from '../config/routeData'
import { useHistoricalRoutes } from '../hooks/globe'
```

Update the panels import to include `HistoricalRoutesPanel`:
```typescript
import { ZoomControls, SocialLinks, OptionsPanel, MapLayersPanel, HistoricalLayersSection, EmpireBordersPanel, HistoricalRoutesPanel } from './Globe/panels'
```

**Step 2: Use the hook**

After the `useEmpireBorders` destructuring block (~line 226), add:
```typescript
  const routes = useHistoricalRoutes()
  const {
    routesPanelOpen, setRoutesPanelOpen,
    routesPanelHeight, setRoutesPanelHeight,
    visibleRoutes, setVisibleRoutes,
    loadingRoutes, setLoadingRoutes,
    expandedRouteGroups, setExpandedRouteGroups,
  } = routes
```

**Step 3: Add route line object refs**

Near other refs in Globe.tsx, add:
```typescript
  const routeLineObjectsRef = useRef<Record<string, THREE.Line[]>>({})
```

**Step 4: Add route toggle function**

After the empire toggle functions, add:
```typescript
  const toggleRoute = useCallback((routeId: string) => {
    setVisibleRoutes(prev => {
      const next = new Set(prev)
      if (next.has(routeId)) {
        next.delete(routeId)
        // Remove lines from scene
        const lines = routeLineObjectsRef.current[routeId]
        if (lines && sceneRef.current) {
          lines.forEach(line => {
            sceneRef.current!.globe.remove(line)
            ;(line.geometry as THREE.BufferGeometry).dispose()
            ;(line.material as THREE.Material).dispose()
          })
          delete routeLineObjectsRef.current[routeId]
        }
      } else {
        next.add(routeId)
        // Load route
        loadRoute(routeId)
      }
      return next
    })
  }, [])

  const loadRoute = useCallback(async (routeId: string) => {
    if (!sceneRef.current) return

    setLoadingRoutes(prev => {
      const next = new Set(prev)
      next.add(routeId)
      return next
    })

    try {
      // Determine which file to fetch and how to filter features
      let url: string
      let filterFn: ((feature: any) => boolean) | null = null

      if (routeId === AWMC_ROADS_CONFIG.id) {
        url = AWMC_ROADS_CONFIG.file
      } else {
        url = '/data/layers/trade_routes.geojson'
        filterFn = (feature: any) => feature.properties?.name === routeId
      }

      const response = await fetch(url)
      if (!response.ok) throw new Error(`Failed to load route: ${routeId}`)
      const data = await response.json()

      if (!sceneRef.current) return

      const features = filterFn ? data.features.filter(filterFn) : data.features
      if (features.length === 0) {
        console.warn(`No features found for route: ${routeId}`)
        return
      }

      // Get color
      const routeConfig = getRouteById(routeId)
      const color = routeId === AWMC_ROADS_CONFIG.id
        ? AWMC_ROADS_CONFIG.color
        : (routeConfig?.color ?? 0xFFD700)

      // Create front material
      const material = createFrontMaterial(color, 0)
      shaderMaterialsRef.current.push(material)
      material.uniforms.uCameraPos.value.copy(sceneRef.current.camera.position)

      // Build merged geometry from all features
      const allPositions: number[] = []
      const latLngTo3D = latLngTo3DRef.current

      for (const feature of features) {
        const geomType = feature.geometry.type
        let coordSets: number[][][] = []

        if (geomType === 'LineString') {
          coordSets = [feature.geometry.coordinates]
        } else if (geomType === 'MultiLineString') {
          coordSets = feature.geometry.coordinates
        } else if (geomType === 'Polygon') {
          coordSets = feature.geometry.coordinates
        } else if (geomType === 'MultiPolygon') {
          coordSets = feature.geometry.coordinates.flat()
        }

        for (const coords of coordSets) {
          if (coords.length > 1) {
            for (const coord of coords) {
              const point = latLngTo3D(coord[1], coord[0], 1.002)
              allPositions.push(point.x, point.y, point.z)
            }
            allPositions.push(NaN, NaN, NaN) // Line break
          }
        }
      }

      // Remove trailing NaNs
      while (allPositions.length >= 3 && isNaN(allPositions[allPositions.length - 1])) {
        allPositions.pop(); allPositions.pop(); allPositions.pop()
      }

      if (allPositions.length === 0) return

      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(allPositions, 3))
      geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1.003)

      const line = new THREE.Line(geometry, material)
      line.renderOrder = 10
      sceneRef.current.globe.add(line)

      routeLineObjectsRef.current[routeId] = [line]

      // Fade in
      fadeManagerRef.current.fadeTo(`route_${routeId}`, [material], 1)

    } catch (err) {
      console.error(`Failed to load route ${routeId}:`, err)
    } finally {
      setLoadingRoutes(prev => {
        const next = new Set(prev)
        next.delete(routeId)
        return next
      })
    }
  }, [])
```

Note: `createFrontMaterial`, `shaderMaterialsRef`, `sceneRef`, `latLngTo3DRef`, and `fadeManagerRef` are already available in Globe.tsx scope from the existing vector layer rendering setup.

**Step 5: Add props to HistoricalLayersSection**

Find the `<HistoricalLayersSection` JSX and add the new props:
```typescript
          hasVisibleRoutes={visibleRoutes.size > 0}
          onHistoricalRoutesToggle={() => setRoutesPanelOpen(prev => !prev)}
```

**Step 6: Add HistoricalRoutesPanel JSX**

After the `</MapLayersPanel>` closing tag and near `<EmpireBordersPanel`, add:
```tsx
      {/* Historical Routes Window */}
      <HistoricalRoutesPanel
        isOpen={routesPanelOpen}
        onClose={() => setRoutesPanelOpen(false)}
        height={routesPanelHeight}
        onHeightChange={setRoutesPanelHeight}
        visibleRoutes={visibleRoutes}
        onToggleRoute={toggleRoute}
        loadingRoutes={loadingRoutes}
        expandedGroups={expandedRouteGroups}
        onToggleGroup={(group) => setExpandedRouteGroups(prev => {
          const next = new Set(prev)
          if (next.has(group)) next.delete(group)
          else next.add(group)
          return next
        })}
      />
```

**Step 7: Verify build**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean compile.

**Step 8: Commit**

```bash
git add ancient-nerds-map/src/components/Globe.tsx
git commit -m "feat: wire up Historical Routes panel with route loading and rendering"
```

---

### Task 9: Test end-to-end in dev server

**Step 1: Start dev server**

```bash
cd ancient-nerds-map && npm run dev
```

**Step 2: Manual testing checklist**

- [ ] "Historical Routes" toggle appears in Historical Layers section (below Empire Borders)
- [ ] Clicking it opens a floating panel (similar to Empire Borders)
- [ ] Panel shows two groups: "Ancient Trade Routes" and "Roman Roads (AWMC)"
- [ ] Expanding "Ancient Trade Routes" shows 21 individual route toggles with color dots
- [ ] Toggling a route shows loading indicator (...) then renders colored lines on the globe
- [ ] Toggling a route off removes the lines
- [ ] "Roman Roads (AWMC)" group has single toggle that loads the full AWMC dataset
- [ ] All/None/Invert quick buttons work
- [ ] Panel is resizable (drag bottom edge)
- [ ] Panel close button works
- [ ] No console errors
- [ ] `romanRoads` no longer appears in Vector Layers section

**Step 3: Fix any issues found**

**Step 4: Final commit if fixes needed**

---

### Task 10: Copy data files and verify prod build

**Step 1: Copy updated data to public/**

```bash
cp ancient-nerds-map/public/data/layers/trade_routes.geojson public/data/layers/trade_routes.geojson
cp ancient-nerds-map/public/data/layers/awmc_roads.geojson public/data/layers/awmc_roads.geojson
```

**Step 2: Build for production**

```bash
cd ancient-nerds-map && npm run build
```
Expected: Clean build, no errors.

**Step 3: Final commit**

```bash
git add public/data/layers/trade_routes.geojson public/data/layers/awmc_roads.geojson
git commit -m "chore: sync data files to public/ for production"
```
