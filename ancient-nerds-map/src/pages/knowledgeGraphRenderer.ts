/**
 * GPU-friendly renderer for the knowledge graph.
 *
 * Follows the globe's rendering recipe (sitesRenderer.ts): ALL nodes live in
 * ONE THREE.Points object (BufferGeometry + point shader), all edges in ONE
 * THREE.LineSegments — two draw calls total, regardless of graph size. The
 * previous 3d-force-graph engine created a sphere mesh per node (11K draw
 * calls) and melted GPUs.
 *
 * Layout runs with d3-force-3d on the main thread, ticked inside the render
 * loop until it settles; positions stream into the buffers each tick.
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { forceCenter, forceLink, forceManyBody, forceSimulation } from 'd3-force-3d'

export interface RenderNode {
  id: string
  label: string
  kind: string
  status: string
  signal: number
  degree: number
  paper_slug: string | null
  site_id: string | null
  x?: number
  y?: number
  z?: number
}

export interface RenderLink {
  source: string | RenderNode
  target: string | RenderNode
  kind: string
}

type Rgb = [number, number, number]

interface Callbacks {
  onNodeClick: (node: RenderNode | null) => void
  onHover: (node: RenderNode | null, x: number, y: number) => void
}

const VERTEX_SHADER = `
attribute float size;
varying vec3 vColor;
void main() {
  vColor = color;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = size * (240.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}
`

const FRAGMENT_SHADER = `
varying vec3 vColor;
void main() {
  vec2 c = gl_PointCoord - vec2(0.5);
  float d = length(c);
  if (d > 0.5) discard;
  float alpha = smoothstep(0.5, 0.32, d);
  gl_FragColor = vec4(vColor, alpha * 0.95);
}
`

export class KnowledgeGraphRenderer {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()

  private nodes: RenderNode[] = []
  private links: RenderLink[] = []
  private points: THREE.Points | null = null
  private lines: THREE.LineSegments | null = null
  private simulation: ReturnType<typeof forceSimulation> | null = null

  private nodeColorFn: (n: RenderNode) => Rgb = () => [0.5, 0.7, 0.8]
  private linkColorFn: (l: RenderLink) => Rgb = () => [0.2, 0.35, 0.4]

  private rafId = 0
  private paused = false
  private hoverIndex = -1
  private flyTarget: { pos: THREE.Vector3; look: THREE.Vector3; t: number } | null = null

  constructor(
    private container: HTMLElement,
    private callbacks: Callbacks,
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setClearColor('#0a1a1f')
    container.appendChild(this.renderer.domElement)

    this.camera = new THREE.PerspectiveCamera(60, 1, 1, 20000)
    this.camera.position.set(0, 0, 900)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08

    this.raycaster.params.Points = { threshold: 6 }

    this.handleResize()
    window.addEventListener('resize', this.handleResize)
    this.renderer.domElement.addEventListener('pointermove', this.handlePointerMove)
    this.renderer.domElement.addEventListener('click', this.handleClick)

    this.loop()
  }

  setData(nodes: RenderNode[], links: RenderLink[]): void {
    this.simulation?.stop()
    this.disposeGraphObjects()
    this.nodes = nodes
    this.links = links
    this.hoverIndex = -1

    const n = nodes.length
    const positions = new Float32Array(n * 3)
    const colors = new Float32Array(n * 3)
    const sizes = new Float32Array(n)
    for (let i = 0; i < n; i++) {
      // sqrt keeps hubs prominent without dwarfing everything else
      sizes[i] = 2.5 + Math.sqrt(Math.min(nodes[i].signal + nodes[i].degree, 60)) * 1.6
    }

    const pointGeo = new THREE.BufferGeometry()
    pointGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    pointGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    pointGeo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    const pointMat = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
    })
    this.points = new THREE.Points(pointGeo, pointMat)
    this.scene.add(this.points)

    const m = links.length
    const linePos = new Float32Array(m * 6)
    const lineCol = new Float32Array(m * 6)
    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3))
    lineGeo.setAttribute('color', new THREE.BufferAttribute(lineCol, 3))
    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
    })
    this.lines = new THREE.LineSegments(lineGeo, lineMat)
    this.scene.add(this.lines)

    this.simulation = forceSimulation(nodes as object[], 3)
      .force(
        'link',
        forceLink(links as object[])
          .id((d: RenderNode) => d.id)
          .distance(34),
      )
      .force('charge', forceManyBody().strength(-45).distanceMax(600))
      .force('center', forceCenter(0, 0, 0))
      .alphaDecay(0.035)
      .stop()

    this.applyColors()
  }

  setColorFns(nodeFn: (n: RenderNode) => Rgb, linkFn: (l: RenderLink) => Rgb): void {
    this.nodeColorFn = nodeFn
    this.linkColorFn = linkFn
    this.applyColors()
  }

  /** One-off recolor of both buffers — cheap (two typed-array passes). */
  private applyColors(): void {
    if (!this.points || !this.lines) return
    const colorAttr = this.points.geometry.getAttribute('color') as THREE.BufferAttribute
    for (let i = 0; i < this.nodes.length; i++) {
      const [r, g, b] = this.nodeColorFn(this.nodes[i])
      colorAttr.setXYZ(i, r, g, b)
    }
    colorAttr.needsUpdate = true

    const lineAttr = this.lines.geometry.getAttribute('color') as THREE.BufferAttribute
    for (let i = 0; i < this.links.length; i++) {
      const [r, g, b] = this.linkColorFn(this.links[i])
      lineAttr.setXYZ(i * 2, r, g, b)
      lineAttr.setXYZ(i * 2 + 1, r, g, b)
    }
    lineAttr.needsUpdate = true
  }

  private syncPositions(): void {
    if (!this.points || !this.lines) return
    const posAttr = this.points.geometry.getAttribute('position') as THREE.BufferAttribute
    for (let i = 0; i < this.nodes.length; i++) {
      const nd = this.nodes[i]
      posAttr.setXYZ(i, nd.x ?? 0, nd.y ?? 0, nd.z ?? 0)
    }
    posAttr.needsUpdate = true
    this.points.geometry.computeBoundingSphere()

    const lineAttr = this.lines.geometry.getAttribute('position') as THREE.BufferAttribute
    for (let i = 0; i < this.links.length; i++) {
      const s = this.links[i].source as RenderNode
      const t = this.links[i].target as RenderNode
      lineAttr.setXYZ(i * 2, s.x ?? 0, s.y ?? 0, s.z ?? 0)
      lineAttr.setXYZ(i * 2 + 1, t.x ?? 0, t.y ?? 0, t.z ?? 0)
    }
    lineAttr.needsUpdate = true
  }

  flyTo(node: RenderNode): void {
    const target = new THREE.Vector3(node.x ?? 0, node.y ?? 0, node.z ?? 0)
    const dir = target.clone().sub(this.camera.position).normalize()
    const pos = target.clone().sub(dir.multiplyScalar(160))
    this.flyTarget = { pos, look: target, t: 0 }
  }

  pause(): void {
    this.paused = true
  }

  resume(): void {
    this.paused = false
  }

  dispose(): void {
    cancelAnimationFrame(this.rafId)
    this.simulation?.stop()
    window.removeEventListener('resize', this.handleResize)
    this.renderer.domElement.removeEventListener('pointermove', this.handlePointerMove)
    this.renderer.domElement.removeEventListener('click', this.handleClick)
    this.disposeGraphObjects()
    this.controls.dispose()
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }

  private disposeGraphObjects(): void {
    for (const obj of [this.points, this.lines]) {
      if (!obj) continue
      this.scene.remove(obj)
      obj.geometry.dispose()
      ;(obj.material as THREE.Material).dispose()
    }
    this.points = null
    this.lines = null
  }

  private handleResize = (): void => {
    const w = this.container.clientWidth || window.innerWidth
    const h = this.container.clientHeight || window.innerHeight
    this.renderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  private pickNode(event: PointerEvent | MouseEvent): number {
    if (!this.points) return -1
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const hits = this.raycaster.intersectObject(this.points)
    return hits.length ? (hits[0].index ?? -1) : -1
  }

  private handlePointerMove = (event: PointerEvent): void => {
    const idx = this.pickNode(event)
    if (idx !== this.hoverIndex) {
      this.hoverIndex = idx
      this.renderer.domElement.style.cursor = idx >= 0 ? 'pointer' : 'grab'
    }
    this.callbacks.onHover(idx >= 0 ? this.nodes[idx] : null, event.clientX, event.clientY)
  }

  private handleClick = (event: MouseEvent): void => {
    const idx = this.pickNode(event)
    this.callbacks.onNodeClick(idx >= 0 ? this.nodes[idx] : null)
  }

  private loop = (): void => {
    this.rafId = requestAnimationFrame(this.loop)
    if (this.paused) return

    const sim = this.simulation
    if (sim && sim.alpha() > 0.012) {
      // A couple of ticks per frame settles ~11K nodes in a few seconds
      // while the assembly stays visible and interactive.
      sim.tick()
      if (sim.alpha() > 0.2) sim.tick()
      this.syncPositions()
    }

    if (this.flyTarget) {
      this.flyTarget.t = Math.min(1, this.flyTarget.t + 0.03)
      const e = 1 - Math.pow(1 - this.flyTarget.t, 3)
      this.camera.position.lerp(this.flyTarget.pos, e * 0.2)
      this.controls.target.lerp(this.flyTarget.look, e * 0.2)
      if (this.flyTarget.t >= 1) this.flyTarget = null
    }

    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }
}
