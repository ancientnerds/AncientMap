/**
 * OG Card entry point — renders a real SiteCard for Playwright to screenshot.
 * Used by /api/og/{id} to generate Open Graph preview images.
 */

import { createRoot } from 'react-dom/client'
import { useEffect, useState, useRef } from 'react'
import { SiteCard } from './components/SiteCard'
import type { SiteData } from './data/sites'
import './styles/index.css'
import './components/site-card.css'

function OgCard() {
  const [site, setSite] = useState<SiteData | null>(null)
  const [error, setError] = useState(false)
  const [ready, setReady] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('id')
    if (!id) { setError(true); return }

    fetch(`/api/sites/${id}`)
      .then(res => { if (!res.ok) throw new Error(); return res.json() })
      .then(data => {
        setSite({
          id: data.id,
          title: data.name || 'Unknown Site',
          location: data.country || '',
          category: data.type || 'Unknown',
          period: data.periodName || 'Unknown',
          periodStart: data.periodStart ?? undefined,
          description: data.description || '',
          image: data.thumbnailUrl || undefined,
          sourceId: data.sourceId || '',
          coordinates: [data.lon ?? 0, data.lat ?? 0],
        })
      })
      .catch(() => setError(true))
  }, [])

  // Wait for images to load before signaling ready
  useEffect(() => {
    if (!site || ready) return
    const el = cardRef.current
    if (!el) return

    const imgs = el.querySelectorAll('img')
    if (imgs.length === 0) { setReady(true); return }

    let loaded = 0
    const total = imgs.length
    const check = () => { if (++loaded >= total) setReady(true) }
    imgs.forEach(img => {
      if (img.complete) { check(); return }
      img.addEventListener('load', check, { once: true })
      img.addEventListener('error', check, { once: true })
    })
    // Fallback timeout — don't wait forever
    const timer = setTimeout(() => setReady(true), 5000)
    return () => clearTimeout(timer)
  }, [site, ready])

  if (error) return <div data-ready>Error</div>
  if (!site) return null

  return (
    <div
      id="og-card"
      ref={cardRef}
      data-ready={ready || undefined}
      style={{ width: 500, background: '#0a1419', padding: 16 }}
    >
      <SiteCard site={site} sourceName="Ancient Nerds" />
    </div>
  )
}

createRoot(document.getElementById('og-root')!).render(<OgCard />)
