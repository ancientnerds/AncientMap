/**
 * Highlighted Sites Renderer Module
 *
 * Handles rendering of highlighted site indicators (ring sprites) when sites
 * are selected from the search/proximity list or hovered.
 *
 * Extracted from Globe.tsx to reduce file size and improve maintainability.
 */

import * as THREE from 'three'
import type { SiteData } from '../../../data/sites'
import type { MapboxGlobeService } from '../../../services/MapboxGlobeService'

// ============================================================================
// Types
// ============================================================================

export interface HighlightedSitesContext {
  globe: THREE.Mesh
  camera: THREE.PerspectiveCamera
  highlightGlowsRef: React.MutableRefObject<THREE.Sprite[]>
  validSitesRef: React.MutableRefObject<SiteData[]>
  listHighlightedPositionsRef: React.MutableRefObject<Map<string, { x: number; y: number }>>
}

export interface HighlightedSitesOptions {
  highlightedSiteId: string | null | undefined
  listFrozenSiteIds: string[]
  showMapbox: boolean
  mapboxService: MapboxGlobeService | null
}

export interface HighlightedSitesResult {
  visibleSites: SiteData[]
  positions: Map<string, { x: number; y: number }>
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Create a ring texture for site highlight indicators
 */
function createRingTexture(): THREE.CanvasTexture {
  const ringCanvas = document.createElement('canvas')
  ringCanvas.width = 64
  ringCanvas.height = 64
  const ctx = ringCanvas.getContext('2d')!

  // Draw lime green ring
  ctx.strokeStyle = '#32CD32'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.arc(32, 32, 24, 0, Math.PI * 2)
  ctx.stroke()

  // Add subtle outer glow
  ctx.strokeStyle = 'rgba(50, 205, 50, 0.4)'
  ctx.lineWidth = 6
  ctx.beginPath()
  ctx.arc(32, 32, 27, 0, Math.PI * 2)
  ctx.stroke()

  return new THREE.CanvasTexture(ringCanvas)
}

/**
 * Convert lat/lng to 3D position on globe
 */
function latLngToPosition(lat: number, lng: number, r: number = 1.002): THREE.Vector3 {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  )
}

/**
 * Project 3D position to screen coordinates
 */
function projectToScreen(position: THREE.Vector3, camera: THREE.Camera): { x: number; y: number } {
  const projected = position.clone().project(camera)
  return {
    x: (projected.x + 1) / 2 * window.innerWidth,
    y: (-projected.y + 1) / 2 * window.innerHeight
  }
}

// ============================================================================
// Main Functions
// ============================================================================

/**
 * Clean up existing highlight glows
 */
export function cleanupHighlightGlows(
  globe: THREE.Mesh | null | undefined,
  highlightGlowsRef: React.MutableRefObject<THREE.Sprite[]>
): void {
  if (!globe) return

  for (const glow of highlightGlowsRef.current) {
    globe.remove(glow)
    glow.material.dispose()
  }
  highlightGlowsRef.current = []
}

/**
 * Render highlighted sites in Mapbox mode
 * Returns screen positions for tooltips
 */
export function renderHighlightedSitesMapbox(
  options: HighlightedSitesOptions,
  validSites: SiteData[],
  listFrozenSiteIds: string[],
  existingPositions: Map<string, { x: number; y: number }>
): HighlightedSitesResult {
  const { highlightedSiteId, mapboxService } = options

  // Combine frozen sites with hovered site
  const activeSiteIds = listFrozenSiteIds.length > 0
    ? (highlightedSiteId && !listFrozenSiteIds.includes(highlightedSiteId)
        ? [...listFrozenSiteIds, highlightedSiteId]
        : listFrozenSiteIds)
    : (highlightedSiteId ? [highlightedSiteId] : [])

  const visibleSites: SiteData[] = []
  const positions = new Map<string, { x: number; y: number }>()

  if (!mapboxService?.getIsInitialized()) {
    return { visibleSites, positions }
  }

  for (const siteId of activeSiteIds) {
    const site = validSites.find(s => s.id === siteId)
    if (!site) continue

    const [lng, lat] = site.coordinates
    const screenPos = mapboxService.projectToScreen(lng, lat)
    const isSelected = listFrozenSiteIds.includes(siteId)

    if (screenPos) {
      visibleSites.push(site)
      positions.set(site.id, screenPos)
    } else if (isSelected) {
      // Selected sites stay visible - use existing position as fallback
      const existingPos = existingPositions.get(siteId)
      if (existingPos) {
        visibleSites.push(site)
        positions.set(site.id, existingPos)
      }
    }
  }

  return { visibleSites, positions }
}

/**
 * Render highlighted sites in Three.js mode
 * Creates ring sprites and returns screen positions for tooltips
 */
export function renderHighlightedSitesThreeJS(
  ctx: HighlightedSitesContext,
  options: HighlightedSitesOptions
): HighlightedSitesResult {
  const { globe, camera, highlightGlowsRef, validSitesRef, listHighlightedPositionsRef } = ctx
  const { highlightedSiteId, listFrozenSiteIds } = options

  // Combine frozen sites with hovered site
  const activeSiteIds = listFrozenSiteIds.length > 0
    ? (highlightedSiteId && !listFrozenSiteIds.includes(highlightedSiteId)
        ? [...listFrozenSiteIds, highlightedSiteId]
        : listFrozenSiteIds)
    : (highlightedSiteId ? [highlightedSiteId] : [])

  const visibleSites: SiteData[] = []
  const positions = new Map<string, { x: number; y: number }>()

  if (activeSiteIds.length === 0) {
    return { visibleSites, positions }
  }

  const cameraDir = camera.position.clone().normalize()
  const ringTexture = createRingTexture()

  for (const siteId of activeSiteIds) {
    const site = validSitesRef.current.find(s => s.id === siteId)
    if (!site) continue

    const [lng, lat] = site.coordinates
    const sitePos = latLngToPosition(lat, lng)

    // Check if site is on front side
    const isOnFront = sitePos.clone().normalize().dot(cameraDir) > 0
    const isSelected = listFrozenSiteIds.includes(siteId)

    // Skip non-selected sites on back of globe
    if (!isOnFront && !isSelected) {
      continue
    }

    visibleSites.push(site)

    // Only add ring marker if site is on front
    if (isOnFront) {
      // Create ring sprite
      const ringMaterial = new THREE.SpriteMaterial({
        map: ringTexture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
      })
      const ringSprite = new THREE.Sprite(ringMaterial)
      ringSprite.position.copy(sitePos)
      ringSprite.scale.set(0.025, 0.025, 1)
      ringSprite.renderOrder = 25
      globe.add(ringSprite)
      highlightGlowsRef.current.push(ringSprite)

      // Project to screen
      const screenPos = projectToScreen(sitePos, camera)
      positions.set(site.id, screenPos)
    } else if (isSelected) {
      // Selected site on back - use existing position as fallback
      const existingPos = listHighlightedPositionsRef.current.get(site.id)
      if (existingPos) {
        positions.set(site.id, existingPos)
      } else {
        // Default to center of screen
        positions.set(site.id, { x: window.innerWidth / 2, y: 100 })
      }
    }
  }

  return { visibleSites, positions }
}

/**
 * Calculate tooltip position for a highlighted site
 */
export function calculateSiteTooltipPosition(
  site: SiteData,
  camera: THREE.PerspectiveCamera
): { x: number; y: number } {
  const [lng, lat] = site.coordinates
  const sitePos = latLngToPosition(lat, lng)
  return projectToScreen(sitePos, camera)
}
