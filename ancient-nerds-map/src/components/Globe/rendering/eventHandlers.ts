import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { SiteData } from '../../../data/sites'
import { MapboxGlobeService } from '../../../services/MapboxGlobeService'
import {
  updateEmpireHoverState,
  clearEmpireHoverState,
  getHoverCursorStyle,
  type EmpireHoverRefs
} from './empireHoverUtils'

/** Refs and state setters needed by event handlers. */
export interface EventHandlerRefs {
  containerRef: React.RefObject<HTMLDivElement | null>
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
  showMapboxRef: React.MutableRefObject<boolean>
  sitesRef: React.MutableRefObject<SiteData[]>
  lastMousePosRef: React.MutableRefObject<{ x: number; y: number }>
  lastMoveTimeRef: React.MutableRefObject<number>
  lastCoordsUpdateRef: React.MutableRefObject<number>
  currentHoveredSiteRef: React.MutableRefObject<SiteData | null>
  isFrozenRef: React.MutableRefObject<boolean>
  frozenSiteRef: React.MutableRefObject<SiteData | null>
  hoveredSiteRef: React.MutableRefObject<SiteData | null>
  highlightFrozenRef: React.MutableRefObject<boolean>
  cameraAnimationRef: React.MutableRefObject<number | null>
  onSiteSelectRef: React.MutableRefObject<((siteId: string | null, ctrlKey: boolean) => void) | undefined>
  onEmpireClickRef: React.MutableRefObject<((empireId: string, defaultYear?: number, yearOptions?: number[]) => void) | undefined>
  isContributePickerActiveRef: React.MutableRefObject<boolean>
  onContributeMapConfirmRef: React.MutableRefObject<(() => void) | undefined>
  measureModeRef: React.MutableRefObject<boolean | undefined>
  onMeasurePointAddRef: React.MutableRefObject<((coords: [number, number], snapped: boolean) => void) | undefined>
  measureSnapEnabledRef: React.MutableRefObject<boolean | undefined>
  measurementsRef: React.MutableRefObject<Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>>
  currentMeasurePointsRef: React.MutableRefObject<Array<{ coords: [number, number]; snapped: boolean }>>
  zoomRef: React.MutableRefObject<number>
  // Empire hover refs
  hoveredEmpireRef: React.MutableRefObject<string | null>
  empireBorderLinesRef: React.MutableRefObject<Record<string, THREE.Line[]>>
  empireFillMeshesRef: React.MutableRefObject<Record<string, THREE.Mesh[]>>
  empireDefaultYearsRef: React.MutableRefObject<Record<string, number>>
  empireYearOptionsRef: React.MutableRefObject<Record<string, number[]>>
}

/** State setters needed by event handlers. */
export interface EventHandlerSetters {
  setZoom: (zoom: number) => void
  setCursorCoords: (coords: { lat: number; lon: number } | null) => void
  setTooltipPos: (pos: { x: number; y: number }) => void
  setHoveredSite: (site: SiteData | null) => void
  setIsFrozen: (frozen: boolean) => void
  setFrozenSite: (site: SiteData | null) => void
}

/** External callbacks passed from the Globe component props. */
export interface EventHandlerCallbacks {
  onProximitySet?: (coords: [number, number]) => void
  isLoading?: boolean
}

/** Core scene objects needed by event handlers. */
export interface EventHandlerSceneObjects {
  renderer: THREE.WebGLRenderer
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  globe: THREE.Mesh
  minDist: number
  maxDist: number
}

/** Result of setupEventHandlers, containing all cleanup functions. */
export interface EventHandlerCleanup {
  /** Call this to remove all event listeners */
  cleanup: () => void
}

/** Creates the window resize handler. */
export function createResizeHandler(
  camera: THREE.PerspectiveCamera,
  renderer: THREE.WebGLRenderer,
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
): () => void {
  return () => {
    camera.aspect = window.innerWidth / window.innerHeight
    camera.updateProjectionMatrix()
    renderer.setSize(window.innerWidth, window.innerHeight)
    // Update Mapbox dot sizes for new resolution
    mapboxServiceRef.current?.resize()
  }
}

/** Sets up the OrbitControls change listener that syncs the zoom slider. */
export function createControlsChangeHandler(
  camera: THREE.PerspectiveCamera,
  minDist: number,
  maxDist: number,
  isManualZoom: React.MutableRefObject<boolean>,
  showMapboxRef: React.MutableRefObject<boolean>,
  controls: OrbitControls,
  setZoom: (zoom: number) => void
): () => void {
  return () => {
    if (!isManualZoom.current && !showMapboxRef.current) {
      const dist = camera.position.length()
      const scaledZoom = ((maxDist - dist) / (maxDist - minDist)) * 100
      const newZoom = Math.max(0, Math.min(66, Math.round((scaledZoom / 80) * 66)))
      setZoom(newZoom)

      // Update rotation speed based on zoom
      controls.rotateSpeed = 0.5 - (scaledZoom / 100) * 0.3
    }
  }
}

/** Creates the wheel zoom handler with cursor-following zoom. */
export function createWheelHandler(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  globe: THREE.Mesh,
  minDist: number,
  maxDist: number,
  showMapboxRef: React.MutableRefObject<boolean>,
  zoomRef: React.MutableRefObject<number>
): { handleWheel: (e: WheelEvent) => void; zoomTimeout: { current: number | null } } {
  const zoomTimeoutObj = { current: null as number | null }

  const handleWheel = (e: WheelEvent) => {
    // In Mapbox mode at/above transition point, let Mapbox handle zoom
    if (showMapboxRef.current && zoomRef.current >= 66) return

    e.preventDefault()

    const zoomSpeed = 0.03
    const delta = e.deltaY > 0 ? 1 : -1

    // Reset zoom session after 500ms of no scrolling
    if (zoomTimeoutObj.current) clearTimeout(zoomTimeoutObj.current)
    zoomTimeoutObj.current = window.setTimeout(() => {}, 500)

    const currentDist = camera.position.length()

    const scaleFactor = 1 + delta * zoomSpeed
    const newDist = Math.max(minDist, Math.min(maxDist, currentDist * scaleFactor))

    if (newDist === currentDist) return

    // Get cursor position on globe
    const mouseX = (e.clientX / window.innerWidth) * 2 - 1
    const mouseY = -(e.clientY / window.innerHeight) * 2 + 1

    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), camera)
    const intersects = raycaster.intersectObject(globe, false)

    if (intersects.length > 0) {
      const cursorDir = intersects[0].point.clone().normalize()
      const cameraDir = camera.position.clone().normalize()

      // Calculate blend factor based on zoom direction and level
      // Zoom in: move toward cursor. Zoom out: stay on current direction
      const zoomingIn = delta < 0
      const zoomLevel = 1 - (currentDist - minDist) / (maxDist - minDist) // 0 = far, 1 = close

      if (zoomingIn) {
        // Blend camera direction toward cursor direction
        // More aggressive blend when zoomed out, gentler when zoomed in
        const blendFactor = 0.15 * (1 - zoomLevel * 0.5)
        const newDir = cameraDir.lerp(cursorDir, blendFactor).normalize()
        camera.position.copy(newDir.multiplyScalar(newDist))
      } else {
        // Zooming out - just change distance, keep direction
        camera.position.copy(cameraDir.multiplyScalar(newDist))
      }

      controls.target.set(0, 0, 0)
      camera.lookAt(0, 0, 0)
    } else {
      // Cursor not on globe - just zoom without panning
      const direction = camera.position.clone().normalize()
      camera.position.copy(direction.multiplyScalar(newDist))
    }

    controls.update()
  }

  return { handleWheel, zoomTimeout: zoomTimeoutObj }
}

/** Creates the browser zoom prevention handler (Ctrl+scroll). */
export function createPreventBrowserZoomHandler(
  showMapboxRef: React.MutableRefObject<boolean>
): (e: WheelEvent) => void {
  return (e: WheelEvent) => {
    // In Mapbox primary mode, don't interfere with any wheel events
    if (showMapboxRef.current) return
    if (e.ctrlKey) {
      e.preventDefault()
    }
  }
}

/** Creates the arcball point calculation function using ray-sphere intersection. */
export function createArcballSystem(camera: THREE.PerspectiveCamera): {
  getArcballPoint: (clientX: number, clientY: number) => THREE.Vector3 | null
} {
  // Reusable objects for raycasting (created once, not per frame)
  const arcballRaycaster = new THREE.Raycaster()
  const arcballMouse = new THREE.Vector2()
  const arcballSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1)

  // Get point on unit sphere from screen coords using ray-sphere intersection
  // Returns null when cursor is outside the globe
  const getArcballPoint = (clientX: number, clientY: number): THREE.Vector3 | null => {
    arcballMouse.x = (clientX / window.innerWidth) * 2 - 1
    arcballMouse.y = -(clientY / window.innerHeight) * 2 + 1
    arcballRaycaster.setFromCamera(arcballMouse, camera)

    const ray = arcballRaycaster.ray
    const target = new THREE.Vector3()

    // Only return a point if we hit the actual globe sphere
    if (ray.intersectSphere(arcballSphere, target)) {
      return target.normalize()
    }

    // Outside globe - return null to trigger screen-space rotation
    return null
  }

  return { getArcballPoint }
}

/** Creates the mousedown handler. */
export function createMouseDownHandler(
  showMapboxRef: React.MutableRefObject<boolean>
): {
  onMouseDown: (e: MouseEvent) => void
  mouseState: { mouseDownPos: { x: number; y: number }; lastMousePos: { x: number; y: number }; isMouseDown: boolean }
} {
  const mouseState = {
    mouseDownPos: { x: 0, y: 0 },
    lastMousePos: { x: 0, y: 0 },
    isMouseDown: false
  }

  const onMouseDown = (e: MouseEvent) => {
    // In Mapbox primary mode, let Mapbox handle mouse interactions
    if (showMapboxRef.current) return
    if (e.button !== 0) return
    // IMPORTANT: Update properties in-place instead of replacing the object
    // This ensures references to mouseDownPos in other handlers stay valid
    mouseState.mouseDownPos.x = e.clientX
    mouseState.mouseDownPos.y = e.clientY
    mouseState.lastMousePos.x = e.clientX
    mouseState.lastMousePos.y = e.clientY
    mouseState.isMouseDown = true
  }

  return { onMouseDown, mouseState }
}

/** Creates the mouseup handler. */
export function createMouseUpHandler(
  mouseState: { isMouseDown: boolean }
): () => void {
  return () => {
    mouseState.isMouseDown = false
  }
}

/** Creates the mousemove handler with arcball rotation and coordinate tracking. */
export function createMouseMoveHandler(
  camera: THREE.PerspectiveCamera,
  _renderer: THREE.WebGLRenderer,
  controls: OrbitControls,
  mouseState: { lastMousePos: { x: number; y: number }; isMouseDown: boolean },
  getArcballPoint: (clientX: number, clientY: number) => THREE.Vector3 | null,
  showMapboxRef: React.MutableRefObject<boolean>,
  lastMousePosRef: React.MutableRefObject<{ x: number; y: number }>,
  lastMoveTimeRef: React.MutableRefObject<number>,
  lastCoordsUpdateRef: React.MutableRefObject<number>,
  currentHoveredSiteRef: React.MutableRefObject<SiteData | null>,
  isFrozenRef: React.MutableRefObject<boolean>,
  setCursorCoords: (coords: { lat: number; lon: number } | null) => void,
  setTooltipPos: (pos: { x: number; y: number }) => void,
  setHoveredSite: (site: SiteData | null) => void,
  globe?: THREE.Mesh,
  empireHoverRefs?: EmpireHoverRefs
): (e: MouseEvent) => void {
  return (e: MouseEvent) => {
    // In Mapbox primary mode, let Mapbox handle mouse interactions
    if (showMapboxRef.current) return

    // Rotation - arcball on globe, screen-space outside
    if (mouseState.isMouseDown) {
      const prevPoint = getArcballPoint(mouseState.lastMousePos.x, mouseState.lastMousePos.y)
      const currPoint = getArcballPoint(e.clientX, e.clientY)

      let quat: THREE.Quaternion | null = null

      if (prevPoint && currPoint) {
        // Both on globe - use arcball rotation
        const axis = new THREE.Vector3().crossVectors(prevPoint, currPoint)
        const axisLen = axis.length()

        if (axisLen > 1e-10) {
          axis.divideScalar(axisLen)
          const dot = THREE.MathUtils.clamp(prevPoint.dot(currPoint), -1, 1)
          const angle = Math.acos(dot)
          if (angle > 1e-10) {
            quat = new THREE.Quaternion().setFromAxisAngle(axis, -angle)
          }
        }
      } else {
        // At least one point outside globe - use screen-space rotation
        const dx = e.clientX - mouseState.lastMousePos.x
        const dy = e.clientY - mouseState.lastMousePos.y
        const sensitivity = 0.005

        // Rotate around world Y for horizontal, camera right for vertical
        const yRot = new THREE.Quaternion().setFromAxisAngle(
          new THREE.Vector3(0, 1, 0),
          -dx * sensitivity
        )
        const cameraRight = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion)
        const xRot = new THREE.Quaternion().setFromAxisAngle(
          cameraRight,
          -dy * sensitivity
        )
        quat = yRot.multiply(xRot)
      }

      if (quat) {
        // Test where we'd end up - prevent crossing poles
        const testPos = camera.position.clone().applyQuaternion(quat)
        const testDir = testPos.clone().normalize()

        if (Math.abs(testDir.y) < 0.996) {
          camera.position.copy(testPos)
          camera.lookAt(0, 0, 0)
          controls.update()
        }
      }

      // Update properties in-place to preserve reference
      mouseState.lastMousePos.x = e.clientX
      mouseState.lastMousePos.y = e.clientY
    }

    // Track mouse position (hover detection is done in animation loop for performance)
    const mouseX = e.clientX
    const mouseY = e.clientY

    lastMousePosRef.current = { x: mouseX, y: mouseY }
    lastMoveTimeRef.current = Date.now()

    // Raycast to get geographic coordinates on globe
    const mouse = new THREE.Vector2(
      (mouseX / window.innerWidth) * 2 - 1,
      -(mouseY / window.innerHeight) * 2 + 1
    )
    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(mouse, camera)

    // Find intersection with globe (radius 1)
    const globeGeometry = new THREE.SphereGeometry(1, 32, 32)
    const globeMesh = new THREE.Mesh(globeGeometry)
    const intersects = raycaster.intersectObject(globeMesh)

    if (intersects.length > 0) {
      const point = intersects[0].point
      // Convert 3D point to lat/lon
      const lat = 90 - Math.acos(point.y) * 180 / Math.PI
      const lon = Math.atan2(point.z, -point.x) * 180 / Math.PI - 180
      // Normalize longitude to -180 to 180
      const normalizedLon = lon < -180 ? lon + 360 : lon > 180 ? lon - 360 : lon
      // Throttle coordinate updates to every 50ms
      const now = Date.now()
      if (now - lastCoordsUpdateRef.current > 50) {
        setCursorCoords({ lat, lon: normalizedLon })
        lastCoordsUpdateRef.current = now
      }
    } else {
      setCursorCoords(null)
    }

    // If frozen, ignore all cursor movement and site changes
    if (isFrozenRef.current) {
      return
    }

    // Not frozen - tooltip follows cursor and updates content
    // Use cached hover result from animation loop (set every 50ms)
    const nearestSite = currentHoveredSiteRef.current
    if (nearestSite) {
      setTooltipPos({ x: mouseX, y: mouseY })
      setHoveredSite(nearestSite)
    } else {
      setHoveredSite(null)
    }

    // Empire hover detection - both site and empire can show hover effects
    if (globe && empireHoverRefs) {
      const hoverResult = updateEmpireHoverState(
        mouseX,
        mouseY,
        camera,
        globe,
        empireHoverRefs
      )

      // Update cursor style: site > empire > crosshair
      const canvas = _renderer.domElement
      canvas.style.cursor = getHoverCursorStyle(nearestSite, hoverResult.empireId)
    }
  }
}

/** Creates the single-click handler with site selection and measurement snap. */
export function createSingleClickHandler(
  camera: THREE.PerspectiveCamera,
  renderer: THREE.WebGLRenderer,
  globe: THREE.Mesh,
  refs: {
    containerRef: React.RefObject<HTMLDivElement | null>
    highlightFrozenRef: React.MutableRefObject<boolean>
    isFrozenRef: React.MutableRefObject<boolean>
    frozenSiteRef: React.MutableRefObject<SiteData | null>
    hoveredSiteRef: React.MutableRefObject<SiteData | null>
    isContributePickerActiveRef: React.MutableRefObject<boolean>
    onContributeMapConfirmRef: React.MutableRefObject<(() => void) | undefined>
    measureModeRef: React.MutableRefObject<boolean | undefined>
    onMeasurePointAddRef: React.MutableRefObject<((coords: [number, number], snapped: boolean) => void) | undefined>
    measureSnapEnabledRef: React.MutableRefObject<boolean | undefined>
    sitesRef: React.MutableRefObject<SiteData[]>
    measurementsRef: React.MutableRefObject<Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>>
    currentMeasurePointsRef: React.MutableRefObject<Array<{ coords: [number, number]; snapped: boolean }>>
    onSiteSelectRef: React.MutableRefObject<((siteId: string | null, ctrlKey: boolean) => void) | undefined>
    onEmpireClickRef: React.MutableRefObject<((empireId: string, defaultYear?: number, yearOptions?: number[]) => void) | undefined>
    empireDefaultYearsRef: React.MutableRefObject<Record<string, number>>
    empireYearOptionsRef: React.MutableRefObject<Record<string, number[]>>
  },
  setters: {
    setIsFrozen: (frozen: boolean) => void
    setFrozenSite: (site: SiteData | null) => void
  },
  callbacks: {
    onProximitySet?: (coords: [number, number]) => void
  },
  mouseDownPos: { x: number; y: number }
): (e: MouseEvent) => void {
  return (e: MouseEvent) => {
    const clickX = e.clientX
    const clickY = e.clientY

    // Calculate distance from mousedown - if user dragged significantly, don't select
    const dragDist = Math.sqrt(
      (clickX - mouseDownPos.x) ** 2 + (clickY - mouseDownPos.y) ** 2
    )
    const maxClickDist = 10 // Allow up to 10px of movement and still count as a click
    const wasCleanClick = dragDist <= maxClickDist

    // If this was a drag (not a clean click), don't select anything
    if (!wasCleanClick) return

    // Clear highlight freeze on any globe click - allows clicking other dots
    if (refs.highlightFrozenRef.current) {
      refs.highlightFrozenRef.current = false
      refs.isFrozenRef.current = false
      setters.setIsFrozen(false)
      setters.setFrozenSite(null)
    }

    // Check if we're in "set on globe" mode for proximity
    // We need to access the current proximity state through a closure-safe way
    // The proximity prop is accessed from the outer scope
    const mouseX = (clickX / window.innerWidth) * 2 - 1
    const mouseY = -(clickY / window.innerHeight) * 2 + 1

    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), camera)
    const hits = raycaster.intersectObject(globe, false)

    if (hits.length > 0) {
      const point = hits[0].point.normalize()
      // Convert 3D point back to lat/lng
      const lat = 90 - Math.acos(point.y) * 180 / Math.PI
      const lng = Math.atan2(point.z, -point.x) * 180 / Math.PI - 180

      // Check if proximity set mode is active (via container data attribute)
      const isProximityMode = refs.containerRef.current?.dataset.proximityMode === 'true'
      if (isProximityMode && callbacks.onProximitySet) {
        callbacks.onProximitySet([lng, lat])
        return
      }

      // Check if contribute map picker mode is active - click confirms selection
      if (refs.isContributePickerActiveRef.current && refs.onContributeMapConfirmRef.current) {
        refs.onContributeMapConfirmRef.current()
        return
      }

      // Check if measurement mode is active
      if (refs.measureModeRef.current && refs.onMeasurePointAddRef.current) {
        // Snap to nearest point if snap mode is enabled
        let finalLng = lng
        let finalLat = lat
        let snapped = false

        if (refs.measureSnapEnabledRef.current) {
          try {
            const maxSnapDist = 20 // 20px snap radius
            let nearestScreenDist = Infinity
            let snapCoords: [number, number] | null = null
            const cameraPos = camera.position.clone().normalize()

            // Helper to check a point for snapping
            const checkSnapPoint = (pointLng: number, pointLat: number) => {
              if (typeof pointLng !== 'number' || typeof pointLat !== 'number') return
              if (isNaN(pointLng) || isNaN(pointLat)) return

              const phi = (90 - pointLat) * Math.PI / 180
              const theta = (pointLng + 180) * Math.PI / 180
              const pointPos = new THREE.Vector3(
                -Math.sin(phi) * Math.cos(theta),
                Math.cos(phi),
                Math.sin(phi) * Math.sin(theta)
              )

              // Only check front-facing points
              if (pointPos.dot(cameraPos) < 0) return

              // Project to screen
              const screenPos = pointPos.clone().project(camera)
              const screenX = (screenPos.x * 0.5 + 0.5) * renderer.domElement.clientWidth
              const screenY = (-screenPos.y * 0.5 + 0.5) * renderer.domElement.clientHeight

              // Calculate distance to click position
              const dx = screenX - clickX
              const dy = screenY - clickY
              const dist = Math.sqrt(dx * dx + dy * dy)

              if (dist < maxSnapDist && dist < nearestScreenDist) {
                nearestScreenDist = dist
                snapCoords = [pointLng, pointLat]
              }
            }

            // Check site dots for snapping
            if (refs.sitesRef.current && Array.isArray(refs.sitesRef.current)) {
              refs.sitesRef.current.forEach(site => {
                if (site?.coordinates) {
                  checkSnapPoint(site.coordinates[0], site.coordinates[1])
                }
              })
            }

            // Check existing measurement points for snapping
            if (refs.measurementsRef.current && Array.isArray(refs.measurementsRef.current)) {
              refs.measurementsRef.current.forEach(measurement => {
                if (measurement?.points) {
                  const [start, end] = measurement.points
                  if (start) checkSnapPoint(start[0], start[1])
                  if (end) checkSnapPoint(end[0], end[1])
                }
              })
            }

            // Also check current measurement point (if placing second point)
            if (refs.currentMeasurePointsRef.current && Array.isArray(refs.currentMeasurePointsRef.current) && refs.currentMeasurePointsRef.current.length > 0) {
              const firstPoint = refs.currentMeasurePointsRef.current[0]
              if (firstPoint?.coords) {
                checkSnapPoint(firstPoint.coords[0], firstPoint.coords[1])
              }
            }

            // Apply snap if found
            if (snapCoords) {
              finalLng = snapCoords[0]
              finalLat = snapCoords[1]
              snapped = true
            }
          } catch (e) {
            console.error('Snap calculation error:', e)
          }
        }

        refs.onMeasurePointAddRef.current([finalLng, finalLat], snapped)
        return
      }
    }

    // ========== SITE SELECTION (HIGHEST PRIORITY) ==========
    // Sites ALWAYS take priority over empires

    // IMPORTANT UX: If a tooltip is visible, ALWAYS select that site
    // This ensures the user selects what they're reading, not what's under cursor
    const displayedSite = refs.isFrozenRef.current ? refs.frozenSiteRef.current : refs.hoveredSiteRef.current
    if (displayedSite && refs.onSiteSelectRef.current) {
      // Freeze tooltip position on click to prevent any position jumping
      if (!refs.isFrozenRef.current) {
        refs.isFrozenRef.current = true
        setters.setIsFrozen(true)
        setters.setFrozenSite(displayedSite)
      }
      refs.onSiteSelectRef.current(displayedSite.id, e.ctrlKey || e.metaKey)
      return
    }

    // No tooltip visible - find nearest site within click radius (front side only)
    let nearestSite: SiteData | null = null
    let nearestScreenDist = Infinity
    const siteClickRadius = 10 // 10px radius for direct site clicks
    const cameraPos = camera.position.clone().normalize()

    refs.sitesRef.current.forEach(site => {
      const [lng, lat] = site.coordinates
      const phi = (90 - lat) * Math.PI / 180
      const theta = (lng + 180) * Math.PI / 180
      const r = 1.002
      const sitePos = new THREE.Vector3(
        -r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi),
        r * Math.sin(phi) * Math.sin(theta)
      )

      // Only detect front-side sites
      if (sitePos.clone().normalize().dot(cameraPos) <= 0) return

      // Project to screen coordinates
      const projectedPos = sitePos.clone()
      projectedPos.project(camera)
      const screenX = (projectedPos.x + 1) / 2 * window.innerWidth
      const screenY = (-projectedPos.y + 1) / 2 * window.innerHeight

      const screenDist = Math.sqrt((clickX - screenX) ** 2 + (clickY - screenY) ** 2)
      if (screenDist < nearestScreenDist) {
        nearestScreenDist = screenDist
        if (screenDist <= siteClickRadius) {
          nearestSite = site
        }
      }
    })

    // If a site was clicked, select it (sites have priority over empires)
    if (nearestSite && refs.onSiteSelectRef.current) {
      refs.onSiteSelectRef.current((nearestSite as SiteData).id, e.ctrlKey || e.metaKey)
      return
    }

    // ========== EMPIRE CLICK (SECOND PRIORITY) ==========
    // Only triggers if no site was clicked
    if (refs.onEmpireClickRef.current) {
      const raycasterEmpire = new THREE.Raycaster()
      raycasterEmpire.setFromCamera(new THREE.Vector2(mouseX, mouseY), camera)

      // Find all empire fill meshes (they have userData.empireId and isFillMesh)
      const empireMeshes: THREE.Object3D[] = []
      globe.traverse((child) => {
        if (child.userData?.empireId && child.userData?.isFillMesh && child instanceof THREE.Mesh) {
          empireMeshes.push(child)
        }
      })

      if (empireMeshes.length > 0) {
        const empireHits = raycasterEmpire.intersectObjects(empireMeshes)
        if (empireHits.length > 0) {
          // Find the first visible hit with an empireId
          for (const hit of empireHits) {
            const empireId = hit.object.userData?.empireId
            if (empireId && hit.object.visible) {
              const defaultYear = refs.empireDefaultYearsRef.current[empireId]
              const yearOptions = refs.empireYearOptionsRef.current[empireId]
              refs.onEmpireClickRef.current(empireId, defaultYear, yearOptions)
              return
            }
          }
        }
      }
    }

    // ========== EMPTY SPACE CLICK (DESELECT) ==========
    // Click on empty space (globe or stars) - deselect all
    if (refs.onSiteSelectRef.current) {
      refs.onSiteSelectRef.current(null, false)
    }
  }
}

/** Creates the click handler that distinguishes single vs double click. */
export function createClickHandler(
  handleSingleClick: (e: MouseEvent) => void,
  isLoading?: boolean
): {
  onClick: (e: MouseEvent) => void
  clickState: { clickTimeout: number | null; pendingClickEvent: MouseEvent | null }
} {
  const clickState = {
    clickTimeout: null as number | null,
    pendingClickEvent: null as MouseEvent | null
  }

  const onClick = (e: MouseEvent) => {
    if (isLoading) return  // Don't handle clicks while loading
    // Store click and wait to see if it's a double-click
    clickState.pendingClickEvent = e
    if (clickState.clickTimeout) clearTimeout(clickState.clickTimeout)
    clickState.clickTimeout = window.setTimeout(() => {
      if (clickState.pendingClickEvent) {
        handleSingleClick(clickState.pendingClickEvent)
        clickState.pendingClickEvent = null
      }
    }, 250) // Wait 250ms for potential double-click
  }

  return { onClick, clickState }
}

/** Creates the double-click zoom handler. */
export function createDoubleClickHandler(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  globe: THREE.Mesh,
  minDist: number,
  maxDist: number,
  cameraAnimationRef: React.MutableRefObject<number | null>,
  clickState: { clickTimeout: number | null; pendingClickEvent: MouseEvent | null }
): (e: MouseEvent) => void {
  return (e: MouseEvent) => {
    // Cancel pending single click
    if (clickState.clickTimeout) {
      clearTimeout(clickState.clickTimeout)
      clickState.clickTimeout = null
    }
    clickState.pendingClickEvent = null

    const mouseX = (e.clientX / window.innerWidth) * 2 - 1
    const mouseY = -(e.clientY / window.innerHeight) * 2 + 1
    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), camera)

    const hits = raycaster.intersectObject(globe, false)
    if (hits.length > 0) {
      const clickedPoint = hits[0].point.clone().normalize()
      const currentDist = camera.position.length()

      // Calculate target zoom - zoom in 3 steps toward clicked point
      const zoomStep = (maxDist - minDist) / 10 // Each step is 10% of total range
      const newDist = Math.max(minDist, currentDist - zoomStep * 3)

      const startPos = camera.position.clone()
      // Position camera so clicked point is centered on screen after zoom
      // Camera at clickedPoint * distance, looking at origin = clicked point at center
      const endPos = clickedPoint.clone().multiplyScalar(newDist)

      // Cancel any existing camera animation
      if (cameraAnimationRef.current) {
        cancelAnimationFrame(cameraAnimationRef.current)
        cameraAnimationRef.current = null
      }

      // Animate to new position
      const duration = 400
      const startTime = performance.now()

      const animateZoom = () => {
        const elapsed = performance.now() - startTime
        const progress = Math.min(1, elapsed / duration)
        const eased = 1 - Math.pow(1 - progress, 3) // Ease out cubic

        camera.position.lerpVectors(startPos, endPos, eased)
        camera.lookAt(0, 0, 0)
        controls.update()

        if (progress < 1) {
          cameraAnimationRef.current = requestAnimationFrame(animateZoom)
        } else {
          cameraAnimationRef.current = null
        }
      }
      cameraAnimationRef.current = requestAnimationFrame(animateZoom)
    }
  }
}

/** Creates the mouseleave handler. */
export function createMouseLeaveHandler(
  setHoveredSite: (site: SiteData | null) => void,
  lastMousePosRef: React.MutableRefObject<{ x: number; y: number }>,
  renderer?: THREE.WebGLRenderer,
  empireHoverRefs?: EmpireHoverRefs
): () => void {
  return () => {
    setHoveredSite(null)
    lastMousePosRef.current = { x: -1000, y: -1000 } // Move off screen

    // Clear empire hover state when leaving canvas
    if (empireHoverRefs) {
      clearEmpireHoverState(empireHoverRefs)
    }

    // Reset cursor to crosshair
    if (renderer) {
      renderer.domElement.style.cursor = 'crosshair'
    }
  }
}

/**
 * Sets up all event handlers and returns a cleanup function.
 * This is the main entry point for attaching all event listeners.
 */
export function setupEventHandlers(
  sceneObjects: EventHandlerSceneObjects,
  refs: EventHandlerRefs,
  setters: EventHandlerSetters,
  callbacks: EventHandlerCallbacks,
  isManualZoom: React.MutableRefObject<boolean>
): EventHandlerCleanup {
  const { renderer, camera, controls, globe, minDist, maxDist } = sceneObjects

  // ----- 3.1: Window Resize -----
  const onResize = createResizeHandler(camera, renderer, refs.mapboxServiceRef)
  window.addEventListener('resize', onResize)

  // ----- 3.2: Zoom Control -----
  // Disable default zoom - we'll handle it ourselves
  controls.enableZoom = false

  // Sync slider when camera changes (mouse wheel zoom, not slider)
  const onControlsChange = createControlsChangeHandler(
    camera, minDist, maxDist, isManualZoom, refs.showMapboxRef, controls, setters.setZoom
  )
  controls.addEventListener('change', onControlsChange)

  // Wheel zoom
  const { handleWheel } = createWheelHandler(
    camera, controls, globe, minDist, maxDist, refs.showMapboxRef, refs.zoomRef
  )
  renderer.domElement.addEventListener('wheel', handleWheel, { passive: false })

  // Prevent browser zoom (Ctrl+scroll)
  const preventBrowserZoom = createPreventBrowserZoomHandler(refs.showMapboxRef)
  window.addEventListener('wheel', preventBrowserZoom, { passive: false })

  // ----- 3.3: Mouse Event Handlers -----
  // Arcball rotation
  const { getArcballPoint } = createArcballSystem(camera)

  // Mouse down/up
  const { onMouseDown, mouseState } = createMouseDownHandler(refs.showMapboxRef)
  const onMouseUp = createMouseUpHandler(mouseState)

  // Mouse move (arcball + coordinates + tooltips + empire hover)
  const onMouseMove = createMouseMoveHandler(
    camera, renderer, controls, mouseState, getArcballPoint,
    refs.showMapboxRef, refs.lastMousePosRef, refs.lastMoveTimeRef,
    refs.lastCoordsUpdateRef, refs.currentHoveredSiteRef,
    refs.isFrozenRef, setters.setCursorCoords, setters.setTooltipPos, setters.setHoveredSite,
    globe,
    {
      hoveredEmpireRef: refs.hoveredEmpireRef,
      empireBorderLinesRef: refs.empireBorderLinesRef,
      empireFillMeshesRef: refs.empireFillMeshesRef,
    }
  )

  // Click handling (single click with delay for double-click discrimination)
  const handleSingleClick = createSingleClickHandler(
    camera, renderer, globe,
    {
      containerRef: refs.containerRef,
      highlightFrozenRef: refs.highlightFrozenRef,
      isFrozenRef: refs.isFrozenRef,
      frozenSiteRef: refs.frozenSiteRef,
      hoveredSiteRef: refs.hoveredSiteRef,
      isContributePickerActiveRef: refs.isContributePickerActiveRef,
      onContributeMapConfirmRef: refs.onContributeMapConfirmRef,
      measureModeRef: refs.measureModeRef,
      onMeasurePointAddRef: refs.onMeasurePointAddRef,
      measureSnapEnabledRef: refs.measureSnapEnabledRef,
      sitesRef: refs.sitesRef,
      measurementsRef: refs.measurementsRef,
      currentMeasurePointsRef: refs.currentMeasurePointsRef,
      onSiteSelectRef: refs.onSiteSelectRef,
      onEmpireClickRef: refs.onEmpireClickRef,
      empireDefaultYearsRef: refs.empireDefaultYearsRef,
      empireYearOptionsRef: refs.empireYearOptionsRef,
    },
    {
      setIsFrozen: setters.setIsFrozen,
      setFrozenSite: setters.setFrozenSite,
    },
    {
      onProximitySet: callbacks.onProximitySet,
    },
    mouseState.mouseDownPos
  )

  const { onClick, clickState } = createClickHandler(handleSingleClick, callbacks.isLoading)

  // Double-click zoom
  const onDoubleClick = createDoubleClickHandler(
    camera, controls, globe, minDist, maxDist,
    refs.cameraAnimationRef, clickState
  )

  // Mouse leave (with empire hover cleanup)
  const onMouseLeave = createMouseLeaveHandler(
    setters.setHoveredSite,
    refs.lastMousePosRef,
    renderer,
    {
      hoveredEmpireRef: refs.hoveredEmpireRef,
      empireBorderLinesRef: refs.empireBorderLinesRef,
      empireFillMeshesRef: refs.empireFillMeshesRef,
    }
  )

  // ----- Attach listeners -----
  renderer.domElement.addEventListener('mousedown', onMouseDown)
  renderer.domElement.addEventListener('mousemove', onMouseMove)
  renderer.domElement.addEventListener('mouseleave', onMouseLeave)
  renderer.domElement.addEventListener('click', onClick)
  renderer.domElement.addEventListener('dblclick', onDoubleClick)
  window.addEventListener('mouseup', onMouseUp)

  // ----- Cleanup -----
  return {
    cleanup: () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('wheel', preventBrowserZoom)
      renderer.domElement.removeEventListener('wheel', handleWheel)
      renderer.domElement.removeEventListener('mousedown', onMouseDown)
      renderer.domElement.removeEventListener('mousemove', onMouseMove)
      renderer.domElement.removeEventListener('mouseleave', onMouseLeave)
      renderer.domElement.removeEventListener('click', onClick)
      renderer.domElement.removeEventListener('dblclick', onDoubleClick)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }
}
