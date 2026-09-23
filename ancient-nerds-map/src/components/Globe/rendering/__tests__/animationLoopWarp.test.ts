/**
 * @vitest-environment jsdom
 *
 * The intro warp. It starts when the loading overlay starts to fade
 * (splashDone) and this globe's layers are ready, never before: a globe that
 * mounts at once and loads faster than the sites or a focus site's position
 * would otherwise spin in behind the overlay. Until the first warp frame the
 * target may still move (a late geolocation); onWarpComplete fires exactly once,
 * in the frame the warp ends, and is what starts the background queue.
 *
 * Driven frame by frame: requestAnimationFrame is captured, real three objects.
 */

import * as THREE from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FadeManager } from '../../../../utils/FadeManager'
import { type AnimationLoopContext, runAnimationLoop } from '../animationLoop'
import { computeWarpCameraPositions } from '../sceneInit'

let pending: FrameRequestCallback | null = null

beforeEach(() => {
  pending = null
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    pending = cb
    return 1
  })
  vi.stubGlobal('cancelAnimationFrame', () => { pending = null })
})

afterEach(() => vi.unstubAllGlobals())

/** Runs one booked frame. */
function frame(): void {
  const cb = pending
  if (!cb) throw new Error('no frame booked')
  pending = null
  cb(performance.now())
}

function makeCtx(position: [number, number] | null) {
  const camera = new THREE.PerspectiveCamera(60, 16 / 9, 0.01, 1500)
  const { start, target } = computeWarpCameraPositions(position)
  camera.position.copy(start)
  const starMaterial = new THREE.ShaderMaterial({ uniforms: { uGlobeScale: { value: 0.3 }, uCameraDist: { value: 0 } } })
  const starsGroup = new THREE.Group()
  starsGroup.add(new THREE.Points(new THREE.BufferGeometry(), starMaterial))
  const onWarpComplete = vi.fn()
  const ref = <T,>(current: T) => ({ current })

  const ctx: AnimationLoopContext = {
    renderer: { getContext: () => ({ isContextLost: () => false }), render: vi.fn() } as unknown as THREE.WebGLRenderer,
    scene: new THREE.Scene(),
    camera,
    controls: { update: vi.fn() } as unknown as AnimationLoopContext['controls'],
    globe: new THREE.Mesh(),
    starsGroup,
    minDist: 1.02,
    maxDist: 2.44,
    rotationSpeed: 0.01,
    lastFrameTime: { value: performance.now() },
    frames: { value: 0 },
    fpsLastTime: { value: performance.now() },
    animationId: { value: 0 },
    _cameraDir: new THREE.Vector3(),
    _centerPoint: new THREE.Vector3(),
    _right: new THREE.Vector3(),
    _up: new THREE.Vector3(0, 1, 0),
    _p1: new THREE.Vector3(),
    _p2: new THREE.Vector3(),
    _p1Screen: new THREE.Vector3(),
    _p2Screen: new THREE.Vector3(),
    isPageVisibleRef: ref(true),
    webglContextLostRef: ref(false),
    onContextLost: vi.fn(),
    fpsRef: ref(null),
    lowFpsStartTimeRef: ref(null),
    setLowFps: vi.fn(),
    warpProgressRef: ref(0),
    warpLinearProgressRef: ref(0),
    warpStartTimeRef: ref<number | null>(null),
    warpCompleteForLabelsRef: ref(false),
    warpInitialCameraPosRef: ref<THREE.Vector3 | null>(start.clone()),
    warpTargetCameraPosRef: ref<THREE.Vector3 | null>(target),
    layersReadyCalledRef: ref(false),
    dotsAnimationCompleteRef: ref(false),
    logoAnimationStartedRef: ref(false),
    onWarpComplete,
    logoSpriteRef: ref(null),
    logoMaterialRef: ref(null),
    basemapMeshRef: ref(new THREE.Mesh()),
    basemapBackMeshRef: ref(new THREE.Mesh()),
    basemapSectionMeshes: ref([]),
    shaderMaterialsRef: ref([]),
    selectedDotMaterialRef: ref(null),
    dotSizeRef: ref(1),
    isAutoRotatingRef: ref(true),
    isHoveringListRef: ref(false),
    manualRotationRef: ref(false),
    backgroundLoadingCompleteRef: ref(true),
    showMapboxRef: ref(false),
    mapboxServiceRef: ref(null),
    mapboxTransitioningRef: ref(false),
    satelliteModeRef: ref(false),
    isManualZoom: ref(false),
    setZoom: vi.fn(),
    splashDoneRef: ref<boolean | undefined>(false),
    starsRef: ref(starsGroup),
    updateEmpireLabelsVisibilityRef: ref(null),
    updateMeasurementLabelsVisibilityRef: ref(null),
    lastScaleUpdateRef: ref(0),
    kmPerPixelRef: ref(1),
    setScaleBar: vi.fn(),
    listHighlightedSitesRef: ref([]),
    showTooltipsRef: ref(true),
    setListHighlightedPositions: vi.fn(),
    listHighlightedPositionsRef: ref(new Map()),
    highlightFrozenRef: ref(false),
    frozenSiteRef: ref(null),
    setTooltipSiteOnFront: vi.fn(),
    setTooltipPos: vi.fn(),
    frozenTooltipPosRef: ref({ x: 0, y: 0 }),
    highlightGlowsRef: ref([]),
    measurementLabelsRef: ref([]),
    measurementMarkersRef: ref([]),
    proximityCenterRef: ref(null),
    lastMousePosRef: ref({ x: 0, y: 0 }),
    isNewsFeedOpenRef: ref(false),
    sitePositions3DRef: ref(null),
    validSitesRef: ref([]),
    lastHoverCheckRef: ref(0),
    currentHoveredSiteRef: ref(null),
    lastMoveTimeRef: ref(0),
    lastSeenSiteRef: ref(null),
    isFrozenRef: ref(false),
    frozenAtRef: ref(0),
    firstFreezeCompleteRef: ref(false),
    sitesPassedDuringFreezeRef: ref(0),
    lastSiteIdRef: ref(null),
    isHoveringTooltipRef: ref(false),
    setHoveredSite: vi.fn(),
    setIsFrozen: vi.fn(),
    setFrozenSite: vi.fn(),
    allLabelMeshesRef: ref([]),
    geoLabelsVisibleRef: ref(false),
    geoLabelsRef: ref([]),
    layerLabelsRef: ref({}),
    fadeManagerRef: ref(new FadeManager()),
    labelVisibilityStateRef: ref(new Map()),
    visibleAfterCollisionRef: ref(new Set()),
    cuddleOffsetsRef: ref(new Map()),
    cuddleAnimationsRef: ref(new Map()),
  }
  return { ctx, onWarpComplete, camera }
}

/** Longitude of a camera position, in the scene's lat/lng convention (inverse of computeWarpCameraPositions). */
function lngOf(v: THREE.Vector3): number {
  const lng = (Math.atan2(v.z, -v.x) * 180) / Math.PI - 180
  return ((lng + 540) % 360) - 180
}

describe('the intro warp', () => {
  it('does not start before the overlay fades, even with every layer ready', () => {
    const { ctx, camera } = makeCtx(null)
    ctx.layersReadyCalledRef.current = true
    const before = camera.position.clone()
    runAnimationLoop(ctx)
    for (let i = 0; i < 30; i++) frame()
    expect(ctx.warpStartTimeRef.current).toBeNull()
    expect(ctx.warpProgressRef.current).toBe(0)
    expect(ctx.globe.scale.x).toBe(1) // untouched: the warp never ran
    expect(camera.position.y).toBeCloseTo(before.y, 12)
  })

  it('does not start on the fade alone while this globe has no layers yet (remount after the gate)', () => {
    const { ctx } = makeCtx(null)
    ctx.splashDoneRef.current = true
    runAnimationLoop(ctx)
    for (let i = 0; i < 30; i++) frame()
    expect(ctx.warpStartTimeRef.current).toBeNull()
  })

  it('honours a target replaced before the first warp frame, and completes exactly once', () => {
    const { ctx, onWarpComplete, camera } = makeCtx(null)
    ctx.layersReadyCalledRef.current = true
    runAnimationLoop(ctx)
    frame()
    // A geolocation arrives before the fade: Globe moves the camera and both refs
    const moved = computeWarpCameraPositions([139.7, 35.7])
    camera.position.copy(moved.start)
    ctx.warpInitialCameraPosRef.current = moved.start.clone()
    ctx.warpTargetCameraPosRef.current = moved.target
    ctx.splashDoneRef.current = true
    frame()
    expect(ctx.warpStartTimeRef.current).not.toBeNull()

    let frames = 1
    while (ctx.warpProgressRef.current < 1 && frames < 400) {
      frame()
      frames++
    }
    // 0.0055 per frame: 182 frames
    expect(frames).toBe(182)
    expect(onWarpComplete).toHaveBeenCalledOnce()
    // Lands at the replaced target's latitude and (within the slow auto-rotation) longitude
    expect(camera.position.y).toBeCloseTo(moved.target.y, 6)
    expect(camera.position.length()).toBeCloseTo(2.44, 6)
    expect(Math.abs(lngOf(camera.position) - 139.7)).toBeLessThan(2)

    for (let i = 0; i < 50; i++) frame()
    expect(onWarpComplete).toHaveBeenCalledOnce()
  })
})
