/**
 * Shared helpers for video scene scripts.
 */

import type { Page } from 'puppeteer'

/**
 * Flush 2 RAFs so the Three.js renderer catches up after state changes.
 * Call this after any awaited demo API call (setFilterMode, setSatellite, etc.)
 * but before capture() so the first captured frame shows the new state.
 */
export const settle = (page: Page) => page.evaluate(
  'new Promise(function(r) { requestAnimationFrame(function() { requestAnimationFrame(r); }); })'
)
