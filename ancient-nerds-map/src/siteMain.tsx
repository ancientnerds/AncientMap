import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import './styles/index.css'
import SitePage from './pages/SitePage'
import { CountrySitesPage, SitesIndexPage } from './pages/SiteListingPage'
import { anRoute } from './types/anRoute'

const route = anRoute()

function Entry() {
  if (route?.type === 'sitesIndex') return <SitesIndexPage countries={route.countries} />
  if (route?.type === 'country') {
    return (
      <CountrySitesPage
        country={route.country}
        sections={route.sections}
        periodSpan={route.periodSpan}
        total={route.total}
      />
    )
  }
  // 'site', or the legacy /site.html?id= entry point
  return <SitePage />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <OfflineProvider>
        <Entry />
      </OfflineProvider>
    </AuthProvider>
  </React.StrictMode>,
)
