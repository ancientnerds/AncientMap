import { useEffect, useState } from 'react'

export interface CurrentResearch {
  running: {
    question: string
    started_at: string | null
    elapsed_s: number | null
    sites_found: number
    llm_calls: number
    total_tokens: number
  } | null
  queued_batch: number
  last_published: { title: string; slug: string } | null
}

const POLL_MS = 30_000

/**
 * Live view of the permanent researcher (public endpoint, no auth).
 * Returns null until the first successful fetch; fails silently so the
 * consuming panel can simply render nothing.
 */
export function useCurrentResearch(): CurrentResearch | null {
  const [data, setData] = useState<CurrentResearch | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      fetch('/api/theo/research/current')
        .then((r) => {
          if (!r.ok) throw new Error(`${r.status}`)
          return r.json()
        })
        .then((d) => {
          if (!cancelled) setData(d)
        })
        .catch(() => {
          /* silent — panel hides itself */
        })
    }
    load()
    const timer = setInterval(load, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return data
}
