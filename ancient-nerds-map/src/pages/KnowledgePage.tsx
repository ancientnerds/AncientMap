import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import HamburgerNav from '../components/layout/HamburgerNav'
import { useCurrentResearch } from '../hooks/useCurrentResearch'
import { navigateGlobeToSite } from '../utils/globeNavigation'
import {
  KnowledgeGraphRenderer,
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
const LINK_RGB: Rgb = [0.18, 0.32, 0.38]
const LINK_FOCUS_RGB: Rgb = [1.0, 0.84, 0.0]
const LINK_DIM_RGB: Rgb = [0.06, 0.08, 0.09]

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
  const rendererRef = useRef<KnowledgeGraphRenderer | null>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState(false)
  // The graph opens as Theo's brain — heavier layers are one chip away.
  const [activeLayers, setActiveLayers] = useState<Set<string>>(new Set(['research']))
  const [search, setSearch] = useState('')
  const [focused, setFocused] = useState<RenderNode | null>(null)
  const [hover, setHover] = useState<{ node: RenderNode; x: number; y: number } | null>(null)
  const current = useCurrentResearch()

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

  const applyColors = useCallback(() => {
    const renderer = rendererRef.current
    if (!renderer) return
    const focus = focusRef.current
    renderer.setColorFns(
      (n) => {
        if (focus && n.id !== focus.id && !focus.neighbors.has(n.id)) return DIM_RGB
        if (n.status === 'researching') return RESEARCHING_RGB
        const base = KIND_RGB[n.kind] ?? DEFAULT_RGB
        if (n.status === 'frontier') return [base[0] * 0.55, base[1] * 0.55, base[2] * 0.55]
        return base
      },
      (l) => {
        if (!focus) return LINK_RGB
        const src = typeof l.source === 'object' ? l.source.id : String(l.source)
        const dst = typeof l.target === 'object' ? l.target.id : String(l.target)
        return src === focus.id || dst === focus.id ? LINK_FOCUS_RGB : LINK_DIM_RGB
      },
    )
  }, [])

  const clearFocus = useCallback(() => {
    focusRef.current = null
    setFocused(null)
  }, [])

  // Renderer lifecycle — created once, torn down on unmount.
  useEffect(() => {
    if (!containerRef.current) return
    const renderer = new KnowledgeGraphRenderer(containerRef.current, {
      onNodeClick: (node) => {
        if (!node) {
          clearFocus()
        } else {
          focusRef.current = {
            id: node.id,
            neighbors: adjacencyRef.current.get(node.id) ?? new Set(),
          }
          setFocused(node)
        }
        applyColors()
      },
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
  }, [applyColors, clearFocus])

  // Feed data into the renderer when the dataset or layer set changes.
  useEffect(() => {
    const renderer = rendererRef.current
    if (!renderer || !data || data.nodes.length === 0) return
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
    const links: RenderLink[] = data.edges
      .filter((e) => ids.has(e.src) && ids.has(e.dst))
      .map((e) => ({ source: e.src, target: e.dst, kind: e.kind }))
    // Fresh copies — the simulation mutates node objects (x/y/z).
    renderer.setData(
      nodes.map((n) => ({ ...n })),
      links,
    )
    clearFocus()
    applyColors()
  }, [data, activeLayers, applyColors, clearFocus])

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
