/**
 * Offline downloads store exactly the URLs the globe fetches. OfflineFetch answers from the
 * Cache API with an exact-URL match, so a download under any other key (the old GitHub
 * Natural Earth URLs, the non-existent *_hires files) can never be read back offline.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../OfflineStorage', () => ({
  OfflineStorage: {
    addDownloadedLayer: vi.fn(async () => undefined),
    removeDownloadedLayer: vi.fn(async () => undefined),
    getDownloadState: vi.fn(async () => ({ layers: [] })),
    setMetadata: vi.fn(async () => undefined),
  },
}))

import { getGlobeLayerUrl, getLayerFiles, LAYER_CONFIG, type VectorLayerKey } from '../../config/vectorLayers'
import { globeStartLayerUrls } from '../GlobeStartCache'
import { OfflineStorage } from '../OfflineStorage'
import { VectorLayerCache } from '../VectorLayerCache'

const KEYS = Object.keys(LAYER_CONFIG) as VectorLayerKey[]

/**
 * The coastline and border start tiers belong to the globe's start files
 * (GlobeStartCache), which every download stores first: a layer download that
 * fetched them again fetched, stored and counted them twice.
 */
const COAST_START = getGlobeLayerUrl('coastlines', 'start')
const BORDERS_START = getGlobeLayerUrl('countryBorders', 'start')
const START_TIER = /\/(coast|borders)_start\.[0-9a-f]+\.json$/

/** getLayerFiles(key) without its start tier, named here, not taken from the code under test. */
function expectedDownload(key: VectorLayerKey): string[] {
  const files = getLayerFiles(key)
  const start = key === 'coastlines' ? COAST_START : key === 'countryBorders' ? BORDERS_START : null
  if (start === null) return files
  expect(files).toContain(start)
  return files.filter(url => url !== start)
}

let stored: Map<string, Response>
let fetched: string[]
let deleted: string[]

beforeEach(() => {
  stored = new Map()
  fetched = []
  deleted = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    fetched.push(url)
    return new Response('{}', { status: 200, headers: { 'Content-Length': '2' } })
  }))
  vi.stubGlobal('caches', {
    open: async () => ({
      put: async (url: string, res: Response) => { stored.set(url, res) },
      delete: async (url: string) => { deleted.push(url); return true },
      match: async (url: string) => stored.get(url),
    }),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.mocked(OfflineStorage.addDownloadedLayer).mockClear()
  vi.mocked(OfflineStorage.getDownloadState).mockReset()
  vi.mocked(OfflineStorage.getDownloadState).mockImplementation(async () => ({ layers: [] }) as never)
})

function markDownloaded(layers: string[]) {
  vi.mocked(OfflineStorage.getDownloadState).mockImplementation(async () => ({ layers }) as never)
}

function cacheFiles(urls: string[]) {
  for (const url of urls) stored.set(url, new Response('{}'))
}

describe('VectorLayerCache', () => {
  it('offers every vector layer of the globe with its real file count', () => {
    for (const key of KEYS) {
      const info = VectorLayerCache.getLayerInfo(key)
      expect(info, key).toBeDefined()
      expect(info!.fileCount).toBe(expectedDownload(key).length)
    }
  })

  it('leaves the coastline and border start tiers to the start files', () => {
    expect(COAST_START).toMatch(START_TIER)
    expect(BORDERS_START).toMatch(START_TIER)
    expect(globeStartLayerUrls()).toEqual([COAST_START, BORDERS_START])
    expect(VectorLayerCache.getLayerInfo('coastlines')!.fileCount).toBe(getLayerFiles('coastlines').length - 1)
    expect(VectorLayerCache.getLayerInfo('countryBorders')!.fileCount).toBe(getLayerFiles('countryBorders').length - 1)
  })

  it.each(KEYS)('downloads and stores exactly getLayerFiles(%s) without the start files', async key => {
    await VectorLayerCache.downloadLayer(key)
    expect(fetched.filter(url => START_TIER.test(url))).toEqual([])
    expect(fetched).toEqual(expectedDownload(key))
    expect([...stored.keys()]).toEqual(expectedDownload(key))
    expect(OfflineStorage.addDownloadedLayer).toHaveBeenCalledWith(key)
  })

  it('clears the layer download, never a start file the offline start needs', async () => {
    await VectorLayerCache.clearLayer('coastlines')
    expect(deleted).not.toContain(COAST_START)
    expect(deleted).toEqual(expectedDownload('coastlines'))
  })

  it('counts a layer as downloaded only when every file of getLayerFiles is in the cache', async () => {
    markDownloaded(['coastlines', 'countryBorders', 'rivers'])
    // A download from before the tiers: coast_hires only
    cacheFiles(['/data/layers/coast_hires.geojson'])
    cacheFiles(getLayerFiles('countryBorders'))
    cacheFiles(getLayerFiles('rivers').slice(1))
    expect(await VectorLayerCache.getCachedLayers(await OfflineStorage.getDownloadState())).toEqual(['countryBorders'])
  })

  it('counts a completed download of this build as downloaded', async () => {
    markDownloaded([])
    cacheFiles(globeStartLayerUrls()) // every download stores the start files first
    await VectorLayerCache.downloadLayer('coastlines')
    markDownloaded(['coastlines'])
    expect(await VectorLayerCache.getCachedLayers(await OfflineStorage.getDownloadState())).toEqual(['coastlines'])
  })

  it('does not count files the service worker cached without a download', async () => {
    markDownloaded([])
    cacheFiles(getLayerFiles('countryBorders'))
    expect(await VectorLayerCache.getCachedLayers(await OfflineStorage.getDownloadState())).toEqual([])
  })

  it('keeps the download mark of the paleoshorelines, which are not globe layer files', async () => {
    markDownloaded(['paleoshorelines'])
    expect(await VectorLayerCache.getCachedLayers(await OfflineStorage.getDownloadState())).toEqual(['paleoshorelines'])
  })

  it('does not mark a layer downloaded when a file failed', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response('missing', { status: url.includes('detail') ? 404 : 200 })))
    await expect(VectorLayerCache.downloadLayer('countryBorders')).rejects.toThrow(/borders_detail.*404/)
    expect(OfflineStorage.addDownloadedLayer).not.toHaveBeenCalled()
  })
})
