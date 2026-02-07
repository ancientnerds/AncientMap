import { useState, useCallback } from 'react'
import './metadata.css'

interface CopyButtonProps {
  text: string
  title?: string
  size?: number
}

export function CopyButton({ text, title = 'Copy', size = 12 }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [text])

  return (
    <button
      className={`meta-copy-btn ${copied ? 'copied' : ''}`}
      onClick={(e) => { e.stopPropagation(); handleCopy() }}
      onMouseDown={(e) => e.stopPropagation()}
      title={title}
    >
      {copied ? (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      ) : (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
      )}
    </button>
  )
}
