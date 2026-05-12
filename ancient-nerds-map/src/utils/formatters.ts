export function formatDuration(minutes: number): string {
  const totalSeconds = Math.round(minutes * 60)
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function formatDurationMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Compact token count: 1_234 -> "1.2k", 1_234_567 -> "1.2M". */
export function formatTokenCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

export function formatCoord(coord: number, isLat: boolean): string {
  const abs = Math.abs(coord)
  const dir = isLat ? (coord >= 0 ? 'N' : 'S') : (coord >= 0 ? 'E' : 'W')
  return `${abs.toFixed(4)}\u00B0 ${dir}`
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  return `${months}mo ago`
}

export function formatRelativeDate(isoDate: string): string {
  const d = new Date(isoDate)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  if (diffMs < 0) {
    const futureMin = Math.floor(-diffMs / 60000)
    if (futureMin < 1) return 'just now'
    if (futureMin < 60) return `in ${futureMin}m`
    const futureHr = Math.floor(futureMin / 60)
    if (futureHr < 24) return `in ${futureHr}h`
    const futureDays = Math.floor(futureHr / 24)
    return `in ${futureDays}d`
  }
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDays = Math.floor(diffHr / 24)
  if (diffDays < 30) return `${diffDays}d ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: d.getFullYear() !== now.getFullYear() ? 'numeric' : undefined })
}
