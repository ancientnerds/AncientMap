/**
 * AccountPage — User account with Discord profile and Lyra credits.
 * Accessed via /account.html (separate Vite entry point).
 *
 * On first load after OAuth, reads ?token= from URL and stores it.
 */

import { useEffect, useState, useCallback, useRef } from 'react'
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
  grant_period: string | null
  created_at: string
}

interface AdminUser {
  id: string
  username: string
  avatar_url: string | null
  credits: number
  is_unlimited: boolean
  is_founder: boolean
  is_og_nerd: boolean
  roles: string[]
  last_login: string | null
}

type CreditAction = 'add' | 'set' | 'remove' | 'set_unlimited'

interface ActionOption {
  value: CreditAction
  label: string
  desc: string
  color: string
}

const CREDIT_ACTIONS: ActionOption[] = [
  { value: 'add', label: 'Add', desc: 'Add credits to balance', color: '#22c55e' },
  { value: 'set', label: 'Set to', desc: 'Set balance to exact amount', color: '#3b82f6' },
  { value: 'remove', label: 'Remove', desc: 'Subtract credits from balance', color: '#ef4444' },
]

function ActionDropdown({ value, onChange }: {
  value: CreditAction
  onChange: (v: CreditAction) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const selected = CREDIT_ACTIONS.find(a => a.value === value)!

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="action-dropdown" ref={ref}>
      <button
        className="action-dropdown-trigger"
        onClick={() => setOpen(!open)}
        style={{ borderColor: open ? selected.color : undefined }}
      >
        <span className="action-dropdown-dot" style={{ background: selected.color }} />
        <span className="action-dropdown-label">{selected.label}</span>
        <span className="action-dropdown-arrow">{open ? '\u25B4' : '\u25BE'}</span>
      </button>
      {open && (
        <div className="action-dropdown-panel">
          {CREDIT_ACTIONS.map(opt => (
            <button
              key={opt.value}
              className={`action-dropdown-item ${opt.value === value ? 'active' : ''}`}
              onClick={() => { onChange(opt.value); setOpen(false) }}
            >
              <span className="action-dropdown-dot" style={{ background: opt.color }} />
              <div className="action-dropdown-item-text">
                <span className="action-dropdown-item-label">{opt.label}</span>
                <span className="action-dropdown-item-desc">{opt.desc}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const REASON_LABELS: Record<string, string> = {
  og_nerd_role: 'OG Nerd Role',
  founder_role: 'Founder Role',
  founder_grant: 'Founder Grant',
  unlimited_set: 'Unlimited Enabled',
  unlimited_removed: 'Unlimited Removed',
  monthly_patron_explorer: 'Patron Explorer (Monthly)',
  monthly_patron_archaeologist: 'Patron Archaeologist (Monthly)',
  monthly_patron_scholar: 'Patron Scholar (Monthly)',
  team_role: 'Team Role',
  researcher_role: 'Researcher Role',
  adeptus_major_role: 'Adeptus Major Role',
  adeptus_minor_role: 'Adeptus Minor Role',
  initiate_role: 'Initiate Role',
  adept_role: 'Adept Role',
  neophyte_role: 'Neophyte Role',
  ancient_nerds_role: 'Ancient Nerds Role',
}

// Discord role ID → display info for profile badges (glass style: colored text on translucent bg)
const ROLE_DISPLAY: Record<string, { name: string; color: string }> = {
  '933105341292486707': { name: 'Founder', color: '#00ff2e' },
  '972439407086944266': { name: 'OG Nerd', color: '#f86600' },
  '933104896310378546': { name: 'Team', color: '#00ffa5' },
  '933105424264220815': { name: 'Researcher', color: '#2ecc71' },
  '1083087065010417775': { name: 'Adeptus Major', color: '#ffb500' },
  '1083088517510484009': { name: 'Adeptus Minor', color: '#ffe400' },
  '1083088899494129695': { name: 'Initiate', color: '#e0c32b' },
  '1083088426074640466': { name: 'Adept', color: '#eee247' },
  '1083088078379417630': { name: 'Neophyte', color: '#f1dd80' },
  '968574705760100392': { name: 'Ancient Nerds', color: '#db2424' },
  '1083785196861657198': { name: 'Explorer', color: '#c34586' },
  '1083785565398380544': { name: 'Archaeologist', color: '#9553ff' },
  '1083785826586075278': { name: 'Scholar', color: '#00b0fc' },
}

// Short labels for admin badge display
const ROLE_SHORT: Record<string, string> = {
  '933105341292486707': 'F',
  '972439407086944266': 'OG',
  '933104896310378546': 'TM',
  '933105424264220815': 'RS',
  '1083087065010417775': 'A+',
  '1083088517510484009': 'A-',
  '1083088899494129695': 'IN',
  '1083088426074640466': 'AD',
  '1083088078379417630': 'NP',
  '968574705760100392': 'AN',
  '1083785196861657198': 'EX',
  '1083785565398380544': 'AR',
  '1083785826586075278': 'SC',
}

const DISCORD_INVITE_URL = 'https://discord.gg/ancientnerds'
const PATREON_URL = 'https://patreon.com/ancientnerds'

export default function AccountPage() {
  const { user, token, isLoggedIn, isLoading, logout } = useAuth()
  const [usage, setUsage] = useState<UsageEntry[]>([])
  const [grants, setGrants] = useState<GrantEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [grantsExpanded, setGrantsExpanded] = useState(false)
  const [usageExpanded, setUsageExpanded] = useState(false)

  // Admin state
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([])
  const [adminSearch, setAdminSearch] = useState('')
  const [adminLoading, setAdminLoading] = useState(false)
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [creditAction, setCreditAction] = useState<CreditAction>('add')
  const [creditAmount, setCreditAmount] = useState(100)
  const [adminError, setAdminError] = useState<string | null>(null)
  const [adminSuccess, setAdminSuccess] = useState<string | null>(null)
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()

  // Handle OAuth error callback (?error= in URL). Token is now delivered via cookie
  // and consumed by AuthContext on mount — no ?token= in URL anymore.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const urlError = params.get('error')

    if (urlError) {
      if (urlError === 'not_in_guild') {
        setError('guild_required')
      } else {
        setError(`Login failed: ${urlError.replace(/_/g, ' ')}`)
      }
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

  // Admin: fetch users
  const fetchAdminUsers = useCallback(async (q = '') => {
    if (!token) return
    setAdminLoading(true)
    setAdminError(null)
    try {
      const params = q ? `?q=${encodeURIComponent(q)}` : ''
      const resp = await fetch(`${config.api.baseUrl}/auth/admin/users${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (resp.ok) {
        const data = await resp.json()
        setAdminUsers(data.users)
      } else {
        setAdminError('Failed to load users')
      }
    } catch {
      setAdminError('Failed to load users')
    } finally {
      setAdminLoading(false)
    }
  }, [token])

  // Fetch admin users on mount if founder
  useEffect(() => {
    if (isLoggedIn && user?.is_founder) fetchAdminUsers()
  }, [isLoggedIn, user?.is_founder, fetchAdminUsers])

  // Debounced search
  const handleAdminSearch = (value: string) => {
    setAdminSearch(value)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => fetchAdminUsers(value), 300)
  }

  // Admin: adjust credits
  const handleCreditAdjust = async (action: CreditAction, amount: number) => {
    if (!token || !selectedUser) return
    setAdminError(null)
    setAdminSuccess(null)
    try {
      const resp = await fetch(`${config.api.baseUrl}/auth/admin/credits`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_id: selectedUser.id, action, amount }),
      })
      if (resp.ok) {
        const data = await resp.json()
        const newCredits = data.new_credits as number
        const newUnlimited = data.is_unlimited as boolean | undefined
        const actionLabel = action === 'set_unlimited'
          ? (amount !== 0 ? 'set to unlimited' : 'removed unlimited')
          : action === 'set' ? 'set to' : action === 'add' ? 'increased by' : 'decreased by'
        const creditsDisplay = newUnlimited ? '∞' : newCredits.toLocaleString()
        setAdminSuccess(
          `${selectedUser.username}: credits ${actionLabel} ${action === 'set_unlimited' ? '' : amount} → now ${creditsDisplay}`
        )
        // Update local list
        setAdminUsers(prev => prev.map(u =>
          u.id === selectedUser.id
            ? { ...u, credits: newCredits, is_unlimited: newUnlimited ?? u.is_unlimited }
            : u
        ))
        setSelectedUser(prev => prev
          ? { ...prev, credits: newCredits, is_unlimited: newUnlimited ?? prev.is_unlimited }
          : null
        )
      } else {
        const data = await resp.json().catch(() => null)
        setAdminError(data?.detail || 'Failed to adjust credits')
      }
    } catch {
      setAdminError('Failed to adjust credits')
    }
  }

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
        {error === 'guild_required' ? (
          <div className="account-error">
            You need to join our Discord server to sign in.{' '}
            <a href={DISCORD_INVITE_URL} target="_blank" rel="noopener noreferrer"
               style={{ color: '#7289da', textDecoration: 'underline' }}>
              Join Discord
            </a>
          </div>
        ) : error ? (
          <div className="account-error">{error}</div>
        ) : null}

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
                    {user?.roles?.map(roleId => {
                      const info = ROLE_DISPLAY[roleId]
                      if (!info) return null
                      return (
                        <span key={roleId} className="account-badge" style={{
                          background: `${info.color}1F`,
                          color: info.color,
                          border: `1px solid ${info.color}40`,
                        }}>
                          {info.name}
                        </span>
                      )
                    })}
                  </div>
                </div>
              </div>

              {/* Credits */}
              <div className="account-credits-section">
                <div className="account-credits-label">Lyra Credits</div>
                <div className="account-credits-value">
                  {user?.is_unlimited ? '∞' : (user?.credits?.toLocaleString() ?? 0)}
                </div>
                <div className="account-credits-note">
                  {user?.is_unlimited
                    ? `Unlimited access${user?.is_founder ? ' — thank you, Founder!' : ''}`
                    : '1 credit = 100 tokens (input + output)'}
                </div>
                {user?.next_grant_date && (
                  <div className="account-credits-note" style={{ marginTop: '4px', fontSize: '0.8em', opacity: 0.7 }}>
                    Next credit grant: {new Date(user.next_grant_date).toLocaleDateString()}
                  </div>
                )}
                {user && !user.is_unlimited && user.tier === 'free' && (
                  <a
                    href={PATREON_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="account-upgrade-link"
                    style={{
                      display: 'inline-block',
                      marginTop: '8px',
                      padding: '6px 14px',
                      background: '#f96854',
                      color: '#fff',
                      borderRadius: '6px',
                      fontSize: '0.85em',
                      textDecoration: 'none',
                    }}
                  >
                    Upgrade on Patreon
                  </a>
                )}
              </div>

              <button className="account-logout-btn" onClick={logout}>
                Sign Out
              </button>
            </div>

            {/* Credit grants */}
            {grants.length > 0 && (() => {
              const sorted = [...grants].sort((a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
              )
              const visible = grantsExpanded ? sorted : sorted.slice(0, 10)
              return (
                <div className="account-section">
                  <h3 className="account-section-title">Credit Grants</h3>
                  <div className="account-table-wrap">
                    <table className="account-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Reason</th>
                          <th>Period</th>
                          <th>Credits</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((g, i) => (
                          <tr key={i}>
                            <td>{new Date(g.created_at).toLocaleDateString()}</td>
                            <td>{REASON_LABELS[g.reason] || g.reason}</td>
                            <td>{g.grant_period || '—'}</td>
                            <td className={g.amount >= 0 ? 'account-credits-positive' : 'account-credits-negative'}>
                              {g.amount > 0 ? '+' : ''}{g.amount.toLocaleString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {sorted.length > 10 && (
                    <button className="account-expand-btn" onClick={() => setGrantsExpanded(!grantsExpanded)}>
                      <span className={`account-expand-arrow ${grantsExpanded ? 'expanded' : ''}`}>{'\u25B6'}</span>
                      {grantsExpanded ? 'Show less' : `Show all ${sorted.length}`}
                    </button>
                  )}
                </div>
              )
            })()}

            {/* Usage history */}
            {usage.length > 0 && (() => {
              const sorted = [...usage].sort((a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
              )
              const visible = usageExpanded ? sorted : sorted.slice(0, 10)
              return (
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
                        {visible.map((u, i) => (
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
                  {sorted.length > 10 && (
                    <button className="account-expand-btn" onClick={() => setUsageExpanded(!usageExpanded)}>
                      <span className={`account-expand-arrow ${usageExpanded ? 'expanded' : ''}`}>{'\u25B6'}</span>
                      {usageExpanded ? 'Show less' : `Show all ${sorted.length}`}
                    </button>
                  )}
                </div>
              )
            })()}

            {/* Founder Admin Panel */}
            {user?.is_founder && (
              <div className="account-section admin-panel">
                <h3 className="account-section-title">Admin — Credit Management</h3>

                <input
                  type="text"
                  className="admin-search"
                  placeholder="Search users by name..."
                  value={adminSearch}
                  onChange={e => handleAdminSearch(e.target.value)}
                />

                {adminError && <div className="admin-error">{adminError}</div>}
                {adminSuccess && <div className="admin-success">{adminSuccess}</div>}

                {adminLoading ? (
                  <div className="admin-loading">Loading users...</div>
                ) : (
                  <div className="admin-user-list">
                    {adminUsers.map(u => (
                      <div
                        key={u.id}
                        className={`admin-user-row ${selectedUser?.id === u.id ? 'selected' : ''}`}
                        onClick={() => {
                          setSelectedUser(selectedUser?.id === u.id ? null : u)
                          setAdminSuccess(null)
                          setAdminError(null)
                        }}
                      >
                        {u.avatar_url ? (
                          <img src={u.avatar_url} alt={u.username} className="admin-user-avatar" />
                        ) : (
                          <div className="admin-user-avatar-placeholder">
                            {u.username.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <span className="admin-user-name">{u.username}</span>
                        <div className="admin-user-badges">
                          {(u.roles || []).map(roleId => {
                            const info = ROLE_DISPLAY[roleId]
                            if (!info) return null
                            const short = ROLE_SHORT[roleId] || info.name.slice(0, 2)
                            return (
                              <span
                                key={roleId}
                                className="account-badge"
                                style={{ color: info.color, borderColor: `${info.color}44`, background: `${info.color}18` }}
                                title={info.name}
                              >
                                {short}
                              </span>
                            )
                          })}
                        </div>
                        <span className="admin-user-credits">
                          {u.is_unlimited ? '∞' : u.credits.toLocaleString()}
                        </span>
                      </div>
                    ))}
                    {adminUsers.length === 0 && (
                      <div className="admin-loading">No users found</div>
                    )}
                  </div>
                )}

                {/* Credit adjustment form */}
                {selectedUser && (
                  <div className="admin-credit-form">
                    <div className="admin-credit-form-header">
                      Adjust credits for <strong>{selectedUser.username}</strong>
                      <span className="admin-credit-form-current">
                        (current: {selectedUser.is_unlimited ? '∞' : selectedUser.credits.toLocaleString()})
                      </span>
                    </div>
                    <div className="admin-credit-controls">
                      <ActionDropdown value={creditAction} onChange={setCreditAction} />
                      <input
                        type="number"
                        className="admin-amount-input"
                        value={creditAmount}
                        onChange={e => setCreditAmount(parseInt(e.target.value) || 0)}
                      />
                      <button
                        className="admin-apply-btn"
                        onClick={() => handleCreditAdjust(creditAction, creditAmount)}
                      >
                        Apply
                      </button>
                    </div>
                    <div className="admin-shortcuts">
                      <button className="admin-shortcut-btn add" onClick={() => handleCreditAdjust('add', 100)}>
                        +100
                      </button>
                      <button className="admin-shortcut-btn add" onClick={() => handleCreditAdjust('add', 500)}>
                        +500
                      </button>
                      <button className="admin-shortcut-btn add" onClick={() => handleCreditAdjust('add', 1000)}>
                        +1000
                      </button>
                      {!selectedUser.is_unlimited && (
                        <button className="admin-shortcut-btn set" onClick={() => handleCreditAdjust('set_unlimited', 1)}>
                          Set Unlimited
                        </button>
                      )}
                      {selectedUser.is_unlimited && (
                        <button className="admin-shortcut-btn remove" onClick={() => handleCreditAdjust('set_unlimited', 0)}>
                          Remove Unlimited
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
