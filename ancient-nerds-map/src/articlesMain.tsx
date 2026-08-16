/**
 * Entry for the journal routes (/articles/ and /articles/{slug}).
 *
 * SeoRoute resolves ArticlesPage from the registry. A missing or foreign
 * payload (direct hit on the static /articles.html) redirects at module
 * level to /articles/, which serves the same shell with an articleIndex
 * payload — uniform with the other SEO entries.
 *
 * No OfflineProvider: nothing under ArticlesPage consumes useOffline()
 * (only Globe, FilterPanel and SitePopup do).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { SeoRoute } from './seo/registry'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

const route = readInjectedRoute()

if (route?.type !== 'article' && route?.type !== 'articleIndex') {
  window.location.replace('/articles/')
} else {
  // /articles/{slug} is served by the API inside this shell; ArticlesPage
  // selects an article from the hash, so seed it before the first render.
  if (route.type === 'article' && !window.location.hash) {
    window.history.replaceState(null, '', `${window.location.pathname}#${route.slug}`)
  }

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <RouteProvider value={route}>
        <AuthProvider>
          <SeoRoute />
        </AuthProvider>
      </RouteProvider>
    </React.StrictMode>,
  )
}
