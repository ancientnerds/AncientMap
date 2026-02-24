/**
 * Backward-compatibility re-exports.
 * All card rendering now lives in GameCard.tsx.
 */

import type { CardData } from '../../types/cards'
import { GameCard, GameCardDetail, StatBar as GCStatBar } from './GameCard'

export function CardTile({ card, onClick, action }: {
  card: CardData
  onClick?: () => void
  action?: React.ReactNode
}) {
  return <GameCard card={card} variant="tile" onClick={onClick} action={action} />
}

export function CardDetail({ card, onClose }: { card: CardData; onClose: () => void }) {
  return <GameCardDetail card={card} onClose={onClose} />
}

export { GCStatBar as StatBar }
