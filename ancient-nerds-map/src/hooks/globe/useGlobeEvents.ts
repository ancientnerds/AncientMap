/**
 * useGlobeEvents - Mouse, keyboard, and resize event handlers
 * Manages all user interactions with the globe
 */

import { useCallback, useRef, useEffect } from 'react'
import type * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

interface GlobeEventRefs {
  camera: THREE.PerspectiveCamera | null
  renderer: THREE.WebGLRenderer | null
  controls: OrbitControls | null
  globe: THREE.Mesh | null
  showMapbox: boolean
}

interface GlobeEventCallbacks {
  // Resize
  onResize?: () => void

  // Mouse move/coordinate tracking
  onMouseMove?: (x: number, y: number, lat: number | null, lng: number | null) => void
  onCursorCoordsChange?: (lat: number, lng: number) => void
  onCursorOffGlobe?: () => void

  // Click handling (returning true from onClick skips default behavior)
  onClick?: (e: MouseEvent, lat: number, lng: number, wasCleanClick: boolean) => boolean | void
  onGlobeClick?: (lat: number, lng: number) => void
  onDoubleClick?: (lat: number, lng: number) => void

  // Hover/site interaction
  onHover?: (site: unknown | null) => void

  // Zoom
  onZoomChange?: (zoom: number) => void
  onZoomStart?: () => void
  onZoomEnd?: () => void

  // Drag state
  onDragStart?: () => void
  onDragEnd?: () => void

  // Keyboard
  onKeyDown?: (e: KeyboardEvent) => void
  onKeyUp?: (e: KeyboardEvent) => void
}

interface GlobeEventsOptions {
  containerRef: React.RefObject<HTMLElement>
  refs: React.MutableRefObject<GlobeEventRefs>
  callbacks?: GlobeEventCallbacks
  minDist?: number
  maxDist?: number
}

export function useGlobeEvents(options: GlobeEventsOptions) {
  const {
    containerRef,
    refs,
    callbacks = {},
    minDist = 1.02,
    maxDist = 2.44
  } = options

  // Mouse tracking
  const lastMousePosRef = useRef({ x: -1, y: -1 })
  const lastMoveTimeRef = useRef(0)
  const isMouseDownRef = useRef(false)
  const mouseDownPosRef = useRef({ x: 0, y: 0 })

  // Cursor coordinates (lat/lng under cursor)
  const cursorCoordsRef = useRef<{ lat: number; lng: number } | null>(null)

  // Auto-rotation state
  const isAutoRotatingRef = useRef(true)
  const manualRotationRef = useRef(false)
  const isHoveringListRef = useRef(false)

  // Animation frame tracking
  const cameraAnimationRef = useRef<number | null>(null)

  // Get point on unit sphere from screen coords
  const getArcballPoint = useCallback((clientX: number, clientY: number): THREE.Vector3 | null => {
    const { camera, globe } = refs.current
    if (!camera || !globe) return null

    const raycaster = new (window as any).THREE.Raycaster()
    const mouse = new (window as any).THREE.Vector2()

    mouse.x = (clientX / window.innerWidth) * 2 - 1
    mouse.y = -(clientY / window.innerHeight) * 2 + 1

    raycaster.setFromCamera(mouse, camera)

    const sphere = new (window as any).THREE.Sphere(new (window as any).THREE.Vector3(0, 0, 0), 1)
    const target = new (window as any).THREE.Vector3()

    if (raycaster.ray.intersectSphere(sphere, target)) {
      return target.normalize()
    }

    return null
  }, [refs])

  // Convert 3D point to lat/lng
  const pointToLatLng = useCallback((point: THREE.Vector3): { lat: number; lng: number } => {
    const lat = 90 - Math.acos(point.y) * (180 / Math.PI)
    const lng = Math.atan2(point.z, -point.x) * (180 / Math.PI)
    return { lat, lng }
  }, [])

  // Handle window resize
  const handleResize = useCallback(() => {
    const { camera, renderer } = refs.current
    if (!camera || !renderer) return

    camera.aspect = window.innerWidth / window.innerHeight
    camera.updateProjectionMatrix()
    renderer.setSize(window.innerWidth, window.innerHeight)

    callbacks.onResize?.()
  }, [refs, callbacks])

  // Handle mouse down
  const handleMouseDown = useCallback((e: MouseEvent) => {
    const { showMapbox } = refs.current
    if (showMapbox) return
    if (e.button !== 0) return

    isMouseDownRef.current = true
    mouseDownPosRef.current = { x: e.clientX, y: e.clientY }
    lastMousePosRef.current = { x: e.clientX, y: e.clientY }
  }, [refs])

  // Handle mouse up
  const handleMouseUp = useCallback(() => {
    isMouseDownRef.current = false
  }, [])

  // Handle mouse move
  const handleMouseMove = useCallback((e: MouseEvent) => {
    const { camera, controls, showMapbox } = refs.current
    if (!camera || !controls) return
    if (showMapbox) return

    // Rotation when dragging
    if (isMouseDownRef.current) {
      const prevPoint = getArcballPoint(lastMousePosRef.current.x, lastMousePosRef.current.y)
      const currPoint = getArcballPoint(e.clientX, e.clientY)

      if (prevPoint && currPoint) {
        // Arcball rotation
        const axis = new (window as any).THREE.Vector3().crossVectors(prevPoint, currPoint)
        const axisLen = axis.length()

        if (axisLen > 1e-10) {
          axis.divideScalar(axisLen)
          const dot = (window as any).THREE.MathUtils.clamp(prevPoint.dot(currPoint), -1, 1)
          const angle = Math.acos(dot)

          if (angle > 1e-10) {
            const quat = new (window as any).THREE.Quaternion().setFromAxisAngle(axis, -angle)
            const testPos = camera.position.clone().applyQuaternion(quat)
            const testDir = testPos.clone().normalize()

            // Prevent crossing poles
            if (Math.abs(testDir.y) < 0.996) {
              camera.position.copy(testPos)
              camera.lookAt(0, 0, 0)
              controls.update()
            }
          }
        }
      } else {
        // Screen-space rotation when outside globe
        const dx = e.clientX - lastMousePosRef.current.x
        const dy = e.clientY - lastMousePosRef.current.y
        const sensitivity = 0.005

        const yRot = new (window as any).THREE.Quaternion().setFromAxisAngle(
          new (window as any).THREE.Vector3(0, 1, 0),
          -dx * sensitivity
        )
        const cameraRight = new (window as any).THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion)
        const xRot = new (window as any).THREE.Quaternion().setFromAxisAngle(
          cameraRight,
          -dy * sensitivity
        )
        const quat = yRot.multiply(xRot)

        const testPos = camera.position.clone().applyQuaternion(quat)
        const testDir = testPos.clone().normalize()

        if (Math.abs(testDir.y) < 0.996) {
          camera.position.copy(testPos)
          camera.lookAt(0, 0, 0)
          controls.update()
        }
      }

      lastMousePosRef.current = { x: e.clientX, y: e.clientY }
    }

    // Track mouse position for hover
    lastMousePosRef.current = { x: e.clientX, y: e.clientY }
    lastMoveTimeRef.current = Date.now()

    // Get lat/lng under cursor
    const point = getArcballPoint(e.clientX, e.clientY)
    if (point) {
      const coords = pointToLatLng(point)
      cursorCoordsRef.current = coords
      callbacks.onMouseMove?.(e.clientX, e.clientY, coords.lat, coords.lng)
    } else {
      cursorCoordsRef.current = null
      callbacks.onMouseMove?.(e.clientX, e.clientY, null, null)
    }
  }, [refs, getArcballPoint, pointToLatLng, callbacks])

  // Handle wheel zoom
  const handleWheel = useCallback((e: WheelEvent) => {
    const { camera, controls, globe, showMapbox } = refs.current
    if (!camera || !controls || !globe) return
    if (showMapbox) return

    e.preventDefault()

    const zoomSpeed = 0.03
    const delta = e.deltaY > 0 ? 1 : -1
    const currentDist = camera.position.length()
    const scaleFactor = 1 + delta * zoomSpeed
    const newDist = Math.max(minDist, Math.min(maxDist, currentDist * scaleFactor))

    if (newDist === currentDist) return

    // Get cursor position on globe for zoom-to-cursor
    const mouseX = (e.clientX / window.innerWidth) * 2 - 1
    const mouseY = -(e.clientY / window.innerHeight) * 2 + 1

    const raycaster = new (window as any).THREE.Raycaster()
    raycaster.setFromCamera(new (window as any).THREE.Vector2(mouseX, mouseY), camera)
    const intersects = raycaster.intersectObject(globe, false)

    if (intersects.length > 0) {
      const cursorDir = intersects[0].point.clone().normalize()
      const cameraDir = camera.position.clone().normalize()
      const zoomingIn = delta < 0
      const zoomLevel = 1 - (currentDist - minDist) / (maxDist - minDist)

      if (zoomingIn) {
        const blendFactor = 0.15 * (1 - zoomLevel * 0.5)
        const newDir = cameraDir.lerp(cursorDir, blendFactor).normalize()
        camera.position.copy(newDir.multiplyScalar(newDist))
      } else {
        camera.position.copy(cameraDir.multiplyScalar(newDist))
      }

      controls.target.set(0, 0, 0)
      camera.lookAt(0, 0, 0)
    } else {
      const direction = camera.position.clone().normalize()
      camera.position.copy(direction.multiplyScalar(newDist))
    }

    controls.update()

    // Calculate new zoom percent
    const scaledZoom = ((maxDist - newDist) / (maxDist - minDist)) * 100
    const zoomPercent = Math.max(0, Math.min(66, (scaledZoom / 80) * 66))
    callbacks.onZoomChange?.(Math.round(zoomPercent))
  }, [refs, minDist, maxDist, callbacks])

  // Handle keyboard events
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    callbacks.onKeyDown?.(e)
  }, [callbacks])

  const handleKeyUp = useCallback((e: KeyboardEvent) => {
    callbacks.onKeyUp?.(e)
  }, [callbacks])

  // Prevent browser zoom (Ctrl+scroll) when not in Mapbox mode
  const preventBrowserZoom = useCallback((e: WheelEvent) => {
    const { showMapbox } = refs.current
    if (showMapbox) return
    if (e.ctrlKey) {
      e.preventDefault()
    }
  }, [refs])

  // Handle click with clean click detection
  const handleClick = useCallback((e: MouseEvent) => {
    // Calculate drag distance to determine if this was a clean click
    const dx = e.clientX - mouseDownPosRef.current.x
    const dy = e.clientY - mouseDownPosRef.current.y
    const dragDist = Math.sqrt(dx * dx + dy * dy)
    const maxClickDist = 10 // Allow up to 10px of movement and still count as a click
    const wasCleanClick = dragDist <= maxClickDist

    const point = getArcballPoint(e.clientX, e.clientY)
    if (point) {
      const coords = pointToLatLng(point)
      // If custom onClick handler returns true, skip default behavior
      const handled = callbacks.onClick?.(e, coords.lat, coords.lng, wasCleanClick)
      if (!handled && wasCleanClick) {
        callbacks.onGlobeClick?.(coords.lat, coords.lng)
      }
    }
  }, [getArcballPoint, pointToLatLng, callbacks])

  // Set up event listeners
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    window.addEventListener('resize', handleResize)
    container.addEventListener('mousedown', handleMouseDown)
    window.addEventListener('mouseup', handleMouseUp)
    container.addEventListener('mousemove', handleMouseMove)
    container.addEventListener('wheel', handleWheel, { passive: false })
    window.addEventListener('wheel', preventBrowserZoom, { passive: false })
    container.addEventListener('click', handleClick)
    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)

    return () => {
      window.removeEventListener('resize', handleResize)
      container.removeEventListener('mousedown', handleMouseDown)
      window.removeEventListener('mouseup', handleMouseUp)
      container.removeEventListener('mousemove', handleMouseMove)
      container.removeEventListener('wheel', handleWheel)
      window.removeEventListener('wheel', preventBrowserZoom)
      container.removeEventListener('click', handleClick)
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
    }
  }, [containerRef, handleResize, handleMouseDown, handleMouseUp, handleMouseMove, handleWheel, preventBrowserZoom, handleClick, handleKeyDown, handleKeyUp])

  return {
    // Mouse state
    lastMousePosRef,
    lastMoveTimeRef,
    isMouseDownRef,
    cursorCoordsRef,

    // Rotation state
    isAutoRotatingRef,
    manualRotationRef,
    isHoveringListRef,

    // Animation
    cameraAnimationRef,

    // Utility functions
    getArcballPoint,
    pointToLatLng
  }
}
