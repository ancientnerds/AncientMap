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
  is_og_nerd: boolean
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [isLoading, setIsLoading] = useState(!!localStorage.getItem(TOKEN_KEY))

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
        setUser(prev => prev ? { ...prev, credits: data.credits } : null)
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
