import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import LyraRadarPage from './pages/LyraRadarPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <LyraRadarPage />
    </OfflineProvider>
  </React.StrictMode>,
)
