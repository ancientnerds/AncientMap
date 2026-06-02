/**
 * Device-capability tiering for the globe's basemap textures.
 *
 * The high-res basemap is 16383x8192 (~512 MB once decoded + uploaded). That
 * crashes memory-constrained tablets during the loading splash:
 *  - Android/Galaxy GPUs whose GL_MAX_TEXTURE_SIZE is below 16384 cannot upload
 *    it at all.
 *  - iPadOS Safari hits its per-tab memory ceiling decoding the image.
 * Desktops have the headroom, so they keep the high tier. We pick the tier from
 * the GPU's real max texture size plus a touch/mobile heuristic, and load a
 * pre-generated smaller asset (see scripts/gen_basemap_tiers.py) when needed.
 */

export type BasemapTier = 'high' | 'med' | 'low'

interface TierAssets {
  gray: string
  satellite: string
  /** Texture dimensions, used to set the back-mesh blur texel-size uniform. */
  width: number
  height: number
}

const TIER_DIMENSIONS: Record<BasemapTier, { width: number; height: number }> = {
  high: { width: 16384, height: 8192 },
  med: { width: 8192, height: 4096 },
  low: { width: 4096, height: 2048 },
}

/** True for touch-primary devices (phones/tablets), false for desktops even with a touchscreen. */
function isTouchPrimaryDevice(): boolean {
  const ua = navigator.userAgent
  if (/iPhone|iPod|Android|Tablet|Silk|Kindle|PlayBook|BlackBerry|Mobile/i.test(ua)) return true
  // iPadOS 13+ reports a desktop Safari UA; detect via Mac platform + touch.
  if (navigator.platform === 'MacIntel' && (navigator.maxTouchPoints ?? 0) > 1) return true
  // Generic touch-primary signal (coarse pointer as the primary input).
  if (typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches) {
    return (navigator.maxTouchPoints ?? 0) > 1
  }
  return false
}

/**
 * Choose the basemap tier for this device.
 * @param maxTextureSize  GPU GL_MAX_TEXTURE_SIZE (THREE renderer.capabilities.maxTextureSize)
 */
export function getBasemapTier(maxTextureSize: number): BasemapTier {
  // Explicit override for testing on any device: ?basemap=high|medium|med|low
  const override = new URLSearchParams(window.location.search).get('basemap')
  if (override === 'high') return 'high'
  if (override === 'medium' || override === 'med') return 'med'
  if (override === 'low') return 'low'

  // GPU cannot physically hold the larger textures.
  if (maxTextureSize > 0 && maxTextureSize < 8192) return 'low'
  if (maxTextureSize > 0 && maxTextureSize < 16384) return 'med'

  // GPU is capable, but constrained devices still crash on the 512 MB upload.
  const lowMemory =
    typeof (navigator as Navigator & { deviceMemory?: number }).deviceMemory === 'number' &&
    (navigator as Navigator & { deviceMemory?: number }).deviceMemory! <= 4
  if (isTouchPrimaryDevice() || lowMemory) return 'med'

  return 'high'
}

/** Resolve the asset URLs and dimensions for a tier. */
export function getBasemapAssets(tier: BasemapTier): TierAssets {
  const { width, height } = TIER_DIMENSIONS[tier]
  return {
    gray: `/data/basemaps/gray_dark_${tier}.webp`,
    satellite: `/data/basemaps/satellite_${tier}.webp`,
    width,
    height,
  }
}
