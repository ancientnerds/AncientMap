import { useState, useCallback, useEffect } from 'react'
import type { SiteData } from '../../../data/sites'
import { config } from '../../../config'

interface UseAdminModeOptions {
  site: SiteData
  onSiteUpdate?: (siteId: string, updatedSite: SiteData) => void
}

interface UseAdminModeReturn {
  // State
  showAdminPin: boolean
  isAdminMode: boolean
  editedSite: SiteData | null
  isSaving: boolean
  saveError: string | null
  localSite: SiteData

  // Handlers
  setShowAdminPin: (show: boolean) => void
  enterAdminMode: () => void
  handleSave: () => Promise<void>
  handleCancelEdit: () => void
  setEditedSite: (site: SiteData | null) => void
}

export function useAdminMode({
  site,
  onSiteUpdate
}: UseAdminModeOptions): UseAdminModeReturn {
  // Local site data that can be updated after save (overrides prop)
  const [localSite, setLocalSite] = useState<SiteData>(site)

  // Sync localSite when site prop changes (different popup opened)
  useEffect(() => {
    setLocalSite(site)
  }, [site.id])

  // Admin mode state
  const [showAdminPin, setShowAdminPin] = useState(false)
  const [isAdminMode, setIsAdminMode] = useState(false)
  const [editedSite, setEditedSite] = useState<SiteData | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Enter admin mode after PIN validation
  const enterAdminMode = useCallback(() => {
    setEditedSite({ ...localSite })
    setIsAdminMode(true)
    setShowAdminPin(false)
  }, [localSite])

  // Admin mode save handler
  const handleSave = useCallback(async () => {
    if (!editedSite) return
    setIsSaving(true)
    setSaveError(null)
    try {
      const response = await fetch(`${config.api.baseUrl}/sites/${localSite.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editedSite)
      })
      if (response.ok) {
        // Clear Service Worker cache for sites API to ensure fresh data on refresh
        if ('caches' in window) {
          try {
            const cache = await caches.open('api-sites')
            const keys = await cache.keys()
            await Promise.all(keys.map(key => cache.delete(key)))
            console.log('[Admin] Cleared Service Worker sites cache')
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
  }, [editedSite, localSite.id, onSiteUpdate])

  // Cancel admin edit
  const handleCancelEdit = useCallback(() => {
    setIsAdminMode(false)
    setEditedSite(null)
    setSaveError(null)
  }, [])

  return {
    // State
    showAdminPin,
    isAdminMode,
    editedSite,
    isSaving,
    saveError,
    localSite,

    // Handlers
    setShowAdminPin,
    enterAdminMode,
    handleSave,
    handleCancelEdit,
    setEditedSite
  }
}
