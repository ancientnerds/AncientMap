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
import { FIXTURES, pyrefRoute } from './fixtures'

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

describe('research-Seiten (Task 12): der SSR-Body trägt den Python-Fragment-Inhalt', () => {
  const html = renderRoute(FIXTURES.research)

  it('genau ein h1, und es trägt den Papertitel', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
    expect(html).toContain('Obsidian Trade Networks in Neolithic Anatolia')
  })

  it('Art.-50-Hinweis sichtbar UND maschinenlesbar (data-ai-generated)', () => {
    expect(html).toContain('data-ai-generated="true"')
    expect(html).toContain('AI-generated')
  })

  it('body_html ist gerendert — kompletter Papertext im ersten Render, kein Fetch', () => {
    expect(html).toContain('<p>body</p>')
    expect(html).not.toContain('Loading...')
  })

  it('Theo-Autorenzeile mit AI-Agent-Kennzeichnung, Datum und Lizenz', () => {
    expect(html).toContain('by Theo')
    expect(html).toContain('AI research agent')
    expect(html).toContain('2026-07-02')
    expect(html).toContain('CC BY 4.0')
  })

  it('Hero-Bild und Summary aus dem Payload', () => {
    expect(html).toContain('https://ancientnerds.com/data/research/obsidian/hero.webp')
    expect(html).toContain('Sourcing analyses of 1,200 obsidian artefacts')
  })

  it('Rückweg zur Library und CommunityCta', () => {
    expect(html).toContain('href="/research/"')
    expect(html).toContain('Keep exploring')
  })

  it('menschlicher Autor OHNE AI-Agent-Suffix (Fälle aus TestResearchAuthorship)', () => {
    const person = renderRoute(pyrefRoute('research_person'))
    expect(person).toContain('by Dr. Jane Doe')
    expect(person).not.toContain('AI research agent')
    // Der Art.-50-Banner bleibt trotzdem: der Papertext ist KI-generiert.
    expect(person).toContain('data-ai-generated="true"')
  })
})

describe('researchIndex (Task 12): echte Listenseite statt Redirect', () => {
  const html = renderRoute(FIXTURES.researchIndex)

  it('genau ein h1: Research Library', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
    expect(html).toContain('Research Library')
  })

  it('eine Karte pro Paper, mit Link und Summary-Blurb', () => {
    expect(html).toContain('href="/research/obsidian-trade-networks-anatolia"')
    expect(html).toContain('href="/research/gobekli-tepe-water-management"')
    expect(html).toContain('Water Management at Göbekli Tepe')
    expect(html).toContain('Cistern volumes suggest')
  })

  it('Art.-50-Banner und CommunityCta', () => {
    expect(html).toContain('data-ai-generated="true"')
    expect(html).toContain('Keep exploring')
  })
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

  it('Bild ohne Credit-Daten: keine leere <figcaption> (Python ließ sie weg)', () => {
    const bare = renderRoute({
      ...FIXTURES.site,
      image: { url: '/data/images/wiki/9c8b7a65/hero.webp', author: null, license: null, commons_url: null },
    })
    expect(bare).toContain('/data/images/wiki/9c8b7a65/hero.webp')
    expect(bare).not.toContain('<figcaption')
  })
})

describe('article-Seite (Task 13): der SSR-Body trägt den Python-Fragment-Inhalt', () => {
  const html = renderRoute(FIXTURES.article)

  it('genau ein h1, und es trägt den Journaltitel', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
    expect(html).toContain('Week 31: Hoards &amp; Harbours')
  })

  it('Art.-50-Hinweis sichtbar UND maschinenlesbar (data-ai-generated)', () => {
    expect(html).toContain('data-ai-generated="true"')
    expect(html).toContain('AI-generated')
  })

  it('body_html ist gerendert — komplettes Journal im ersten Render, kein Fetch', () => {
    expect(html).toContain('<p>body</p>')
    expect(html).not.toContain('Loading journals')
  })

  it('Datum und Summary aus dem Payload', () => {
    expect(html).toContain('2026-08-03')
    expect(html).toContain('A Viking silver hoard on Gotland')
  })

  it('Rückweg zum Hub und CommunityCta', () => {
    expect(html).toContain('href="/articles/"')
    expect(html).toContain('Keep exploring')
  })
})

describe('articleIndex (Task 13): der crawlbare Journal-Hub aus dem Payload', () => {
  const html = renderRoute(FIXTURES.articleIndex)

  it('genau ein h1: Weekly Archaeology Journal', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
    expect(html).toContain('Weekly Archaeology Journal')
  })

  it('eine Karte pro Journal, mit Link und Summary-Blurb', () => {
    expect(html).toContain('href="/articles/week-31-hoards-and-harbours"')
    expect(html).toContain('href="/articles/week-30-mummies-and-mosaics"')
    expect(html).toContain('Week 30: Mummies &amp; Mosaics')
    expect(html).toContain('New Saqqara burials')
  })

  it('Art.-50-Banner und CommunityCta', () => {
    expect(html).toContain('data-ai-generated="true"')
    expect(html).toContain('Keep exploring')
  })
})

describe('story-Seite (Task 14): der SSR-Body trägt den Python-Fragment-Inhalt', () => {
  // Inhaltliche Parität zu seo_pages.story_page() — was dort am Python-Body
  // hing (Quellen, Deeplink, Site-Chips, Related), muss im React-Body stehen.
  const html = renderRoute(FIXTURES.story)

  it('genau ein h1, und es trägt die Headline', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
    expect(html).toContain('Sun Chariot')
  })

  it('Datum aus dem rohen ISO-Timestamp: dateTime ISO, Anzeige lang', () => {
    expect(html).toContain('dateTime="2026-03-14"')
    expect(html).toContain('March 14, 2026')
  })

  it('Video-Link mit &t=-Deeplink und absolutiertem Screenshot', () => {
    expect(html).toContain('https://www.youtube.com/watch?v=abc123&amp;t=754s')
    expect(html).toContain('https://ancientnerds.com/data/news/screenshots/4711.jpg')
    expect(html).toContain('by Ancient Architects')
  })

  it('kuratierte Site: Chip zur Detailseite UND zum Globus', () => {
    expect(html).toContain('href="/sites/denmark/trundholm-mose-1b2c3d4e"')
    expect(html).toContain('/globe.html?focus=1b2c3d4e-0000-4000-8000-000000000000')
  })

  it('unkuratierte Site: kein Detailseiten-Link (wäre ein 404), nur der Globus', () => {
    const uncurated = renderRoute({ ...FIXTURES.story, site_curated: false })
    // href="/sites/" (der Hub in CommunityCta) bleibt — nur der Chip zur
    // Detailseite darf nicht entstehen.
    expect(uncurated).not.toContain('href="/sites/denmark')
    expect(uncurated).toContain('📍 <!-- -->Trundholm Mose')
    expect(uncurated).toContain('/globe.html?focus=1b2c3d4e-0000-4000-8000-000000000000')
  })

  it('Quellen aus web_sources: Titel, nackter Host, Snippet', () => {
    expect(html).toContain('https://en.natmus.dk/sun-chariot/')
    expect(html).toContain('National Museum of Denmark')
    expect(html).toContain('en.natmus.dk')
    expect(html).toContain('found in 1902 in the Trundholm bog')
  })

  it('web_sources ist LLM-derived: ein javascript:-Eintrag wird nie ein href', () => {
    const evil = renderRoute({
      ...FIXTURES.story,
      web_sources: [{ url: 'javascript:alert(1)', title: 'evil' }],
    })
    expect(evil).not.toContain('javascript:')
    expect(evil).not.toContain('>Sources<') // nichts Valides übrig
  })

  it('Related-Block mit Site-Überschrift und Story-Link', () => {
    expect(html).toContain('More about Trundholm Mose')
    expect(html).toContain('href="/news-archive/trundholm-bog-survey-planned-4600"')
  })

  it('Art.-50-Fußnote maschinenlesbar (data-ai-generated) und CommunityCta', () => {
    expect(html).toContain('data-ai-generated="true"')
    expect(html).toContain('AI-generated')
    expect(html).toContain('Keep exploring')
  })
})

describe('storyArchive (Task 14): das paginierte Listing aus dem Rohpayload', () => {
  const html = renderRoute(FIXTURES.storyArchive)

  it('genau ein h1: Story Archive, mit Zählern', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
    expect(html).toContain('Story Archive')
    expect(html).toContain('2,248')
    expect(html).toContain('page 1 of 94')
  })

  it('Karten mit Link, Thumbnail, Blurb und Meta-Zeile', () => {
    expect(html).toContain(
      'href="/news-archive/bronze-age-sun-chariot-a-second-fragment-found-at-trundholm-4711"',
    )
    expect(html).toContain('src="/data/news/screenshots/4711.jpg"')
    expect(html).toContain('Conservators at the National Museum')
    expect(html).toContain('March 14, 2026')
    expect(html).toContain('via Ancient Architects')
  })

  it('Speculative-Badge auf der markierten Karte', () => {
    expect(html).toContain('speculative')
  })

  it('Pager Seite 1: nur Next, auf /news-archive/page/2', () => {
    expect(html).toContain('href="/news-archive/page/2"')
    expect(html).not.toContain('Previous')
  })

  it('Pager Seite 2: Previous zurück auf /news-archive/', () => {
    const page2 = renderRoute(pyrefRoute('storyArchive_page2'))
    expect(page2).toContain('page 2 of 94')
    expect(page2).toContain('href="/news-archive/"')
    expect(page2).toContain('href="/news-archive/page/3"')
  })

  it('Art.-50-Banner und CommunityCta', () => {
    expect(html).toContain('data-ai-generated="true"')
    expect(html).toContain('Keep exploring')
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
