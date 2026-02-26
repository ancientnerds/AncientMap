/**
 * GameCard — Unified card component module.
 *
 * Variants:
 *   tile     — Collection grid (compact card with hero image, rarity glow, badges)
 *   showcase — Full-size showcase (GamePage rules, featured display)
 *   row      — Compact horizontal row for deck builder list
 *
 * Also exports: GameCardDetail (modal), EmpireCard, StatBar, StarDisplay
 */

import type { CardData } from '../../types/cards'
import { STAR_LEVELS, MAX_STAR_LEVEL, DUPES_FOR_NEXT } from '../../constants/cards'
import { RARITY_TIERS, STAT_COLORS, STAT_META, STAT_ACCENTS, RARITY_POWER_COLORS, RARITY_RIBBON_BG, type StatKey } from '../../constants/rarity'
import { getCountryCode } from '../../utils/countryFlags'
import './gameCard.css'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getRarity(tier: number) {
  return RARITY_TIERS[tier] ?? RARITY_TIERS[1]
}

function getStatValue(card: CardData, key: StatKey): number {
  return card[key]
}

// ---------------------------------------------------------------------------
// StarDisplay
// ---------------------------------------------------------------------------

export function StarDisplay({ level, xp, dupsFilled, showDups = false }: {
  level: number
  xp?: number
  dupsFilled?: number
  showDups?: boolean
}) {
  const nextThreshold = STAR_LEVELS[level + 1] ?? 0
  const currentThreshold = STAR_LEVELS[level] ?? 0
  const range = nextThreshold - currentThreshold
  const progress = range > 0 && xp != null
    ? (xp - currentThreshold) / range
    : 0
  const dupsNeeded = DUPES_FOR_NEXT[level] ?? 0

  return (
    <div className="gc-stars">
      {Array.from({ length: MAX_STAR_LEVEL }, (_, i) => (
        <span key={i} className={i < level ? 'gc-star-filled' : 'gc-star-empty'}>
          {i < level ? '\u2605' : '\u2606'}
        </span>
      ))}
      {showDups && dupsNeeded > 0 && dupsFilled != null && (
        <div className="gc-dup-icons">
          {Array.from({ length: dupsNeeded }, (_, i) => (
            <div key={i} className={`gc-dup-icon${i < dupsFilled ? ' filled' : ''}`} />
          ))}
        </div>
      )}
      {!showDups && nextThreshold > 0 && xp != null && xp > 0 && (
        <div className="gc-star-progress" title={`${xp - currentThreshold}/${nextThreshold - currentThreshold} to next star`}>
          <div className="gc-star-progress-fill" style={{ width: `${Math.min(100, progress * 100)}%` }} />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// StatBar
// ---------------------------------------------------------------------------

export function StatBar({ stat, label, value, bonus, max = 10, compact = false }: {
  stat: string
  label: string
  value: number
  bonus?: number
  max?: number
  compact?: boolean
}) {
  const basePct = Math.min(100, (value / max) * 100)
  const bonusPct = bonus ? Math.min(100 - basePct, (bonus / max) * 100) : 0
  const total = Math.min(max, value + (bonus ?? 0))
  const gradient = STAT_COLORS[stat]?.gradient ?? STAT_COLORS.antiquity.gradient

  if (compact) {
    return (
      <div className="gc-stat-row">
        <span className="gc-stat-label">{label}</span>
        <div className="gc-stat-bar">
          <div className="gc-stat-fill" style={{ width: `${basePct}%`, background: gradient }} />
          {bonusPct > 0 && <div className="gc-stat-fill-bonus" style={{ width: `${bonusPct}%` }} />}
        </div>
        <span className={`gc-stat-val${bonus && bonus > 0 ? ' gc-stat-val-boosted' : ''}`}>{total}</span>
      </div>
    )
  }

  return (
    <div className="gc-stat-row">
      <span className="gc-stat-icon">{STAT_META.find(s => s.key === stat)?.icon ?? ''}</span>
      <span className="gc-stat-label">{label}</span>
      <div className="gc-stat-bar">
        <div className="gc-stat-fill" style={{ width: `${basePct}%`, background: gradient }} />
        {bonusPct > 0 && <div className="gc-stat-fill-bonus" style={{ width: `${bonusPct}%` }} />}
      </div>
      <span className={`gc-stat-val${bonus && bonus > 0 ? ' gc-stat-val-boosted' : ''}`}>{total}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// GameCard
// ---------------------------------------------------------------------------

interface GameCardProps {
  card: CardData
  variant?: 'tile' | 'showcase' | 'row'
  onClick?: () => void
  action?: React.ReactNode
  onRemove?: () => void
  index?: number
  /** Per-stat bonuses from synergies, e.g. { antiquity: 2, mystery: 1 } */
  bonuses?: Partial<Record<string, number>>
  /** Short description (showcase only, 3-line clamp) */
  description?: string
  /** Coordinates string, e.g. "37.22° N, 38.92° E" (showcase only) */
  coords?: string
  /** Override color for the type (site_type) badge */
  typeBadgeColor?: string
  /** Override color for the period badge */
  periodBadgeColor?: string
  /** Number of duplicate card slots filled (star display) */
  dupsFilled?: number
}

export function GameCard({ card, variant = 'tile', onClick, action, onRemove, index, bonuses, description, coords, typeBadgeColor, periodBadgeColor, dupsFilled }: GameCardProps) {
  const rarity = getRarity(card.rarity_tier)
  const powerColor = RARITY_POWER_COLORS[card.rarity_tier] ?? '#888'

  // Row variant — compact deck list item
  if (variant === 'row') {
    return (
      <div
        className="gc-row"
        style={{ borderLeftColor: rarity.color }}
      >
        {index != null && <span className="gc-row-num">{index}.</span>}
        {card.thumbnail_url && (
          <img src={card.thumbnail_url} alt="" className="gc-row-thumb" />
        )}
        <div className="gc-row-info">
          <span className="gc-row-name">{card.name}</span>
          <span className="gc-row-power" style={{ color: powerColor }}>
            {'\u26a1'} {card.total_power}
          </span>
        </div>
        {onRemove && (
          <button className="gc-row-remove" onClick={onRemove}>&minus;</button>
        )}
      </div>
    )
  }

  // Shared card sizing
  const isShowcase = variant === 'showcase'
  const countryCode = card.country ? getCountryCode(card.country)?.toLowerCase() : null
  const ribbonBg = RARITY_RIBBON_BG[card.rarity_tier] ?? RARITY_RIBBON_BG[1]
  const ribbonStyle: React.CSSProperties = { background: ribbonBg }

  // Compute power (base + bonuses)
  const bonusTotal = bonuses
    ? Object.values(bonuses).reduce<number>((sum, b) => sum + (b ?? 0), 0)
    : 0
  const displayPower = card.total_power + bonusTotal

  return (
    <div
      className={`gc-card gc-${rarity.slug}${isShowcase ? ' gc-showcase' : ' gc-tile'}`}
      style={{
        borderWidth: `${rarity.borderWidth}px`,
        boxShadow: rarity.glow !== 'none' ? rarity.glow : undefined,
      }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {/* Rarity ribbon */}
      <div className="gc-ribbon" style={ribbonStyle}>{rarity.name}</div>

      {/* Hero image */}
      <div className="gc-hero">
        {card.thumbnail_url ? (
          <img src={card.thumbnail_url} alt={card.name} loading="lazy" />
        ) : (
          <div className="gc-hero-placeholder" />
        )}
        <div className="gc-vignette" />
        <div className="gc-hero-content">
          <div className="gc-title">{card.name}</div>
          <div className="gc-badges">
            {card.site_type && (
              <span className="gc-badge" style={{ borderColor: typeBadgeColor ?? '#ff5500', color: typeBadgeColor ?? '#ff5500' }}>
                {card.site_type}
              </span>
            )}
            {card.period_name && (
              <span className="gc-badge" style={{ borderColor: periodBadgeColor ?? '#ffcc00', color: periodBadgeColor ?? '#ffcc00' }}>
                {card.period_name}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Body — country + coords + description */}
      <div className="gc-body">
        {card.country && (
          <div className="gc-country">
            {countryCode && (
              <img src={`https://flagcdn.com/w40/${countryCode}.webp`} alt={countryCode.toUpperCase()} />
            )}
            {card.country}
            {isShowcase && coords && (
              <span className="gc-coords">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
                {coords}
              </span>
            )}
          </div>
        )}
        {isShowcase && (description || card.card_description) && (() => {
          const text = description || card.card_description || ''
          const len = text.length
          const fontSize = len <= 100 ? '0.68rem' : len <= 150 ? '0.62rem' : '0.56rem'
          return <div className="gc-desc" style={{ fontSize }}>{text}</div>
        })()}
      </div>

      {/* Stats */}
      {isShowcase && (
        <div className="gc-stats">
          {STAT_META.map(s => (
            <StatBar
              key={s.key}
              stat={s.key}
              label={s.label}
              value={getStatValue(card, s.cardDataKey)}
              bonus={bonuses?.[s.key]}
            />
          ))}
        </div>
      )}

      {/* Footer — stars + power */}
      <div className="gc-footer">
        {card.star_level != null && card.star_level >= 0 ? (
          <StarDisplay
            level={card.star_level}
            xp={card.card_xp}
            showDups={isShowcase}
            dupsFilled={dupsFilled ?? 0}
          />
        ) : <div />}
        <div className="gc-power-badge">
          <span className="gc-power-icon" style={{ color: powerColor }}>{'\u26a1'}</span>
          <span className="gc-power" style={{ color: powerColor }}>{displayPower}</span>
        </div>
      </div>

      {/* Action slot (pick button in collection browser) */}
      {action && <div className="gc-action">{action}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// GameCardDetail (modal)
// ---------------------------------------------------------------------------

export function GameCardDetail({ card, onClose, bonuses }: {
  card: CardData
  onClose: () => void
  bonuses?: Partial<Record<string, number>>
}) {
  const rarity = getRarity(card.rarity_tier)

  return (
    <div className="gc-detail-overlay" onClick={onClose}>
      <div
        className="gc-detail"
        style={{
          borderColor: rarity.color,
          boxShadow: rarity.glow !== 'none' ? rarity.glow : undefined,
        }}
        onClick={e => e.stopPropagation()}
      >
        <button className="gc-detail-close" onClick={onClose}>&times;</button>
        {card.thumbnail_url && (
          <img src={card.thumbnail_url} alt={card.name} className="gc-detail-img" />
        )}
        <h2>{card.name}</h2>
        <p className="gc-detail-meta">
          {[card.period_name, card.country, card.category_group].filter(Boolean).join(' | ')}
        </p>
        <p className="gc-detail-rarity" style={{ color: rarity.color }}>
          {rarity.name} &middot; Tier {card.rarity_tier}
        </p>
        {card.card_description && (
          <p className="gc-detail-desc">{card.card_description}</p>
        )}
        <div className="gc-detail-stats">
          {STAT_META.map(s => (
            <StatBar
              key={s.key}
              stat={s.key}
              label={s.label}
              value={getStatValue(card, s.cardDataKey)}
              bonus={bonuses?.[s.key]}
              compact
            />
          ))}
        </div>
        <div className="gc-detail-total-power">Total Power: {card.total_power}</div>
        {card.star_level != null && card.star_level >= 1 && (
          <div className="gc-detail-stars">
            <StarDisplay level={card.star_level} xp={card.card_xp} />
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// EmpireCard
// ---------------------------------------------------------------------------

interface EmpireCardProps {
  empire: {
    name: string
    region: string
    period?: string
    thematicStat: string
    /** Override icon — if omitted, derived from thematicStat */
    statIcon?: string
    /** Override color — if omitted, derived from thematicStat */
    statColor?: string
    desc: string
    /** Empire accent color — if omitted, derived from thematicStat */
    color?: string
    /** Empire glow color — if omitted, derived from thematicStat */
    colorGlow?: string
    /** "via expedition" etc. — shown in footer if provided */
    acquiredVia?: string
  }
}

export function EmpireCard({ empire }: EmpireCardProps) {
  const accent = STAT_ACCENTS[empire.thematicStat] ?? STAT_ACCENTS.mystery
  const color = empire.color ?? accent.color
  const colorGlow = empire.colorGlow ?? accent.glow
  const statColor = empire.statColor ?? accent.color
  const statIcon = empire.statIcon ?? accent.icon
  const statLabel = empire.thematicStat.replace(/_/g, ' ')

  return (
    <div
      className="gc-empire"
      style={{ '--empire-color': color, '--empire-glow': colorGlow } as React.CSSProperties}
    >
      <div className="gc-empire-accent" />
      <div className="gc-empire-header">
        <div className="gc-empire-icon">{'\u{1f451}'}</div>
        <div className="gc-empire-name">{empire.name}</div>
        <div className="gc-empire-region">{empire.region}</div>
      </div>
      {empire.period && <div className="gc-empire-period">{empire.period}</div>}
      <div className="gc-empire-desc">{empire.desc}</div>
      <div className="gc-empire-stat">
        <span className="gc-empire-stat-icon" style={{ color: statColor }}>{statIcon}</span>
        <span className="gc-empire-stat-label">Thematic Stat</span>
        <span className="gc-empire-stat-value" style={{ color: statColor }}>{statLabel}</span>
      </div>
      <div className="gc-empire-footer">
        {empire.acquiredVia ? (
          <span className="gc-empire-commander-bonus">Earned via {empire.acquiredVia}</span>
        ) : (
          <>
            <span className="gc-empire-commander-label">Commander Bonus</span>
            <span className="gc-empire-commander-bonus">+1 {statLabel} to 3 homeland sites</span>
          </>
        )}
      </div>
    </div>
  )
}
