/**
 * Entry for the research routes (/research/, /research/{slug}).
 *
 * SeoRoute resolves paper and library listing from the registry — since
 * react-ssr Task 12 both payloads carry everything the pages render, so
 * there is no fetch and no redirect. Only a payload-less direct hit on the
 * static /research.html still redirects to the Theo library, exactly as
 * before the cutover.
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
