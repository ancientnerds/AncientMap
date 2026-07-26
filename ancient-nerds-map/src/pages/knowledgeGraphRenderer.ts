/**
 * GPU-friendly 2D map renderer for the knowledge graph.
 *
 * Follows the globe's rendering recipe (sitesRenderer.ts): ALL nodes live in
 * ONE THREE.Points object (BufferGeometry + point shader) — one draw call
 * regardless of graph size. The view is a flat, pannable/zoomable map:
 * every node class clusters on its own labeled "island" (cluster forces pull
 * points toward per-kind centers; link forces act only as a weak kinship
 * pull). Edges are NOT rendered globally — only the focused node's own
 * connections appear, which keeps the picture readable and screenshottable.
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from 'd3-force-3d'

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
}

export interface RenderLink {
  source: string | RenderNode
  target: string | RenderNode
  kind: string
}

export interface ClusterDef {
  kind: string
  label: string
  x: number
  y: number
  color: string
}

type Rgb = [number, number, number]

interface Callbacks {
  onNodeClick: (node: RenderNode | null) => void
  onHover: (node: RenderNode | null, x: number, y: number) => void
}

const VERTEX_SHADER = `
attribute float size;
uniform float uZoom;
varying vec3 vColor;
void main() {
  vColor = color;
  gl_PointSize = size * uZoom;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

const FRAGMENT_SHADER = `
varying vec3 vColor;
void main() {
  vec2 c = gl_PointCoord - vec2(0.5);
  float d = length(c);
  if (d > 0.5) discard;
  float alpha = smoothstep(0.5, 0.3, d);
  gl_FragColor = vec4(vColor, alpha * 0.95);
}
`

export class KnowledgeGraphRenderer {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.OrthographicCamera
  private controls: OrbitControls
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()

  private nodes: RenderNode[] = []
  private links: RenderLink[] = []
  private points: THREE.Points | null = null
  private focusLines: THREE.LineSegments | null = null
  private pointMat: THREE.ShaderMaterial | null = null
  private simulation: ReturnType<typeof forceSimulation> | null = null

  private nodeColorFn: (n: RenderNode) => Rgb = () => [0.5, 0.7, 0.8]

  private clusterDefs: ClusterDef[] = []
  private clusterLabels: HTMLDivElement[] = []

  private rafId = 0
  private paused = false
  private hoverIndex = -1
  private flyTarget: { look: THREE.Vector3; zoom: number; t: number } | null = null

  constructor(
    private container: HTMLElement,
    private callbacks: Callbacks,
  ) {
    // preserveDrawingBuffer keeps the canvas readable for PNG export.
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setClearColor('#0a1a1f')
    container.appendChild(this.renderer.domElement)

    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100)
    this.camera.position.set(0, 0, 10)
    this.camera.zoom = 0.9

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableRotate = false
    this.controls.screenSpacePanning = true
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.1
    this.controls.minZoom = 0.2
    this.controls.maxZoom = 20
    this.controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY }
    this.controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_PAN }

    this.raycaster.params.Points = { threshold: 8 }

    this.handleResize()
    window.addEventListener('resize', this.handleResize)
    this.renderer.domElement.addEventListener('pointermove', this.handlePointerMove)
    this.renderer.domElement.addEventListener('click', this.handleClick)

    this.loop()
  }

  setData(nodes: RenderNode[], links: RenderLink[], clusters: ClusterDef[]): void {
    this.simulation?.stop()
    this.disposeGraphObjects()
    this.nodes = nodes
    this.links = links
    this.clusterDefs = clusters
    this.hoverIndex = -1
    this.rebuildClusterLabels()

    const clusterByKind = new Map(clusters.map((c) => [c.kind, c]))
    // Seed positions near the cluster centers so the islands form instantly.
    for (const nd of nodes) {
      const c = clusterByKind.get(nd.kind)
      nd.x = (c?.x ?? 0) + (Math.random() - 0.5) * 120
      nd.y = (c?.y ?? 0) + (Math.random() - 0.5) * 120
    }

    const n = nodes.length
    const positions = new Float32Array(n * 3)
    const colors = new Float32Array(n * 3)
    const sizes = new Float32Array(n)
    for (let i = 0; i < n; i++) {
      sizes[i] = 2.2 + Math.sqrt(Math.min(nodes[i].signal + nodes[i].degree, 60)) * 1.4
    }

    const pointGeo = new THREE.BufferGeometry()
    pointGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    pointGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    pointGeo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    this.pointMat = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      uniforms: { uZoom: { value: this.camera.zoom } },
      vertexColors: true,
      transparent: true,
      depthWrite: false,
    })
    this.points = new THREE.Points(pointGeo, this.pointMat)
    this.scene.add(this.points)

    // 2D simulation: strong pull to the kind's island, weak link kinship,
    // mild repulsion + collision so islands spread into readable blobs.
    this.simulation = forceSimulation(nodes as object[], 2)
      .force(
        'x',
        forceX((d: RenderNode) => clusterByKind.get(d.kind)?.x ?? 0).strength(0.12),
      )
      .force(
        'y',
        forceY((d: RenderNode) => clusterByKind.get(d.kind)?.y ?? 0).strength(0.12),
      )
      .force(
        'link',
        forceLink(links as object[])
          .id((d: RenderNode) => d.id)
          .strength(0.02)
          .distance(60),
      )
      .force('charge', forceManyBody().strength(-4).distanceMax(160))
      .force(
        'collide',
        forceCollide((d: RenderNode) => 2.5 + Math.sqrt(Math.min(d.signal + d.degree, 60))),
      )
      .alphaDecay(0.05)
      .stop()

    this.applyColors()
    this.syncPositions()
  }

  setColorFn(nodeFn: (n: RenderNode) => Rgb): void {
    this.nodeColorFn = nodeFn
    this.applyColors()
  }

  /** Render ONLY the focused node's own edges (or clear with null). */
  showFocusEdges(nodeId: string | null): void {
    if (this.focusLines) {
      this.scene.remove(this.focusLines)
      this.focusLines.geometry.dispose()
      ;(this.focusLines.material as THREE.Material).dispose()
      this.focusLines = null
    }
    if (!nodeId) return
    const segments: number[] = []
    for (const l of this.links) {
      const s = l.source as RenderNode
      const t = l.target as RenderNode
      if (typeof s !== 'object' || typeof t !== 'object') continue
      if (s.id !== nodeId && t.id !== nodeId) continue
      segments.push(s.x ?? 0, s.y ?? 0, 0, t.x ?? 0, t.y ?? 0, 0)
    }
    if (!segments.length) return
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(segments), 3))
    const mat = new THREE.LineBasicMaterial({
      color: '#ffd700',
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
    })
    this.focusLines = new THREE.LineSegments(geo, mat)
    this.scene.add(this.focusLines)
  }

  screenshot(): string {
    this.renderer.render(this.scene, this.camera)
    return this.renderer.domElement.toDataURL('image/png')
  }

  flyTo(node: RenderNode): void {
    this.flyTarget = {
      look: new THREE.Vector3(node.x ?? 0, node.y ?? 0, 0),
      zoom: Math.max(this.camera.zoom, 4),
      t: 0,
    }
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
    for (const el of this.clusterLabels) el.remove()
    this.clusterLabels = []
    this.controls.dispose()
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }

  private disposeGraphObjects(): void {
    this.showFocusEdges(null)
    if (this.points) {
      this.scene.remove(this.points)
      this.points.geometry.dispose()
      ;(this.points.material as THREE.Material).dispose()
      this.points = null
      this.pointMat = null
    }
  }

  private rebuildClusterLabels(): void {
    for (const el of this.clusterLabels) el.remove()
    this.clusterLabels = this.clusterDefs.map((c) => {
      const el = document.createElement('div')
      el.className = 'kg-cluster-label'
      el.textContent = c.label
      el.style.color = c.color
      this.container.appendChild(el)
      return el
    })
  }

  private updateClusterLabels(): void {
    const w = this.container.clientWidth
    const h = this.container.clientHeight
    const v = new THREE.Vector3()
    this.clusterDefs.forEach((c, i) => {
      const el = this.clusterLabels[i]
      if (!el) return
      v.set(c.x, c.y, 0).project(this.camera)
      el.style.transform = `translate(-50%, -50%) translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px)`
      el.style.opacity = this.camera.zoom > 6 ? '0' : '1'
    })
  }

  private handleResize = (): void => {
    const w = this.container.clientWidth || window.innerWidth
    const h = this.container.clientHeight || window.innerHeight
    this.renderer.setSize(w, h)
    this.camera.left = -w / 2
    this.camera.right = w / 2
    this.camera.top = h / 2
    this.camera.bottom = -h / 2
    this.camera.updateProjectionMatrix()
  }

  private pickNode(event: PointerEvent | MouseEvent): number {
    if (!this.points) return -1
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    // Screen-space pick radius must shrink as we zoom in.
    this.raycaster.params.Points = { threshold: Math.max(2, 10 / this.camera.zoom) }
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

  private applyColors(): void {
    if (!this.points) return
    const colorAttr = this.points.geometry.getAttribute('color') as THREE.BufferAttribute
    for (let i = 0; i < this.nodes.length; i++) {
      const [r, g, b] = this.nodeColorFn(this.nodes[i])
      colorAttr.setXYZ(i, r, g, b)
    }
    colorAttr.needsUpdate = true
  }

  private syncPositions(): void {
    if (!this.points) return
    const posAttr = this.points.geometry.getAttribute('position') as THREE.BufferAttribute
    for (let i = 0; i < this.nodes.length; i++) {
      posAttr.setXYZ(i, this.nodes[i].x ?? 0, this.nodes[i].y ?? 0, 0)
    }
    posAttr.needsUpdate = true
    this.points.geometry.computeBoundingSphere()
  }

  private loop = (): void => {
    this.rafId = requestAnimationFrame(this.loop)
    if (this.paused) return

    const sim = this.simulation
    if (sim && sim.alpha() > 0.02) {
      sim.tick()
      if (sim.alpha() > 0.3) sim.tick()
      this.syncPositions()
    }

    if (this.flyTarget) {
      this.flyTarget.t = Math.min(1, this.flyTarget.t + 0.04)
      this.controls.target.lerp(this.flyTarget.look, 0.15)
      this.camera.position.x = this.controls.target.x
      this.camera.position.y = this.controls.target.y
      this.camera.zoom += (this.flyTarget.zoom - this.camera.zoom) * 0.12
      this.camera.updateProjectionMatrix()
      if (this.flyTarget.t >= 1) this.flyTarget = null
    }

    if (this.pointMat) this.pointMat.uniforms.uZoom.value = Math.sqrt(this.camera.zoom)
    this.controls.update()
    this.updateClusterLabels()
    this.renderer.render(this.scene, this.camera)
  }
}
