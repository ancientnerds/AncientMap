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

describe('heutige Produktions-Stubs (bis zum Cutover, Tasks 12-14)', () => {
  // pipeline/seo_pages.py injiziert für diese Typen nur Stubs — die Seiten
  // holen ihre Daten selbst. Die Registry muss auch mit exakt diesen
  // Payloads rendern, nicht nur mit den Post-Cutover-Fixtures. (site trägt
  // seit Task 11 das volle Payload — sein Stub existiert nicht mehr.)
  const stubs = [
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

describe('site-Detailseite (Task 11): der SSR-Body trägt den Python-Fragment-Inhalt', () => {
  // Inhaltliche Parität zu tests/pipeline/test_site_detail_seo.py — dieselben
  // Punkte, die dort am Python-Body hängen, müssen im React-Body stehen.
  const html = renderRoute(FIXTURES.site)

  it('genau ein h1, und es trägt den Site-Namen', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
    expect(html).toContain('Göbekli Tepe')
  })

  it('Typ, Periode und Land in der Meta-Zeile ("< 4500 BC" HTML-escaped)', () => {
    expect(html).toContain('Temple complex')
    expect(html).toContain('&lt; 4500 BC')
    expect(html).toContain('Türkiye')
  })

  it('Hero-Bild mit Commons-Attribution (Lizenzpflicht)', () => {
    expect(html).toContain('/data/images/wiki/9c8b7a65/hero.webp')
    expect(html).toContain('Teomancimit')
    expect(html).toContain('CC BY-SA 3.0')
    expect(html).toContain('commons.wikimedia.org')
  })

  it('Alt-Namen ohne den Hauptnamen selbst', () => {
    expect(html).toContain('Also known as:')
    expect(html).toContain('Portasar, Potbelly Hill')
  })

  it('Koordinaten aus coordDisplay', () => {
    expect(html).toContain('37.2231° N, 38.9224° E')
  })

  it('interne und externe Links: News, Ressourcen, Parent, Geschwister, Land', () => {
    expect(html).toContain('/news-archive/gobekli-tepe-dig-resumes-991')
    expect(html).toContain('https://whc.unesco.org/en/list/1572/')
    expect(html).toContain('/sites/türkiye/taş-tepeler-0f9e8d7c') // Part of
    expect(html).toContain('/sites/türkiye/karahan-tepe-1a2b3c4d') // sibling
    expect(html).toContain('/sites/türkiye') // country listing
  })

  it('Globus-CTA mit ?focus= und der CommunityCta-Block', () => {
    expect(html).toContain('/globe.html?focus=9c8b7a65-4321-4cba-8000-111122223333')
    expect(html).toContain('Keep exploring')
    expect(html).toContain('discord')
  })

  it('kein Fetch-Spinner im ersten Render — das Payload trägt alles', () => {
    expect(html).not.toContain('Loading site details')
  })
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
