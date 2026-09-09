/**
 * The Stories section: a NERV window running the story page.
 *
 * Not a teaser strip (2026-09-10, owner feedback "the stories preview is
 * stupid"). The payload carries whole StoryData objects, so the window body
 * is the very <StoryArticle> /news-archive/{slug} renders — headline, meta,
 * video still, body, key facts, site chips, sources, Art.-50 footnote — and
 * the list beside it swaps which story is in the window.
 *
 * Every list row is a real <a> to the story page. Swapping is an onClick
 * that preventDefaults a plain left click; crawlers, middle clicks and
 * ctrl-clicks get the link they came for, and the server renders the lead's
 * article, so the section is complete without JavaScript.
 */
import { useState, type MouseEvent } from 'react'

import StoryArticle from '../components/news/StoryArticle'
import { getNewsCategoryLabel } from '../components/news/significance'
import type { LandingRoute, StoryData } from '../types/anRoute'
import { fetchFeed, pickLeadAndRail, storyHref } from './feedClient'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

interface Props {
  initial: NonNullable<LandingRoute['stories']>
  total: number
}

const PAGE = 7
const RAIL = 6
const MAX_LOADS = 2

function Badge({ category }: { category: string | null }) {
  if (!category) return null
  return <span className="ll-badge">{getNewsCategoryLabel(category)}</span>
}

export default function LandingStories({ initial, total }: Props) {
  const [category, setCategory] = useState<string | null>(null)
  const [list, setList] = useState<StoryData[]>([initial.lead, ...initial.rail])
  const [active, setActive] = useState<StoryData>(initial.lead)
  const [loads, setLoads] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function applyChip(next: string | null) {
    if (next === category || busy) return
    setError(null)
    if (next === null) {
      setCategory(null)
      setList([initial.lead, ...initial.rail])
      setActive(initial.lead)
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
      setList([picked.lead, ...picked.rail.slice(0, RAIL)])
      setActive(picked.lead)
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
      const shown = new Set(list.map(s => s.id))
      const { items } = await fetchFeed({ category, page: loads + 2, pageSize: RAIL })
      setList(prev => [...prev, ...items.filter(i => !shown.has(i.id))])
      setLoads(n => n + 1)
    } catch {
      setError('feed unavailable')
    } finally {
      setBusy(false)
    }
  }

  /** Plain left click swaps the window; every modified click stays a link. */
  function swap(story: StoryData) {
    return (e: MouseEvent) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      e.preventDefault()
      setActive(story)
    }
  }

  const chips: (string | null)[] = [null, ...initial.categories]
  const activeHref = storyHref(active)
  return (
    <section className="ll-section" id="stories-live" aria-labelledby="ll-fig-1">
      <SectionHead fig={1} name="stories, live" status={`${total.toLocaleString('en-US')} stories · newest first`} />
      <div className="ll-chips" role="group" aria-label="story categories">
        {chips.map(c => (
          <button key={c ?? 'all'} type="button" className="ll-chip" aria-pressed={c === category} onClick={() => applyChip(c)}>
            {c ? getNewsCategoryLabel(c) : 'All'}
          </button>
        ))}
        {/* Always mounted, usually empty: a live region that appears together
            with its text is ignored by some screen readers. */}
        <span className="ll-error ll-meta" role="status">{error}</span>
      </div>

      <div className="ll-window">
        <div className="ll-window-bar">
          <span className="ll-window-title">
            {'>_ stories.log — '}
            <b>{active.headline}</b>
          </span>
          <span className="popup-window-controls ll-window-controls">
            <a className="popup-window-btn" href={activeHref} title="Open the full story">↗</a>
            <a className="popup-window-btn" href="/news-archive/" title="Story archive">≡</a>
          </span>
        </div>
        <div className="ll-window-body">
          <article className="ll-window-article">
            <StoryArticle story={active} headingLevel="h3" compact headlineHref={activeHref} />
          </article>
          <nav className="ll-window-list" aria-label="More stories">
            {list.map(s => (
              <a
                key={s.id}
                className="ll-row ll-row-thumb"
                href={storyHref(s)}
                aria-current={s.id === active.id ? 'true' : undefined}
                onClick={swap(s)}
              >
                {/* Plain <img>, never LazyImage: that one starts hidden and
                    unhides in React's onLoad, which never fires for an image
                    the browser already finished before hydration — and never
                    at all without JS. The empty span keeps the aspect-ratio
                    box for a story without a screenshot. */}
                <span className="ll-img ll-img-16x9">
                  {s.screenshot_url && (
                    <img src={s.screenshot_url} alt="" width={192} height={108} loading="lazy" decoding="async" />
                  )}
                </span>
                <span>
                  <span className="ll-row-title">{s.headline}</span>
                  <span className="ll-meta">
                    {/* The feed does emit category-less stories; the separator
                        only belongs there when the badge in front of it exists. */}
                    {s.news_category && (
                      <>
                        <Badge category={s.news_category} />
                        {' · '}
                      </>
                    )}
                    SIG {s.significance ?? '–'} · {s.site_name || s.channel_name} ·{' '}
                    <RelativeTime iso={s.published_at} />
                  </span>
                </span>
              </a>
            ))}
            {loads < MAX_LOADS ? (
              <button type="button" className="ll-more" onClick={loadMore} disabled={busy}>
                {busy ? 'loading…' : 'load more'}
              </button>
            ) : null}
          </nav>
        </div>
      </div>

      <div className="ll-foot">
        <span>lead = highest significance of the last 48h · list = newest</span>
        <a href="/news.html">all stories →</a>
      </div>
    </section>
  )
}
