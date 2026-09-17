import './analytics/boot' // vitals, errors, scroll depth, outbound clicks (once per page)
import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import LibraryPage from './pages/LibraryPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <LibraryPage />
    </OfflineProvider>
  </React.StrictMode>,
)
