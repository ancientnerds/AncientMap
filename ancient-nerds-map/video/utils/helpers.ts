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

/**
 * Advance synthetic time by `frames` ticks WITHOUT capturing. Lets an animation
 * play through once so tiles/labels along its path are loaded before the real
 * take (satellite globe zooms pop tiles in otherwise).
 */
export const advanceFrames = (page: Page, frames: number) => page.evaluate(`(async function() {
  for (var i = 0; i < ${frames}; i++) {
    window.__tickFrame();
    await new Promise(function(r) { requestAnimationFrame(function() { requestAnimationFrame(r); }); });
  }
})()`)
