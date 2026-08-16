/**
 * Beweis der Serverfähigkeit: jeder der 9 Typen rendert per renderToString
 * unter Node — ohne window, document, localStorage (Vitest läuft ohne
 * DOM-Environment). Effekte — die Daten-Fetches von SitePage,
 * ResearchPaperPage und ArticlesPage — laufen bei renderToString nicht;
 * genau so rendert später der SSR-Dienst.
 *
 * AuthProvider gehört zum Baum: ResearchPaperPage und ArticlesPage rufen
 * useIsFounder() → useAuth(), das ohne Provider wirft — und entry-server
 * (Task 6) wickelt SeoRoute genauso ein. Bewusst KEIN OfflineProvider:
 * kein serverseitig gerenderter Zweig konsumiert useOffline(), und der
 * Test beweist das gleich mit.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '../../contexts/AuthContext'
import ArticlesPage from '../../pages/ArticlesPage'
import type { AnRoute } from '../../types/anRoute'
import { SeoRoute } from '../registry'
import { RouteProvider } from '../RouteContext'
import { FIXTURES } from './fixtures'

function renderRoute(route: AnRoute): string {
  return renderToString(
    <RouteProvider value={route}>
      <AuthProvider>
        <SeoRoute />
      </AuthProvider>
    </RouteProvider>,
  )
}

describe('serverseitiges Rendern', () => {
  for (const [type, payload] of Object.entries(FIXTURES)) {
    it(`rendert ${type} ohne Browser-APIs`, () => {
      const html = renderRoute(payload)
      expect(html.length).toBeGreaterThan(50)
    })
  }
})

describe('heutige Produktions-Stubs (bis zum Cutover, Tasks 11-14)', () => {
  // pipeline/seo_pages.py injiziert für diese Typen nur Stubs — die Seiten
  // holen ihre Daten selbst. Die Registry muss auch mit exakt diesen
  // Payloads rendern, nicht nur mit den Post-Cutover-Fixtures.
  const stubs = [
    { type: 'site', id: '5281654c' },
    { type: 'research', slug: 'goebekli-tepe' },
    { type: 'researchIndex' },
    { type: 'article', slug: 'weekly-journal' },
    { type: 'articleIndex' },
  ] as unknown as AnRoute[]

  for (const stub of stubs) {
    it(`rendert den ${stub.type}-Stub`, () => {
      const html = renderRoute(stub)
      expect(html.length).toBeGreaterThan(50)
    })
  }
})

describe('Standalone-SPA-Modus (/articles.html ohne Payload)', () => {
  // Produktentscheidung 2026-08: /articles.html (indexiert) und /articles/
  // bleiben BEIDE bestehen, 301 erst nach Indexierung des neuen Hubs —
  // articlesMain rendert ohne Payload deshalb ArticlesPage direkt statt
  // umzuleiten. Der Baum entspricht articlesMain.tsx: RouteProvider ohne
  // value, ArticlesPage holt ihre Daten selbst.
  it('rendert ArticlesPage ohne Route und ohne Browser-APIs', () => {
    const html = renderToString(
      <RouteProvider>
        <AuthProvider>
          <ArticlesPage />
        </AuthProvider>
      </RouteProvider>,
    )
    expect(html.length).toBeGreaterThan(50)
  })
})
