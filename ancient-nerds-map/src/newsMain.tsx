import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import NewsFeedPage from './pages/NewsFeedPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <NewsFeedPage />
    </OfflineProvider>
  </React.StrictMode>,
)
