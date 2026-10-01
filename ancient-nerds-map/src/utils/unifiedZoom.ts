/**
 * The globe's one zoom value: the slider, 0-100 %. 0-65 is the Three.js globe,
 * 66-100 the Mapbox map.
 *
 * In Mapbox mode the slider is anchored to the zoom the map had when it was
 * entered (its "base", as a percent of the Mapbox range below): 66 % is that
 * zoom, 100 % is street level. The wheel and the slider go slider -> map
 * (mapboxPercentForSlider); a finger pinch on the map goes map -> slider
 * (sliderForMapboxZoom), so pinching out past the entry zoom returns the 3D
 * globe (2026-10-01: until then a pinch zoomed only the map, the slider stayed
 * at 66 % and the globe never came back).
 */

/** Slider value at and above which Mapbox shows the map. */
export const MAPBOX_SWITCH_PERCENT = 66

/** Mapbox zoom levels the 0-100 % map scale spans (MapboxGlobeService). */
export const MAPBOX_PERCENT_ZOOM = { MIN: 0.7, MAX: 18 } as const

/** A Mapbox zoom level as a percent of MAPBOX_PERCENT_ZOOM, unrounded. */
export function mapboxZoomToPercent(mapboxZoom: number): number {
  return ((mapboxZoom - MAPBOX_PERCENT_ZOOM.MIN) / (MAPBOX_PERCENT_ZOOM.MAX - MAPBOX_PERCENT_ZOOM.MIN)) * 100
}

/** Slider (66-100) -> Mapbox zoom percent, starting from the entry zoom's percent. */
export function mapboxPercentForSlider(slider: number, basePercent: number): number {
  const sliderProgress = (slider - MAPBOX_SWITCH_PERCENT) / (100 - MAPBOX_SWITCH_PERCENT)
  return Math.min(100, basePercent + sliderProgress * (100 - basePercent))
}

/**
 * The Mapbox zoom at which two points measured `measuredPx` apart at `currentZoom`
 * end up `targetPx` apart: one zoom level doubles every on-screen distance.
 */
export function zoomForSpan(currentZoom: number, measuredPx: number, targetPx: number): number {
  return currentZoom + Math.log2(targetPx / measuredPx)
}

/** The slider value (whole percent, 0-100) a finger zoom of the map to `mapboxZoom` stands for. */
export function sliderAfterTouchZoom(mapboxZoom: number, basePercent: number): number {
  return Math.max(0, Math.min(100, Math.round(sliderForMapboxZoom(mapboxZoom, basePercent))))
}

/** Mapbox zoom -> slider value; below the entry zoom it is below 66. Unrounded. */
export function sliderForMapboxZoom(mapboxZoom: number, basePercent: number): number {
  const progress = (mapboxZoomToPercent(mapboxZoom) - basePercent) / (100 - basePercent)
  return MAPBOX_SWITCH_PERCENT + progress * (100 - MAPBOX_SWITCH_PERCENT)
}
