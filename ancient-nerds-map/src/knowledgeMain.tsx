import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import KnowledgePage from './pages/KnowledgePage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <KnowledgePage />
    </OfflineProvider>
  </React.StrictMode>,
)
