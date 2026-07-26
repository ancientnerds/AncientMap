import { useState, useEffect, useRef, useCallback } from 'react'
import { config } from '../../config'

const NAV_ITEMS = [
  { page: 'globe', label: 'Globe', href: '/globe.html', icon: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10A15 15 0 0 1 12 2z' },
  { page: 'search', label: 'Search', href: '/search.html', icon: 'M21 21l-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z' },
  { page: 'news', label: 'Stories', href: '/news.html', icon: 'M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1m2 13a2 2 0 0 1-2-2V7m2 13a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2' },
  { page: 'radar', label: 'Radar', href: '/radar.html', icon: 'M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83' },
  { page: 'articles', label: 'Journal', href: '/articles.html', icon: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z' },
  { page: 'lyra', label: 'Lyra', href: '/lyra.html', icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' },
  { page: 'theo', label: 'Research', href: '/theo.html#research-library', icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 9l2 2 4-4' },
  { page: 'knowledge', label: 'Knowledge', href: '/knowledge.html', icon: 'M6 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM6 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM7.8 7.3l8.4 9.4M16.2 7.3l-8.4 9.4M8.5 5.5h7M8.5 18.5h7' },
  { page: 'library', label: 'Library', href: '/library.html', icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253' },
  { page: 'db', label: 'Database', href: '/db.html', icon: 'M12 2C6.48 2 2 3.79 2 6v12c0 2.21 4.48 4 10 4s10-1.79 10-4V6c0-2.21-4.48-4-10-4zM2 12c0 2.21 4.48 4 10 4s10-1.79 10-4' },
  { page: 'game', label: 'Card Game', href: '/game.html', icon: 'M4 4h4v4H4zM14 4h4v4h-4zM4 14h4v4H4zM14 14h4v4h-4zM9 9h4v4H9z' },
  { page: 'api', label: 'API', href: '/api.html', icon: 'M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2z' },
]

// Account/Sign In icons
const ACCOUNT_ICON = 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z'

interface HamburgerNavProps {
  currentPage?: string
  openInNewTab?: boolean
}

/**
 * Check if user is logged in by reading the auth token from localStorage.
 * This avoids requiring AuthProvider on every page.
 */
function useAuthToken(): boolean {
  const [isLoggedIn, setIsLoggedIn] = useState(() => !!localStorage.getItem('an_auth_token'))

  useEffect(() => {
    // Re-check on storage events (e.g. login in another tab)
    const handler = () => setIsLoggedIn(!!localStorage.getItem('an_auth_token'))
    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  }, [])

  return isLoggedIn
}

export default function HamburgerNav({ currentPage, openInNewTab }: HamburgerNavProps) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const isLoggedIn = useAuthToken()

  const updatePos = useCallback(() => {
    if (!btnRef.current) return
    const rect = btnRef.current.getBoundingClientRect()
    setPos({ top: rect.bottom + 4, left: rect.left })
  }, [])

  useEffect(() => {
    if (!open) return
    updatePos()
    const handleClick = (e: MouseEvent) => {
      if (btnRef.current?.contains(e.target as Node)) return
      if (dropRef.current?.contains(e.target as Node)) return
      setOpen(false)
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open, updatePos])

  // Build the auth link based on login state
  const authItem = isLoggedIn
    ? { page: 'account', label: 'Account', href: '/account.html', icon: ACCOUNT_ICON }
    : { page: 'signin', label: 'Sign In', href: `${config.api.baseUrl}/auth/discord?return_to=${encodeURIComponent(window.location.pathname + window.location.search)}`, icon: ACCOUNT_ICON }

  return (
    <div className="hamburger-nav">
      <button
        ref={btnRef}
        className="hamburger-btn"
        onClick={() => setOpen(!open)}
        aria-label="Navigation menu"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      {open && (
        <div
          ref={dropRef}
          className="hamburger-dropdown"
          style={{ position: 'fixed', top: pos.top, left: pos.left }}
        >
          {NAV_ITEMS.map(item => (
            <a
              key={item.page}
              href={item.href}
              className={`hamburger-link${currentPage === item.page ? ' active' : ''}`}
              onClick={() => setOpen(false)}
              {...(openInNewTab ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d={item.icon} />
              </svg>
              {item.label}
            </a>
          ))}
          <div className="hamburger-divider" />
          <a
            href={authItem.href}
            className={`hamburger-link${currentPage === authItem.page ? ' active' : ''}`}
            onClick={() => setOpen(false)}
            {...(openInNewTab ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d={authItem.icon} />
            </svg>
            {authItem.label}
          </a>
        </div>
      )}
    </div>
  )
}
