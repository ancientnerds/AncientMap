/**
 * The landing sections render under Node without browser APIs — exactly
 * what the SSR sidecar does. The homepage ships no React to the browser
 * (no landingMain entry since 2026-09-10), so the server output IS the
 * page: absolute dates, no effect, nothing left for a client to do.
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
 * page each one is on, its poster name, its CTA and the window buttons.
 * Stories and Sites have an archive of their own; the journal hub and the
 * research library ARE their archive.
 */
const SECTIONS = [
  { page: '/news.html', poster: 'news', label: 'Open stories', buttons: ['/news.html', '/news-archive/'] },
  { page: '/articles.html', poster: 'articles', label: 'Open journals', buttons: ['/articles.html'] },
  { page: '/research/', poster: 'research', label: 'Open research library', buttons: ['/research/'] },
  { page: '/search.html', poster: 'search', label: 'Open site search', buttons: ['/search.html', '/sites/'] },
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
    // and research papers on the right side?" The page on the poster IS the
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
 * Each window is a portal: a poster screenshot of the real page and the link
 * that covers it, carrying the CTA. Nothing else — no frame, no effect
 * (owner, 2026-09-10: "Those are no screenshots! It lags like hell! The
 * landing page must load super fast — and mobile first!").
 */
describe('PagePortal', () => {
  const html = render(FIXTURES.landing)

  it('frames each section in a NERV window titled after the page it shows', () => {
    expect([...html.matchAll(/class="ll-window"/g)]).toHaveLength(4)
    expect([...html.matchAll(/class="ll-window-bar"/g)]).toHaveLength(4)
    expect([...html.matchAll(/class="ll-window-body"/g)]).toHaveLength(4)
    for (const { page } of SECTIONS) {
      expect(html).toContain(`&gt;_ portal — <b>${page}</b>`)
    }
    // The bar's controls reuse the app's window buttons, not a second set.
    expect(html).toContain('class="popup-window-controls ll-window-controls"')
  })

  it('puts exactly one portal per window', () => {
    const panes = windows(html)
    expect(panes).toHaveLength(4)
    for (const pane of panes) {
      expect([...pane.matchAll(/<div class="ll-portal">/g)]).toHaveLength(1)
    }
  })

  it('runs nothing inside a portal — no frame, no page in a page', () => {
    expect(html).not.toContain('<iframe')
    expect(html).not.toContain('data-src')
    expect(html).not.toContain('ll-portal-frame')
    // The random draw is the capture's business (capture-previews.mjs), not
    // the page's: the homepage never links or loads it.
    expect(html).not.toContain('?random')
  })

  it('posters every portal with the screenshot of its own page, in two widths', () => {
    windows(html).forEach((pane, i) => {
      const { poster } = SECTIONS[i]
      const imgs = [...pane.matchAll(/<img class="ll-portal-poster"[^>]*>/g)].map(m => m[0])
      expect(imgs, poster).toHaveLength(1)
      const img = imgs[0]
      expect(img).toContain(`src="/data/previews/${poster}.webp"`)
      // The 640 px file is what a phone downloads; the browser picks by the
      // rendered width in `sizes`, so the phone never pays for 1280 px.
      // React emits the attribute as srcSet; HTML attribute names are case-insensitive.
      expect(img).toMatch(new RegExp(`srcset="/data/previews/${poster}-640\.webp 640w, /data/previews/${poster}\.webp 1280w"`, 'i'))
      expect(img).toContain('sizes="')
      expect(img).toContain('loading="lazy"')
      expect(img).toContain('width="1280" height="800"')
      const alt = /alt="([^"]*)"/.exec(img)
      expect(alt, img).not.toBeNull()
      expect(alt![1], img).toMatch(/ current view$/)
    })
    // JPEGs are gone with the frame — every poster is a WebP.
    expect(html).not.toContain('.jpg')
  })

  it('covers every portal with one link into its page, carrying a red CTA', () => {
    windows(html).forEach((pane, i) => {
      const { label, page } = SECTIONS[i]
      const links = [...pane.matchAll(/<a class="ll-portal-link"[^>]*>/g)]
      expect(links, page).toHaveLength(1)
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
