# Radar Map-First Redesign

**Date**: 2026-04-12
**Status**: Draft

## Context

The Radar tracks archaeological sites Lyra discovers in YouTube videos that aren't yet in the main database. The current layout is a card grid with an optional map toggle — most users never see the Mapbox sweep animation that defines the feature's identity. Meanwhile, the pipeline produces rich metadata (significance scores, news categories, speculative tags, AI reasoning) that never reaches the frontend.

This redesign makes the map the permanent primary interface, surfaces unused pipeline data, and improves the map itself.

## 1. Split-View Layout

### Structure
- **Left pane (60%)**: Mapbox globe with sweep animation, always visible
- **Right pane (40%)**: Scrollable card list with full-size cards (same design as current RadarCards)
- **No map toggle button** — map is always present

### Floating overlays on the map pane
- **Filter chips**: Top of map, horizontal row (status, category, speculative toggle, min mentions, sort)
- **Stats bar**: Below filters (enriched / pending / added / known sites)
- **Lyra avatar + speech bubble**: Top-left corner overlay

### Hover sync
- Hover a card in the list → its map dot glows with a pulsing ring
- Hover a map dot → corresponding card scrolls into view in the right pane and gets a subtle border highlight
- Click a map dot → card scrolls into view and expands (if collapsibles exist)
- Deselect by clicking empty map space or scrolling away

### Mobile layout (<768px)
- Map fills the viewport
- Card list becomes a bottom sheet with a drag handle
- Pull up to browse cards, pull down to see map
- Filters stay floating on top of the map

### Component changes
- `LyraRadarPage.tsx`: Replace grid-only layout with split-view container
- `RadarMap.tsx`: Stays mostly as-is (already has hover/click callbacks). Add `onDotHover` and `onDotClick` props for sync.
- New: CSS for split-view layout, bottom sheet on mobile

### Files to modify
- `ancient-nerds-map/src/pages/LyraRadarPage.tsx` — layout restructure
- `ancient-nerds-map/src/pages/LyraRadarPage.css` — split-view CSS + mobile bottom sheet
- `ancient-nerds-map/src/components/RadarMap.tsx` — sync event props

## 2. Pipeline Data Surfacing

### New API fields

Add to the `video_agg` CTE in `api/routes/radar.py`:

| Field | SQL | Purpose |
|---|---|---|
| `avg_significance` | `AVG(ni.significance) FILTER (WHERE ni.significance IS NOT NULL)` | Average story importance (1-10) |
| `top_news_category` | `MODE() WITHIN GROUP (ORDER BY ni.news_category) FILTER (WHERE ni.news_category IS NOT NULL)` | Most common category |
| `is_speculative` | `BOOL_OR(ni.speculative_tag IS NOT NULL)` | Any speculative source? |
| `speculative_tag` | `(ARRAY_AGG(ni.speculative_tag) FILTER (WHERE ni.speculative_tag IS NOT NULL))[1]` | Which speculative type |

Add from `enrichment_data` unpacking in `_row_to_item()`:

| Field | Source | Purpose |
|---|---|---|
| `ai_reasoning` | `enrichment_data["identification"]["reasoning"]` | Why Lyra identified this as a site |

### New frontend elements on RadarCard

1. **Speculative warning badge** — Yellow warning badge after source badge: "Speculative: Lost Civilization". Only shown when `is_speculative` is true.

2. **News category badge** — Chip next to site_type badge showing `top_news_category` (e.g., "excavation", "artifact", "dating"). Color-coded by group:
   - Fieldwork (excavation, survey, underwater): blue
   - Analysis (artifact, dating, bioarchaeology, epigraphy): purple
   - Technology (remote_sensing, technology, archaeoastronomy): cyan
   - Heritage (conservation, heritage, art, architecture): amber
   - Other (theory, general): gray

3. **Significance indicator** — Small filled bar (1-10 scale) below the enrichment score section. Label: "Story importance".

4. **AI reasoning tooltip** — Hover the confidence badge in the score breakdown to see `ai_reasoning` as a tooltip.

### New filters

- **Category filter chip**: Dropdown/chip selecting news_category (or "All")
- **Hide speculative toggle**: Filter chip that excludes `is_speculative = true` items

### API query parameter additions
- `news_category` (string, optional): Filter applied as a HAVING clause on the video_agg CTE — keeps only contributions whose most-mentioned news_category matches the parameter
- `hide_speculative` (bool, default false): Filter applied as a HAVING clause — excludes contributions where any linked news_item has a non-null speculative_tag

### Files to modify
- `api/routes/radar.py` — CTE additions, response dict additions, new query params
- `ancient-nerds-map/src/pages/LyraRadarPage.tsx` — new badges, tooltip, filters, RadarItem type

## 3. Map Improvements

### Score color legend
- Floating element in bottom-left corner of the map pane
- Small horizontal gradient bar: red → yellow → green
- Labels: "0%" on left, "100%" on right
- Title: "Enrichment Score"
- Semi-transparent dark background, matches existing map overlay style

### Dot clustering
- Enable Mapbox GL built-in clustering at zoom levels where dots overlap
- Cluster circles show count number
- Click cluster to zoom in and expand
- Uses `clusterMaxZoom: 8` and `clusterRadius: 40`

### Active dot highlight
- When a card is hovered in the right pane, the corresponding dot gets:
  - Larger radius (5px → 10px)
  - Pulsing ring animation (reuse existing glow system with `radar-glow` layer)
  - Z-index boost (rendered on top of other dots)

### Filter sync
- When filters change in the chip bar, update the GeoJSON source on the map to match
- Currently the map loads all items once via `/radar/map` and never re-filters
- New behavior: Apply client-side filtering to the loaded GeoJSON features based on active filters (status, category, speculative)
- No additional API calls needed — filter the already-loaded data

### Files to modify
- `ancient-nerds-map/src/components/RadarMap.tsx` — clustering config, legend overlay, filter sync, active dot highlight
- `ancient-nerds-map/src/pages/LyraRadarPage.css` — legend styling

## Files Summary

| File | Changes |
|---|---|
| `api/routes/radar.py` | Add 5 fields to video_agg CTE, unpack ai_reasoning, add 2 query params |
| `ancient-nerds-map/src/pages/LyraRadarPage.tsx` | Split-view layout, new badges/filters/tooltips, hover sync wiring, RadarItem type |
| `ancient-nerds-map/src/pages/LyraRadarPage.css` | Split-view CSS, mobile bottom sheet, legend styling, hover highlight |
| `ancient-nerds-map/src/components/RadarMap.tsx` | Clustering, legend, filter sync, active dot highlight, sync event props |

## Verification

1. **Layout**: Open `/radar.html` — map should fill left 60%, cards right 40%. Resize to <768px — should switch to map + bottom sheet.
2. **Hover sync**: Hover a card → dot glows on map. Hover a dot → card scrolls into view with highlight.
3. **Data**: Hit `GET /api/radar/list` — response should include `avg_significance`, `top_news_category`, `is_speculative`, `speculative_tag`, `ai_reasoning`.
4. **Badges**: Cards show speculative warning (if applicable), category chip, significance bar.
5. **AI tooltip**: Hover confidence badge → shows reasoning text.
6. **Filters**: Category filter and speculative toggle work correctly and also filter map dots.
7. **Map**: Score legend visible. Dots cluster at low zoom. Active dot pulses on hover.
