import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import CardsPage from './pages/CardsPage'
import './styles/index.css'

document.body.classList.add('theme-amber')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <CardsPage />
    </AuthProvider>
  </React.StrictMode>,
)
