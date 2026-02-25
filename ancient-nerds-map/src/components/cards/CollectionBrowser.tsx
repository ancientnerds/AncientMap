import { useEffect, useState, useCallback, useMemo } from 'react'
import type { CardData } from '../../types/cards'
import { apiFetch } from '../../utils/cardApi'
import { CardTile, CardDetail } from './CardTile'

interface CollectionBrowserProps {
  token: string | null
  /** 'browse' = normal collection view; 'pick' = adds [+] button, dims cards in excludeIds */
  mode?: 'browse' | 'pick'
  /** Card IDs to dim/mark as already selected (pick mode) */
  excludeIds?: Set<string>
  /** Called when user clicks [+] on a card (pick mode) */
  onPick?: (card: CardData) => void
}

export default function CollectionBrowser({ token, mode = 'browse', excludeIds, onPick }: CollectionBrowserProps) {
  const [cards, setCards] = useState<CardData[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<CardData | null>(null)
  const [rarity, setRarity] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), per_page: '50' })
      if (rarity != null) params.set('rarity', String(rarity))
      const data = await apiFetch<{ cards: CardData[]; total: number; pages: number }>(
        `/cards/collection?${params}`, token,
      )
      setCards(data.cards)
      setTotal(data.total)
      setPages(data.pages)
    } catch (e) {
      console.error('Failed to load collection:', e)
    } finally {
      setLoading(false)
    }
  }, [token, page, rarity])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(
    () => search
      ? cards.filter(c => c.name.toLowerCase().includes(search.toLowerCase()))
      : cards,
    [cards, search],
  )

  return (
    <div className="cards-section">
      <div className="cards-toolbar">
        <span className="cards-count">{total} cards</span>
        <input
          type="text"
          className="collection-search"
          placeholder="Search cards..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select value={rarity ?? ''} onChange={e => { setRarity(e.target.value ? Number(e.target.value) : null); setPage(1) }}>
          <option value="">All rarities</option>
          <option value="1">Common</option>
          <option value="2">Uncommon</option>
          <option value="3">Rare</option>
          <option value="4">Epic</option>
          <option value="5">Legendary</option>
        </select>
      </div>
      {loading ? (
        <div className="cards-loading">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="cards-empty">
          {total === 0 ? 'No cards yet. Open packs or claim your starter deck!' : 'No matching cards.'}
        </div>
      ) : (
        <>
          <div className="cards-grid">
            {filtered.map(c => {
              const inDeck = excludeIds?.has(c.site_id)
              return (
                <div key={c.site_id} className={inDeck ? 'card-tile-dimmed' : ''}>
                  <CardTile
                    card={c}
                    onClick={mode === 'browse' ? () => setSelected(c) : undefined}
                    action={mode === 'pick' ? (
                      <button
                        className="card-pick-btn"
                        onClick={e => { e.stopPropagation(); onPick?.(c) }}
                        disabled={inDeck}
                      >
                        {inDeck ? '\u2713' : '+'}
                      </button>
                    ) : undefined}
                  />
                </div>
              )
            })}
          </div>
          {pages > 1 && (
            <div className="cards-pagination">
              <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</button>
              <span>Page {page} / {pages}</span>
              <button disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          )}
        </>
      )}
      {selected && <CardDetail card={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
