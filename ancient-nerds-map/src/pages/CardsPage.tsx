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
      await apiFetch('/cards/starter', token, { method: 'POST' })
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
            <a href="/account.html" className="cards-login-btn">Sign In</a>
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
              {stats?.total_cards === 0 && (
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
    </div>
  )
}
