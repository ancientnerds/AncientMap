import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import NewsFeedPage from './pages/NewsFeedPage'
import './styles/index.css'

document.body.classList.add('theme-blue')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <NewsFeedPage />
    </OfflineProvider>
  </React.StrictMode>,
)
