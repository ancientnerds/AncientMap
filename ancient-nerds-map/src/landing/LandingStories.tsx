import { useState } from 'react'

import type { StoryTeaser } from '../types/anRoute'
import LazyImage from '../components/LazyImage'
import { fetchFeed, pickLeadAndRail } from './feedClient'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

export interface StoriesBlock {
  lead: StoryTeaser
  rail: StoryTeaser[]
  categories: string[]
}

interface Props {
  initial: StoriesBlock
  total: number
}

const PLACEHOLDER =
  'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><rect fill="%230a1a14" width="16" height="9"/></svg>'

function Badge({ category }: { category: string | null }) {
  if (!category) return null
  return <span className={`ll-badge ll-cat-${category}`}>{category}</span>
}

function Meter({ value }: { value: number | null }) {
  if (value == null) return null
  return (
    <span className="ll-sig" aria-label={`significance ${value} of 10`}>
      SIG <b>{value}</b>
      <span className="ll-meter">
        <i style={{ width: `${value * 10}%` }} />
      </span>
    </span>
  )
}

export function StoryLead({ story }: { story: StoryTeaser }) {
  // Both halves of the row are optional in the payload — an empty row would
  // be a bare gap above the headline.
  const hasMetaRow = Boolean(story.category) || story.significance != null
  return (
    <a className="ll-lead" href={story.path}>
      <span className="ll-img ll-img-16x9">
        <LazyImage src={story.screenshot_url ?? PLACEHOLDER} alt="" width={1280} height={720} fallbackSrc={PLACEHOLDER} />
      </span>
      <span className="ll-body">
        {hasMetaRow && (
          <span className="ll-meta-row">
            <Badge category={story.category} /> <Meter value={story.significance} />
          </span>
        )}
        <span className="ll-title">{story.headline}</span>
        <span className="ll-p">{story.summary}</span>
        <span className="ll-meta">
          <b>{story.channel}</b> · {story.sources} sources · <RelativeTime iso={story.created_at} />
          {story.site && (
            <>
              {' · '}
              <span className="ll-site">{story.site.name}{story.site.country ? ` · ${story.site.country}` : ''}</span>
            </>
          )}
        </span>
      </span>
    </a>
  )
}

export function StoryRow({ story }: { story: StoryTeaser }) {
  return (
    <a className="ll-row ll-row-thumb" href={story.path}>
      <span className="ll-img ll-img-16x9">
        <LazyImage src={story.screenshot_url ?? PLACEHOLDER} alt="" width={192} height={108} fallbackSrc={PLACEHOLDER} />
      </span>
      <span>
        <span className="ll-row-title">{story.headline}</span>
        <span className="ll-meta">
          {/* The feed does emit category-less stories; the separator only
              belongs there when the badge in front of it exists. */}
          {story.category && (
            <>
              <Badge category={story.category} />
              {' · '}
            </>
          )}
          SIG {story.significance ?? '–'} · {story.site ? story.site.name : story.channel} ·{' '}
          <RelativeTime iso={story.created_at} />
        </span>
      </span>
    </a>
  )
}

const PAGE = 7
const RAIL = 6
const MAX_LOADS = 2

export default function LandingStories({ initial, total }: Props) {
  const [category, setCategory] = useState<string | null>(null)
  const [lead, setLead] = useState(initial.lead)
  const [rail, setRail] = useState(initial.rail)
  const [loads, setLoads] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function applyChip(next: string | null) {
    if (next === category || busy) return
    setError(null)
    if (next === null) {
      setCategory(null)
      setLead(initial.lead)
      setRail(initial.rail)
      setLoads(0)
      return
    }
    setBusy(true)
    try {
      const { items } = await fetchFeed({ category: next, page: 1, pageSize: PAGE })
      if (items.length === 0) {
        setError(`no ${next} stories yet`)
        return
      }
      const picked = pickLeadAndRail(items)
      setCategory(next)
      setLead(picked.lead)
      setRail(picked.rail.slice(0, RAIL))
      setLoads(0)
    } catch {
      setError('feed unavailable')
    } finally {
      setBusy(false)
    }
  }

  async function loadMore() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const shown = new Set([lead.id, ...rail.map(r => r.id)])
      const { items } = await fetchFeed({ category, page: loads + 2, pageSize: RAIL })
      setRail(prev => [...prev, ...items.filter(i => !shown.has(i.id))])
      setLoads(n => n + 1)
    } catch {
      setError('feed unavailable')
    } finally {
      setBusy(false)
    }
  }

  const chips: (string | null)[] = [null, ...initial.categories]
  return (
    <section className="ll-section" id="stories-live" aria-labelledby="ll-fig-1">
      <SectionHead fig={1} name="stories, live" status={`${total.toLocaleString('en-US')} stories · newest first`} />
      <div className="ll-chips" role="group" aria-label="story categories">
        {chips.map(c => (
          <button key={c ?? 'all'} type="button" className="ll-chip" aria-pressed={c === category} onClick={() => applyChip(c)}>
            {c ?? 'all'}
          </button>
        ))}
        {error && <span className="ll-error ll-meta" role="status">{error}</span>}
      </div>
      <div className="ll-two">
        <StoryLead story={lead} />
        <div className="ll-rail">
          {rail.map(s => (
            <StoryRow key={s.id} story={s} />
          ))}
        </div>
      </div>
      {loads < MAX_LOADS ? (
        <button type="button" className="ll-more" onClick={loadMore} disabled={busy}>
          {busy ? 'loading…' : 'load more'}
        </button>
      ) : null}
      <div className="ll-foot">
        <span>lead = highest significance of the last 48h · rail = newest</span>
        <a href="/news.html">all stories →</a>
      </div>
    </section>
  )
}
