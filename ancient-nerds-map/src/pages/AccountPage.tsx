/**
 * AccountPage — User account with Discord profile and Lyra credits.
 * Accessed via /account.html (separate Vite entry point).
 *
 * On first load after OAuth, reads ?token= from URL and stores it.
 */

import { useEffect, useState, useCallback } from 'react'
import { config } from '../config'
import { useAuth } from '../contexts/AuthContext'
import PageHeader from '../components/layout/PageHeader'
import '../styles/account.css'

interface UsageEntry {
  input_tokens: number
  output_tokens: number
  voyage_tokens: number
  credits_used: number
  created_at: string
}

interface GrantEntry {
  amount: number
  reason: string
  created_at: string
}

const REASON_LABELS: Record<string, string> = {
  og_nerd_role: 'OG Nerd Role',
  founder_role: 'Founder Role',
  patreon_tier_1: 'Patreon Tier 1',
  patreon_tier_2: 'Patreon Tier 2',
  patreon_tier_3: 'Patreon Tier 3',
}

export default function AccountPage() {
  const { user, token, isLoggedIn, isLoading, logout } = useAuth()
  const [usage, setUsage] = useState<UsageEntry[]>([])
  const [grants, setGrants] = useState<GrantEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  // Handle OAuth error callback (?error= in URL). Token is now delivered via cookie
  // and consumed by AuthContext on mount — no ?token= in URL anymore.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const urlError = params.get('error')

    if (urlError) {
      setError(`Login failed: ${urlError.replace(/_/g, ' ')}`)
      window.history.replaceState({}, '', '/account.html')
    }
  }, [])

  // Fetch credits + usage when logged in
  const fetchCredits = useCallback(async () => {
    if (!token) return
    try {
      const resp = await fetch(`${config.api.baseUrl}/auth/credits`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (resp.ok) {
        const data = await resp.json()
        setUsage(data.usage || [])
        setGrants(data.grants || [])
      }
    } catch {
      // Non-critical
    }
  }, [token])

  useEffect(() => {
    if (isLoggedIn) fetchCredits()
  }, [isLoggedIn, fetchCredits])

  const handleSignIn = () => {
    window.location.href = `${config.api.baseUrl}/auth/discord`
  }

  if (isLoading) {
    return (
      <div className="account-page">
        <PageHeader currentPage="account">
          <span className="page-header-title">Account</span>
        </PageHeader>
        <div className="account-loading">Loading...</div>
      </div>
    )
  }

  return (
    <div className="account-page">
      <PageHeader currentPage="account">
        <span className="page-header-title">Account</span>
      </PageHeader>

      <div className="account-content">
        {error && <div className="account-error">{error}</div>}

        {!isLoggedIn ? (
          <div className="account-signin-container">
            <img src="/lyra.png" alt="Lyra" className="account-lyra-avatar" />
            <h2 className="account-signin-title">Sign in to Ancient Nerds</h2>
            <p className="account-signin-desc">
              Connect your Discord account to access Lyra and track your credits.
            </p>
            <button className="account-discord-btn" onClick={handleSignIn}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.36-.698.772-1.362 1.225-1.993a.076.076 0 0 0-.041-.107 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.12-.094.246-.194.373-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
              </svg>
              Continue with Discord
            </button>
          </div>
        ) : (
          <div className="account-profile">
            {/* Profile card */}
            <div className="account-card">
              <div className="account-card-header">
                {user?.avatar_url ? (
                  <img src={user.avatar_url} alt={user.username} className="account-avatar" />
                ) : (
                  <div className="account-avatar-placeholder">
                    {user?.username?.charAt(0)?.toUpperCase() || '?'}
                  </div>
                )}
                <div className="account-card-info">
                  <h2 className="account-username">{user?.username}</h2>
                  <div className="account-badges">
                    {user?.is_founder && (
                      <span className="account-badge founder">Founder</span>
                    )}
                    {user?.is_og_nerd && (
                      <span className="account-badge og-nerd">OG Nerd</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Credits */}
              <div className="account-credits-section">
                <div className="account-credits-label">Lyra Credits</div>
                <div className="account-credits-value">
                  {user?.credits === -1 ? '∞' : (user?.credits?.toLocaleString() ?? 0)}
                </div>
                <div className="account-credits-note">
                  {user?.credits === -1
                    ? 'Unlimited access — thank you, Founder!'
                    : '1 credit = 100 tokens (input + output)'}
                </div>
              </div>

              <button className="account-logout-btn" onClick={logout}>
                Sign Out
              </button>
            </div>

            {/* Credit grants */}
            {grants.length > 0 && (
              <div className="account-section">
                <h3 className="account-section-title">Credit Grants</h3>
                <div className="account-table-wrap">
                  <table className="account-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Reason</th>
                        <th>Credits</th>
                      </tr>
                    </thead>
                    <tbody>
                      {grants.map((g, i) => (
                        <tr key={i}>
                          <td>{new Date(g.created_at).toLocaleDateString()}</td>
                          <td>{REASON_LABELS[g.reason] || g.reason}</td>
                          <td className="account-credits-positive">+{g.amount.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Usage history */}
            {usage.length > 0 && (
              <div className="account-section">
                <h3 className="account-section-title">Recent Usage</h3>
                <div className="account-table-wrap">
                  <table className="account-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Input</th>
                        <th>Output</th>
                        <th>Credits</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usage.map((u, i) => (
                        <tr key={i}>
                          <td>{new Date(u.created_at).toLocaleDateString()}</td>
                          <td>{u.input_tokens.toLocaleString()}</td>
                          <td>{u.output_tokens.toLocaleString()}</td>
                          <td className="account-credits-negative">-{u.credits_used}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
