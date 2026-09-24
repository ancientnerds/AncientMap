/**
 * The offline basemap download holds what the globe's loader will request.
 * The 'Satellite' item holds the satellite at every tier up to the device's
 * maximum (the start tier follows the window height at load time, so all of
 * them); the gray, which the start cannot do without, comes with every
 * offline download (GlobeStartCache). An item counts as downloaded only when
 * every one of its files is in the 'basemaps' cache.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../OfflineStorage', () => ({
  OfflineStorage: {
    addBasemapItem: vi.fn(async () => undefined),
    getDownloadState: vi.fn(async () => ({ basemapItems: [] })),
  },
}))

import { OfflineStorage } from '../OfflineStorage'
import { BasemapCache, grayBasemapFiles } from '../BasemapCache'

function env(ua: string): void {
  vi.stubGlobal('navigator', { userAgent: ua, platform: 'Win32', maxTouchPoints: 0 })
  vi.stubGlobal('window', { location: { search: '' }, innerWidth: 1920, innerHeight: 1080 })
}

let stored: Map<string, string>

beforeEach(() => {
  stored = new Map()
  vi.stubGlobal('caches', {
    open: async (name: string) => ({
      put: async (url: string) => { stored.set(url, name) },
      match: async (url: string) => (stored.get(url) === name ? new Response('x') : undefined),
    }),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.mocked(OfflineStorage.getDownloadState).mockReset()
  vi.mocked(OfflineStorage.getDownloadState).mockImplementation(async () => ({ basemapItems: [] }) as never)
})

function markDownloaded(basemapItems: string[]) {
  vi.mocked(OfflineStorage.getDownloadState).mockImplementation(async () => ({ basemapItems }) as never)
}

const DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'
const TABLET = 'Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'

describe('BasemapCache satellite item', () => {
  it('holds the satellite at every tier on a desktop', () => {
    env(DESKTOP)
    const item = BasemapCache.getBasemapItemInfo('satellite')
    expect(item.files.map(f => f.url)).toEqual([
      '/data/basemaps/satellite_low.webp',
      '/data/basemaps/satellite_med.webp',
      '/data/basemaps/satellite_high.webp',
    ])
    expect(item.totalSize).toBe(item.files.reduce((sum, f) => sum + f.size, 0))
    expect(item.files.find(f => f.url.endsWith('satellite_high.webp'))!.size).toBe(17_001_226)
  })

  it('stops at the maximum tier of a tablet', () => {
    env(TABLET)
    const urls = BasemapCache.getBasemapItemInfo('satellite').files.map(f => f.url)
    expect(urls).toEqual(['/data/basemaps/satellite_low.webp', '/data/basemaps/satellite_med.webp'])
    expect(BasemapCache.estimateSize(['satellite'])).toBe(714_326 + 2_657_496)
  })

  it('names the gray tiers up to the maximum for the start set', () => {
    env(TABLET)
    expect(grayBasemapFiles()).toEqual([
      { url: '/data/basemaps/gray_dark_low.webp', size: 109_724 },
      { url: '/data/basemaps/gray_dark_med.webp', size: 482_678 },
    ])
  })

  it('keeps the item list and the labels item as they were', () => {
    env(DESKTOP)
    expect(BasemapCache.getBasemapItems().map(i => [i.id, i.name])).toEqual([['satellite', 'Satellite'], ['labels', 'Labels']])
    expect(BasemapCache.getBasemapItemInfo('labels').files.map(f => f.url)).toEqual(['/data/labels.json'])
  })
})

describe('BasemapCache.getCachedItems', () => {
  it('counts an item as downloaded only when every file is in the basemaps cache', async () => {
    env(DESKTOP)
    // A 'Satellite' download from before the tiers: satellite_high.webp only
    markDownloaded(['satellite', 'labels'])
    stored.set('/data/basemaps/satellite_high.webp', 'basemaps')
    stored.set('/data/labels.json', 'basemaps')
    expect(await BasemapCache.getCachedItems()).toEqual(['labels'])
    expect(await BasemapCache.isBasemapItemCached('satellite')).toBe(false)
    expect(await BasemapCache.isBasemapItemCached('labels')).toBe(true)
  })

  it('counts a completed download of this build as downloaded', async () => {
    env(DESKTOP)
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(url)))
    await BasemapCache.downloadBasemapItem('satellite')
    markDownloaded(['satellite'])
    expect(await BasemapCache.getCachedItems()).toEqual(['satellite'])
  })

  it('does not count files the service worker cached without a download', async () => {
    env(TABLET)
    markDownloaded([])
    stored.set('/data/basemaps/satellite_low.webp', 'basemaps')
    stored.set('/data/basemaps/satellite_med.webp', 'basemaps')
    expect(await BasemapCache.getCachedItems()).toEqual([])
  })
})
