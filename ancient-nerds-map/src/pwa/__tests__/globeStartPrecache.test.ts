/**
 * The coastline and border start tiers are content-hashed file names compiled
 * into the bundle (globeLayers.generated.json), and globe.html with its JS is
 * served cache-first from the service worker's precache. The first online
 * visit after a deploy therefore still runs the previous build's JS, which
 * never asks for the new start tiers; the next start, offline, runs the new
 * JS. Only the worker that serves that JS can hold its tiers: they ride in
 * its precache, and OfflineFetch reads that cache in app offline mode.
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import manifest from '../../data/globeLayers.generated.json'
import { precacheCacheName } from '../cacheNames'
import { GLOBE_START_PRECACHE } from '../globeStartPrecache'
import { SW_INSTALL } from '../serviceWorkerSnippet'

const APP = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const read = (path: string) => readFileSync(resolve(APP, path), 'utf-8')

describe('GLOBE_START_PRECACHE', () => {
  it('lists the start tier of every globe layer of the manifest the bundle is built with', () => {
    expect(GLOBE_START_PRECACHE).toEqual([
      { url: manifest.coastlines.start, revision: null },
      { url: manifest.countryBorders.start, revision: null },
    ])
  })

  it('goes into the worker build', () => {
    expect(read('vite.config.ts')).toContain('additionalManifestEntries: GLOBE_START_PRECACHE,')
  })

  it('is stored under its plain URL, the key OfflineFetch looks up (no revision: the name is the hash)', () => {
    // workbox-precaching's createCacheKey: an entry without a revision is keyed by its URL alone
    const createCacheKey = read('node_modules/workbox-precaching/utils/createCacheKey.js')
    expect(createCacheKey).toMatch(/if \(!revision\) \{\s*const urlObject = new URL\(url, location\.href\);\s*return \{\s*cacheKey: urlObject\.href,/)
  })
})

describe('precacheCacheName', () => {
  it("is workbox's precache cache for the worker registered at scope '/'", () => {
    const cacheNames = read('node_modules/workbox-core/_private/cacheNames.js')
    expect(cacheNames).toContain("precache: 'precache-v2',")
    expect(cacheNames).toContain("prefix: 'workbox',")
    expect(cacheNames).toContain("suffix: typeof registration !== 'undefined' ? registration.scope : '',")
    expect(precacheCacheName('https://ancientnerds.com')).toBe('workbox-precache-v2-https://ancientnerds.com/')
    // Both registrations use that scope
    expect(SW_INSTALL).toContain('register("/sw.js",{scope:"/"})')
    expect(read('src/pwa/registerServiceWorker.ts')).toContain("navigator.serviceWorker.register('/sw.js', { scope: '/' })")
  })
})
