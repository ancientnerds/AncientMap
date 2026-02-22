/**
 * OG Card entry point — renders a real SiteCard for Playwright to screenshot.
 * Used by /api/og/{id} to generate Open Graph preview images.
 */

import { createRoot } from 'react-dom/client'
import { useEffect, useState } from 'react'
import { SiteCard } from './components/SiteCard'
import type { SiteData } from './data/sites'
import './styles/index.css'
import './components/site-card.css'

function OgCard() {
  const [site, setSite] = useState<SiteData | null>(null)
  const [error, setError] = useState(false)

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
          category: data.site_type || 'Unknown',
          period: data.period_name || 'Unknown',
          periodStart: data.period_start ?? undefined,
          description: data.description || '',
          image: data.thumbnail_url || undefined,
          sourceId: data.source_id || '',
          coordinates: [data.lon ?? 0, data.lat ?? 0],
        })
      })
      .catch(() => setError(true))
  }, [])

  if (error) return <div data-ready>Error</div>

  if (!site) return null

  return (
    <div
      id="og-card"
      data-ready
      style={{ width: 500, background: '#0a1419', padding: 0 }}
    >
      <SiteCard site={site} />
    </div>
  )
}

createRoot(document.getElementById('og-root')!).render(<OgCard />)
