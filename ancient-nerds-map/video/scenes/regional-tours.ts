/**
 * Regional tour scenes — flyTo-driven tours through major archaeological regions.
 * 5 tours: Mediterranean, Americas, Asia, Europe, Near East.
 *
 * No breathing. Fixed zoom per tour. Visual interest from flyTo hops,
 * filter switches, and empire reveals.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

// ─── Mediterranean Tour (20s) ───

async function runTourMediterranean(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('age')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.1)
  await demo.flyTo(20, 37)
  await settle(page)

  // 0-3s: Face Med
  console.log('  [0-3s] Mediterranean overview...')
  await recorder.capture(page, 3)

  // 3-4s: Fly to Athens
  console.log('  [3-4s] Fly to Athens...')
  fire(`window.__DEMO.flyTo(23.73, 37.97)`)
  await recorder.capture(page, 1)

  // 4-7s: Category filter, hold on Athens
  console.log('  [4-7s] Athens, category filter...')
  await demo.setFilterMode('category')
  await settle(page)
  await recorder.capture(page, 3)

  // 7-8s: Fly to Rome
  console.log('  [7-8s] Fly to Rome...')
  fire(`window.__DEMO.flyTo(12.49, 41.89)`)
  await recorder.capture(page, 1)

  // 8-11s: Roman Empire hold
  console.log('  [8-11s] Roman Empire...')
  await demo.showEmpire('roman')
  await settle(page)
  await recorder.capture(page, 3)

  // 11-12s: Fly to Petra
  console.log('  [11-12s] Fly to Petra...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(35.44, 30.33)`)
  await recorder.capture(page, 1)

  // 12-15s: Country filter, hold on Petra
  console.log('  [12-15s] Petra, country filter...')
  await demo.setFilterMode('country')
  await settle(page)
  await recorder.capture(page, 3)

  // 15-16s: Fly to Baalbek
  console.log('  [15-16s] Fly to Baalbek...')
  fire(`window.__DEMO.flyTo(36.20, 34.01)`)
  await recorder.capture(page, 1)

  // 16-18s: Hold on Baalbek
  console.log('  [16-18s] Hold on Baalbek...')
  await recorder.capture(page, 2)

  // 18-20s: Fly to Giza, end
  console.log('  [18-20s] End on Giza...')
  fire(`window.__DEMO.flyTo(31.13, 29.98)`)
  await recorder.capture(page, 2)
}

// ─── Americas Tour (18s) ───

async function runTourAmericas(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.15)
  await demo.flyTo(-90, 15)
  await settle(page)

  // 0-3s: Face Americas
  console.log('  [0-3s] Americas overview...')
  await recorder.capture(page, 3)

  // 3-4s: Fly to Teotihuacan
  console.log('  [3-4s] Fly to Teotihuacan...')
  fire(`window.__DEMO.flyTo(-98.84, 19.69)`)
  await recorder.capture(page, 1)

  // 4-7s: Teotihuacan empire hold
  console.log('  [4-7s] Teotihuacan empire...')
  await demo.showEmpire('teotihuacan')
  await settle(page)
  await recorder.capture(page, 3)

  // 7-8s: Fly to Chichen Itza
  console.log('  [7-8s] Fly to Chichen Itza...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(-88.57, 20.68)`)
  await recorder.capture(page, 1)

  // 8-11s: Maya empire hold
  console.log('  [8-11s] Maya empire...')
  await demo.showEmpire('maya')
  await settle(page)
  await recorder.capture(page, 3)

  // 11-12s: Fly to Machu Picchu
  console.log('  [11-12s] Fly to Machu Picchu...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(-72.545, -13.163)`)
  await recorder.capture(page, 1)

  // 12-15s: Inca empire hold
  console.log('  [12-15s] Inca empire...')
  await demo.showEmpire('inca')
  await settle(page)
  await recorder.capture(page, 3)

  // 15-16s: Fly to Easter Island
  console.log('  [15-16s] Fly to Easter Island...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(-109.37, -27.12)`)
  await recorder.capture(page, 1)

  // 16-18s: Age filter, hold on Easter Island
  console.log('  [16-18s] Easter Island, age filter...')
  await demo.setFilterMode('age')
  await settle(page)
  await recorder.capture(page, 2)
}

// ─── Asia Tour (18s) ───

async function runTourAsia(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('age')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.15)
  await demo.flyTo(80, 25)
  await settle(page)

  // 0-3s: Face India
  console.log('  [0-3s] Asia overview...')
  await recorder.capture(page, 3)

  // 3-4s: Fly to Mohenjo-daro
  console.log('  [3-4s] Fly to Mohenjo-daro...')
  fire(`window.__DEMO.flyTo(70.75, 28.30)`)
  await recorder.capture(page, 1)

  // 4-7s: Indus Valley empire hold
  console.log('  [4-7s] Indus Valley...')
  await demo.showEmpire('indus_valley')
  await settle(page)
  await recorder.capture(page, 3)

  // 7-8s: Fly to Angkor Wat
  console.log('  [7-8s] Fly to Angkor Wat...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(103.87, 13.41)`)
  await recorder.capture(page, 1)

  // 8-11s: Category filter, hold on Angkor
  console.log('  [8-11s] Angkor Wat, category filter...')
  await demo.setFilterMode('category')
  await settle(page)
  await recorder.capture(page, 3)

  // 11-12s: Fly to Han China
  console.log('  [11-12s] Fly to Han China...')
  fire(`window.__DEMO.flyTo(106.27, 33.15)`)
  await recorder.capture(page, 1)

  // 12-15s: Han Dynasty hold
  console.log('  [12-15s] Han Dynasty...')
  await demo.showEmpire('han')
  await settle(page)
  await recorder.capture(page, 3)

  // 15-16s: Fly to Persepolis
  console.log('  [15-16s] Fly to Persepolis...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(52.89, 29.94)`)
  await recorder.capture(page, 1)

  // 16-18s: Achaemenid Empire hold, cleanup
  console.log('  [16-18s] Achaemenid Empire...')
  await demo.showEmpire('achaemenid')
  await settle(page)
  await recorder.capture(page, 2)
  await demo.hideAllEmpires()
}

// ─── Europe Tour (15s) ───

async function runTourEurope(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('age')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.1)
  await demo.flyTo(0, 50)
  await settle(page)

  // 0-3s: Face Western Europe
  console.log('  [0-3s] Europe overview...')
  await recorder.capture(page, 3)

  // 3-4s: Fly to Carnac
  console.log('  [3-4s] Fly to Carnac...')
  fire(`window.__DEMO.flyTo(-3.08, 47.58)`)
  await recorder.capture(page, 1)

  // 4-6s: Hold on Carnac megaliths
  console.log('  [4-6s] Carnac megaliths...')
  await recorder.capture(page, 2)

  // 6-7s: Fly to Newgrange
  console.log('  [6-7s] Fly to Newgrange...')
  fire(`window.__DEMO.flyTo(-6.48, 53.69)`)
  await recorder.capture(page, 1)

  // 7-9s: Category filter, hold on Ireland
  console.log('  [7-9s] Newgrange, category filter...')
  await demo.setFilterMode('category')
  await settle(page)
  await recorder.capture(page, 2)

  // 9-10s: Fly to Stonehenge
  console.log('  [9-10s] Fly to Stonehenge...')
  fire(`window.__DEMO.flyTo(-1.826, 51.179)`)
  await recorder.capture(page, 1)

  // 10-12s: Hold on Stonehenge
  console.log('  [10-12s] Hold on Stonehenge...')
  await recorder.capture(page, 2)

  // 12-13s: Fly to Lascaux
  console.log('  [12-13s] Fly to Lascaux...')
  fire(`window.__DEMO.flyTo(1.17, 45.05)`)
  await recorder.capture(page, 1)

  // 13-15s: Hold on cave art region
  console.log('  [13-15s] Lascaux cave art region...')
  await recorder.capture(page, 2)
}

// ─── Near East Tour (15s) ───

async function runTourNearEast(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('age')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.1)
  await demo.flyTo(42, 34)
  await settle(page)

  // 0-3s: Face Fertile Crescent
  console.log('  [0-3s] Fertile Crescent overview...')
  await recorder.capture(page, 3)

  // 3-4s: Fly to Gobekli Tepe
  console.log('  [3-4s] Fly to Gobekli Tepe...')
  fire(`window.__DEMO.flyTo(38.92, 37.22)`)
  await recorder.capture(page, 1)

  // 4-7s: Hold on world's oldest temple
  console.log('  [4-7s] Gobekli Tepe...')
  await recorder.capture(page, 3)

  // 7-8s: Fly to Nile Valley (Luxor)
  console.log('  [7-8s] Fly to Luxor...')
  fire(`window.__DEMO.flyTo(31.80, 26.69)`)
  await recorder.capture(page, 1)

  // 8-10s: Egyptian Empire hold
  console.log('  [8-10s] Egyptian Empire...')
  await demo.showEmpire('egyptian')
  await settle(page)
  await recorder.capture(page, 2)

  // 10-11s: Fly to Persepolis
  console.log('  [10-11s] Fly to Persepolis...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(52.89, 29.94)`)
  await recorder.capture(page, 1)

  // 11-13s: Achaemenid Empire hold
  console.log('  [11-13s] Achaemenid Empire...')
  await demo.showEmpire('achaemenid')
  await settle(page)
  await recorder.capture(page, 2)

  // 13-15s: Category filter, cleanup
  console.log('  [13-15s] Category filter, wrap up...')
  await demo.hideAllEmpires()
  await demo.setFilterMode('category')
  await settle(page)
  await recorder.capture(page, 2)
}

export const regionalToursScene: SceneDefinition[] = [
  { name: 'tour-mediterranean', duration: 20, resolution: 'section', run: runTourMediterranean },
  { name: 'tour-americas',      duration: 18, resolution: 'section', run: runTourAmericas },
  { name: 'tour-asia',          duration: 18, resolution: 'section', run: runTourAsia },
  { name: 'tour-europe',        duration: 15, resolution: 'section', run: runTourEurope },
  { name: 'tour-near-east',     duration: 15, resolution: 'section', run: runTourNearEast },
]
