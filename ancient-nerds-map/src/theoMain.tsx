import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import TheoPage from './pages/TheoPage'
import './styles/index.css'

// AuthProvider mounts before TheoPage and promotes the post-OAuth cookie
// (`an_auth_token`, set by /api/auth/discord/callback) into localStorage.
// TheoPage reads the token from localStorage during its own mount effect,
// so without this wrapper a fresh Discord login lands here with an empty
// localStorage and the page wrongly shows "Continue with Discord".
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <OfflineProvider>
        <TheoPage />
      </OfflineProvider>
    </AuthProvider>
  </React.StrictMode>,
)
