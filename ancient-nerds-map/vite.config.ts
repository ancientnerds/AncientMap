import { defineConfig, loadEnv, type Plugin } from 'vite'
import { resolve, extname } from 'path'
import { execSync } from 'child_process'
import { createReadStream, existsSync, readFileSync, statSync } from 'fs'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

import { countryLinksHtml, pickSnapshotPath, type CountryHub } from './src/landing/hubsHtml'

const commitHash = execSync('git rev-parse --short HEAD').toString().trim()
const buildTime = new Date().toISOString()

// Dev only: serve /data/ from repo-root public/data/ (production uses nginx alias)
// Backend for /api and /goto in dev. Defaults to the local API container; the
// video recorder points it at production (VITE_DEV_API_TARGET=https://ancientnerds.com)
// so the globe has real site dots without a local database.
const DEV_API_TARGET = process.env.VITE_DEV_API_TARGET ?? 'http://localhost:8000'
// The video recorder's dev server must never hot-reload: an edit anywhere in
// src/ during a take reloads the page and kills the capture ("Execution
// context was destroyed", 17.09. — another session was editing the frontend).
const VIDEO_RECORD = process.env.VIDEO_RECORD === '1'

function servePublicData(): Plugin {
  const dataRoot = resolve(__dirname, '..', 'public', 'data')
  const mimeTypes: Record<string, string> = {
    '.json': 'application/json',
    '.geojson': 'application/geo+json',
    '.webp': 'image/webp',
    '.jpg': 'image/jpeg',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.gz': 'application/gzip',
  }
  return {
    name: 'serve-public-data',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        if (!req.url) return next()
        const clean = decodeURIComponent(req.url.split('?')[0])
        const filePath = resolve(dataRoot, clean.startsWith('/') ? clean.slice(1) : clean)
        if (!filePath.startsWith(dataRoot)) return next()
        try {
          if (!existsSync(filePath) || !statSync(filePath).isFile()) return next()
        } catch { return next() }
        res.setHeader('Content-Type', mimeTypes[extname(filePath)] || 'application/octet-stream')
        res.setHeader('Access-Control-Allow-Origin', '*')
        createReadStream(filePath).pipe(res)
      })
    },
  }
}

// Commit-Hash und Build-Zeit als <meta> in jede Entry-HTML — NICHT als
// define in die Chunks. Als define landete der Hash über DataStore.ts in 28
// von 101 Chunks und gab ihnen bei jedem Deploy einen neuen Content-Hash,
// obwohl sich kein Quellcode geändert hatte; Googlebot verbrannte daraufhin
// zwei Drittel seines Budgets auf /assets/ (Belege in src/constants/buildInfo.ts).
// .html trägt no-cache, /assets/ ein Jahr immutable — der wechselnde Wert
// gehört deshalb ins Dokument.
function buildInfoMeta(): Plugin {
  return {
    name: 'build-info-meta',
    transformIndexHtml: {
      order: 'pre',
      handler(html: string) {
        return html.replace(
          '</head>',
          `  <meta name="an-build-hash" content="${commitHash}">\n` +
            `    <meta name="an-build-time" content="${buildTime}">\n  </head>`,
        )
      },
    },
  }
}

// Build time: bake the country hubs into index.html. The homepage is static,
// so this is its only crawlable link path to the 98 /sites/{country} pages
// (see hubsHtml.ts). The papers are linked by /research/, which the research
// portal opens.
// Data: the pipeline's public/data/hubs.snapshot.json when present (VPS,
// rewritten at every export and paper publish), else the committed
// src/data baseline. A missing placeholder or an empty snapshot fails the
// build on purpose.
function landingHubs(): Plugin {
  return {
    name: 'landing-hubs',
    transformIndexHtml: {
      order: 'pre',
      handler(html: string, ctx: { filename: string }) {
        if (!ctx.filename.endsWith('index.html')) return html
        const snapshotPath = pickSnapshotPath(
          [
            resolve(__dirname, '..', 'public', 'data', 'hubs.snapshot.json'),
            resolve(__dirname, 'src', 'data', 'hubs.snapshot.json'),
          ],
          existsSync,
        )
        const snapshot = JSON.parse(readFileSync(snapshotPath, 'utf8')) as {
          exported_at: string
          countries: CountryHub[]
        }
        console.log(
          `[landing-hubs] ${snapshotPath}: ${snapshot.countries.length} countries (exported ${snapshot.exported_at})`,
        )
        const marker = '<!-- hubs:countries -->'
        if (!html.includes(marker)) throw new Error(`index.html lost its ${marker} placeholder`)
        return html.replace(marker, countryLinksHtml(snapshot.countries))
      },
    },
  }
}

// Post-build tuning of the HTML entries. On every page: registerSW deferred.
// On the landing page only: CSS non-render-blocking (the critical CSS is
// inlined in <style>), and no service-worker INSTALL — the precache is the
// whole app (139 files, 5.8 MB), which a first visit to the homepage has no
// business downloading on a phone (owner, 2026-09-10: "The landing page must
// load super fast — and mobile first!"). The app pages register it; the
// homepage only asks an already installed worker to update itself, so a
// visitor with an old worker still gets the one that lets "/" through.
function tuneLandingHtml() {
  return {
    name: 'tune-landing-html',
    enforce: 'post' as const,
    transformIndexHtml: {
      order: 'post' as const,
      handler(html: string, ctx: { filename: string }) {
        // Make registerSW non-render-blocking on all pages (it already waits for 'load' internally)
        html = html.replace(
          '<script id="vite-plugin-pwa:register-sw" src="/registerSW.js">',
          '<script id="vite-plugin-pwa:register-sw" src="/registerSW.js" defer>'
        )
        // The four SSR templates serve ~7,000 indexed landing pages; a
        // visitor arriving from Google gets the same update-only snippet as
        // the homepage (see comment above). The app entries still install.
        const updateOnly = ['index.html', 'site.html', 'story.html', 'research.html', 'articles.html']
        if (!updateOnly.some(name => ctx.filename.endsWith(name))) return html
        html = html.replace(
          '<script id="vite-plugin-pwa:register-sw" src="/registerSW.js" defer></script>',
          '<script>if("serviceWorker" in navigator)addEventListener("load",function(){navigator.serviceWorker.getRegistration().then(function(r){if(r)r.update()})})</script>'
        )
        if (!ctx.filename.endsWith('index.html')) return html
        // Make landing CSS non-render-blocking (critical CSS is inlined)
        html = html.replace(
          /<link\b([^>]*)href="(\/assets\/landing-[^"]+\.css)"([^>]*)>/g,
          (_match: string, before: string, href: string, after: string) => {
            if (_match.includes('media=')) return _match
            return `<link rel="stylesheet" href="${href}" media="print" onload="this.media='all'" />\n    <noscript><link rel="stylesheet" href="${href}" /></noscript>`
          }
        )
        return html
      }
    }
  }
}

// Umami tracker on every entry, and therefore on every server-rendered page
// built from one (pipeline/app_shell.py keeps the shell's <head> scripts).
// Self-hosted and cookieless; /pulse.js and /api/pulse are our own paths,
// proxied by nginx to the umami container. The Python error pages emit the
// same tag (pipeline/article_html_renderer.py analytics_tag) — the test in
// tests/pipeline/test_analytics_tag.py keeps the two markup strings equal.
// data-do-not-track honours the browser's DNT signal.
function analyticsTag(websiteId: string | undefined): Plugin {
  return {
    name: 'analytics-tag',
    transformIndexHtml: {
      order: 'post' as const,
      handler(html: string) {
        if (!websiteId) return html
        return html.replace(
          '</head>',
          `  <script defer src="/pulse.js" data-website-id="${websiteId}" data-do-not-track="true"></script>\n  </head>`
        )
      }
    }
  }
}

export default defineConfig(({ isSsrBuild, mode }) => ({
  envDir: '..',
  build: {
    // The SSR bundle is imported by the node sidecar, which serves no static
    // files — copying public/ (61 MB of textures; 1.5 GB if a stale
    // public/data/ exists locally) into dist-ssr/ only bloats the image.
    copyPublicDir: !isSsrBuild,
    rollupOptions: {
      input: {
        landing: resolve(__dirname, 'index.html'),
        main: resolve(__dirname, 'globe.html'),
        news: resolve(__dirname, 'news.html'),
        story: resolve(__dirname, 'story.html'),
        radar: resolve(__dirname, 'radar.html'),
        lyra: resolve(__dirname, 'lyra.html'),
        lyraOps: resolve(__dirname, 'lyra-ops.html'),
        db: resolve(__dirname, 'db.html'),
        articles: resolve(__dirname, 'articles.html'),
        account: resolve(__dirname, 'account.html'),
        search: resolve(__dirname, 'search.html'),
        site: resolve(__dirname, 'site.html'),
        api: resolve(__dirname, 'api.html'),
        cards: resolve(__dirname, 'cards.html'),
        game: resolve(__dirname, 'game.html'),
        theo: resolve(__dirname, 'theo.html'),
        research: resolve(__dirname, 'research.html'),
        knowledge: resolve(__dirname, 'knowledge.html'),
        library: resolve(__dirname, 'library.html'),
        imprint: resolve(__dirname, 'imprint.html'),
        privacy: resolve(__dirname, 'privacy.html'),
        terms: resolve(__dirname, 'terms.html'),
      },
    },
  },
  server: {
    ...(VIDEO_RECORD ? { hmr: false, watch: { ignored: ['**'] } } : {}),
    proxy: {
      '/api/': {
        target: DEV_API_TARGET,
        changeOrigin: true,
        timeout: 60000, // 60 seconds - backend connectors can take time
      },
      // Funnel redirect (api/routes/goto.py) — without this, a Discord CTA
      // click in dev lands on the SPA fallback instead of the 302
      '/goto/': {
        target: DEV_API_TARGET,
        changeOrigin: true,
      }
    }
  },
  plugins: [
    buildInfoMeta(),
    // The deploy's .env (envDir '..') names the Umami website; local
    // builds and dev have no id and stay untracked.
    analyticsTag(loadEnv(mode, resolve(__dirname, '..'), 'VITE_').VITE_UMAMI_WEBSITE_ID),
    landingHubs(),
    servePublicData(),
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'Ancient Nerds Research Platform',
        short_name: 'Ancient Map',
        description: 'Interactive 3D globe of 1.7M+ archaeological sites worldwide',
        theme_color: '#0a1520',
        background_color: '#0a1520',
        display: 'standalone',
        icons: [
          {
            src: '/favicon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable'
          }
        ]
      },
      workbox: {
        // The homepage is server-rendered (GET /home via nginx), so the
        // precached index.html must never answer "/". precacheAndRoute's
        // default directoryIndex ('index.html') would rewrite that navigation
        // to /index.html and serve it from the precache before the
        // NavigationRoute (and its denylist) is ever consulted. Every SPA page
        // here is an explicit .html URL — nothing needs a directory index.
        directoryIndex: null,
        // No navigation fallback. Every SPA page is an explicit .html URL that
        // precacheAndRoute serves on its own, and everything else — "/", the
        // SSR trees (/sites/, /research/, /articles/, /news-archive/), /api/,
        // /goto/, the sitemaps — is server-rendered or a backend route that
        // must reach the network. So the fallback only ever answered unknown
        // paths, with the app shell instead of the server's 404 (2026-09-17;
        // nginx sends those to GET /not-found now). The denylist that kept
        // the fallback off the routes above went with it.
        navigateFallback: null,
        // Pre-cache app shell assets
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        // Don't pre-cache large data files
        globIgnores: ['**/data/**'],
        // Increase file size limit for larger bundles
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024, // 6 MB

        // Runtime caching strategies
        runtimeCaching: [
          // API sites endpoint - Network First with offline fallback
          {
            urlPattern: /\/api\/sites\//,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-sites',
              networkTimeoutSeconds: 10,
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          // API sources endpoint - Stale While Revalidate
          {
            urlPattern: /\/api\/sources/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-sources',
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          // Basemap images - Cache First (manually cached by user)
          {
            urlPattern: /\/data\/basemaps\/.*\.(jpg|png)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'basemaps',
              cacheableResponse: {
                statuses: [0, 200]
              },
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 60 * 60 * 24 * 365 // 1 year
              }
            }
          },
          // Historical empire GeoJSON - Cache First (manually cached)
          {
            urlPattern: /\/data\/historical\/.*\.geojson$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'historical-data',
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          // Vector layer data - Stale While Revalidate
          {
            urlPattern: /\/data\/layers\/.*\.json$/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'vector-layers',
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          // Sources metadata JSON
          {
            urlPattern: /\/data\/sources\.json/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'static-data',
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          // External images (Wikipedia) - Network First with short timeout
          {
            urlPattern: /^https:\/\/upload\.wikimedia\.org\//,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'external-images',
              networkTimeoutSeconds: 5,
              cacheableResponse: {
                statuses: [0, 200]
              },
              expiration: {
                maxEntries: 1000,  // Increased from 200 for field users with many sites
                maxAgeSeconds: 60 * 60 * 24 * 30 // 30 days
              }
            }
          },
          // Natural Earth vector data from GitHub
          {
            urlPattern: /^https:\/\/raw\.githubusercontent\.com\/nvkelso\/natural-earth-vector\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'natural-earth',
              cacheableResponse: {
                statuses: [0, 200]
              },
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 60 * 60 * 24 * 365 // 1 year
              }
            }
          }
        ]
      }
    }),
    tuneLandingHtml(),
  ],
}))
