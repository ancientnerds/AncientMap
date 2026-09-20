/**
 * The wiring around the Discord token that no unit test reaches: AuthProvider
 * promotes the post-OAuth handoff cookie into the token store, announces it to
 * the tree, and reports the Lyra login success — but only for that promotion,
 * never for a token that was already stored. lyraMain.tsx mounts exactly this
 * pair (AuthProvider, a consumer of useAuth), so the test renders the same
 * tree the page does; jsdom supplies document.cookie and the storages.
 *
 * @vitest-environment jsdom
 */

import { StrictMode, act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { _resetForTests } from '../../analytics'
import { setLoginPending } from '../../analytics/loginFunnel'
import { _resetAuthTokenForTests } from '../authToken'
import { AuthProvider, useAuth } from '../AuthContext'

// React only flushes effects inside act() when this flag is set.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const COOKIE = 'an_auth_token'
const MARKER = 'an_login_pending'

type Tracker = (name: string, data?: Record<string, string | number | boolean>) => unknown

const USER = {
  id: '1',
  discord_id: '42',
  username: 'nerd',
  avatar_url: null,
  roles: [],
  credits: 10,
  is_unlimited: false,
  is_og_nerd: false,
  is_founder: false,
  tier: 'free',
  next_grant_date: null,
  created_at: null,
}

/** A real Response, so the code under test sees status, ok and json(). */
function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

function Probe() {
  const { token, user, isLoggedIn, isLoading } = useAuth()
  return (
    <div
      data-testid="probe"
      data-token={token ?? ''}
      data-user={user?.username ?? ''}
      data-logged-in={String(isLoggedIn)}
      data-loading={String(isLoading)}
    />
  )
}

let container: HTMLDivElement | null = null
let root: Root | null = null
let fetchMock: ReturnType<typeof vi.fn>
let track: Mock<Tracker>

function probe(attribute: string): string | null {
  return container!.querySelector('[data-testid="probe"]')!.getAttribute(attribute)
}

async function renderAuthProvider(): Promise<void> {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(
      <StrictMode>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </StrictMode>,
    )
  })
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  for (const entry of document.cookie.split('; ')) {
    if (entry) document.cookie = `${entry.split('=')[0]}=; expires=${new Date(0).toUTCString()}; path=/`
  }
  track = vi.fn<Tracker>()
  window.umami = { track }
  fetchMock = vi.fn().mockResolvedValue(response(USER))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount()
    })
  }
  container?.remove()
  container = null
  root = null
  vi.unstubAllGlobals()
  delete window.umami
  _resetAuthTokenForTests()
  _resetForTests()
})

describe('AuthProvider promotes the OAuth handoff cookie', () => {
  it('shows the token to the tree and counts exactly one Lyra login success', async () => {
    setLoginPending('lyra')
    document.cookie = `${COOKIE}=jwt-from-oauth-cookie; path=/`

    await renderAuthProvider()

    expect(probe('data-token')).toBe('jwt-from-oauth-cookie')
    expect(localStorage.getItem(COOKIE)).toBe('jwt-from-oauth-cookie')
    expect(probe('data-user')).toBe('nerd')
    expect(probe('data-logged-in')).toBe('true')
    // StrictMode mounts the provider twice; the marker is single-use.
    expect(track).toHaveBeenCalledTimes(1)
    expect(track).toHaveBeenCalledWith('lyra_login_success', { src: 'lyra' })
  })

  it('does not count a token that was already stored: only the promotion is a login', async () => {
    setLoginPending('lyra')
    localStorage.setItem(COOKIE, 'jwt-from-storage')

    await renderAuthProvider()

    expect(probe('data-token')).toBe('jwt-from-storage')
    expect(probe('data-user')).toBe('nerd')
    expect(track).not.toHaveBeenCalled()
    // The marker survives for a return leg that may still arrive.
    expect(sessionStorage.getItem(MARKER)).not.toBeNull()
  })

  it('keeps the token when /auth/me answers 503 — no verdict, no logout', async () => {
    document.cookie = `${COOKIE}=jwt; path=/`
    fetchMock.mockResolvedValue(response({ detail: 'Service Unavailable' }, 503))

    await renderAuthProvider()

    expect(localStorage.getItem(COOKIE)).toBe('jwt')
    expect(probe('data-token')).toBe('jwt')
    // Unconfirmed: no user, not signed in, but the check has ended.
    expect(probe('data-user')).toBe('')
    expect(probe('data-logged-in')).toBe('false')
    expect(probe('data-loading')).toBe('false')
  })

  it('drops the token when the server answers 401', async () => {
    document.cookie = `${COOKIE}=jwt-dead; path=/`
    fetchMock.mockResolvedValue(response({ detail: 'Unauthorized' }, 401))

    await renderAuthProvider()

    expect(localStorage.getItem(COOKIE)).toBeNull()
    expect(probe('data-token')).toBe('')
    expect(probe('data-loading')).toBe('false')
  })

  it('treats a cookie with a broken percent escape as no cookie', async () => {
    document.cookie = `${COOKIE}=%; path=/`

    await renderAuthProvider()

    expect(probe('data-token')).toBe('')
    expect(probe('data-loading')).toBe('false')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
