/**
 * Entry for the site routes (/sites/, /sites/{country}, /sites/{country}/{slug}).
 *
 * The server pre-renders the same tree into #root through the SSR sidecar;
 * hydrateRoot adopts that markup instead of throwing it away (react-ssr
 * Task 15). A missing or foreign payload (direct hit on /site.html — the
 * legacy ?id= form answers 301 since 1ad85ed) redirects at module level,
 * before any React root exists.
 *
 * OfflineProvider stays: SitePopup (inside SitePage) consumes useOffline().
 * This is the only SEO entry whose tree actually reads that context — the
 * server tree omits the provider, which is hydration-safe because providers
 * emit no DOM and no server-rendered branch reads the context (SitePopup
 * mounts only after the post-hydration `interactive` effect).
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
  ReactDOM.hydrateRoot(
    document.getElementById('root')!,
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
