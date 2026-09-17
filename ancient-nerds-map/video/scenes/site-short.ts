/**
 * Site-short globe clips — two Mapbox takes per site that make the short loop
 * (spec: docs/superpowers/specs/2026-09-16-site-shorts-prototype-design.md).
 *
 *   short-opening (6.1 s) 0.1 s hold on the space pose (trimmed by the renderer),
 *                         satellite globe rotates onto the site (1 s), continuous
 *                         zoom down to z14 with tilt (2 s), 3D orbit (3 s)
 *   short-return  (3 s)   from the orbit's end pose back up to the space pose —
 *                         its last frame is the opening's first kept frame, so the
 *                         finished short loops without a visible cut.
 *
 * Everything runs on the Mapbox globe (satellite-streets style = imagery +
 * labels, DEM terrain, stock atmosphere, roads/POIs/site dots hidden, raster
 * fades off). Tiles along a path are warmed up by jumping to sampled poses and
 * waiting for `idle` at each: a real-time dry run lets Mapbox abort requests for
 * views it has already left, which shows as black frames on zoom-outs.
 *
 * Input: SITE_SHORT_INPUT = path to `video-assets/shorts/<slug>/site.json`
 * (record.ts sets it from `--input`). Record in portrait at 60 fps:
 *   VITE_DEV_API_TARGET=https://ancientnerds.com npm run video:record -- \
 *     short-opening,short-return --portrait --fps 60 --input <site.json> --out <dir>/clips
 */

import { readFileSync } from 'fs'
import type { SceneDefinition, SceneContext } from '../record'
import type { MapboxKeyframe } from '../../src/utils/demoApi'
import { getCountryCode } from '../../src/utils/countryFlags'
import { settle } from '../utils/helpers.js'

interface SiteInput {
  name: string
  lat: number
  lng: number
  country?: string
  /** Orbit zoom by site type (pipeline/video/shorts_export.orbit_zoom_for); SITE_ZOOM if absent. */
  orbit_zoom?: number
  /** Length of the spoken name (written by the tts step); the return flight must outlast it. */
  name_audio_s?: number
}

// The site's country tinted on the globe (brand green, --_palette-green-bright):
// visible in space on both takes, so the loop frames match; gone inside the country.
const COUNTRY_HIGHLIGHT = '#00cc66'

const HOLD_S = 0.1 // must match OPENING_TRIM_S in pipeline/video/shorts_render.py
const ROTATE_S = 1
const ZOOM_S = 2
const ORBIT_S = 3
const OPENING_TAKE_S = HOLD_S + ROTATE_S + ZOOM_S + ORBIT_S
const RETURN_MIN_S = 3
// Spoken name starts NAME_AUDIO_DELAY_S into the return and must be over
// NAME_END_GAP_S before the loop point (both mirror shorts_render.py).
const NAME_AUDIO_DELAY_S = 0.2
const NAME_END_GAP_S = 0.15

/** Return flight length: at least RETURN_MIN_S, longer for long spoken names. */
function returnSeconds(site: SiteInput): number {
  const needed = (site.name_audio_s ?? 0) + NAME_AUDIO_DELAY_S + NAME_END_GAP_S + 0.3
  return Math.max(RETURN_MIN_S, Math.ceil(needed * 10) / 10)
}

const STYLE_WITH_LABELS = 'mapbox://styles/mapbox/satellite-streets-v12'
// Mapbox's stock globe atmosphere; the app's dark fog paints the satellite globe black from space.
const NATURAL_FOG = {
  color: 'rgb(186, 210, 235)',
  'high-color': 'rgb(36, 92, 223)',
  'horizon-blend': 0.02,
  'space-color': 'rgb(6, 6, 14)',
  'star-intensity': 0.5,
}
// Roads, tunnels, bridges, POI/transit/airport/neighbourhood labels and the
// app's site dots: noise on a terrain orbit. Country/state/settlement/water/
// natural labels stay.
const CLUTTER_LAYERS = '^(tunnel|road|bridge|sites)-|^aerialway$|^(path-pedestrian|ferry-aerialway|poi|transit|airport|settlement-subdivision)-label$'
// z2.2 fills the portrait width with the globe; z1.6 left it a small ball.
const SPACE_ZOOM = 2.2
const SITE_ZOOM = 14.2 // default orbit zoom; site.json overrides per site type
const ORBIT_PITCH = 62
const ORBIT_BEARING_FROM = 20
const ORBIT_BEARING_TO = 110
const TERRAIN_EXAGGERATION = 1.4

// Start 40° west and a little north so the first second visibly rotates onto the site.
const START_LNG_OFFSET = -40
const START_LAT_OFFSET = 15

// Any Three.js distance works here — enterMapbox syncs from it, then the paths
// take over with their own zoom.
const HANDOFF_DIST = 1.36
const FRAME_YIELD_MS = 40
const WARMUP_SAMPLES_PER_S = 3

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

function spacePose(site: SiteInput): MapboxKeyframe {
  return { at: 0, lng: site.lng + START_LNG_OFFSET, lat: site.lat + START_LAT_OFFSET, zoom: SPACE_ZOOM, pitch: 0, bearing: 0 }
}

function orbitZoom(site: SiteInput): number {
  return site.orbit_zoom ?? SITE_ZOOM
}

function orbitEndPose(site: SiteInput): MapboxKeyframe {
  return { at: 0, lng: site.lng, lat: site.lat, zoom: orbitZoom(site), pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_TO }
}

function openingPath(site: SiteInput): MapboxKeyframe[] {
  const space = spacePose(site)
  const here = { lng: site.lng, lat: site.lat }
  const t = (s: number) => s / OPENING_TAKE_S
  // Terrain off while in space and switched on for the zoom: the return flight
  // ends with terrain off, and the two loop frames must render identically
  // (Greenland's ice sheet showed a visible difference with terrain on).
  return [
    { ...space, terrain: null },
    { ...space, at: t(HOLD_S) },
    { at: t(HOLD_S + ROTATE_S), ...here, zoom: SPACE_ZOOM, pitch: 0, bearing: 0, terrain: TERRAIN_EXAGGERATION },
    { at: t(HOLD_S + ROTATE_S + ZOOM_S), ...here, zoom: orbitZoom(site), pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_FROM },
    { ...orbitEndPose(site), at: 1 },
  ]
}

// Return flight in three legs, all with the centre pinned on the site until high:
//   1. lift off over the site (terrain on) — swinging while low and pitched put
//      the camera inside the Andes west of Machu Picchu (brown wall, black frames);
//   2. rise to a flat, north-up view with terrain OFF — moving the centre from
//      mountains to sea with terrain on recomputes the camera height and drops
//      it below the surface;
//   3. slide the centre to the space pose the opening holds at its start.
const LIFT_AT = 0.3
const LIFT_ZOOM = 11.5
const LIFT_PITCH = 20
const HIGH_AT = 0.6
const HIGH_ZOOM = 5

// The return arrives at the space pose END_HOLD_S before the take ends and
// holds it, so the last frame is exactly the pose the opening starts from.
const END_HOLD_S = 0.1

function returnPath(site: SiteInput): MapboxKeyframe[] {
  const end = orbitEndPose(site)
  const space = spacePose(site)
  return [
    { ...end, terrain: TERRAIN_EXAGGERATION },
    { ...end, at: LIFT_AT, zoom: LIFT_ZOOM, pitch: LIFT_PITCH, terrain: null },
    { ...end, at: HIGH_AT, zoom: HIGH_ZOOM, pitch: 0, bearing: 0 },
    { ...space, at: 1 - END_HOLD_S / returnSeconds(site) },
    { ...space, at: 1 },
  ]
}

/** Enter Mapbox with the recording look: labels, atmosphere, terrain, no clutter, no raster fades. */
async function prepareMapbox(ctx: SceneContext, site: SiteInput): Promise<void> {
  const { page, demo } = ctx
  await demo.setAutoRotate(false)
  await demo.setSatellite(true)
  await demo.setCameraPose(site.lng, site.lat, HANDOFF_DIST)
  await settle(page)
  await demo.enterMapbox()
  await demo.mapboxWaitIdle(15000)
  await demo.setMapboxStyleUrl(STYLE_WITH_LABELS)
  await demo.mapboxWaitIdle(15000)
  await demo.setMapboxFog(NATURAL_FOG)
  console.log(`  hidden clutter layers: ${await demo.hideMapboxLayers(CLUTTER_LAYERS)}`)
  const code = site.country ? getCountryCode(site.country) : null
  if (code) {
    await demo.setMapboxCountryHighlight(code, COUNTRY_HIGHLIGHT)
    console.log(`  country highlight: ${code}`)
  } else {
    console.log(`  no country code for ${JSON.stringify(site.country)}: no highlight`)
  }
  await demo.setMapboxRasterFade(0)
  await demo.setTerrain(TERRAIN_EXAGGERATION)
}

/** Warm the tile/DEM cache along the path, reset to its first pose, then capture. */
async function recordPath(ctx: SceneContext, path: MapboxKeyframe[], seconds: number): Promise<void> {
  const { page, demo, fire, recorder } = ctx
  const samples = Math.max(2, Math.round(seconds * WARMUP_SAMPLES_PER_S))
  for (let i = 0; i <= samples; i++) {
    await demo.mapboxJumpToPathPose(path, i / samples)
    await demo.mapboxWaitIdle(15000)
  }
  console.log(`  warmed ${samples + 1} poses`)

  await demo.mapboxJumpToPathPose(path, 0)
  await demo.mapboxWaitIdle(15000)
  await realWait(500)
  await settle(page)
  fire(`window.__DEMO.mapboxPath(${JSON.stringify(path)}, ${seconds * 1000})`)
  await recorder.capture(page, seconds)
}

async function runOpening(ctx: SceneContext): Promise<void> {
  const site = loadSite()
  console.log(`  Opening: ${site.name} (${site.lat}, ${site.lng}) @ ${ctx.fps} fps`)
  await prepareMapbox(ctx, site)
  await recordPath(ctx, openingPath(site), OPENING_TAKE_S)
}

async function runReturn(ctx: SceneContext): Promise<void> {
  const site = loadSite()
  console.log(`  Return: ${site.name} @ ${ctx.fps} fps, ${returnSeconds(site)} s`)
  await prepareMapbox(ctx, site)
  await recordPath(ctx, returnPath(site), returnSeconds(site))
}

const MAPBOX_CANVAS = '.mapbox-globe-container canvas'

export const siteShortScenes: SceneDefinition[] = [
  { name: 'short-opening', duration: OPENING_TAKE_S, resolution: 'short', canvasSelector: MAPBOX_CANVAS, frameYieldMs: FRAME_YIELD_MS, waitForTiles: true, run: runOpening },
  { name: 'short-return', duration: () => returnSeconds(loadSite()), resolution: 'short', canvasSelector: MAPBOX_CANVAS, frameYieldMs: FRAME_YIELD_MS, waitForTiles: true, run: runReturn },
]
