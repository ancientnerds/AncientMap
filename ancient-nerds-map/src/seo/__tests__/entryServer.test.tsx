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
