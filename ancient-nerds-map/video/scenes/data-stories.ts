/**
 * Data story scenes — narrative clips that showcase data richness.
 * 3 stories: sources, timeline, categories.
 *
 * No breathing. Fixed zoom. Visual interest from data changes.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

// ─── Data Sources (12s) ───
// Show the 29-source aggregation

async function runDataSources(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await settle(page)

  // 0-3s: Category filter, rotation
  console.log('  [0-3s] Category filter...')
  await recorder.capture(page, 3)

  // 3-6s: Switch to source filter — rainbow explosion
  console.log('  [3-6s] Source filter rainbow...')
  await demo.setFilterMode('source')
  await settle(page)
  await recorder.capture(page, 3)

  // 6-7s: Fly to Mediterranean (max source overlap)
  console.log('  [6-7s] Fly to Mediterranean...')
  fire(`window.__DEMO.flyTo(20, 37)`)
  await recorder.capture(page, 1)

  // 7-10s: Hold on multi-source density
  console.log('  [7-10s] Hold on multi-source density...')
  await recorder.capture(page, 3)

  // 10-12s: Fly to wider view
  console.log('  [10-12s] Wider view...')
  fire(`window.__DEMO.flyTo(40, 20)`)
  await recorder.capture(page, 2)
}

// ─── Data Timeline (15s) ───
// Walk through archaeological time using setAgeRange

async function runDataTimeline(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  // Setup: face Near East
  await demo.setFilterMode('age')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)
  await demo.flyTo(35, 30)
  await settle(page)

  // 0-3s: Full range
  console.log('  [0-3s] Full time range...')
  await recorder.capture(page, 3)

  // 3-5s: Earliest only (-10000 to -4500)
  console.log('  [3-5s] Earliest sites...')
  await demo.setAgeRange(-10000, -4500)
  await settle(page)
  await recorder.capture(page, 2)

  // 5-7s: Bronze Age (-3000 to -1500)
  console.log('  [5-7s] Bronze Age...')
  await demo.setAgeRange(-3000, -1500)
  await settle(page)
  await recorder.capture(page, 2)

  // 7-9s: Classical era (-500 to 500)
  console.log('  [7-9s] Classical era...')
  await demo.setAgeRange(-500, 500)
  await settle(page)
  await recorder.capture(page, 2)

  // 9-11s: Medieval (500 to 1500)
  console.log('  [9-11s] Medieval...')
  await demo.setAgeRange(500, 1500)
  await settle(page)
  await recorder.capture(page, 2)

  // 11-13s: Modern era (1500 to 2025)
  console.log('  [11-13s] Modern era...')
  await demo.setAgeRange(1500, 2025)
  await settle(page)
  await recorder.capture(page, 2)

  // 13-15s: Full range — all 800K visible
  console.log('  [13-15s] Full range, all sites...')
  await demo.setAgeRange(-10000, 2025)
  await settle(page)
  await recorder.capture(page, 2)
}

// ─── Data Categories (10s) ───
// Category color meanings through geographic examples

async function runDataCategories(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup
  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)
  await settle(page)

  // 0-3s: All 10 colors visible, rotation
  console.log('  [0-3s] All category colors...')
  await recorder.capture(page, 3)

  // 3-4s: Fly to UK/Ireland (megalithic blue)
  console.log('  [3-4s] Fly to British Isles...')
  fire(`window.__DEMO.flyTo(-3, 53)`)
  await recorder.capture(page, 1)

  // 4-6s: Hold on British Isles
  console.log('  [4-6s] Megalithic sites...')
  await recorder.capture(page, 2)

  // 6-7s: Fly to Nile Valley (religious gold)
  console.log('  [6-7s] Fly to Nile Valley...')
  fire(`window.__DEMO.flyTo(31.80, 26.69)`)
  await recorder.capture(page, 1)

  // 7-10s: Hold on Egypt
  console.log('  [7-10s] Nile religious sites...')
  await recorder.capture(page, 3)
}

export const dataStoriesScene: SceneDefinition[] = [
  { name: 'data-sources',    duration: 12, resolution: 'section', run: runDataSources },
  { name: 'data-timeline',   duration: 15, resolution: 'section', run: runDataTimeline },
  { name: 'data-categories', duration: 10, resolution: 'section', run: runDataCategories },
]
