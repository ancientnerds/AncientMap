/**
 * useGlobeAnimation - Animation loop management for Three.js globe
 * Manages frame-rate independent animations, warp effects, and render loop
 */

import { useRef, useCallback, useEffect } from 'react'
import * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CAMERA, GEO } from '../../config/globeConstants'

interface AnimationRefs {
  renderer: THREE.WebGLRenderer | null
  scene: THREE.Scene | null
  camera: THREE.PerspectiveCamera | null
  controls: OrbitControls | null
  globe: THREE.Mesh | null
  starsGroup: THREE.Group | null
}

interface WarpState {
  startTime: number | null
  progress: number
  linearProgress: number
  initialCameraPos: THREE.Vector3 | null
  targetCameraPos: THREE.Vector3 | null
  complete: boolean
  dotsComplete: boolean
}

interface AnimationCallbacks {
  // Core frame callback
  onFrame?: (deltaTime: number, fps: number, time: number) => void

  // Zoom and scale
  onZoomChange?: (zoomPercent: number, scaledZoom: number, cameraDist: number) => void
  onScaleBarUpdate?: (kmPerPixel: number) => void

  // Warp animation
  onWarpProgress?: (progress: number, linearProgress: number, scale: number) => void
  onWarpComplete?: () => void

  // Shader and visual updates
  updateShaderMaterials?: (cameraDist: number, sunDirection: THREE.Vector3, hideBackside: number, time: number, zoomPercent: number) => void
  updateLabels?: (cameraDir: THREE.Vector3, kmPerPixel: number, hideBackside: number) => void
  updateMapboxSync?: (zoomPercent: number, cameraDist: number) => void

  // Empire and measurement labels (backside hiding)
  updateEmpireLabelsVisibility?: (cameraDir: THREE.Vector3) => void
  updateMeasurementLabelsVisibility?: (cameraDir: THREE.Vector3, hideBackside: number) => void

  // Tooltip and highlight positions
  updateListHighlightedPositions?: (camera: THREE.PerspectiveCamera) => void
  updateFrozenTooltipPosition?: (camera: THREE.PerspectiveCamera) => void

  // Constant screen size elements
  updateRingMarkers?: (kmPerPixel: number, time: number) => void
  updateMeasurementLabelScales?: (kmPerPixel: number) => void
  updateProximityCrosshair?: (kmPerPixel: number) => void

  // Low FPS tracking
  onFpsUpdate?: (fps: number, isLowFps: boolean) => void

  // Hover detection (throttled)
  checkHover?: (time: number) => void
}

interface UseGlobeAnimationOptions {
  refs: React.MutableRefObject<AnimationRefs>
  callbacks?: AnimationCallbacks
  minDist?: number
  maxDist?: number
  rotationSpeed?: number
  isPageVisibleRef?: React.MutableRefObject<boolean>
  webglContextLostRef?: React.MutableRefObject<boolean>
  isAutoRotatingRef?: React.MutableRefObject<boolean>
  manualRotationRef?: React.MutableRefObject<boolean>
  isHoveringListRef?: React.MutableRefObject<boolean>
  showMapboxRef?: React.MutableRefObject<boolean>
  satelliteModeRef?: React.MutableRefObject<boolean>
}

export function useGlobeAnimation(options: UseGlobeAnimationOptions) {
  const {
    refs,
    callbacks = {},
    minDist = CAMERA.MIN_DISTANCE,
    maxDist = CAMERA.MAX_DISTANCE,
    rotationSpeed = 0.08,
    isPageVisibleRef,
    webglContextLostRef,
    isAutoRotatingRef,
    manualRotationRef,
    isHoveringListRef,
    showMapboxRef,
    satelliteModeRef: _satelliteModeRef  // Reserved for satellite mode handling
  } = options

  // Animation frame tracking
  const animationIdRef = useRef<number | null>(null)
  const lastFrameTimeRef = useRef(performance.now())
  const fpsRef = useRef(0)
  const framesRef = useRef(0)
  const fpsLastTimeRef = useRef(performance.now())

  // Low FPS tracking (below 15 for 7+ seconds)
  const lowFpsStartTimeRef = useRef<number | null>(null)
  const isLowFpsRef = useRef(false)

  // Warp animation state
  const warpStateRef = useRef<WarpState>({
    startTime: null,
    progress: 0,
    linearProgress: 0,
    initialCameraPos: null,
    targetCameraPos: null,
    complete: false,
    dotsComplete: false
  })

  // Background loading state
  const backgroundLoadingCompleteRef = useRef(false)
  const layersReadyRef = useRef(false)

  // Cached vectors (avoid per-frame allocations)
  const sunDirectionRef = useRef(new THREE.Vector3())
  const cameraDirRef = useRef(new THREE.Vector3())

  // km per pixel for scale calculations
  const kmPerPixelRef = useRef(1)

  // Calculate sun position based on current UTC time
  const calculateSunDirection = useCallback(() => {
    const now = new Date()
    const utcHours = now.getUTCHours() + now.getUTCMinutes() / 60 + now.getUTCSeconds() / 3600

    // Subsolar longitude: sun is at 0° at 12:00 UTC, moves 15° westward per hour
    const sunLongitude = (12 - utcHours) * 15

    // Subsolar latitude (solar declination): varies ±23.44° through the year
    const dayOfYear = Math.floor((now.getTime() - Date.UTC(now.getUTCFullYear(), 0, 0)) / 86400000)
    const sunLatitude = 23.44 * Math.sin((2 * Math.PI / 365) * (dayOfYear - 81))

    // Convert lat/lng to 3D direction
    const sunPhi = (90 - sunLatitude) * Math.PI / 180
    const sunTheta = (sunLongitude + 180) * Math.PI / 180

    sunDirectionRef.current.set(
      -Math.sin(sunPhi) * Math.cos(sunTheta),
      Math.cos(sunPhi),
      Math.sin(sunPhi) * Math.sin(sunTheta)
    ).normalize()

    return sunDirectionRef.current
  }, [])

  // Calculate scale bar km per pixel
  const calculateKmPerPixel = useCallback((camera: THREE.PerspectiveCamera) => {
    // Cached vectors for scale calculation
    const centerPoint = new THREE.Vector3()
    const right = new THREE.Vector3()
    const up = new THREE.Vector3(0, 1, 0)
    const p1 = new THREE.Vector3()
    const p2 = new THREE.Vector3()
    const p1Screen = new THREE.Vector3()
    const p2Screen = new THREE.Vector3()

    // Get the point on globe closest to camera
    centerPoint.copy(camera.position).normalize()

    // Create a perpendicular vector for measuring horizontal distance
    right.crossVectors(centerPoint, up).normalize()

    // Two points 500km apart on the globe surface
    const testKm = 500
    const angleRad = testKm / GEO.EARTH_RADIUS_KM

    p1.copy(centerPoint)
    p2.copy(centerPoint).multiplyScalar(Math.cos(angleRad))
    p2.addScaledVector(right, Math.sin(angleRad))

    // Project both points to screen
    p1Screen.copy(p1).project(camera)
    p2Screen.copy(p2).project(camera)

    const px1 = (p1Screen.x + 1) / 2 * window.innerWidth
    const px2 = (p2Screen.x + 1) / 2 * window.innerWidth
    const py1 = (-p1Screen.y + 1) / 2 * window.innerHeight
    const py2 = (-p2Screen.y + 1) / 2 * window.innerHeight

    const pixelsFor500km = Math.sqrt((px2 - px1) ** 2 + (py2 - py1) ** 2)
    return testKm / pixelsFor500km
  }, [])

  // Main animation loop
  const animate = useCallback(() => {
    const { renderer, scene, camera, controls, globe, starsGroup } = refs.current
    if (!renderer || !scene || !camera || !controls) {
      animationIdRef.current = requestAnimationFrame(animate)
      return
    }

    // Skip rendering when tab is hidden or WebGL context is lost
    if (isPageVisibleRef?.current === false || webglContextLostRef?.current === true) {
      animationIdRef.current = requestAnimationFrame(animate)
      return
    }

    const now = performance.now()
    const deltaTime = (now - lastFrameTimeRef.current) / 1000
    lastFrameTimeRef.current = now

    // FPS counter (every 500ms)
    framesRef.current++
    if (now - fpsLastTimeRef.current >= 500) {
      const currentFps = Math.round(framesRef.current * 1000 / (now - fpsLastTimeRef.current))
      fpsRef.current = currentFps

      // Track low FPS state (below 15 for 7+ seconds)
      if (currentFps < 15) {
        if (lowFpsStartTimeRef.current === null) {
          lowFpsStartTimeRef.current = now
        } else if (now - lowFpsStartTimeRef.current >= 7000) {
          isLowFpsRef.current = true
        }
      } else {
        lowFpsStartTimeRef.current = null
        isLowFpsRef.current = false
      }

      callbacks.onFpsUpdate?.(currentFps, isLowFpsRef.current)
      framesRef.current = 0
      fpsLastTimeRef.current = now
    }

    const warpState = warpStateRef.current

    // Warp-in effect
    if (warpState.progress < 1 && layersReadyRef.current) {
      if (warpState.startTime === null) {
        warpState.startTime = now
      }

      // Frame-based warp: ~3 seconds at 60fps
      const PROGRESS_PER_FRAME = 0.0055
      const newProgress = Math.min(warpState.progress + PROGRESS_PER_FRAME, 1.0)
      warpState.progress = newProgress
      warpState.linearProgress = newProgress

      let scale: number
      let rotationProgress: number

      if (newProgress >= 0.999) {
        warpState.progress = 1
        warpState.linearProgress = 1
        scale = 1
        rotationProgress = 1
      } else {
        // Cubic ease-in-out
        const t = newProgress
        const eased = t < 0.5
          ? 4 * t * t * t
          : 1 - Math.pow(-2 * t + 2, 3) / 2
        scale = 0.3 + 0.7 * eased
        rotationProgress = eased
      }

      // Apply scale to globe
      if (globe) {
        globe.scale.setScalar(scale)
      }

      callbacks.onWarpProgress?.(newProgress, warpState.linearProgress, scale)

      // Rotate camera from opposite side to target position
      if (warpState.initialCameraPos && warpState.targetCameraPos) {
        const startPos = warpState.initialCameraPos
        const endPos = warpState.targetCameraPos
        const dist = startPos.length()

        const startAngle = Math.atan2(startPos.z, startPos.x)
        const endAngle = Math.atan2(endPos.z, endPos.x)
        let angleDiff = endAngle - startAngle
        if (angleDiff < 0) angleDiff += 2 * Math.PI

        const warpAngle = startAngle + angleDiff * rotationProgress
        const y = startPos.y + (endPos.y - startPos.y) * rotationProgress
        const horizDist = Math.sqrt(dist * dist - y * y)

        const prevAngle = Math.atan2(camera.position.z, camera.position.x)
        let angleChange = warpAngle - prevAngle
        if (angleChange < 0) angleChange += 2 * Math.PI
        if (angleChange > Math.PI) angleChange -= 2 * Math.PI

        const minAngleChange = rotationSpeed * deltaTime
        const finalAngleChange = Math.max(angleChange, minAngleChange)
        const finalAngle = prevAngle + finalAngleChange

        camera.position.x = Math.cos(finalAngle) * horizDist
        camera.position.z = Math.sin(finalAngle) * horizDist
        camera.position.y = y
      }
    }

    // Warp complete
    if (warpState.progress >= 1 && !warpState.complete) {
      warpState.complete = true
      callbacks.onWarpComplete?.()
    }

    // Auto-rotation (frame-rate independent)
    const dist = camera.position.length()
    const zoomPercent = ((maxDist - dist) / (maxDist - minDist)) * 100
    const isZoomedIn = zoomPercent >= 34
    const warpComplete = warpState.progress >= 1
    const canRotate = warpComplete || backgroundLoadingCompleteRef.current
    const shouldAutoStop = !canRotate ||
      ((isHoveringListRef?.current || isZoomedIn) && !manualRotationRef?.current)

    if (isAutoRotatingRef?.current && !shouldAutoStop) {
      const zoomFactor = (dist - minDist) / (maxDist - minDist)
      const adjustedSpeed = rotationSpeed * (0.1 + zoomFactor * 0.9)

      const angle = adjustedSpeed * deltaTime
      const cosAngle = Math.cos(angle)
      const sinAngle = Math.sin(angle)
      const x = camera.position.x
      const z = camera.position.z
      camera.position.x = x * cosAngle - z * sinAngle
      camera.position.z = x * sinAngle + z * cosAngle
    }

    // Stars drift
    if (starsGroup) {
      starsGroup.rotation.y = now * 0.000001
    }

    // Calculate sun direction
    const sunDirection = calculateSunDirection()

    // Camera updates
    const cameraDist = camera.position.length()
    cameraDirRef.current.copy(camera.position).normalize()

    // Calculate backside fade
    const hideBackside = zoomPercent <= 60 ? 0.0 : zoomPercent >= 70 ? 1.0 : (zoomPercent - 60) / 10

    // Update shader materials
    callbacks.updateShaderMaterials?.(cameraDist, sunDirection, hideBackside, now / 1000, zoomPercent)

    // Telephoto effect: reduce FOV when zoomed in
    const zoomT = (maxDist - cameraDist) / (maxDist - minDist)
    const targetFov = 60 - (zoomT * 58.5)
    if (Math.abs(camera.fov - targetFov) > 0.1) {
      camera.fov = targetFov
      camera.updateProjectionMatrix()
    }

    // Update zoom
    const scaledZoom = ((maxDist - cameraDist) / (maxDist - minDist)) * 100
    const normalizedZoom = Math.max(0, Math.min(66, (scaledZoom / 80) * 66))
    callbacks.onZoomChange?.(Math.round(normalizedZoom), scaledZoom, cameraDist)

    // Update scale bar (Three.js mode only)
    if (!showMapboxRef?.current) {
      kmPerPixelRef.current = calculateKmPerPixel(camera)
      callbacks.onScaleBarUpdate?.(kmPerPixelRef.current)
    }

    // Mapbox sync
    callbacks.updateMapboxSync?.(normalizedZoom, cameraDist)

    // Empire label visibility (backside hiding)
    callbacks.updateEmpireLabelsVisibility?.(cameraDirRef.current)

    // Measurement label visibility (backside hiding)
    callbacks.updateMeasurementLabelsVisibility?.(cameraDirRef.current, hideBackside)

    controls.update()

    // Render
    renderer.render(scene, camera)

    // Update labels (after render, for visibility transitions)
    callbacks.updateLabels?.(cameraDirRef.current, kmPerPixelRef.current, hideBackside)

    // Update list-highlighted tooltip positions
    callbacks.updateListHighlightedPositions?.(camera)

    // Update frozen tooltip position
    callbacks.updateFrozenTooltipPosition?.(camera)

    // Update ring markers (pulse animation, constant screen size)
    callbacks.updateRingMarkers?.(kmPerPixelRef.current, now)

    // Update measurement label scales (constant screen size)
    callbacks.updateMeasurementLabelScales?.(kmPerPixelRef.current)

    // Update proximity crosshair (constant screen size)
    callbacks.updateProximityCrosshair?.(kmPerPixelRef.current)

    // Hover detection (throttled check)
    callbacks.checkHover?.(now)

    // Frame callback
    callbacks.onFrame?.(deltaTime, fpsRef.current, now)

    animationIdRef.current = requestAnimationFrame(animate)
  }, [
    refs,
    callbacks,
    minDist,
    maxDist,
    rotationSpeed,
    isPageVisibleRef,
    webglContextLostRef,
    isAutoRotatingRef,
    manualRotationRef,
    isHoveringListRef,
    showMapboxRef,
    calculateSunDirection,
    calculateKmPerPixel
  ])

  // Start animation
  const start = useCallback(() => {
    if (animationIdRef.current === null) {
      lastFrameTimeRef.current = performance.now()
      animationIdRef.current = requestAnimationFrame(animate)
    }
  }, [animate])

  // Stop animation
  const stop = useCallback(() => {
    if (animationIdRef.current !== null) {
      cancelAnimationFrame(animationIdRef.current)
      animationIdRef.current = null
    }
  }, [])

  // Initialize warp animation
  const initWarp = useCallback((initialPos: THREE.Vector3, targetPos: THREE.Vector3) => {
    warpStateRef.current = {
      startTime: null,
      progress: 0,
      linearProgress: 0,
      initialCameraPos: initialPos.clone(),
      targetCameraPos: targetPos.clone(),
      complete: false,
      dotsComplete: false
    }
  }, [])

  // Mark layers as ready (triggers warp start)
  const setLayersReady = useCallback(() => {
    layersReadyRef.current = true
  }, [])

  // Mark background loading complete
  const setBackgroundLoadingComplete = useCallback(() => {
    backgroundLoadingCompleteRef.current = true
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop()
    }
  }, [stop])

  return {
    // Control methods
    start,
    stop,
    initWarp,
    setLayersReady,
    setBackgroundLoadingComplete,

    // State refs
    fpsRef,
    kmPerPixelRef,
    warpStateRef,
    animationIdRef,
    lowFpsStartTimeRef,
    isLowFpsRef,
    cameraDirRef,

    // Flags
    isAnimating: animationIdRef.current !== null
  }
}
