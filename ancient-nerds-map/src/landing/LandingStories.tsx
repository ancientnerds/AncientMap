/**
 * The Stories section: a NERV window with a portal on /news.html.
 *
 * Not a teaser strip and not an article either (2026-09-10, owner: "I want
 * a kind of portal to the pages — like a screenshot that shows the current
 * state"). The window body is the live story page, scaled down; the column
 * beside it lists the stories as plain links, which is what a crawler and a
 * no-JS visitor get.
 *
 * The only client work left is the list: category chips refetch it from
 * /api/news/feed, "load more" appends the next page.
 */
import { useState } from 'react'

import { getNewsCategoryLabel } from '../components/news/significance'
import { storyPath } from '../seo/meta'
import type { LandingRoute, StoryTeaser } from '../types/anRoute'
import { fetchFeed, leadFirst } from './feedClient'
import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
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
  const [list, setList] = useState<StoryTeaser[]>(initial.items)
  const [loads, setLoads] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function applyChip(next: string | null) {
    if (next === category || busy) return
    setError(null)
    if (next === null) {
      setCategory(null)
      setList(initial.items)
      setLoads(0)
      return
    }
    setBusy(true)
    try {
      const items = await fetchFeed({ category: next, page: 1, pageSize: PAGE })
      if (items.length === 0) {
        setError(`no ${next} stories yet`)
        return
      }
      setCategory(next)
      setList(leadFirst(items).slice(0, RAIL + 1))
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
      const items = await fetchFeed({ category, page: loads + 2, pageSize: RAIL })
      setList(prev => [...prev, ...items.filter(i => !shown.has(i.id))])
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
            {c ? getNewsCategoryLabel(c) : 'All'}
          </button>
        ))}
        {/* Always mounted, usually empty: a live region that appears together
            with its text is ignored by some screen readers. */}
        <span className="ll-error ll-meta" role="status">{error}</span>
      </div>

      <LandingWindow
        title={
          <>
            {'>_ portal — '}
            <b>/news.html</b>
          </>
        }
        openHref="/news.html"
        openTitle="Open stories"
        archive={{ href: '/news-archive/', title: 'Story archive' }}
        listLabel="More stories"
        main={
          <PagePortal
            src="/news.html"
            title="Stories — live view"
            openHref="/news.html"
            openLabel="Open stories"
          />
        }
        list={
          <>
            {list.map(s => (
              <a key={s.id} className="ll-row ll-row-thumb" href={storyPath(s.headline, s.id)}>
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
          </>
        }
      />

      <div className="ll-foot">
        <span>lead = highest significance of the last 48h · list = newest</span>
        <a href="/news.html">all stories →</a>
      </div>
    </section>
  )
}
