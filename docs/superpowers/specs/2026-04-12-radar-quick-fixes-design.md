# Radar Quick Fixes — Design Spec

**Date**: 2026-04-12  
**Status**: Draft  
**Scope**: Three surgical fixes to the Radar feature

## Context

The Radar tracks archaeological sites discovered from YouTube videos. Three issues undermine its usefulness:

1. **Missing images** — Many cards show nothing because `thumbnail_url` (Wikidata/Wikipedia) is null for obscure sites
2. **All green scores** — The enrichment score formula gives 75/100 minimum for typical enriched items; HSL color mapping makes everything look green
3. **Wrong sites extracted** — The pipeline picks up natural landmarks (Grand Canyon) and tourist spots instead of filtering for genuinely ancient sites

## Fix 1: Image Fallback

**Fallback chain**: Wikipedia/Wikidata site image → Story screenshot from relevant video timestamp → nothing.

The pipeline already extracts `screenshot_url` on `NewsItem` — a frame from the YouTube video at the timestamp where the site was discussed. This is contextually relevant (shows the actual video moment) and already in the database. We add it to the Radar API response and use it as fallback when `thumbnail_url` is null.

No YouTube generic video thumbnail — those could show anything from the video, not the specific site.

### API Change (`api/routes/radar.py`)
- Add `latest_screenshot_url` to the `video_agg` CTE via `ARRAY_AGG(ni.screenshot_url ORDER BY ni.created_at DESC) FILTER (WHERE ni.screenshot_url IS NOT NULL))[1]`
- Include in main SELECT and response dict

### Frontend Change (`LyraRadarPage.tsx`)
- Add `screenshot_url` to `RadarItem` type
- Render image when `thumbnail_url || screenshot_url` is truthy
- `LazyImage` src uses `thumbnail_url || screenshot_url`

## Fix 2: Score Color Differentiation

**Root cause**: Linear HSL mapping (`hue = pct/100 * 120`) maps the 75-85% cluster to hues 90-102 (all green).

**Fix**: Power curve `hue = Math.pow(pct/100, 2.5) * 120` spreads the common range:
- 50% → hue 21 (orange-red)
- 75% → hue 58 (yellow)
- 85% → hue 80 (yellow-green)
- 95% → hue 106 (green)
- 100% → hue 120 (full green)

Applied in both `scoreColor()` (card list) and `scoreToColor()` (map dots).

The enrichment score formula itself is unchanged — it correctly tracks metadata completeness for the promotion workflow.

## Fix 3: Tighter Site Extraction Prompts

Two prompts need explicit exclusion rules.

### `summary.txt` — New primary_site rules
- Do NOT extract natural landmarks, geographic features, or national parks (e.g., Grand Canyon, Niagara Falls)
- Do NOT extract modern cities unless discussing the ancient settlement specifically
- Site must be primarily known as an archaeological/historical site built or modified by ancient humans

### `identify_site.txt` — Tightened definition + rejection block
- Definition change: "primarily known for archaeological remains that were built or significantly modified by ancient humans"
- Explicit rejections: natural features, caves without archaeological significance, national parks, modern tourist attractions, living cities (unless referencing specific ancient ruins within)
- Key test: "Is this place primarily known for its archaeological significance, not its natural beauty or modern function?"

### Scope
Only affects future pipeline runs. Existing false positives in `user_contributions` are unaffected.

## Files Modified
| File | Fix |
|------|-----|
| `api/routes/radar.py` | 1 |
| `ancient-nerds-map/src/pages/LyraRadarPage.tsx` | 1, 2 |
| `ancient-nerds-map/src/components/RadarMap.tsx` | 2 |
| `pipeline/lyra/prompts/summary.txt` | 3 |
| `pipeline/lyra/prompts/identify_site.txt` | 3 |
