/**
 * Entry for the journal routes (/articles/, /articles/{slug}) and the
 * standalone /articles.html SPA.
 *
 * WITH a server-injected payload the sidecar has pre-rendered the same tree
 * into #root; hydrateRoot adopts that markup instead of throwing it away
 * (react-ssr Task 15). The composition inside StrictMode must stay
 * identical to entry-server.tsx. The payload carries everything (Task 13:
 * articleIndex list, article body_html), so those modes render with no
 * fetch and no hash routing.
 *
 * WITHOUT a payload — a direct hit on the static /articles.html — there is
 * no server markup to hydrate, so this stays createRoot: ArticlesPage
 * renders in standalone SPA mode, fetches its own data and does hash
 * routing, unchanged.
 *
 * Deliberately NO module-level redirect here (unlike story/site/research):
 * product decision 2026-08 — /articles.html (indexed, avg. position 2.1)
 * and /articles/ both stay; a 301 comes only once Google has indexed the
 * new hub. A location.replace would also drop #slug deep links, which the
 * standalone page itself writes (ArticlesPage.tsx, openArticle).
 * Do not re-unify this.
 *
 * No OfflineProvider: nothing under ArticlesPage consumes useOffline()
 * (only Globe, FilterPanel and SitePopup do).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import ArticlesPage from './pages/ArticlesPage'
import { SeoRoute } from './seo/registry'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

const route = readInjectedRoute()
const container = document.getElementById('root')!

if (route) {
  ReactDOM.hydrateRoot(
    container,
    <React.StrictMode>
      <RouteProvider value={route}>
        <AuthProvider>
          <SeoRoute />
        </AuthProvider>
      </RouteProvider>
    </React.StrictMode>,
  )
} else {
  ReactDOM.createRoot(container).render(
    <React.StrictMode>
      <RouteProvider value={route}>
        <AuthProvider>
          <ArticlesPage />
        </AuthProvider>
      </RouteProvider>
    </React.StrictMode>,
  )
}
