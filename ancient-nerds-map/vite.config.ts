import { defineConfig, type Plugin } from 'vite'
import { resolve, extname } from 'path'
import { execSync } from 'child_process'
import { createReadStream, existsSync, readFileSync, statSync } from 'fs'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

import { countryLinksHtml, paperLinksHtml, pickSnapshotPath, type CountryHub, type PaperHub } from './src/landing/hubsHtml'

const commitHash = execSync('git rev-parse --short HEAD').toString().trim()
const buildTime = new Date().toISOString()

// Dev only: serve /data/ from repo-root public/data/ (production uses nginx alias)
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

// Build time: bake the country hubs and research papers into index.html.
// The homepage is static, so these are its only crawlable links to the 98
// /sites/{country} pages and the /research/{slug} papers (see hubsHtml.ts).
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
          papers: PaperHub[]
        }
        console.log(
          `[landing-hubs] ${snapshotPath}: ${snapshot.countries.length} countries, ${snapshot.papers.length} papers (exported ${snapshot.exported_at})`,
        )
        const fills: [string, string][] = [
          ['<!-- hubs:countries -->', countryLinksHtml(snapshot.countries)],
          ['<!-- hubs:papers -->', paperLinksHtml(snapshot.papers)],
        ]
        for (const [marker, replacement] of fills) {
          if (!html.includes(marker)) throw new Error(`index.html lost its ${marker} placeholder`)
          html = html.replace(marker, replacement)
        }
        return html
      },
    },
  }
}

// Post-build: make landing page CSS non-render-blocking (critical CSS is inlined in <style>)
function asyncLandingCss() {
  return {
    name: 'async-landing-css',
    enforce: 'post' as const,
    transformIndexHtml: {
      order: 'post' as const,
      handler(html: string, ctx: { filename: string }) {
        // Make registerSW non-render-blocking on all pages (it already waits for 'load' internally)
        html = html.replace(
          '<script id="vite-plugin-pwa:register-sw" src="/registerSW.js">',
          '<script id="vite-plugin-pwa:register-sw" src="/registerSW.js" defer>'
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

export default defineConfig(({ isSsrBuild }) => ({
  envDir: '..',
  define: {
    __BUILD_HASH__: JSON.stringify(commitHash),
    __BUILD_TIME__: JSON.stringify(buildTime),
  },
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
    proxy: {
      '/api/': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 60000, // 60 seconds - backend connectors can take time
      },
      // Funnel redirect (api/routes/goto.py) — without this, a Discord CTA
      // click in dev lands on the SPA fallback instead of the 302
      '/goto/': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  plugins: [
    landingHubs(),
    servePublicData(),
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'Ancient Nerds Research Platform',
        short_name: 'Ancient Map',
        description: 'Interactive 3D globe of 750K+ archaeological sites worldwide',
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
        // Don't serve index.html for backend routes or server-rendered SEO pages
        // (/articles/, /news-archive/, /research/, /sites/ are HTML from the API,
        // not SPA pages — the SW must let them hit the network)
        navigateFallbackDenylist: [
          /^\/api\//,
          /\.html(\?|$)/,
          /^\/articles\//,
          /^\/news-archive\//,
          /^\/research\//,
          /^\/sites\//,
          /^\/seo\//,
          /^\/sitemap/,
          // Funnel redirect: the SW must not answer with the SPA shell —
          // the whole point is that the click reaches the API log
          /^\/goto\//,
        ],
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
    asyncLandingCss(),
  ],
}))
