import { useState, useEffect } from 'react'
import { config } from '../../config'
import { apiDetailToSiteData } from '../../utils/siteApi'
import { hasMetadataFields } from '../../config/sourceFields'
import { OfflineFetch } from '../../services/OfflineFetch'
import { DataStore } from '../../data/DataStore'
import type { SiteData } from '../../data/sites'

interface UseSiteDetailDataReturn {
  site: SiteData | null
  isLoading: boolean
  error: string | null
  rawData: Record<string, unknown> | null
  rawDataLoading: boolean
  isFounder: boolean
}

export function useSiteDetailData(siteId: string | null): UseSiteDetailDataReturn {
  const [site, setSite] = useState<SiteData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rawData, setRawData] = useState<Record<string, unknown> | null>(null)
  const [rawDataLoading] = useState(false)
  const [isFounder, setIsFounder] = useState(false)

  // Standalone page loaded over HTTP — force online mode so gallery/content fetches fire
  useEffect(() => { OfflineFetch.setOfflineMode(false) }, [])

  // Check founder status. The token is read inside the effect: localStorage
  // is a browser API and this hook renders during renderToString (SitePage
  // sits in the SSR registry), where only effects are skipped.
  useEffect(() => {
    const authToken = localStorage.getItem('an_auth_token')
    if (!authToken) return
    fetch(`${config.api.baseUrl}/auth/me`, {
      headers: { 'Authorization': `Bearer ${authToken}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.is_founder) setIsFounder(true) })
      .catch(() => {})
  }, [])

  // Fetch site data
  useEffect(() => {
    if (!siteId) {
      setError('No site ID provided')
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    setError(null)

    // Load source metadata (for display names/colors) in parallel with the site fetch
    Promise.all([
      DataStore.loadSources(),
      fetch(`${config.api.baseUrl}/sites/${siteId}`)
        .then(res => {
          if (!res.ok) throw new Error(res.status === 404 ? 'Site not found' : `Failed to load site (${res.status})`)
          return res.json()
        }),
    ])
      .then(([, data]) => {
        const siteData = apiDetailToSiteData(data)
        setSite(siteData)

        // Extract rawData if present and source has metadata fields
        if (hasMetadataFields(siteData.sourceId) && data.rawData) {
          setRawData(data.rawData)
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setIsLoading(false))
  }, [siteId])

  return { site, isLoading, error, rawData, rawDataLoading, isFounder }
}
