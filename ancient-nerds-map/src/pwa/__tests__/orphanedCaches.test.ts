/**
 * Browsers that installed an earlier service worker keep Cache Storage that
 * nothing reads any more: the `natural-earth` bucket of the old GitHub border
 * rule, and GitHub URLs that old Download Manager runs put into
 * `vector-layers` (the globe's layers are self-hosted now). The globe's `sw`
 * background task removes them once the worker is registered. Node
 * environment: `caches`, `navigator`, `document` and `window` are stubbed.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

const GITHUB = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_boundary_lines_land.geojson'
const GITHUB_RIVERS = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_rivers_lake_centerlines.geojson'
const LOCAL_COAST = 'https://ancientnerds.com/data/layers/globe/coast_start.1a2b3c4d.json'
const LOCAL_RIVERS = 'https://ancientnerds.com/data/layers/ne_110m_rivers.geojson'

/** A CacheStorage over plain maps, with the calls the browser API has. */
function fakeCacheStorage(initial: Record<string, string[]>) {
  const buckets = new Map<string, Map<string, Response>>()
  for (const [name, urls] of Object.entries(initial)) {
    buckets.set(name, new Map(urls.map(url => [url, new Response('{}')])))
  }
  const opened: string[] = []
  const cacheOf = (bucket: Map<string, Response>) => ({
    keys: vi.fn(async () => [...bucket.keys()].map(url => new Request(url))),
    delete: vi.fn(async (req: Request | string) => bucket.delete(typeof req === 'string' ? req : req.url)),
  })
  const storage = {
    has: vi.fn(async (name: string) => buckets.has(name)),
    delete: vi.fn(async (name: string) => buckets.delete(name)),
    open: vi.fn(async (name: string) => {
      opened.push(name)
      if (!buckets.has(name)) buckets.set(name, new Map())
      return cacheOf(buckets.get(name)!)
    }),
  }
  const urls = (name: string) => (buckets.has(name) ? [...buckets.get(name)!.keys()] : null)
  return { storage: storage as unknown as CacheStorage, raw: storage, urls, opened }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('pruneOrphanedCaches', () => {
  it('deletes the natural-earth cache and the GitHub entries of vector-layers, nothing else', async () => {
    const { pruneOrphanedCaches } = await import('../orphanedCaches')
    const c = fakeCacheStorage({
      'natural-earth': [GITHUB],
      'vector-layers': [GITHUB, LOCAL_COAST, GITHUB_RIVERS, LOCAL_RIVERS],
      basemaps: ['https://ancientnerds.com/data/basemaps/gray_dark_med.webp'],
    })
    await pruneOrphanedCaches(c.storage)
    expect(c.urls('natural-earth')).toBeNull()
    expect(c.urls('vector-layers')).toEqual([LOCAL_COAST, LOCAL_RIVERS])
    expect(c.urls('basemaps')).toEqual(['https://ancientnerds.com/data/basemaps/gray_dark_med.webp'])
  })

  it('does not create a vector-layers cache that is not there', async () => {
    const { pruneOrphanedCaches } = await import('../orphanedCaches')
    const c = fakeCacheStorage({})
    await pruneOrphanedCaches(c.storage)
    expect(c.raw.delete).toHaveBeenCalledWith('natural-earth')
    expect(c.opened).toEqual([])
    expect(c.urls('vector-layers')).toBeNull()
  })

  it('a second run finds nothing to do', async () => {
    const { pruneOrphanedCaches } = await import('../orphanedCaches')
    const c = fakeCacheStorage({ 'natural-earth': [GITHUB], 'vector-layers': [GITHUB, LOCAL_COAST] })
    await pruneOrphanedCaches(c.storage)
    await pruneOrphanedCaches(c.storage)
    expect(c.urls('vector-layers')).toEqual([LOCAL_COAST])
  })

  it('a storage failure rejects (the queue reports it as bg:sw)', async () => {
    const { pruneOrphanedCaches } = await import('../orphanedCaches')
    const c = fakeCacheStorage({ 'vector-layers': [GITHUB] })
    const err = new DOMException('The operation is insecure.', 'SecurityError')
    c.raw.delete.mockRejectedValueOnce(err)
    await expect(pruneOrphanedCaches(c.storage)).rejects.toBe(err)
  })

  it('touches no browser global when imported (SSR-safe module scope)', async () => {
    vi.stubGlobal('caches', undefined)
    vi.stubGlobal('navigator', undefined)
    vi.stubGlobal('window', undefined)
    vi.stubGlobal('document', undefined)
    const mod = await import('../orphanedCaches')
    expect(typeof mod.pruneOrphanedCaches).toBe('function')
  })
})

describe('serviceWorkerTask (the globe background task sw)', () => {
  function stubBrowser(register: ReturnType<typeof vi.fn> | null, cacheStorage: CacheStorage) {
    vi.stubGlobal('navigator', register ? { serviceWorker: { register } } : {})
    vi.stubGlobal('document', { readyState: 'complete' })
    vi.stubGlobal('window', { addEventListener: vi.fn() })
    vi.stubGlobal('caches', cacheStorage)
  }

  it('registers the worker, then removes the orphaned caches', async () => {
    const c = fakeCacheStorage({ 'natural-earth': [GITHUB], 'vector-layers': [GITHUB, LOCAL_COAST] })
    const register = vi.fn(async () => {
      expect(c.urls('natural-earth')).not.toBeNull() // not before the registration
      return {}
    })
    stubBrowser(register, c.storage)
    const { serviceWorkerTask } = await import('../registerServiceWorker')
    await serviceWorkerTask()
    expect(register).toHaveBeenCalledWith('/sw.js', { scope: '/' })
    expect(c.urls('natural-earth')).toBeNull()
    expect(c.urls('vector-layers')).toEqual([LOCAL_COAST])
  })

  it('leaves the caches alone when the registration is refused, and rejects with the refusal', async () => {
    const c = fakeCacheStorage({ 'natural-earth': [GITHUB] })
    const refusal = new Error('Failed to register a ServiceWorker: The operation is insecure.')
    stubBrowser(vi.fn().mockRejectedValue(refusal), c.storage)
    const { serviceWorkerTask } = await import('../registerServiceWorker')
    await expect(serviceWorkerTask()).rejects.toBe(refusal)
    expect(c.urls('natural-earth')).toEqual([GITHUB])
  })

  it('does nothing where the browser has no service workers', async () => {
    const c = fakeCacheStorage({ 'natural-earth': [GITHUB] })
    stubBrowser(null, c.storage)
    const { serviceWorkerTask } = await import('../registerServiceWorker')
    await serviceWorkerTask()
    expect(c.raw.delete).not.toHaveBeenCalled()
  })
})
