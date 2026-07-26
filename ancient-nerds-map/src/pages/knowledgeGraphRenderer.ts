/**
 * GPU-friendly 2D map renderer for the knowledge graph.
 *
 * Globe recipe: ALL nodes in ONE THREE.Points draw call. The layout is
 * simulated ONCE for the full dataset; layer toggles only flip a per-vertex
 * visibility attribute (no re-simulation, no assembly animation). Edges are
 * rendered only for the focused neighborhood (configurable depth), and the
 * focused neighborhood gets DOM title labels at the bubbles.
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

export interface RenderNode {
  id: string
  label: string
  kind: string
  status: string
  signal: number
  degree: number
  paper_slug: string | null
  site_id: string | null
  /** Sub-cluster key within the island (country, channel, source paper, …). */
  group?: string
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
attribute float aVisible;
uniform float uZoom;
varying vec3 vColor;
varying float vVisible;
void main() {
  vColor = color;
  vVisible = aVisible;
  gl_PointSize = size * uZoom;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

const FRAGMENT_SHADER = `
varying vec3 vColor;
varying float vVisible;
void main() {
  if (vVisible < 0.5) discard;
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
  private visibleFlags: Float32Array = new Float32Array(0)
  private points: THREE.Points | null = null
  private focusLines: THREE.LineSegments | null = null
  private pointMat: THREE.ShaderMaterial | null = null

  private nodeColorFn: (n: RenderNode) => Rgb = () => [0.5, 0.7, 0.8]

  private clusterDefs: ClusterDef[] = []
  private clusterLabels: HTMLDivElement[] = []
  private visibleKinds: Set<string> | null = null

  private labeledNodes: RenderNode[] = []
  private nodeLabelEls: HTMLDivElement[] = []
  // Per-label declutter verdict from the last frame (mirrored in screenshots).
  private labelKeep: boolean[] = []

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

    this.handleResize()
    window.addEventListener('resize', this.handleResize)
    this.renderer.domElement.addEventListener('pointerdown', this.handlePointerDown)
    this.renderer.domElement.addEventListener('pointermove', this.handlePointerMove)
    this.renderer.domElement.addEventListener('click', this.handleClick)

    this.loop()
  }

  /**
   * Load the FULL dataset once. The simulation runs over every node exactly
   * one time; later layer toggles only flip visibility flags.
   */
  setFullData(nodes: RenderNode[], links: RenderLink[], clusters: ClusterDef[]): void {
    this.disposeGraphObjects()
    this.nodes = nodes
    this.links = links
    this.clusterDefs = clusters
    this.hoverIndex = -1
    this.rebuildClusterLabels()

    // Deterministic layout, computed analytically in one pass (no force
    // simulation, no assembly animation, identical result on every load).
    // Each island packs its nodes' sub-groups (country, channel, source
    // paper — provided by the page via node.group) as an archipelago of
    // blobs; within every blob a phyllotaxis spiral puts the biggest
    // bubbles at the center. Groups with < 4 members merge into a rest blob.
    const clusterByKind = new Map(clusters.map((c) => [c.kind, c]))
    const byKind = new Map<string, RenderNode[]>()
    for (const nd of nodes) {
      const bucket = byKind.get(nd.kind)
      if (bucket) bucket.push(nd)
      else byKind.set(nd.kind, [nd])
    }
    const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))
    const SPACING = 4.4
    const packSpiral = (members: RenderNode[], cx: number, cy: number) => {
      members.sort((a, b) => b.signal + b.degree - (a.signal + a.degree))
      members.forEach((nd, i) => {
        const r = SPACING * Math.sqrt(i)
        const a = i * GOLDEN_ANGLE
        nd.x = cx + r * Math.cos(a)
        nd.y = cy + r * Math.sin(a)
      })
    }
    for (const [kind, members] of byKind) {
      const c = clusterByKind.get(kind)
      const cx = c?.x ?? 0
      const cy = c?.y ?? 0

      const byGroup = new Map<string, RenderNode[]>()
      for (const nd of members) {
        const key = nd.group ?? ''
        const bucket = byGroup.get(key)
        if (bucket) bucket.push(nd)
        else byGroup.set(key, [nd])
      }
      // Merge dust groups into the rest blob.
      const rest = byGroup.get('') ?? []
      for (const [key, bucket] of [...byGroup]) {
        if (key !== '' && bucket.length < 4) {
          rest.push(...bucket)
          byGroup.delete(key)
        }
      }
      if (rest.length) byGroup.set('', rest)

      if (byGroup.size <= 1) {
        packSpiral(members, cx, cy)
        continue
      }

      // Greedy circle packing of the sub-blobs: biggest at the island
      // center, each next blob walks outward along its golden-angle ray
      // until it clears everything already placed.
      const groups = [...byGroup.values()].sort((a, b) => b.length - a.length)
      const placed: { x: number; y: number; r: number }[] = []
      groups.forEach((bucket, gi) => {
        const radius = SPACING * Math.sqrt(bucket.length) + 14
        let gx = cx
        let gy = cy
        if (gi > 0) {
          const angle = gi * GOLDEN_ANGLE
          let dist = placed[0].r + radius
          for (;;) {
            gx = cx + dist * Math.cos(angle)
            gy = cy + dist * Math.sin(angle)
            const collides = placed.some(
              (p) => Math.hypot(gx - p.x, gy - p.y) < p.r + radius + 6,
            )
            if (!collides) break
            dist += 8
          }
        }
        placed.push({ x: gx, y: gy, r: radius })
        packSpiral(bucket, gx, gy)
      })
    }

    // Resolve link endpoints to node objects (no forceLink does it for us).
    const nodeById = new Map(nodes.map((nd) => [nd.id, nd]))
    for (const l of links) {
      if (typeof l.source === 'string') l.source = nodeById.get(l.source) ?? l.source
      if (typeof l.target === 'string') l.target = nodeById.get(l.target) ?? l.target
    }

    const n = nodes.length
    const positions = new Float32Array(n * 3)
    const colors = new Float32Array(n * 3)
    const sizes = new Float32Array(n)
    this.visibleFlags = new Float32Array(n).fill(1)
    const anchorKinds = new Set(['period', 'empire', 'country', 'culture'])
    for (let i = 0; i < n; i++) {
      const size = 2.2 + Math.sqrt(Math.min(nodes[i].signal + nodes[i].degree, 60)) * 1.4
      // Structural anchors (9 epochs, 46 empires, ...) are few but carry
      // thousands of connections — a size floor keeps their islands legible.
      sizes[i] = anchorKinds.has(nodes[i].kind) ? Math.max(size, 9) : size
    }

    const pointGeo = new THREE.BufferGeometry()
    pointGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    pointGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    pointGeo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    pointGeo.setAttribute('aVisible', new THREE.BufferAttribute(this.visibleFlags, 1))
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

    this.applyColors()
    this.syncPositions()
  }

  /** Flip per-vertex visibility — instant, no re-simulation, no animation. */
  setVisibleKinds(kinds: Set<string> | null): void {
    this.visibleKinds = kinds
    if (!this.points) return
    for (let i = 0; i < this.nodes.length; i++) {
      this.visibleFlags[i] = !kinds || kinds.has(this.nodes[i].kind) ? 1 : 0
    }
    const attr = this.points.geometry.getAttribute('aVisible') as THREE.BufferAttribute
    attr.needsUpdate = true
  }

  setColorFn(nodeFn: (n: RenderNode) => Rgb): void {
    this.nodeColorFn = nodeFn
    this.applyColors()
  }

  /**
   * Render every edge whose BOTH endpoints are inside the focus set.
   * Each line carries its endpoints' CLUSTER colors — WebGL interpolates
   * between the two vertices, so a site→story edge fades green→light blue.
   */
  showFocusEdges(focusSet: Set<string> | null): void {
    if (this.focusLines) {
      this.scene.remove(this.focusLines)
      this.focusLines.geometry.dispose()
      ;(this.focusLines.material as THREE.Material).dispose()
      this.focusLines = null
    }
    if (!focusSet || focusSet.size === 0) return

    const kindColor = new Map<string, THREE.Color>(
      this.clusterDefs.map((c) => [c.kind, new THREE.Color(c.color)]),
    )
    const fallback = new THREE.Color('#7ab4c8')

    const segments: number[] = []
    const colors: number[] = []
    for (const l of this.links) {
      const s = l.source as RenderNode
      const t = l.target as RenderNode
      if (typeof s !== 'object' || typeof t !== 'object') continue
      if (!focusSet.has(s.id) || !focusSet.has(t.id)) continue
      if (this.visibleKinds && (!this.visibleKinds.has(s.kind) || !this.visibleKinds.has(t.kind)))
        continue
      segments.push(s.x ?? 0, s.y ?? 0, 0, t.x ?? 0, t.y ?? 0, 0)
      const sc = kindColor.get(s.kind) ?? fallback
      const tc = kindColor.get(t.kind) ?? fallback
      colors.push(sc.r, sc.g, sc.b, tc.r, tc.g, tc.b)
    }
    if (!segments.length) return
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(segments), 3))
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(colors), 3))
    const mat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.6,
      depthWrite: false,
    })
    this.focusLines = new THREE.LineSegments(geo, mat)
    this.scene.add(this.focusLines)
  }

  /** Title labels rendered AT the bubbles (focused node + its neighborhood). */
  setNodeLabels(nodes: RenderNode[]): void {
    for (const el of this.nodeLabelEls) el.remove()
    this.labeledNodes = nodes
    this.labelKeep = nodes.map(() => true)
    this.nodeLabelEls = nodes.map((nd) => {
      const el = document.createElement('div')
      el.className = 'kg-node-label'
      el.textContent = nd.label.length > 42 ? `${nd.label.slice(0, 40)}…` : nd.label
      this.container.appendChild(el)
      return el
    })
  }

  /**
   * High-resolution PNG export (default 7680px wide = 8K). Cluster titles and
   * active node labels are composited INTO the bitmap.
   */
  screenshot(targetWidth = 7680): string {
    const prevW = this.container.clientWidth || window.innerWidth
    const prevH = this.container.clientHeight || window.innerHeight
    const prevRatio = this.renderer.getPixelRatio()
    const scale = targetWidth / prevW
    const w = targetWidth
    const h = Math.round(prevH * scale)

    this.renderer.setPixelRatio(1)
    this.renderer.setSize(w, h, false)
    if (this.pointMat) {
      this.pointMat.uniforms.uZoom.value = Math.sqrt(this.camera.zoom) * scale
    }
    this.renderer.render(this.scene, this.camera)

    const out = document.createElement('canvas')
    out.width = w
    out.height = h
    const ctx = out.getContext('2d')!
    ctx.drawImage(this.renderer.domElement, 0, 0, w, h)

    const v = new THREE.Vector3()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.shadowColor = 'rgba(0, 0, 0, 0.9)'
    ctx.shadowBlur = Math.round(w * 0.004)
    ctx.font = `600 ${Math.round(w * 0.011)}px Orbitron, sans-serif`
    for (const c of this.clusterDefs) {
      if (this.visibleKinds && !this.visibleKinds.has(c.kind)) continue
      v.set(c.x, c.y, 0).project(this.camera)
      if (v.x < -1 || v.x > 1 || v.y < -1 || v.y > 1) continue
      ctx.fillStyle = c.color
      ctx.fillText(c.label.toUpperCase(), ((v.x + 1) / 2) * w, ((1 - v.y) / 2) * h)
    }
    ctx.font = `500 ${Math.round(w * 0.005)}px "JetBrains Mono", monospace`
    ctx.fillStyle = '#e0e0e0'
    this.labeledNodes.forEach((nd, i) => {
      if (!this.labelKeep[i]) return // same declutter verdict as the live view
      v.set(nd.x ?? 0, nd.y ?? 0, 0).project(this.camera)
      if (v.x < -1 || v.x > 1 || v.y < -1 || v.y > 1) return
      ctx.fillText(
        nd.label.length > 42 ? `${nd.label.slice(0, 40)}…` : nd.label,
        ((v.x + 1) / 2) * w,
        ((1 - v.y) / 2) * h - Math.round(w * 0.006),
      )
    })

    this.renderer.setPixelRatio(prevRatio)
    this.renderer.setSize(prevW, prevH, false)
    if (this.pointMat) this.pointMat.uniforms.uZoom.value = Math.sqrt(this.camera.zoom)
    this.renderer.render(this.scene, this.camera)

    return out.toDataURL('image/png')
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
    window.removeEventListener('resize', this.handleResize)
    this.renderer.domElement.removeEventListener('pointerdown', this.handlePointerDown)
    this.renderer.domElement.removeEventListener('pointermove', this.handlePointerMove)
    this.renderer.domElement.removeEventListener('click', this.handleClick)
    this.disposeGraphObjects()
    for (const el of this.clusterLabels) el.remove()
    this.clusterLabels = []
    for (const el of this.nodeLabelEls) el.remove()
    this.nodeLabelEls = []
    this.controls.dispose()
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }

  private disposeGraphObjects(): void {
    this.showFocusEdges(null)
    this.setNodeLabels([])
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

  private projectToScreen(x: number, y: number, v: THREE.Vector3): [number, number] {
    const w = this.container.clientWidth
    const h = this.container.clientHeight
    v.set(x, y, 0).project(this.camera)
    return [((v.x + 1) / 2) * w, ((1 - v.y) / 2) * h]
  }

  private updateLabels(): void {
    const v = new THREE.Vector3()
    this.clusterDefs.forEach((c, i) => {
      const el = this.clusterLabels[i]
      if (!el) return
      const [px, py] = this.projectToScreen(c.x, c.y, v)
      el.style.transform = `translate(-50%, -50%) translate(${px}px, ${py}px)`
      const hidden =
        this.camera.zoom > 6 || (this.visibleKinds !== null && !this.visibleKinds.has(c.kind))
      el.style.opacity = hidden ? '0' : '1'
    })
    // Greedy screen-space decluttering, borrowed from the globe's label
    // system: labeledNodes arrive priority-sorted (focused node first, then
    // by bubble size), so the bigger bubble always wins a collision.
    const keptRects: { x1: number; y1: number; x2: number; y2: number }[] = []
    this.labeledNodes.forEach((nd, i) => {
      const el = this.nodeLabelEls[i]
      if (!el) return
      const [px, py] = this.projectToScreen(nd.x ?? 0, nd.y ?? 0, v)
      el.style.transform = `translate(-50%, -130%) translate(${px}px, ${py}px)`
      const textLen = (el.textContent ?? '').length
      const w = textLen * 6.2 + 8
      const h = 16
      const cy = py - 18
      const rect = { x1: px - w / 2, y1: cy - h / 2, x2: px + w / 2, y2: cy + h / 2 }
      const collides = keptRects.some(
        (r) => rect.x1 < r.x2 && rect.x2 > r.x1 && rect.y1 < r.y2 && rect.y2 > r.y1,
      )
      if (collides) {
        el.style.opacity = '0'
        this.labelKeep[i] = false
      } else {
        keptRects.push(rect)
        el.style.opacity = '1'
        this.labelKeep[i] = true
      }
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
    this.raycaster.params.Points = { threshold: Math.max(2, 10 / this.camera.zoom) }
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const hits = this.raycaster.intersectObject(this.points)
    // Skip vertices hidden by the current layer set.
    for (const hit of hits) {
      const idx = hit.index ?? -1
      if (idx >= 0 && this.visibleFlags[idx] > 0.5) return idx
    }
    return -1
  }

  private downPos: { x: number; y: number } | null = null

  private handlePointerDown = (event: PointerEvent): void => {
    this.downPos = { x: event.clientX, y: event.clientY }
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
    // A pan gesture ends with a click event too — only treat it as a click
    // (and possibly a deselect) when the pointer barely moved.
    if (this.downPos) {
      const dx = event.clientX - this.downPos.x
      const dy = event.clientY - this.downPos.y
      if (dx * dx + dy * dy > 25) return
    }
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
    this.updateLabels()
    this.renderer.render(this.scene, this.camera)
  }
}
