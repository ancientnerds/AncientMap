/**
 * Globe overview scene — 12-second clip showing the interactive 3D globe
 * and data density. Single zoom in + single zoom out for narrative purpose.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

async function runGlobeOverview(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx

  // Setup: category mode, auto-rotate, wide zoom
  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.4)
  await settle(page)

  // 0-4s: Wide orbit
  console.log('  [0-4s] Wide orbit...')
  await recorder.capture(page, 4)

  // 4-5s: Fly to Mediterranean + zoom in (2.4 → 2.1)
  console.log('  [4-5s] Fly to Med, zoom in...')
  fire(`window.__DEMO.flyTo(20, 37)`)
  fire(`window.__DEMO.smoothZoom(2.4, 2.1, 800)`)
  await recorder.capture(page, 1)

  // 5-8s: Hold at 2.1. Dense Mediterranean.
  console.log('  [5-8s] Hold on Mediterranean...')
  await recorder.capture(page, 3)

  // 8-9s: Zoom out (2.1 → 2.4)
  console.log('  [8-9s] Zoom out...')
  fire(`window.__DEMO.smoothZoom(2.1, 2.4, 800)`)
  await recorder.capture(page, 1)

  // 9-12s: Wide orbit resume.
  console.log('  [9-12s] Wide orbit resume...')
  await recorder.capture(page, 3)
}

export const globeOverviewScene: SceneDefinition[] = [
  {
    name: 'globe-overview',
    duration: 12,
    resolution: 'section',
    run: runGlobeOverview,
  },
]
