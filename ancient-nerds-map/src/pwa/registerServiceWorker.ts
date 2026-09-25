/**
 * Registers the service worker on globe.html. The other pages keep the inline
 * snippet that vite.config.ts writes (serviceWorkerSnippet.ts); the globe
 * does it here, as the last task of its background queue, because the
 * worker's install precaches ~8.8 MB (JS incl. the lazy Mapbox chunk, fonts,
 * the globe's start tiers: globeStartPrecache.ts)
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
  return (await registerWorker()) !== null
}

/** The registration; null where the browser has no service workers. */
async function registerWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null
  if (document.readyState !== 'complete') {
    await new Promise<void>(resolve => window.addEventListener('load', () => resolve(), { once: true }))
  }
  return navigator.serviceWorker.register('/sw.js', { scope: '/' })
}

/**
 * An offline download (DownloadManager) is unusable without an active worker:
 * its precache holds globe.html, the JS, the fonts and the coastline and
 * border start tiers an offline start needs,
 * and nothing else registers one for a globe-only visitor. The queue's `sw`
 * task may not have run yet (it is the last task, after the warp, and nothing
 * starts while the tab is hidden), so the download registers it itself
 * (idempotent) and waits until a worker is active. Rejects where the browser
 * has no service workers, on a refusal, and when the install fails (the worker
 * turns redundant, e.g. its precache could not be fetched).
 */
export async function ensureServiceWorkerActive(): Promise<void> {
  const registration = await registerWorker()
  if (!registration) throw new Error('this browser has no service workers')
  if (registration.active) return
  const worker = registration.installing ?? registration.waiting
  if (!worker) throw new Error('the service worker registration has no worker')
  await new Promise<void>((resolve, reject) => {
    const onStateChange = () => {
      if (worker.state === 'activated') {
        worker.removeEventListener('statechange', onStateChange)
        resolve()
      } else if (worker.state === 'redundant') {
        worker.removeEventListener('statechange', onStateChange)
        reject(new Error('the service worker could not install'))
      }
    }
    worker.addEventListener('statechange', onStateChange)
    onStateChange()
  })
}

/**
 * An installed worker looks for a new build now, not after the globe has
 * started. globe.html and its JS come cache-first from the precache, and the
 * one check for a new worker on this page used to be the queue's last task
 * (serviceWorkerTask). Behind the phone gate the globe never starts, so a phone
 * that always leaves the gate for another page kept the build of its first
 * visit: on 2026-09-25 a founder's phone still showed the six-button gate the
 * 24 Sep deploy had replaced. Only an existing registration: a first visit
 * still installs from the queue, after the globe, so its ~8.8 MB precache never
 * competes with the start. Resolves false where there is nothing to update.
 */
export async function updateInstalledServiceWorker(): Promise<boolean> {
  if (!('serviceWorker' in navigator)) return false
  const registration = await navigator.serviceWorker.getRegistration()
  if (!registration) return false
  await registration.update()
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
