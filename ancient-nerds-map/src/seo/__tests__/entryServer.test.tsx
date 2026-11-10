/**
 * render() ist der Vertrag zum Node-Sidecar (ssr/server.mjs): ein
 * Route-Payload rein, {head, html} raus. Head und Body kommen aus denselben
 * Quellen wie in den Einzeltests (meta.test.ts, render.test.tsx) — hier
 * wird nur der Verbund geprüft, plus das laute Scheitern bei Tippfehlern.
 */

import { describe, expect, it } from 'vitest'

import { render } from '../../entry-server'
import { FIXTURES } from './fixtures'

describe('render()', () => {
  it('liefert head und html für jeden Typ', () => {
    for (const payload of Object.values(FIXTURES)) {
      const out = render(payload)
      expect(out.head).toContain('<title>')
      expect(out.head.match(/<link rel="canonical"/g)).toHaveLength(1)
      expect(out.html.length).toBeGreaterThan(50)
    }
  })

  it('wirft bei unbekanntem Typ, statt leer zu liefern', () => {
    expect(() => render({ type: 'gibtsnicht' } as never)).toThrow(/unknown route type/)
  })
})

// Owner decisions D141 and O22 (2026-11-10): what the sidecar hands the API for the three
// kinds of page that leave Google's index. Each page still renders its whole body (it is
// served to visitors and every other engine as before), and the robots tag stays "index".
describe('render(): the Google-only noindex in the served head', () => {
  const GOOGLEBOT = '<meta name="googlebot" content="noindex">'
  const ROBOTS_INDEX = '<meta name="robots" content="index, follow, max-image-preview:large">'

  it('a story created on or after 2026-11-11 carries it, an older one does not', () => {
    const fresh = render({ ...FIXTURES.story, created_at: '2026-11-11T00:00:00' })
    expect(fresh.head).toContain(GOOGLEBOT)
    expect(fresh.head).toContain(ROBOTS_INDEX)
    expect(fresh.html).toContain('a second fragment found at Trundholm')

    const older = render({ ...FIXTURES.story, created_at: '2026-11-10T23:59:59' })
    expect(older.head).not.toContain('googlebot')
    expect(older.head).toContain(ROBOTS_INDEX)
    // Same page either way: the rule changes one head tag, nothing in the body.
    expect(older.html).toBe(fresh.html)
  })

  it('a site page without a description carries it until the description exists', () => {
    const bare = render({ ...FIXTURES.site, description: null })
    expect(bare.head).toContain(GOOGLEBOT)
    expect(bare.head).toContain(ROBOTS_INDEX)
    expect(bare.html).toContain('Göbekli Tepe')

    const described = render(FIXTURES.site)
    expect(described.head).not.toContain('googlebot')
    expect(described.head).toContain(ROBOTS_INDEX)
  })

  it('a country page with at most four sites carries it, one with five does not', () => {
    const site = FIXTURES.country.sites[0]
    const country = (n: number) =>
      render({
        ...FIXTURES.country,
        sites: Array.from({ length: n }, (_, i) => ({ ...site, name: `Site ${i + 1}` })),
      })

    const four = country(4)
    expect(four.head).toContain(GOOGLEBOT)
    expect(four.head).toContain(ROBOTS_INDEX)
    expect(four.html).toContain('Site 4')

    const five = country(5)
    expect(five.head).not.toContain('googlebot')
    expect(five.head).toContain(ROBOTS_INDEX)
  })

  it('every other fixture page is served without it', () => {
    for (const [type, payload] of Object.entries(FIXTURES)) {
      if (type === 'country') continue // three sites: under the rule
      expect(render(payload).head, type).not.toContain('googlebot')
    }
  })
})
