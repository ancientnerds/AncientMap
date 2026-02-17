/**
 * Tool clips — short 5-second clips for each research tool card.
 * Each tool gets its own scene for independent encoding.
 *
 * No breathing. Fixed zoom per scene. Purposeful single-direction zooms only.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

// Search: Rotate 1.5s → fly to Giza → hold 2.5s
async function runSearch(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await settle(page)

  // 0-1.5s: Rotating globe
  console.log('  [0-1.5s] Rotating...')
  await recorder.capture(page, 1.5)

  // 1.5-2.5s: Fly to Giza
  console.log('  [1.5-2.5s] Fly to Giza...')
  fire(`window.__DEMO.flyTo(31.13, 29.98)`)
  await recorder.capture(page, 1)

  // 2.5-5s: Hold on Giza
  console.log('  [2.5-5s] Hold on Giza...')
  await recorder.capture(page, 2.5)
}

// Proximity: Rotate 1s → fly to Rome → hold 3s
async function runProximity(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await settle(page)

  // 0-1s: Rotating
  console.log('  [0-1s] Rotating...')
  await recorder.capture(page, 1)

  // 1-2s: Fly to Rome
  console.log('  [1-2s] Fly to Rome...')
  fire(`window.__DEMO.flyTo(12.5, 41.9)`)
  await recorder.capture(page, 1)

  // 2-5s: Hold on Rome
  console.log('  [2-5s] Hold on Rome...')
  await recorder.capture(page, 3)
}

// Measure: Rotate 1s → fly to E. Mediterranean → hold 3s
async function runMeasure(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await settle(page)

  // 0-1s: Rotating
  console.log('  [0-1s] Rotating...')
  await recorder.capture(page, 1)

  // 1-2s: Fly to E. Mediterranean
  console.log('  [1-2s] Fly to E. Med...')
  fire(`window.__DEMO.flyTo(30, 35)`)
  await recorder.capture(page, 1)

  // 2-5s: Hold
  console.log('  [2-5s] Hold...')
  await recorder.capture(page, 3)
}

// Map Layers: Rotate 1s → rivers 1s → lakes 1s → plates 1s → all visible 1s
async function runMapLayers(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)
  await settle(page)

  // 0-1s: Rotating
  console.log('  [0-1s] Rotating...')
  await recorder.capture(page, 1)

  // 1-2s: Rivers ON
  console.log('  [1-2s] Rivers...')
  await demo.setVectorLayer('rivers', true)
  await settle(page)
  await recorder.capture(page, 1)

  // 2-3s: Lakes ON
  console.log('  [2-3s] Lakes...')
  await demo.setVectorLayer('lakes', true)
  await settle(page)
  await recorder.capture(page, 1)

  // 3-4s: Tectonic plates ON
  console.log('  [3-4s] Plates...')
  await demo.setVectorLayer('plateBoundaries', true)
  await settle(page)
  await recorder.capture(page, 1)

  // 4-5s: All visible
  console.log('  [4-5s] All layers visible...')
  await recorder.capture(page, 1)

  // Cleanup
  await demo.setVectorLayer('rivers', false)
  await demo.setVectorLayer('lakes', false)
  await demo.setVectorLayer('plateBoundaries', false)
}

// Paleoshoreline: Rotate, then show ice age coastlines (kept as-is)
async function runPaleoshoreline(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)
  await settle(page)

  // 0-1s: Rotating globe
  console.log('  [0-1s] Rotating...')
  await recorder.capture(page, 1)

  // 1-3s: Paleoshoreline at -120m (LGM)
  console.log('  [1-3s] Ice age coastlines (-120m)...')
  await demo.setPaleoshoreline(true, -120)
  await settle(page)
  await recorder.capture(page, 2)

  // 3-5s: Rising sea level (-60m)
  console.log('  [3-5s] Rising sea level (-60m)...')
  await demo.setPaleoshoreline(true, -60)
  await settle(page)
  await recorder.capture(page, 2)

  // Cleanup
  await demo.setPaleoshoreline(false)
}

// Satellite: Dark globe 2s → satellite ON 2.5s → off
async function runSatellite(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await settle(page)

  // 0-2s: Dark globe rotating
  console.log('  [0-2s] Dark globe...')
  await recorder.capture(page, 2)

  // 2-4.5s: Satellite ON with dots
  console.log('  [2-4.5s] Satellite mode...')
  await demo.setSatellite(true)
  await settle(page)
  await recorder.capture(page, 2.5)

  // 4.5-5s: Satellite OFF
  console.log('  [4.5-5s] Satellite off...')
  await demo.setSatellite(false)
  await settle(page)
  await recorder.capture(page, 0.5)
}

// Empires Tool: Rotate 1s → fly to Rome → show Roman empire 3.5s
async function runEmpiresTool(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)
  await settle(page)

  // 0-1s: Rotating
  console.log('  [0-1s] Rotating...')
  await recorder.capture(page, 1)

  // 1-1.5s: Fly to Rome
  console.log('  [1-1.5s] Fly to Rome...')
  fire(`window.__DEMO.flyTo(18.64, 39.86)`)
  await recorder.capture(page, 0.5)

  // 1.5-5s: Show Roman Empire, hold
  console.log('  [1.5-5s] Roman Empire...')
  await demo.showEmpire('roman')
  await settle(page)
  await recorder.capture(page, 3.5)

  // Cleanup
  await demo.hideAllEmpires()
}

export const toolsScene: SceneDefinition[] = [
  { name: 'search',        duration: 5, resolution: 'tool', run: runSearch },
  { name: 'proximity',     duration: 5, resolution: 'tool', run: runProximity },
  { name: 'measure',       duration: 5, resolution: 'tool', run: runMeasure },
  { name: 'map-layers',    duration: 5, resolution: 'tool', run: runMapLayers },
  { name: 'paleoshoreline', duration: 5, resolution: 'tool', run: runPaleoshoreline },
  { name: 'satellite',     duration: 5, resolution: 'tool', run: runSatellite },
  { name: 'empires-tool',  duration: 5, resolution: 'tool', run: runEmpiresTool },
]
