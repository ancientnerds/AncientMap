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
 */

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type {
  AnRoute,
  ArticleIndexRoute,
  ArticleRoute,
  CountryRoute,
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
}
