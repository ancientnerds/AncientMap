import { useAuth } from '../contexts/AuthContext'

/**
 * True when the logged-in user has the founder role.
 * Thin wrapper over AuthContext — the provider already validates the token
 * via /api/auth/me on mount, so no extra fetch is needed here.
 */
export function useIsFounder(): boolean {
  const { user } = useAuth()
  return !!user?.is_founder
}
