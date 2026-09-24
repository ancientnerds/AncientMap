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

/**
 * The three caches of /api/sites/ answers. workbox-expiration bounds each
 * cacheName as one LRU over every URL it wrote, so the kinds are split: the
 * many small per-site and search answers, or a user's opt-in sources, would
 * otherwise evict the globe's own payload, the one entry NetworkFirst's
 * timeout and offline fallback exist for. An admin save clears all three
 * (useAdminMode).
 */
export const API_SITES_CACHE_NAMES = ['api-sites-globe', 'api-sites-sources', 'api-sites'] as const

const API_SITES_NETWORK_FIRST = {
  networkTimeoutSeconds: 10,
  cacheableResponse: { statuses: [0, 200] },
}

export const RUNTIME_CACHING: RuntimeCaching = [
  // The globe's payloads: DataStore always loads source=ancient_nerds, with a
  // per-deploy `_v` (the globe keys and the full payload), and the offline
  // download asks for it without `_v`. Six = these three for the current and
  // the previous build. `(?![^&])`: the value ends at `&` or the end.
  {
    urlPattern: /\/api\/sites\/all\?(?:[^#]*&)?source=ancient_nerds(?![^&])/,
    handler: 'NetworkFirst',
    options: { cacheName: 'api-sites-globe', ...API_SITES_NETWORK_FIRST, expiration: { maxEntries: 6 } },
  },
  // Opt-in sources (SourceLoader, per-deploy `_v`; DownloadManager): room for
  // every source of the filter panel in one build.
  {
    urlPattern: /\/api\/sites\/all\?/,
    handler: 'NetworkFirst',
    options: { cacheName: 'api-sites-sources', ...API_SITES_NETWORK_FIRST, expiration: { maxEntries: 32 } },
  },
  // Everything else under /api/sites/: one small entry per opened site, its
  // alternates, and per distinct search query.
  {
    urlPattern: /\/api\/sites\//,
    handler: 'NetworkFirst',
    options: { cacheName: 'api-sites', ...API_SITES_NETWORK_FIRST, expiration: { maxEntries: 200 } },
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
]
