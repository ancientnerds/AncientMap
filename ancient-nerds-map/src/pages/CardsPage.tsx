/**
 * CardsPage — Card game collection, deck builder, leaderboard, and pack opening.
 * Accessed via /cards.html (separate Vite entry point).
 *
 * Visual card design is deferred — placeholder card components used for now.
 */

import { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'
import PageHeader from '../components/layout/PageHeader'
import { CardTile } from '../components/cards/CardTile'
import CollectionBrowser from '../components/cards/CollectionBrowser'
import type { CardData, DeckData, LeaderboardEntry, PackInfo, PlayerStats } from '../types/cards'
import { apiFetch } from '../utils/cardApi'
import { handleAchievementResponse } from '../components/AchievementToast'
import AchievementToast from '../components/AchievementToast'
import '../styles/cards.css'

type Tab = 'collection' | 'decks' | 'leaderboard' | 'packs'

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

function DecksSection({ token }: { token: string | null }) {
  const [decks, setDecks] = useState<DeckData[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      const data = await apiFetch<{ decks: DeckData[] }>('/cards/decks', token)
      setDecks(data.decks)
    } catch (e) {
      console.error('Failed to load decks:', e)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { load() }, [load])

  const activateDeck = async (deckId: string) => {
    if (!token) return
    try {
      await apiFetch(`/cards/decks/${deckId}/activate`, token, { method: 'PUT' })
      load()
    } catch (e) {
      console.error('Failed to activate deck:', e)
    }
  }

  return (
    <div className="cards-section">
      {loading ? (
        <div className="cards-loading">Loading...</div>
      ) : decks.length === 0 ? (
        <div className="cards-empty">No decks yet. Create one below!</div>
      ) : (
        <div className="decks-list">
          {decks.map(d => (
            <div key={d.id} className={`deck-card ${d.is_active ? 'deck-active' : ''}`}>
              <div className="deck-name">{d.name}</div>
              <div className="deck-info">{d.card_ids.length} / 10 cards</div>
              {!d.is_active && (
                <button className="deck-activate-btn" onClick={() => activateDeck(d.id)}>
                  Set Active
                </button>
              )}
              {d.is_active && <span className="deck-active-badge">Active</span>}
            </div>
          ))}
        </div>
      )}
      <p className="decks-hint">Full deck builder coming soon. Use Discord <code>/deck</code> commands for now.</p>
    </div>
  )
}

function LeaderboardSection() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [sort, setSort] = useState<string>('wins')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch<{ leaderboard: LeaderboardEntry[] }>(
        `/cards/leaderboard?sort=${sort}&limit=20`, null,
      )
      setEntries(data.leaderboard)
    } catch (e) {
      console.error('Failed to load leaderboard:', e)
    } finally {
      setLoading(false)
    }
  }, [sort])

  useEffect(() => { load() }, [load])

  return (
    <div className="cards-section">
      <div className="cards-toolbar">
        <select value={sort} onChange={e => setSort(e.target.value)}>
          <option value="wins">Wins</option>
          <option value="cards">Collection Size</option>
          <option value="power">XP</option>
          <option value="streak">Best Streak</option>
        </select>
      </div>
      {loading ? (
        <div className="cards-loading">Loading...</div>
      ) : entries.length === 0 ? (
        <div className="cards-empty">No players yet. Be the first!</div>
      ) : (
        <table className="leaderboard-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Player</th>
              <th>W/L/D</th>
              <th>Cards</th>
              <th>XP</th>
              <th>Streak</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={`${e.username}-${i}`}>
                <td>{i + 1}</td>
                <td>{e.username}</td>
                <td>{e.wins}/{e.losses}/{e.draws}</td>
                <td>{e.total_cards}</td>
                <td>{e.xp}</td>
                <td>{e.best_streak}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function PacksSection({ token, onOpen }: { token: string | null; onOpen: () => void }) {
  const [packs, setPacks] = useState<Record<string, PackInfo>>({})
  const [opening, setOpening] = useState(false)
  const [result, setResult] = useState<CardData[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<{ packs: Record<string, PackInfo> }>('/cards/packs', null)
      .then(d => setPacks(d.packs))
      .catch(e => console.error('Failed to load packs:', e))
  }, [])

  const openPack = async (packType: string) => {
    if (!token) return
    setOpening(true)
    setError(null)
    setResult(null)
    try {
      const data = await apiFetch<{ cards: CardData[] }>('/cards/pack/open', token, {
        method: 'POST',
        body: JSON.stringify({ pack_type: packType }),
      })
      setResult(data.cards)
      handleAchievementResponse(data as unknown as Record<string, unknown>)
      onOpen()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to open pack')
    } finally {
      setOpening(false)
    }
  }

  return (
    <div className="cards-section">
      <div className="packs-grid">
        {Object.entries(packs).map(([name, info]) => (
          <div key={name} className={`pack-card pack-${name}`}>
            <div className="pack-name">{name.charAt(0).toUpperCase() + name.slice(1)} Pack</div>
            <div className="pack-cost">{info.cost.toLocaleString()} credits</div>
            <div className="pack-cards">{info.cards} cards</div>
            <div className="pack-guarantees">
              {info.guarantees.map((g, i) => (
                <span key={i} className="pack-guarantee">{g}</span>
              ))}
            </div>
            <button
              className="pack-open-btn"
              disabled={!token || opening}
              onClick={() => openPack(name)}
            >
              {opening ? 'Opening...' : 'Open'}
            </button>
          </div>
        ))}
      </div>
      {error && <div className="pack-error">{error}</div>}
      {result && (
        <div className="pack-result">
          <h3>You received:</h3>
          <div className="cards-grid">
            {result.map(c => <CardTile key={c.site_id} card={c} />)}
          </div>
          <button className="pack-dismiss-btn" onClick={() => setResult(null)}>Close</button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CardsPage() {
  const { user, token } = useAuth()
  const [tab, setTab] = useState<Tab>('collection')
  const [stats, setStats] = useState<PlayerStats | null>(null)
  const [claimingStarter, setClaimingStarter] = useState(false)
  const [claimingDaily, setClaimingDaily] = useState(false)
  const [dailyResult, setDailyResult] = useState<string | null>(null)

  const loadStats = useCallback(async () => {
    if (!token) return
    try {
      const data = await apiFetch<PlayerStats>('/cards/player-stats', token)
      setStats(data)
    } catch (e) {
      console.error('Failed to load player stats:', e)
    }
  }, [token])

  useEffect(() => { loadStats() }, [loadStats])

  const claimStarter = async () => {
    if (!token) return
    setClaimingStarter(true)
    try {
      const starterData = await apiFetch<Record<string, unknown>>('/cards/starter', token, { method: 'POST' })
      handleAchievementResponse(starterData)
      loadStats()
      setTab('collection')
    } catch (e) {
      console.error('Starter claim failed:', e instanceof Error ? e.message : e)
    } finally {
      setClaimingStarter(false)
    }
  }

  const claimDaily = async () => {
    if (!token) return
    setClaimingDaily(true)
    setDailyResult(null)
    try {
      const data = await apiFetch<{ credits: number; card: CardData | null; daily_streak: number }>(
        '/cards/daily', token, { method: 'POST' },
      )
      const parts = [`+${data.credits} credits`]
      if (data.card) parts.push(`Card: ${data.card.name}`)
      parts.push(`Streak: ${data.daily_streak} days`)
      setDailyResult(parts.join(' | '))
      handleAchievementResponse(data as unknown as Record<string, unknown>)
      loadStats()
    } catch (e) {
      setDailyResult(e instanceof Error ? e.message : 'Failed')
    } finally {
      setClaimingDaily(false)
    }
  }

  return (
    <div className="cards-page">
      <PageHeader currentPage="cards">
        <h1>Card Game</h1>
      </PageHeader>

      <div className="cards-container">
        {!user ? (
          <div className="cards-login-prompt">
            <p>Sign in to start collecting cards!</p>
            <a href={`/api/auth/discord?return_to=${encodeURIComponent('/cards.html')}`} className="account-discord-btn" style={{ textDecoration: 'none' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.36-.698.772-1.362 1.225-1.993a.076.076 0 0 0-.041-.107 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.12-.094.246-.194.373-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
              </svg>
              Continue with Discord
            </a>
          </div>
        ) : (
          <>
            {/* Player summary bar */}
            <div className="player-bar">
              <span className="player-stat">Cards: {stats?.total_cards ?? 0}</span>
              <span className="player-stat">W/L: {stats?.wins ?? 0}/{stats?.losses ?? 0}</span>
              <span className="player-stat">XP: {stats?.xp ?? 0}</span>
              <span className="player-stat">Streak: {stats?.daily_streak ?? 0}d</span>
              <button
                className="daily-btn"
                onClick={claimDaily}
                disabled={claimingDaily}
              >
                {claimingDaily ? 'Claiming...' : 'Daily Reward'}
              </button>
              {stats && !stats.has_claimed_starter && (
                <button
                  className="starter-btn"
                  onClick={claimStarter}
                  disabled={claimingStarter}
                >
                  {claimingStarter ? 'Claiming...' : 'Claim Starter Deck'}
                </button>
              )}
            </div>
            {dailyResult && <div className="daily-result">{dailyResult}</div>}

            {/* Tab navigation */}
            <nav className="cards-tabs">
              {(['collection', 'decks', 'leaderboard', 'packs'] as Tab[]).map(t => (
                <button
                  key={t}
                  className={`cards-tab ${tab === t ? 'active' : ''}`}
                  onClick={() => setTab(t)}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </nav>

            {/* Tab content */}
            {tab === 'collection' && <CollectionBrowser token={token} />}
            {tab === 'decks' && <DecksSection token={token} />}
            {tab === 'leaderboard' && <LeaderboardSection />}
            {tab === 'packs' && <PacksSection token={token} onOpen={loadStats} />}
          </>
        )}
      </div>
      <AchievementToast />
    </div>
  )
}
