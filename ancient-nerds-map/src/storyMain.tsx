/**
 * Entry for the Story Archive routes (/news-archive/ and /news-archive/{slug}).
 *
 * The server injects the route payload and pre-renders the same content
 * into #root; SeoRoute resolves the matching page from the registry.
 * A missing or foreign payload (direct hit on /story.html) redirects at
 * module level, before createRoot — never during a render phase.
 *
 * No OfflineProvider: nothing under StoryPage/StoryArchivePage consumes
 * useOffline() (only Globe, FilterPanel and SitePopup do).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { SeoRoute } from './seo/registry'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

const route = readInjectedRoute()

if (route?.type !== 'story' && route?.type !== 'storyArchive') {
  // Opened without server context — the archive is the only sensible destination.
  window.location.replace('/news-archive/')
} else {
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
