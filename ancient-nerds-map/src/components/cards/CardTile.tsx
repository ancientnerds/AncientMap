import type { CardData } from '../../types/cards'
import { RARITY_CLASSES } from '../../constants/cards'
import { STAR_LEVELS } from '../../constants/cards'

function StarDisplay({ level, xp }: { level: number; xp: number }) {
  const nextThreshold = STAR_LEVELS[level + 1] ?? 0
  const currentThreshold = STAR_LEVELS[level] ?? 0
  const progress = nextThreshold > 0 ? (xp - currentThreshold) / (nextThreshold - currentThreshold) : 0

  return (
    <div className="card-stars">
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} className={i < level ? 'star-filled' : 'star-empty'}>
          {i < level ? '\u2605' : '\u2606'}
        </span>
      ))}
      {nextThreshold > 0 && xp > 0 && (
        <div className="star-progress" title={`${xp - currentThreshold}/${nextThreshold - currentThreshold} to next star`}>
          <div className="star-progress-fill" style={{ width: `${Math.min(100, progress * 100)}%` }} />
        </div>
      )}
    </div>
  )
}

export function CardTile({ card, onClick, action }: {
  card: CardData
  onClick?: () => void
  action?: React.ReactNode
}) {
  const rarityClass = RARITY_CLASSES[card.rarity_tier] || 'rarity-common'

  return (
    <div className={`card-tile ${rarityClass}`} onClick={onClick} role="button" tabIndex={0}>
      {card.thumbnail_url ? (
        <img src={card.thumbnail_url} alt={card.name} className="card-thumb" loading="lazy" />
      ) : (
        <div className="card-thumb card-thumb-placeholder" />
      )}
      <div className="card-info">
        <div className="card-name">{card.name}</div>
        <div className="card-meta">
          {card.rarity_name} &middot; {card.category_group}
        </div>
        <div className="card-power">Power: {card.total_power}</div>
        {card.star_level != null && card.star_level >= 1 && (
          <StarDisplay level={card.star_level} xp={card.card_xp ?? 0} />
        )}
      </div>
      {action && <div className="card-tile-action">{action}</div>}
    </div>
  )
}

export function StatBar({ label, value, max = 10 }: { label: string; value: number; max?: number }) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="stat-bar-row">
      <span className="stat-label">{label}</span>
      <div className="stat-bar-track">
        <div className="stat-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="stat-value">{value}</span>
    </div>
  )
}

export function CardDetail({ card, onClose }: { card: CardData; onClose: () => void }) {
  const rarityClass = RARITY_CLASSES[card.rarity_tier] || 'rarity-common'
  return (
    <div className="card-detail-overlay" onClick={onClose}>
      <div className={`card-detail ${rarityClass}`} onClick={e => e.stopPropagation()}>
        <button className="card-detail-close" onClick={onClose}>&times;</button>
        {card.thumbnail_url && <img src={card.thumbnail_url} alt={card.name} className="card-detail-img" />}
        <h2>{card.name}</h2>
        <p className="card-detail-meta">
          {[card.period_name, card.country, card.category_group].filter(Boolean).join(' | ')}
        </p>
        <p className="card-detail-rarity">{card.rarity_name} &middot; Tier {card.rarity_tier}</p>
        <div className="card-stats">
          <StatBar label="Antiquity" value={card.antiquity} />
          <StatBar label="Fortification" value={card.fortification} />
          <StatBar label="Cultural Influence" value={card.cultural_influence} />
          <StatBar label="Mystery" value={card.mystery} />
          <StatBar label="Legacy" value={card.legacy} />
        </div>
        <div className="card-total-power">Total Power: {card.total_power}</div>
      </div>
    </div>
  )
}
