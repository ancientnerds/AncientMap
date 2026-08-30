/**
 * Share button around the app-wide share flow (utils/share.ts), with the
 * "copied" flash NewsCard introduced: the native share sheet is its own
 * feedback, only the clipboard path swaps to the check icon for 1.5s.
 *
 * Renders fine through renderToString — the browser APIs live entirely in
 * the click handler, so the SSR pages (StoryPage) can carry it too.
 */

import { useState } from 'react'

import { shareOrCopy } from '../utils/share'

interface ShareButtonProps {
  /** Title handed to the native share sheet. */
  title: string
  /** Canonical public URL — never window.location: a story shared from
      the globe panel or a localhost tab has to open the story page. */
  url: string
  className: string
  /** Optional visible text next to the icon (icon-only when omitted). */
  label?: string
}

export default function ShareButton({ title, url, className, label }: ShareButtonProps) {
  const [copied, setCopied] = useState(false)

  const handleShare = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const result = await shareOrCopy(title, url)
    if (result !== 'copied') return
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      className={`${className}${copied ? ' copied' : ''}`}
      onClick={handleShare}
      title={copied ? 'Link copied' : 'Share story'}
      aria-label={copied ? 'Link copied' : 'Share story'}
    >
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
      )}
      {label && <span>{label}</span>}
    </button>
  )
}
