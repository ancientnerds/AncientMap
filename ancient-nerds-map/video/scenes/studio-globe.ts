/**
 * Studio globe scenes, landscape 1920x1080 (spec 2026-09-26 section 4.5), driven by
 * pipeline/studio/capture/globe.py through STUDIO_SCENE_INPUT (record.ts sets it
 * from --input). Our vector globe only: every distance stays at or above 1.2,
 * well outside CAMERA_EXTENDED.MAPBOX_ENABLE_DISTANCE (1.12), so no Mapbox tile
 * is drawn and the shot carries no map credit. Frames are grabbed one by one
 * (studio-frames.ts) into the input's frames_dir; every scene first writes the
 * page's WebGL renderer to renderer_path, which globe.py checks (spec 4.11).
 * Places are projected per frame (owner rule): after every grabbed frame a
 * PointTracker reads where the page draws each place (window.__DEMO.screenPoint)
 * and points_path receives one pixel or null per frame and place.
 *
 *   studio-globe-flyto   space pose, rotate onto lat/lng (rotate_s), zoom to
 *                        `distance` (zoom_s), hold; optional empire layer; with
 *                        `places` (the target) it tracks the target in every frame
 *   studio-globe-places  a pose that frames the places, fixed (sweep_lng_deg 0:
 *                        computed in Python by projection.fit_globe_distance) or
 *                        sweeping the camera longitude from cam_lng by
 *                        sweep_lng_deg over the take (globe.py's world
 *                        distribution is a sweep of 360 degrees)
 *
 *   VITE_DEV_API_TARGET=https://ancientnerds.com npm run video:record -- \
 *     studio-globe-flyto --fps 60 --input <input.json> --out <dir>
 */

import { readFileSync } from 'fs'
import type { SceneContext, SceneDefinition } from '../record'
import { FrameGrabber, GLOBE_CANVAS, PointTracker, type TrackedPlace, nextFrames, writeRenderer } from './studio-frames.js'

export interface StudioInput {
  scene: string
  duration_s: number
  frames_dir: string
  /** Where the scene writes {"renderer": <WebGL renderer>} (studio-frames.ts writeRenderer). */
  renderer_path: string
}

export interface FlytoInput extends StudioInput {
  scene: 'flyto'
  lat: number
  lng: number
  distance: number
  empire: string | null
  rotate_s: number
  zoom_s: number
  /** With a place: the target to track in every frame, and where its pixels go. */
  places?: TrackedPlace[]
  points_path?: string
}

export interface PlacesInput extends StudioInput {
  scene: 'places'
  cam_lat: number
  /** Camera longitude of the first frame. */
  cam_lng: number
  distance: number
  /** Degrees the camera longitude turns over the take (0: a fixed pose). */
  sweep_lng_deg: number
  places: TrackedPlace[]
  /** Where the scene writes {place id: [[x, y] | null, ...]}, one entry per frame. */
  points_path: string
}

/** Three.js camera distance the fly-to starts from: the whole globe in frame. */
export const SPACE_DISTANCE = 2.3
/** Start this far west and north of the target so the first second visibly rotates. */
export const START_LNG_OFFSET = -40
export const START_LAT_OFFSET = 15

/** Read the scene input written by globe.py; the scene must match and both output paths must be named. */
export function readStudioInput<T extends StudioInput>(scene: T['scene']): T {
  const path = process.env.STUDIO_SCENE_INPUT
  if (!path) throw new Error('STUDIO_SCENE_INPUT not set: pass --input <input.json>')
  const input = JSON.parse(readFileSync(path, 'utf-8')) as T
  if (input.scene !== scene) throw new Error(`${path} holds a ${input.scene} input, the scene needs ${scene}`)
  if (!(input.duration_s > 0)) throw new Error(`${path}: duration_s must be positive`)
  if (typeof input.frames_dir !== 'string' || input.frames_dir === '') throw new Error(`${path}: frames_dir is missing`)
  if (typeof input.renderer_path !== 'string' || input.renderer_path === '') throw new Error(`${path}: renderer_path is missing`)
  return input
}

/** Start pose of the fly-to (latitude clamped away from the poles, where lookAt degenerates). */
export function flytoStart(input: Pick<FlytoInput, 'lat' | 'lng'>): { lng: number; lat: number } {
  return { lng: input.lng + START_LNG_OFFSET, lat: Math.max(-70, Math.min(70, input.lat + START_LAT_OFFSET)) }
}

/** Camera longitude of frame `index` of a sweep: linear from `from` by `sweep` degrees over the take, in -180..180. */
export function sweepLng(from: number, sweep: number, index: number, fps: number, durationS: number): number {
  const lng = from + (sweep * index) / (fps * durationS)
  return ((((lng + 180) % 360) + 360) % 360) - 180
}

async function runFlyto(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<FlytoInput>('flyto')
  const { page, demo, fire } = ctx
  if (input.places !== undefined && !input.points_path) throw new Error('a flyto input with places needs points_path')
  const grabber = new FrameGrabber(input.frames_dir, GLOBE_CANVAS, false)
  await writeRenderer(page, input.renderer_path)
  const tracker = input.places === undefined ? null : new PointTracker(input.places)
  const hooks = tracker ? { after: () => tracker.sample(page) } : {}
  const start = flytoStart(input)
  await demo.setAutoRotate(false)
  await demo.setCameraPose(start.lng, start.lat, SPACE_DISTANCE)
  if (input.empire) await demo.showEmpire(input.empire)
  await demo.setFlyToDuration(input.rotate_s * 1000)
  await nextFrames(page)
  // The app's fly-to keeps the distance it starts with, so rotate first, then zoom.
  fire(`window.__DEMO.flyTo(${input.lng}, ${input.lat})`)
  await grabber.grabUntil(ctx, input.rotate_s, hooks)
  fire(`window.__DEMO.smoothZoom(${SPACE_DISTANCE}, ${input.distance}, ${input.zoom_s * 1000})`)
  await grabber.grabUntil(ctx, input.rotate_s + input.zoom_s, hooks)
  await grabber.grabUntil(ctx, input.duration_s, hooks)
  if (tracker && input.points_path) tracker.write(input.points_path, grabber.frames)
}

async function runPlaces(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<PlacesInput>('places')
  const { page, demo } = ctx
  const grabber = new FrameGrabber(input.frames_dir, GLOBE_CANVAS, false)
  await writeRenderer(page, input.renderer_path)
  await demo.setAutoRotate(false)
  await demo.setCameraPose(input.cam_lng, input.cam_lat, input.distance)
  await nextFrames(page)
  // The page's own camera (telephoto FOV included) says where each place is drawn, frame by frame.
  const tracker = new PointTracker(input.places)
  const turn = async (index: number) => {
    await demo.setCameraPose(sweepLng(input.cam_lng, input.sweep_lng_deg, index, ctx.fps, input.duration_s), input.cam_lat, input.distance)
  }
  await grabber.grabUntil(ctx, input.duration_s, {
    ...(input.sweep_lng_deg === 0 ? {} : { before: turn }),
    after: () => tracker.sample(page),
  })
  tracker.write(input.points_path, grabber.frames)
}

export const studioGlobeScenes: SceneDefinition[] = [
  { name: 'studio-globe-flyto', duration: () => readStudioInput<FlytoInput>('flyto').duration_s, resolution: 'section', grabsFrames: true, run: runFlyto },
  { name: 'studio-globe-places', duration: () => readStudioInput<PlacesInput>('places').duration_s, resolution: 'section', grabsFrames: true, run: runPlaces },
]
