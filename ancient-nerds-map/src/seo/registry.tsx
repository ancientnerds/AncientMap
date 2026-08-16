/**
 * Die eine Stelle, die alle indexierten Seitentypen kennt.
 *
 * Server (entry-server.tsx, Task 6) und Browser (die vier *Main.tsx) lösen
 * den Typ über dieselbe Tabelle auf. Kommt ein Seitentyp dazu, wird er hier
 * eingetragen — und ist damit sofort in beiden Welten vorhanden.
 *
 * article/articleIndex teilen sich ArticlesPage: sie verzweigt intern auf
 * den Route-Typ und behält daneben ihren Standalone-SPA-Modus für
 * /articles.html ohne Payload (Produktentscheidung, siehe articlesMain.tsx).
 */

import ArticlesPage from '../pages/ArticlesPage'
import ResearchIndexPage from '../pages/ResearchIndexPage'
import ResearchPaperPage from '../pages/ResearchPaperPage'
import { CountrySitesPage, SitesIndexPage } from '../pages/SiteListingPage'
import SitePage from '../pages/SitePage'
import StoryArchivePage from '../pages/StoryArchivePage'
import StoryPage from '../pages/StoryPage'
import type { AnRoute } from '../types/anRoute'
import * as meta from './meta'
import { useRoute } from './RouteContext'

type Entry = {
  Component: () => JSX.Element | null
  /** never = Schnittmenge aller Routen — jede konkrete *Meta-Funktion passt. */
  meta: (route: never) => meta.PageMeta
}

export const registry = {
  story: { Component: StoryPage, meta: meta.storyMeta },
  storyArchive: { Component: StoryArchivePage, meta: meta.storyArchiveMeta },
  site: { Component: SitePage, meta: meta.siteMeta },
  sitesIndex: { Component: SitesIndexPage, meta: meta.sitesIndexMeta },
  country: { Component: CountrySitesPage, meta: meta.countryMeta },
  research: { Component: ResearchPaperPage, meta: meta.researchMeta },
  researchIndex: { Component: ResearchIndexPage, meta: meta.researchIndexMeta },
  article: { Component: ArticlesPage, meta: meta.articleMeta },
  articleIndex: { Component: ArticlesPage, meta: meta.articleIndexMeta },
} satisfies Record<AnRoute['type'], Entry>

export const ROUTE_TYPES = Object.keys(registry) as AnRoute['type'][]

/** Rendert die zum Payload passende Seite. Server und Browser benutzen das. */
export function SeoRoute() {
  const route = useRoute()
  if (!route) return null
  const { Component } = registry[route.type]
  return <Component />
}
