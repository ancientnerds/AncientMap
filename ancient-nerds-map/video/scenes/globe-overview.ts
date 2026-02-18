/**
 * Globe overview scene — 20-second clip for the "INTERACTIVE 3D GLOBE" section.
 *
 * Shows what makes the globe interactive: site tooltips, street-level Mapbox
 * with slow panning, and the site popup.
 *
 * Flow:
 *   0-3s   — Fly to Rome, zoom in close
 *   3-6s   — Tooltip on Colosseum (hold)
 *   6-8s   — Fly to Pyramids of Giza
 *   8-11s  — Tooltip on Great Pyramid (hold)
 *   11-13s — Enter Mapbox street level at Giza
 *   13-16s — Slow Mapbox pan around the Pyramids (frame-by-frame jumpTo)
 *   16-17s — Exit Mapbox, zoom back out
 *   17-20s — Open site popup for Great Pyramid
 *
 * IMPORTANT: Real-time waits (setTimeout) are used between state changes
 * to give React time to re-render. Capture segments are separated by
 * await calls that let the browser process DOM updates.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

/** Real-time wait — lets the browser process React state updates */
const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

async function runGlobeOverview(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // === SETUP ===
  await demo.setFilterMode('category')
  await demo.setAutoRotate(false)
  await demo.setZoom(2.0)
  await demo.setFlyToDuration(2000)
  // Enable tooltip visibility in demo mode
  await demo.setDemoTooltips(true)
  await wait(500) // Let CSS class apply
  await settle(page)

  // ─── 0-3s: Fly to Rome, zoom in ───
  console.log('  [0-3s] Fly to Rome, zoom in...')
  fire(`window.__DEMO.flyTo(12.49, 41.89)`)
  fire(`window.__DEMO.smoothZoom(2.0, 1.5, 2500)`)
  await recorder.capture(page, 3)

  // ─── 3-6s: Show tooltip on Colosseum ───
  console.log('  [3-6s] Tooltip: Colosseum...')
  await demo.selectSite('Colosseum')
  await wait(200) // Let React re-render the tooltip
  await settle(page)
  await recorder.capture(page, 3)

  // ─── 6-8s: Dismiss tooltip, fly to Pyramids of Giza ───
  console.log('  [6-8s] Fly to Pyramids...')
  await demo.deselectSite()
  await settle(page)
  fire(`window.__DEMO.flyTo(31.13, 29.98)`)
  await recorder.capture(page, 2)

  // ─── 8-11s: Show tooltip on Great Pyramid ───
  console.log('  [8-11s] Tooltip: Great Pyramid...')
  await demo.selectSite('Great Pyramid of Giza')
  await wait(200)
  await settle(page)
  await recorder.capture(page, 3)

  // ─── 11-13s: Dismiss tooltip, enter Mapbox street level ───
  console.log('  [11-13s] Enter Mapbox street level...')
  await demo.deselectSite()
  await demo.setDemoTooltips(false)
  await settle(page)
  // enterMapbox now waits for initialization + CSS transition
  await demo.enterMapbox()
  // Set initial Mapbox camera at Giza, zoomed in to street level
  await demo.mapboxJumpTo(31.134, 29.979, 16)
  await wait(1500) // Let Mapbox tiles load
  await settle(page)
  await recorder.capture(page, 2)

  // ─── 13-16s: Slow Mapbox pan (frame-by-frame jumpTo) ───
  // We can't use easeTo because it uses RAF timestamps, not synthetic time.
  // Instead, capture in 0.5s segments with small jumpTo shifts between them.
  console.log('  [13-16s] Mapbox slow pan...')
  const panSteps = 6
  const startLng = 31.134, startLat = 29.979
  const endLng = 31.140, endLat = 29.982
  for (let i = 0; i < panSteps; i++) {
    const t = (i + 1) / panSteps
    const lng = startLng + (endLng - startLng) * t
    const lat = startLat + (endLat - startLat) * t
    await demo.mapboxJumpTo(lng, lat, 16)
    await settle(page)
    await recorder.capture(page, 0.5)
  }

  // ─── 16-17s: Exit Mapbox ───
  console.log('  [16-17s] Exit Mapbox...')
  await demo.exitMapbox()
  await wait(300) // Let CSS transition complete
  fire(`window.__DEMO.smoothZoom(1.5, 1.7, 800)`)
  await settle(page)
  await recorder.capture(page, 1)

  // ─── 17-20s: Open site popup ───
  console.log('  [17-20s] Site popup...')
  await demo.setDemoPopups(true)
  await wait(100)
  await demo.openSitePopup('Great Pyramid of Giza')
  await wait(500) // Let popup render + images start loading
  await settle(page)
  await recorder.capture(page, 3)

  // Cleanup
  await demo.closeAllPopups()
  await demo.setDemoPopups(false)
  await demo.setFlyToDuration(600)
  await demo.setDemoTooltips(false)
}

export const globeOverviewScene: SceneDefinition[] = [
  {
    name: 'globe-overview',
    duration: 20,
    resolution: 'section',
    run: runGlobeOverview,
  },
]
