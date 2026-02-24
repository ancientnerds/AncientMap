/**
 * AccountPage — User hub with Discord profile, card collection, deck builder.
 * Accessed via /account.html (separate Vite entry point).
 *
 * On first load after OAuth, reads ?token= from URL and stores it.
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { config } from '../config'
import { useAuth } from '../contexts/AuthContext'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { apiFetch } from '../utils/cardApi'
import type { PlayerStats, CardData } from '../types/cards'
import { EmpireCard } from '../components/cards/GameCard'
import CollectionBrowser from '../components/cards/CollectionBrowser'
import DeckBuilder from '../components/cards/DeckBuilder'
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

interface InteractionSite {
  id: string
  name: string
  country: string | null
  site_type: string | null
  thumbnail_url: string | null
  lat: number
  lon: number
  liked_at?: string
  bookmarked_at?: string
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
  bulk_role_grant: 'Bulk Role Grant',
}

// Discord role ID -> display info for profile badges (glass style: colored text on translucent bg)
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

type AccountTab = 'profile' | 'likes' | 'bookmarks' | 'collection' | 'empires' | 'decks' | 'admin'

const TAB_LABELS: Record<AccountTab, string> = {
  profile: 'Profile',
  likes: 'Likes',
  bookmarks: 'Bookmarks',
  collection: 'Collection',
  empires: 'Empires',
  decks: 'Decks',
  admin: 'Admin',
}

function getTabFromHash(): AccountTab {
  const hash = window.location.hash.replace('#', '') as AccountTab
  if (hash && hash in TAB_LABELS) return hash
  return 'profile'
}

// ---------------------------------------------------------------------------
// Empire Collection Tab
// ---------------------------------------------------------------------------
interface EmpireEntry {
  empire_id: string
  name: string
  region: string
  thematic_stat: string
  description: string
  acquired_via: string | null
  acquired_at: string | null
}

function EmpireCollectionTab({ token }: { token: string | null }) {
  const [empires, setEmpires] = useState<EmpireEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    setLoading(true)
    apiFetch<{ empires: EmpireEntry[] }>('/cards/empires', token)
      .then(data => setEmpires(data.empires))
      .catch(() => setEmpires([]))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) return <div className="cards-loading">Loading empire cards...</div>
  if (empires.length === 0) {
    return (
      <div className="deck-empty">
        No empire cards yet! Complete expeditions to earn them.
      </div>
    )
  }

  return (
    <div className="empire-collection">
      <div className="empire-grid">
        {empires.map(e => (
          <EmpireCard
            key={e.empire_id}
            empire={{
              name: e.name,
              region: e.region,
              thematicStat: e.thematic_stat,
              desc: e.description,
              acquiredVia: e.acquired_via ?? undefined,
            }}
          />
        ))}
      </div>
    </div>
  )
}

export default function AccountPage() {
  const { user, token, isLoggedIn, isLoading, logout } = useAuth()
  const [tab, setTab] = useState<AccountTab>(getTabFromHash)
  const [usage, setUsage] = useState<UsageEntry[]>([])
  const [grants, setGrants] = useState<GrantEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [grantsExpanded, setGrantsExpanded] = useState(false)
  const [usageExpanded, setUsageExpanded] = useState(false)

  // Player stats (card game)
  const [playerStats, setPlayerStats] = useState<PlayerStats | null>(null)
  const [claimingDaily, setClaimingDaily] = useState(false)
  const [dailyResult, setDailyResult] = useState<string | null>(null)
  const [claimingStarter, setClaimingStarter] = useState(false)

  // Liked & bookmarked sites
  const [likedSites, setLikedSites] = useState<InteractionSite[]>([])
  const [bookmarkedSites, setBookmarkedSites] = useState<InteractionSite[]>([])

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
  const [selectedRoles, setSelectedRoles] = useState<Set<string>>(new Set())
  const [bulkExpanded, setBulkExpanded] = useState(false)
  const [bulkRole, setBulkRole] = useState('')
  const [bulkAmount, setBulkAmount] = useState(100)
  const [bulkPreview, setBulkPreview] = useState<{ count: number } | null>(null)
  const [bulkLoading, setBulkLoading] = useState(false)

  // Hash-based tab routing
  const changeTab = (t: AccountTab) => {
    setTab(t)
    window.history.replaceState(null, '', `#${t}`)
  }

  useEffect(() => {
    const onHash = () => setTab(getTabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // Handle OAuth error callback
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

  // Fetch player stats
  const loadPlayerStats = useCallback(async () => {
    if (!token) return
    try {
      const data = await apiFetch<PlayerStats>('/cards/player-stats', token)
      setPlayerStats(data)
    } catch {
      // Non-critical — card game may not be set up
    }
  }, [token])

  useEffect(() => {
    if (isLoggedIn) loadPlayerStats()
  }, [isLoggedIn, loadPlayerStats])

  // Fetch liked & bookmarked sites
  useEffect(() => {
    if (!isLoggedIn || !token) return
    const headers = { 'Authorization': `Bearer ${token}` }
    fetch(`${config.api.baseUrl}/interactions/me/likes`, { headers })
      .then(r => r.ok ? r.json() : [])
      .then(setLikedSites)
      .catch(() => {})
    fetch(`${config.api.baseUrl}/interactions/me/bookmarks`, { headers })
      .then(r => r.ok ? r.json() : [])
      .then(setBookmarkedSites)
      .catch(() => {})
  }, [isLoggedIn, token])

  // Daily reward
  const claimDaily = async () => {
    if (!token) return
    setClaimingDaily(true)
    setDailyResult(null)
    try {
      const data = await apiFetch<{
        credits: number
        card: CardData | null
        daily_streak: number
        streak_reward: { type: string; value: string; streak: number } | null
      }>('/cards/daily', token, { method: 'POST' })
      const parts = [`+${data.credits} credits`]
      if (data.card) parts.push(`Card: ${data.card.name}`)
      parts.push(`Streak: ${data.daily_streak} days`)
      if (data.streak_reward) {
        const r = data.streak_reward
        if (r.type === 'credits') parts.push(`Streak bonus: +${r.value} credits!`)
        else if (r.type === 'pack') parts.push(`Streak bonus: ${r.value.charAt(0).toUpperCase() + r.value.slice(1)} Pack!`)
      }
      setDailyResult(parts.join(' | '))
      loadPlayerStats()
    } catch (e: any) {
      setDailyResult(e.message || 'Failed')
    } finally {
      setClaimingDaily(false)
    }
  }

  // Starter deck
  const claimStarter = async () => {
    if (!token) return
    setClaimingStarter(true)
    try {
      await apiFetch('/cards/starter', token, { method: 'POST' })
      loadPlayerStats()
      changeTab('collection')
    } catch (e: any) {
      console.error('Starter claim failed:', e.message)
    } finally {
      setClaimingStarter(false)
    }
  }

  // Admin: fetch users
  const fetchAdminUsers = useCallback(async (q = '', roles?: Set<string>) => {
    if (!token) return
    setAdminLoading(true)
    setAdminError(null)
    try {
      const searchParams = new URLSearchParams()
      if (q) searchParams.set('q', q)
      const roleSet = roles ?? selectedRoles
      if (roleSet.size > 0) searchParams.set('role', [...roleSet].join(','))
      const qs = searchParams.toString()
      const resp = await fetch(`${config.api.baseUrl}/auth/admin/users${qs ? `?${qs}` : ''}`, {
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
  }, [token, selectedRoles])

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

  // Toggle a role filter chip
  const toggleRoleFilter = (roleId: string) => {
    setSelectedRoles(prev => {
      const next = new Set(prev)
      if (next.has(roleId)) next.delete(roleId)
      else next.add(roleId)
      clearTimeout(searchTimer.current)
      searchTimer.current = setTimeout(() => fetchAdminUsers(adminSearch, next), 150)
      return next
    })
  }

  // Bulk: fetch preview count
  const fetchBulkPreview = async () => {
    if (!token || !bulkRole) return
    setBulkLoading(true)
    setBulkPreview(null)
    try {
      const resp = await fetch(
        `${config.api.baseUrl}/auth/admin/users/count-by-role?role_id=${encodeURIComponent(bulkRole)}`,
        { headers: { 'Authorization': `Bearer ${token}` } },
      )
      if (resp.ok) {
        const data = await resp.json()
        setBulkPreview({ count: data.count })
      }
    } catch { /* ignore */ }
    finally { setBulkLoading(false) }
  }

  // Bulk: apply grant
  const applyBulkGrant = async () => {
    if (!token || !bulkRole || !bulkPreview) return
    setBulkLoading(true)
    setAdminError(null)
    setAdminSuccess(null)
    try {
      const resp = await fetch(`${config.api.baseUrl}/auth/admin/credits/bulk`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_id: bulkRole, amount: bulkAmount }),
      })
      if (resp.ok) {
        const data = await resp.json()
        const roleName = ROLE_DISPLAY[bulkRole]?.name || bulkRole
        setAdminSuccess(`Bulk grant: +${bulkAmount} credits to ${data.affected} ${roleName} users`)
        setBulkPreview(null)
        fetchAdminUsers(adminSearch)
      } else {
        const data = await resp.json().catch(() => null)
        setAdminError(data?.detail || 'Bulk grant failed')
      }
    } catch {
      setAdminError('Bulk grant failed')
    } finally {
      setBulkLoading(false)
    }
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
        const creditsDisplay = newUnlimited ? '\u221E' : newCredits.toLocaleString()
        setAdminSuccess(
          `${selectedUser.username}: credits ${actionLabel} ${action === 'set_unlimited' ? '' : amount} \u2192 now ${creditsDisplay}`
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

  // Determine which tabs to show
  const visibleTabs: AccountTab[] = ['profile', 'likes', 'bookmarks', 'collection', 'empires', 'decks']
  if (user?.is_founder) visibleTabs.push('admin')

  // Wide tabs need more horizontal space
  const isWideTab = tab === 'collection' || tab === 'empires' || tab === 'decks'

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

      <div className={`account-content ${isWideTab ? 'account-content-wide' : ''}`}>
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
            {/* Tab navigation */}
            <nav className="account-tabs">
              {visibleTabs.map(t => (
                <button
                  key={t}
                  className={`account-tab ${tab === t ? 'active' : ''}`}
                  onClick={() => changeTab(t)}
                >
                  {TAB_LABELS[t]}
                  {t === 'likes' && likedSites.length > 0 && (
                    <span className="account-tab-count">{likedSites.length}</span>
                  )}
                  {t === 'bookmarks' && bookmarkedSites.length > 0 && (
                    <span className="account-tab-count">{bookmarkedSites.length}</span>
                  )}
                </button>
              ))}
            </nav>

            {/* ============ PROFILE TAB ============ */}
            {tab === 'profile' && (
              <>
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

                  {/* Credits + XP side by side */}
                  <div className="account-stats-row">
                    <div className="account-stat-block">
                      <div className="account-credits-label">Lyra Credits</div>
                      <div className="account-credits-value">
                        {user?.is_unlimited ? '\u221E' : (user?.credits?.toLocaleString() ?? 0)}
                      </div>
                      <div className="account-credits-note">
                        {user?.is_unlimited
                          ? `Unlimited access${user?.is_founder ? ' \u2014 thank you, Founder!' : ''}`
                          : '1 credit = 100 tokens'}
                      </div>
                      {user?.next_grant_date && (
                        <div className="account-credits-note" style={{ marginTop: '4px', fontSize: '0.8em', opacity: 0.7 }}>
                          Next grant: {new Date(user.next_grant_date).toLocaleDateString()}
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
                    {playerStats && (
                      <div className="account-stat-block">
                        <div className="account-credits-label">Card Game</div>
                        <div className="account-card-stats-grid">
                          <div className="account-mini-stat">
                            <span className="account-mini-stat-value">{playerStats.xp}</span>
                            <span className="account-mini-stat-label">XP</span>
                          </div>
                          <div className="account-mini-stat">
                            <span className="account-mini-stat-value">{playerStats.total_cards}</span>
                            <span className="account-mini-stat-label">Cards</span>
                          </div>
                          <div className="account-mini-stat">
                            <span className="account-mini-stat-value">{playerStats.wins}/{playerStats.losses}</span>
                            <span className="account-mini-stat-label">W/L</span>
                          </div>
                          <div className="account-mini-stat">
                            <span className="account-mini-stat-value">{playerStats.daily_streak}d</span>
                            <span className="account-mini-stat-label">Streak</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Daily reward + Starter buttons */}
                  <div className="account-card-actions">
                    <button
                      className="account-action-btn daily"
                      onClick={claimDaily}
                      disabled={claimingDaily}
                    >
                      {claimingDaily ? 'Claiming...' : 'Daily Reward'}
                    </button>
                    {playerStats?.total_cards === 0 && (
                      <button
                        className="account-action-btn starter"
                        onClick={claimStarter}
                        disabled={claimingStarter}
                      >
                        {claimingStarter ? 'Claiming...' : 'Claim Starter Deck'}
                      </button>
                    )}
                  </div>
                  {dailyResult && <div className="account-daily-result">{dailyResult}</div>}

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
                                <td>{g.grant_period || '\u2014'}</td>
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
              </>
            )}

            {/* ============ LIKES TAB ============ */}
            {tab === 'likes' && (
              <div className="account-section">
                {likedSites.length === 0 ? (
                  <div className="account-empty-tab">No liked sites yet. Explore the map and like sites you find interesting!</div>
                ) : (
                  <div className="account-site-grid">
                    {likedSites.map(s => {
                      const flagUrl = s.country ? getCountryFlatFlagUrl(s.country) : null
                      return (
                        <a key={s.id} href={`/site.html?id=${s.id}`} className="account-site-card">
                          {s.thumbnail_url ? (
                            <img src={s.thumbnail_url} alt="" className="account-site-thumb" />
                          ) : (
                            <div className="account-site-thumb-empty" />
                          )}
                          <div className="account-site-info">
                            <span className="account-site-name">{s.name}</span>
                            {s.country && (
                              <span className="account-site-country">
                                {flagUrl && <img src={flagUrl} alt="" className="account-site-flag" />}
                                {s.country}
                              </span>
                            )}
                          </div>
                        </a>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ============ BOOKMARKS TAB ============ */}
            {tab === 'bookmarks' && (
              <div className="account-section">
                {bookmarkedSites.length === 0 ? (
                  <div className="account-empty-tab">No bookmarked sites yet. Bookmark sites to save them for later!</div>
                ) : (
                  <div className="account-site-grid">
                    {bookmarkedSites.map(s => {
                      const flagUrl = s.country ? getCountryFlatFlagUrl(s.country) : null
                      return (
                        <a key={s.id} href={`/site.html?id=${s.id}`} className="account-site-card">
                          {s.thumbnail_url ? (
                            <img src={s.thumbnail_url} alt="" className="account-site-thumb" />
                          ) : (
                            <div className="account-site-thumb-empty" />
                          )}
                          <div className="account-site-info">
                            <span className="account-site-name">{s.name}</span>
                            {s.country && (
                              <span className="account-site-country">
                                {flagUrl && <img src={flagUrl} alt="" className="account-site-flag" />}
                                {s.country}
                              </span>
                            )}
                          </div>
                        </a>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ============ COLLECTION TAB ============ */}
            {tab === 'collection' && (
              <CollectionBrowser token={token} />
            )}

            {/* ============ EMPIRES TAB ============ */}
            {tab === 'empires' && (
              <EmpireCollectionTab token={token} />
            )}

            {/* ============ DECKS TAB ============ */}
            {tab === 'decks' && (
              <DeckBuilder token={token} />
            )}

            {/* ============ ADMIN TAB ============ */}
            {tab === 'admin' && user?.is_founder && (
              <div className="account-section admin-panel">
                <h3 className="account-section-title">Admin — Credit Management</h3>

                <input
                  type="text"
                  className="admin-search"
                  placeholder="Search users by name..."
                  value={adminSearch}
                  onChange={e => handleAdminSearch(e.target.value)}
                />

                {/* Bulk grant section */}
                <div className="admin-bulk-section">
                  <button
                    className="account-expand-btn"
                    onClick={() => setBulkExpanded(!bulkExpanded)}
                    style={{ marginTop: 0, marginBottom: bulkExpanded ? 10 : 0 }}
                  >
                    <span className={`account-expand-arrow ${bulkExpanded ? 'expanded' : ''}`}>{'\u25B6'}</span>
                    Bulk Grant
                  </button>
                  {bulkExpanded && (
                    <div className="admin-bulk-controls">
                      <select
                        className="admin-bulk-select"
                        value={bulkRole}
                        onChange={e => { setBulkRole(e.target.value); setBulkPreview(null) }}
                      >
                        <option value="">Select role...</option>
                        {Object.entries(ROLE_DISPLAY).map(([id, info]) => (
                          <option key={id} value={id}>{info.name}</option>
                        ))}
                      </select>
                      <input
                        type="number"
                        className="admin-amount-input"
                        value={bulkAmount}
                        onChange={e => { setBulkAmount(parseInt(e.target.value) || 0); setBulkPreview(null) }}
                        style={{ maxWidth: 100 }}
                      />
                      <button
                        className="admin-apply-btn"
                        onClick={fetchBulkPreview}
                        disabled={!bulkRole || bulkAmount <= 0 || bulkLoading}
                        style={{ opacity: (!bulkRole || bulkAmount <= 0) ? 0.4 : 1 }}
                      >
                        Preview
                      </button>
                    </div>
                  )}
                  {bulkPreview && bulkExpanded && (
                    <div className="admin-bulk-preview">
                      Add <strong>+{bulkAmount.toLocaleString()}</strong> credits to{' '}
                      <strong>{bulkPreview.count}</strong>{' '}
                      {ROLE_DISPLAY[bulkRole]?.name || 'unknown'} users?
                      <button
                        className="admin-apply-btn"
                        onClick={applyBulkGrant}
                        disabled={bulkLoading || bulkPreview.count === 0}
                        style={{ marginLeft: 10 }}
                      >
                        {bulkLoading ? 'Applying...' : 'Apply'}
                      </button>
                    </div>
                  )}
                </div>

                {/* Role filter chips */}
                <div className="admin-role-filters">
                  {Object.entries(ROLE_DISPLAY).map(([id, info]) => {
                    const active = selectedRoles.has(id)
                    return (
                      <button
                        key={id}
                        className={`admin-role-chip ${active ? 'active' : ''}`}
                        style={{
                          borderColor: active ? info.color : `${info.color}44`,
                          background: active ? `${info.color}25` : 'transparent',
                          color: active ? info.color : `${info.color}99`,
                        }}
                        onClick={() => toggleRoleFilter(id)}
                      >
                        {ROLE_SHORT[id] || info.name.slice(0, 2)}
                      </button>
                    )
                  })}
                </div>

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
                          {u.is_unlimited ? '\u221E' : u.credits.toLocaleString()}
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
                        (current: {selectedUser.is_unlimited ? '\u221E' : selectedUser.credits.toLocaleString()})
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
