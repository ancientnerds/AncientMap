/**
 * AuthContext — Discord OAuth authentication state.
 *
 * Stores JWT in localStorage. On mount, validates token via /api/auth/me.
 * Provides user profile, credits, and login/logout actions.
 *
 * The stored token itself lives in ./authToken: that module also announces
 * every change in this tab, which is how a mounted LyraChatModal notices the
 * post-OAuth cookie being promoted (see the comment there).
 */

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { config } from '../config'
import { getAuthToken, storeAuthToken } from './authToken'
import { reportLyraLoginSuccess } from '../analytics/loginFunnel'

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

const COOKIE_NAME = 'an_auth_token'

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  if (!match) return null
  try {
    return decodeURIComponent(match[1])
  } catch {
    // A value with a broken percent escape (`an_auth_token=%`): not a token we
    // can use, and an exception here would take the React root down — treated
    // like no cookie at all.
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  // One initial state in EVERY environment — renderToString, hydrateRoot and
  // plain createRoot all start "unknown, checking": no token, no user,
  // isLoading true. Reading localStorage/document.cookie in the useState
  // initializers made the hydrating client's first render disagree with the
  // server markup (react-ssr Task 15); the real token read lives in the
  // mount effect below. isLoading starts true (not false) so an auth-gated
  // page (AccountPage) shows its checking state first instead of flashing
  // "signed out" for one effect tick.
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const clearAuth = useCallback(() => {
    storeAuthToken(null)
    setToken(null)
    setUser(null)
    setIsLoading(false)
  }, [])

  const validateToken = useCallback(async (jwt: string): Promise<boolean> => {
    try {
      const resp = await fetch(`${config.api.baseUrl}/auth/me`, {
        headers: { 'Authorization': `Bearer ${jwt}` },
      })
      if (resp.status === 401 || resp.status === 403) {
        // The server judged the token: it is dead or revoked, drop it.
        clearAuth()
        return false
      }
      if (!resp.ok) {
        // No verdict. A deploy answers 503 for ~110 s, a missing key does too,
        // and an offline moment looks the same — none of that expires a login.
        // Keep the token, end the check, leave the state unconfirmed: the next
        // mount validates again. Deleting here would sign every visitor out on
        // every deploy, and deleting revoked nothing — the JWT stays valid on
        // the server, which is where authorization lives anyway.
        return false
      }
      const data: AuthUser = await resp.json()
      setUser(data)
      return true
    } catch {
      // Network error — the same "no verdict" as a 5xx.
      return false
    } finally {
      setIsLoading(false)
    }
  }, [clearAuth])

  // On mount: read the stored token and validate it. The OAuth callback sets
  // a short-lived (120s) cookie that the frontend promotes into localStorage.
  // We used to clear the cookie immediately after reading it, but in
  // multi-tab setups that races: whichever tab mounted first stole the token
  // and the others saw nothing. Now we let the cookie expire on its own —
  // every tab gets to read it during the ~2 minute window, and they all end
  // up with the same JWT in localStorage. (StrictMode runs this twice in
  // dev: the promotion and the /auth/me validation are both idempotent.)
  useEffect(() => {
    const cookieToken = readCookie(COOKIE_NAME)
    if (cookieToken) {
      // Store it and announce it in this tab: a Lyra sign-in gate that is
      // already mounted opens on the announcement (contexts/authToken.ts).
      storeAuthToken(cookieToken)
    }
    const stored = cookieToken ?? getAuthToken()
    if (stored) {
      setToken(stored)
      // The Lyra login funnel (analytics/loginFunnel.ts) counts a success only
      // when the server confirmed the token: /auth/me returning the user is
      // that confirmation, a 401 or a failed request is not.
      validateToken(stored).then(confirmed => {
        // …and only for the token that just came out of the handoff cookie,
        // i.e. the return leg of an OAuth round trip. A token that was already
        // in storage is an ordinary page load: it must not consume a marker a
        // failed attempt left behind and count a foreign login as a Lyra one.
        if (cookieToken) reportLyraLoginSuccess(confirmed)
      })
    } else {
      setIsLoading(false)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback((newToken: string) => {
    storeAuthToken(newToken)
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
