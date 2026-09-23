/**
 * @vitest-environment jsdom
 *
 * Before the intro starts, the warp owns the camera. The globe now mounts at
 * once, so App's start-up fly-tos (?lat&lon, proximity=1) reach a scene that
 * exists; flown there before the warp, the camera would flip ~180° at the warp's
 * first frame. Every start-up target is already the warp target
 * (initialPosition), so a pre-warp fly-to does nothing.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import * as THREE from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

function makeRefs(warpStartTime: number | null) {
  const camera = new THREE.PerspectiveCamera()
  camera.position.set(-2, 0.5, 1)
  const ref = <T,>(current: T) => ({ current })
  const refs = {
    warpStartTime: ref(warpStartTime),
    showMapbox: ref(false),
    mapboxService: ref(null),
    scene: ref({ camera, controls: { update: vi.fn() } }),
    cameraAnimation: ref<number | null>(null),
    isAutoRotating: ref(true),
    flyToDuration: ref(600),
  } as unknown as GlobeRefs
  return { refs, camera }
}

function Probe({ refs, flyTo }: { refs: GlobeRefs; flyTo: [number, number] | null }) {
  useFlyToAnimation({ refs, flyTo })
  return null
}

async function render(refs: GlobeRefs, flyTo: [number, number] | null) {
  const container = document.createElement('div')
  root = createRoot(container)
  await act(async () => root!.render(<Probe refs={refs} flyTo={flyTo} />))
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
})
