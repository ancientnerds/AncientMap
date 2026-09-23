/**
 * Registers the service worker on globe.html. The other pages keep the inline
 * snippet that vite.config.ts writes (SW_INSTALL / SW_UPDATE_ONLY); the globe
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
 * No browser access at module scope (SSR import safety).
 */
export async function registerServiceWorker(): Promise<void> {
  if (!('serviceWorker' in navigator)) return
  if (document.readyState !== 'complete') {
    await new Promise<void>(resolve => window.addEventListener('load', () => resolve(), { once: true }))
  }
  await navigator.serviceWorker.register('/sw.js', { scope: '/' })
}
