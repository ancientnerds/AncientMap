import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import AccountPage from './pages/AccountPage'
import './styles/index.css'

document.body.classList.add('theme-red')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <AccountPage />
    </AuthProvider>
  </React.StrictMode>,
)
