import { useEffect, useState } from 'react'

export type Loaded<T> = { data: T | null; error: 'unauthorized' | 'failed' | null }

/**
 * One /api/stats/<path> resource, refreshed every minute. The an_stats cookie
 * travels with the request (same origin); a 401 means it expired while the
 * page was open — the page then shows the Discord entry again.
 */
export function useStats<T>(path: string, refreshMs = 60_000): Loaded<T> {
  const [state, set] = useState<Loaded<T>>({ data: null, error: null })
  useEffect(() => {
    let alive = true
    const load = async () => {
      const r = await fetch(`/api/stats/${path}`, { credentials: 'same-origin' })
      if (!alive) return
      if (r.status === 401) return set({ data: null, error: 'unauthorized' })
      if (!r.ok) return set({ data: null, error: 'failed' })
      set({ data: (await r.json()) as T, error: null })
    }
    load()
    const t = setInterval(load, refreshMs)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [path, refreshMs])
  return state
}
