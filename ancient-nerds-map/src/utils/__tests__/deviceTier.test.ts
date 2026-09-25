import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getBasemapAssets,
  getBasemapTier,
  getStartTier,
  isPhoneOrSmallScreen,
  MIN_BASEMAP_TEXTURE_SIZE,
  requiredBasemapWidth,
  TIER_WIDTH,
  tierRank,
} from '../deviceTier'

const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
const PHONE_UA = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36'
const IPAD_DESKTOP_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'

interface Env {
  search?: string
  ua?: string
  platform?: string
  maxTouchPoints?: number
  coarse?: boolean
  deviceMemory?: number
  innerWidth?: number
  innerHeight?: number
}

// Node 20 has no global navigator/window: every test installs both.
function env(e: Env = {}): void {
  vi.stubGlobal('navigator', {
    userAgent: e.ua ?? DESKTOP_UA,
    platform: e.platform ?? 'Win32',
    maxTouchPoints: e.maxTouchPoints ?? 0,
    ...(e.deviceMemory === undefined ? {} : { deviceMemory: e.deviceMemory }),
  })
  vi.stubGlobal('window', {
    location: { search: e.search ?? '' },
    matchMedia: (q: string) => ({ matches: q === '(pointer: coarse)' && (e.coarse ?? false) }),
    innerWidth: e.innerWidth ?? 1920,
    innerHeight: e.innerHeight ?? 1080,
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('getBasemapTier (maximum tier, unchanged semantics)', () => {
  it('pins the tier through ?basemap=', () => {
    env({ search: '?basemap=low' })
    expect(getBasemapTier(16384)).toBe('low')
    env({ search: '?basemap=medium' })
    expect(getBasemapTier(16384)).toBe('med')
    env({ search: '?basemap=med' })
    expect(getBasemapTier(16384)).toBe('med')
    env({ search: '?basemap=high', ua: PHONE_UA })
    expect(getBasemapTier(4096)).toBe('high')
  })

  it('follows the GPU limit', () => {
    env()
    expect(getBasemapTier(4096)).toBe('low')
    expect(getBasemapTier(8192)).toBe('med')
    expect(getBasemapTier(16384)).toBe('high')
    // 0 = unknown, treated as unconstrained
    expect(getBasemapTier(0)).toBe('high')
  })

  it('keeps touch-primary devices on med', () => {
    env({ ua: PHONE_UA })
    expect(getBasemapTier(16384)).toBe('med')
    env({ ua: IPAD_DESKTOP_UA, platform: 'MacIntel', maxTouchPoints: 5 })
    expect(getBasemapTier(16384)).toBe('med')
    env({ coarse: true, maxTouchPoints: 10 })
    expect(getBasemapTier(16384)).toBe('med')
    // a coarse pointer without multi-touch is not touch-primary
    env({ coarse: true, maxTouchPoints: 0 })
    expect(getBasemapTier(16384)).toBe('high')
  })

  it('keeps low-memory devices on med', () => {
    env({ deviceMemory: 4 })
    expect(getBasemapTier(16384)).toBe('med')
    env({ deviceMemory: 8 })
    expect(getBasemapTier(16384)).toBe('high')
  })
})

describe('tier table', () => {
  it('names the real widths of the files (the high tier is 16383 wide)', () => {
    expect(TIER_WIDTH).toEqual({ low: 4096, med: 8192, high: 16383 })
    expect(MIN_BASEMAP_TEXTURE_SIZE).toBe(4096)
  })

  it('ranks the tiers', () => {
    expect(tierRank('low')).toBe(0)
    expect(tierRank('med')).toBe(1)
    expect(tierRank('high')).toBe(2)
  })

  it('resolves the asset URLs', () => {
    expect(getBasemapAssets('med')).toEqual({
      gray: '/data/basemaps/gray_dark_med.webp',
      satellite: '/data/basemaps/satellite_med.webp',
    })
  })
})

describe('requiredBasemapWidth', () => {
  it('is 3.78 texels per device pixel of viewport height', () => {
    expect(requiredBasemapWidth(1080, 1)).toBeCloseTo(4082.4, 6)
    expect(requiredBasemapWidth(1080, 2)).toBeCloseTo(8164.8, 6)
  })

  it('caps the device pixel ratio at 2 like the renderer does', () => {
    expect(requiredBasemapWidth(915, 2.625)).toBeCloseTo(requiredBasemapWidth(915, 2), 6)
  })
})

describe('getStartTier', () => {
  it('picks the smallest tier at least as wide as the canvas needs', () => {
    env()
    expect(getStartTier(16384, { cssHeight: 1080, dpr: 1 })).toBe('low') // 4082 <= 4096
    expect(getStartTier(16384, { cssHeight: 1084, dpr: 1 })).toBe('med') // 4098 > 4096
    expect(getStartTier(16384, { cssHeight: 1080, dpr: 2 })).toBe('med') // 8165 <= 8192
  })

  it('goes to high only when med is too narrow', () => {
    env()
    // 3.78 * 1083 * 2 = 8187.5 fits med; 3.78 * 1084 * 2 = 8195.0 does not
    expect(getStartTier(16384, { cssHeight: 1083, dpr: 2 })).toBe('med')
    expect(getStartTier(16384, { cssHeight: 1084, dpr: 2 })).toBe('high')
    // a 5K-class screen needs more than the largest file: the largest file
    expect(getStartTier(16384, { cssHeight: 2880, dpr: 2 })).toBe('high')
  })

  it('never goes above the maximum tier', () => {
    env()
    expect(getStartTier(8192, { cssHeight: 1440, dpr: 2 })).toBe('med')
    expect(getStartTier(4096, { cssHeight: 1440, dpr: 2 })).toBe('low')
    env({ ua: PHONE_UA })
    expect(getStartTier(16384, { cssHeight: 915, dpr: 2.625 })).toBe('med')
    env({ deviceMemory: 2 })
    expect(getStartTier(16384, { cssHeight: 2160, dpr: 2 })).toBe('med')
  })

  it('is low on a 4096 GPU', () => {
    env()
    expect(getStartTier(4096, { cssHeight: 600, dpr: 1 })).toBe('low')
  })

  it('is pinned by ?basemap= like the maximum tier', () => {
    env({ search: '?basemap=high' })
    expect(getStartTier(16384, { cssHeight: 600, dpr: 1 })).toBe('high')
    env({ search: '?basemap=low' })
    expect(getStartTier(16384, { cssHeight: 2160, dpr: 2 })).toBe('low')
    env({ search: '?basemap=med' })
    expect(getStartTier(16384, { cssHeight: 600, dpr: 1 })).toBe('med')
  })
})

describe('isPhoneOrSmallScreen (the phone gate rule)', () => {
  it('gates small viewports', () => {
    env({ innerWidth: 767, innerHeight: 1000 })
    expect(isPhoneOrSmallScreen()).toBe(true)
    env({ innerWidth: 1200, innerHeight: 499 })
    expect(isPhoneOrSmallScreen()).toBe(true)
    env({ innerWidth: 768, innerHeight: 500 })
    expect(isPhoneOrSmallScreen()).toBe(false)
  })

  it('gates phone user agents but lets tablets through', () => {
    env({ ua: PHONE_UA, innerWidth: 1200, innerHeight: 900 })
    expect(isPhoneOrSmallScreen()).toBe(true)
    env({ ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148', innerWidth: 1200, innerHeight: 900 })
    expect(isPhoneOrSmallScreen()).toBe(true)
    // Android without "Mobile" is a tablet; iPad UAs carry no "Mobile" in the matched form
    env({ ua: 'Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 Chrome/140.0 Safari/537.36', innerWidth: 1280, innerHeight: 800 })
    expect(isPhoneOrSmallScreen()).toBe(false)
    env({ ua: 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Safari/604.1', innerWidth: 1024, innerHeight: 768 })
    expect(isPhoneOrSmallScreen()).toBe(false)
  })
})
