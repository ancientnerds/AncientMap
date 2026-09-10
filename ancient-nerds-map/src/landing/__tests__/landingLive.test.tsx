/**
 * The landing sections render under Node without browser APIs — exactly
 * what the SSR sidecar does. Effects (relative time, the portal iframes) do
 * not run in renderToString, so the server output carries absolute dates and
 * no iframe at all.
 */
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '../../contexts/AuthContext'
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

/** The window bodies, in document order. */
function windows(html: string): string[] {
  return html.split('<div class="ll-window">').slice(1)
}

/**
 * The four portals in document order (Stories, Journal, Papers, Sites): the
 * page each one is on, what its frame shows, its poster, its CTA and the
 * window buttons. Stories and Sites have an archive of their own; the
 * journal hub and the research library ARE their archive.
 */
const SECTIONS = [
  { page: '/news.html', view: '/news.html', poster: '/data/previews/news.jpg', label: 'Open stories', buttons: ['/news.html', '/news-archive/'] },
  { page: '/articles.html', view: '/articles.html', poster: '/data/previews/articles.jpg', label: 'Open journals', buttons: ['/articles.html'] },
  { page: '/research/', view: '/research/', poster: '/data/previews/research.jpg', label: 'Open research library', buttons: ['/research/'] },
  { page: '/search.html', view: '/search.html?random', poster: '/data/previews/search.jpg', label: 'Open site search', buttons: ['/search.html', '/sites/'] },
]

describe('LandingLive', () => {
  const html = render(FIXTURES.landing)

  it('renders four h2 section labels in spec order', () => {
    const labels = [...html.matchAll(/<h2[^>]*class="ll-fig"[^>]*>(.*?)<\/h2>/g)].map(m => m[1])
    expect(labels).toHaveLength(4)
    expect(labels[0]).toContain('stories, live')
    expect(labels[1]).toContain('weekly journal')
    expect(labels[2]).toContain('research papers')
    expect(labels[3]).toContain('site search')
    expect(html).not.toContain('<h1')
  })

  it('counts every section in its status line', () => {
    expect(html).toContain('3,189 stories · newest first')
    expect(html).toContain('23 issues · every Sunday')
    expect(html).toContain('24 public · CC BY 4.0 · by Theo')
    expect(html).toContain('1,759,673 sites · 30 sources')
  })

  it('links the page of every section', () => {
    for (const href of ['/news.html', '/news-archive/', '/articles.html', '/research/', '/search.html', '/sites/']) {
      expect(html).toContain(`href="${href}"`)
    }
  })

  it('names every section landmark with its own fig heading', () => {
    const sections = [...html.matchAll(/<section\b[^>]*>/g)].map(m => m[0])
    expect(sections).toHaveLength(4)
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

  it('renders absolute dates on the server, never "ago"', () => {
    const times = [...html.matchAll(/<time[^>]*>(.*?)<\/time>/g)].map(m => m[1])
    expect(times.length).toBeGreaterThan(0)
    for (const text of times) expect(text).not.toContain('ago')
  })

  it('runs no list beside a portal and no gallery under one', () => {
    // Owner, 2026-09-10: "Why do we still have the list of stories, journals
    // and research papers on the right side?" The page in the frame IS the
    // list; a second one said the same thing twice. A day later the same
    // verdict hit the paper cards: "The research paper examples should be
    // inside the portal, not below it" — they live on /research/, which is
    // exactly the page the third portal shows.
    for (const gone of [
      'll-window-list',
      'll-row',
      'll-chip',
      'll-more',
      'll-badge',
      'll-img',
      'll-gallery',
      'theo-public-card',
      'theo-public-grid',
    ]) {
      expect(html, gone).not.toContain(gone)
    }
  })

  it('never prints undefined or null', () => {
    expect(html).not.toMatch(/undefined|null/)
  })

  it('drops the Theo line and whole sections when their data is null', () => {
    const out = render({
      ...FIXTURES.landing,
      journals: null,
      papers: { ...FIXTURES.landing.papers!, theo: null },
    })
    expect(out).not.toContain('weekly journal')
    expect(out).not.toContain('Theo is researching')
    // Stories and Sites have no source of their own: their counts are in
    // stats, which is the whole payload, so both sections are always there.
    expect(out).toContain('stories, live')
    expect(out).toContain('site search')
  })
})

/**
 * Each window is a portal: a poster screenshot of the real page, with the
 * live frame scaled down on top of it — but only on hover-capable desktops
 * (2026-09-10). The frame is decoration — the one interactive thing is the
 * link that covers it and carries the CTA.
 */
describe('PagePortal', () => {
  const html = render(FIXTURES.landing)

  it('frames each section in a NERV window titled after the page it shows', () => {
    expect([...html.matchAll(/class="ll-window"/g)]).toHaveLength(4)
    expect([...html.matchAll(/class="ll-window-bar"/g)]).toHaveLength(4)
    expect([...html.matchAll(/class="ll-window-body"/g)]).toHaveLength(4)
    for (const { page } of SECTIONS) {
      // The bare page, never the ?random view the frame opens.
      expect(html).toContain(`&gt;_ portal — <b>${page}</b>`)
    }
    // The bar's controls reuse the app's window buttons, not a second set.
    expect(html).toContain('class="popup-window-controls ll-window-controls"')
  })

  it('puts exactly one portal per window, pointed at the view of that window', () => {
    const panes = windows(html)
    expect(panes).toHaveLength(4)
    panes.forEach((pane, i) => {
      const portals = [...pane.matchAll(/<div class="ll-portal" data-src="([^"]+)"/g)]
      expect(portals, SECTIONS[i].page).toHaveLength(1)
      expect(portals[0][1]).toBe(SECTIONS[i].view)
    })
  })

  it('renders no iframe on the server — the frame is an effect', () => {
    expect(html).not.toContain('<iframe')
  })

  it('posters every portal with the screenshot of its own page', () => {
    // Owner, 2026-09-10: "On the phone everything flickers quite a bit — are
    // screenshots maybe better after all?" The poster is what the server
    // sends and what a phone keeps; the frame only ever lands on top of it.
    windows(html).forEach((pane, i) => {
      const imgs = [...pane.matchAll(/<img class="ll-portal-poster"[^>]*>/g)].map(m => m[0])
      expect(imgs, SECTIONS[i].poster).toHaveLength(1)
      expect(imgs[0]).toContain(`src="${SECTIONS[i].poster}"`)
      const alt = /alt="([^"]*)"/.exec(imgs[0])
      expect(alt, imgs[0]).not.toBeNull()
      expect(alt![1], imgs[0]).toMatch(/ current view$/)
    })
  })

  it('covers every portal with one link into its page, carrying a red CTA', () => {
    windows(html).forEach((pane, i) => {
      const { label, page } = SECTIONS[i]
      const links = [...pane.matchAll(/<a class="ll-portal-link"[^>]*>/g)]
      expect(links, page).toHaveLength(1)
      // Into the page itself — the search portal frames ?random, its link
      // opens the plain search.
      expect(links[0][0]).toContain(`href="${page}"`)
      // The visible text ends in a glyph a screen reader reads as "north
      // east arrow" — the accessible name has to be the words alone.
      expect(links[0][0]).toContain(`aria-label="${label}"`)
      // .cta-primary is landing.css's call to action: red, like the hero's.
      expect(pane).toContain(`<span class="cta-primary ll-portal-cta">${label} ↗</span>`)
    })
    // The old corner link is gone; the CTA replaced it and its muted line.
    expect(html).not.toContain('ll-portal-open')
    expect(html).not.toContain('live view of')
  })

  it('links nowhere with the ?random view — it is what the frame shows, not a page', () => {
    expect(html).not.toContain('href="/search.html?random"')
    expect(html).toContain('data-src="/search.html?random"')
  })

  it('names every window control — their link text is an arrow glyph', () => {
    for (const label of [
      'Open stories',
      'Story archive',
      'Open journals',
      'Open research library',
      'Open site search',
      'Sites by country',
    ]) {
      expect(html).toContain(`aria-label="${label}"`)
    }
    const btns = [...html.matchAll(/<a class="popup-window-btn"[^>]*>/g)].map(m => m[0])
    expect(btns).toHaveLength(6)
    for (const btn of btns) expect(btn, btn).toContain('aria-label=')
  })

  it('carries no second control on the href the first one already opens', () => {
    const hrefs = windows(html).map(pane =>
      [...pane.matchAll(/<a class="popup-window-btn" href="([^"]+)"/g)].map(m => m[1]),
    )
    expect(hrefs).toEqual(SECTIONS.map(s => s.buttons))
  })
})
