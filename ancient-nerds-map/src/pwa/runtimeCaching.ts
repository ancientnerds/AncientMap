/**
 * Runtime caching rules of the service worker, imported by vite.config.ts
 * (VitePWA → workbox-build serialises the RegExps into sw.js) and by its test.
 * Pure data: no browser or node access, RegExps only.
 *
 * How workbox reads this table (node_modules/workbox-routing/RegExpRoute.js):
 * - `regExp.exec(url.href)` runs on the full href, query string included, so a
 *   pattern ending in `$` never matches `…?_v=<hash>`: end with `(\?|$)`.
 * - The first registered route that matches wins, so a specific rule has to
 *   come before a generic one for the same path.
 * - Cross-origin URLs only match at index 0 (hence `^https://…`).
 */

import type { VitePWAOptions } from 'vite-plugin-pwa'

type RuntimeCaching = NonNullable<NonNullable<Partial<VitePWAOptions>['workbox']>['runtimeCaching']>

const ONE_YEAR = 60 * 60 * 24 * 365

export const RUNTIME_CACHING: RuntimeCaching = [
  // API sites endpoint - Network First with offline fallback. The globe asks
  // with a per-deploy `_v`, so every deploy adds entries: bounded here.
  {
    urlPattern: /\/api\/sites\//,
    handler: 'NetworkFirst',
    options: {
      cacheName: 'api-sites',
      networkTimeoutSeconds: 10,
      cacheableResponse: { statuses: [0, 200] },
      expiration: { maxEntries: 8 },
    },
  },
  // API sources endpoint - Stale While Revalidate
  {
    urlPattern: /\/api\/sources/,
    handler: 'StaleWhileRevalidate',
    options: {
      cacheName: 'api-sources',
      cacheableResponse: { statuses: [0, 200] },
    },
  },
  // Basemap images - Cache First. The tiers are .webp (the old `(jpg|png)$`
  // rule never matched them, so repeat visits re-downloaded every basemap).
  // Unversioned file names: the content is stable. The offline download
  // (BasemapCache) writes into the same cache under the same URL.
  {
    urlPattern: /\/data\/basemaps\/[^/?]+\.(webp|jpg|png)(\?|$)/,
    handler: 'CacheFirst',
    options: {
      cacheName: 'basemaps',
      cacheableResponse: { statuses: [0, 200] },
      expiration: { maxEntries: 10, maxAgeSeconds: ONE_YEAR },
    },
  },
  // Historical empire GeoJSON - Cache First (manually cached)
  {
    urlPattern: /\/data\/historical\/.*\.geojson(\?|$)/,
    handler: 'CacheFirst',
    options: {
      cacheName: 'historical-data',
      cacheableResponse: { statuses: [0, 200] },
    },
  },
  // Globe coastline/border tiers: the file name carries a content hash
  // (scripts/build_globe_layers.py), so a cached copy is never stale. Before
  // the generic layer rule, which would catch these URLs first. Same cache
  // name as the offline layer download, which OfflineFetch looks up.
  // maxEntries: four files per build, room for a few builds.
  {
    urlPattern: /\/data\/layers\/globe\/[^/?]+\.json(\?|$)/,
    handler: 'CacheFirst',
    options: {
      cacheName: 'vector-layers',
      cacheableResponse: { statuses: [0, 200] },
      expiration: { maxEntries: 16 },
    },
  },
  // Vector layer data - Stale While Revalidate
  {
    urlPattern: /\/data\/layers\/.*\.json(\?|$)/,
    handler: 'StaleWhileRevalidate',
    options: {
      cacheName: 'vector-layers',
      cacheableResponse: { statuses: [0, 200] },
    },
  },
  // Sources metadata JSON
  {
    urlPattern: /\/data\/sources\.json/,
    handler: 'StaleWhileRevalidate',
    options: {
      cacheName: 'static-data',
      cacheableResponse: { statuses: [0, 200] },
    },
  },
  // External images (Wikipedia) - Network First with short timeout
  {
    urlPattern: /^https:\/\/upload\.wikimedia\.org\//,
    handler: 'NetworkFirst',
    options: {
      cacheName: 'external-images',
      networkTimeoutSeconds: 5,
      cacheableResponse: { statuses: [0, 200] },
      expiration: {
        maxEntries: 1000, // Increased from 200 for field users with many sites
        maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
      },
    },
  },
  // Natural Earth vector data from GitHub
  {
    urlPattern: /^https:\/\/raw\.githubusercontent\.com\/nvkelso\/natural-earth-vector\//,
    handler: 'CacheFirst',
    options: {
      cacheName: 'natural-earth',
      cacheableResponse: { statuses: [0, 200] },
      expiration: { maxEntries: 50, maxAgeSeconds: ONE_YEAR },
    },
  },
]
