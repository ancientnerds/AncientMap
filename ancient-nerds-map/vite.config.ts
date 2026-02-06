import { defineConfig } from 'vite'
import { resolve } from 'path'
import { execSync } from 'child_process'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const commitHash = execSync('git rev-parse --short HEAD').toString().trim()
const buildTime = new Date().toISOString()

export default defineConfig({
  envDir: '..',
  define: {
    __BUILD_HASH__: JSON.stringify(commitHash),
    __BUILD_TIME__: JSON.stringify(buildTime),
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        news: resolve(__dirname, 'news.html'),
        discoveries: resolve(__dirname, 'lyra-discoveries.html'),
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 60000, // 60 seconds - backend connectors can take time
      }
    }
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'Ancient Nerds Research Platform',
        short_name: 'Ancient Map',
        description: 'Interactive 3D globe of 800K+ archaeological sites worldwide',
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
    })
  ],
})
