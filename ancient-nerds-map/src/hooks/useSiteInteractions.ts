/**
 * Hook for site like/bookmark interactions.
 *
 * Reads auth token from localStorage (works with or without AuthProvider).
 * Redirects to Discord OAuth if user tries to interact while logged out.
 */

import { useState, useEffect, useCallback } from 'react'
import { config } from '../config'

const TOKEN_KEY = 'an_auth_token'

interface SiteInteractions {
  likeCount: number
  liked: boolean
  bookmarked: boolean
  toggleLike: () => void
  toggleBookmark: () => void
}

export function useSiteInteractions(siteId: string | undefined): SiteInteractions {
  const [likeCount, setLikeCount] = useState(0)
  const [liked, setLiked] = useState(false)
  const [bookmarked, setBookmarked] = useState(false)

  // Fetch initial status
  useEffect(() => {
    if (!siteId) return
    const token = localStorage.getItem(TOKEN_KEY)
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    fetch(`${config.api.baseUrl}/interactions/sites/${siteId}/status`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setLikeCount(data.like_count)
          setLiked(data.liked)
          setBookmarked(data.bookmarked)
        }
      })
      .catch(() => {})
  }, [siteId])

  const requireAuth = useCallback((): string | null => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      window.location.href = `${config.api.baseUrl}/auth/discord`
      return null
    }
    return token
  }, [])

  const toggleLike = useCallback(() => {
    if (!siteId) return
    const token = requireAuth()
    if (!token) return

    // Optimistic update
    const wasLiked = liked
    setLiked(!wasLiked)
    setLikeCount(c => wasLiked ? c - 1 : c + 1)

    fetch(`${config.api.baseUrl}/interactions/sites/${siteId}/like`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setLiked(data.liked)
          setLikeCount(data.like_count)
        }
      })
      .catch(() => {
        // Revert on error
        setLiked(wasLiked)
        setLikeCount(c => wasLiked ? c + 1 : c - 1)
      })
  }, [siteId, liked, requireAuth])

  const toggleBookmark = useCallback(() => {
    if (!siteId) return
    const token = requireAuth()
    if (!token) return

    // Optimistic update
    const wasBookmarked = bookmarked
    setBookmarked(!wasBookmarked)

    fetch(`${config.api.baseUrl}/interactions/sites/${siteId}/bookmark`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setBookmarked(data.bookmarked)
        }
      })
      .catch(() => {
        setBookmarked(wasBookmarked)
      })
  }, [siteId, bookmarked, requireAuth])

  return { likeCount, liked, bookmarked, toggleLike, toggleBookmark }
}
