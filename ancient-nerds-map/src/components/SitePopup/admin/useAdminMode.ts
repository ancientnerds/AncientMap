import { useState, useCallback, useEffect } from 'react'
import type { SiteData } from '../../../data/sites'
import { config } from '../../../config'

interface UseAdminModeOptions {
  site: SiteData
  onSiteUpdate?: (siteId: string, updatedSite: SiteData) => void
  authToken?: string | null
}

interface UseAdminModeReturn {
  // State
  isAdminMode: boolean
  editedSite: SiteData | null
  isSaving: boolean
  saveError: string | null
  localSite: SiteData

  // Handlers
  enterAdminMode: () => void
  handleSave: () => Promise<void>
  handleCancelEdit: () => void
  setEditedSite: (site: SiteData | null) => void
}

export function useAdminMode({
  site,
  onSiteUpdate,
  authToken
}: UseAdminModeOptions): UseAdminModeReturn {
  // Local site data that can be updated after save (overrides prop)
  const [localSite, setLocalSite] = useState<SiteData>(site)

  // Sync localSite when site prop changes (different popup opened)
  useEffect(() => {
    setLocalSite(site)
  }, [site.id])

  // Admin mode state
  const [isAdminMode, setIsAdminMode] = useState(false)
  const [editedSite, setEditedSite] = useState<SiteData | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Enter admin mode directly (no PIN step)
  const enterAdminMode = useCallback(() => {
    setEditedSite({ ...localSite })
    setIsAdminMode(true)
  }, [localSite])

  // Admin mode save handler
  const handleSave = useCallback(async () => {
    if (!editedSite) return
    setIsSaving(true)
    setSaveError(null)
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`

      const response = await fetch(`${config.api.baseUrl}/sites/${localSite.id}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(editedSite)
      })
      if (response.ok) {
        // Clear Service Worker cache for sites API to ensure fresh data on refresh
        if ('caches' in window) {
          try {
            const cache = await caches.open('api-sites')
            const keys = await cache.keys()
            await Promise.all(keys.map(key => cache.delete(key)))
          } catch (e) {
            console.warn('[Admin] Could not clear SW cache:', e)
          }
        }
        // Update local state with edited data and exit admin mode
        setLocalSite(editedSite)
        // Notify parent to update sites array for tooltip/UI refresh
        onSiteUpdate?.(localSite.id, editedSite)
        setIsAdminMode(false)
        setEditedSite(null)
      } else {
        const err = await response.json()
        setSaveError(err.message || 'Failed to save')
      }
    } catch (err) {
      console.error('Failed to save:', err)
      setSaveError('Network error - failed to save')
    }
    setIsSaving(false)
  }, [editedSite, localSite.id, onSiteUpdate, authToken])

  // Cancel admin edit
  const handleCancelEdit = useCallback(() => {
    setIsAdminMode(false)
    setEditedSite(null)
    setSaveError(null)
  }, [])

  return {
    // State
    isAdminMode,
    editedSite,
    isSaving,
    saveError,
    localSite,

    // Handlers
    enterAdminMode,
    handleSave,
    handleCancelEdit,
    setEditedSite
  }
}
