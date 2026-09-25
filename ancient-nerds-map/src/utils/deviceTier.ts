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
 *
 * Two tiers per device: the maximum tier (getBasemapTier) is the sharpest file
 * the device may hold; the start tier (getStartTier) is the smallest file that
 * still renders the first frame at full detail on this canvas. The start tier
 * is on the critical path, the upgrade to the maximum runs in the background.
 *
 * Module scope stays free of window/navigator (SSR-safe imports).
 */

export type BasemapTier = 'high' | 'med' | 'low'

/**
 * Pixel width of each tier's files. The high tier is 16383 wide, not 16384
 * (scripts/gen_basemap_tiers.py); uploads allocate from the decoded bitmap's
 * own size, this table only drives the tier choice.
 */
export const TIER_WIDTH: Record<BasemapTier, number> = { low: 4096, med: 8192, high: 16383 }

/** The smallest basemap file; a GPU below this texture size cannot show the globe. */
export const MIN_BASEMAP_TEXTURE_SIZE = TIER_WIDTH.low

/** Every tier, smallest first. */
export const BASEMAP_TIERS: readonly BasemapTier[] = ['low', 'med', 'high']

/** Order of the tiers: low < med < high. */
export function tierRank(tier: BasemapTier): 0 | 1 | 2 {
  return tier === 'low' ? 0 : tier === 'med' ? 1 : 2
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
 * The phone gate's rule (App): a viewport too small for the globe UI, or a
 * phone user agent. Tablets pass: Android without "Mobile" is a tablet, and
 * iPad user agents match none of the phone names.
 */
export function isPhoneOrSmallScreen(): boolean {
  const isSmallScreen = window.innerWidth < 768 || window.innerHeight < 500
  const isPhone = /iPhone|iPod|Android.*Mobile|webOS|BlackBerry|IEMobile|Opera Mini|Windows Phone/i.test(navigator.userAgent)
  return isSmallScreen || isPhone
}

/** `?basemap=high|medium|med|low` pins both the start and the maximum tier (testing, probes). */
function basemapOverride(): BasemapTier | null {
  const override = new URLSearchParams(window.location.search).get('basemap')
  if (override === 'high') return 'high'
  if (override === 'medium' || override === 'med') return 'med'
  if (override === 'low') return 'low'
  return null
}

/**
 * The maximum tier for this device.
 * @param maxTextureSize  GPU GL_MAX_TEXTURE_SIZE (THREE renderer.capabilities.maxTextureSize); 0 = unknown
 */
export function getBasemapTier(maxTextureSize: number): BasemapTier {
  const override = basemapOverride()
  if (override) return override

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

/**
 * Texture width at which one texel meets one device pixel at the centre of the
 * globe in the start view (camera 2.44 from the centre, vertical FOV 60 deg):
 * a surface arc s at distance 1.44 spans s / (1.44 * tan 30 deg) * H/2 px, so
 * a radian of longitude covers 0.6014 * H px and the 2*pi texture width needs
 * 3.78 * H texels. The renderer caps the pixel ratio at 2.
 */
export function requiredBasemapWidth(cssHeight: number, dpr: number): number {
  return 3.78 * cssHeight * Math.min(dpr, 2)
}

/**
 * The start tier: the smallest file at least as wide as the canvas needs
 * (so the first frame samples the same detail as the maximum tier would), the
 * largest file when none is wide enough, and never above the maximum tier.
 */
export function getStartTier(maxTextureSize: number, viewport: { cssHeight: number; dpr: number }): BasemapTier {
  const override = basemapOverride()
  if (override) return override
  const max = getBasemapTier(maxTextureSize)
  const required = requiredBasemapWidth(viewport.cssHeight, viewport.dpr)
  const fit = BASEMAP_TIERS.find(tier => TIER_WIDTH[tier] >= required) ?? 'high'
  return tierRank(fit) <= tierRank(max) ? fit : max
}

/** Resolve the asset URLs for a tier. Unversioned: the files are content-stable. */
export function getBasemapAssets(tier: BasemapTier): { gray: string; satellite: string } {
  return {
    gray: `/data/basemaps/gray_dark_${tier}.webp`,
    satellite: `/data/basemaps/satellite_${tier}.webp`,
  }
}
