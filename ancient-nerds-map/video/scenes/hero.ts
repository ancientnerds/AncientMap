/**
 * Hero scene — 60-second cinematic loop for the landing page hero background.
 *
 * Camera philosophy: NO BREATHING. No smoothZoom oscillation.
 * Visual interest comes from filter switches, empire reveals, layer toggles,
 * source showcases, and purposeful single-direction zoom changes.
 *
 * 5 acts:
 *   Act 1 (0-14s)  — "The Living Planet" — filter cycling at fixed zoom
 *   Act 2 (14-22s) — "Mediterranean & Shipwrecks" — source showcase
 *   Act 3 (22-44s) — "Iconic Sites" — slower flyTo hops with empires + Asia volcanos
 *   Act 4 (44-55s) — "Layers of Time" — satellite+labels, rivers, paleoshoreline
 *   Act 5 (55-60s) — "Full Circle" — return to start for seamless loop
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

async function runHero(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // === SETUP ===
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await demo.setFilterMode('age')
  // Preload extra sources we'll need later
  await demo.loadSources(['shipwrecks_oxrep', 'volcanic_holvol'])
  // Allow source data to load
  await new Promise(r => setTimeout(r, 3000))
  await settle(page)

  // ─── Act 1: "The Living Planet" (0-14s) ─── zoom 2.3, auto-rotate ON

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

  // ─── Act 2: "Mediterranean & Shipwrecks" (14-22s) ─── shipwreck showcase

  // 14-17s: Fly to Mediterranean, enable shipwrecks source (slower fly-to)
  console.log('  [14-17s] Fly to Mediterranean + shipwrecks...')
  await demo.setFlyToDuration(1800)
  await demo.setSelectedSources(['ancient_nerds', 'shipwrecks_oxrep'])
  await demo.setFilterMode('source')
  await settle(page)
  fire(`window.__DEMO.flyTo(20, 37)`)
  await recorder.capture(page, 3)

  // 17-20s: Hold on Mediterranean with shipwrecks visible.
  console.log('  [17-20s] Hold Mediterranean + shipwrecks...')
  await recorder.capture(page, 3)

  // 20-22s: Clear shipwrecks, category filter, zoom in for sites.
  console.log('  [20-22s] Clear shipwrecks, zoom in...')
  await demo.setSelectedSources(['ancient_nerds'])
  await demo.setFilterMode('category')
  await settle(page)
  fire(`window.__DEMO.smoothZoom(2.3, 2.1, 1200)`)
  await recorder.capture(page, 2)

  // ─── Act 3: "Iconic Sites" (22-44s) ─── slower flyTos (2s each)

  // 22-24s: Egyptian empire + fly to Giza (2s fly-to)
  console.log('  [22-24s] Egyptian empire + fly to Giza...')
  fire(`window.__DEMO.showEmpire("egyptian")`)
  fire(`window.__DEMO.flyTo(31.13, 29.98)`)
  await recorder.capture(page, 2)

  // 24-27s: Hold on Giza with Egyptian empire.
  console.log('  [24-27s] Hold on Giza...')
  await recorder.capture(page, 3)

  // 27-29s: Switch to Roman empire + fly to Rome (2s fly-to)
  console.log('  [27-29s] Roman empire + fly to Rome...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.showEmpire("roman")`)
  fire(`window.__DEMO.flyTo(12.49, 41.89)`)
  await recorder.capture(page, 2)

  // 29-32s: Hold on Rome with Roman empire.
  console.log('  [29-32s] Hold on Rome...')
  await recorder.capture(page, 3)

  // 32-34s: Fly to Stonehenge (2s fly-to)
  console.log('  [32-34s] Fly to Stonehenge...')
  await demo.hideAllEmpires()
  await demo.setFilterMode('age')
  await settle(page)
  fire(`window.__DEMO.flyTo(-1.826, 51.179)`)
  await recorder.capture(page, 2)

  // 34-36s: Hold on Stonehenge.
  console.log('  [34-36s] Hold on Stonehenge...')
  await recorder.capture(page, 2)

  // 36-38s: Fly to Machu Picchu (2s fly-to)
  console.log('  [36-38s] Fly to Machu Picchu...')
  fire(`window.__DEMO.flyTo(-72.545, -13.163)`)
  await recorder.capture(page, 2)

  // 38-40s: Inca empire, hold.
  console.log('  [38-40s] Inca empire, hold...')
  fire(`window.__DEMO.showEmpire("inca")`)
  await recorder.capture(page, 2)

  // 40-41s: Hide empires, fly toward Asia.
  console.log('  [40-41s] Hide empires...')
  await demo.hideAllEmpires()
  await recorder.capture(page, 1)

  // 41-44s: Fly to Indonesia/Southeast Asia + volcanos source.
  console.log('  [41-44s] Fly to Asia + volcanos...')
  await demo.setSelectedSources(['ancient_nerds', 'volcanic_holvol'])
  await demo.setFilterMode('source')
  await settle(page)
  fire(`window.__DEMO.flyTo(110, 5)`)
  await recorder.capture(page, 3)

  // ─── Act 4: "Layers of Time" (44-55s) ─── satellite+labels, paleoshoreline

  // 44-45s: Clear volcanos, zoom out.
  console.log('  [44-45s] Clear volcanos, zoom out...')
  await demo.setSelectedSources(['ancient_nerds'])
  await demo.setFilterMode('category')
  await settle(page)
  fire(`window.__DEMO.smoothZoom(2.1, 2.3, 800)`)
  await recorder.capture(page, 1)

  // 45-48s: Satellite ON + labels ON.
  console.log('  [45-48s] Satellite + labels ON...')
  await demo.setSatellite(true)
  await demo.setGeoLabels(true)
  await settle(page)
  await recorder.capture(page, 3)

  // 48-50s: Add rivers layer on satellite.
  console.log('  [48-50s] Rivers layer...')
  await demo.setVectorLayer('rivers', true)
  await settle(page)
  await recorder.capture(page, 2)

  // 50-52s: Remove rivers + satellite + labels. Paleoshoreline -120m (ice age).
  console.log('  [50-52s] Paleoshoreline -120m...')
  await demo.setVectorLayer('rivers', false)
  await demo.setSatellite(false)
  await demo.setGeoLabels(false)
  await demo.setPaleoshoreline(true, -120)
  await settle(page)
  await recorder.capture(page, 2)

  // 52-55s: Shift paleoshoreline to -60m.
  console.log('  [52-55s] Paleoshoreline -60m...')
  await demo.setPaleoshoreline(true, -60)
  await settle(page)
  await recorder.capture(page, 3)

  // ─── Act 5: "Full Circle" (55-60s) ─── loop point

  // 55-57s: Remove paleoshoreline. Country filter. Clean.
  console.log('  [55-57s] Country filter, clean...')
  await demo.setPaleoshoreline(false)
  await demo.setFilterMode('country')
  await settle(page)
  await recorder.capture(page, 2)

  // 57-60s: Age filter. Fly back toward start. Reset fly-to duration.
  console.log('  [57-60s] Age filter, fly toward start (loop point)...')
  await demo.setFlyToDuration(600)
  await demo.setFilterMode('age')
  await settle(page)
  fire(`window.__DEMO.flyTo(30, 20)`)
  await recorder.capture(page, 3)
}

export const heroScene: SceneDefinition[] = [
  {
    name: 'hero',
    duration: 60,
    resolution: 'hero',
    run: runHero,
  },
]
