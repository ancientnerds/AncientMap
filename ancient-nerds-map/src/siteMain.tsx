import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import './styles/index.css'
import SitePage from './pages/SitePage'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <OfflineProvider>
        <SitePage />
      </OfflineProvider>
    </AuthProvider>
  </React.StrictMode>,
)
