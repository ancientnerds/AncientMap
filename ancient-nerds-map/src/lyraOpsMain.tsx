import './analytics/boot' // vitals, errors, scroll depth, outbound clicks (once per page)
import React from 'react'
import ReactDOM from 'react-dom/client'
import LyraOpsPage from './pages/LyraOpsPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LyraOpsPage />
  </React.StrictMode>,
)
