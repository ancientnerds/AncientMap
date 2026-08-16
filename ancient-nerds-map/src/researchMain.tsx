import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import ResearchPaperPage from './pages/ResearchPaperPage'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

const route = readInjectedRoute()

function Entry() {
  // The research index has its own listing page in the Theo library; sending
  // visitors there keeps one canonical listing instead of two.
  if (route?.type === 'researchIndex') {
    window.location.replace('/theo.html#research-library')
    return null
  }
  return <ResearchPaperPage />
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
