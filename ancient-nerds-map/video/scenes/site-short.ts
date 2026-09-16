/**
 * Site-short scenes — the two globe clips a site teaser needs
 * (spec: docs/superpowers/specs/2026-09-16-site-shorts-prototype-design.md).
 *
 *   short-approach  dark globe from space, fly-to + zoom onto the site (4 s)
 *   short-terrain   Mapbox satellite with DEM terrain, slow orbit (17 s)
 *
 * Input: SITE_SHORT_INPUT = path to `video-assets/shorts/<slug>/site.json`
 * (record.ts sets it from `--input`). Record in portrait:
 *   npm run video:record -- short-approach --portrait --input <site.json> --out <dir>
 */

import { readFileSync } from 'fs'
import type { SceneDefinition, SceneContext } from '../record'
import { settle } from '../utils/helpers.js'

interface SiteInput {
  name: string
  lat: number
  lng: number
}

const APPROACH_S = 4
const ROTATE_S = 2.4
const TERRAIN_S = 17

// Camera distances for setZoom/smoothZoom (globe radius = 1). 2.3 is the
// landing-video overview; 1.36 maps to Mapbox zoom ≈ 14 via
// threeJsCameraToMapbox, close enough for enterMapbox to sync sensibly.
const SPACE_DIST = 2.44  // CAMERA.MAX_DISTANCE — OrbitControls clamps anything farther
const APPROACH_END_DIST = 1.75
const MAPBOX_HANDOFF_DIST = 1.36

const ORBIT_ZOOM = 14.2
const ORBIT_PITCH = 62
const ORBIT_BEARING_FROM = 20
const ORBIT_BEARING_TO = 110
const TERRAIN_EXAGGERATION = 1.4

function loadSite(): SiteInput {
  const path = process.env.SITE_SHORT_INPUT
  if (!path) throw new Error('SITE_SHORT_INPUT not set — pass --input <site.json>')
  const site = JSON.parse(readFileSync(path, 'utf-8')) as SiteInput
  if (typeof site.lat !== 'number' || typeof site.lng !== 'number') {
    throw new Error(`site.json at ${path} has no numeric lat/lng`)
  }
  return site
}

const realWait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

async function runApproach(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx
  const site = loadSite()
  console.log(`  Approach: ${site.name} (${site.lat}, ${site.lng})`)

  await demo.setAutoRotate(false)
  // Park the camera a quarter turn west and a little north so the fly-to
  // visibly rotates the globe instead of just zooming.
  await demo.setFlyToDuration(1)
  await demo.flyTo(site.lng - 70, site.lat + 15)
  await demo.setZoom(SPACE_DIST)
  await settle(page)

  console.log('  camera before:', JSON.stringify(await demo.getCameraState()))

  // useFlyToAnimation pins the camera distance for the whole rotation, so the
  // zoom has to follow the rotation instead of running alongside it.
  await demo.setFlyToDuration(ROTATE_S * 1000)
  fire(`window.__DEMO.flyTo(${site.lng}, ${site.lat})`)
  await recorder.capture(page, ROTATE_S)
  console.log('  camera after rotate:', JSON.stringify(await demo.getCameraState()))

  fire(`window.__DEMO.smoothZoom(${SPACE_DIST}, ${APPROACH_END_DIST}, ${(APPROACH_S - ROTATE_S) * 1000})`)
  await recorder.capture(page, APPROACH_S - ROTATE_S)
  console.log('  camera after zoom:', JSON.stringify(await demo.getCameraState()))
}

async function runTerrain(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder } = ctx
  const site = loadSite()
  console.log(`  Terrain orbit: ${site.name}`)

  await demo.setAutoRotate(false)
  await demo.setSatellite(true)
  await demo.setFlyToDuration(1)
  await demo.flyTo(site.lng, site.lat)
  await demo.setZoom(MAPBOX_HANDOFF_DIST)
  await settle(page)

  await demo.enterMapbox()
  await demo.setTerrain(TERRAIN_EXAGGERATION)
  await demo.mapboxJumpTo(site.lng, site.lat, ORBIT_ZOOM, ORBIT_BEARING_FROM, ORBIT_PITCH)
  // Tiles and DEM load over the network; synthetic time does not gate that.
  await demo.mapboxWaitIdle(20000)
  await realWait(1500)
  await settle(page)

  fire(
    `window.__DEMO.mapboxOrbit(${site.lng}, ${site.lat}, ${ORBIT_ZOOM}, ${ORBIT_PITCH}, ` +
    `${ORBIT_BEARING_FROM}, ${ORBIT_BEARING_TO}, ${TERRAIN_S * 1000})`
  )
  await recorder.capture(page, TERRAIN_S)
}

const FRAME_YIELD_MS = 40

export const siteShortScenes: SceneDefinition[] = [
  { name: 'short-approach', duration: APPROACH_S, resolution: 'short', frameYieldMs: FRAME_YIELD_MS, run: runApproach },
  {
    name: 'short-terrain',
    duration: TERRAIN_S,
    resolution: 'short',
    canvasSelector: '.mapbox-globe-container canvas',
    frameYieldMs: FRAME_YIELD_MS,
    run: runTerrain,
  },
]
