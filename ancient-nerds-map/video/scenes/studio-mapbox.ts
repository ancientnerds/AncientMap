/**
 * Studio Mapbox scenes, landscape 1920x1080 (spec 2026-09-26 section 4.5): the
 * site-short fly-in adapted to 16:9 and a plain orbit. Same recording look and
 * tile warm-up as the shorts (prepareMapbox / warmPath from site-short.ts);
 * input from pipeline/studio/capture/globe.py via STUDIO_SCENE_INPUT; every
 * frame is grabbed exactly (studio-frames.ts), each after its tiles loaded;
 * the page's WebGL renderer goes to renderer_path first (spec 4.11).
 *
 *   studio-mapbox-flyin  satellite globe from space, rotate onto the site
 *                        (ROTATE_S), zoom in with tilt (ZOOM_S), orbit for the rest
 *   studio-mapbox-orbit  terrain orbit around the site, bearing_from to bearing_to
 *
 * Map content: the capture manifest credits "© Mapbox © OpenStreetMap © Maxar".
 */

import { getCountryCode } from '../../src/utils/countryFlags'
import type { MapboxKeyframe } from '../../src/utils/demoApi'
import type { SceneContext, SceneDefinition } from '../record'
import { TERRAIN_EXAGGERATION, prepareMapbox, warmPath } from './site-short.js'
import { FrameGrabber, MAPBOX_CANVAS, writeRenderer } from './studio-frames.js'
import { type StudioInput, flytoStart, readStudioInput } from './studio-globe.js'

export interface FlyinInput extends StudioInput {
  scene: 'mapbox_flyin'
  name: string
  lat: number
  lng: number
  country?: string
  orbit_zoom: number
}

export interface OrbitInput extends StudioInput {
  scene: 'mapbox_orbit'
  name: string
  lat: number
  lng: number
  country?: string
  zoom: number
  pitch: number
  bearing_from: number
  bearing_to: number
}

/**
 * The satellite globe's diameter is about 512 * 2^zoom / pi px: z2.4 fills ~80 % of
 * the 1080 px frame height (z1.7 filled half of it in the first real take, 2026-09-26).
 */
export const SPACE_ZOOM = 2.4
export const ROTATE_S = 1.2
export const ZOOM_S = 2.4
export const ORBIT_PITCH = 60
export const ORBIT_BEARING_FROM = 20
export const ORBIT_BEARING_TO = 100

/** Space pose, rotate onto the site, zoom in with tilt, orbit until the end of the take. */
export function flyinPath(input: Pick<FlyinInput, 'lat' | 'lng' | 'orbit_zoom' | 'duration_s'>): MapboxKeyframe[] {
  const minimum = ROTATE_S + ZOOM_S + 1
  if (input.duration_s < minimum) throw new Error(`studio-mapbox-flyin needs at least ${minimum} s, got ${input.duration_s}`)
  const t = (s: number) => s / input.duration_s
  const here = { lng: input.lng, lat: input.lat }
  return [
    { at: 0, ...flytoStart(input), zoom: SPACE_ZOOM, pitch: 0, bearing: 0, terrain: null },
    { at: t(ROTATE_S), ...here, zoom: SPACE_ZOOM, pitch: 0, bearing: 0, terrain: TERRAIN_EXAGGERATION },
    { at: t(ROTATE_S + ZOOM_S), ...here, zoom: input.orbit_zoom, pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_FROM },
    { at: 1, ...here, zoom: input.orbit_zoom, pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_TO },
  ]
}

/** One eased sweep of the bearing around the site. */
export function orbitPath(input: Pick<OrbitInput, 'lat' | 'lng' | 'zoom' | 'pitch' | 'bearing_from' | 'bearing_to'>): MapboxKeyframe[] {
  const pose = { lng: input.lng, lat: input.lat, zoom: input.zoom, pitch: input.pitch }
  return [
    { at: 0, ...pose, bearing: input.bearing_from, terrain: TERRAIN_EXAGGERATION },
    { at: 1, ...pose, bearing: input.bearing_to },
  ]
}

/**
 * A studio take's `country` is shown data (plan C binds it to the site export): a
 * name the site's country table does not know would make prepareMapbox log "no
 * highlight" and record the take without it, so it is refused before anything
 * is recorded. The site Shorts keep prepareMapbox's own behaviour.
 */
export function checkCountry(country: string | undefined): void {
  if (country !== undefined && getCountryCode(country) === null) throw new Error(`unknown country ${JSON.stringify(country)}: getCountryCode has no code for it, the take would lack its highlight`)
}

async function flyPath(ctx: SceneContext, input: FlyinInput | OrbitInput, path: MapboxKeyframe[]): Promise<void> {
  checkCountry(input.country)
  const grabber = new FrameGrabber(input.frames_dir, MAPBOX_CANVAS, true)
  await writeRenderer(ctx.page, input.renderer_path)
  await prepareMapbox(ctx, input)
  await warmPath(ctx, path, input.duration_s)
  ctx.fire(`window.__DEMO.mapboxPath(${JSON.stringify(path)}, ${input.duration_s * 1000})`)
  await grabber.grabUntil(ctx, input.duration_s)
}

async function runFlyin(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<FlyinInput>('mapbox_flyin')
  await flyPath(ctx, input, flyinPath(input))
}

async function runOrbit(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<OrbitInput>('mapbox_orbit')
  await flyPath(ctx, input, orbitPath(input))
}

export const studioMapboxScenes: SceneDefinition[] = [
  { name: 'studio-mapbox-flyin', duration: () => readStudioInput<FlyinInput>('mapbox_flyin').duration_s, resolution: 'section', grabsFrames: true, run: runFlyin },
  { name: 'studio-mapbox-orbit', duration: () => readStudioInput<OrbitInput>('mapbox_orbit').duration_s, resolution: 'section', grabsFrames: true, run: runOrbit },
]
