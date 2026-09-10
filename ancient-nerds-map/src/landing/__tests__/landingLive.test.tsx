/**
 * The landing sections render under Node without browser APIs — exactly
 * what the SSR sidecar does. Effects (relative time, the portal iframes,
 * feed refetch) do not run in renderToString, so the server output carries
 * absolute dates and no iframe at all.
 */
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '../../contexts/AuthContext'
import { storyPath } from '../../seo/meta'
import { SeoRoute } from '../../seo/registry'
import { RouteProvider } from '../../seo/RouteContext'
import { FIXTURES } from '../../seo/__tests__/fixtures'
import type { LandingRoute } from '../../types/anRoute'

function render(route: LandingRoute): string {
  return renderToString(
    <RouteProvider value={route}>
      <AuthProvider>
        <SeoRoute />
      </AuthProvider>
    </RouteProvider>,
  )
}

/** The three window bodies, in document order. */
function windows(html: string): string[] {
  return html.split('<div class="ll-window">').slice(1)
}

const STORIES = FIXTURES.landing.stories!.items
const JOURNALS = FIXTURES.landing.journals!.items
const PAPERS = FIXTURES.landing.papers!.items

describe('LandingLive', () => {
  const html = render(FIXTURES.landing)

  it('renders three h2 section labels in spec order', () => {
    const labels = [...html.matchAll(/<h2[^>]*class="ll-fig"[^>]*>(.*?)<\/h2>/g)].map(m => m[1])
    expect(labels).toHaveLength(3)
    expect(labels[0]).toContain('stories, live')
    expect(labels[1]).toContain('weekly journal')
    expect(labels[2]).toContain('research papers')
    expect(html).not.toContain('<h1')
  })

  it('links every item to its page', () => {
    for (const href of [
      ...STORIES.map(s => storyPath(s.headline, s.id)),
      ...JOURNALS.map(j => j.path),
      ...PAPERS.map(p => p.path),
    ]) {
      expect(html).toContain(`href="${href}"`)
    }
    expect(html).toContain('href="/news.html"')
    expect(html).toContain('href="/articles.html"')
    expect(html).toContain('href="/research/"')
  })

  it('renders absolute dates on the server, never "ago"', () => {
    expect(html).toContain('Sep 7')
    // Only the <time> elements may carry a date: RelativeTime switches to
    // "2h ago" in an effect, which renderToString never runs. Headlines are
    // exempt on purpose — real ones say "around 1000 years ago".
    const times = [...html.matchAll(/<time[^>]*>(.*?)<\/time>/g)].map(m => m[1])
    expect(times.length).toBeGreaterThan(0)
    for (const text of times) expect(text).not.toContain('ago')
  })

  it('formats the journal week from the literal ISO date, not the renderer timezone', () => {
    // The row's week_start is "2026-08-24T00:00:00" — zoneless. Going through
    // new Date() would render "Aug 23" wherever the renderer sits east of UTC
    // and desync server from client.
    expect(html).toContain('Aug 24 – Aug 30')
  })

  it('names every section landmark with its own fig heading', () => {
    const sections = [...html.matchAll(/<section\b[^>]*>/g)].map(m => m[0])
    expect(sections).toHaveLength(3)
    const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]))
    for (const tag of sections) {
      const labelled = /aria-labelledby="([^"]+)"/.exec(tag)
      expect(labelled, `no aria-labelledby on ${tag}`).not.toBeNull()
      expect(ids, tag).toContain(labelled![1])
    }
  })

  it('shows the Theo line', () => {
    expect(html).toContain('Theo is researching')
    expect(html).toContain('Water erosion evidence in the Osiris Shaft')
    // The start time follows the page rule: absolute now, relative after
    // mount — a <time> from RelativeTime, not a frozen "since Sep 9".
    const theoLine = /<a class="ll-theo"[\s\S]*?<\/a>/.exec(html)![0]
    expect(theoLine).toContain('started')
    expect(theoLine).toContain('<time')
  })

  it('drops the separator in front of a story without a category', () => {
    const [story] = STORIES
    const out = render({
      ...FIXTURES.landing,
      stories: { ...FIXTURES.landing.stories!, items: [{ ...story, news_category: null }] },
    })
    const row = out.slice(out.indexOf(`href="${storyPath(story.headline, story.id)}"`))
    const meta = /<span class="ll-meta">([\s\S]*?)<\/span>/.exec(row)
    expect(meta).not.toBeNull()
    const text = meta![1].replace(/<[^>]*>/g, '').replace(/<!-- -->/g, '').trim()
    expect(text.startsWith('·')).toBe(false)
    expect(text.startsWith('SIG')).toBe(true)
  })

  it('serves plain lazy <img>, never the JS-gated LazyImage', () => {
    // LazyImage starts on .lazy-image--hidden and unhides in React's onLoad
    // — an event that never fires for an image the browser finished before
    // hydration, and never at all for a crawler without JS.
    expect(html).not.toContain('lazy-image')
    expect(html).not.toContain('data:image/svg+xml')
    const imgs = [...html.matchAll(/<span class="ll-img[^"]*"><img\b[^>]*>/g)].map(m => m[0])
    for (const tag of imgs) {
      expect(tag, tag).toContain('loading="lazy"')
      expect(tag, tag).toContain('decoding="async"')
    }
    // Two of the three story rows — the story without a screenshot keeps its
    // empty aspect-ratio box. Journals and papers have no row image at all.
    expect(imgs).toHaveLength(2)
  })

  it('joins meta lines from the parts that exist, without a dangling separator', () => {
    const journals = FIXTURES.landing.journals!
    const papers = FIXTURES.landing.papers!
    const row = journals.items[1]
    const paperRow = papers.items[1]
    const out = render({
      ...FIXTURES.landing,
      journals: { ...journals, items: [{ ...row, week_start: null, week_end: null }] },
      papers: { ...papers, items: [{ ...paperRow, published_at: null, words: null }] },
    })
    const metaAfter = (href: string): string => {
      const tail = out.slice(out.indexOf(`href="${href}"`))
      const meta = /<span class="ll-meta">([\s\S]*?)<\/span>/.exec(tail)
      expect(meta, `no ll-meta after ${href}`).not.toBeNull()
      return meta![1].replace(/<[^>]*>/g, '').trim()
    }
    for (const text of [metaAfter(row.path), metaAfter(paperRow.path)]) {
      expect(text).not.toContain('· ·')
      expect(text.startsWith('·')).toBe(false)
      expect(text.endsWith('·')).toBe(false)
    }
    expect(metaAfter(row.path)).toBe(`No. ${row.id} · ${row.minutes} min`)
  })

  it('never prints undefined or null', () => {
    expect(html).not.toMatch(/undefined|null/)
  })

  it('drops the Theo line and whole sections when their data is null', () => {
    const bare: LandingRoute = {
      ...FIXTURES.landing,
      journals: null,
      papers: { ...FIXTURES.landing.papers!, theo: null },
    }
    const out = render(bare)
    expect(out).not.toContain('weekly journal')
    expect(out).not.toContain('Theo is researching')
  })
})

/**
 * Each window is a portal: the real page, scaled down, loaded lazily on
 * desktop after mount (2026-09-10, owner: "a kind of portal to the pages —
 * like a screenshot that shows the current state"). What the crawler gets is
 * the link list beside it and a plain link into the page — never an iframe,
 * which is why the first render carries none.
 */
describe('PagePortal', () => {
  const html = render(FIXTURES.landing)
  const pages = ['/news.html', '/articles.html', '/research/']

  it('frames each section in a NERV window titled after the page it shows', () => {
    expect([...html.matchAll(/class="ll-window"/g)]).toHaveLength(3)
    expect([...html.matchAll(/class="ll-window-bar"/g)]).toHaveLength(3)
    expect([...html.matchAll(/class="ll-window-main"/g)]).toHaveLength(3)
    for (const page of pages) {
      expect(html).toContain(`&gt;_ portal — <b>${page}</b>`)
    }
    // The bar's controls reuse the app's window buttons, not a second set.
    expect(html).toContain('class="popup-window-controls ll-window-controls"')
  })

  it('puts exactly one portal per window, pointed at the page of that window', () => {
    const panes = windows(html)
    expect(panes).toHaveLength(3)
    panes.forEach((pane, i) => {
      const portals = [...pane.matchAll(/<div class="ll-portal" data-src="([^"]+)"/g)]
      expect(portals, pages[i]).toHaveLength(1)
      expect(portals[0][1]).toBe(pages[i])
    })
  })

  it('renders no iframe on the server — the frame is a desktop-only effect', () => {
    expect(html).not.toContain('<iframe')
    const openLinks: [string, string][] = [
      ['Open stories', '/news.html'],
      ['Open journals', '/articles.html'],
      ['Open research library', '/research/'],
    ]
    for (const [label, src] of openLinks) {
      expect(html).toContain(`<a class="ll-portal-open" href="${src}">${label} ↗</a>`)
      expect(html).toContain(`live view of ${src}`)
    }
  })

  it('names the two window controls — their link text is an arrow glyph', () => {
    for (const label of [
      'Open stories',
      'Story archive',
      'Open journals',
      'Journal archive',
      'Open research library',
      'Research library',
    ]) {
      expect(html).toContain(`aria-label="${label}"`)
    }
    const btns = [...html.matchAll(/<a class="popup-window-btn"[^>]*>/g)].map(m => m[0])
    expect(btns).toHaveLength(6)
    for (const btn of btns) expect(btn, btn).toContain('aria-label=')
  })

  it('lists every item beside the portal as a plain link, no in-window swap', () => {
    const [stories, journals, papers] = windows(html)
    const rows = [...stories.matchAll(/<a class="ll-row ll-row-thumb" href="([^"]+)"([^>]*)>/g)]
    expect(rows.map(m => m[1])).toEqual(STORIES.map(s => storyPath(s.headline, s.id)))
    for (const row of rows) expect(row[2]).not.toContain('aria-current')
    expect([...journals.matchAll(/<a class="ll-row" href="([^"]+)"/g)].map(m => m[1])).toEqual(
      JOURNALS.map(j => j.path),
    )
    expect([...papers.matchAll(/<a class="ll-row" href="([^"]+)"/g)].map(m => m[1])).toEqual(
      PAPERS.map(p => p.path),
    )
  })

  it('runs no page article inside a window any more', () => {
    // The windows showed StoryArticle/JournalArticle/PaperArticle until the
    // portals replaced them; those components belong to their pages now.
    expect(html).not.toContain('story-title')
    expect(html).not.toContain('articles-reader')
    expect(html).not.toContain('theo-paper')
    expect(html).not.toContain('data-ai-generated')
    expect(html).not.toContain('ll-continue')
    expect(html).not.toContain('ll-toc')
    expect(html).not.toContain('ll-evidence')
  })
})
