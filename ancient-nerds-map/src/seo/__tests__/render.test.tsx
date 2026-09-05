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

  it('Globus-CTA mit #focus= (Fragment, nicht Query) und der CommunityCta-Block', () => {
    expect(html).toContain('/globe.html#focus=9c8b7a65-4321-4cba-8000-111122223333')
    expect(html).not.toContain('/globe.html?focus=')
    expect(html).toContain('Keep exploring')
    expect(html).toContain('discord')
  })

  it('kein Fetch-Spinner im ersten Render — das Payload trägt alles', () => {
    expect(html).not.toContain('Loading site details')
  })

  it('kuratierte Site-Records tragen KEINEN Art.-50-Hinweis (menschlich kuratiert)', () => {
    // Aus tests/pipeline/test_ai_act_notices.py übernommen (Task 16): Art. 50
    // gilt für KI-generierten Text, nicht für kuratierte Site-Datensätze.
    expect(html).not.toContain('data-ai-generated')
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
    expect(html).toContain('/globe.html#focus=1b2c3d4e-0000-4000-8000-000000000000')
  })

  it('unkuratierte Site: kein Detailseiten-Link (wäre ein 404), dafür die Länderseite', () => {
    const uncurated = renderRoute({ ...FIXTURES.story, site_curated: false })
    // Der Detailpfad trägt IMMER ein zweites Segment — nur der wäre der 404.
    // Die Länderseite darunter existiert für jede Site mit Land.
    expect(uncurated).not.toContain('href="/sites/denmark/')
    expect(uncurated).toContain('📍 <!-- -->Trundholm Mose')
    expect(uncurated).toContain('href="/sites/denmark"')
    expect(uncurated).toContain('/globe.html#focus=1b2c3d4e-0000-4000-8000-000000000000')
  })

  it('kuratierte Site behält den Detaillink und bekommt KEINEN Länder-Chip', () => {
    expect(html).toContain('href="/sites/denmark/trundholm-mose-1b2c3d4e"')
    expect(html).not.toContain('More sites in')
  })

  // Seit 2026-08-21 trägt das Payload site_type/period/significance, damit die
  // Seite dieselben Komponenten rendert wie die Karten.
  it('Badges, Flagge, Kategorie-Label und Signifikanz aus dem Payload', () => {
    const rich = renderRoute({
      ...FIXTURES.story,
      site_country: 'Denmark',
      site_type: 'Burial mound',
      site_period_start: -1400,
      news_category: 'remote_sensing',
      significance: 8,
    })
    expect(rich).toContain('Burial mound')          // Typ-Badge
    expect(rich).toContain('Bronze Age')            // Zeitalter aus period_start
    expect(rich).toContain('Remote Sensing')        // Label statt "remote_sensing"
    expect(rich).not.toContain('>remote_sensing<')
    expect(rich).toContain('Breakthrough')          // Signifikanz-Stempel (8)
    expect(rich).toContain('meta-flag')             // Länderflagge
  })

  it('ohne Site-Metadaten bleiben die Badges weg', () => {
    const bare = renderRoute({
      ...FIXTURES.story,
      site_type: null,
      site_period_name: null,
      site_period_start: null,
      significance: null,
    })
    expect(bare).not.toContain('meta-badges')
    expect(bare).not.toContain('story-significance')
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

  // Seit 2026-08-21 rendert <Breadcrumbs> Markup UND BreadcrumbList-Schema
  // aus einer Liste — vorher stand die Kette in sieben Seiten handgeschrieben
  // und ohne Schema.
  it('BreadcrumbList-Schema passt zur sichtbaren Krümelnavigation', () => {
    const scripts = [...html.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs)]
    const crumbs = scripts
      .map(m => JSON.parse(m[1].replace(/\\u003c/g, '<')))
      .find(s => s['@type'] === 'BreadcrumbList')
    expect(crumbs).toBeDefined()
    expect(crumbs.itemListElement.map((e: { name: string }) => e.name)).toEqual([
      'Home',
      'Story Archive',
      FIXTURES.story.headline,
    ])
    // Positionen lückenlos ab 1, sonst ignoriert Google die Kette.
    expect(crumbs.itemListElement.map((e: { position: number }) => e.position)).toEqual([1, 2, 3])
    // Die aktuelle Seite ist der letzte Eintrag und trägt bewusst kein item.
    expect(crumbs.itemListElement[1].item).toBe('https://ancientnerds.com/news-archive/')
    expect(crumbs.itemListElement[2].item).toBeUndefined()
    // Und die sichtbare Zeile zeigt dieselben Stationen.
    expect(html).toContain('<nav class="story-crumb">')
    expect(html).toContain('href="/news-archive/"')
  })

  it('Art.-50-Fußnote maschinenlesbar (data-ai-generated) und CommunityCta', () => {
    expect(html).toContain('data-ai-generated="true"')
    expect(html).toContain('AI-generated')
    expect(html).toContain('Keep exploring')
  })

  // Seit 2026-08-21: news_items.summary ist keine geschriebene Zusammenfassung,
  // sondern Headline + die ersten drei Fakten (summarizer.py). Als erster
  // Absatz wiederholte sie die H1 und danach die "Key facts"-Liste.
  it('kein summary-Absatz mehr — der Body beginnt mit dem post_text', () => {
    expect(html).not.toContain('story-summary')
    expect(html).not.toContain(FIXTURES.story.summary)
    expect(html).toContain('Archaeologists re-examined spoil heaps')
  })

  // post_text ist Tweet-Copy: die nackte Quell-URL am Ende stand mitten im
  // Artikel als toter Text. Sie gehört als echter Link zu den Quellen.
  it('angehängte Tweet-URL verlässt den Fließtext und wird eine Quelle', () => {
    const withLink = renderRoute({
      ...FIXTURES.story,
      web_sources: null,
      post_text: `${FIXTURES.story.post_text} https://www.english-heritage.org.uk/stonehenge/`,
    })
    const body = withLink.slice(withLink.indexOf('story-body'), withLink.indexOf('Key facts'))
    expect(body).not.toContain('english-heritage')
    expect(withLink).toContain('>Sources<')
    expect(withLink).toContain('href="https://www.english-heritage.org.uk/stonehenge/"')
    expect(withLink).toContain('english-heritage.org.uk') // nackter Host wie bei web_sources
  })

  it('eine URL, die schon in web_sources steht, erscheint nicht doppelt', () => {
    const dupe = renderRoute({
      ...FIXTURES.story,
      post_text: `${FIXTURES.story.post_text} https://en.natmus.dk/sun-chariot/`,
    })
    expect(dupe.match(/href="https:\/\/en\.natmus\.dk\/sun-chariot\/"/g)).toHaveLength(1)
  })

  // Der Player ersetzt das Standbild erst im Client; der SSR-Body muss
  // weiterhin den YouTube-Link tragen (Crawler und no-JS-Besucher).
  it('das Standbild bleibt serverseitig ein echter YouTube-Link', () => {
    expect(html).toContain('class="story-video-link"')
    expect(html).toContain('href="https://www.youtube.com/watch?v=abc123&amp;t=754s"')
  })

  it('Share-Knopf schon im SSR-Markup — Browser-APIs erst im Click-Handler', () => {
    expect(html).toContain('class="story-share"')
    expect(html).toContain('aria-label="Share story"')
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

  it('Pager Seite 2: Previous zurück auf /news-archive/, Leiste bis Seite 94', () => {
    const page2 = renderRoute(pyrefRoute('storyArchive_page2'))
    expect(page2).toContain('page 2 of 94')
    expect(page2).toContain('href="/news-archive/"')
    expect(page2).toContain('href="/news-archive/page/3"')
    // Nummerierte Leiste: 1 [2] 3 4 … 94 — letzte Seite in einem Hop,
    // aktuelle Seite als <span>, nicht als Link.
    expect(page2).toContain('href="/news-archive/page/4"')
    expect(page2).toContain('href="/news-archive/page/94"')
    expect(page2).toMatch(/aria-current="page"[^>]*>2</)
    expect(page2).toContain('…')
  })

  it('Nummerierte Leiste mitten im Archiv: 1 … 22 23 [24] 25 26 … 46', () => {
    // Eigenes Test-Payload — die route.json-Fixtures bleiben eingefroren.
    const html24 = renderRoute({ ...FIXTURES.storyArchive, page: 24, total_pages: 46 })
    expect(html24).toContain('href="/news-archive/"') // Seite 1
    expect(html24).toContain('href="/news-archive/page/22"')
    expect(html24).toContain('href="/news-archive/page/23"')
    expect(html24).toContain('href="/news-archive/page/25"')
    expect(html24).toContain('href="/news-archive/page/26"')
    expect(html24).toContain('href="/news-archive/page/46"') // letzte Seite
    // Fenster endet bei ±2 — davor/dahinter nur die Ellipse.
    expect(html24).not.toContain('href="/news-archive/page/21"')
    expect(html24).not.toContain('href="/news-archive/page/27"')
    // Die aktuelle Seite ist ein <span aria-current>, nie ein Link.
    expect(html24).not.toContain('href="/news-archive/page/24"')
    expect(html24).toMatch(/aria-current="page"[^>]*>24</)
    // KEIN rel=prev/next — Google ignoriert es seit 2019.
    expect(html24).not.toContain('rel="prev"')
    expect(html24).not.toContain('rel="next"')
  })

  it('Letzte Seite: kein Next, Leiste zeigt zurück zum Anfang', () => {
    const last = renderRoute({ ...FIXTURES.storyArchive, page: 46, total_pages: 46 })
    expect(last).not.toContain('Next')
    expect(last).toContain('href="/news-archive/"') // Seite 1
    expect(last).toContain('href="/news-archive/page/45"')
    expect(last).toMatch(/aria-current="page"[^>]*>46</)
  })

  it('Suchformular: plain GET auf /news-archive/ — funktioniert ohne JS', () => {
    expect(html).toContain('role="search"')
    expect(html).toContain('action="/news-archive/"')
    expect(html).toContain('name="q"')
  })

  it('aktive Suche: Wert im Feld, Trefferzeile, Pager trägt q weiter', () => {
    const searched = renderRoute({
      ...FIXTURES.storyArchive,
      q: 'chariot',
      total: 60,
      total_pages: 2,
    })
    expect(searched).toContain('value="chariot"')
    expect(searched).toContain('matching')
    expect(searched).toContain('href="/news-archive/page/2?q=chariot"')
    expect(searched).toContain('clear search')
  })

  it('leere Trefferliste nennt den Begriff und führt zurück ins Archiv', () => {
    const empty = renderRoute({
      ...FIXTURES.storyArchive,
      q: 'xenoglyph',
      stories: [],
      total: 0,
      total_pages: 1,
    })
    expect(empty).toContain('No stories match')
    expect(empty).toContain('Browse all stories')
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
