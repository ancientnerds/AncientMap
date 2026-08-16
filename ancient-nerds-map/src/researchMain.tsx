/**
 * Entry for the research routes (/research/{slug}).
 *
 * SeoRoute resolves the paper page from the registry. researchIndex and
 * missing/foreign payloads (direct hit on /research.html) redirect at
 * module level, before createRoot — the research index has its own listing
 * page in the Theo library, and one canonical listing beats two.
 *
 * No OfflineProvider: nothing under ResearchPaperPage consumes useOffline()
 * (only Globe, FilterPanel and SitePopup do).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { SeoRoute } from './seo/registry'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

const route = readInjectedRoute()

if (route?.type !== 'research') {
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
