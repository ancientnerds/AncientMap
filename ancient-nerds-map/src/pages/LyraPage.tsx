/**
 * LyraPage - Dedicated full-page Lyra chat.
 * Accessed via /lyra.html (separate Vite entry point).
 * Renders LyraChatModal in "page" mode — same component, no duplicate logic.
 *
 * Context arrives via URL params: ?site=<uuid> (SitePopupOverlay) or
 * ?news=<id> (NewsFeedPage story cards).
 */

import { useMemo } from 'react'
import LyraChatModal from '../components/LyraChatModal'
import type { LyraContextType } from '../types/ai'

export default function LyraPage() {
  const context = useMemo((): { type: LyraContextType; id?: string } => {
    const params = new URLSearchParams(window.location.search)
    const siteId = params.get('site')
    if (siteId) return { type: 'site', id: siteId }
    const newsId = params.get('news')
    if (newsId) return { type: 'news', id: newsId }
    return { type: 'global' }
  }, [])

  return (
    <LyraChatModal
      isOpen={true}
      onClose={() => {}}
      contextType={context.type}
      contextId={context.id}
      mode="page"
    />
  )
}
