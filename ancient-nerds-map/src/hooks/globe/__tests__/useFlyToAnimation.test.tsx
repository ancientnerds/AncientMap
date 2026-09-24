/**
 * @vitest-environment jsdom
 *
 * Before the intro starts, the warp owns the camera. The globe now mounts at
 * once, so App's start-up fly-tos (?lat&lon, proximity=1) reach a scene that
 * exists; flown there before the warp, the camera would flip ~180° at the warp's
 * first frame. So a pre-warp fly-to waits: the latest one is flown once the
 * warp has ended (Globe calls replayPendingFlyTo from onWarpComplete), unless it
 * aims where the warp has just landed - every start-up target is the warp
 * target (initialPosition). A fly-to from another tab (focus-site,
 * fly-to-coords) that arrives while the globe loads is therefore not lost.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import * as THREE from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { computeWarpCameraPositions } from '../../../components/Globe/rendering/sceneInit'
import type { GlobeRefs } from '../types'
import { useFlyToAnimation } from '../useFlyToAnimation'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null
const booked = vi.fn(() => 7)

beforeEach(() => {
  booked.mockClear()
  vi.stubGlobal('requestAnimationFrame', booked)
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
  vi.unstubAllGlobals()
})

function makeRefs(warpStartTime: number | null, warpTarget: [number, number] = [10, 51]) {
  const camera = new THREE.PerspectiveCamera()
  camera.position.set(-2, 0.5, 1)
  const ref = <T,>(current: T) => ({ current })
  const refs = {
    warpStartTime: ref(warpStartTime),
    warpTargetCameraPos: ref(computeWarpCameraPositions(warpTarget).target),
    showMapbox: ref(false),
    mapboxService: ref(null),
    scene: ref({ camera, controls: { update: vi.fn() } }),
    cameraAnimation: ref<number | null>(null),
    isAutoRotating: ref(true),
    flyToDuration: ref(600),
  } as unknown as GlobeRefs
  return { refs, camera }
}

let replay: () => void = () => { throw new Error('not rendered') }

function Probe({ refs, flyTo }: { refs: GlobeRefs; flyTo: [number, number] | null }) {
  replay = useFlyToAnimation({ refs, flyTo }).replayPendingFlyTo
  return null
}

async function render(refs: GlobeRefs, flyTo: [number, number] | null) {
  if (!root) root = createRoot(document.createElement('div'))
  await act(async () => root!.render(<Probe refs={refs} flyTo={flyTo} />))
}

/** The warp's first frame (animationLoop sets warpStartTime), then its end (onWarpComplete). */
async function warpEnds(refs: GlobeRefs) {
  refs.warpStartTime.current = 1000
  await act(async () => replay())
}

/** Runs the booked fly-to frames to the end (performance.now past the duration). */
function runFlight(refs: GlobeRefs) {
  const now = vi.spyOn(performance, 'now').mockReturnValue(1e9)
  for (let i = 0; i < 5 && booked.mock.calls.length > 0; i++) {
    const frame = (booked.mock.calls.at(-1) as unknown as [FrameRequestCallback])[0]
    booked.mockClear()
    frame(0)
  }
  now.mockRestore()
  return refs
}

/** Unit direction of [lng, lat] (useFlyToAnimation's mapping). */
function direction([lng, lat]: [number, number]) {
  return computeWarpCameraPositions([lng, lat]).target.normalize()
}

describe('useFlyToAnimation', () => {
  it('does nothing before the warp has started', async () => {
    const { refs, camera } = makeRefs(null)
    const before = camera.position.clone()
    await render(refs, [13.4, 52.5])
    expect(booked).not.toHaveBeenCalled()
    expect(camera.position.equals(before)).toBe(true)
    expect(refs.isAutoRotating.current).toBe(true)
  })

  it("flies once the warp has started (a click during the intro's last seconds works as before)", async () => {
    const { refs } = makeRefs(1234)
    await render(refs, [13.4, 52.5])
    expect(booked).toHaveBeenCalledOnce()
    expect(refs.isAutoRotating.current).toBe(false)
  })

  it('flies to a fly-to that arrived before the warp once the warp has ended', async () => {
    const { refs, camera } = makeRefs(null, [10, 51])
    const athens: [number, number] = [23.7, 37.98]
    await render(refs, athens)
    expect(booked).not.toHaveBeenCalled()
    await warpEnds(refs)
    expect(booked).toHaveBeenCalledOnce()
    expect(refs.isAutoRotating.current).toBe(false)
    const distance = camera.position.length()
    runFlight(refs)
    expect(camera.position.clone().normalize().angleTo(direction(athens))).toBeLessThan(1e-6)
    expect(camera.position.length()).toBeCloseTo(distance, 9) // no zoom change
    expect(refs.isAutoRotating.current).toBe(true)
  })

  it('flies only to the latest of several pre-warp fly-tos, once', async () => {
    const { refs, camera } = makeRefs(null)
    const rome: [number, number] = [12.5, 41.9]
    await render(refs, [23.7, 37.98])
    await render(refs, null) // App: setFlyToCoords(null), then the next target a frame later
    await render(refs, rome)
    await warpEnds(refs)
    expect(booked).toHaveBeenCalledOnce()
    runFlight(refs)
    expect(camera.position.clone().normalize().angleTo(direction(rome))).toBeLessThan(1e-6)
    booked.mockClear()
    await act(async () => replay()) // a second warp end (remount) replays nothing
    expect(booked).not.toHaveBeenCalled()
  })

  it('does not fly again to where the warp has just landed (a start-up target: ?lat&lon, proximity=1)', async () => {
    const lima: [number, number] = [-77.04, -12.05]
    const { refs, camera } = makeRefs(null, lima)
    const before = camera.position.clone()
    await render(refs, lima)
    await warpEnds(refs)
    expect(booked).not.toHaveBeenCalled()
    expect(camera.position.equals(before)).toBe(true)
    expect(refs.isAutoRotating.current).toBe(true)
  })

  it('a fly-to during the warp replaces the one that was waiting', async () => {
    const { refs } = makeRefs(null)
    await render(refs, [23.7, 37.98])
    refs.warpStartTime.current = 1000 // the warp runs
    await render(refs, [12.5, 41.9]) // flies at once, as before
    expect(booked).toHaveBeenCalledOnce()
    booked.mockClear()
    await act(async () => replay())
    expect(booked).not.toHaveBeenCalled()
  })

  it('the warp ending without a waiting fly-to does nothing', async () => {
    const { refs } = makeRefs(null)
    await render(refs, null)
    await warpEnds(refs)
    expect(booked).not.toHaveBeenCalled()
  })
})
