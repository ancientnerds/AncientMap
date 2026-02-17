/**
 * B-roll scenes — pure ambient shots for background use.
 * No interactions, no transitions. Just beauty and rotation.
 *
 * All use 'hero' resolution for maximum visual quality.
 */

import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

// Dark globe rotating — 15s
async function runBrollDarkRotate(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('age')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.35)
  await settle(page)

  console.log('  [0-15s] Dark globe rotation...')
  await recorder.capture(page, 15)
}

// Satellite rotating — 15s
async function runBrollSatelliteRotate(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await demo.setSatellite(true)
  await settle(page)

  console.log('  [0-15s] Satellite rotation...')
  await recorder.capture(page, 15)

  await demo.setSatellite(false)
}

// Country colors rotating — 10s
async function runBrollCountryColors(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('country')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await settle(page)

  console.log('  [0-10s] Country colors rotation...')
  await recorder.capture(page, 10)
}

// Source rainbow rotating — 10s
async function runBrollSourceRainbow(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('source')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await settle(page)

  console.log('  [0-10s] Source rainbow rotation...')
  await recorder.capture(page, 10)
}

// Ice age Earth — 12s
async function runBrollIceAge(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('age')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.3)
  await demo.setPaleoshoreline(true, -150)
  await settle(page)

  console.log('  [0-12s] Ice age Earth rotation...')
  await recorder.capture(page, 12)

  await demo.setPaleoshoreline(false)
}

// All layers ON — maximum data density — 10s
async function runBrollLayersFull(ctx: SceneContext): Promise<void> {
  const { page, demo, recorder } = ctx

  await demo.setFilterMode('category')
  await demo.setAutoRotate(true)
  await demo.setZoom(2.2)

  // Turn on all 7 vector layers
  await demo.setVectorLayer('coastlines', true)
  await demo.setVectorLayer('countryBorders', true)
  await demo.setVectorLayer('rivers', true)
  await demo.setVectorLayer('lakes', true)
  await demo.setVectorLayer('coralReefs', true)
  await demo.setVectorLayer('glaciers', true)
  await demo.setVectorLayer('plateBoundaries', true)
  await settle(page)

  console.log('  [0-10s] All layers rotation...')
  await recorder.capture(page, 10)

  // Cleanup
  await demo.setVectorLayer('coastlines', false)
  await demo.setVectorLayer('countryBorders', false)
  await demo.setVectorLayer('rivers', false)
  await demo.setVectorLayer('lakes', false)
  await demo.setVectorLayer('coralReefs', false)
  await demo.setVectorLayer('glaciers', false)
  await demo.setVectorLayer('plateBoundaries', false)
}

export const brollScene: SceneDefinition[] = [
  { name: 'broll-dark-rotate',     duration: 15, resolution: 'hero', run: runBrollDarkRotate },
  { name: 'broll-satellite-rotate', duration: 15, resolution: 'hero', run: runBrollSatelliteRotate },
  { name: 'broll-country-colors',  duration: 10, resolution: 'hero', run: runBrollCountryColors },
  { name: 'broll-source-rainbow',  duration: 10, resolution: 'hero', run: runBrollSourceRainbow },
  { name: 'broll-ice-age',         duration: 12, resolution: 'hero', run: runBrollIceAge },
  { name: 'broll-layers-full',     duration: 10, resolution: 'hero', run: runBrollLayersFull },
]
