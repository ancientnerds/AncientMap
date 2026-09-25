/**
 * Built files the service worker must not precache, imported by vite.config.ts
 * (workbox globIgnores) and by its test. Pure data.
 *
 * Workbox installs a worker only when every precache URL answers 200: one 404
 * rejects the install ("bad-precaching-response"), and the browser keeps the
 * worker it had - with that worker's globe.html, gate and pages - for good.
 * site.html is built as the template the API reads from disk for
 * /sites/{country}/{slug}; its own URL is proxied to the API (nginx
 * `location = /site.html`), which 301s /site.html?id= and answers the bare
 * path 404 since 2026-09-12. From then on no worker installed anywhere: a
 * founder's phone still showed the phone gate of before 24 Sep on 25 Sep, and
 * Umami logged "Failed to register/update a ServiceWorker" from 17 Sep.
 * research.html is the same kind of template (301 to /research/).
 */
export const PRECACHE_GLOB_IGNORES = [
  // Large data files
  '**/data/**',
  // The founders dashboard lives on another host
  'dashboard.html',
  // Templates of server-rendered pages, whose own URL nginx sends to the API
  'site.html',
  'research.html',
]
