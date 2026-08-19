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
  star_level?: number
  card_xp?: number
  lat?: number
  lon?: number
  empires?: string[]
  empire_count?: number
  card_description?: string | null
}

export interface DeckData {
  id: string
  name: string
  is_active: boolean
  card_ids: string[]
  commander_empire_id: string | null
  created_at: string | null
}

export interface EmpireCardData {
  empire_id: string
  name: string
  region: string
  thematic_stat: string
  description: string
  acquired_via?: string
  acquired_at?: string
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
  level?: number
  xp_progress?: number
  xp_to_next?: number
  // Owning cards ≠ having claimed the starter deck: daily, contributions and
  // achievements grant cards too. Gate the starter button on this, not on count.
  has_claimed_starter?: boolean
}

export interface LeaderboardEntry {
  username: string
  avatar_hash: string | null
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

export interface AchievementData {
  id: string
  category: string
  name: string
  description: string
  tier: string
  reward_credits: number
  reward_xp: number
  reward_card_tier: number | null
  reward_card_count: number
  icon: string
  sort_order: number
  hidden: boolean
  unlocked: boolean
  unlocked_at?: string | null
  claimed: boolean
  claimed_at?: string | null
}

export interface AchievementUnlock {
  id: string
  name: string
  description: string
  tier: string
  icon: string
  reward_credits: number
  reward_xp: number
  reward_card_tier: number | null
  reward_card_count: number
}

export interface AchievementSummary {
  total_available: number
  total_unlocked: number
  unclaimed: number
}
