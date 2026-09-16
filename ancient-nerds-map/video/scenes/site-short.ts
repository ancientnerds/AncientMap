/**
 * Site-short opening — one 6 s Mapbox clip per site
 * (spec: docs/superpowers/specs/2026-09-16-site-shorts-prototype-design.md).
 *
 *   0–1 s  satellite globe from space rotates onto the site
 *   1–3 s  continuous zoom from space down to z14 while the camera tilts
 *   3–6 s  3D terrain orbit around the site
 *
 * Everything runs on the Mapbox globe (satellite-streets style = imagery +
 * labels, DEM terrain), so the zoom never switches canvases. The narration
 * starts at 0 and continues over Ken-Burns photos after this clip.
 *
 * Input: SITE_SHORT_INPUT = path to `video-assets/shorts/<slug>/site.json`
 * (record.ts sets it from `--input`). Record in portrait at 60 fps with the
 * dev proxy pointed at production so the site dots load:
 *   VITE_DEV_API_TARGET=https://ancientnerds.com npm run video:record -- \
 *     short-opening --portrait --fps 60 --input <site.json> --out <dir>/clips
 */

import { readFileSync } from 'fs'
import type { SceneDefinition, SceneContext } from '../record'
import type { MapboxKeyframe } from '../../src/utils/demoApi'
import { advanceFrames, settle } from '../utils/helpers.js'

interface SiteInput {
  name: string
  lat: number
  lng: number
}

const OPENING_S = 6
const ROTATE_S = 1
const ZOOM_S = 2

const STYLE_WITH_LABELS = 'mapbox://styles/mapbox/satellite-streets-v12'
// Mapbox's stock globe atmosphere; the app's dark fog paints the satellite globe black from space.
const NATURAL_FOG = {
  color: 'rgb(186, 210, 235)',
  'high-color': 'rgb(36, 92, 223)',
  'horizon-blend': 0.02,
  'space-color': 'rgb(6, 6, 14)',
  'star-intensity': 0.5,
}
// Roads, tunnels, bridges, POI/transit/airport/neighbourhood labels: noise on a
// terrain orbit. Country/state/settlement/water/natural labels stay.
const CLUTTER_LAYERS = '^(tunnel|road|bridge)-|^aerialway$|^(path-pedestrian|ferry-aerialway|poi|transit|airport|settlement-subdivision)-label$'
// z2.2 fills the portrait width with the globe; z1.6 left it a small ball.
const SPACE_ZOOM = 2.2
const SITE_ZOOM = 14.2
const ORBIT_PITCH = 62
const ORBIT_BEARING_FROM = 20
const ORBIT_BEARING_TO = 110
const TERRAIN_EXAGGERATION = 1.4

// Start a quarter turn west and a little north so the first second visibly rotates.
const START_LNG_OFFSET = -40
const START_LAT_OFFSET = 15

// Any Three.js distance works here — enterMapbox syncs from it, then the path
// takes over with its own zoom.
const HANDOFF_DIST = 1.36
const FRAME_YIELD_MS = 40
const TILE_SETTLE_MS = 1500

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

function openingPath(site: SiteInput): MapboxKeyframe[] {
  const start = { lng: site.lng + START_LNG_OFFSET, lat: site.lat + START_LAT_OFFSET }
  const here = { lng: site.lng, lat: site.lat }
  return [
    { at: 0, ...start, zoom: SPACE_ZOOM, pitch: 0, bearing: 0 },
    { at: ROTATE_S / OPENING_S, ...here, zoom: SPACE_ZOOM, pitch: 0, bearing: 0 },
    { at: (ROTATE_S + ZOOM_S) / OPENING_S, ...here, zoom: SITE_ZOOM, pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_FROM },
    { at: 1, ...here, zoom: SITE_ZOOM, pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_TO },
  ]
}

async function runOpening(ctx: SceneContext): Promise<void> {
  const { page, demo, fire, recorder, fps } = ctx
  const site = loadSite()
  const path = openingPath(site)
  const first = path[0]
  const move = `window.__DEMO.mapboxPath(${JSON.stringify(path)}, ${OPENING_S * 1000})`
  console.log(`  Opening: ${site.name} (${site.lat}, ${site.lng}) @ ${fps} fps`)

  await demo.setAutoRotate(false)
  await demo.setSatellite(true)
  await demo.setCameraPose(site.lng, site.lat, HANDOFF_DIST)
  await settle(page)
  await demo.enterMapbox()
  await demo.mapboxWaitIdle(15000)
  await demo.setMapboxStyleUrl(STYLE_WITH_LABELS)
  await demo.setMapboxFog(NATURAL_FOG)
  console.log(`  hidden clutter layers: ${await demo.hideMapboxLayers(CLUTTER_LAYERS)}`)
  await demo.setTerrain(TERRAIN_EXAGGERATION)
  await demo.mapboxJumpTo(first.lng, first.lat, first.zoom, first.bearing, first.pitch)
  await demo.mapboxWaitIdle(20000)
  await realWait(TILE_SETTLE_MS)

  // Dry run without capture: caches the tiles along the whole zoom path and
  // the DEM at the orbit, so the real take does not pop tiles in.
  fire(move)
  await advanceFrames(page, OPENING_S * fps)
  await demo.mapboxWaitIdle(20000)
  await realWait(TILE_SETTLE_MS)

  await demo.mapboxJumpTo(first.lng, first.lat, first.zoom, first.bearing, first.pitch)
  await demo.mapboxWaitIdle(10000)
  await settle(page)
  fire(move)
  await recorder.capture(page, OPENING_S)
}

export const siteShortScenes: SceneDefinition[] = [
  {
    name: 'short-opening',
    duration: OPENING_S,
    resolution: 'short',
    canvasSelector: '.mapbox-globe-container canvas',
    frameYieldMs: FRAME_YIELD_MS,
    run: runOpening,
  },
]
