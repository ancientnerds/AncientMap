import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import './styles/index.css'
import SitePage from './pages/SitePage'
import { CountrySitesPage, SitesIndexPage } from './pages/SiteListingPage'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'

const route = readInjectedRoute()

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
  // 'site' — SitePage reads the id from the route context.
  return <SitePage />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouteProvider value={route}>
      <AuthProvider>
        <OfflineProvider>
          <Entry />
        </OfflineProvider>
      </AuthProvider>
    </RouteProvider>
  </React.StrictMode>,
)
