import './analytics/boot' // vitals, errors, scroll depth, outbound clicks (once per page)
import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import LyraPage from './pages/LyraPage'
import './styles/index.css'

// AuthProvider mounts before LyraPage for the same reason theoMain names it:
// it promotes the post-OAuth cookie (`an_auth_token`, set by
// /api/auth/discord/callback) into localStorage and announces it, so the sign-in
// gate of the chat opens instead of sending the visitor in a circle. Without
// it, /lyra.html — the landing page's main Lyra link — was a login that always
// ended on the gate again.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <OfflineProvider>
        <LyraPage />
      </OfflineProvider>
    </AuthProvider>
  </React.StrictMode>,
)
