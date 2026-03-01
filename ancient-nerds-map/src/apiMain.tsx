import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import ApiDocsPage from './pages/ApiDocsPage'
import './styles/index.css'

document.body.classList.add('theme-white')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <ApiDocsPage />
    </OfflineProvider>
  </React.StrictMode>,
)
