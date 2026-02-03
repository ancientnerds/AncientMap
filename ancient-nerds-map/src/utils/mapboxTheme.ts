/**
 * Shared Mapbox theming utilities
 * Used by both MapboxGlobeService and EmpireMinimap for consistent styling
 */

import type { Map as MapboxMap } from 'mapbox-gl'

/**
 * Apply dark teal/green haze theme to Mapbox map layers
 * This creates the distinctive look that matches the Three.js globe
 */
export function applyDarkTealTheme(map: MapboxMap): void {
  // Land - dark teal/green tint
  if (map.getLayer('land')) {
    map.setPaintProperty('land', 'background-color', 'rgb(8, 32, 28)')
  }

  // Water - darker teal
  if (map.getLayer('water')) {
    map.setPaintProperty('water', 'fill-color', 'rgb(4, 18, 16)')
  }

  // Background - very dark
  if (map.getLayer('background')) {
    map.setPaintProperty('background', 'background-color', 'rgb(4, 18, 16)')
  }

  // Landuse layers - subtle teal tints
  const landuseColors: Record<string, string> = {
    'landuse': 'rgb(10, 36, 32)',
    'landcover': 'rgb(12, 40, 35)',
  }

  for (const [layerId, color] of Object.entries(landuseColors)) {
    if (map.getLayer(layerId)) {
      map.setPaintProperty(layerId, 'fill-color', color)
    }
  }

  // For outdoors style (if used) - style terrain/hillshade layers with teal tint
  if (map.getLayer('contour')) {
    map.setPaintProperty('contour', 'line-color', 'rgba(0, 224, 208, 0.15)')
  }

  if (map.getLayer('hillshade')) {
    map.setPaintProperty('hillshade', 'hillshade-shadow-color', 'rgb(4, 18, 16)')
    map.setPaintProperty('hillshade', 'hillshade-highlight-color', 'rgba(0, 224, 208, 0.1)')
  }
}

/**
 * Set up fog for globe projection with dark teal theme
 */
export function setupDarkFog(map: MapboxMap): void {
  map.setFog({
    color: 'rgb(10, 10, 20)',
    'high-color': 'rgb(20, 20, 40)',
    'horizon-blend': 0.02,
    'space-color': 'rgb(5, 5, 10)',
    'star-intensity': 0.0
  })
}

/**
 * Convert hex color number to CSS rgba string
 */
export function hexToRgba(hex: number, alpha: number): string {
  const r = (hex >> 16) & 255
  const g = (hex >> 8) & 255
  const b = hex & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * Convert hex color number to CSS hex string
 */
export function hexToString(hex: number): string {
  return '#' + hex.toString(16).padStart(6, '0')
}
