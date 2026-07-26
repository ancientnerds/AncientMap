import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph'
import HamburgerNav from '../components/layout/HamburgerNav'
import { useCurrentResearch } from '../hooks/useCurrentResearch'
import { navigateGlobeToSite } from '../utils/globeNavigation'
import './KnowledgePage.css'

interface GraphNode {
  id: string
  label: string
  kind: string
  status: string
  signal: number
  degree: number
  paper_slug: string | null
  site_id: string | null
}

interface GraphEdge {
  src: string
  dst: string
  kind: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  total_nodes: number
}

// Layout engine adds coordinates once the simulation runs.
type KgNode = GraphNode & { x?: number; y?: number; z?: number }

// Color by node CLASS; status drives the pulse (frontier dim/bright,
// researching red) on top.
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

// Layer toggles — each chip switches a group of node classes.
const LAYERS: Record<string, string[]> = {
  structure: ['period', 'empire', 'country', 'culture'],
  sites: ['site'],
  content: ['story', 'video', 'channel', 'journal', 'person'],
  research: ['paper', 'topic', 'entity'],
}

function layerOf(kind: string): string | null {
  for (const [layer, kinds] of Object.entries(LAYERS)) {
    if (kinds.includes(kind)) return layer
  }
  return null
}

export default function KnowledgePage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraph3DInstance | null>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState(false)
  // Content (stories+videos, ~5K nodes) is opt-in — first paint stays light.
  const [activeLayers, setActiveLayers] = useState<Set<string>>(
    new Set(['structure', 'sites', 'research']),
  )
  const [search, setSearch] = useState('')
  const [focused, setFocused] = useState<KgNode | null>(null)
  const current = useCurrentResearch()

  // Focus state lives in refs so the color/link accessors always read the
  // latest values without re-creating the graph.
  const focusRef = useRef<{ id: string; neighbors: Set<string> } | null>(null)
  const adjacencyRef = useRef<Map<string, Set<string>>>(new Map())

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

  const clearFocus = useCallback(() => {
    focusRef.current = null
    setFocused(null)
  }, [])

  // Re-assigning color accessors makes the lib re-evaluate EVERY node
  // material — at 11K nodes that must only happen on focus/layer changes,
  // never on a timer (the original 900ms pulse melted GPUs).
  const applyColors = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    const focus = focusRef.current
    graph.nodeColor((n) => {
      const node = n as KgNode
      if (focus && node.id !== focus.id && !focus.neighbors.has(node.id)) {
        return 'rgba(80, 100, 110, 0.12)'
      }
      if (node.status === 'researching') return '#c02023'
      const base = KIND_COLORS[node.kind] ?? '#667788'
      if (node.status === 'frontier') return `${base}99`
      return base
    })
    graph.linkColor((l) => {
      if (!focus) return 'rgba(122, 180, 200, 0.22)'
      const src = typeof l.source === 'object' ? (l.source as KgNode).id : String(l.source)
      const dst = typeof l.target === 'object' ? (l.target as KgNode).id : String(l.target)
      return src === focus.id || dst === focus.id
        ? 'rgba(255, 215, 0, 0.6)'
        : 'rgba(80, 100, 110, 0.04)'
    })
  }, [])

  // Initialize / update the 3D graph when data or the layer set changes.
  useEffect(() => {
    if (!containerRef.current || !data || data.nodes.length === 0) return
    const activeKinds = new Set(
      Object.entries(LAYERS)
        .filter(([layer]) => activeLayers.has(layer))
        .flatMap(([, kinds]) => kinds),
    )
    const nodes = data.nodes.filter((n) => {
      const layer = layerOf(n.kind)
      return layer === null || activeKinds.has(n.kind)
    })
    const ids = new Set(nodes.map((n) => n.id))
    const links = data.edges
      .filter((e) => ids.has(e.src) && ids.has(e.dst))
      .map((e) => ({ source: e.src, target: e.dst, kind: e.kind }))

    let graph = graphRef.current
    if (!graph) {
      // Accessor callbacks are typed against the base NodeObject upstream —
      // narrow to KgNode inside each callback instead of fighting the
      // library's chain generics.
      const g = new ForceGraph3D(containerRef.current)
      g.backgroundColor('#0a1a1f')
      g.showNavInfo(false)
      // ~10K nodes: low-poly spheres + a fast-settling, bounded simulation.
      g.nodeResolution(4)
      g.warmupTicks(0)
      g.cooldownTicks(120)
      g.d3AlphaDecay(0.05)
      g.nodeVal((n) => {
        const node = n as KgNode
        return 1 + Math.min(node.signal + node.degree, 40)
      })
      g.nodeOpacity(0.9)
      g.nodeLabel((n) => {
        const node = n as KgNode
        const hint =
          node.status === 'frontier'
            ? '<br/><i>Theo will research this</i>'
            : node.status === 'researching'
              ? '<br/><i>Theo is researching this right now</i>'
              : ''
        return `<div class="kg-tooltip"><b>${node.label}</b><br/><span>${node.kind}</span>${hint}</div>`
      })
      // linkWidth MUST stay 0: any positive width renders every edge as a
      // cylinder mesh (~20K meshes) instead of a cheap GL line.
      g.linkWidth(0)
      g.onNodeClick((n) => {
        // Focus mode: dim everything outside the 1-hop neighborhood and
        // show the info card. Navigation moved to the card's actions —
        // direct click-through is wrong at this node density.
        const node = n as KgNode
        focusRef.current = {
          id: node.id,
          neighbors: adjacencyRef.current.get(node.id) ?? new Set(),
        }
        setFocused(node)
        applyColors()
      })
      g.onBackgroundClick(() => {
        clearFocus()
        applyColors()
      })
      graphRef.current = g
      graph = g
    }
    // Fresh copies — the layout engine mutates node objects (x/y/z).
    graph.graphData({ nodes: nodes.map((n) => ({ ...n })), links })
    applyColors()
  }, [data, activeLayers, applyColors, clearFocus])

  // Stop the 60fps render loop while the tab is hidden.
  useEffect(() => {
    const onVisibility = () => {
      const graph = graphRef.current
      if (!graph) return
      if (document.hidden) graph.pauseAnimation()
      else graph.resumeAnimation()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  const flyToMatch = useCallback(() => {
    const graph = graphRef.current
    const term = search.trim().toLowerCase()
    if (!graph || !term) return
    const match = graph
      .graphData()
      .nodes.find((n) => ((n as KgNode).label || '').toLowerCase().includes(term)) as
      | KgNode
      | undefined
    if (!match || match.x === undefined) return
    const dist = 120
    const ratio = 1 + dist / Math.hypot(match.x, match.y ?? 0, match.z ?? 0)
    graph.cameraPosition(
      { x: match.x * ratio, y: (match.y ?? 0) * ratio, z: (match.z ?? 0) * ratio },
      { x: match.x, y: match.y ?? 0, z: match.z ?? 0 },
      1200,
    )
  }, [search])

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
            {data ? `${data.nodes.length.toLocaleString()} nodes` : '…'} · {counts.explored}{' '}
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
        </div>
      </header>

      {error && (
        <div className="kg-empty">
          <h2>The graph is unreachable right now.</h2>
          <p>Please try again in a moment.</p>
        </div>
      )}
      {!error && data && data.nodes.length === 0 && (
        <div className="kg-empty">
          <h2>The knowledge graph is just being born.</h2>
          <p>
            Theo&apos;s permanent researcher is mapping the ancient world — the first nodes appear
            with the next published paper. Watch the live research on the{' '}
            <a href="/theo.html">Research page</a>.
          </p>
        </div>
      )}
      <div ref={containerRef} className="kg-canvas" />

      {focused && (
        <div className="kg-infocard">
          <button
            className="kg-infocard-close"
            onClick={() => {
              clearFocus()
              applyColors()
            }}
            aria-label="Close"
          >
            ×
          </button>
          <span className="kg-infocard-kind" style={{ color: KIND_COLORS[focused.kind] ?? '#7ab4c8' }}>
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
              <button onClick={() => navigateGlobeToSite(focused.site_id!)}>
                Show on globe →
              </button>
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
