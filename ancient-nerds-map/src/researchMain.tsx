/**
 * Entry for the research routes (/research/, /research/{slug}).
 *
 * The server pre-renders paper and library listing into #root through the
 * SSR sidecar; hydrateRoot adopts that markup instead of throwing it away
 * (react-ssr Task 15). Both payloads carry everything the pages render
 * (Task 12), so there is no fetch. Only a payload-less direct hit on the
 * static /research.html still redirects to the Theo library, exactly as
 * before the cutover — at module level, before any React root exists.
 *
 * No OfflineProvider: nothing under these pages consumes useOffline()
 * (only Globe, FilterPanel and SitePopup do).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { SeoRoute } from './seo/registry'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

const route = readInjectedRoute()

if (!route) {
  window.location.replace('/theo.html#research-library')
} else {
  ReactDOM.hydrateRoot(
    document.getElementById('root')!,
    <React.StrictMode>
      <RouteProvider value={route}>
        <AuthProvider>
          <SeoRoute />
        </AuthProvider>
      </RouteProvider>
    </React.StrictMode>,
  )
}
