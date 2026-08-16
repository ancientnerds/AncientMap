/**
 * AuthContext — Discord OAuth authentication state.
 *
 * Stores JWT in localStorage. On mount, validates token via /api/auth/me.
 * Provides user profile, credits, and login/logout actions.
 */

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { config } from '../config'

export interface AuthUser {
  id: string
  discord_id: string
  username: string
  avatar_url: string | null
  roles: string[]
  credits: number
  is_unlimited: boolean
  is_og_nerd: boolean
  is_founder: boolean
  tier: string
  next_grant_date: string | null
  created_at: string | null
}

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  isLoggedIn: boolean
  isLoading: boolean
  login: (token: string) => void
  logout: () => void
  refreshCredits: () => Promise<void>
  updateCredits: (credits: number) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const TOKEN_KEY = 'an_auth_token'
const COOKIE_NAME = 'an_auth_token'

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(() => {
    // Server render (renderToString): no cookie, no storage — the page
    // renders logged out; the browser evaluates this initializer itself
    // on mount.
    if (typeof window === 'undefined') return null
    // The OAuth callback sets a short-lived (120s) cookie that the frontend
    // promotes into localStorage. We used to clear the cookie immediately
    // after reading it, but in multi-tab setups that races: whichever tab
    // mounted first stole the token and the others saw nothing. Now we let
    // the cookie expire on its own — every tab gets to read it during the
    // ~2 minute window, and they all end up with the same JWT in localStorage.
    const cookieToken = readCookie(COOKIE_NAME)
    if (cookieToken) {
      localStorage.setItem(TOKEN_KEY, cookieToken)
      return cookieToken
    }
    return localStorage.getItem(TOKEN_KEY)
  })
  const [isLoading, setIsLoading] = useState(
    () =>
      typeof window !== 'undefined' &&
      (!!localStorage.getItem(TOKEN_KEY) || !!readCookie(COOKIE_NAME)),
  )

  const clearAuth = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    setIsLoading(false)
  }, [])

  const validateToken = useCallback(async (jwt: string) => {
    try {
      const resp = await fetch(`${config.api.baseUrl}/auth/me`, {
        headers: { 'Authorization': `Bearer ${jwt}` },
      })
      if (!resp.ok) {
        clearAuth()
        return
      }
      const data: AuthUser = await resp.json()
      setUser(data)
    } catch {
      clearAuth()
    } finally {
      setIsLoading(false)
    }
  }, [clearAuth])

  // On mount: validate existing token
  useEffect(() => {
    if (token) {
      validateToken(token)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback((newToken: string) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
    setIsLoading(true)
    validateToken(newToken)
  }, [validateToken])

  const logout = useCallback(() => {
    clearAuth()
  }, [clearAuth])

  const refreshCredits = useCallback(async () => {
    if (!token) return
    try {
      const resp = await fetch(`${config.api.baseUrl}/auth/credits`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (resp.ok) {
        const data = await resp.json()
        setUser(prev => prev ? { ...prev, credits: data.credits, is_unlimited: data.is_unlimited } : null)
      }
    } catch {
      // Ignore — non-critical
    }
  }, [token])

  const updateCredits = useCallback((credits: number) => {
    setUser(prev => prev ? { ...prev, credits } : null)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoggedIn: !!user,
        isLoading,
        login,
        logout,
        refreshCredits,
        updateCredits,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
