import { config } from '../config'

export function authHeaders(token: string | null): HeadersInit {
  const h: HeadersInit = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

export async function apiFetch<T>(path: string, token: string | null, init?: RequestInit): Promise<T> {
  const res = await fetch(`${config.api.baseUrl}${path}`, {
    ...init,
    headers: { ...authHeaders(token), ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

/**
 * Fire-and-forget achievement event reporting for frontend-triggered actions.
 * Silently ignores errors — should never block UI.
 * If token is not provided, reads from localStorage.
 */
export function reportAchievementEvent(
  eventType: string,
  token?: string | null,
  extra?: { layer_count?: number },
): void {
  const t = token ?? localStorage.getItem('an_auth_token')
  if (!t) return
  const body: Record<string, unknown> = { event_type: eventType }
  if (extra?.layer_count !== undefined) body.layer_count = extra.layer_count
  fetch(`${config.api.baseUrl}/api/cards/achievements/event`, {
    method: 'POST',
    headers: authHeaders(t),
    body: JSON.stringify(body),
  }).catch(() => {})
}
