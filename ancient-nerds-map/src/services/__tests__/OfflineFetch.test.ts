/**
 * @vitest-environment jsdom
 *
 * App offline mode answers only from Cache Storage. The globe's start tiers of
 * the build that runs may be only in the service worker's precache (the
 * worker installed them with its globe.html, src/pwa/globeStartPrecache.ts):
 * OfflineFetch reads that cache too, so an offline start finds them.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import manifest from '../../data/globeLayers.generated.json'
import { VECTOR_LAYER_CACHE, precacheCacheName } from '../../pwa/cacheNames'
import { OfflineFetch, OfflineNotCachedError } from '../OfflineFetch'

/** cache name -> absolute URL -> body */
let storage: Map<string, Map<string, string>>

function put(cacheName: string, url: string, body: string) {
  if (!storage.has(cacheName)) storage.set(cacheName, new Map())
  storage.get(cacheName)!.set(new URL(url, location.href).href, body)
}

beforeEach(() => {
  storage = new Map()
  vi.stubGlobal('caches', {
    open: async (name: string) => ({
      match: async (url: string) => {
        const body = storage.get(name)?.get(new URL(url, location.href).href)
        return body === undefined ? undefined : new Response(body)
      },
    }),
  })
  vi.stubGlobal('fetch', vi.fn(async () => new Response('network')))
  OfflineFetch.setOfflineMode(true)
})

afterEach(() => {
  OfflineFetch.setOfflineMode(false)
  vi.unstubAllGlobals()
})

describe('OfflineFetch in app offline mode', () => {
  it("answers a start tier from the service worker's precache", async () => {
    put(precacheCacheName(location.origin), manifest.coastlines.start, 'precached')
    const response = await OfflineFetch.fetch(manifest.coastlines.start)
    expect(await response.text()).toBe('precached')
    expect(await OfflineFetch.isCached(manifest.coastlines.start)).toBe(true)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('answers from the layer cache as before', async () => {
    put(VECTOR_LAYER_CACHE, manifest.countryBorders.start, 'downloaded')
    expect(await (await OfflineFetch.fetch(manifest.countryBorders.start)).text()).toBe('downloaded')
  })

  it('throws for a file no cache holds, without a request', async () => {
    await expect(OfflineFetch.fetch(manifest.countryBorders.start)).rejects.toBeInstanceOf(OfflineNotCachedError)
    expect(fetch).not.toHaveBeenCalled()
  })
})
