/**
 * Animation Loop - Frame-by-frame rendering, updates, and hover detection
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { SiteData } from '../../../data/sites'
import { MapboxGlobeService, type MapboxTileType } from '../../../services/MapboxGlobeService'
import { FadeManager } from '../../../utils/FadeManager'
import {
  fadeLabelIn,
  fadeLabelOut,
  updateGlobeLabelScale,
  animateCuddleOffset,
  type GlobeLabelMesh,
} from '../../../utils/LabelRenderer'
import { GEO } from '../../../config/globeConstants'

const EARTH_RADIUS_KM = GEO.EARTH_RADIUS_KM

interface GeoLabel {
  name: string
  lat: number
  lng: number
  type: 'continent' | 'country' | 'capital' | 'ocean' | 'sea' | 'region' | 'mountain' | 'desert' | 'lake' | 'river' | 'metropol' | 'city' | 'plate' | 'glacier' | 'coralReef'
  rank: number
  hidden?: boolean
  layerBased?: boolean
  country?: string
  national?: boolean
  detailLevel?: number
}

interface GlobeLabel {
  label: GeoLabel
  mesh: GlobeLabelMesh
  position: THREE.Vector3
}

/** All external state/refs the animation loop reads or writes. */
export interface AnimationLoopContext {
  // --- Scene objects (created in setup, passed to animate) ---
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  globe: THREE.Mesh
  starsGroup: THREE.Group

  // --- Camera / zoom constants ---
  minDist: number
  maxDist: number
  rotationSpeed: number

  // --- Mutable frame-level state (owned by the closure in useEffect) ---
  /** Updated each frame; seconds since last frame */
  lastFrameTime: { value: number }
  /** FPS counter accumulator */
  frames: { value: number }
  fpsLastTime: { value: number }
  /** requestAnimationFrame handle */
  animationId: { value: number }

  // --- Pre-allocated Vector3 temps (avoids GC pressure) ---
  _cameraDir: THREE.Vector3
  _centerPoint: THREE.Vector3
  _right: THREE.Vector3
  _up: THREE.Vector3
  _p1: THREE.Vector3
  _p2: THREE.Vector3
  _p1Screen: THREE.Vector3
  _p2Screen: THREE.Vector3

  // --- Refs (React useRef objects or equivalent { current: T }) ---
  isPageVisibleRef: { current: boolean }
  webglContextLostRef: { current: boolean }
  fpsRef: { current: HTMLDivElement | null }
  lowFpsStartTimeRef: { current: number | null }
  setLowFps: (v: boolean) => void

  // Warp animation
  warpProgressRef: { current: number }
  warpLinearProgressRef: { current: number }
  warpStartTimeRef: { current: number | null }
  warpCompleteForLabelsRef: { current: boolean }
  warpInitialCameraPosRef: { current: THREE.Vector3 | null }
  warpTargetCameraPosRef: { current: THREE.Vector3 | null }
  layersReadyCalledRef: { current: boolean }
  dotsAnimationCompleteRef: { current: boolean }
  logoAnimationStartedRef: { current: boolean }

  // Logo
  logoSpriteRef: { current: THREE.Sprite | null }
  logoMaterialRef: { current: THREE.SpriteMaterial | null }

  // Basemap meshes (warp scale + visibility)
  basemapMeshRef: { current: THREE.Mesh | null }
  basemapBackMeshRef: { current: THREE.Mesh | null }
  basemapSectionMeshes: { current: THREE.Mesh[] }

  // Shader materials registry
  shaderMaterialsRef: { current: THREE.ShaderMaterial[] }

  // Selected dot material
  selectedDotMaterialRef: { current: THREE.ShaderMaterial | null }

  // Dot size
  dotSizeRef: { current: number }

  // Rotation
  isAutoRotatingRef: { current: boolean }
  isHoveringListRef: { current: boolean }
  manualRotationRef: { current: boolean }
  backgroundLoadingCompleteRef: { current: boolean }

  // Mapbox
  showMapboxRef: { current: boolean }
  mapboxServiceRef: { current: MapboxGlobeService | null }
  mapboxTransitioningRef: { current: boolean }
  satelliteModeRef: { current: boolean }

  // Zoom sync
  isManualZoom: { current: boolean }
  setZoom: (v: number) => void

  // Splash / loading
  splashDoneRef: { current: boolean | undefined }

  // Stars
  starsRef: { current: THREE.Group | null }

  // Empire / measurement label visibility callbacks
  updateEmpireLabelsVisibilityRef: { current: ((cameraDir: THREE.Vector3) => void) | null }
  updateMeasurementLabelsVisibilityRef: { current: ((cameraDir: THREE.Vector3, hideBackside?: number) => void) | null }

  // Scale bar
  lastScaleUpdateRef: { current: number }
  kmPerPixelRef: { current: number }
  setScaleBar: (v: { km: number; pixels: number }) => void

  // Highlight / tooltip tracking
  listHighlightedSitesRef: { current: SiteData[] }
  showTooltipsRef: { current: boolean }
  setListHighlightedPositions: (v: Map<string, { x: number; y: number }>) => void
  listHighlightedPositionsRef: { current: Map<string, { x: number; y: number }> }
  highlightFrozenRef: { current: boolean }
  frozenSiteRef: { current: SiteData | null }
  setTooltipSiteOnFront: (v: boolean) => void
  setTooltipPos: (v: { x: number; y: number }) => void
  frozenTooltipPosRef: { current: { x: number; y: number } }

  // Selection ring pulse
  highlightGlowsRef: { current: THREE.Sprite[] }

  // Measurement labels / markers / rings
  measurementLabelsRef: { current: Array<{ label: THREE.Sprite; midpoint: THREE.Vector3; targetWidth: number; targetHeight: number }> }
  measurementMarkersRef: { current: Array<{ marker: THREE.Object3D; position: THREE.Vector3 }> }

  // Proximity crosshair
  proximityCenterRef: { current: (THREE.Sprite & { targetPixels?: number }) | null }

  // Hover / freeze state
  lastMousePosRef: { current: { x: number; y: number } }
  sitePositions3DRef: { current: Float32Array | null }
  validSitesRef: { current: SiteData[] }
  lastHoverCheckRef: { current: number }
  currentHoveredSiteRef: { current: SiteData | null }
  lastMoveTimeRef: { current: number }
  lastSeenSiteRef: { current: SiteData | null }
  isFrozenRef: { current: boolean }
  frozenAtRef: { current: number }
  firstFreezeCompleteRef: { current: boolean }
  sitesPassedDuringFreezeRef: { current: number }
  lastSiteIdRef: { current: string | null }
  isHoveringTooltipRef: { current: boolean }
  setHoveredSite: (v: SiteData | null) => void
  setIsFrozen: (v: boolean) => void
  setFrozenSite: (v: SiteData | null) => void

  // Geo labels
  allLabelMeshesRef: { current: GlobeLabelMesh[] }
  geoLabelsVisibleRef: { current: boolean }
  geoLabelsRef: { current: GlobeLabel[] }
  layerLabelsRef: { current: Record<string, GlobeLabel[]> }
  fadeManagerRef: { current: FadeManager }
  labelVisibilityStateRef: { current: Map<string, boolean> }
  visibleAfterCollisionRef: { current: Set<string> }

  // Cuddle offsets (country label push-away system)
  cuddleOffsetsRef: { current: Map<string, THREE.Vector3> }
  cuddleAnimationsRef: { current: Map<string, number> }
}

/**
 * The animation loop. Call this once; it calls requestAnimationFrame on itself.
 */
export function runAnimationLoop(ctx: AnimationLoopContext): void {
  const {
    renderer, scene, camera, controls, globe, starsGroup,
    minDist, maxDist, rotationSpeed,
    lastFrameTime, frames, fpsLastTime, animationId,
    _cameraDir, _centerPoint, _right, _up, _p1, _p2, _p1Screen, _p2Screen,
  } = ctx

  const animate = () => {
    animationId.value = requestAnimationFrame(animate)

    // Skip rendering when tab is hidden or WebGL context is lost
    // This prevents wasted GPU cycles and state corruption
    if (!ctx.isPageVisibleRef.current || ctx.webglContextLostRef.current) {
      return
    }

    const now = performance.now()
    const deltaTime = (now - lastFrameTime.value) / 1000 // Convert to seconds
    lastFrameTime.value = now

    // FPS counter
    frames.value++
    if (now - fpsLastTime.value >= 500) {
      const currentFps = Math.round(frames.value * 1000 / (now - fpsLastTime.value))
      if (ctx.fpsRef.current) {
        ctx.fpsRef.current.textContent = currentFps + ' FPS'
      }
      // Track low FPS state (below 15 for 7+ seconds)
      if (currentFps < 15) {
        if (ctx.lowFpsStartTimeRef.current === null) {
          ctx.lowFpsStartTimeRef.current = now
        } else if (now - ctx.lowFpsStartTimeRef.current >= 7000) {
          ctx.setLowFps(true)
        }
      } else {
        ctx.lowFpsStartTimeRef.current = null
        ctx.setLowFps(false)
      }
      frames.value = 0
      fpsLastTime.value = now
    }

    // Warp-in effect - scale globe from small to full size
    // Also rotates from opposite side to create a "spin in" reveal
    // Starts when ALL assets are loaded (layersReadyCalledRef) - this avoids delay from React prop propagation
    // The loading overlay hides the globe during this, so warp can start immediately
    if (ctx.warpProgressRef.current < 1 && ctx.layersReadyCalledRef.current) {
      if (ctx.warpStartTimeRef.current === null) {
        ctx.warpStartTimeRef.current = now
        console.log('[Warp] Starting smooth warp animation (assets ready)')
      }

      // FRAME-BASED WARP: ~3 seconds at 60fps (180 frames)
      const PROGRESS_PER_FRAME = 0.0055
      const prevProgress = ctx.warpProgressRef.current
      const newProgress = Math.min(prevProgress + PROGRESS_PER_FRAME, 1.0)

      // Debug logging every 10%
      const prevPercent = Math.floor(prevProgress * 10)
      const newPercent = Math.floor(newProgress * 10)
      if (newPercent > prevPercent) {
        const elapsed = now - ctx.warpStartTimeRef.current
        console.log(`[Warp] ${newPercent * 10}% | elapsed=${(elapsed/1000).toFixed(1)}s scale=${(0.3 + 0.7 * newProgress).toFixed(2)}`)
      }

      ctx.warpProgressRef.current = newProgress
      ctx.warpLinearProgressRef.current = newProgress  // Track for dots timing

      let scale: number
      let rotationProgress: number
      if (newProgress >= 0.999) {
        // Warp complete - snap to exactly 1.0
        ctx.warpProgressRef.current = 1
        ctx.warpLinearProgressRef.current = 1
        scale = 1
        rotationProgress = 1
      } else {
        // Apply cubic ease-in-out for smoother warp start
        // This has a gentler ease-in than smoothstep, making the initial growth feel more natural
        const t = newProgress
        const eased = t < 0.5
          ? 4 * t * t * t  // Cubic ease-in (slow start)
          : 1 - Math.pow(-2 * t + 2, 3) / 2  // Cubic ease-out (smooth finish)
        // Scale from 0.3 to 1.0
        scale = 0.3 + 0.7 * eased
        rotationProgress = eased
      }
      // Apply scale to globe and ALL basemap meshes (including sections)
      globe.scale.setScalar(scale)
      if (ctx.basemapMeshRef.current) ctx.basemapMeshRef.current.scale.setScalar(scale)
      if (ctx.basemapBackMeshRef.current) ctx.basemapBackMeshRef.current.scale.setScalar(scale)
      for (const sectionMesh of ctx.basemapSectionMeshes.current) {
        sectionMesh.scale.setScalar(scale)
      }
      // Update star shader with current globe scale (fixes black ring during warp)
      const starPoints = starsGroup?.children[0] as THREE.Points | undefined
      if (starPoints) {
        const starMat = starPoints.material as THREE.ShaderMaterial
        if (starMat.uniforms.uGlobeScale) {
          starMat.uniforms.uGlobeScale.value = scale
        }
      }

      // Transition logo: scale with globe AND fade from red/visible to transparent
      if (ctx.logoSpriteRef.current) {
        // Debug: log first time logo animation runs
        if (!ctx.logoAnimationStartedRef.current) {
          ctx.logoAnimationStartedRef.current = true
          console.log(`[Logo] Animation started at warp progress: ${newProgress.toFixed(2)}`)
        }
        // Scale logo with globe (base size: height=1.2, width=1.488)
        const logoHeight = 1.2 * scale
        const logoWidth = logoHeight * (620 / 500)
        ctx.logoSpriteRef.current.scale.set(logoWidth, logoHeight, 1)
      }
      if (ctx.logoMaterialRef.current) {
        // Exponential fade: stays visible longer at start, fades faster at end
        // Using cubic falloff: 0.7 * (1 - progress)^3
        // Starts at 70% opacity (30% transparency), fades to 2% watermark
        // At 0%: 0.7, at 50%: 0.087, at 75%: 0.011, at 100%: 0.02 (min)
        const exponentialFade = 0.7 * Math.pow(1 - newProgress, 3)
        // Minimum 2% opacity for subtle watermark
        const logoOpacity = Math.max(exponentialFade, 0.02)
        ctx.logoMaterialRef.current.opacity = logoOpacity

        // Color transition: RED -> TEAL-GREEN with pop effect in first 20% of animation
        const colorProgress = Math.min(newProgress / 0.2, 1.0)
        const popEase = colorProgress < 1 ? 1 - Math.pow(1 - colorProgress, 3) : 1 // Cubic ease-out for snappy pop
        ctx.logoMaterialRef.current.color.setRGB(
          0.75 * (1 - popEase) + 0.0 * popEase,  // Red: 0.75 -> 0
          0.13 * (1 - popEase) + 0.88 * popEase, // Green: 0.13 -> 0.88
          0.14 * (1 - popEase) + 0.64 * popEase  // Blue: 0.14 -> 0.64 (teal-green #00E0A3)
        )
      }

      // Rotate camera from opposite side to target position (counter-clockwise, same as auto-rotation)
      if (ctx.warpInitialCameraPosRef.current && ctx.warpTargetCameraPosRef.current) {
        const startPos = ctx.warpInitialCameraPosRef.current
        const endPos = ctx.warpTargetCameraPosRef.current
        const dist = startPos.length()

        // Calculate warp rotation
        const startAngle = Math.atan2(startPos.z, startPos.x)
        const endAngle = Math.atan2(endPos.z, endPos.x)
        // Force counter-clockwise rotation (positive angle change, same direction as auto-rotation)
        let angleDiff = endAngle - startAngle
        if (angleDiff < 0) angleDiff += 2 * Math.PI

        // Calculate current and target angles from warp interpolation
        const warpAngle = startAngle + angleDiff * rotationProgress
        const y = startPos.y + (endPos.y - startPos.y) * rotationProgress
        const horizDist = Math.sqrt(dist * dist - y * y)

        // Get current camera angle to calculate how much we'd move this frame
        const prevAngle = Math.atan2(camera.position.z, camera.position.x)
        let angleChange = warpAngle - prevAngle
        // Normalize to positive (counter-clockwise)
        if (angleChange < 0) angleChange += 2 * Math.PI
        if (angleChange > Math.PI) angleChange -= 2 * Math.PI  // Take shorter path if it's huge

        // SMOOTH HANDOFF: Ensure rotation speed never drops below auto-rotation speed
        // This prevents the "stop" at the end - warp completes but maintains momentum
        const minAngleChange = rotationSpeed * deltaTime
        const finalAngleChange = Math.max(angleChange, minAngleChange)
        const finalAngle = prevAngle + finalAngleChange

        camera.position.x = Math.cos(finalAngle) * horizDist
        camera.position.z = Math.sin(finalAngle) * horizDist
        camera.position.y = y
      }
    }

    // Warp complete
    if (ctx.warpProgressRef.current >= 1 && !ctx.warpCompleteForLabelsRef.current) {
      const totalTime = ctx.warpStartTimeRef.current ? now - ctx.warpStartTimeRef.current : 0
      console.log(`[Warp] 100% COMPLETE in ${totalTime.toFixed(0)}ms`)
      ctx.warpCompleteForLabelsRef.current = true
    }

    // Dots fade-in animation - starts at 1 second into warp (33% progress)
    const dotsStartLinear = 0.33
    if (ctx.warpLinearProgressRef.current >= dotsStartLinear && !ctx.dotsAnimationCompleteRef.current) {
      // Calculate dots progress based on remaining time (linear, not eased)
      // Dots go from 0 to 1 as linear progress goes from 0.4 to 1.0
      const dotsProgress = Math.min((ctx.warpLinearProgressRef.current - dotsStartLinear) / (1 - dotsStartLinear), 1)

      // Update uDotsFadeProgress on all dot materials
      for (const mat of ctx.shaderMaterialsRef.current) {
        if (mat.uniforms.uDotsFadeProgress !== undefined) {
          mat.uniforms.uDotsFadeProgress.value = dotsProgress
        }
      }

      if (dotsProgress >= 1) {
        ctx.dotsAnimationCompleteRef.current = true
      }
    }

    // Frame-rate independent auto-rotation (pause when hovering over list or zoomed in, unless manually enabled)
    // Also continue rotation after warp completes for smooth handoff (even if background still loading)
    const dist = camera.position.length()
    const zoomPercent = ((maxDist - dist) / (maxDist - minDist)) * 100
    const isZoomedIn = zoomPercent >= 34 // Stop auto-rotation when zoomed in
    // Allow rotation if: warp complete OR background loading complete
    // This ensures smooth handoff from warp animation to auto-rotation
    const warpComplete = ctx.warpProgressRef.current >= 1
    const canRotate = warpComplete || ctx.backgroundLoadingCompleteRef.current
    const shouldAutoStop = !canRotate ||
      ((ctx.isHoveringListRef.current || isZoomedIn) && !ctx.manualRotationRef.current)

    if (ctx.isAutoRotatingRef.current && !shouldAutoStop) {
      // Get current zoom level to adjust rotation speed
      const zoomFactor = (dist - minDist) / (maxDist - minDist) // 0 = zoomed in, 1 = zoomed out
      const adjustedSpeed = rotationSpeed * (0.1 + zoomFactor * 0.9) // Slower when zoomed in

      // Rotate camera around Y axis
      const angle = adjustedSpeed * deltaTime
      const cosAngle = Math.cos(angle)
      const sinAngle = Math.sin(angle)
      const x = camera.position.x
      const z = camera.position.z
      camera.position.x = x * cosAngle - z * sinAngle
      camera.position.z = x * sinAngle + z * cosAngle
    }

    // Stars are attached to camera, just add slow drift
    starsGroup.rotation.y = now * 0.000001 // Extremely slow drift

    // Calculate real-time sun position based on current UTC time
    const nowDate = new Date()
    const utcHours = nowDate.getUTCHours() + nowDate.getUTCMinutes() / 60 + nowDate.getUTCSeconds() / 3600

    // Subsolar longitude: sun is at 0 at 12:00 UTC, moves 15 westward per hour
    const sunLongitude = (12 - utcHours) * 15 // degrees

    // Subsolar latitude (solar declination): varies +/-23.44 through the year
    const dayOfYear = Math.floor((nowDate.getTime() - Date.UTC(nowDate.getUTCFullYear(), 0, 0)) / 86400000)
    const sunLatitude = 23.44 * Math.sin((2 * Math.PI / 365) * (dayOfYear - 81)) // degrees

    // Convert lat/lng to 3D direction (same formula as latLngTo3D but normalized)
    const sunPhi = (90 - sunLatitude) * Math.PI / 180
    const sunTheta = (sunLongitude + 180) * Math.PI / 180
    const sunDirection = new THREE.Vector3(
      -Math.sin(sunPhi) * Math.cos(sunTheta),
      Math.cos(sunPhi),
      Math.sin(sunPhi) * Math.sin(sunTheta)
    ).normalize()

    // Update camera position and distance for all shader materials (back-face culling)
    const cameraDist = camera.position.length()

    // Sync zoom slider when user zooms via mouse wheel (not via slider)
    // Only sync in Three.js mode (0-66%), not in Mapbox mode
    // Inverse of: scaledZoom = (zoom / 66) * 80, targetDist = maxDist - (scaledZoom/100) * range
    // So: scaledZoom = ((maxDist - cameraDist) / range) * 100, then zoom = (scaledZoom / 80) * 66
    if (!ctx.isManualZoom.current && !ctx.showMapboxRef.current) {
      const scaledZoom = ((maxDist - cameraDist) / (maxDist - minDist)) * 100
      const zoomPct = Math.max(0, Math.min(66, (scaledZoom / 80) * 66))
      ctx.setZoom(Math.round(zoomPct))
    }

    // Telephoto effect: reduce FOV when zoomed in for 40x magnification
    // At 0% zoom: FOV = 60 (normal), at 100% zoom: FOV = 1.5 (40x magnification)
    const zoomT = (maxDist - cameraDist) / (maxDist - minDist) // 0=zoomed out, 1=zoomed in
    const targetFov = 60 - (zoomT * 58.5) // 60 -> 1.5 degrees
    if (Math.abs(camera.fov - targetFov) > 0.1) {
      camera.fov = targetFov
      camera.updateProjectionMatrix()
    }

    // Smooth fade: start at 60%, fully hidden at 70%
    const hideBackside = zoomPercent <= 60 ? 0.0 : zoomPercent >= 70 ? 1.0 : (zoomPercent - 60) / 10
    ctx.shaderMaterialsRef.current.forEach(mat => {
      mat.uniforms.uCameraPos.value.copy(camera.position)
      if (mat.uniforms.uCameraDist) {
        mat.uniforms.uCameraDist.value = cameraDist
      }
      if (mat.uniforms.uHideBackside) {
        mat.uniforms.uHideBackside.value = hideBackside
      }
      // Update time for pulsing LED glow (2 second cycle like CSS led-pulse)
      if (mat.uniforms.uTime) {
        mat.uniforms.uTime.value = (now / 1000) % 2
      }
      // Update real-time sun position
      if (mat.uniforms.uSunDirection) {
        mat.uniforms.uSunDirection.value.copy(sunDirection)
      }
      // Update satellite mode for conditional sun lighting on dots
      if (mat.uniforms.uSatelliteEnabled !== undefined) {
        mat.uniforms.uSatelliteEnabled.value = ctx.satelliteModeRef.current
      }
    })

    // Update star shader camera distance for behind-globe dimming
    const starPts = starsGroup?.children[0] as THREE.Points | undefined
    if (starPts) {
      const starMat = starPts.material as THREE.ShaderMaterial
      if (starMat.uniforms?.uCameraDist) {
        starMat.uniforms.uCameraDist.value = cameraDist
      }
    }

    // Scale dot size with zoom: 1x at 0%, 2x at 66%
    const dotZoomScale = 1 + (zoomPercent / 66)
    const baseDotSize = ctx.dotSizeRef.current
    // Scale for constant visual size across resolutions:
    // - innerHeight/1080: more pixels at higher res = need more gl_PointSize pixels
    // - devicePixelRatio: renderer uses DPR, so gl_PointSize is in framebuffer pixels not CSS pixels
    const dpr = window.devicePixelRatio || 1
    const resolutionScale = (window.innerHeight / 1080) * dpr
    const scaledSize = baseDotSize * dotZoomScale * resolutionScale

    // Update all shader materials that have uSize (dots, shadows)
    ctx.shaderMaterialsRef.current.forEach(mat => {
      if (mat.uniforms?.uSize) {
        mat.uniforms.uSize.value = scaledSize
      }
    })

    // Selected dots are 2x base size, also scaled
    if (ctx.selectedDotMaterialRef.current?.uniforms?.uSize) {
      ctx.selectedDotMaterialRef.current.uniforms.uSize.value = scaledSize * 2
    }

    // Fade out AN logo between 20% and 30% zoom (only after warp animation is done)
    if (ctx.logoMaterialRef.current && ctx.splashDoneRef.current) {
      if (zoomPercent <= 20) {
        // Fully visible (subtle watermark)
        ctx.logoMaterialRef.current.opacity = 0.02
      } else if (zoomPercent >= 30) {
        // Fully hidden
        ctx.logoMaterialRef.current.opacity = 0
      } else {
        // Fade out: 20% -> 30% maps to opacity 0.02 -> 0
        const fadeProgress = (zoomPercent - 20) / 10
        ctx.logoMaterialRef.current.opacity = 0.02 * (1 - fadeProgress)
      }
    }

    // Mapbox is shown ONLY when showMapboxRef.current = true (user clicked Map button)
    const shouldShowMapbox = ctx.showMapboxRef.current && ctx.mapboxServiceRef.current?.getIsInitialized()

    if (shouldShowMapbox && !ctx.mapboxTransitioningRef.current) {
      // Hide Three.js basemap when Mapbox globe is showing (but not during transition)
      if (ctx.basemapMeshRef.current) {
        ctx.basemapMeshRef.current.visible = false
      }
      // Note: Don't hide entire globe - keep it visible for measurement/proximity overlays
      // Only the dots are hidden (handled in mode switch effect)

      // Update Mapbox style if tile type changed (dark <-> satellite)
      const tileType: MapboxTileType = ctx.satelliteModeRef.current ? 'satellite' : 'dark'
      if (ctx.mapboxServiceRef.current!.getStyle() !== tileType) {
        console.log(`[Mapbox] Switching style: ${ctx.mapboxServiceRef.current!.getStyle()} -> ${tileType}`)
        ctx.mapboxServiceRef.current!.setStyle(tileType)
      }
      // Note: visibility/opacity handled by CSS via mapbox-primary-mode class
    } else {
      // Show basemap (Mapbox fades out via CSS transition)
      // Globe is always visible (for measurement/proximity overlays)
      if (ctx.basemapMeshRef.current && !ctx.basemapMeshRef.current.visible) {
        ctx.basemapMeshRef.current.visible = true
      }
    }

    // Hide empire labels, city markers, and region labels on the backside of the globe
    // Call via ref so HMR can update the logic without recreating the animation loop
    _cameraDir.copy(camera.position).normalize()
    if (ctx.updateEmpireLabelsVisibilityRef.current) {
      ctx.updateEmpireLabelsVisibilityRef.current(_cameraDir)
    }

    // Fade measurement labels when approaching/leaving back side of globe
    // Call via ref so HMR can update the logic without recreating the animation loop
    if (ctx.updateMeasurementLabelsVisibilityRef.current) {
      ctx.updateMeasurementLabelsVisibilityRef.current(_cameraDir, hideBackside)
    }

    controls.update()

    const currentTime = Date.now()

    // Update scale bar (throttled to 50ms) - Three.js mode only
    // Mapbox mode has its own scale bar update below
    if (!ctx.showMapboxRef.current && currentTime - ctx.lastScaleUpdateRef.current > 50) {
      ctx.lastScaleUpdateRef.current = currentTime

      // Get the point on globe closest to camera (center of visible area)
      _centerPoint.copy(camera.position).normalize()

      // Create a perpendicular vector for measuring horizontal distance
      _right.crossVectors(_centerPoint, _up).normalize()

      // Two points 500km apart on the globe surface (at center)
      // 500km = 500/6371 radians on great circle
      const testKm = 500
      const angleRad = testKm / EARTH_RADIUS_KM

      _p1.copy(_centerPoint)
      _p2.copy(_centerPoint).multiplyScalar(Math.cos(angleRad))
      _p2.addScaledVector(_right, Math.sin(angleRad))

      // Project both points to screen
      _p1Screen.copy(_p1).project(camera)
      _p2Screen.copy(_p2).project(camera)

      const px1 = (_p1Screen.x + 1) / 2 * window.innerWidth
      const px2 = (_p2Screen.x + 1) / 2 * window.innerWidth
      const py1 = (-_p1Screen.y + 1) / 2 * window.innerHeight
      const py2 = (-_p2Screen.y + 1) / 2 * window.innerHeight

      const pixelsFor500km = Math.sqrt((px2 - px1) ** 2 + (py2 - py1) ** 2)
      const kmPerPixel = testKm / pixelsFor500km
      ctx.kmPerPixelRef.current = kmPerPixel // Store for ring scaling

      // Pick nice round number for scale (in km, including sub-km values)
      const niceValues = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 25, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
      const targetPixels = 100
      const targetKm = kmPerPixel * targetPixels

      let bestKm = niceValues[0]
      for (const km of niceValues) {
        if (km <= targetKm * 1.5) bestKm = km
      }

      const barPixels = bestKm / kmPerPixel
      if (barPixels > 15 && barPixels < 400 && !isNaN(barPixels)) {
        ctx.setScaleBar({ km: bestKm, pixels: Math.round(barPixels) })
      }
    }

    // Update list-highlighted tooltip positions (follows sites during rotation/flyTo)
    const listSites = ctx.listHighlightedSitesRef.current
    if (listSites.length > 0 && ctx.showTooltipsRef.current) {
      const newPositions = new Map<string, { x: number, y: number }>()
      const cameraDir = camera.position.clone().normalize()

      for (const site of listSites) {
        const [lng, lat] = site.coordinates
        const phi = (90 - lat) * Math.PI / 180
        const theta = (lng + 180) * Math.PI / 180
        const r = 1.002
        const sitePos = new THREE.Vector3(
          -r * Math.sin(phi) * Math.cos(theta),
          r * Math.cos(phi),
          r * Math.sin(phi) * Math.sin(theta)
        )

        // Check if site is on front side
        const isVisible = sitePos.clone().normalize().dot(cameraDir) > 0

        if (isVisible) {
          // Project to screen
          const projectedPos = sitePos.clone().project(camera)
          const screenX = (projectedPos.x + 1) / 2 * window.innerWidth
          const screenY = (-projectedPos.y + 1) / 2 * window.innerHeight
          newPositions.set(site.id, { x: screenX, y: screenY })
        }
      }
      ctx.setListHighlightedPositions(newPositions)
      ctx.listHighlightedPositionsRef.current = newPositions
    }

    // Update main tooltip position for highlight-frozen site (follows during rotation/flyTo)
    if (ctx.highlightFrozenRef.current && ctx.frozenSiteRef.current && ctx.showTooltipsRef.current) {
      const site = ctx.frozenSiteRef.current
      const [lng, lat] = site.coordinates
      const phi = (90 - lat) * Math.PI / 180
      const theta = (lng + 180) * Math.PI / 180
      const r = 1.002
      const sitePos = new THREE.Vector3(
        -r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi),
        r * Math.sin(phi) * Math.sin(theta)
      )

      // Check if site is on front of globe (visible side)
      const siteNormal = sitePos.clone().normalize()
      const cameraDir = camera.position.clone().normalize()
      const dotProduct = siteNormal.dot(cameraDir)
      const isOnFront = dotProduct > 0.05 // Small threshold to avoid edge flickering
      ctx.setTooltipSiteOnFront(isOnFront)

      const projectedPos = sitePos.clone().project(camera)
      const screenX = (projectedPos.x + 1) / 2 * window.innerWidth
      const screenY = (-projectedPos.y + 1) / 2 * window.innerHeight
      ctx.setTooltipPos({ x: screenX, y: screenY })
      ctx.frozenTooltipPosRef.current = { x: screenX, y: screenY }
    }

    // Pulse animation for selection ring markers (constant screen size using kmPerPixel)
    const rings = ctx.highlightGlowsRef.current
    if (rings.length > 0) {
      // Target size in pixels, converted to 3D units using kmPerPixel
      const targetPixels = 30 // Ring size in pixels on screen
      const kmSize = targetPixels * ctx.kmPerPixelRef.current
      const baseScale = kmSize / EARTH_RADIUS_KM // Convert km to 3D units (globe radius = 1)
      const pulse = baseScale * (1 + 0.25 * Math.sin(currentTime * 0.004)) // 25% pulse variation
      for (const ring of rings) {
        ring.scale.set(pulse, pulse, 1)
      }
    }

    // Update measurement labels for constant screen size (same technique as selection rings)
    const measureLabels = ctx.measurementLabelsRef.current
    if (measureLabels.length > 0 && ctx.kmPerPixelRef.current > 0) {
      for (const entry of measureLabels) {
        if (!entry || !entry.label) continue
        // Convert target pixel size to 3D units
        const kmWidth = entry.targetWidth * ctx.kmPerPixelRef.current
        const kmHeight = entry.targetHeight * ctx.kmPerPixelRef.current
        const scaleW = kmWidth / EARTH_RADIUS_KM
        const scaleH = kmHeight / EARTH_RADIUS_KM
        entry.label.scale.set(scaleW, scaleH, 1)
      }
    }

    // Update measurement ring markers for constant screen size (same technique as selection rings)
    const measureMarkers = ctx.measurementMarkersRef.current
    if (measureMarkers.length > 0 && ctx.kmPerPixelRef.current > 0) {
      for (const entry of measureMarkers) {
        if (!entry || !entry.marker) continue
        const marker = entry.marker as any
        if (marker.isRingMarker && marker.targetPixels) {
          // Convert target pixel size to 3D units
          const kmSize = marker.targetPixels * ctx.kmPerPixelRef.current
          const scale = kmSize / EARTH_RADIUS_KM
          marker.scale.set(scale, scale, 1)
        }
      }
    }

    // Update proximity crosshair for constant screen size (same technique as selection rings)
    const proximityCrosshair = ctx.proximityCenterRef.current as (THREE.Sprite & { targetPixels?: number }) | null
    if (proximityCrosshair && proximityCrosshair.targetPixels && ctx.kmPerPixelRef.current > 0) {
      const kmSize = proximityCrosshair.targetPixels * ctx.kmPerPixelRef.current
      const scale = kmSize / EARTH_RADIUS_KM
      proximityCrosshair.scale.set(scale, scale, 1)
    }

    // FIRST: Track what site is under cursor (throttled for performance)
    // Skip entirely if tooltips are disabled - major performance gain
    // Skip in Mapbox mode - Mapbox hover callback handles this via currentHoveredSiteRef
    const mouseX = ctx.lastMousePosRef.current.x
    const mouseY = ctx.lastMousePosRef.current.y
    const positions3D = ctx.sitePositions3DRef.current
    if (ctx.showTooltipsRef.current && mouseX >= 0 && positions3D && !ctx.showMapboxRef.current) { // Only if tooltips enabled and not in Mapbox mode
      // Throttle expensive hover detection to every 150ms (performance with 750k sites)
      if (currentTime - ctx.lastHoverCheckRef.current > 150) {
        ctx.lastHoverCheckRef.current = currentTime

        let nearestSite: SiteData | null = null
        let nearestScreenDist = Infinity
        const maxHoverDist = 10
        const earlyExitDist = 3 // Exit early if we find something this close
        const camX = camera.position.x
        const camY = camera.position.y
        const camZ = camera.position.z
        const camLen = Math.sqrt(camX * camX + camY * camY + camZ * camZ)
        const camNormX = camX / camLen
        const camNormY = camY / camLen
        const camNormZ = camZ / camLen
        const sites = ctx.validSitesRef.current // Use validSites (same order as positions3D)
        const windowWidth = window.innerWidth
        const windowHeight = window.innerHeight
        const numSites = sites.length

        // Performance: only check a sample of sites when there are many
        // With 750k sites, checking all is too slow. Sample every Nth site.
        const MAX_SITES_TO_CHECK = 50000
        const step = numSites > MAX_SITES_TO_CHECK ? Math.ceil(numSites / MAX_SITES_TO_CHECK) : 1

        // Reusable Vector3 for projection (avoid allocations)
        const projVec = new THREE.Vector3()

        // Use pre-computed 3D positions from sitePositions3DRef
        for (let i = 0; i < numSites; i += step) {
          const px = positions3D[i * 3]
          const py = positions3D[i * 3 + 1]
          const pz = positions3D[i * 3 + 2]

          // Front-side check: dot product with camera direction
          // Position is already normalized (on unit sphere)
          if (px * camNormX + py * camNormY + pz * camNormZ <= 0) continue

          // Project to screen coordinates
          projVec.set(px, py, pz)
          projVec.project(camera)
          const screenX = (projVec.x + 1) / 2 * windowWidth
          const screenY = (-projVec.y + 1) / 2 * windowHeight

          const dx = mouseX - screenX
          const dy = mouseY - screenY
          const screenDistSq = dx * dx + dy * dy
          const maxHoverDistSq = maxHoverDist * maxHoverDist

          if (screenDistSq < nearestScreenDist && screenDistSq < maxHoverDistSq) {
            nearestScreenDist = screenDistSq
            nearestSite = sites[i]
            // Early exit: if we found something very close, no need to keep searching
            if (screenDistSq < earlyExitDist * earlyExitDist) break
          }
        }

        ctx.currentHoveredSiteRef.current = nearestSite
      }

      // Use cached hover result for freeze logic (runs every frame)
      const foundSite = ctx.currentHoveredSiteRef.current
      const timeSinceMove = currentTime - ctx.lastMoveTimeRef.current
      const cursorStopped = timeSinceMove > 200

      // Always track the site while moving (for freeze)
      if (!cursorStopped && foundSite) {
        ctx.lastSeenSiteRef.current = foundSite
      }
      // Clear stale reference when cursor moves and no site is under it
      if (!cursorStopped && !foundSite) {
        ctx.lastSeenSiteRef.current = null
      }

      // === RULE 1: CURSOR STOPPED = FREEZE (highest priority) ===
      if (!ctx.isFrozenRef.current) {
        // NOT FROZEN: tooltip follows cursor
        ctx.setHoveredSite(foundSite)

        // FREEZE when cursor stops and we CURRENTLY have a site under cursor
        if (cursorStopped && foundSite) {
          ctx.isFrozenRef.current = true
          ctx.frozenAtRef.current = currentTime
          ctx.firstFreezeCompleteRef.current = false // New freeze, not complete yet
          ctx.setIsFrozen(true)
          ctx.setFrozenSite(foundSite)
          ctx.setTooltipPos({ x: mouseX, y: mouseY })
          ctx.frozenTooltipPosRef.current = { x: mouseX, y: mouseY } // Store for distance check
          ctx.sitesPassedDuringFreezeRef.current = 0
          ctx.lastSiteIdRef.current = foundSite.id
        }
      } else {
        // === RULE 2: Count sites AFTER first freeze completed ===
        // Skip if frozen via highlightedSiteId (minimized bar)
        // Use flag instead of duration since RULE 3 resets the timer
        if (!ctx.highlightFrozenRef.current && ctx.firstFreezeCompleteRef.current && !cursorStopped && foundSite) {
          const currentSiteId = foundSite.id
          if (currentSiteId !== ctx.lastSiteIdRef.current) {
            ctx.lastSiteIdRef.current = currentSiteId
            ctx.sitesPassedDuringFreezeRef.current++

            // >3 sites AFTER first freeze = RESET everything
            if (ctx.sitesPassedDuringFreezeRef.current > 3) {
              ctx.isFrozenRef.current = false
              ctx.firstFreezeCompleteRef.current = false
              ctx.setIsFrozen(false)
              ctx.setFrozenSite(null)
              ctx.sitesPassedDuringFreezeRef.current = 0
              ctx.lastSeenSiteRef.current = foundSite
            }
          }
        }
      }

      // === RULE 3: After 1s frozen, mark complete and update tooltip ===
      // Skip if frozen via highlightedSiteId (minimized bar)
      if (ctx.isFrozenRef.current && !ctx.highlightFrozenRef.current) {
        const frozenDuration = currentTime - ctx.frozenAtRef.current

        if (frozenDuration > 1000 && !ctx.isHoveringTooltipRef.current) {
          // Mark first freeze as complete (enables site counting in RULE 2)
          ctx.firstFreezeCompleteRef.current = true

          if (foundSite) {
            // Update to current site, start new 1s freeze period
            ctx.setTooltipPos({ x: mouseX, y: mouseY })
            ctx.frozenTooltipPosRef.current = { x: mouseX, y: mouseY } // Update for distance check
            ctx.setFrozenSite(foundSite)
            ctx.frozenAtRef.current = currentTime
            // DON'T reset sitesPassedDuringFreezeRef here - keep counting!
          } else {
            // No site under cursor - unfreeze
            ctx.isFrozenRef.current = false
            ctx.firstFreezeCompleteRef.current = false
            ctx.setIsFrozen(false)
            ctx.setFrozenSite(null)
          }
        }
      }

      // === RULE 4: Unfreeze if cursor is >50px from tooltip ===
      // Skip this check if frozen via highlightedSiteId (minimized bar click)
      if (ctx.isFrozenRef.current && !ctx.highlightFrozenRef.current) {
        const dx = mouseX - ctx.frozenTooltipPosRef.current.x
        const dy = mouseY - ctx.frozenTooltipPosRef.current.y
        const distance = Math.sqrt(dx * dx + dy * dy)

        if (distance > 50) {
          ctx.isFrozenRef.current = false
          ctx.firstFreezeCompleteRef.current = false
          ctx.setIsFrozen(false)
          ctx.setFrozenSite(null)
          ctx.sitesPassedDuringFreezeRef.current = 0
          ctx.lastSeenSiteRef.current = foundSite
        }
      }
    }

    // === MAPBOX MODE SCALE BAR ===
    // Update scale bar in Mapbox mode (throttled)
    if (ctx.showMapboxRef.current && ctx.mapboxServiceRef.current?.getIsInitialized()) {
      if (currentTime - ctx.lastScaleUpdateRef.current > 50) {
        ctx.lastScaleUpdateRef.current = currentTime
        const mapboxScale = ctx.mapboxServiceRef.current.getScaleBar()
        if (mapboxScale) {
          ctx.setScaleBar(mapboxScale)
        }
      }
    }

    // === MAPBOX MODE FREEZE LOGIC ===
    // Same freeze behavior as Three.js but uses currentHoveredSiteRef set by Mapbox hover callback
    // Skip entirely when mouseX < 0 (hovering over tooltip - keeps tooltip frozen like Three.js)
    const mapboxMouseX = ctx.lastMousePosRef.current.x
    const mapboxMouseY = ctx.lastMousePosRef.current.y
    if (ctx.showMapboxRef.current && ctx.showTooltipsRef.current && mapboxMouseX >= 0) {
      const foundSite = ctx.currentHoveredSiteRef.current
      const timeSinceMove = currentTime - ctx.lastMoveTimeRef.current
      const cursorStopped = timeSinceMove > 200

      // Track site while moving (remember last seen site for freeze)
      if (!cursorStopped && foundSite) {
        ctx.lastSeenSiteRef.current = foundSite
      }
      // DON'T aggressively clear lastSeenSite - user might be moving toward tooltip
      // Only clear when cursor has stopped AND no site (means user stopped somewhere with no site)
      if (cursorStopped && !foundSite && !ctx.isHoveringTooltipRef.current && !ctx.isFrozenRef.current) {
        ctx.lastSeenSiteRef.current = null
      }

      // Use lastSeenSite for freeze - allows user to move from dot to tooltip
      const siteForFreeze = foundSite || ctx.lastSeenSiteRef.current

      // NOT FROZEN: show tooltip following cursor when over a site
      if (!ctx.isFrozenRef.current) {
        // Show hoveredSite when over a site (callback handles this, but sync here too)
        if (foundSite) {
          ctx.setHoveredSite(foundSite)
        }

        // RULE 1: Freeze when cursor stops and we have a site (current or last seen)
        if (cursorStopped && siteForFreeze) {
          ctx.isFrozenRef.current = true
          ctx.frozenAtRef.current = currentTime
          ctx.firstFreezeCompleteRef.current = false
          ctx.setIsFrozen(true)
          ctx.setFrozenSite(siteForFreeze)
          ctx.setTooltipPos({ x: mapboxMouseX, y: mapboxMouseY })
          ctx.frozenTooltipPosRef.current = { x: mapboxMouseX, y: mapboxMouseY }
          ctx.sitesPassedDuringFreezeRef.current = 0
          ctx.lastSiteIdRef.current = siteForFreeze.id
        }
      } else {
        // RULE 2: Count sites after first freeze
        if (!ctx.highlightFrozenRef.current && ctx.firstFreezeCompleteRef.current && !cursorStopped && foundSite) {
          const currentSiteId = foundSite.id
          if (currentSiteId !== ctx.lastSiteIdRef.current) {
            ctx.lastSiteIdRef.current = currentSiteId
            ctx.sitesPassedDuringFreezeRef.current++
            if (ctx.sitesPassedDuringFreezeRef.current > 3) {
              ctx.isFrozenRef.current = false
              ctx.firstFreezeCompleteRef.current = false
              ctx.setIsFrozen(false)
              ctx.setFrozenSite(null)
              ctx.sitesPassedDuringFreezeRef.current = 0
              ctx.lastSeenSiteRef.current = foundSite
            }
          }
        }
      }

      // RULE 3: After 1s frozen, update to current site
      if (ctx.isFrozenRef.current && !ctx.highlightFrozenRef.current) {
        const frozenDuration = currentTime - ctx.frozenAtRef.current
        if (frozenDuration > 1000 && !ctx.isHoveringTooltipRef.current) {
          ctx.firstFreezeCompleteRef.current = true
          if (foundSite) {
            ctx.setTooltipPos({ x: mapboxMouseX, y: mapboxMouseY })
            ctx.frozenTooltipPosRef.current = { x: mapboxMouseX, y: mapboxMouseY }
            ctx.setFrozenSite(foundSite)
            ctx.frozenAtRef.current = currentTime
          } else {
            ctx.isFrozenRef.current = false
            ctx.firstFreezeCompleteRef.current = false
            ctx.setIsFrozen(false)
            ctx.setFrozenSite(null)
          }
        }
      }

      // RULE 4: Unfreeze if cursor moves far from frozen position
      // (isHoveringTooltip check not needed - entire block skipped when mouseX < 0)
      if (ctx.isFrozenRef.current && !cursorStopped && !ctx.highlightFrozenRef.current) {
        const frozenPos = ctx.frozenTooltipPosRef.current
        const dx = mapboxMouseX - frozenPos.x
        const dy = mapboxMouseY - frozenPos.y
        const distance = Math.sqrt(dx * dx + dy * dy)
        if (distance > 50) {
          ctx.isFrozenRef.current = false
          ctx.firstFreezeCompleteRef.current = false
          ctx.setIsFrozen(false)
          ctx.setFrozenSite(null)
          ctx.sitesPassedDuringFreezeRef.current = 0
          ctx.lastSeenSiteRef.current = foundSite
        }
      }

      // Update selected site label positions (they move as map pans/zooms)
      // IMPORTANT: Selected labels are LOCKED - only update position, never remove
      if (ctx.listHighlightedSitesRef.current.length > 0 && ctx.mapboxServiceRef.current?.getIsInitialized()) {
        const currentPositions = ctx.listHighlightedPositionsRef.current
        const newPositions = new Map<string, { x: number, y: number }>(currentPositions) // Start with existing positions
        let positionsChanged = false

        for (const site of ctx.listHighlightedSitesRef.current) {
          const [lng, lat] = site.coordinates
          const screenPos = ctx.mapboxServiceRef.current.projectToScreen(lng, lat)
          if (screenPos) {
            const oldPos = currentPositions.get(site.id)
            // Only update if position actually changed (avoid jitter)
            if (!oldPos || Math.abs(oldPos.x - screenPos.x) > 0.5 || Math.abs(oldPos.y - screenPos.y) > 0.5) {
              newPositions.set(site.id, screenPos)
              positionsChanged = true
            }
          }
          // If projectToScreen returns null, keep the old position (don't remove)
        }

        if (positionsChanged) {
          ctx.listHighlightedPositionsRef.current = newPositions
          ctx.setListHighlightedPositions(newPositions)
        }
      }
    }

    // Render scene with native hardware AA
    renderer.render(scene, camera)

    // Update label visibility - only backside hiding during rotation
    // Collision detection is done in updateGeoLabels (only on zoom change)
    // Update scale for VISIBLE globe-tangent label meshes using kmPerPixel
    // This maintains constant screen size regardless of zoom level (distance + FOV)
    // Skip invisible meshes for performance (e.g., disabled city labels)
    const currentKmPerPixel = ctx.kmPerPixelRef.current
    if (currentKmPerPixel > 0) {
      for (const mesh of ctx.allLabelMeshesRef.current) {
        if (!mesh.visible) continue
        updateGlobeLabelScale(mesh, currentKmPerPixel)
      }
    }

    if (ctx.geoLabelsVisibleRef.current) {
      // Geo and layer labels - only apply fade visibility transitions
      // Backside hiding is handled by the shader's vViewFade uniform
      // Bubble/stacking positions are calculated in updateGeoLabels (on zoom change only)
      const geoAndLayerLabels = [
        ...ctx.geoLabelsRef.current,
        ...Object.values(ctx.layerLabelsRef.current).flat()
      ]

      const fm = ctx.fadeManagerRef.current
      const visibilityState = ctx.labelVisibilityStateRef.current

      for (const item of geoAndLayerLabels) {
        const labelName = item.label.name

        // Target visibility based on collision detection
        const shouldBeVisible = ctx.visibleAfterCollisionRef.current.has(labelName)
        const isCurrentlyVisible = visibilityState.get(labelName) ?? false

        // Only trigger fade when visibility state changes
        if (shouldBeVisible !== isCurrentlyVisible) {
          visibilityState.set(labelName, shouldBeVisible)
          if (shouldBeVisible) {
            fadeLabelIn(item.mesh, fm, `geo-${labelName}`)
          } else {
            fadeLabelOut(item.mesh, fm, `geo-${labelName}`)
          }
        }
      }

      // === Apply cuddle offsets for country labels (pushed away from their capitals) ===
      const cuddleOffsets = ctx.cuddleOffsetsRef.current
      const cuddleAnims = ctx.cuddleAnimationsRef.current

      for (const item of ctx.geoLabelsRef.current) {
        // Only process country labels
        if (item.label.type !== 'country') continue

        const name = item.label.name
        const targetOffset = cuddleOffsets.get(name) ?? null
        const currentOffset = item.mesh.userData.cuddleOffset as THREE.Vector3 | undefined

        // Store original position on first encounter
        if (!item.mesh.userData.originalPosition) {
          item.mesh.userData.originalPosition = item.position.clone()
        }

        // Check if offset changed
        const offsetChanged = targetOffset
          ? !currentOffset || !currentOffset.equals(targetOffset)
          : !!currentOffset

        if (offsetChanged) {
          item.mesh.userData.cuddleOffset = targetOffset?.clone()
          animateCuddleOffset(
            item.mesh,
            `cuddle-${name}`,
            targetOffset,
            item.mesh.userData.originalPosition as THREE.Vector3,
            cuddleAnims
          )
        }
      }
    }
  }
  animate()
}
