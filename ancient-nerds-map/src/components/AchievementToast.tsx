/**
 * AchievementToast — slide-in notification when achievements unlock.
 * Renders a stack of toasts at top-right, auto-dismisses after 5s.
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import type { AchievementUnlock } from '../types/cards'
import '../styles/achievement-toast.css'

const RARITY_LABELS: Record<number, string> = {
  1: 'Common',
  2: 'Uncommon',
  3: 'Rare',
  4: 'Epic',
  5: 'Legendary',
}

const TIER_COLORS: Record<string, string> = {
  bronze: '#cd7f32',
  silver: '#c0c0c0',
  gold: '#ffd700',
  platinum: '#e5e4e2',
}

interface ToastItem {
  id: string
  achievement: AchievementUnlock
  exiting: boolean
}

// Global event bus for achievement unlocks
type AchievementListener = (achievements: AchievementUnlock[]) => void
const listeners: Set<AchievementListener> = new Set()

export function notifyAchievements(achievements: AchievementUnlock[]): void {
  if (!achievements || achievements.length === 0) return
  listeners.forEach(fn => fn(achievements))
}

/**
 * Call this on any API response to auto-show toasts for achievements_unlocked.
 */
export function handleAchievementResponse(data: Record<string, unknown>): void {
  const unlocked = data?.achievements_unlocked as AchievementUnlock[] | undefined
  if (unlocked && unlocked.length > 0) {
    notifyAchievements(unlocked)
  }
}

export default function AchievementToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const counterRef = useRef(0)

  const addToasts = useCallback((achievements: AchievementUnlock[]) => {
    const newToasts = achievements.map(a => ({
      id: `${a.id}-${counterRef.current++}`,
      achievement: a,
      exiting: false,
    }))
    setToasts(prev => [...prev, ...newToasts])
  }, [])

  useEffect(() => {
    listeners.add(addToasts)
    return () => { listeners.delete(addToasts) }
  }, [addToasts])

  // Auto-dismiss after 5s
  useEffect(() => {
    if (toasts.length === 0) return
    const timer = setTimeout(() => {
      setToasts(prev => {
        if (prev.length === 0) return prev
        // Mark first non-exiting toast as exiting
        const idx = prev.findIndex(t => !t.exiting)
        if (idx === -1) return prev
        const updated = [...prev]
        updated[idx] = { ...updated[idx], exiting: true }
        return updated
      })
    }, 5000)
    return () => clearTimeout(timer)
  }, [toasts])

  // Remove exiting toasts after animation
  useEffect(() => {
    const exiting = toasts.filter(t => t.exiting)
    if (exiting.length === 0) return
    const timer = setTimeout(() => {
      setToasts(prev => prev.filter(t => !t.exiting))
    }, 400)
    return () => clearTimeout(timer)
  }, [toasts])

  if (toasts.length === 0) return null

  return (
    <div className="achievement-toast-container">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`achievement-toast ${t.exiting ? 'exiting' : ''}`}
          style={{ borderLeftColor: TIER_COLORS[t.achievement.tier] || TIER_COLORS.bronze }}
        >
          <div className="achievement-toast-icon">{t.achievement.icon}</div>
          <div className="achievement-toast-body">
            <div className="achievement-toast-title">Achievement Unlocked!</div>
            <div className="achievement-toast-name">{t.achievement.name}</div>
            <div className="achievement-toast-rewards">
              {t.achievement.reward_credits > 0 && (
                <span className="achievement-toast-reward">{t.achievement.reward_credits} cr</span>
              )}
              {t.achievement.reward_xp > 0 && (
                <span className="achievement-toast-reward">{t.achievement.reward_xp} xp</span>
              )}
              {t.achievement.reward_card_tier && t.achievement.reward_card_count > 0 && (
                <span className="achievement-toast-reward">
                  {t.achievement.reward_card_count}x {RARITY_LABELS[t.achievement.reward_card_tier] || 'Card'}
                </span>
              )}
            </div>
          </div>
          <button
            className="achievement-toast-close"
            onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  )
}
