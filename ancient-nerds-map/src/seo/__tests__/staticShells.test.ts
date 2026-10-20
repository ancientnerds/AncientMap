/**
 * The static entry shells (index.html, search.html, …) as a crawler without scripts reads
 * them: the SEO evaluation of 2026-10-19 found no WebSite schema and no <main> on the
 * homepage (tech-10, tech-14), two h1 on search, theo and library (tech-6, index-6), and
 * news, articles and library self-canonical next to their server-rendered hubs (tech-6;
 * owner decision 2026-10-20: canonical on the hub, no 301).
 */

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const APP_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const shell = (name: string) => readFileSync(join(APP_DIR, name), 'utf8')

const jsonLdTypes = (html: string) =>
  [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(
    m => (JSON.parse(m[1]) as { '@type': string })['@type'],
  )

describe('index.html', () => {
  const html = shell('index.html')

  it('carries a WebSite schema without a SearchAction', () => {
    expect(jsonLdTypes(html)).toEqual(['WebSite', 'WebApplication', 'Organization', 'Dataset'])
    const site = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)]
      .map(m => JSON.parse(m[1]) as Record<string, unknown>)
      .find(s => s['@type'] === 'WebSite')!
    expect(site.url).toBe('https://ancientnerds.com/')
    expect(site.name).toBe('Ancient Nerds')
    expect(site).not.toHaveProperty('potentialAction')
  })

  it('has exactly one <main>, from the hero to the final call to action, footer outside', () => {
    expect(html.match(/<main[\s>]/g)).toHaveLength(1)
    const main = html.slice(html.indexOf('<main>'), html.indexOf('</main>'))
    expect(main).toContain('<section class="hero">')
    expect(main).toContain('<div id="root"></div>')
    expect(main).toContain('<section class="final-cta full-width">')
    expect(main).not.toContain('<footer')
  })
})

describe('search.html, theo.html, library.html', () => {
  for (const name of ['search.html', 'theo.html', 'library.html']) {
    it(`${name} has one h1 (the <noscript> title) and the boot block's heading as h2`, () => {
      const html = shell(name)
      expect(html.match(/<h1[\s>]/g)).toHaveLength(1)
      expect(html).toMatch(/<div class="seo-boot">\s*<h2>/)
      // The h2 keeps the size the h1 had.
      expect(html).toContain('.seo-boot h2{color:#fff;font-size:2em}')
    })
  }
})

describe('news.html, articles.html, library.html', () => {
  const hubs: Record<string, string> = {
    'news.html': 'https://ancientnerds.com/news-archive/',
    'articles.html': 'https://ancientnerds.com/articles/',
    'library.html': 'https://ancientnerds.com/research/',
  }
  for (const [name, hub] of Object.entries(hubs)) {
    it(`${name} names ${hub} as canonical and og:url`, () => {
      const html = shell(name)
      expect([...html.matchAll(/<link rel="canonical" href="([^"]+)"/g)].map(m => m[1])).toEqual([
        hub,
      ])
      expect(html).toContain(`<meta property="og:url" content="${hub}" />`)
    })
  }
})
