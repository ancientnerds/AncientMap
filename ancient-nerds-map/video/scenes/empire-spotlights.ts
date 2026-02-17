/**
 * Empire spotlight scenes — individual 8-10s clips for each historical empire.
 * Steady zoom, auto-rotate, fly to heartland, show empire, hold.
 *
 * No breathing. Fixed zoom 2.2 throughout.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

// Helper: standard empire spotlight pattern
async function empireSpotlight(
  ctx: SceneContext,
  empireId: string,
  lon: number,
  lat: number,
  holdSec: number,
  endFilter: 'age' | 'category' | 'country' | 'source',
  endHoldSec: number,
): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)
  await settle(page)

  // 0-1s: Establishing shot
  console.log('  [0-1s] Establishing shot...')
  await recorder.capture(page, 1)

  // 1-2s: Fly to heartland
  console.log(`  [1-2s] Fly to ${empireId}...`)
  fire(`window.__DEMO.flyTo(${lon}, ${lat})`)
  await recorder.capture(page, 1)

  // 2-(2+holdSec)s: Show empire, hold
  console.log(`  [2-${2 + holdSec}s] ${empireId} empire...`)
  await demo.showEmpire(empireId)
  await settle(page)
  await recorder.capture(page, holdSec)

  // End filter + hold
  console.log(`  [${2 + holdSec}-${2 + holdSec + endHoldSec}s] ${endFilter} filter...`)
  await demo.setFilterMode(endFilter)
  await settle(page)
  await recorder.capture(page, endHoldSec)

  // Cleanup
  await demo.hideAllEmpires()
}

// Roman Empire — 10s
async function runEmpireRoman(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'roman', 18.64, 39.86, 6, 'age', 2)
}

// Achaemenid Empire — 8s
async function runEmpireAchaemenid(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'achaemenid', 52.89, 29.94, 4, 'age', 2)
}

// Egyptian Empire — 8s
async function runEmpireEgyptian(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'egyptian', 31.80, 26.69, 4, 'age', 2)
}

// Han Dynasty — 8s
async function runEmpireHan(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'han', 106.27, 33.15, 4, 'source', 2)
}

// Byzantine Empire — 8s
async function runEmpireByzantine(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'byzantine', 30.56, 35.41, 4, 'country', 2)
}

// Maya Empire — 8s
async function runEmpireMaya(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'maya', -90.22, 17.57, 4, 'age', 2)
}

// Inca Empire — 8s
async function runEmpireInca(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'inca', -72.545, -13.163, 4, 'age', 2)
}

// Indus Valley — 8s
async function runEmpireIndusValley(ctx: SceneContext): Promise<void> {
  await empireSpotlight(ctx, 'indus_valley', 70.75, 28.30, 4, 'category', 2)
}

export const empireSpotlightsScene: SceneDefinition[] = [
  { name: 'empire-roman',        duration: 10, resolution: 'section', run: runEmpireRoman },
  { name: 'empire-achaemenid',   duration: 8,  resolution: 'section', run: runEmpireAchaemenid },
  { name: 'empire-egyptian',     duration: 8,  resolution: 'section', run: runEmpireEgyptian },
  { name: 'empire-han',          duration: 8,  resolution: 'section', run: runEmpireHan },
  { name: 'empire-byzantine',    duration: 8,  resolution: 'section', run: runEmpireByzantine },
  { name: 'empire-maya',         duration: 8,  resolution: 'section', run: runEmpireMaya },
  { name: 'empire-inca',         duration: 8,  resolution: 'section', run: runEmpireInca },
  { name: 'empire-indus-valley', duration: 8,  resolution: 'section', run: runEmpireIndusValley },
]
