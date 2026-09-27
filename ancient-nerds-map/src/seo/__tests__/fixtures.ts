/**
 * Fixtures für die SEO-Tests: die Route-Payloads aus pyref/.
 *
 * pyref/ ist seit Task 16 ein EINGEFRORENER Fixture-Satz: die Heads hat
 * der gelöschte Python-Renderer (pipeline/seo_pages.py, via
 * scripts/gen_meta_reference.py — beide weg) einmal byte-genau erzeugt,
 * die zugehörigen Route-Payloads stammen aus demselben Lauf, Payload und
 * Soll-Head können also nicht auseinanderlaufen. Die Dateien ändern sich
 * nur noch, wenn jemand meta.ts BEWUSST ändert — dann von Hand nachziehen
 * und die Abweichung im Commit begründen. Alle Typen tragen die rohen
 * snake_case-Zeilenfelder (Cutovers Tasks 10–14) — Formatierung lebt in
 * src/seo/.
 *
 * Eine Ausnahme: `landing.route.json` ist von Hand geschrieben — die
 * Startseite hatte nie einen Python-Renderer, es gibt also nichts
 * einzufrieren; die Datei darf mit dem Payload-Builder mitwachsen.
 */

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type {
  AnRoute,
  ArticleIndexRoute,
  ArticleRoute,
  CountryRoute,
  LandingRoute,
  ResearchIndexRoute,
  ResearchRoute,
  SiteRoute,
  SitesIndexRoute,
  StoryArchiveRoute,
  StoryRoute,
} from '../../types/anRoute'

export const PYREF_DIR = join(dirname(fileURLToPath(import.meta.url)), 'pyref')

/** Eingefrorener Referenz-Head des gelöschten Python-Renderers, CRLF-normalisiert. */
export function pyrefHead(name: string): string {
  return readFileSync(join(PYREF_DIR, `${name}.html`), 'utf8').replace(/\r\n/g, '\n')
}

/** Route-Payload, das zum Referenz-Head `name` gehört. */
export function pyrefRoute(name: string): AnRoute {
  return JSON.parse(readFileSync(join(PYREF_DIR, `${name}.route.json`), 'utf8')) as AnRoute
}

export const FIXTURES = {
  story: pyrefRoute('story') as StoryRoute,
  storyArchive: pyrefRoute('storyArchive') as StoryArchiveRoute,
  site: pyrefRoute('site') as SiteRoute,
  sitesIndex: pyrefRoute('sitesIndex') as SitesIndexRoute,
  country: pyrefRoute('country') as CountryRoute,
  research: pyrefRoute('research') as ResearchRoute,
  researchIndex: pyrefRoute('researchIndex') as ResearchIndexRoute,
  article: pyrefRoute('article') as ArticleRoute,
  articleIndex: pyrefRoute('articleIndex') as ArticleIndexRoute,
  landing: pyrefRoute('landing') as LandingRoute,
}

/**
 * A Claude-written paper with every optional part (studio spec 2026-09-26
 * §2.7, §3.7), handwritten on top of the frozen research payload — like
 * landing.route.json there is no Python head to freeze for it. body_html is
 * byte for byte what pipeline/research_html_renderer.inject_evidence_anchors
 * emits for REPORT/EVIDENCE/MOMENTS in
 * tests/pipeline/test_research_evidence_anchors.py (the reference line cut).
 */
export const RESEARCH_WITH_EXTRAS: ResearchRoute = {
  ...FIXTURES.research,
  body_html:
    '<h2 id="the-quarry">The Quarry</h2>\n' +
    '<p id="ev-01" class="theo-evidence">The “Stone of the Pregnant Woman” weighs about 1,000 tonnes – roughly the mass of <em>three</em> jumbo jets [1] [2].' +
    ' <a class="theo-evidence-video" href="https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=312s" target="_blank" rel="noopener noreferrer" title="Watch this passage in the video: Baalbek: the 1,000-tonne question">Video at 5:12</a></p>\n' +
    '<p id="ev-02" class="theo-evidence"><span class="theo-evidence-anchor" id="ev-03"></span>Ruprechtsberger’s team dated the quarry face to the 1st century AD… a date others dispute [3].</p>',
  videos: [
    {
      youtube_id: 'dQw4w9WgXcQ',
      title: 'Baalbek: the 1,000-tonne question',
      published_at: '2026-10-01T15:00:00+00:00',
      // Our own studio thumbnail (owner decision #13); the posterless variant
      // is covered by PaperVideo.test.tsx.
      poster: '/data/research-images/7f00aa00-0000-4000-8000-000000000000/video_dQw4w9WgXcQ.jpg',
    },
  ],
  corrections: [
    {
      date: '2026-10-02',
      text: 'The quarry date now cites the 2014 excavation report.',
      evidence_id: 'ev-02',
      holds_anchor: false,
    },
    {
      date: '2026-10-04',
      text: 'Removed the claim about a fourth monolith; the cited survey does not support it.',
      evidence_id: 'ev-05',
      holds_anchor: true,
    },
  ],
  writer: {
    model: 'claude-opus-5-5',
    tool: 'claude-code',
    research_model: 'MiniMax-M3',
    published: 'automatic',
    human_review: false,
  },
}
