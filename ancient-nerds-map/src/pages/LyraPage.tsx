/**
 * LyraPage - Dedicated full-page Lyra chat.
 * Accessed via /lyra.html (separate Vite entry point).
 * Renders LyraChatModal in "page" mode — same component, no duplicate logic.
 */

import LyraChatModal from '../components/LyraChatModal'

export default function LyraPage() {
  return (
    <LyraChatModal
      isOpen={true}
      onClose={() => {}}
      mode="page"
    />
  )
}
