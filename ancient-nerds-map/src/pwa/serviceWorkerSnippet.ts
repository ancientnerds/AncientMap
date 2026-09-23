/**
 * The inline service-worker snippet each built HTML entry gets, imported by
 * vite.config.ts (tuneLandingHtml) and by its test. Pure data: no browser or
 * node access.
 *
 * Written here instead of by vite-plugin-pwa (`injectRegister: null`): its
 * registerSW.js calls register() without a catch, so every browser that
 * refuses a worker (private mode, blocked storage, a datacenter crawler) left
 * an unhandled rejection that boot.ts reported as a JavaScript error with
 * triple weight on the founders dashboard, for something that costs the
 * visitor nothing (2026-09-19). Inline and ~130 bytes: no request, and the
 * work waits for 'load' anyway.
 */

export const SW_INSTALL =
  'if("serviceWorker" in navigator)addEventListener("load",function(){navigator.serviceWorker.register("/sw.js",{scope:"/"}).catch(function(){})})'

// The four SSR templates serve ~7,000 indexed landing pages; a visitor
// arriving from Google only updates an already installed worker instead of
// downloading the whole precache (over 6 MB), which a first visit has
// no business doing on a phone (owner, 2026-09-10: "The landing page must
// load super fast — and mobile first!"). getRegistration() needs the catch
// for the same reason register() does.
export const SW_UPDATE_ONLY =
  'if("serviceWorker" in navigator)addEventListener("load",function(){navigator.serviceWorker.getRegistration().then(function(r){if(r)r.update()}).catch(function(){})})'

const SW_UPDATE_ONLY_PAGES = ['index.html', 'site.html', 'story.html', 'research.html', 'articles.html']

const NO_SNIPPET_PAGES = [
  // The globe registers the worker itself, as the last task of its
  // background queue (src/pwa/registerServiceWorker.ts): on 'load' the
  // precache download (~6.9 MB) ran in parallel with the globe's critical load.
  'globe.html',
  // The dashboard lives on stats.ancientnerds.com, where /sw.js would be
  // proxied to Umami (404) and a precache would run into the gate: no worker.
  'dashboard.html',
]

/** The snippet for the entry at `filename`, or null for an entry without one. */
export function serviceWorkerSnippetFor(filename: string): string | null {
  if (NO_SNIPPET_PAGES.some(name => filename.endsWith(name))) return null
  return SW_UPDATE_ONLY_PAGES.some(name => filename.endsWith(name)) ? SW_UPDATE_ONLY : SW_INSTALL
}
