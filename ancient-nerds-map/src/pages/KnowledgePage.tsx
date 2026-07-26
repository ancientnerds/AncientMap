import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import HamburgerNav from '../components/layout/HamburgerNav'
import { useCurrentResearch } from '../hooks/useCurrentResearch'
import { navigateGlobeToSite } from '../utils/globeNavigation'
import {
  KnowledgeGraphRenderer,
  type ClusterDef,
  type RenderLink,
  type RenderNode,
} from './knowledgeGraphRenderer'
import './KnowledgePage.css'

interface GraphEdge {
  src: string
  dst: string
  kind: string
}

interface GraphData {
  nodes: RenderNode[]
  edges: GraphEdge[]
  total_nodes: number
}

// Color by node CLASS; focus mode dims everything outside the neighborhood.
const KIND_COLORS: Record<string, string> = {
  paper: '#ffd700',
  topic: '#3aa8c2',
  entity: '#a78bfa',
  site: '#22c55e',
  period: '#8b5cf6',
  empire: '#e67e22',
  country: '#64748b',
  culture: '#14b8a6',
  person: '#ec4899',
  story: '#93c5fd',
  video: '#ef4444',
  channel: '#f97316',
  journal: '#eab308',
}

type Rgb = [number, number, number]

function hexToRgb(hex: string): Rgb {
  const v = parseInt(hex.slice(1), 16)
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255]
}

const KIND_RGB: Record<string, Rgb> = Object.fromEntries(
  Object.entries(KIND_COLORS).map(([k, c]) => [k, hexToRgb(c)]),
) as Record<string, Rgb>
const DEFAULT_RGB: Rgb = [0.4, 0.47, 0.53]
const RESEARCHING_RGB: Rgb = hexToRgb('#c02023')
const DIM_RGB: Rgb = [0.16, 0.2, 0.22]

// Layer toggles — each chip switches a group of node classes.
const LAYERS: Record<string, string[]> = {
  structure: ['period', 'empire', 'country', 'culture'],
  sites: ['site'],
  content: ['story', 'video', 'channel', 'journal', 'person'],
  research: ['paper', 'topic', 'entity'],
}

// The map: research sits at the center (Theo's brain), everything else forms
// labeled islands around it. World units; the view starts zoomed to fit.
const CLUSTERS: ClusterDef[] = [
  { kind: 'paper', label: 'Papers', x: 0, y: 40, color: KIND_COLORS.paper },
  { kind: 'topic', label: 'Topics', x: 60, y: 340, color: KIND_COLORS.topic },
  { kind: 'entity', label: 'Entities', x: -340, y: 200, color: KIND_COLORS.entity },
  { kind: 'site', label: 'Sites', x: 950, y: 0, color: KIND_COLORS.site },
  { kind: 'period', label: 'Epochs', x: -850, y: 380, color: KIND_COLORS.period },
  { kind: 'empire', label: 'Empires', x: -1000, y: 0, color: KIND_COLORS.empire },
  { kind: 'country', label: 'Countries', x: -850, y: -380, color: KIND_COLORS.country },
  { kind: 'culture', label: 'Cultures', x: -450, y: -560, color: KIND_COLORS.culture },
  { kind: 'story', label: 'Stories', x: 480, y: 580, color: KIND_COLORS.story },
  { kind: 'video', label: 'Videos', x: 1000, y: 720, color: KIND_COLORS.video },
  { kind: 'channel', label: 'Channels', x: 1400, y: 500, color: KIND_COLORS.channel },
  { kind: 'journal', label: 'Journals', x: 480, y: -580, color: KIND_COLORS.journal },
  { kind: 'person', label: 'People', x: 0, y: -640, color: KIND_COLORS.person },
]

export default function KnowledgePage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<KnowledgeGraphRenderer | null>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState(false)
  // All layers on by default — instant toggles make this cheap now.
  const [activeLayers, setActiveLayers] = useState<Set<string>>(new Set(Object.keys(LAYERS)))
  const [search, setSearch] = useState('')
  const [focused, setFocused] = useState<RenderNode | null>(null)
  // How many hops of connections to reveal around the focused bubble.
  const [depth, setDepth] = useState(1)
  const [hover, setHover] = useState<{ node: RenderNode; x: number; y: number } | null>(null)
  const current = useCurrentResearch()

  const focusRef = useRef<{ id: string; set: Set<string> } | null>(null)
  const adjacencyRef = useRef<Map<string, Set<string>>>(new Map())
  const nodeByIdRef = useRef<Map<string, RenderNode>>(new Map())

  useEffect(() => {
    fetch('/api/v1/graph')
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch(() => setError(true))
  }, [])

  // Build the adjacency index once per dataset (for focus mode).
  useEffect(() => {
    if (!data) return
    const adj = new Map<string, Set<string>>()
    for (const e of data.edges) {
      if (!adj.has(e.src)) adj.set(e.src, new Set())
      if (!adj.has(e.dst)) adj.set(e.dst, new Set())
      adj.get(e.src)!.add(e.dst)
      adj.get(e.dst)!.add(e.src)
    }
    adjacencyRef.current = adj
  }, [data])

  const activeKinds = useMemo(
    () =>
      new Set(
        Object.entries(LAYERS)
          .filter(([layer]) => activeLayers.has(layer))
          .flatMap(([, kinds]) => kinds),
      ),
    [activeLayers],
  )

  /** BFS over the adjacency up to `depth` hops, restricted to visible kinds. */
  const computeFocusSet = useCallback(
    (startId: string): Set<string> => {
      const nodeById = nodeByIdRef.current
      const set = new Set<string>([startId])
      let ring = [startId]
      for (let level = 0; level < depth; level++) {
        const next: string[] = []
        for (const id of ring) {
          for (const nb of adjacencyRef.current.get(id) ?? []) {
            if (set.has(nb)) continue
            const node = nodeById.get(nb)
            if (!node || !activeKinds.has(node.kind)) continue
            set.add(nb)
            next.push(nb)
          }
        }
        ring = next
      }
      return set
    },
    [depth, activeKinds],
  )

  const applyColors = useCallback(() => {
    const renderer = rendererRef.current
    if (!renderer) return
    const focus = focusRef.current
    renderer.setColorFn((n) => {
      if (focus && !focus.set.has(n.id)) return DIM_RGB
      if (n.status === 'researching') return RESEARCHING_RGB
      const base = KIND_RGB[n.kind] ?? DEFAULT_RGB
      if (n.status === 'frontier') return [base[0] * 0.55, base[1] * 0.55, base[2] * 0.55]
      return base
    })
    renderer.showFocusEdges(focus ? focus.set : null)
    if (focus) {
      // Titles at the bubbles: the focused node + the most connected part
      // of its neighborhood (capped so a 5000-site epoch stays readable).
      const nodeById = nodeByIdRef.current
      const members = [...focus.set]
        .map((id) => nodeById.get(id))
        .filter((n): n is RenderNode => !!n)
        .sort((a, b) => b.signal + b.degree - (a.signal + a.degree))
      const focusedNode = nodeById.get(focus.id)
      const labeled = focusedNode
        ? [focusedNode, ...members.filter((n) => n.id !== focus.id)]
        : members
      renderer.setNodeLabels(labeled.slice(0, 60))
    } else {
      renderer.setNodeLabels([])
    }
  }, [])

  const focusNode = useCallback(
    (node: RenderNode | null) => {
      if (!node) {
        focusRef.current = null
        setFocused(null)
      } else {
        focusRef.current = { id: node.id, set: computeFocusSet(node.id) }
        setFocused(node)
      }
      applyColors()
    },
    [computeFocusSet, applyColors],
  )
  const focusNodeRef = useRef(focusNode)
  focusNodeRef.current = focusNode

  // Renderer lifecycle — created once, torn down on unmount.
  useEffect(() => {
    if (!containerRef.current) return
    const renderer = new KnowledgeGraphRenderer(containerRef.current, {
      onNodeClick: (node) => focusNodeRef.current(node),
      onHover: (node, x, y) => {
        setHover(node ? { node, x, y } : null)
      },
    })
    rendererRef.current = renderer
    const onVisibility = () => {
      if (document.hidden) renderer.pause()
      else renderer.resume()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      renderer.dispose()
      rendererRef.current = null
    }
  }, [])

  // Load the full dataset into the renderer ONCE — layer toggles afterwards
  // only flip vertex visibility (no re-simulation, no assembly animation).
  useEffect(() => {
    const renderer = rendererRef.current
    if (!renderer || !data || data.nodes.length === 0) return
    const nodes = data.nodes.map((n) => ({ ...n }))
    nodeByIdRef.current = new Map(nodes.map((n) => [n.id, n]))
    const links: RenderLink[] = data.edges.map((e) => ({
      source: e.src,
      target: e.dst,
      kind: e.kind,
    }))
    renderer.setFullData(nodes, links, CLUSTERS)
    applyColors()
  }, [data, applyColors])

  // Instant layer switching; drop the focus if its node just got hidden,
  // otherwise recompute the neighborhood against the new visible set.
  useEffect(() => {
    const renderer = rendererRef.current
    if (!renderer) return
    renderer.setVisibleKinds(activeKinds)
    const focus = focusRef.current
    if (focus) {
      const node = nodeByIdRef.current.get(focus.id)
      if (!node || !activeKinds.has(node.kind)) focusNodeRef.current(null)
      else focusNodeRef.current(node)
    }
  }, [activeKinds])

  // Depth changes re-expand the current focus.
  useEffect(() => {
    const focus = focusRef.current
    if (!focus) return
    const node = nodeByIdRef.current.get(focus.id)
    if (node) focusNodeRef.current(node)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depth])

  const takeScreenshot = useCallback(() => {
    const url = rendererRef.current?.screenshot()
    if (!url) return
    const a = document.createElement('a')
    a.href = url
    a.download = `ancient-nerds-knowledge-graph-${new Date().toISOString().slice(0, 10)}.png`
    a.click()
  }, [])

  const flyToMatch = useCallback(() => {
    const renderer = rendererRef.current
    const term = search.trim().toLowerCase()
    if (!renderer || !term || !data) return
    const match = data.nodes.find((n) => (n.label || '').toLowerCase().includes(term))
    if (match) renderer.flyTo(match)
  }, [search, data])

  const toggleLayer = useCallback((layer: string) => {
    setActiveLayers((prev) => {
      const next = new Set(prev)
      if (next.has(layer)) next.delete(layer)
      else next.add(layer)
      return next
    })
  }, [])

  const counts = useMemo(() => {
    if (!data) return { explored: 0, frontier: 0 }
    return {
      explored: data.nodes.filter((n) => n.status === 'explored').length,
      frontier: data.nodes.filter((n) => n.status === 'frontier').length,
    }
  }, [data])

  return (
    <div className="knowledge-page">
      <HamburgerNav currentPage="knowledge" />
      <header className="kg-header">
        <div className="kg-title-block">
          <h1>Knowledge Graph</h1>
          <p className="kg-subtitle">
            {data ? `${data.total_nodes.toLocaleString()} nodes` : '…'} · {counts.explored}{' '}
            explored · {counts.frontier} frontier topics
          </p>
        </div>
        {current?.running && (
          <div className="kg-live">
            <span className="kg-live-dot" />
            Theo is researching: <em>{current.running.question.slice(0, 90)}…</em>
          </div>
        )}
        <div className="kg-controls">
          <input
            className="kg-search"
            placeholder="Find anything…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && flyToMatch()}
          />
          {Object.keys(LAYERS).map((layer) => (
            <button
              key={layer}
              className={`kg-chip ${activeLayers.has(layer) ? 'active' : ''}`}
              onClick={() => toggleLayer(layer)}
            >
              {layer}
            </button>
          ))}
          <span className="kg-depth">
            depth
            {[1, 2, 3].map((d) => (
              <button
                key={d}
                className={`kg-chip kg-chip--depth ${depth === d ? 'active' : ''}`}
                onClick={() => setDepth(d)}
                title={`Show ${d} level${d > 1 ? 's' : ''} of connections`}
              >
                {d}
              </button>
            ))}
          </span>
          <button className="kg-chip" onClick={takeScreenshot} title="Save as PNG (8K)">
            📷
          </button>
        </div>
      </header>

      {error && (
        <div className="kg-empty">
          <h2>The graph is unreachable right now.</h2>
          <p>Please try again in a moment.</p>
        </div>
      )}
      <div ref={containerRef} className="kg-canvas" />

      {hover && !focused && (
        <div className="kg-tooltip kg-tooltip--floating" style={{ left: hover.x + 14, top: hover.y + 10 }}>
          <b>{hover.node.label}</b>
          <br />
          <span>{hover.node.kind}</span>
          {hover.node.status === 'frontier' && (
            <>
              <br />
              <i>Theo will research this</i>
            </>
          )}
          {hover.node.status === 'researching' && (
            <>
              <br />
              <i>Theo is researching this right now</i>
            </>
          )}
        </div>
      )}

      {focused && (
        <div className="kg-infocard">
          <button className="kg-infocard-close" onClick={() => focusNode(null)} aria-label="Close">
            ×
          </button>
          <span
            className="kg-infocard-kind"
            style={{ color: KIND_COLORS[focused.kind] ?? '#7ab4c8' }}
          >
            {focused.kind}
            {focused.status === 'frontier' ? ' · frontier' : ''}
            {focused.status === 'researching' ? ' · researching now' : ''}
          </span>
          <h3>{focused.label}</h3>
          <div className="kg-infocard-meta">{focused.degree} connections</div>
          <div className="kg-infocard-actions">
            {focused.kind === 'paper' && focused.paper_slug && (
              <a href={`/research.html?slug=${focused.paper_slug}`}>Read the paper →</a>
            )}
            {focused.site_id && (
              <button onClick={() => navigateGlobeToSite(focused.site_id!)}>Show on globe →</button>
            )}
            {focused.status === 'frontier' && (
              <span className="kg-infocard-hint">Theo will research this topic</span>
            )}
          </div>
        </div>
      )}

      <div className="kg-legend">
        {Object.entries(KIND_COLORS)
          .filter(([kind]) => ['site', 'paper', 'topic', 'story', 'period', 'person'].includes(kind))
          .map(([kind, color]) => (
            <span key={kind}>
              <i style={{ background: color }} /> {kind}
            </span>
          ))}
      </div>
    </div>
  )
}
