/**
 * Sites Renderer Module
 *
 * Handles rendering of archaeological site dots on the Three.js globe.
 * Creates front/back point clouds with shader materials for visibility effects.
 *
 * Extracted from Globe.tsx to reduce file size and improve maintainability.
 */

import * as THREE from 'three'
import { SiteData, SOURCE_COLORS, getCategoryColor } from '../../../data/sites'
import { hexToRgb } from '../../../utils/geoUtils'
import {
  createFrontDotMaterial,
  createBackDotMaterial,
  createDotShadowMaterial,
} from '../../../shaders/globe'

// ============================================================================
// Types
// ============================================================================

export interface SitesRendererOptions {
  sites: SiteData[]
  filterMode: string
  sourceColors: Record<string, string>
  countryColors: Record<string, string>
  dotSize: number
  contextIsOffline: boolean
  cachedSourceIds: Set<string>
  searchWithinProximity?: boolean
  proximityCenter?: [number, number] | null
  isSatelliteMode: boolean
  dotsAnimationComplete: boolean
}

export interface SitesRendererResult {
  frontPoints: THREE.Points
  backPoints: THREE.Points
  shadowPoints: THREE.Points
  selectedPoints: THREE.Points | null
  frontMaterial: THREE.ShaderMaterial
  backMaterial: THREE.ShaderMaterial
  shadowMaterial: THREE.ShaderMaterial
  selectedMaterial: THREE.ShaderMaterial | null
  validSites: SiteData[]
  positions3D: Float32Array
  baseColors: Float32Array
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Convert period string to approximate year
 */
function periodToYear(period: string): number | null {
  switch (period) {
    case '< 4500 BC': return -5000
    case '4500 - 3000 BC': return -3750
    case '3000 - 1500 BC': return -2250
    case '1500 - 500 BC': return -1000
    case '500 BC - 1 AD': return -250
    case '1 - 500 AD': return 250
    case '500 - 1000 AD': return 750
    case '1000 - 1500 AD': return 1250
    case '1500+ AD': return 1750
    case '': return null
    default: return null
  }
}

/**
 * Convert RGB to hex string
 */
function rgbToHex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('')
}

/**
 * Get color for age based on actual year
 */
function getAgeColor(year: number | null | undefined): string {
  if (year === null || year === undefined) return '#9ca3af'

  const minYear = -5000
  const maxYear = 1500
  const clampedYear = Math.max(minYear, Math.min(maxYear, year))
  const t = (clampedYear - minYear) / (maxYear - minYear)

  const colors = [
    { pos: 0, r: 255, g: 0, b: 0 },
    { pos: 0.2, r: 255, g: 68, b: 0 },
    { pos: 0.4, r: 255, g: 102, b: 0 },
    { pos: 0.6, r: 255, g: 153, b: 0 },
    { pos: 0.8, r: 255, g: 204, b: 0 },
    { pos: 1, r: 255, g: 255, b: 0 },
  ]

  let c1 = colors[0], c2 = colors[1]
  for (let i = 0; i < colors.length - 1; i++) {
    if (t >= colors[i].pos && t <= colors[i + 1].pos) {
      c1 = colors[i]
      c2 = colors[i + 1]
      break
    }
  }

  const localT = (t - c1.pos) / (c2.pos - c1.pos)
  const r = Math.round(c1.r + (c2.r - c1.r) * localT)
  const g = Math.round(c1.g + (c2.g - c1.g) * localT)
  const b = Math.round(c1.b + (c2.b - c1.b) * localT)

  return rgbToHex(r, g, b)
}

/**
 * Extract country from location string
 */
function extractCountry(location: string | undefined): string {
  if (!location) return 'Unknown'
  const parts = location.split(',')
  return parts[parts.length - 1].trim() || 'Unknown'
}

/**
 * Get color for a site based on filter mode
 */
function getSiteColor(
  site: SiteData,
  filterMode: string,
  sourceColors: Record<string, string>,
  countryColors: Record<string, string>
): string {
  const FALLBACK_COLOR = '#9ca3af'
  let color: string | undefined

  switch (filterMode) {
    case 'source':
      color = sourceColors?.[site.sourceId] || SOURCE_COLORS[site.sourceId] || SOURCE_COLORS.default || FALLBACK_COLOR
      break
    case 'category':
      color = getCategoryColor(site.category)
      break
    case 'country':
      const country = extractCountry(site.location)
      color = countryColors?.[country] || '#a855f7'
      break
    case 'age':
    default:
      const year = site.periodStart ?? periodToYear(site.period)
      color = getAgeColor(year)
      break
  }

  if (!color || !/^#[0-9A-Fa-f]{6}$/.test(color)) {
    return FALLBACK_COLOR
  }
  return color
}

// ============================================================================
// Main Renderer Function
// ============================================================================

/**
 * Create site dot point clouds for the globe
 *
 * @param options - Rendering options
 * @returns Result with created point clouds and data arrays, or null if no valid sites
 */
export function createSitePoints(options: SitesRendererOptions): SitesRendererResult | null {
  const {
    sites,
    filterMode,
    sourceColors,
    countryColors,
    dotSize,
    contextIsOffline,
    cachedSourceIds,
    searchWithinProximity,
    proximityCenter,
    isSatelliteMode,
    dotsAnimationComplete,
  } = options

  // Scale dot size for constant visual size across resolutions
  const dpr = window.devicePixelRatio || 1
  const effectiveDotSize = dotSize * (window.innerHeight / 1080) * dpr

  // Filter valid sites
  const validSites = sites.filter(site => {
    const coords = site.coordinates
    if (!coords || !Array.isArray(coords) || coords.length < 2) return false
    const [lng, lat] = coords
    if (typeof lng !== 'number' || typeof lat !== 'number' || isNaN(lng) || isNaN(lat)) return false
    if (searchWithinProximity && (site as any).isInsideProximity === false) return false
    return true
  })

  if (!validSites.length) {
    return null
  }

  // Create arrays
  const positions = new Float32Array(validSites.length * 3)
  const baseColors = new Float32Array(validSites.length * 3)
  const colors = new Float32Array(validSites.length * 3)
  const glowEnabled = new Float32Array(validSites.length)
  const fadeDelays = new Float32Array(validSites.length)

  // Pre-fill with fallback color
  const fallbackRgb = hexToRgb('#9ca3af')
  for (let i = 0; i < validSites.length; i++) {
    baseColors[i * 3] = fallbackRgb[0]
    baseColors[i * 3 + 1] = fallbackRgb[1]
    baseColors[i * 3 + 2] = fallbackRgb[2]
    colors[i * 3] = fallbackRgb[0]
    colors[i * 3 + 1] = fallbackRgb[1]
    colors[i * 3 + 2] = fallbackRgb[2]
  }

  // Find min/max ages for normalization
  let minAge = Infinity
  let maxAge = -Infinity
  const ages: number[] = []
  for (let i = 0; i < validSites.length; i++) {
    const site = validSites[i]
    const year = site.periodStart ?? periodToYear(site.period) ?? 0
    ages[i] = year
    if (year < minAge) minAge = year
    if (year > maxAge) maxAge = year
  }
  const ageRange = maxAge - minAge || 1

  // Fill position and color arrays
  for (let i = 0; i < validSites.length; i++) {
    const site = validSites[i]
    const [lng, lat] = site.coordinates
    const phi = (90 - lat) * Math.PI / 180
    const theta = (lng + 180) * Math.PI / 180
    const r = 1.002

    positions[i * 3] = -r * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = r * Math.cos(phi)
    positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta)

    const [cr, cg, cb] = hexToRgb(getSiteColor(site, filterMode, sourceColors, countryColors))

    baseColors[i * 3] = cr
    baseColors[i * 3 + 1] = cg
    baseColors[i * 3 + 2] = cb

    const isOutsideProximity = proximityCenter && (site as any).isInsideProximity === false
    const fadeFactor = isOutsideProximity ? 0.65 : 1.0

    colors[i * 3] = cr * fadeFactor
    colors[i * 3 + 1] = cg * fadeFactor
    colors[i * 3 + 2] = cb * fadeFactor

    const siteSourceCached = cachedSourceIds.has(site.sourceId)
    glowEnabled[i] = (!contextIsOffline || siteSourceCached) ? 1.0 : 0.0

    const normalizedAge = (ages[i] - minAge) / ageRange
    const randomOffset = Math.random() * 0.3
    fadeDelays[i] = Math.min(normalizedAge * 0.7 + randomOffset, 1.0)
  }

  // Separate selected and unselected dots
  const selectedIndices: number[] = []
  const unselectedIndices: number[] = []
  for (let i = 0; i < validSites.length; i++) {
    if ((validSites[i] as any).isSelected === true) {
      selectedIndices.push(i)
    } else {
      unselectedIndices.push(i)
    }
  }

  // Create geometry for selected dots
  const selectedPositions = new Float32Array(selectedIndices.length * 3)
  const selectedColors = new Float32Array(selectedIndices.length * 3)
  const selectedGlow = new Float32Array(selectedIndices.length)
  const selectedFadeDelays = new Float32Array(selectedIndices.length)
  for (let j = 0; j < selectedIndices.length; j++) {
    const i = selectedIndices[j]
    selectedPositions[j * 3] = positions[i * 3]
    selectedPositions[j * 3 + 1] = positions[i * 3 + 1]
    selectedPositions[j * 3 + 2] = positions[i * 3 + 2]
    selectedColors[j * 3] = baseColors[i * 3]
    selectedColors[j * 3 + 1] = baseColors[i * 3 + 1]
    selectedColors[j * 3 + 2] = baseColors[i * 3 + 2]
    selectedGlow[j] = glowEnabled[i]
    selectedFadeDelays[j] = fadeDelays[i]
  }

  // Main geometry (all dots for raycasting)
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geo.setAttribute('glow', new THREE.BufferAttribute(glowEnabled, 1))
  geo.setAttribute('fadeDelay', new THREE.BufferAttribute(fadeDelays, 1))

  // Create materials
  const backMaterial = createBackDotMaterial(effectiveDotSize)
  const frontMaterial = createFrontDotMaterial(effectiveDotSize)

  if (dotsAnimationComplete) {
    backMaterial.uniforms.uDotsFadeProgress.value = 1.0
    frontMaterial.uniforms.uDotsFadeProgress.value = 1.0
  }

  // Back dots
  const backPoints = new THREE.Points(geo, backMaterial)
  backPoints.renderOrder = -12

  // Front dots
  const frontPoints = new THREE.Points(geo, frontMaterial)
  frontPoints.renderOrder = 20

  // Shadow layer
  const shadowMaterial = createDotShadowMaterial(effectiveDotSize)
  if (dotsAnimationComplete) {
    shadowMaterial.uniforms.uDotsFadeProgress.value = 1.0
  }
  const shadowPoints = new THREE.Points(geo, shadowMaterial)
  shadowPoints.renderOrder = 18
  shadowPoints.visible = true

  // Hide back dots in satellite mode
  backPoints.visible = !isSatelliteMode

  // Create selected dots overlay if needed
  let selectedPoints: THREE.Points | null = null
  let selectedMaterial: THREE.ShaderMaterial | null = null

  if (selectedIndices.length > 0) {
    const selectedGeo = new THREE.BufferGeometry()
    selectedGeo.setAttribute('position', new THREE.BufferAttribute(selectedPositions, 3))
    selectedGeo.setAttribute('color', new THREE.BufferAttribute(selectedColors, 3))
    selectedGeo.setAttribute('glow', new THREE.BufferAttribute(selectedGlow, 1))
    selectedGeo.setAttribute('fadeDelay', new THREE.BufferAttribute(selectedFadeDelays, 1))

    selectedMaterial = createFrontDotMaterial(effectiveDotSize * 2)
    if (dotsAnimationComplete) {
      selectedMaterial.uniforms.uDotsFadeProgress.value = 1.0
    }

    selectedPoints = new THREE.Points(selectedGeo, selectedMaterial)
    selectedPoints.renderOrder = 24
  }

  return {
    frontPoints,
    backPoints,
    shadowPoints,
    selectedPoints,
    frontMaterial,
    backMaterial,
    shadowMaterial,
    selectedMaterial,
    validSites,
    positions3D: positions,
    baseColors,
  }
}

/**
 * Clean up a point cloud and remove its material from tracking
 */
export function cleanupPoints(
  points: THREE.Points | null | undefined,
  shaderMaterials: THREE.ShaderMaterial[]
): void {
  if (!points) return

  points.parent?.remove(points)
  points.geometry.dispose()
  const mat = points.material as THREE.Material
  const idx = shaderMaterials.indexOf(mat as THREE.ShaderMaterial)
  if (idx !== -1) shaderMaterials.splice(idx, 1)
  mat.dispose()
}
