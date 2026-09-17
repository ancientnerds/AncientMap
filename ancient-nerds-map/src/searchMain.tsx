import './analytics/boot' // vitals, errors, scroll depth, outbound clicks (once per page)
import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import SearchPage from './pages/SearchPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <SearchPage />
    </OfflineProvider>
  </React.StrictMode>,
)
