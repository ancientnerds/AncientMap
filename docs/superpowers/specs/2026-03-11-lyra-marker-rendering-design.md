# Lyra Marker Rendering Fixes — Design Spec

**Date:** 2026-03-11
**Status:** Approved

## Problem

Lyra's structured output markers render poorly in chat:
- Video embeds show as plain text links instead of expandable YouTube players
- Video index mismatch between backend (`all_news` enumerate) and frontend (dedup merge) causes `sidebarNewsRef[idx]` lookups to fail → falls back to plain `<span>`
- Site hover preview doesn't show hero image (compact mode hides it)
- No hover preview for news/video items
- Coordinates fly to globe but don't activate proximity mode
- LLM outputs redundant markers (both `«vN»` and `«lN»` for same video)
- LLM adds unnecessary wrapper text ("Video:", "Link:", "Koordinaten:", "Land:")
- Empire links are dead `<span>` elements with no styling

## Changes

### 1. Video protocol: index → video_id (backend + frontend)

**Backend** (`lyra_schema.py` `expand_markers()`):
- Change `lyra-video:INDEX` → `lyra-video:VIDEO_ID:TIMESTAMP`
- No more `news_index` dict needed — embed the video_id directly in the protocol

**Frontend** (`LyraChatModal.tsx` `mdComponents.a`):
- Parse `lyra-video:VIDEO_ID:TIMESTAMP` protocol
- Look up news item by `video_id` from `sidebarNewsRef.current` using `.find()` instead of array index
- If not found in sidebarNews, construct a minimal `NewsHighlight` from the URL params so the embed still works

### 2. Video hover → NewsCard preview

**Component** (`LyraChatModal.tsx` `LyraInlineVideo`):
- Add hover state with 300ms show delay, 200ms hide delay (same pattern as SiteChip)
- On hover, show `NewsCard` (size="sm") positioned above the button
- Reuse `newsHighlightToCardProps()` adapter already exported from NewsCard

### 3. SiteCard compact shows hero image

**Component** (`SiteCard.tsx`):
- In compact mode, keep rendering the hero image section
- Only hide: description, footer, copy buttons (already hidden)
- The hero image makes the hover preview visually useful

### 4. Coord fly-to activates proximity

**Backend** (no change needed):
- `lyra-coord:` protocol already works

**Frontend** (`LyraChatModal.tsx` coord handler + `App.tsx` message handler):
- Add `activateProximity: true` field to the `fly-to-coords` postMessage
- In `App.tsx` handler: after setting `flyToCoords`, also set proximity state if the flag is true
- The `onFlyToSite` callback path: add optional proximity param, wire through from App

### 5. Redundant marker fix (backend prompts)

**File** (`lyra_tool_prompts.py`):
- `search_news` instruction: add "Do NOT create «lN» link markers for videos that already have «vN» markers."
- All tool instructions: add "Do not prefix markers with labels like 'Video:', 'Link:', 'Koordinaten:', 'Land:' — markers render as interactive UI elements, labels are redundant."

### 6. Empire links styled as badges

**Frontend** (`LyraChatModal.tsx` + `index.css`):
- Style `.lyra-empire-link` as a colored inline badge (amber/gold tone to differentiate from cyan site chips)
- Add a small crown/shield icon before the text
- No hover/click behavior — purely visual for now

## Files to modify

| File | Change |
|------|--------|
| `api/services/lyra_schema.py` | Video marker: index → `VIDEO_ID:TIMESTAMP` protocol |
| `api/services/lyra_tool_prompts.py` | Anti-redundancy instructions for all tools |
| `ancient-nerds-map/src/components/LyraChatModal.tsx` | Video protocol parser, video hover preview, coord proximity flag, empire badge |
| `ancient-nerds-map/src/components/SiteCard.tsx` | Show hero image in compact mode |
| `ancient-nerds-map/src/components/lyra/SiteChip.tsx` | No changes needed (already works) |
| `ancient-nerds-map/src/styles/index.css` | Video hover preview CSS, empire badge CSS |
| `ancient-nerds-map/src/utils/globeNavigation.ts` | Add proximity flag to postMessage |
| App.tsx message handler | Handle proximity activation on fly-to |
