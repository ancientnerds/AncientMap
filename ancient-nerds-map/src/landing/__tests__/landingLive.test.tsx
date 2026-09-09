/**
 * The landing sections render under Node without browser APIs — exactly
 * what the SSR sidecar does. Effects (relative time, feed refetch) do not
 * run in renderToString, so the server output carries absolute dates.
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

  it('links every teaser to its page', () => {
    for (const href of [
      FIXTURES.landing.stories!.lead.path,
      ...FIXTURES.landing.stories!.rail.map(s => s.path),
      FIXTURES.landing.journals!.lead.path,
      ...FIXTURES.landing.journals!.rail.map(j => j.path),
      FIXTURES.landing.papers!.lead.path,
      ...FIXTURES.landing.papers!.rail.map(p => p.path),
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
    // week_start is "2026-08-31T00:00:00" — zoneless. Going through
    // new Date() would render "Aug 30" wherever the renderer sits east of
    // UTC and desync server from client.
    expect(html).toContain('Aug 31 – Sep 6')
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

  it('shows the evidence strip and the Theo line', () => {
    expect(html).toContain('2,748')
    expect(html).toContain('Theo is researching')
    expect(html).toContain('Water erosion evidence in the Osiris Shaft')
    // The start time follows the page rule: absolute now, relative after
    // mount — a <time> from RelativeTime, not a frozen "since Sep 9".
    const theoLine = /<a class="ll-theo"[\s\S]*?<\/a>/.exec(html)![0]
    expect(theoLine).toContain('started')
    expect(theoLine).toContain('<time')
  })

  it('drops the separator in front of a story without a category', () => {
    const rail = FIXTURES.landing.stories!.rail
    const out = render({
      ...FIXTURES.landing,
      stories: { ...FIXTURES.landing.stories!, rail: [{ ...rail[0], category: null }] },
    })
    const row = out.slice(out.indexOf(`href="${rail[0].path}"`))
    const meta = /<span class="ll-meta">([\s\S]*?)<\/span>/.exec(row)
    expect(meta).not.toBeNull()
    const text = meta![1].replace(/<[^>]*>/g, '').trim()
    expect(text.startsWith('·')).toBe(false)
    expect(text.startsWith('SIG')).toBe(true)
  })

  it('serves plain lazy <img>, never the JS-gated LazyImage', () => {
    // LazyImage starts on .lazy-image--hidden and unhides in React's onLoad
    // — an event that never fires for an image the browser finished before
    // hydration, and never at all for a crawler without JS.
    expect(html).not.toContain('lazy-image')
    expect(html).not.toContain('data:image/svg+xml')
    const imgs = [...html.matchAll(/<img\b[^>]*>/g)].map(m => m[0])
    expect(imgs.length).toBeGreaterThan(0)
    for (const tag of imgs) {
      expect(tag, tag).toContain('loading="lazy"')
      expect(tag, tag).toContain('decoding="async"')
    }
    // The story without a screenshot keeps its empty aspect-ratio box.
    expect(imgs).toHaveLength(4)
  })

  it('joins meta lines from the parts that exist, without a dangling separator', () => {
    const journals = FIXTURES.landing.journals!
    const papers = FIXTURES.landing.papers!
    const row = journals.rail[0]
    const out = render({
      ...FIXTURES.landing,
      journals: { ...journals, rail: [{ ...row, week_start: null, week_end: null }] },
      papers: { ...papers, lead: { ...papers.lead, published_at: null, minutes: null } },
    })
    const metaAfter = (href: string): string => {
      const tail = out.slice(out.indexOf(`href="${href}"`))
      const meta = /<span class="ll-meta">([\s\S]*?)<\/span>/.exec(tail)
      expect(meta, `no ll-meta after ${href}`).not.toBeNull()
      return meta![1].replace(/<[^>]*>/g, '').trim()
    }
    for (const text of [metaAfter(row.path), metaAfter(papers.lead.path)]) {
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
