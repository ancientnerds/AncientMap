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

/** The three window bodies, in document order. */
function windows(html: string): string[] {
  return html.split('<div class="ll-window">').slice(1)
}

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

  it('counts every section in its status line', () => {
    expect(html).toContain('3,189 stories · newest first')
    expect(html).toContain('23 issues · every Sunday')
    expect(html).toContain('24 public · CC BY 4.0 · by Theo')
  })

  it('links the page of every section', () => {
    for (const href of ['/news.html', '/news-archive/', '/articles.html', '/research/']) {
      expect(html).toContain(`href="${href}"`)
    }
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

  it('renders absolute dates on the server, never "ago"', () => {
    const times = [...html.matchAll(/<time[^>]*>(.*?)<\/time>/g)].map(m => m[1])
    expect(times.length).toBeGreaterThan(0)
    for (const text of times) expect(text).not.toContain('ago')
  })

  it('runs no list beside a portal any more', () => {
    // Owner, 2026-09-10: "Why do we still have the list of stories, journals
    // and research papers on the right side?" The page in the frame IS the
    // list; a second one said the same thing twice.
    for (const gone of ['ll-window-list', 'll-row', 'll-chip', 'll-more', 'll-badge', 'll-img']) {
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
    // Stories has no source of its own left: the count in stats is the whole
    // payload, so the section is always there.
    expect(out).toContain('stories, live')
  })
})

/**
 * Each window is a portal: the real page, scaled down, loaded lazily after
 * mount on every viewport (2026-09-10). The frame is decoration — the one
 * interactive thing is the link that covers it and carries the CTA.
 */
describe('PagePortal', () => {
  const html = render(FIXTURES.landing)
  const pages = ['/news.html', '/articles.html', '/research/']

  it('frames each section in a NERV window titled after the page it shows', () => {
    expect([...html.matchAll(/class="ll-window"/g)]).toHaveLength(3)
    expect([...html.matchAll(/class="ll-window-bar"/g)]).toHaveLength(3)
    expect([...html.matchAll(/class="ll-window-body"/g)]).toHaveLength(3)
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

  it('renders no iframe on the server — the frame is an effect', () => {
    expect(html).not.toContain('<iframe')
  })

  it('covers every portal with one link into its page, carrying a red CTA', () => {
    const labels: [string, string][] = [
      ['Open stories', '/news.html'],
      ['Open journals', '/articles.html'],
      ['Open research library', '/research/'],
    ]
    windows(html).forEach((pane, i) => {
      const [label, href] = labels[i]
      const links = [...pane.matchAll(/<a class="ll-portal-link"[^>]*>/g)]
      expect(links, href).toHaveLength(1)
      expect(links[0][0]).toContain(`href="${href}"`)
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
    for (const label of ['Open stories', 'Story archive', 'Open journals', 'Open research library']) {
      expect(html).toContain(`aria-label="${label}"`)
    }
    const btns = [...html.matchAll(/<a class="popup-window-btn"[^>]*>/g)].map(m => m[0])
    expect(btns).toHaveLength(4)
    for (const btn of btns) expect(btn, btn).toContain('aria-label=')
  })

  it('carries no second control on the href the first one already opens', () => {
    // Only Stories has an archive of its own (/news.html vs /news-archive/).
    // The journal hub and the research library ARE their archive, so the ≡
    // beside their ↗ pointed at the very same page.
    const hrefs = windows(html).map(pane =>
      [...pane.matchAll(/<a class="popup-window-btn" href="([^"]+)"/g)].map(m => m[1]),
    )
    expect(hrefs).toEqual([['/news.html', '/news-archive/'], ['/articles.html'], ['/research/']])
  })
})

/**
 * The papers gallery is Theo's public-library card, the same component
 * (2026-09-10, owner: "Why doesn't it look like Theo's research tasks, where
 * you get cards with images?").
 */
describe('paper gallery', () => {
  const html = render(FIXTURES.landing)
  const gallery = html.slice(html.indexOf('theo-public-grid ll-gallery'))

  it('renders one card per paper, each an <a> on its paper page', () => {
    const cards = [...gallery.matchAll(/<a class="theo-public-card" href="([^"]+)">/g)]
    expect(cards.map(m => m[1])).toEqual(PAPERS.map(p => p.path))
    for (const p of PAPERS) expect(gallery).toContain(`>${p.title}</div>`)
  })

  it('shows the hero image of the papers that have one, and no <img> for the rest', () => {
    const imgs = [...gallery.matchAll(/<img src="([^"]*)" alt="" class="theo-public-card-img"[^>]*>/g)]
    const withCover = PAPERS.filter(p => p.hero_image_url)
    expect(imgs.map(m => m[1])).toEqual(withCover.map(p => p.hero_image_url))
    // Never <img src="">: that resolves against the page URL and refetches it.
    for (const img of imgs) expect(img[1]).not.toBe('')
    expect([...gallery.matchAll(/theo-public-card-vignette/g)]).toHaveLength(PAPERS.length)
  })

  it('prints the blurb only for a paper that has one', () => {
    const descs = [...gallery.matchAll(/<p class="theo-public-card-desc">(.*?)<\/p>/g)].map(m => m[1])
    expect(descs).toEqual(PAPERS.filter(p => p.summary).map(p => p.summary))
  })

  it('joins the footer from the parts that exist, without a dangling separator', () => {
    const footers = [...gallery.matchAll(/<div class="theo-public-card-footer">(.*?)<\/div>/g)].map(
      m => m[1],
    )
    expect(footers).toEqual([
      'by Theo · Aug 31 · 2,748 sources · 6,466 words',
      'by theo · Aug 31 · 3,169 sources · 7,057 words',
    ])
    const bare = render({
      ...FIXTURES.landing,
      papers: {
        ...FIXTURES.landing.papers!,
        items: [{ ...PAPERS[0], published_at: null, words: null }],
      },
    })
    const only = /<div class="theo-public-card-footer">(.*?)<\/div>/.exec(bare)![1]
    expect(only).toBe('by Theo · 2,748 sources')
  })

  it('carries only the fields a card renders — no payload nobody prints', () => {
    // The Python side asserts the same key set (tests/api/test_landing_html.py).
    for (const p of PAPERS) {
      expect(Object.keys(p).sort()).toEqual([
        'author',
        'hero_image_url',
        'path',
        'published_at',
        'slug',
        'sources_analyzed',
        'summary',
        'title',
        'words',
      ])
    }
  })
})
