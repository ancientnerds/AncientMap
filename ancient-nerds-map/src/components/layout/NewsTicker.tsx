/**
 * NewsTicker — NERV-style scrolling ticker tape.
 * Replaces static stats bar with a crawling readout of key stats.
 * Content is doubled for seamless infinite loop.
 */

import { useMemo } from 'react'
import type { NewsStats } from '../../types/news'
import './news-ticker.css'

interface NewsTickerProps {
  stats: NewsStats | null
  totalDisplayed: number
}

function formatHours(h: number): string {
  if (h >= 24) return `${Math.round(h / 24)}d ${Math.round(h % 24)}h`
  return `${Math.round(h)}h`
}

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return 'N/A'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function NewsTicker({ stats, totalDisplayed }: NewsTickerProps) {
  const items = useMemo(() => {
    if (!stats) return []
    const parts: string[] = []
    parts.push(`${stats.total_items.toLocaleString()} stories extracted`)
    parts.push(`${stats.total_videos.toLocaleString()} videos processed`)
    parts.push(`${stats.total_channels} channels monitored`)
    parts.push(`${formatHours(stats.total_duration_hours)} of footage analyzed`)
    if (stats.latest_item_date) {
      parts.push(`latest: ${formatRelative(stats.latest_item_date)}`)
    }
    if (stats.rejected) {
      const total = stats.rejected.low_significance + stats.rejected.duplicate + stats.rejected.verified_rejected
      if (total > 0) parts.push(`${total} filtered out`)
    }
    if (stats.total_articles > 0) {
      parts.push(`${stats.total_articles} weekly journals`)
    }
    parts.push(`${totalDisplayed} displayed`)
    return parts
  }, [stats, totalDisplayed])

  if (items.length === 0) return null

  return (
    <div className="news-ticker">
      <div className="news-ticker-track">
        {items.map((text, i) => (
          <span key={i}>&#9679; {text}</span>
        ))}
        {items.map((text, i) => (
          <span key={`dup-${i}`}>&#9679; {text}</span>
        ))}
      </div>
    </div>
  )
}
