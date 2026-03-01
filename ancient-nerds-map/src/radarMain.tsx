import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import LyraRadarPage from './pages/LyraRadarPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <OfflineProvider>
        <LyraRadarPage />
      </OfflineProvider>
    </AuthProvider>
  </React.StrictMode>,
)
