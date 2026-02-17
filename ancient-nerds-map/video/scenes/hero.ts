/**
 * Hero scene — 60-second cinematic loop for the landing page hero background.
 *
 * Camera philosophy: NO BREATHING. No smoothZoom oscillation.
 * Visual interest comes from filter switches, empire reveals, layer toggles,
 * and purposeful single-direction zoom changes.
 *
 * 4 acts:
 *   Act 1 (0-20s)  — "The Living Planet" — filter cycling at fixed zoom
 *   Act 2 (20-40s) — "Iconic Sites" — flyTo hops with empires
 *   Act 3 (40-55s) — "Layers of Time" — satellite, rivers, paleoshoreline
 *   Act 4 (55-60s) — "Full Circle" — return to start for seamless loop
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

async function runHero(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // === SETUP ===
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await demo.setFilterMode('age')
  await settle(page)

  // ─── Act 1: "The Living Planet" (0-20s) ─── zoom 2.3, auto-rotate ON

  // 0-5s: Age filter, steady rotation. Let density impress.
  console.log('  [0-5s] Age filter, steady rotation...')
  await recorder.capture(page, 5)

  // 5-8s: Switch to category filter. Instant recolor.
  console.log('  [5-8s] Category filter...')
  await demo.setFilterMode('category')
  await settle(page)
  await recorder.capture(page, 3)

  // 8-11s: Switch to country filter. Another recolor.
  console.log('  [8-11s] Country filter...')
  await demo.setFilterMode('country')
  await settle(page)
  await recorder.capture(page, 3)

  // 11-14s: Switch to source filter. 29-color rainbow.
  console.log('  [11-14s] Source filter...')
  await demo.setFilterMode('source')
  await settle(page)
  await recorder.capture(page, 3)

  // 14-17s: Back to age. Fly to Mediterranean.
  console.log('  [14-17s] Age filter, fly to Mediterranean...')
  await demo.setFilterMode('age')
  await settle(page)
  fire(`window.__DEMO.flyTo(20, 37)`)
  await recorder.capture(page, 3)

  // 17-20s: Hold on Mediterranean cluster.
  console.log('  [17-20s] Hold on Mediterranean...')
  await recorder.capture(page, 3)

  // ─── Act 2: "Iconic Sites" (20-40s) ─── zoom to 2.1 once

  // 20-21s: Single zoom in (2.3 → 2.1)
  console.log('  [20-21s] Zoom in to 2.1...')
  fire(`window.__DEMO.smoothZoom(2.3, 2.1, 800)`)
  await recorder.capture(page, 1)

  // 21-24s: Category filter. Show Egyptian empire + fly to Giza.
  console.log('  [21-24s] Egyptian empire + Giza...')
  await demo.setFilterMode('category')
  await settle(page)
  fire(`window.__DEMO.showEmpire("egyptian")`)
  fire(`window.__DEMO.flyTo(31.13, 29.98)`)
  await recorder.capture(page, 3)

  // 24-27s: Hold on Giza with Egyptian empire.
  console.log('  [24-27s] Hold on Giza...')
  await recorder.capture(page, 3)

  // 27-28s: Switch to Roman empire + fly to Rome.
  console.log('  [27-28s] Roman empire + Rome...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.showEmpire("roman")`)
  fire(`window.__DEMO.flyTo(12.49, 41.89)`)
  await recorder.capture(page, 1)

  // 28-31s: Hold on Rome with Roman empire.
  console.log('  [28-31s] Hold on Rome...')
  await recorder.capture(page, 3)

  // 31-32s: Age filter. Fly to Stonehenge.
  console.log('  [31-32s] Fly to Stonehenge...')
  await demo.hideAllEmpires()
  await demo.setFilterMode('age')
  await settle(page)
  fire(`window.__DEMO.flyTo(-1.826, 51.179)`)
  await recorder.capture(page, 1)

  // 32-35s: Hold on Stonehenge.
  console.log('  [32-35s] Hold on Stonehenge...')
  await recorder.capture(page, 3)

  // 35-36s: Fly to Machu Picchu.
  console.log('  [35-36s] Fly to Machu Picchu...')
  fire(`window.__DEMO.flyTo(-72.545, -13.163)`)
  await recorder.capture(page, 1)

  // 36-39s: Show Inca empire. Hold.
  console.log('  [36-39s] Inca empire, hold...')
  fire(`window.__DEMO.showEmpire("inca")`)
  await recorder.capture(page, 3)

  // 39-40s: Hide empires.
  console.log('  [39-40s] Hide empires...')
  await demo.hideAllEmpires()
  await recorder.capture(page, 1)

  // ─── Act 3: "Layers of Time" (40-55s) ─── zoom out to 2.3

  // 40-41s: Single zoom out (2.1 → 2.3)
  console.log('  [40-41s] Zoom out to 2.3...')
  fire(`window.__DEMO.smoothZoom(2.1, 2.3, 800)`)
  await recorder.capture(page, 1)

  // 41-44s: Category filter. Satellite ON.
  console.log('  [41-44s] Satellite mode...')
  await demo.setFilterMode('category')
  await demo.setSatellite(true)
  await settle(page)
  await recorder.capture(page, 3)

  // 44-47s: Add rivers layer on satellite.
  console.log('  [44-47s] Rivers layer...')
  await demo.setVectorLayer('rivers', true)
  await settle(page)
  await recorder.capture(page, 3)

  // 47-50s: Remove rivers + satellite. Paleoshoreline -120m (ice age).
  console.log('  [47-50s] Paleoshoreline -120m...')
  await demo.setVectorLayer('rivers', false)
  await demo.setSatellite(false)
  await demo.setPaleoshoreline(true, -120)
  await settle(page)
  await recorder.capture(page, 3)

  // 50-53s: Shift paleoshoreline to -60m.
  console.log('  [50-53s] Paleoshoreline -60m...')
  await demo.setPaleoshoreline(true, -60)
  await settle(page)
  await recorder.capture(page, 3)

  // 53-55s: Remove paleoshoreline. Country filter. Clean.
  console.log('  [53-55s] Country filter, clean...')
  await demo.setPaleoshoreline(false)
  await demo.setFilterMode('country')
  await settle(page)
  await recorder.capture(page, 2)

  // ─── Act 4: "Full Circle" (55-60s) ─── loop point

  // 55-58s: Age filter. Fly back toward start.
  console.log('  [55-58s] Age filter, fly toward start...')
  await demo.setFilterMode('age')
  await settle(page)
  fire(`window.__DEMO.flyTo(30, 20)`)
  await recorder.capture(page, 3)

  // 58-60s: Steady rotation. Matches frame 0 for seamless loop.
  console.log('  [58-60s] Steady rotation (loop point)...')
  await recorder.capture(page, 2)
}

export const heroScene: SceneDefinition[] = [
  {
    name: 'hero',
    duration: 60,
    resolution: 'hero',
    run: runHero,
  },
]
