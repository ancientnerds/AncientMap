// =============================================================================
// MAPBOX CONSTANTS - Configuration for satellite imagery and dark basemap
// =============================================================================

/**
 * Mapbox access token from environment variable
 * Get your free token at: https://account.mapbox.com/access-tokens/
 */
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || ''

if (!MAPBOX_TOKEN) {
  console.warn('[Mapbox] No access token configured. Set VITE_MAPBOX_ACCESS_TOKEN in .env file.')
}

/**
 * Get the Mapbox token
 */
export function getMapboxToken(): string {
  return MAPBOX_TOKEN
}

/**
 * Token rotation removed - use single token from environment
 * @deprecated No longer needed with single token approach
 */
export function rotateMapboxToken(): boolean {
  console.warn('[Mapbox] Token rotation deprecated - configure VITE_MAPBOX_ACCESS_TOKEN in .env')
  return false
}

/**
 * Mapbox API configuration
 */
export const MAPBOX = {
  get ACCESS_TOKEN() { return getMapboxToken() },
  TILE_SIZE: 512,           // Mapbox tiles are 512x512 at @2x
  MAX_ZOOM: 18,             // Maximum Mapbox zoom level
  MIN_ZOOM: 0,              // Minimum zoom for tiles (full globe view)
  MAX_CONCURRENT_REQUESTS: 6,  // Browser limit per domain
  MAX_CACHE_MB: 256,        // Maximum cache size in megabytes
  MAX_CACHED_TILES: 200,    // Maximum number of tiles in memory
  REQUEST_DELAY_MS: 50,     // Delay between tile requests to avoid rate limiting
} as const

/**
 * Extended camera settings for Mapbox mode
 * Allows zooming beyond the normal 100% to see satellite detail
 */
export const CAMERA_EXTENDED = {
  MIN_DISTANCE: 0.20,             // Extended minimum camera distance for satellite (230% zoom)
  STANDARD_MIN_DISTANCE: 1.12,    // Standard minimum without satellite (100% zoom)
} as const

/**
 * Mapbox tile URLs
 */

// Satellite imagery (raster tiles)
export function getSatelliteTileUrl(z: number, x: number, y: number): string {
  return `https://api.mapbox.com/v4/mapbox.satellite/${z}/${x}/${y}@2x.jpg?access_token=${MAPBOX.ACCESS_TOKEN}`
}

// Dark style (vector-based raster tiles)
export function getDarkTileUrl(z: number, x: number, y: number): string {
  return `https://api.mapbox.com/styles/v1/mapbox/dark-v11/tiles/512/${z}/${x}/${y}@2x?access_token=${MAPBOX.ACCESS_TOKEN}`
}

// Terrain DEM (for 3D elevation)
export function getDemTileUrl(z: number, x: number, y: number): string {
  return `https://api.mapbox.com/v4/mapbox.mapbox-terrain-dem-v1/${z}/${x}/${y}.pngraw?access_token=${MAPBOX.ACCESS_TOKEN}`
}

/**
 * Decode Mapbox terrain RGB elevation value
 * height = -10000 + ((R * 256 * 256 + G * 256 + B) * 0.1)
 *
 * @param r Red channel (0-255)
 * @param g Green channel (0-255)
 * @param b Blue channel (0-255)
 * @returns Height in meters
 */
export function decodeMapboxElevation(r: number, g: number, b: number): number {
  return -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)
}

/**
 * Tile mesh radius offset (slightly above basemap to prevent z-fighting)
 */
export const TILE_RADIUS_OFFSET = 1.0016  // Basemap is at 1.0015
