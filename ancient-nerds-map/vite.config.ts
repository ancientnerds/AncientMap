import { defineConfig, loadEnv, type Connect, type Plugin } from 'vite'
import { resolve, extname } from 'path'
import { execSync } from 'child_process'
import { createReadStream, existsSync, readFileSync, statSync } from 'fs'
import { createGzip } from 'zlib'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

import { countryLinksHtml, pickSnapshotPath, type CountryHub } from './src/landing/hubsHtml'
import { GLOBE_START_PRECACHE } from './src/pwa/globeStartPrecache'
import { RUNTIME_CACHING } from './src/pwa/runtimeCaching'
import { serviceWorkerSnippetFor } from './src/pwa/serviceWorkerSnippet'

const commitHash = execSync('git rev-parse --short HEAD').toString().trim()
const buildTime = new Date().toISOString()

// Dev server and `vite preview`: serve /data/ from repo-root public/data/
// (production uses the nginx alias)
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
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    if (!req.url) return next()
    const clean = decodeURIComponent(req.url.split('?')[0])
    const filePath = resolve(dataRoot, clean.startsWith('/') ? clean.slice(1) : clean)
    if (!filePath.startsWith(dataRoot)) return next()
    const stat = statSync(filePath, { throwIfNoEntry: false })
    if (!stat?.isFile()) return next()
    const contentType = mimeTypes[extname(filePath)] || 'application/octet-stream'
    res.setHeader('Content-Type', contentType)
    res.setHeader('Access-Control-Allow-Origin', '*')
    // Mirror production nginx (gzip level 6, gzip_min_length 1024, gzip_types
    // with application/json): .json goes out compressed, .geojson (served as
    // octet-stream there) and .webp do not — so byte counts of a local probe
    // match what a visitor downloads.
    if (contentType === 'application/json') {
      res.setHeader('Vary', 'Accept-Encoding')
      if (stat.size >= 1024 && /\bgzip\b/.test(String(req.headers['accept-encoding'] ?? ''))) {
        res.setHeader('Content-Encoding', 'gzip')
        createReadStream(filePath).pipe(createGzip({ level: 6 })).pipe(res)
        return
      }
    }
    createReadStream(filePath).pipe(res)
  }
  return {
    name: 'serve-public-data',
    // Registered directly (not as a post hook) in both servers, so it runs
    // before preview's SPA fallback, which would answer /data/* with
    // index.html and status 200.
    configureServer(server) {
      server.middlewares.use('/data', handler)
    },
    configurePreviewServer(server) {
      server.middlewares.use('/data', handler)
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

// Post-build tuning of the HTML entries: the service-worker snippet
// (src/pwa/serviceWorkerSnippet.ts: none on the globe and the dashboard), and
// on the landing page also CSS that does not block rendering (its critical
// CSS is inlined in <style>).
function tuneLandingHtml() {
  return {
    name: 'tune-landing-html',
    enforce: 'post' as const,
    transformIndexHtml: {
      order: 'post' as const,
      handler(html: string, ctx: { filename: string }) {
        // The dashboard lives on stats.ancientnerds.com: no worker, no manifest.
        if (ctx.filename.endsWith('dashboard.html')) {
          return html.replace('<link rel="manifest" href="/manifest.webmanifest">', '')
        }
        const children = serviceWorkerSnippetFor(ctx.filename)
        if (children === null) return html
        const tags = [{ tag: 'script', children, injectTo: 'head' as const }]
        if (!ctx.filename.endsWith('index.html')) return { html, tags }
        // Make landing CSS non-render-blocking (critical CSS is inlined)
        html = html.replace(
          /<link\b([^>]*)href="(\/assets\/landing-[^"]+\.css)"([^>]*)>/g,
          (_match: string, before: string, href: string, after: string) => {
            if (_match.includes('media=')) return _match
            return `<link rel="stylesheet" href="${href}" media="print" onload="this.media='all'" />\n    <noscript><link rel="stylesheet" href="${href}" /></noscript>`
          }
        )
        return { html, tags }
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
// data-do-not-track honours the browser's DNT signal. dashboard.html gets no
// tag: the founders' own visits stay out of the numbers they read.
function analyticsTag(websiteId: string | undefined): Plugin {
  return {
    name: 'analytics-tag',
    transformIndexHtml: {
      order: 'post' as const,
      handler(html: string, ctx: { filename: string }) {
        if (!websiteId || ctx.filename.endsWith('dashboard.html')) return html
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
        // The founders dashboard (stats.ancientnerds.com/); untracked, see analyticsTag.
        dashboard: resolve(__dirname, 'dashboard.html'),
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
      // tuneLandingHtml() writes the registration itself — see SW_INSTALL.
      injectRegister: null,
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
        // Don't pre-cache large data files, nor the founders dashboard (other host)
        globIgnores: ['**/data/**', 'dashboard.html'],
        // ...except the globe's coastline and border start tiers of this build
        // (content-hashed, ~2.1 MB raw): an offline start of this globe.html needs
        // exactly these, and the first visit after a deploy runs the old JS
        // (src/pwa/globeStartPrecache.ts)
        additionalManifestEntries: GLOBE_START_PRECACHE,
        // Increase file size limit for larger bundles
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024, // 6 MB

        // Runtime caching strategies (src/pwa/runtimeCaching.ts, tested there)
        runtimeCaching: RUNTIME_CACHING,
      }
    }),
    tuneLandingHtml(),
  ],
}))
