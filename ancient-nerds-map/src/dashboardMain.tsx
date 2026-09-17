// No './analytics/boot' and no tracker tag (vite.config.ts analyticsTag skips
// dashboard.html): the founders' own visits stay out of the data they read.
import React from 'react'
import ReactDOM from 'react-dom/client'
import DashboardPage from './pages/DashboardPage'
import './styles/dashboard.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <DashboardPage />
  </React.StrictMode>,
)
