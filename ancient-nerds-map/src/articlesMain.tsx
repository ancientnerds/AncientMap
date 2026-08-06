import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import ArticlesPage from './pages/ArticlesPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <ArticlesPage />
    </AuthProvider>
  </React.StrictMode>,
)
