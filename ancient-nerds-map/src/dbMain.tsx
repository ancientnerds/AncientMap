import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import DbAuditPage from './pages/DbAuditPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <DbAuditPage />
    </OfflineProvider>
  </React.StrictMode>,
)
