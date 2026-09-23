/**
 * The offline basemap download holds what the globe's loader will request:
 * the gray (critical, start tier) and the satellite at every tier up to the
 * device's maximum. The start tier follows the window height at load time,
 * so every tier up to the maximum has to be there.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BasemapCache } from '../BasemapCache'

function env(ua: string): void {
  vi.stubGlobal('navigator', { userAgent: ua, platform: 'Win32', maxTouchPoints: 0 })
  vi.stubGlobal('window', { location: { search: '' }, innerWidth: 1920, innerHeight: 1080 })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

const DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'
const TABLET = 'Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'

describe('BasemapCache satellite item', () => {
  it('holds gray and satellite at every tier on a desktop', () => {
    env(DESKTOP)
    const item = BasemapCache.getBasemapItemInfo('satellite')
    expect(item.files.map(f => f.url)).toEqual([
      '/data/basemaps/gray_dark_low.webp',
      '/data/basemaps/satellite_low.webp',
      '/data/basemaps/gray_dark_med.webp',
      '/data/basemaps/satellite_med.webp',
      '/data/basemaps/gray_dark_high.webp',
      '/data/basemaps/satellite_high.webp',
    ])
    expect(item.totalSize).toBe(item.files.reduce((sum, f) => sum + f.size, 0))
    expect(item.files.find(f => f.url.endsWith('satellite_high.webp'))!.size).toBe(17_001_226)
  })

  it('stops at the maximum tier of a tablet', () => {
    env(TABLET)
    const urls = BasemapCache.getBasemapItemInfo('satellite').files.map(f => f.url)
    expect(urls).toEqual([
      '/data/basemaps/gray_dark_low.webp',
      '/data/basemaps/satellite_low.webp',
      '/data/basemaps/gray_dark_med.webp',
      '/data/basemaps/satellite_med.webp',
    ])
    expect(BasemapCache.estimateSize(['satellite'])).toBe(109_724 + 714_326 + 482_678 + 2_657_496)
  })

  it('keeps the item list and the labels item as they were', () => {
    env(DESKTOP)
    expect(BasemapCache.getBasemapItems().map(i => [i.id, i.name])).toEqual([['satellite', 'Satellite'], ['labels', 'Labels']])
    expect(BasemapCache.getBasemapItemInfo('labels').files.map(f => f.url)).toEqual(['/data/labels.json'])
  })
})
