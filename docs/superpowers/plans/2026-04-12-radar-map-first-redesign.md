# Radar Map-First Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Radar page as a split-view (map 60% + card list 40%) with pipeline data surfaced on cards and map improvements.

**Architecture:** The Mapbox globe becomes the permanent left pane with the sweep animation always running. The card list scrolls in the right pane. Hover/click on either side syncs to the other. Five new fields from the pipeline (significance, category, speculative, AI reasoning) are added to the API response and rendered as badges/tooltips on cards. Map gets clustering, a score legend, and filter sync.

**Tech Stack:** React + TypeScript + Mapbox GL JS (frontend), FastAPI + PostgreSQL (API)

**Spec:** `docs/superpowers/specs/2026-04-12-radar-map-first-redesign.md`

---

### Task 1: API — Add Pipeline Data to Radar Response

Add significance, category, speculative, and AI reasoning fields to the `/radar/list` endpoint. Also add `news_category` and `hide_speculative` query parameters.

**Files:**
- Modify: `api/routes/radar.py`

- [ ] **Step 1: Add aggregation columns to video_agg CTE**

In `api/routes/radar.py`, find the `video_agg` CTE (starts around line 381). After the `latest_screenshot_url` line, add four new aggregate columns:

```sql
                (ARRAY_AGG(ni.screenshot_url ORDER BY ni.created_at DESC) FILTER (WHERE ni.screenshot_url IS NOT NULL))[1] AS latest_screenshot_url,
                AVG(ni.significance) FILTER (WHERE ni.significance IS NOT NULL) AS avg_significance,
                MODE() WITHIN GROUP (ORDER BY ni.news_category) FILTER (WHERE ni.news_category IS NOT NULL) AS top_news_category,
                BOOL_OR(ni.speculative_tag IS NOT NULL) AS is_speculative,
                (ARRAY_AGG(ni.speculative_tag) FILTER (WHERE ni.speculative_tag IS NOT NULL))[1] AS speculative_tag
```

- [ ] **Step 2: Add new columns to the main SELECT**

In the main SELECT (around line 424), after `va.latest_screenshot_url`, add:

```sql
            va.latest_screenshot_url,
            va.avg_significance,
            va.top_news_category,
            COALESCE(va.is_speculative, false) AS is_speculative,
            va.speculative_tag
```

- [ ] **Step 3: Unpack ai_reasoning in _row_to_item**

In the `_row_to_item` function (around line 460), where `confidence` is extracted from `enrichment_data["identification"]`, also extract `reasoning`:

```python
            if isinstance(ident, dict):
                confidence = ident.get("confidence")
                ai_reasoning = ident.get("reasoning")
```

Declare `ai_reasoning = None` alongside the existing `confidence = None` declaration.

- [ ] **Step 4: Add new fields to response dict**

In the return dict of `_row_to_item` (around line 501), add after the `"screenshot_url"` line:

```python
            "avg_significance": round(float(row.avg_significance), 1) if row.avg_significance else None,
            "top_news_category": getattr(row, "top_news_category", None),
            "is_speculative": getattr(row, "is_speculative", False),
            "speculative_tag": getattr(row, "speculative_tag", None),
            "ai_reasoning": ai_reasoning,
```

- [ ] **Step 5: Add query parameters for category and speculative filtering**

Add two new query params to `get_radar`:

```python
    news_category: str = Query("all", pattern="^(all|excavation|artifact|architecture|bioarchaeology|dating|remote_sensing|underwater|epigraphy|conservation|heritage|theory|technology|archaeoastronomy|survey|art|general|speculative)$"),
    hide_speculative: bool = Query(False),
```

Add HAVING clauses to the `video_agg` CTE — wrap the existing `GROUP BY c.id` with:

```sql
            GROUP BY c.id
            HAVING (:news_category = 'all' OR MODE() WITHIN GROUP (ORDER BY ni.news_category) FILTER (WHERE ni.news_category IS NOT NULL) = :news_category)
               AND (:hide_speculative = false OR NOT BOOL_OR(ni.speculative_tag IS NOT NULL))
```

Add `"news_category": news_category, "hide_speculative": hide_speculative` to the `params` dict. Update the `cache_key` to include these params.

- [ ] **Step 6: Verify API returns new fields**

Run: `curl -s "http://localhost:8000/radar/list?page=1&page_size=2" | python -m json.tool | head -60`

Expected: Items now include `avg_significance`, `top_news_category`, `is_speculative`, `speculative_tag`, `ai_reasoning` fields.

- [ ] **Step 7: Commit**

```bash
git add api/routes/radar.py
git commit -m "feat(radar): add significance, category, speculative, and AI reasoning to API response"
```

---

### Task 2: Split-View Layout

Replace the current grid-only layout with a permanent split view: map on the left (60%), card list on the right (40%). Remove the map toggle button.

**Files:**
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.tsx`
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.css`

- [ ] **Step 1: Add CSS for split-view layout**

Add to the end of `LyraRadarPage.css`:

```css
/* =============================================================================
   Split-view layout: map (left) + card list (right)
   ============================================================================= */

.radar-split-view {
  display: flex;
  height: calc(100vh - 180px);
  overflow: hidden;
}

.radar-split-map {
  position: relative;
  flex: 0 0 60%;
  min-width: 0;
}

.radar-split-map .radar-map-container {
  height: 100%;
  border-radius: 0;
  margin-bottom: 0;
  border: none;
  border-right: 1px solid rgba(78, 205, 196, 0.15);
}

.radar-split-cards {
  flex: 0 0 40%;
  min-width: 0;
  overflow-y: auto;
  padding: 12px;
  scrollbar-width: thin;
  scrollbar-color: rgba(78, 205, 196, 0.3) transparent;
}

.radar-split-cards .lyra-discoveries-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0;
  max-width: none;
}

.radar-split-cards .lyra-discoveries-column {
  flex: none;
  width: 100%;
}

/* Map overlay: filters + stats float over the map */
.radar-map-overlay-filters {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  pointer-events: none;
}

.radar-map-overlay-filters > * {
  pointer-events: auto;
}

.radar-map-overlay-stats {
  position: absolute;
  top: 50px;
  left: 10px;
  z-index: 2;
  pointer-events: none;
}

.radar-map-overlay-stats > * {
  pointer-events: auto;
}

/* Card highlight when hovered via map */
.radar-card-highlighted {
  outline: 1px solid rgba(78, 205, 196, 0.6);
  outline-offset: -1px;
  box-shadow: 0 0 12px rgba(78, 205, 196, 0.15);
}

/* Mobile: bottom sheet */
@media (max-width: 768px) {
  .radar-split-view {
    flex-direction: column;
    height: 100vh;
  }

  .radar-split-map {
    flex: 1 1 auto;
    min-height: 50vh;
  }

  .radar-split-map .radar-map-container {
    border-right: none;
    border-bottom: 1px solid rgba(78, 205, 196, 0.15);
  }

  .radar-split-cards {
    flex: 0 0 auto;
    max-height: 50vh;
    border-top: 2px solid rgba(78, 205, 196, 0.3);
  }
}
```

- [ ] **Step 2: Update RadarItem interface with new fields**

In `LyraRadarPage.tsx`, add to the `RadarItem` interface (after `source: string | null`):

```typescript
  avg_significance: number | null
  top_news_category: string | null
  is_speculative: boolean
  speculative_tag: string | null
  ai_reasoning: string | null
```

- [ ] **Step 3: Add state for highlighted card and always-on map**

Find the state declarations (around line 640-660). Remove `showMap` state entirely. Add:

```typescript
  const [highlightedCardId, setHighlightedCardId] = useState<string | null>(null)
```

Remove the `showMap` toggle and default the map to always load. Change the map fetch `useEffect` — remove the `if (!showMap || ...)` guard so it always fetches on mount:

```typescript
  useEffect(() => {
    if (radarMapFetched.current) return
    radarMapFetched.current = true
    fetch(`${config.api.baseUrl}/radar/map`)
      // ... rest stays the same
  }, [])
```

- [ ] **Step 4: Restructure JSX to split-view**

Replace the entire return JSX. The new structure:

```
<div className="lyra-discoveries-page">
  <PageHeader ... />
  <div className="radar-experimental-banner">...</div>
  <div className="radar-split-view">
    {/* LEFT: Map pane */}
    <div className="radar-split-map">
      <Suspense fallback={<div style={{ width: '100%', height: '100%' }} />}>
        <RadarMap items={allRadarMapItems} onHoverItem={handleMapHover} onPinItem={handleMapPin} />
      </Suspense>
      {/* Floating filters over map */}
      <div className="radar-map-overlay-filters">
        {/* All filter chips go here (moved from below the header) */}
      </div>
      {/* Floating stats */}
      <div className="radar-map-overlay-stats">
        {stats && <PageStatsBar items={...} />}
      </div>
    </div>
    {/* RIGHT: Card list */}
    <div className="radar-split-cards">
      <AiNoticeBanner />
      {error && <div className="news-page-error">...</div>}
      {!error && items.length === 0 && !loading && <div className="news-page-empty">...</div>}
      <div className="lyra-discoveries-grid" ref={gridRef}>
        {items.map(item => (
          <div key={item.id} data-radar-id={item.id}
               className={highlightedCardId === item.id ? 'radar-card-highlighted' : ''}>
            <RadarCard item={item} onViewSite={setSelectedSite}
                       onPromote={isFounder ? handlePromote : undefined} />
          </div>
        ))}
      </div>
      {loading && <div className="news-page-loading">Loading...</div>}
      <div ref={sentinelRef} style={{ height: 1 }} />
    </div>
  </div>
  {/* Modals stay outside split view */}
</div>
```

Key changes:
- Remove the multi-column masonry layout — cards stack in a single column in the 40% right pane
- Remove the `showMap` toggle button from filters
- Move filters into `radar-map-overlay-filters` (floating over the map)
- Move stats into `radar-map-overlay-stats`
- Remove `radar-map-wrapper` wrapper — map now lives in `radar-split-map`
- Remove the map card overlay (`radar-map-card-overlay`) — cards are in the right pane now
- The `columnCount` state and `ResizeObserver` for masonry can be removed

- [ ] **Step 5: Update the map item mapping to include new fields**

In the map data fetch `useEffect`, add default values for the new fields in the mapping:

```typescript
          avg_significance: null,
          top_news_category: null,
          is_speculative: false,
          speculative_tag: null,
          ai_reasoning: null,
```

- [ ] **Step 6: Verify layout renders**

Run: `cd ancient-nerds-map && npx tsc --noEmit`

Expected: No type errors. Open `/radar.html` in browser — map should fill left 60%, cards should scroll in right 40%. Filters float over the map. Resize to <768px — should stack vertically.

- [ ] **Step 7: Commit**

```bash
git add ancient-nerds-map/src/pages/LyraRadarPage.tsx ancient-nerds-map/src/pages/LyraRadarPage.css
git commit -m "feat(radar): split-view layout with permanent map and scrollable card list"
```

---

### Task 3: Hover Sync Between Map and Cards

Wire bidirectional sync: hovering a card highlights its dot on the map, hovering a map dot scrolls to and highlights its card.

**Files:**
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.tsx`
- Modify: `ancient-nerds-map/src/components/RadarMap.tsx`

- [ ] **Step 1: Add highlightId prop to RadarMap**

In `RadarMap.tsx`, extend `RadarMapProps`:

```typescript
interface RadarMapProps {
  items: RadarMapItem[]
  highlightId?: string | null
  onHoverItem?: (id: string | null) => void
  onPinItem?: (id: string | null) => void
  children?: ReactNode
}
```

- [ ] **Step 2: React to highlightId changes in RadarMap**

Add a `useEffect` in `RadarMap` (after the items update effect, around line 275) that sets the feature state for the highlighted dot:

```typescript
  const prevHighlightRef = useRef<string | null>(null)

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return

    // Clear previous highlight
    if (prevHighlightRef.current) {
      map.setFeatureState(
        { source: 'radar-sites', id: prevHighlightRef.current },
        { glow: false }
      )
    }

    // Set new highlight
    if (highlightId) {
      map.setFeatureState(
        { source: 'radar-sites', id: highlightId },
        { glow: true }
      )
    }

    prevHighlightRef.current = highlightId ?? null
  }, [highlightId])
```

- [ ] **Step 3: Wire card hover → map highlight in LyraRadarPage**

In `LyraRadarPage.tsx`, add a `handleCardHover` callback:

```typescript
  const handleCardHover = useCallback((id: string | null) => {
    setHighlightedCardId(id)
  }, [])
```

Pass `highlightId={highlightedCardId}` to `RadarMap`:

```tsx
<RadarMap items={allRadarMapItems} highlightId={highlightedCardId}
          onHoverItem={handleMapHover} onPinItem={handleMapPin} />
```

Add `onMouseEnter` and `onMouseLeave` to each card wrapper in the right pane:

```tsx
<div key={item.id} data-radar-id={item.id}
     className={highlightedCardId === item.id ? 'radar-card-highlighted' : ''}
     onMouseEnter={() => handleCardHover(item.id)}
     onMouseLeave={() => handleCardHover(null)}>
```

- [ ] **Step 4: Wire map hover → card scroll in LyraRadarPage**

Update `handleMapHover` to scroll the hovered card into view:

```typescript
  const handleMapHover = useCallback((id: string | null) => {
    setHighlightedCardId(id)
    if (id) {
      const cardEl = document.querySelector(`[data-radar-id="${id}"]`)
      if (cardEl) {
        cardEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    }
  }, [])
```

- [ ] **Step 5: Verify hover sync**

Run: `npx tsc --noEmit`

Expected: No errors. Open `/radar.html` — hover a card and its map dot should glow. Hover a map dot and the corresponding card should scroll into view with a teal border highlight.

- [ ] **Step 6: Commit**

```bash
git add ancient-nerds-map/src/pages/LyraRadarPage.tsx ancient-nerds-map/src/components/RadarMap.tsx
git commit -m "feat(radar): bidirectional hover sync between map dots and card list"
```

---

### Task 4: Data Badges on Cards

Add speculative warning, news category chip, significance bar, and AI reasoning tooltip to RadarCard.

**Files:**
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.tsx`
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.css`

- [ ] **Step 1: Add CSS for new badges**

Add to `LyraRadarPage.css`:

```css
/* Speculative warning badge */
.radar-speculative-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 4px;
}

/* News category chip */
.radar-category-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 500;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.radar-category-chip--fieldwork { color: #60a5fa; background: rgba(96, 165, 250, 0.12); }
.radar-category-chip--analysis { color: #a78bfa; background: rgba(167, 139, 250, 0.12); }
.radar-category-chip--tech { color: #22d3ee; background: rgba(34, 211, 238, 0.12); }
.radar-category-chip--heritage { color: #fbbf24; background: rgba(251, 191, 36, 0.12); }
.radar-category-chip--other { color: #9ca3af; background: rgba(156, 163, 175, 0.12); }

/* Significance bar */
.radar-significance {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}

.radar-significance-bar {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  overflow: hidden;
  max-width: 80px;
}

.radar-significance-fill {
  height: 100%;
  border-radius: 2px;
  background: rgba(78, 205, 196, 0.6);
}

/* AI reasoning tooltip */
.radar-confidence-wrapper {
  position: relative;
  cursor: help;
}

.radar-ai-tooltip {
  display: none;
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.4;
  color: rgba(255, 255, 255, 0.85);
  background: rgba(10, 26, 31, 0.95);
  border: 1px solid rgba(78, 205, 196, 0.3);
  border-radius: 6px;
  white-space: normal;
  max-width: 280px;
  z-index: 10;
  margin-bottom: 4px;
}

.radar-confidence-wrapper:hover .radar-ai-tooltip {
  display: block;
}
```

- [ ] **Step 2: Add category color helper function**

In `LyraRadarPage.tsx`, add a helper function near the other helpers (around line 130):

```typescript
const CATEGORY_GROUPS: Record<string, string> = {
  excavation: 'fieldwork', survey: 'fieldwork', underwater: 'fieldwork',
  artifact: 'analysis', dating: 'analysis', bioarchaeology: 'analysis', epigraphy: 'analysis',
  remote_sensing: 'tech', technology: 'tech', archaeoastronomy: 'tech',
  conservation: 'heritage', heritage: 'heritage', art: 'heritage', architecture: 'heritage',
  theory: 'other', general: 'other', speculative: 'other',
}

function getCategoryGroup(category: string): string {
  return CATEGORY_GROUPS[category] || 'other'
}
```

- [ ] **Step 3: Add speculative badge to RadarCard**

In the `RadarCard` component, after the source badge (around line 290, after the `{item.source && ...}` block), add:

```tsx
      {item.is_speculative && item.speculative_tag && (
        <span className="radar-speculative-badge">
          &#9888; Speculative: {item.speculative_tag.replace(/_/g, ' ')}
        </span>
      )}
```

- [ ] **Step 4: Add news category chip to RadarCard**

After the `<SiteBadges ... />` line (around line 335), add:

```tsx
      {item.top_news_category && item.top_news_category !== 'general' && (
        <span className={`radar-category-chip radar-category-chip--${getCategoryGroup(item.top_news_category)}`}>
          {item.top_news_category.replace(/_/g, ' ')}
        </span>
      )}
```

- [ ] **Step 5: Add significance bar to ScoreBreakdown**

In the `ScoreBreakdown` component (around line 230, after the data sources row), add:

```tsx
      {item.avg_significance != null && (
        <div className="radar-significance">
          <span>Story importance</span>
          <div className="radar-significance-bar">
            <div className="radar-significance-fill"
                 style={{ width: `${(item.avg_significance / 10) * 100}%` }} />
          </div>
          <span>{item.avg_significance}/10</span>
        </div>
      )}
```

Note: `ScoreBreakdown` receives `item` as a prop — it already has access to the full `RadarItem`.

- [ ] **Step 6: Wrap confidence badge with AI reasoning tooltip**

Find where the confidence badge is rendered in `ScoreBreakdown` (around line 200). Wrap it:

```tsx
      {item.confidence && (
        <div className="radar-confidence-wrapper">
          <span className={`lyra-confidence-badge lyra-confidence-${item.confidence}`}>
            {item.confidence}
          </span>
          {item.ai_reasoning && (
            <div className="radar-ai-tooltip">{item.ai_reasoning}</div>
          )}
        </div>
      )}
```

- [ ] **Step 7: Verify badges render**

Run: `npx tsc --noEmit`

Expected: No errors. Open `/radar.html` — cards with speculative sources show a yellow warning badge. Cards show category chips. Score breakdown shows significance bar and hoverable AI reasoning tooltip.

- [ ] **Step 8: Commit**

```bash
git add ancient-nerds-map/src/pages/LyraRadarPage.tsx ancient-nerds-map/src/pages/LyraRadarPage.css
git commit -m "feat(radar): add speculative badge, category chip, significance bar, AI tooltip"
```

---

### Task 5: New Filter Chips

Add category filter and speculative toggle to the floating filter bar on the map.

**Files:**
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.tsx`

- [ ] **Step 1: Add filter state**

Add new state variables alongside the existing filter state:

```typescript
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [hideSpeculative, setHideSpeculative] = useState(false)
```

- [ ] **Step 2: Update fetchRadar to include new params**

Update the `fetchRadar` function to accept and pass the new filters:

```typescript
  const fetchRadar = useCallback(async (
    pageNum: number,
    append: boolean = false,
    mentions: number = minMentions,
    sort: string = sortBy,
    statusParam: string = statusFilter,
    srcParam: string = sourceFilter,
    catParam: string = categoryFilter,
    specParam: boolean = hideSpeculative
  ) => {
    try {
      setLoading(true)
      setError(null)
      const url = `${config.api.baseUrl}/radar/list?page=${pageNum}&page_size=24&min_mentions=${mentions}&sort_by=${sort}&status=${statusParam}&source_filter=${srcParam}&news_category=${catParam}&hide_speculative=${specParam}`
      // ... rest stays the same
```

Add `categoryFilter` and `hideSpeculative` to the `useEffect` dependencies that trigger re-fetch:

```typescript
  useEffect(() => {
    fetchRadar(1, false, minMentions, sortBy, statusFilter, sourceFilter, categoryFilter, hideSpeculative)
  }, [minMentions, sortBy, statusFilter, sourceFilter, categoryFilter, hideSpeculative])
```

- [ ] **Step 3: Add filter chips JSX**

In the floating filters section (inside `radar-map-overlay-filters`), add after the sort filter group:

```tsx
        <div className="lyra-filter-group">
          <span className="lyra-discoveries-filter-label">Category:</span>
          <div className="lyra-discoveries-filter-chips">
            {(['all', 'excavation', 'artifact', 'dating', 'remote_sensing', 'architecture'] as const).map(val => (
              <button key={val}
                className={`news-page-chip${categoryFilter === val ? ' active' : ''}`}
                onClick={() => { setCategoryFilter(val); setItems([]); setPage(1); setHasMore(false) }}>
                {val === 'all' ? 'All' : val.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </div>
        <div className="lyra-filter-group">
          <button
            className={`news-page-chip${hideSpeculative ? ' active' : ''}`}
            onClick={() => { setHideSpeculative(v => !v); setItems([]); setPage(1); setHasMore(false) }}>
            Hide speculative
          </button>
        </div>
```

- [ ] **Step 4: Verify filters work**

Run: `npx tsc --noEmit`

Expected: No errors. Open `/radar.html` — category filter chips appear. Clicking "excavation" reloads with only excavation items. "Hide speculative" toggle works.

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/pages/LyraRadarPage.tsx
git commit -m "feat(radar): add category filter and speculative toggle"
```

---

### Task 6: Map Enhancements

Add score color legend, dot clustering, and client-side filter sync to the map.

**Files:**
- Modify: `ancient-nerds-map/src/components/RadarMap.tsx`
- Modify: `ancient-nerds-map/src/pages/LyraRadarPage.css`

- [ ] **Step 1: Add legend CSS**

Add to `LyraRadarPage.css`:

```css
/* Score legend overlay */
.radar-map-legend {
  position: absolute;
  bottom: 30px;
  left: 10px;
  z-index: 2;
  padding: 8px 12px;
  background: rgba(10, 26, 31, 0.85);
  border: 1px solid rgba(78, 205, 196, 0.2);
  border-radius: 6px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.6);
}

.radar-map-legend-title {
  margin-bottom: 4px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
}

.radar-map-legend-bar {
  width: 120px;
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(to right, hsl(0, 72%, 55%), hsl(40, 72%, 55%), hsl(80, 72%, 55%), hsl(120, 72%, 55%));
}

.radar-map-legend-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 2px;
}
```

- [ ] **Step 2: Add legend to RadarMap return JSX**

In `RadarMap.tsx`, update the return to include a legend child:

```tsx
  return (
    <div className="radar-map-container">
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div className="radar-map-legend">
        <div className="radar-map-legend-title">Enrichment Score</div>
        <div className="radar-map-legend-bar" />
        <div className="radar-map-legend-labels">
          <span>0%</span>
          <span>100%</span>
        </div>
      </div>
      {children}
    </div>
  )
```

- [ ] **Step 3: Enable clustering on the GeoJSON source**

In RadarMap's `map.addSource('radar-sites', ...)` (around line 102), enable clustering:

```typescript
      map.addSource('radar-sites', {
        type: 'geojson',
        data: geojsonRef.current,
        promoteId: 'id',
        cluster: true,
        clusterMaxZoom: 8,
        clusterRadius: 40,
      })
```

Add a cluster layer after the `radar-dots` layer:

```typescript
      map.addLayer({
        id: 'radar-clusters',
        type: 'circle',
        source: 'radar-sites',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': 'rgba(78, 205, 196, 0.6)',
          'circle-radius': ['step', ['get', 'point_count'], 15, 10, 20, 50, 25],
          'circle-stroke-width': 1,
          'circle-stroke-color': 'rgba(78, 205, 196, 0.8)',
        },
      })

      map.addLayer({
        id: 'radar-cluster-count',
        type: 'symbol',
        source: 'radar-sites',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': '{point_count_abbreviated}',
          'text-size': 11,
        },
        paint: {
          'text-color': '#ffffff',
        },
      })
```

Update `radar-dots` to only show unclustered points:

```typescript
      map.addLayer({
        id: 'radar-dots',
        type: 'circle',
        source: 'radar-sites',
        filter: ['!', ['has', 'point_count']],
        // ... rest stays the same
```

Add the same `filter: ['!', ['has', 'point_count']]` to `radar-glow` layer.

Add click handler for clusters to zoom in:

```typescript
      map.on('click', 'radar-clusters', (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ['radar-clusters'] })
        const clusterId = features[0]?.properties?.cluster_id
        if (clusterId != null) {
          const source = map.getSource('radar-sites') as mapboxgl.GeoJSONSource
          source.getClusterExpansionZoom(clusterId, (err, zoom) => {
            if (err || zoom == null) return
            map.easeTo({
              center: (features[0].geometry as GeoJSON.Point).coordinates as [number, number],
              zoom,
            })
          })
        }
      })
```

- [ ] **Step 4: Add filter sync via prop**

Add a `filterFn` prop to RadarMap:

```typescript
interface RadarMapProps {
  items: RadarMapItem[]
  highlightId?: string | null
  filterFn?: (item: RadarMapItem) => boolean
  onHoverItem?: (id: string | null) => void
  onPinItem?: (id: string | null) => void
  children?: ReactNode
}
```

Update `geojsonRef` to apply the filter:

```typescript
  const filteredItems = filterFn ? items.filter(filterFn) : items
  geojsonRef.current = buildGeoJSON(filteredItems)
```

In `LyraRadarPage.tsx`, pass a filter function to RadarMap that matches the active UI filters:

```tsx
  const mapFilterFn = useCallback((item: RadarMapItem) => {
    if (statusFilter !== 'all' && item.enrichment_status !== statusFilter) return false
    return true
  }, [statusFilter])

  <RadarMap items={allRadarMapItems} highlightId={highlightedCardId}
            filterFn={mapFilterFn}
            onHoverItem={handleMapHover} onPinItem={handleMapPin} />
```

Note: The map items (`RadarMapItem`) don't have `news_category` or `is_speculative` — those come from the `/list` endpoint's `video_agg`. Client-side filtering on the map is limited to `enrichment_status` for now. Category and speculative filtering happen server-side via the API.

- [ ] **Step 5: Verify map enhancements**

Run: `npx tsc --noEmit`

Expected: No errors. Open `/radar.html` — score legend visible bottom-left. At low zoom, dots cluster into numbered circles. Clicking a cluster zooms in. Status filter affects map dots.

- [ ] **Step 6: Commit**

```bash
git add ancient-nerds-map/src/components/RadarMap.tsx ancient-nerds-map/src/pages/LyraRadarPage.css
git commit -m "feat(radar): add score legend, dot clustering, and filter sync to map"
```

---

## Execution Order

Tasks must be executed in order (1 → 2 → 3 → 4 → 5 → 6) due to dependencies:
- Task 1 (API) must complete before Task 2 (new fields in types)
- Task 2 (layout) must complete before Task 3 (hover sync needs split-view)
- Task 4 (badges) depends on Task 2 (new fields in RadarItem)
- Task 5 (filters) depends on Task 1 (API params) and Task 2 (layout)
- Task 6 (map enhancements) depends on Task 2 (always-on map) and Task 3 (highlightId prop)
