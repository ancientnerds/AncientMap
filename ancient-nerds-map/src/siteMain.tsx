/**
 * Entry for the site routes (/sites/, /sites/{country}, /sites/{country}/{slug}).
 *
 * SeoRoute resolves the matching page from the registry. A missing or
 * foreign payload (direct hit on /site.html — the legacy ?id= form answers
 * 301 since 1ad85ed) redirects at module level, before createRoot; the old
 * in-render "Site Not Found" dead end is gone.
 *
 * OfflineProvider stays: SitePopup (inside SitePage) consumes useOffline().
 * This is the only SEO entry whose tree actually reads that context.
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import { SeoRoute } from './seo/registry'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

const route = readInjectedRoute()

if (route?.type !== 'site' && route?.type !== 'sitesIndex' && route?.type !== 'country') {
  // Opened without server context — the sites index is the sensible destination.
  window.location.replace('/sites/')
} else {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <RouteProvider value={route}>
        <AuthProvider>
          <OfflineProvider>
            <SeoRoute />
          </OfflineProvider>
        </AuthProvider>
      </RouteProvider>
    </React.StrictMode>,
  )
}
