/**
 * The landing sections render under Node without browser APIs — exactly
 * what the SSR sidecar does. Effects (relative time, feed refetch) do not
 * run in renderToString, so the server output carries absolute dates.
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
    const stories = FIXTURES.landing.stories!
    for (const href of [
      ...[stories.lead, ...stories.rail].map(s => storyPath(s.headline, s.id)),
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
      stories: { ...FIXTURES.landing.stories!, rail: [{ ...rail[0], news_category: null }] },
    })
    const row = out.slice(out.indexOf(`href="${storyPath(rail[0].headline, rail[0].id)}"`))
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
    // The teaser images only: the article inside the window brings the story
    // page's own <img> tags (video still, country flag), which are that
    // page's markup and are asserted there.
    const imgs = [...html.matchAll(/<span class="ll-img[^"]*"><img\b[^>]*>/g)].map(m => m[0])
    for (const tag of imgs) {
      expect(tag, tag).toContain('loading="lazy"')
      expect(tag, tag).toContain('decoding="async"')
    }
    // Two of the three story thumbs, the journal lead, the paper lead — the
    // story without a screenshot keeps its empty aspect-ratio box.
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

/**
 * The Stories section is a window running the story page (2026-09-10).
 * Everything a crawler needs is in the first render: the lead's whole
 * article, its sources, the disclosure, and a real link per list row.
 */
describe('LandingStories window', () => {
  const stories = FIXTURES.landing.stories!
  const html = render(FIXTURES.landing)
  const lead = stories.lead
  const leadHref = storyPath(lead.headline, lead.id)

  it('frames the article in a NERV window with the story page as its title', () => {
    expect(html).toContain('class="ll-window"')
    expect(html).toContain('class="ll-window-bar"')
    expect(html).toContain('&gt;_ stories.log')
    // The bar's controls reuse the app's window buttons, not a second set.
    expect(html).toContain('class="popup-window-controls ll-window-controls"')
    expect(html).toContain(`<a class="popup-window-btn" href="${leadHref}"`)
    expect(html).toContain('<a class="popup-window-btn" href="/news-archive/"')
  })

  it('renders the lead as h3 — the section label is the only h2 above it', () => {
    const titles = [...html.matchAll(/<h3 class="story-title">(.*?)<\/h3>/g)].map(m => m[1])
    expect(titles).toHaveLength(1)
    expect(titles[0]).toContain(`<a href="${leadHref}">`)
    expect(html).not.toContain('<h1')
  })

  it('carries the whole story body, not a first sentence', () => {
    const body = /<div class="story-body">([\s\S]*?)<\/div>/.exec(html)
    expect(body).not.toBeNull()
    const paragraphs = [...body![1].matchAll(/<p>/g)]
    expect(paragraphs.length).toBe(lead.post_text.split('\n').length)
    expect(html).toContain('the first Roman mass war grave known from Central Europe')
  })

  it('shows key facts, sources and the Art.-50 disclosure', () => {
    expect(html).toContain('>Key facts<')
    expect(html).toContain('>Sources<')
    for (const source of lead.web_sources!) {
      expect(html).toContain(`<a href="${source.url}" target="_blank" rel="noopener nofollow">`)
    }
    expect(html).toContain('data-ai-generated="true"')
  })

  it('lists lead plus rail as real links, the lead marked current', () => {
    const rows = [...html.matchAll(/<a class="ll-row ll-row-thumb" href="([^"]+)"([^>]*)>/g)]
    expect(rows).toHaveLength(1 + stories.rail.length)
    expect(rows.map(m => m[1])).toEqual(
      [lead, ...stories.rail].map(s => storyPath(s.headline, s.id)),
    )
    expect(rows[0][2]).toContain('aria-current="true"')
    for (const row of rows.slice(1)) expect(row[2]).not.toContain('aria-current')
  })

  it('compact mode drops the country fallback chip', () => {
    // An uncurated site keeps the plain 📍 chip and the globe link; "More
    // sites in {country}" belongs on the page, which has room for it.
    const out = render({
      ...FIXTURES.landing,
      stories: {
        ...stories,
        lead: { ...lead, site_curated: false, site_country: 'Austria' },
      },
    })
    expect(out).toContain('📍 <!-- -->Roman grave')
    expect(out).not.toContain('More sites in')
    expect(out).toContain('🌍 Show on the globe')
  })

  it('compact mode lists at most four sources', () => {
    const many = Array.from({ length: 8 }, (_, i) => ({
      url: `https://source-${i}.example/`,
      title: `Source ${i}`,
      snippet: null,
    }))
    const out = render({
      ...FIXTURES.landing,
      stories: { ...stories, lead: { ...lead, web_sources: many, post_text: 'Body.' } },
    })
    expect([...out.matchAll(/<div class="story-source">/g)]).toHaveLength(4)
    expect(out).toContain('https://source-3.example/')
    expect(out).not.toContain('https://source-4.example/')
  })
})
