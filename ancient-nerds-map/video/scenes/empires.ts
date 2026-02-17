/**
 * Empires showcase scene — 20-second clip showing 4 empires from 4 continents.
 * Confident flyTo hops, no breathing. Fixed zoom 2.2.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

async function runEmpiresShowcase(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)
  await settle(page)

  // 0-2s: Establishing shot, rotating
  console.log('  [0-2s] Establishing shot...')
  await recorder.capture(page, 2)

  // 2-3s: Fly to Roman heartland
  console.log('  [2-3s] Fly to Rome...')
  fire(`window.__DEMO.flyTo(18.64, 39.86)`)
  await recorder.capture(page, 1)

  // 3-6s: Roman Empire hold (3s)
  console.log('  [3-6s] Roman Empire...')
  await demo.showEmpire('roman')
  await settle(page)
  await recorder.capture(page, 3)

  // 6-7s: Fly to Persepolis
  console.log('  [6-7s] Fly to Persepolis...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(52.89, 29.94)`)
  await recorder.capture(page, 1)

  // 7-11s: Achaemenid Empire hold (4s)
  console.log('  [7-11s] Achaemenid Empire...')
  await demo.showEmpire('achaemenid')
  await settle(page)
  await recorder.capture(page, 4)

  // 11-12s: Fly to Han China
  console.log('  [11-12s] Fly to Han China...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(106.27, 33.15)`)
  await recorder.capture(page, 1)

  // 12-16s: Han Dynasty hold (4s)
  console.log('  [12-16s] Han Dynasty...')
  await demo.showEmpire('han')
  await settle(page)
  await recorder.capture(page, 4)

  // 16-17s: Fly to Inca
  console.log('  [16-17s] Fly to Inca...')
  await demo.hideAllEmpires()
  fire(`window.__DEMO.flyTo(-72.545, -13.163)`)
  await recorder.capture(page, 1)

  // 17-20s: Inca Empire hold (3s)
  console.log('  [17-20s] Inca Empire...')
  await demo.showEmpire('inca')
  await settle(page)
  await recorder.capture(page, 3)

  // Cleanup
  await demo.hideAllEmpires()
}

export const empiresScene: SceneDefinition[] = [
  {
    name: 'empires-showcase',
    duration: 20,
    resolution: 'section',
    run: runEmpiresShowcase,
  },
]
