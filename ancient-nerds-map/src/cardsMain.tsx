import './analytics/boot' // vitals, errors, scroll depth, outbound clicks (once per page)
import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import CardsPage from './pages/CardsPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <CardsPage />
    </AuthProvider>
  </React.StrictMode>,
)
