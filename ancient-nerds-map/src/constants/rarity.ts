/** Single source of truth for rarity theming across all card components. */

export const RARITY_TIERS: Record<number, {
  name: string
  slug: string
  color: string
  glow: string
  borderWidth: number
}> = {
  1: { name: 'Common',    slug: 'common',    color: '#9E9E9E', glow: 'none',                              borderWidth: 1 },
  2: { name: 'Uncommon',  slug: 'uncommon',  color: '#4CAF50', glow: '0 0 18px rgba(76,175,80,0.1)',      borderWidth: 1 },
  3: { name: 'Rare',      slug: 'rare',      color: '#00bcd4', glow: '0 0 22px rgba(0,180,180,0.12)',     borderWidth: 1 },
  4: { name: 'Epic',      slug: 'epic',      color: '#9C27B0', glow: '0 0 26px rgba(156,39,176,0.15)',    borderWidth: 1 },
  5: { name: 'Legendary', slug: 'legendary', color: '#FFC107', glow: '0 0 36px rgba(255,193,7,0.2), inset 0 0 30px rgba(255,193,7,0.03)', borderWidth: 2 },
}

export const STAT_COLORS: Record<string, { gradient: string }> = {
  antiquity:          { gradient: 'linear-gradient(90deg, #ff8c00, #ffaa33)' },
  fortification:      { gradient: 'linear-gradient(90deg, #c02023, #e55555)' },
  cultural_influence: { gradient: 'linear-gradient(90deg, #e91e90, #ff6eb4)' },
  mystery:            { gradient: 'linear-gradient(90deg, #00b4b4, #33dddd)' },
  legacy:             { gradient: 'linear-gradient(90deg, #8833dd, #aa66ee)' },
}

export type StatKey = 'antiquity' | 'fortification' | 'cultural_influence' | 'mystery' | 'legacy'

export const STAT_META: { key: string; label: string; icon: string; cardDataKey: StatKey }[] = [
  { key: 'antiquity',          label: 'Antiquity',  icon: '\u23f1', cardDataKey: 'antiquity' },
  { key: 'fortification',      label: 'Fortification', icon: '\u2694', cardDataKey: 'fortification' },
  { key: 'cultural_influence', label: 'Cultural',   icon: '\u2605', cardDataKey: 'cultural_influence' },
  { key: 'mystery',            label: 'Mystery',    icon: '\u2754', cardDataKey: 'mystery' },
  { key: 'legacy',             label: 'Legacy',     icon: '\u{1f3c6}', cardDataKey: 'legacy' },
]

/** Per-stat accent for EmpireCard fallback styling (derived from stat gradients). */
export const STAT_ACCENTS: Record<string, { icon: string; color: string; glow: string }> = {
  antiquity:          { icon: '\u23f1', color: '#ff8c00', glow: 'rgba(255, 140, 0, 0.25)' },
  fortification:      { icon: '\u2694', color: '#c02023', glow: 'rgba(192, 32, 35, 0.25)' },
  cultural_influence: { icon: '\u2605', color: '#e91e90', glow: 'rgba(233, 30, 144, 0.25)' },
  mystery:            { icon: '\u2754', color: '#00b4b4', glow: 'rgba(0, 180, 180, 0.25)' },
  legacy:             { icon: '\u{1f3c6}', color: '#8833dd', glow: 'rgba(136, 51, 221, 0.25)' },
}

/** Power color per rarity (for the bolt icon + power number). */
export const RARITY_POWER_COLORS: Record<number, string> = {
  1: '#888888',
  2: '#4CAF50',
  3: '#00bcd4',
  4: '#ce93d8',
  5: '#FFC107',
}

/** Ribbon background per rarity — all gradients with dark text. */
export const RARITY_RIBBON_BG: Record<number, string> = {
  1: 'linear-gradient(90deg, #888, #bbb, #888)',
  2: 'linear-gradient(90deg, #2E7D32, #4CAF50, #2E7D32)',
  3: 'linear-gradient(90deg, #00838F, #00BCD4, #00838F)',
  4: 'linear-gradient(90deg, #6A1B9A, #AB47BC, #6A1B9A)',
  5: 'linear-gradient(90deg, #FF8F00, #FFC107, #FF8F00)',
}
