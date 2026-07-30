import { useEffect, useState } from 'react'
import { config } from '../config'

/**
 * True when the logged-in user has the founder role (checked via /api/auth/me).
 * Same localStorage-token pattern as SitePopup/useSiteDetailData.
 */
export function useIsFounder(): boolean {
  const [isFounder, setIsFounder] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('an_auth_token')
    if (!token) return
    fetch(`${config.api.baseUrl}/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` },
    })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data?.is_founder) setIsFounder(true) })
      .catch(() => {})
  }, [])

  return isFounder
}
