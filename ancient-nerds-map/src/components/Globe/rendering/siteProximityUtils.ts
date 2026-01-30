/**
 * siteProximityUtils.ts - Utilities for detecting proximity to site dots
 *
 * Used to:
 * 1. Prioritize site clicks/hovers over empire interactions
 * 2. Create dead zones around site dots for empire hover/click detection
 */

import * as THREE from 'three'
import type { SiteData } from '../../../data/sites'

/** Default dead zone radius around site dots (in screen pixels) */
export const SITE_DEAD_ZONE_RADIUS = 15

/** Result of a site proximity check */
export interface SiteProximityResult {
  /** The nearest site within the search radius, or null if none */
  nearestSite: SiteData | null
  /** Screen distance to the nearest site in pixels */
  screenDistance: number
  /** Whether the cursor is within the dead zone of any site */
  isInDeadZone: boolean
}

/**
 * Check if a screen position is near any visible site dot
 *
 * @param screenX - Screen X coordinate (pixels)
 * @param screenY - Screen Y coordinate (pixels)
 * @param camera - Three.js camera for projection
 * @param sites - Array of site data
 * @param searchRadius - Maximum screen distance to search (pixels)
 * @param deadZoneRadius - Radius for dead zone detection (pixels)
 * @returns SiteProximityResult with nearest site and dead zone status
 */
export function checkSiteProximity(
  screenX: number,
  screenY: number,
  camera: THREE.PerspectiveCamera,
  sites: SiteData[],
  searchRadius: number = 10,
  deadZoneRadius: number = SITE_DEAD_ZONE_RADIUS
): SiteProximityResult {
  const cameraPos = camera.position.clone().normalize()
  let nearestSite: SiteData | null = null
  let nearestScreenDist = Infinity

  for (const site of sites) {
    if (!site?.coordinates) continue

    const [lng, lat] = site.coordinates
    const phi = (90 - lat) * Math.PI / 180
    const theta = (lng + 180) * Math.PI / 180
    const r = 1.002

    const sitePos = new THREE.Vector3(
      -r * Math.sin(phi) * Math.cos(theta),
      r * Math.cos(phi),
      r * Math.sin(phi) * Math.sin(theta)
    )

    // Only check front-facing sites
    if (sitePos.clone().normalize().dot(cameraPos) <= 0) continue

    // Project to screen coordinates
    const projectedPos = sitePos.clone().project(camera)
    const siteScreenX = (projectedPos.x + 1) / 2 * window.innerWidth
    const siteScreenY = (-projectedPos.y + 1) / 2 * window.innerHeight

    const screenDist = Math.sqrt(
      (screenX - siteScreenX) ** 2 + (screenY - siteScreenY) ** 2
    )

    if (screenDist < nearestScreenDist) {
      nearestScreenDist = screenDist
      if (screenDist <= searchRadius) {
        nearestSite = site
      }
    }
  }

  return {
    nearestSite,
    screenDistance: nearestScreenDist,
    isInDeadZone: nearestScreenDist <= deadZoneRadius
  }
}

/**
 * Check if click/hover should be blocked by a nearby site (dead zone check)
 * Use this before processing empire interactions
 */
export function isInSiteDeadZone(
  screenX: number,
  screenY: number,
  camera: THREE.PerspectiveCamera,
  sites: SiteData[],
  deadZoneRadius: number = SITE_DEAD_ZONE_RADIUS
): boolean {
  const result = checkSiteProximity(screenX, screenY, camera, sites, 0, deadZoneRadius)
  return result.isInDeadZone
}
