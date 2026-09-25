/**
 * The files the globe's start cannot do without come with every offline
 * download, whatever the visitor ticked: an offline start with only the
 * sources (or only the layers) downloaded shows the globe, not the error
 * screen. Each file goes into the cache its loader reads offline, and a file
 * counts as present where that loader finds it: labels.json and the layer start
 * tiers through OfflineFetch (every app cache and the service worker's
 * precache, which holds the running build's start tiers), the gray only in
 * 'basemaps'. Only missing files are downloaded.
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** url -> the cache it was put into */
let stored: Map<string, string>
/** What the service worker's precache holds (the running build's start tiers) */
let precached: Set<string>

vi.mock('../OfflineFetch', () => ({
  OfflineFetch: { isCached: vi.fn(async (url: string) => stored.has(url) || precached.has(url)) },
}))

import { getGlobeLayerUrl } from '../../config/vectorLayers'
import { VECTOR_LAYER_CACHE } from '../../pwa/cacheNames'
import { downloadGlobeStart, globeStartFiles, missingGlobeStartFiles, startFilesSize } from '../GlobeStartCache'

const DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'

let fetched: string[]

beforeEach(() => {
  vi.stubGlobal('navigator', { userAgent: DESKTOP, platform: 'Win32', maxTouchPoints: 0 })
  vi.stubGlobal('window', { location: { search: '' }, innerWidth: 1920, innerHeight: 1080 })
  stored = new Map()
  precached = new Set()
  fetched = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    fetched.push(url)
    return new Response(url, { status: 200 })
  }))
  vi.stubGlobal('caches', {
    open: async (name: string) => ({
      put: async (url: string) => { stored.set(url, name) },
      match: async (url: string) => (stored.get(url) === name ? new Response('x') : undefined),
    }),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const EXPECTED: Array<[string, string]> = [
  ['/data/labels.json', 'basemaps'],
  ['/data/basemaps/gray_dark_low.webp', 'basemaps'],
  ['/data/basemaps/gray_dark_med.webp', 'basemaps'],
  ['/data/basemaps/gray_dark_high.webp', 'basemaps'],
  [getGlobeLayerUrl('coastlines', 'start'), VECTOR_LAYER_CACHE],
  [getGlobeLayerUrl('countryBorders', 'start'), VECTOR_LAYER_CACHE],
]

describe('the globe start set', () => {
  it('is labels, the gray up to the maximum tier and the coastline and border start tiers', () => {
    expect(globeStartFiles().map(f => [f.url, f.cache])).toEqual(EXPECTED)
    expect(startFilesSize(globeStartFiles())).toBe(globeStartFiles().reduce((sum, f) => sum + f.size, 0))
  })

  it('downloads every file into the cache its loader reads, with progress', async () => {
    const progress = vi.fn()
    const missing = await missingGlobeStartFiles()
    expect(missing).toEqual(globeStartFiles())
    await downloadGlobeStart(missing, progress)
    expect(fetched).toEqual(EXPECTED.map(([url]) => url))
    expect([...stored.entries()]).toEqual(EXPECTED)
    expect(progress).toHaveBeenLastCalledWith(startFilesSize(missing), startFilesSize(missing))
    expect(await missingGlobeStartFiles()).toEqual([])
  })

  it('is not complete while one file is missing, and fetches only that file', async () => {
    await downloadGlobeStart(await missingGlobeStartFiles())
    stored.delete('/data/basemaps/gray_dark_med.webp')
    const missing = await missingGlobeStartFiles()
    expect(missing.map(f => f.url)).toEqual(['/data/basemaps/gray_dark_med.webp'])
    fetched.length = 0
    await downloadGlobeStart(missing)
    expect(fetched).toEqual(['/data/basemaps/gray_dark_med.webp']) // not labels.json again
  })

  it('after a layer rebuild finds the new start tiers in the precache: nothing is missing, nothing is fetched', async () => {
    await downloadGlobeStart(await missingGlobeStartFiles())
    // The rebuild renamed the tiers: the download's copies are under the old names,
    // the new worker precached the new ones
    for (const key of ['coastlines', 'countryBorders'] as const) {
      stored.delete(getGlobeLayerUrl(key, 'start'))
      precached.add(getGlobeLayerUrl(key, 'start'))
    }
    expect(await missingGlobeStartFiles()).toEqual([])
  })

  it('reads the gray only in the basemap cache (the service worker rule the basemap loader goes through)', async () => {
    await downloadGlobeStart(await missingGlobeStartFiles())
    stored.set('/data/basemaps/gray_dark_low.webp', VECTOR_LAYER_CACHE)
    expect((await missingGlobeStartFiles()).map(f => f.url)).toEqual(['/data/basemaps/gray_dark_low.webp'])
  })

  it('names the byte sizes of the files the deploy serves (labels.json and the layer start tiers)', () => {
    const repoPublic = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../public')
    for (const file of globeStartFiles().filter(f => !f.url.endsWith('.webp'))) {
      // git stores LF; a CRLF checkout of labels.json must not change the served size
      const served = readFileSync(join(repoPublic, file.url)).toString('latin1').replace(/\r\n/g, '\n').length
      expect(file.size, file.url).toBe(served)
    }
  })

  it('fails the download on an HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response('missing', { status: url.endsWith('labels.json') ? 404 : 200 })))
    await expect(downloadGlobeStart(globeStartFiles())).rejects.toThrow(/labels\.json.*404/)
  })
})
