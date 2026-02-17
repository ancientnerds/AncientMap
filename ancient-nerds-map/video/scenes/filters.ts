/**
 * Filters showcase scene — 15-second clip demonstrating all 4 filter modes
 * and the age-range slider.
 *
 * Fixed zoom 2.15. No breathing. Visual interest from color changes.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

async function runFiltersShowcase(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  // Setup: face Europe/Middle East, auto-rotate ON, fixed zoom
  await demo.setAutoRotate(true)
  await demo.flyTo(25, 35)
  await demo.setZoom(2.15)
  await settle(page)

  // 0-3s: Age filter mode
  console.log('  [0-3s] Age filter...')
  await demo.setFilterMode('age')
  await settle(page)
  await recorder.capture(page, 3)

  // 3-6s: Country filter mode
  console.log('  [3-6s] Country filter...')
  await demo.setFilterMode('country')
  await settle(page)
  await recorder.capture(page, 3)

  // 6-9s: Category filter mode
  console.log('  [6-9s] Category filter...')
  await demo.setFilterMode('category')
  await settle(page)
  await recorder.capture(page, 3)

  // 9-12s: Source filter mode (29-color rainbow)
  console.log('  [9-12s] Source filter...')
  await demo.setFilterMode('source')
  await settle(page)
  await recorder.capture(page, 3)

  // 12-15s: Age filter + Bronze Age range
  console.log('  [12-15s] Age filter + Bronze Age range...')
  await demo.setFilterMode('age')
  await demo.setAgeRange(-3000, -1500)
  await settle(page)
  await recorder.capture(page, 3)

  // Reset age range
  await demo.setAgeRange(-10000, 2025)
}

export const filtersScene: SceneDefinition[] = [
  {
    name: 'filters-showcase',
    duration: 15,
    resolution: 'section',
    run: runFiltersShowcase,
  },
]
