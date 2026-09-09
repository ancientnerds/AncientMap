/**
 * Entry for the homepage live sections. The API (GET /home) renders
 * LandingLive into #root through the SSR sidecar and injects the payload;
 * this entry adopts that markup. Without a payload — the static index.html
 * nginx serves while the API restarts — there is nothing to hydrate and
 * nothing to do. The hero and the screenshot sections never touch React.
 *
 * LandingLive directly instead of SeoRoute: the registry statically imports
 * every page and resolves them through a dynamic lookup, so Rollup cannot
 * tree-shake the siblings — the homepage would ship SitePopup and the
 * mapbox theme. AuthProvider is left out for the same reason nothing under
 * LandingLive reads it; providers emit no DOM, so the tree the server
 * rendered (entry-server.tsx) still hydrates cleanly.
 *
 * No ./styles/index.css: it sets html,body{overflow:hidden} for the app
 * shell, which would kill the homepage scroll. The page links
 * styles/landing.css, and that imports tokens.css.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'

import LandingLive from './pages/LandingLive'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'

const route = readInjectedRoute()
const root = document.getElementById('root')
if (route?.type === 'landing' && root) {
  ReactDOM.hydrateRoot(
    root,
    <React.StrictMode>
      <RouteProvider value={route}>
        <LandingLive />
      </RouteProvider>
    </React.StrictMode>,
  )
}
