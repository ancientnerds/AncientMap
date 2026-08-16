/**
 * Fixtures für die SEO-Tests: die Route-Payloads aus pyref/.
 *
 * Beide Seiten jeder Vergleichsprüfung stammen aus EINEM Fixture-Satz:
 * scripts/gen_meta_reference.py rendert die Python-Referenz-Heads UND
 * schreibt die zugehörigen Route-Payloads — Payload und Soll-Head können
 * also nicht auseinanderlaufen. Für sitesIndex ist das Payload wörtlich
 * SeoPage.route; alle übrigen Typen tragen seit den Cutovers (Tasks
 * 10–14) die rohen snake_case-Zeilenfelder — Formatierung lebt in
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

/** Referenz-Head aus pipeline/seo_pages.py, CRLF-normalisiert. */
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
