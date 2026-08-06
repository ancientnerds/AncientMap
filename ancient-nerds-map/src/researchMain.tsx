import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import ResearchPaperPage from './pages/ResearchPaperPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <OfflineProvider>
        <ResearchPaperPage />
      </OfflineProvider>
    </AuthProvider>
  </React.StrictMode>,
)
