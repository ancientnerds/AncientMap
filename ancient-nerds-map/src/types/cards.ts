export interface CardData {
  site_id: string
  name: string
  country: string | null
  period_name: string | null
  period_start: number | null
  thumbnail_url: string | null
  site_type: string | null
  antiquity: number
  fortification: number
  cultural_influence: number
  mystery: number
  legacy: number
  total_power: number
  rarity_tier: number
  rarity_name: string
  category_group: string
  civilization: string | null
  acquired_via?: string
  acquired_at?: string
  lat?: number
  lon?: number
}

export interface DeckData {
  id: string
  name: string
  is_active: boolean
  card_ids: string[]
  created_at: string | null
}

export interface PlayerStats {
  total_cards: number
  wins: number
  losses: number
  draws: number
  win_streak: number
  best_streak: number
  xp: number
  daily_streak: number
  packs_opened: number
}

export interface LeaderboardEntry {
  username: string
  avatar_hash: string | null
  discord_id: string | null
  wins: number
  losses: number
  draws: number
  total_cards: number
  xp: number
  best_streak: number
  daily_streak: number
}

export interface PackInfo {
  cost: number
  cards: number
  guarantees: string[]
}

export interface SynergyDescription {
  label: string
  count: number
  bonus: string
}
