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

const STATUS_COLORS: Record<string, string> = {
  explored: '#ffd700',
  researching: '#c02023',
  frontier: '#3aa8c2',
}

const KIND_FILTERS = ['topic', 'paper', 'site'] as const

export default function KnowledgePage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraph3DInstance | null>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState(false)
  const [kindFilter, setKindFilter] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const current = useCurrentResearch()

  useEffect(() => {
    fetch('/api/v1/graph')
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch(() => setError(true))
  }, [])

  // Initialize / update the 3D graph when data or the kind filter changes.
  useEffect(() => {
    if (!containerRef.current || !data || data.nodes.length === 0) return
    const nodes = data.nodes.filter((n) => !kindFilter || n.kind === kindFilter)
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
      g.nodeColor((n) => STATUS_COLORS[(n as KgNode).status] ?? '#667788')
      g.nodeVal((n) => {
        const node = n as KgNode
        return 1 + node.signal + node.degree
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
        return `<div class="kg-tooltip"><b>${node.label}</b><br/><span>${node.kind} · ${node.status}</span>${hint}</div>`
      })
      g.linkColor(() => 'rgba(122, 180, 200, 0.25)')
      g.linkWidth(0.5)
      g.onNodeClick((n) => {
        const node = n as KgNode
        if (node.kind === 'paper' && node.paper_slug) {
          window.location.href = `/research.html?slug=${node.paper_slug}`
        } else if (node.site_id) {
          navigateGlobeToSite(node.site_id)
        }
      })
      graphRef.current = g
      graph = g
    }
    // Fresh copies — the layout engine mutates node objects (x/y/z).
    graph.graphData({ nodes: nodes.map((n) => ({ ...n })), links })
  }, [data, kindFilter])

  // Slow pulse for frontier + researching nodes: re-assigning the color
  // accessor makes the lib re-evaluate node colors each tick.
  useEffect(() => {
    if (!data) return
    let bright = false
    const timer = setInterval(() => {
      bright = !bright
      graphRef.current?.nodeColor((n) => {
        const node = n as KgNode
        if (node.status === 'explored') return STATUS_COLORS.explored
        const base = STATUS_COLORS[node.status] ?? '#667788'
        return bright ? base : `${base}66`
      })
    }, 900)
    return () => clearInterval(timer)
  }, [data])

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
            {counts.explored} explored · {counts.frontier} frontier topics
            {data && data.total_nodes > data.nodes.length
              ? ` · showing top ${data.nodes.length} of ${data.total_nodes}`
              : ''}
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
            placeholder="Find a topic…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && flyToMatch()}
          />
          {KIND_FILTERS.map((kind) => (
            <button
              key={kind}
              className={`kg-chip ${kindFilter === kind ? 'active' : ''}`}
              onClick={() => setKindFilter(kindFilter === kind ? null : kind)}
            >
              {kind}
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
      <div className="kg-legend">
        <span>
          <i style={{ background: STATUS_COLORS.explored }} /> explored
        </span>
        <span>
          <i style={{ background: STATUS_COLORS.frontier }} /> frontier
        </span>
        <span>
          <i style={{ background: STATUS_COLORS.researching }} /> researching now
        </span>
      </div>
    </div>
  )
}
