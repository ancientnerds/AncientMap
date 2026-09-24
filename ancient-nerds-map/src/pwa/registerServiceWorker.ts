/**
 * Registers the service worker on globe.html. The other pages keep the inline
 * snippet that vite.config.ts writes (serviceWorkerSnippet.ts); the globe
 * does it here, as the last task of its background queue, because the
 * worker's install precaches ~6.9 MB (JS incl. the lazy Mapbox chunk, fonts)
 * and on a first visit that download competed with the globe's critical load.
 *
 * Same semantics as SW_INSTALL: only where the browser has service workers
 * (feature detection), not before window 'load', `/sw.js` with scope `/`.
 * A refusal (private mode, blocked storage) rejects with the browser's error:
 * the caller reports it (the queue logs it and tracks `globe_error` with phase
 * `bg:sw`), so it is neither swallowed nor left as an unhandled rejection.
 *
 * Resolves true once the worker is registered, false where the browser has no
 * service workers.
 *
 * No browser access at module scope (SSR import safety).
 */

import { pruneOrphanedCaches } from './orphanedCaches'

export async function registerServiceWorker(): Promise<boolean> {
  if (!('serviceWorker' in navigator)) return false
  if (document.readyState !== 'complete') {
    await new Promise<void>(resolve => window.addEventListener('load', () => resolve(), { once: true }))
  }
  await navigator.serviceWorker.register('/sw.js', { scope: '/' })
  return true
}

/**
 * The globe's background task `sw`: the worker, then the caches earlier
 * workers left behind (orphanedCaches.ts). Rejects on a refusal or a storage
 * failure; the queue reports it as `bg:sw`.
 */
export async function serviceWorkerTask(): Promise<void> {
  if (!(await registerServiceWorker())) return
  await pruneOrphanedCaches(caches)
}
