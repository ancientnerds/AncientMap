import * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

/**
 * The globe camera's motion, one definition for every input device.
 *
 * The mouse handlers (eventHandlers.ts) and the touch gestures
 * (touchGestures.ts) turn and zoom the globe with exactly this maths. It used
 * to live inside the mouse and wheel handlers; on 2026-10-01 the globe could
 * not be turned or zoomed with fingers, and a second copy for touch would have
 * drifted from the first. Moved, not rewritten: desktopCameraMotion.test.ts
 * pins the numbers the mouse and wheel produce.
 */

/** Convert viewport mouse coordinates to normalized device coordinates (-1 to 1).
 *  Uses canvas bounding rect to account for CSS transforms (e.g. news feed shift). */
export function canvasNDC(clientX: number, clientY: number, canvas: HTMLCanvasElement): { x: number; y: number } {
  const rect = canvas.getBoundingClientRect()
  return {
    x: ((clientX - rect.left) / rect.width) * 2 - 1,
    y: -((clientY - rect.top) / rect.height) * 2 + 1,
  }
}

/** Screen position, in the viewport's pixels. */
export interface ScreenPoint {
  x: number
  y: number
}

/**
 * Creates the drag rotation: arcball on the globe, screen-space outside it,
 * never across a pole. `rotate(from, to)` turns the camera as dragging a
 * pointer from `from` to `to` would.
 */
export function createArcballRotator(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  getArcballPoint: (clientX: number, clientY: number) => THREE.Vector3 | null
): (from: ScreenPoint, to: ScreenPoint) => void {
  return (from, to) => {
    const prevPoint = getArcballPoint(from.x, from.y)
    const currPoint = getArcballPoint(to.x, to.y)

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
      const dx = to.x - from.x
      const dy = to.y - from.y
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
  }
}

/** One mouse-wheel notch: the camera distance changes by this fraction. */
export const WHEEL_ZOOM_STEP = 0.03

/**
 * Zoom with cursor-following: the camera distance is multiplied by
 * `scaleFactor` (below 1 zooms in) and, zooming in over the globe, the view
 * leans toward the point under `ndc`.
 *
 * `leanSteps` scales that lean: a wheel notch is one step, a pinch frame
 * covers a fraction or several notches' worth of distance change.
 */
export function zoomCameraBy(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  globe: THREE.Mesh,
  minDist: number,
  maxDist: number,
  scaleFactor: number,
  ndc: { x: number; y: number },
  leanSteps: number
): void {
  const currentDist = camera.position.length()

  // Clamp with the controls' bound: the Mapbox switch distance until Mapbox
  // is ready (orbitMinDistance). minDist stays the zoom formulas' range end.
  const newDist = Math.max(controls.minDistance, Math.min(maxDist, currentDist * scaleFactor))

  // At the clamp, do nothing: steering toward the cursor before
  // controls.update() snaps the distance back would slide the globe.
  // Epsilon, because length() after a clamp is only ~minDistance.
  if (Math.abs(newDist - currentDist) < 1e-6) return

  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(new THREE.Vector2(ndc.x, ndc.y), camera)
  const intersects = raycaster.intersectObject(globe, false)

  if (intersects.length > 0) {
    const cursorDir = intersects[0].point.clone().normalize()
    const cameraDir = camera.position.clone().normalize()

    // Calculate blend factor based on zoom direction and level
    // Zoom in: move toward cursor. Zoom out: stay on current direction
    const zoomingIn = scaleFactor < 1
    const zoomLevel = 1 - (currentDist - minDist) / (maxDist - minDist) // 0 = far, 1 = close

    if (zoomingIn) {
      // Blend camera direction toward cursor direction
      // More aggressive blend when zoomed out, gentler when zoomed in
      const blendFactor = 0.15 * (1 - zoomLevel * 0.5) * leanSteps
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
