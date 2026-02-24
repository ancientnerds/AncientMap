import { useEffect, useState, useCallback, useRef } from 'react'
import type { CardData, DeckData, SynergyDescription } from '../../types/cards'
import { apiFetch } from '../../utils/cardApi'
import { RARITY_CLASSES } from '../../constants/cards'
import CollectionBrowser from './CollectionBrowser'

interface DeckBuilderProps {
  token: string | null
}

const MAX_DECKS = 3
const MAX_CARDS = 10

export default function DeckBuilder({ token }: DeckBuilderProps) {
  const [decks, setDecks] = useState<DeckData[]>([])
  const [activeDeckIdx, setActiveDeckIdx] = useState(0)
  const [deckName, setDeckName] = useState('')
  const [deckCards, setDeckCards] = useState<CardData[]>([])
  const [synergies, setSynergies] = useState<SynergyDescription[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [editingName, setEditingName] = useState(false)
  const synergyTimer = useRef<ReturnType<typeof setTimeout>>()

  // Load existing decks
  const loadDecks = useCallback(async () => {
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

  useEffect(() => { loadDecks() }, [loadDecks])

  // When selecting a deck slot, load its cards
  const selectDeck = useCallback(async (idx: number) => {
    setActiveDeckIdx(idx)
    setError(null)
    setSuccess(null)
    const deck = decks[idx]
    if (!deck) {
      setDeckName('New Deck')
      setDeckCards([])
      setSynergies([])
      return
    }
    setDeckName(deck.name)
    // Fetch full card data for the deck's card_ids
    if (deck.card_ids.length === 0) {
      setDeckCards([])
      setSynergies([])
      return
    }
    if (!token) return
    try {
      const data = await apiFetch<{ cards: CardData[] }>(
        `/cards/collection?per_page=200`, token,
      )
      const cardMap = new Map(data.cards.map(c => [c.site_id, c]))
      setDeckCards(deck.card_ids.map(id => cardMap.get(id)).filter(Boolean) as CardData[])
    } catch {
      // Collection load will still work from the browser
    }
  }, [decks, token])

  useEffect(() => {
    if (decks.length > 0) selectDeck(0)
  }, [decks.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced synergy preview
  const fetchSynergies = useCallback(async (cardIds: string[]) => {
    if (!token || cardIds.length < 2) {
      setSynergies([])
      return
    }
    try {
      const data = await apiFetch<{ synergies: SynergyDescription[] }>(
        '/cards/deck-synergies', token, {
          method: 'POST',
          body: JSON.stringify({ name: 'preview', card_ids: cardIds }),
        },
      )
      setSynergies(data.synergies)
    } catch {
      setSynergies([])
    }
  }, [token])

  const scheduleSynergyFetch = (cards: CardData[]) => {
    clearTimeout(synergyTimer.current)
    synergyTimer.current = setTimeout(() => {
      fetchSynergies(cards.map(c => c.site_id))
    }, 500)
  }

  // Add card to deck
  const addCard = (card: CardData) => {
    if (deckCards.length >= MAX_CARDS) return
    if (deckCards.some(c => c.site_id === card.site_id)) return
    const next = [...deckCards, card]
    setDeckCards(next)
    scheduleSynergyFetch(next)
  }

  // Remove card from deck
  const removeCard = (siteId: string) => {
    const next = deckCards.filter(c => c.site_id !== siteId)
    setDeckCards(next)
    scheduleSynergyFetch(next)
  }

  // Save deck (create or update)
  const saveDeck = async () => {
    if (!token) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    const cardIds = deckCards.map(c => c.site_id)
    const deck = decks[activeDeckIdx]
    try {
      if (deck) {
        // Update existing
        await apiFetch(`/cards/decks/${deck.id}`, token, {
          method: 'PUT',
          body: JSON.stringify({ name: deckName, card_ids: cardIds }),
        })
        setSuccess('Deck saved!')
      } else {
        // Create new
        await apiFetch('/cards/decks', token, {
          method: 'POST',
          body: JSON.stringify({ name: deckName, card_ids: cardIds }),
        })
        setSuccess('Deck created!')
      }
      await loadDecks()
    } catch (e: any) {
      setError(e.message || 'Failed to save deck')
    } finally {
      setSaving(false)
    }
  }

  // Activate deck
  const activateDeck = async () => {
    const deck = decks[activeDeckIdx]
    if (!deck || !token) return
    try {
      await apiFetch(`/cards/decks/${deck.id}/activate`, token, { method: 'PUT' })
      setSuccess('Deck activated!')
      await loadDecks()
    } catch (e: any) {
      setError(e.message || 'Failed to activate deck')
    }
  }

  // Delete deck
  const deleteDeck = async () => {
    const deck = decks[activeDeckIdx]
    if (!deck || !token) return
    try {
      await apiFetch(`/cards/decks/${deck.id}`, token, { method: 'DELETE' })
      setSuccess('Deck deleted')
      setDeckCards([])
      setSynergies([])
      setActiveDeckIdx(0)
      await loadDecks()
    } catch (e: any) {
      setError(e.message || 'Failed to delete deck')
    }
  }

  // New deck slot
  const startNewDeck = () => {
    setActiveDeckIdx(decks.length)
    setDeckName('New Deck')
    setDeckCards([])
    setSynergies([])
    setError(null)
    setSuccess(null)
  }

  const currentDeck = decks[activeDeckIdx]
  const deckCardIds = new Set(deckCards.map(c => c.site_id))

  if (loading) return <div className="cards-loading">Loading decks...</div>

  return (
    <div className="deck-builder">
      {/* Deck selector bar */}
      <div className="deck-selector-bar">
        {decks.map((d, i) => (
          <button
            key={d.id}
            className={`deck-selector-slot ${i === activeDeckIdx ? 'active' : ''}`}
            onClick={() => selectDeck(i)}
          >
            {d.is_active && <span className="deck-star">&#9733;</span>}
            {d.name}
          </button>
        ))}
        {decks.length < MAX_DECKS && (
          <button className="deck-selector-new" onClick={startNewDeck}>
            + New Deck
          </button>
        )}
      </div>

      {/* Split panel */}
      <div className="deck-builder-panels">
        {/* Left: collection browser in pick mode */}
        <div className="deck-builder-left">
          <h3 className="deck-panel-title">Your Collection</h3>
          <CollectionBrowser
            token={token}
            mode="pick"
            excludeIds={deckCardIds}
            onPick={addCard}
          />
        </div>

        {/* Right: current deck */}
        <div className="deck-builder-right">
          <div className="deck-name-row">
            {editingName ? (
              <input
                className="deck-name-input"
                value={deckName}
                onChange={e => setDeckName(e.target.value)}
                onBlur={() => setEditingName(false)}
                onKeyDown={e => e.key === 'Enter' && setEditingName(false)}
                autoFocus
              />
            ) : (
              <h3 className="deck-panel-title deck-name-editable" onClick={() => setEditingName(true)}>
                {deckName} <span className="deck-name-edit-icon">&#9998;</span>
              </h3>
            )}
            <span className="deck-card-count">{deckCards.length}/{MAX_CARDS}</span>
          </div>

          {deckCards.length === 0 ? (
            <div className="deck-empty">Click [+] on cards to add them to your deck.</div>
          ) : (
            <div className="deck-card-list">
              {deckCards.map((c, i) => {
                const rarityClass = RARITY_CLASSES[c.rarity_tier] || 'rarity-common'
                return (
                  <div key={c.site_id} className={`deck-list-item ${rarityClass}`}>
                    <span className="deck-list-num">{i + 1}.</span>
                    {c.thumbnail_url && (
                      <img src={c.thumbnail_url} alt="" className="deck-list-thumb" />
                    )}
                    <div className="deck-list-info">
                      <span className="deck-list-name">{c.name}</span>
                      <span className="deck-list-power">Power: {c.total_power}</span>
                    </div>
                    <button className="deck-list-remove" onClick={() => removeCard(c.site_id)}>
                      &minus;
                    </button>
                  </div>
                )
              })}
            </div>
          )}

          {/* Synergies */}
          {synergies.length > 0 && (
            <div className="deck-synergies">
              <h4 className="deck-synergy-title">Synergies</h4>
              {synergies.map((s, i) => (
                <div key={i} className="deck-synergy-row">
                  <span className="deck-synergy-label">
                    {s.count}&times; {s.label}
                  </span>
                  <span className="deck-synergy-bonus">{s.bonus}</span>
                </div>
              ))}
            </div>
          )}

          {/* Action buttons */}
          {error && <div className="deck-error">{error}</div>}
          {success && <div className="deck-success">{success}</div>}
          <div className="deck-actions">
            <button className="deck-action-btn save" onClick={saveDeck} disabled={saving || deckCards.length === 0}>
              {saving ? 'Saving...' : currentDeck ? 'Save Deck' : 'Create Deck'}
            </button>
            {currentDeck && !currentDeck.is_active && (
              <button className="deck-action-btn activate" onClick={activateDeck}>
                Set Active
              </button>
            )}
            {currentDeck && (
              <button className="deck-action-btn delete" onClick={deleteDeck}>
                Delete
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
