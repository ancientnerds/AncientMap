/**
 * Pure input, path and frame logic of the studio recorder scenes
 * (video/scenes/studio-globe.ts, studio-mapbox.ts, studio-frames.ts). The takes
 * themselves need headed Chrome and run only on the workstation
 * (pipeline/studio/capture/globe.py).
 */

import { mkdtempSync, readFileSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import type { Page } from 'puppeteer'

import { afterEach, describe, expect, it } from 'vitest'

import { FrameGrabber, NO_FRAME_MS, PointTracker, frameCount, frameName } from '../studio-frames'
import { type PlacesInput, START_LNG_OFFSET, flytoStart, readStudioInput, sweepLng } from '../studio-globe'
import { ORBIT_BEARING_TO, ROTATE_S, SPACE_ZOOM, ZOOM_S, checkCountry, flyinPath, orbitPath } from '../studio-mapbox'

const saved = process.env.STUDIO_SCENE_INPUT

afterEach(() => {
  if (saved === undefined) delete process.env.STUDIO_SCENE_INPUT
  else process.env.STUDIO_SCENE_INPUT = saved
})

function writeInput(data: object): string {
  const file = join(mkdtempSync(join(tmpdir(), 'studio-scene-')), 'input.json')
  writeFileSync(file, JSON.stringify(data))
  return file
}

describe('readStudioInput', () => {
  it('reads the input of the matching scene', () => {
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'places', cam_lat: 30, cam_lng: 20, distance: 1.8, duration_s: 6, frames_dir: '/tmp/f', renderer_path: '/tmp/r.json' })
    expect(readStudioInput<PlacesInput>('places').duration_s).toBe(6)
  })
  it('refuses a missing variable, another scene, a non-positive duration and missing output paths', () => {
    delete process.env.STUDIO_SCENE_INPUT
    expect(() => readStudioInput('flyto')).toThrow(/STUDIO_SCENE_INPUT not set/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'places', duration_s: 6, frames_dir: '/tmp/f', renderer_path: '/tmp/r.json' })
    expect(() => readStudioInput('flyto')).toThrow(/holds a places input, the scene needs flyto/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'flyto', duration_s: 0, frames_dir: '/tmp/f', renderer_path: '/tmp/r.json' })
    expect(() => readStudioInput('flyto')).toThrow(/duration_s must be positive/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'flyto', duration_s: 5, renderer_path: '/tmp/r.json' })
    expect(() => readStudioInput('flyto')).toThrow(/frames_dir is missing/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'flyto', duration_s: 5, frames_dir: '/tmp/f' })
    expect(() => readStudioInput('flyto')).toThrow(/renderer_path is missing/)
  })
})

describe('studio-globe-flyto', () => {
  it('starts west and north of the target, away from the poles', () => {
    expect(flytoStart({ lat: 34, lng: 36.2 })).toEqual({ lng: 36.2 + START_LNG_OFFSET, lat: 49 })
    expect(flytoStart({ lat: 68, lng: 0 }).lat).toBe(70)
  })
})

describe('studio-globe-places sweep', () => {
  it('turns the camera linearly over the take and keeps the longitude in -180..180', () => {
    expect(sweepLng(-10, 120, 0, 60, 6)).toBe(-10)
    expect(sweepLng(-10, 120, 90, 60, 6)).toBe(20)
    expect(sweepLng(170, 40, 60, 60, 2)).toBe(-170)
  })
})

describe('PointTracker (points.json)', () => {
  const places = [
    { id: 'p1', lat: 34, lng: 36.2 },
    { id: 'p2', lat: 29.98, lng: 31.13 },
  ]
  it('keeps one pixel or null per grabbed frame and place, read in one page call', async () => {
    const answers = [
      [{ x: 1, y: 2 }, null],
      [
        { x: 3, y: 4 },
        { x: 5, y: 6 },
      ],
    ]
    const calls: string[] = []
    const page = { evaluate: async (code: string) => (calls.push(code), answers[calls.length - 1]) } as unknown as Page
    const tracker = new PointTracker(places)
    await tracker.sample(page)
    await tracker.sample(page)
    expect(calls).toHaveLength(2)
    expect(calls[0]).toContain('window.__DEMO.screenPoint')
    const file = join(mkdtempSync(join(tmpdir(), 'studio-points-')), 'points.json')
    tracker.write(file, 2)
    expect(JSON.parse(readFileSync(file, 'utf-8'))).toEqual({ p1: [[1, 2], [3, 4]], p2: [null, [5, 6]] })
    expect(() => tracker.write(file, 3)).toThrow(/place p1: 2 points for 3 frames/)
  })
})

describe('studio-mapbox-flyin', () => {
  const input = { lat: 34.0067, lng: 36.2033, orbit_zoom: 15, duration_s: 8 }
  it('rotates onto the site, zooms in, then orbits to the end of the take', () => {
    const path = flyinPath(input)
    expect(path.map((k) => k.at)).toEqual([0, ROTATE_S / 8, (ROTATE_S + ZOOM_S) / 8, 1])
    expect(path[0]).toMatchObject({ zoom: SPACE_ZOOM, terrain: null })
    expect(path[1]).toMatchObject({ lng: 36.2033, lat: 34.0067, zoom: SPACE_ZOOM })
    expect(path[3]).toMatchObject({ lng: 36.2033, lat: 34.0067, zoom: 15, bearing: ORBIT_BEARING_TO })
  })
  it('refuses a take too short for rotate + zoom + a second of orbit', () => {
    expect(() => flyinPath({ ...input, duration_s: 4 })).toThrow(/needs at least 4.6 s/)
  })
})

describe('Mapbox country highlight', () => {
  it('refuses a country the site cannot highlight instead of recording the take without it', () => {
    expect(() => checkCountry(undefined)).not.toThrow()
    expect(() => checkCountry('Lebanon')).not.toThrow()
    expect(() => checkCountry('Atlantis')).toThrow(/unknown country "Atlantis"/)
  })
})

describe('studio-mapbox-orbit', () => {
  it('sweeps the bearing around a fixed centre with terrain', () => {
    expect(orbitPath({ lat: 1, lng: 2, zoom: 16, pitch: 55, bearing_from: 0, bearing_to: 90 })).toEqual([
      { at: 0, lng: 2, lat: 1, zoom: 16, pitch: 55, bearing: 0, terrain: 1.4 },
      { at: 1, lng: 2, lat: 1, zoom: 16, pitch: 55, bearing: 90 },
    ])
  })
})

describe('exact frames', () => {
  it('names frames for ffmpeg and counts them to the nearest frame', () => {
    expect(frameName(0)).toBe('f000000.jpg')
    expect(frameName(1234)).toBe('f001234.jpg')
    expect(() => frameName(-1)).toThrow(/not a non-negative integer/)
    expect(frameCount(1.5, 60)).toBe(90)
    expect(frameCount(3.5, 60)).toBe(210)
    expect(() => frameCount(0, 60)).toThrow(/cannot count frames/)
  })
  it('gives up on a missing animation frame after 30 s', () => {
    expect(NO_FRAME_MS).toBe(30_000)
  })
  it('refuses a frames directory that already holds frames', () => {
    const dir = mkdtempSync(join(tmpdir(), 'studio-frames-'))
    writeFileSync(join(dir, frameName(0)), 'x')
    expect(() => new FrameGrabber(dir, '.globe-container canvas', false)).toThrow(/is not empty/)
  })
})
