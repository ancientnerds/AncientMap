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

import { getLayerFiles, LAYER_CONFIG, type VectorLayerKey } from '../../config/vectorLayers'
import { OfflineStorage } from '../OfflineStorage'
import { VectorLayerCache } from '../VectorLayerCache'

const KEYS = Object.keys(LAYER_CONFIG) as VectorLayerKey[]

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
    }),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.mocked(OfflineStorage.addDownloadedLayer).mockClear()
})

describe('VectorLayerCache', () => {
  it('offers every vector layer of the globe with its real file count', () => {
    for (const key of KEYS) {
      const info = VectorLayerCache.getLayerInfo(key)
      expect(info, key).toBeDefined()
      expect(info!.fileCount).toBe(getLayerFiles(key).length)
    }
  })

  it.each(KEYS)('downloads and stores exactly getLayerFiles(%s)', async key => {
    await VectorLayerCache.downloadLayer(key)
    expect(fetched).toEqual(getLayerFiles(key))
    expect([...stored.keys()]).toEqual(getLayerFiles(key))
    expect(OfflineStorage.addDownloadedLayer).toHaveBeenCalledWith(key)
  })

  it('clears exactly getLayerFiles', async () => {
    await VectorLayerCache.clearLayer('coastlines')
    expect(deleted).toEqual(getLayerFiles('coastlines'))
  })

  it('does not mark a layer downloaded when a file failed', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response('missing', { status: url.includes('detail') ? 404 : 200 })))
    await expect(VectorLayerCache.downloadLayer('countryBorders')).rejects.toThrow(/borders_detail.*404/)
    expect(OfflineStorage.addDownloadedLayer).not.toHaveBeenCalled()
  })
})
