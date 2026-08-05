import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PageHeader from '../components/layout/PageHeader'
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
  connection: '#5eead4', // thinking layer: curator-mined link candidates
  hypothesis: '#fbbf24', // thinking layer: falsifiable hypotheses
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
// Outcome tints for hypothesis nodes (spec §7): green once confirmed, grey
// once refuted (dead end). Open hypotheses keep the base amber.
const OUTCOME_CONFIRMED_RGB: Rgb = hexToRgb('#4ade80')
const OUTCOME_REFUTED_RGB: Rgb = hexToRgb('#94a3b8')

/**
 * A node's class color before status/focus effects — shared by the initial
 * fill and focus recoloring so the two paths never drift apart.
 */
function nodeBaseRgb(node: RenderNode): Rgb {
  if (node.kind === 'hypothesis') {
    if (node.outcome === 'confirmed') return OUTCOME_CONFIRMED_RGB
    if (node.outcome === 'refuted') return OUTCOME_REFUTED_RGB
  }
  return KIND_RGB[node.kind] ?? DEFAULT_RGB
}

// Terminal kinds ride along as companions of their node (a video always
// brings its channel, a site its epoch/country) but are never expanded —
// hubs cannot fan out.
const TERMINAL_KINDS = new Set(['period', 'country', 'culture', 'channel', 'empire'])

// Layer toggles — each chip switches a group of node classes.
const LAYERS: Record<string, string[]> = {
  structure: ['period', 'empire', 'country', 'culture'],
  sites: ['site'],
  content: ['story', 'video', 'channel', 'journal', 'person'],
  research: ['paper', 'topic', 'entity'],
  thinking: ['connection', 'hypothesis'],
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
  // Directed adjacency: out = src->dst, in = dst->src.
  const adjOutRef = useRef<Map<string, Set<string>>>(new Map())
  const adjInRef = useRef<Map<string, Set<string>>>(new Map())
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

  // Build the directed adjacency indexes once per dataset (for focus mode).
  useEffect(() => {
    if (!data) return
    const out = new Map<string, Set<string>>()
    const inc = new Map<string, Set<string>>()
    for (const e of data.edges) {
      if (!out.has(e.src)) out.set(e.src, new Set())
      if (!inc.has(e.dst)) inc.set(e.dst, new Set())
      out.get(e.src)!.add(e.dst)
      inc.get(e.dst)!.add(e.src)
    }
    adjOutRef.current = out
    adjInRef.current = inc
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

  /**
   * Focus expansion with two anti-flood rules:
   * - TERMINAL kinds (channel, epoch, country, culture, empire) join as
   *   companions of their node IMMEDIATELY (a video brings its creator on
   *   the same level) but are never expanded — hubs cannot fan out
   * - no sibling fan-out: a node never expands into neighbors of the same
   *   kind it was reached from (a video does not flood back into all its
   *   other stories, a story not into its other sites)
   */
  const computeFocusSet = useCallback(
    (startId: string): Set<string> => {
      const nodeById = nodeByIdRef.current
      const neighborsOf = (id: string): string[] => [
        ...(adjOutRef.current.get(id) ?? []),
        ...(adjInRef.current.get(id) ?? []),
      ]
      const set = new Set<string>()
      const addWithCompanions = (id: string) => {
        set.add(id)
        for (const nbId of neighborsOf(id)) {
          if (set.has(nbId)) continue
          const nb = nodeByIdRef.current.get(nbId)
          if (nb && TERMINAL_KINDS.has(nb.kind) && activeKinds.has(nb.kind)) set.add(nbId)
        }
      }
      addWithCompanions(startId)
      let ring: { id: string; from: string | null }[] = [{ id: startId, from: null }]
      for (let level = 0; level < depth; level++) {
        const next: { id: string; from: string }[] = []
        for (const { id, from } of ring) {
          const self = nodeById.get(id)
          if (!self) continue
          for (const nbId of neighborsOf(id)) {
            if (set.has(nbId)) continue
            const nb = nodeById.get(nbId)
            if (!nb || !activeKinds.has(nb.kind)) continue
            if (TERMINAL_KINDS.has(nb.kind)) continue // only ever a companion
            if (from && nb.kind === from) continue // anti-sibling
            addWithCompanions(nbId)
            next.push({ id: nbId, from: self.kind })
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
      const base = nodeBaseRgb(n)
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
    const nodeById = new Map(nodes.map((n) => [n.id, n]))
    nodeByIdRef.current = nodeById

    // Derive each node's sub-cluster key from its edges: sites group by
    // country, videos by channel, stories by their video's channel,
    // topics/entities/people by the paper that surfaced them. The islands
    // render these as archipelago blobs.
    const outByKind = new Map<string, Map<string, string>>()
    const paperOf = new Map<string, string>()
    for (const e of data.edges) {
      const src = nodeById.get(e.src)
      const dst = nodeById.get(e.dst)
      if (!src || !dst) continue
      let m = outByKind.get(src.id)
      if (!m) {
        m = new Map()
        outByKind.set(src.id, m)
      }
      if (!m.has(dst.kind)) m.set(dst.kind, dst.label)
      if (src.kind === 'paper') {
        if (!paperOf.has(dst.id)) paperOf.set(dst.id, src.label)
      }
    }
    const videoChannel = new Map<string, string>()
    for (const n of nodes) {
      if (n.kind === 'video') {
        const ch = outByKind.get(n.id)?.get('channel')
        if (ch) videoChannel.set(n.label, ch)
      }
    }
    for (const n of nodes) {
      if (n.kind === 'site') n.group = outByKind.get(n.id)?.get('country')
      else if (n.kind === 'video') n.group = outByKind.get(n.id)?.get('channel')
      else if (n.kind === 'story') {
        const video = outByKind.get(n.id)?.get('video')
        n.group = video ? videoChannel.get(video) : undefined
      } else if (n.kind === 'topic' || n.kind === 'entity' || n.kind === 'person') {
        n.group = paperOf.get(n.id)
      }
    }

    // Similarity orders so thematically close sub-blobs become spatial
    // neighbors: countries west→east by their sites' mean longitude, other
    // groups chained by shared-neighbor Jaccard similarity.
    const groupOrders: Record<string, string[]> = {}
    const countryHint = new Map<string, number>()
    for (const n of nodes) {
      if (n.kind === 'country' && n.order_hint != null) countryHint.set(n.label, n.order_hint)
    }
    groupOrders.site = [
      ...new Set(nodes.filter((n) => n.kind === 'site' && n.group).map((n) => n.group!)),
    ].sort((a, b) => (countryHint.get(a) ?? 999) - (countryHint.get(b) ?? 999))

    const neighborsOf = (id: string): Set<string> => {
      const out = adjOutRef.current.get(id)
      const inc = adjInRef.current.get(id)
      const all = new Set<string>(out ?? [])
      for (const x of inc ?? []) all.add(x)
      return all
    }
    const chainFor = (kind: string): string[] => {
      const sigs = new Map<string, Set<string>>()
      for (const n of nodes) {
        if (n.kind !== kind || !n.group) continue
        let s = sigs.get(n.group)
        if (!s) {
          s = new Set()
          sigs.set(n.group, s)
        }
        for (const nb of neighborsOf(n.id)) s.add(nb)
      }
      const keys = [...sigs.keys()]
      if (keys.length <= 2) return keys
      const jaccard = (a: Set<string>, b: Set<string>) => {
        let inter = 0
        for (const x of a) if (b.has(x)) inter++
        return inter / (a.size + b.size - inter || 1)
      }
      keys.sort((a, b) => sigs.get(b)!.size - sigs.get(a)!.size)
      const chain = [keys.shift()!]
      while (keys.length) {
        const last = sigs.get(chain[chain.length - 1])!
        let bestIdx = 0
        let bestSim = -1
        keys.forEach((k, i) => {
          const sim = jaccard(last, sigs.get(k)!)
          if (sim > bestSim) {
            bestSim = sim
            bestIdx = i
          }
        })
        chain.push(keys.splice(bestIdx, 1)[0])
      }
      return chain
    }
    for (const kind of ['video', 'story', 'topic', 'entity', 'person']) {
      groupOrders[kind] = chainFor(kind)
    }

    const links: RenderLink[] = data.edges.map((e) => ({
      source: e.src,
      target: e.dst,
      kind: e.kind,
    }))
    renderer.setFullData(nodes, links, CLUSTERS, groupOrders)
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
      <PageHeader currentPage="knowledge">
        <a href="/knowledge.html" className="page-header-title">
          Knowledge
        </a>
      </PageHeader>
      <div className="kg-toolbar">
        <p className="kg-subtitle">
          {data ? `${data.total_nodes.toLocaleString()} nodes` : '…'} · {counts.explored} explored
          · {counts.frontier} frontier topics
        </p>
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
      </div>

      <div className="kg-stage">
        {error && (
          <div className="kg-empty">
            <h2>The graph is unreachable right now.</h2>
            <p>Please try again in a moment.</p>
          </div>
        )}
        <div ref={containerRef} className="kg-canvas" />
      </div>

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
