import { vi } from 'vitest'
import * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CAMERA } from '../../../../config/globeConstants'
import { createArcballSystem, createMouseDownHandler, createMouseMoveHandler } from '../eventHandlers'

/** A phone-sized canvas: the globe overflows it sideways, as on a real handset. */
const WIDTH = 412
const HEIGHT = 915
export const MIN_DIST = CAMERA.MIN_DISTANCE
export const MAX_DIST = CAMERA.MAX_DISTANCE
/** The closest distance the controls allow until Mapbox is ready. */
export const MAPBOX_SWITCH = 1.304

/** Camera position for a lng/lat/distance pose (inverse of __DEMO.getCameraState). */
export function position(lng: number, lat: number, distance: number): THREE.Vector3 {
  const latR = (lat * Math.PI) / 180
  const theta = ((lng + 180) * Math.PI) / 180
  const rho = distance * Math.cos(latR)
  return new THREE.Vector3(-rho * Math.cos(theta), distance * Math.sin(latR), rho * Math.sin(theta))
}

export const round = (v: THREE.Vector3): number[] => [v.x, v.y, v.z].map(n => Number(n.toFixed(10)))

export type Pose = [lng: number, lat: number, distance: number]

/** The pieces the camera motion needs, around a real camera and a real unit sphere. */
export function scene(pose: Pose, controlsMinDistance = MAPBOX_SWITCH) {
  const camera = new THREE.PerspectiveCamera(CAMERA.FOV, WIDTH / HEIGHT, CAMERA.NEAR, CAMERA.FAR)
  camera.position.copy(position(...pose))
  camera.lookAt(0, 0, 0)
  camera.updateMatrixWorld()
  const globe = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 32))
  globe.updateMatrixWorld()
  const canvas = {
    getBoundingClientRect: () => ({ left: 0, top: 0, width: WIDTH, height: HEIGHT }),
    style: {} as Record<string, string>,
  } as unknown as HTMLCanvasElement
  const controls = {
    minDistance: controlsMinDistance,
    target: new THREE.Vector3(),
    update: vi.fn(),
  } as unknown as OrbitControls
  const renderer = { domElement: canvas } as unknown as THREE.WebGLRenderer
  return { camera, globe, canvas, controls, renderer }
}

/** A mouse drag along `path` through the real mouse handlers; the camera position after each move. */
export function mouseDrag(pose: Pose, path: Array<[number, number]>) {
  const s = scene(pose)
  const showMapbox = { current: false }
  const { getArcballPoint } = createArcballSystem(s.camera, s.renderer)
  const { onMouseDown, mouseState } = createMouseDownHandler(showMapbox)
  const onMouseMove = createMouseMoveHandler(
    s.camera, s.renderer, s.controls, mouseState, getArcballPoint, showMapbox,
    { current: { x: 0, y: 0 } }, { current: 0 }, { current: 0 }, { current: null },
    { current: false }, vi.fn(), vi.fn(), vi.fn(),
  )
  const [first, ...rest] = path
  onMouseDown({ button: 0, clientX: first[0], clientY: first[1] } as MouseEvent)
  const after = rest.map(([x, y]) => {
    onMouseMove({ clientX: x, clientY: y } as MouseEvent)
    return round(s.camera.position)
  })
  return { ...s, after }
}
