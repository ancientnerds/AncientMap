// @vitest-environment jsdom
/**
 * Hydration der echten Produktions-Payloads.
 *
 * Am 20.09.–03.10.2026 meldete die Fehler-Erfassung auf /sites/{country}/{slug}
 * sechsmal "Minified React error #425" (20 Auslösungen, 5 davon iOS): "Text
 * content does not match server-rendered HTML". Der Server rendert
 * renderToString(route), der Browser hydriert denselben Payload - wenn beide
 * Seiten unterschiedlichen Text liefern, tauscht React den Knoten aus und die
 * Seite flackert. render.test.tsx kann das nicht sehen: es laeuft ohne DOM und
 * vergleicht Markup, nicht den Baum, den der Browser daraus baut.
 *
 * Dieser Test baut genau das nach: Server-Markup in einen Container legen,
 * denselben Payload hydrieren, und jeden onRecoverableError als Fehler
 * werten. onRecoverableError ist der Kanal, den React fuer Hydration-
 * Abweichungen benutzt - 418, 425, 423.
 *
 * Die Payloads sind die echten aus der Produktion (abgeholt 04.10.2026,
 * src/seo/__tests__/fixtures/productionSiteRoutes.json), nicht erfundene
 * Beispiele: nur mit dem Text, den Besucher wirklich bekommen, loest ein
 * Tippfehler in einem Bauteil, den diese Seiten benutzen, etwas aus.
 *
 * Was der Test nicht beweist: jsdom ist nicht Chrome. Eine vom Browser
 * reparierte Fehlkonstruktion faellt hier auf, eine Browser-spezifische
 * Textnormalisierung vielleicht nicht. Der Test ist die billigste Stelle, an
 * der sich eine Abweichung faengt, nicht der Beweis fuer Chromium.
 */
import { renderToString } from 'react-dom/server'
import { hydrateRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../contexts/AuthContext'
import type { AnRoute, SiteRoute } from '../../types/anRoute'
import { SeoRoute } from '../registry'
import { RouteProvider } from '../RouteContext'
import productionRoutes from './fixtures/productionSiteRoutes.json'

const ROUTES = Object.entries(productionRoutes as Record<string, SiteRoute>).map(
  ([name, route]) => [name, route as AnRoute] as const,
)

function tree(route: AnRoute) {
  return (
    <RouteProvider value={route}>
      <AuthProvider>
        <SeoRoute />
      </AuthProvider>
    </RouteProvider>
  )
}

/** Wait for React to finish the initial hydration pass and its effects. */
function settle(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0))
}

describe('Hydration der Produktions-Payloads einer Site-Seite', () => {
  let root: HTMLElement

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }))
    document.body.innerHTML = '<div id="root"></div>'
    root = document.getElementById('root') as HTMLElement
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('die Fixture deckt genau die vier betroffenen Seiten ab', () => {
    expect(ROUTES.map(([name]) => name).sort()).toEqual([
      'Cairnpapple Hill',
      'Coom Wedge Tomb',
      'Kekova Island',
      "Serpent's Wall",
    ])
  })

  for (const [name, route] of ROUTES) {
    it(`${name}: der erste Client-Render gleicht dem Server-Markup`, async () => {
      root.innerHTML = renderToString(tree(route))

      const recoverable: string[] = []
      hydrateRoot(root, tree(route), {
        onRecoverableError: error => recoverable.push(String(error)),
      })
      await settle()

      expect(recoverable).toEqual([])
    })
  }
})
