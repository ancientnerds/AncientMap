/**
 * The sign-in gate of the Lyra chat and the token store: the gate has to open
 * when the post-OAuth cookie is promoted in this tab (the /lyra.html login bug)
 * and when another tab signs in. Both listeners live in LyraChatModal and
 * nothing else imports the component — this test is what keeps them there.
 *
 * @vitest-environment jsdom
 */

import { StrictMode, act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LyraChatModal from './LyraChatModal'
import { _resetAuthTokenForTests, storeAuthToken } from '../contexts/authToken'

// React only flushes effects inside act() when this flag is set.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const KEY = 'an_auth_token'

let root: Root | null = null
let fetchMock: ReturnType<typeof vi.fn>

function gate(): Element | null {
  return document.body.querySelector('.lyra-auth-gate')
}

function chatBody(): Element | null {
  return document.body.querySelector('.lyra-chat-body')
}

/** A real Response, so the code under test sees status, ok and json(). */
function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

async function renderModal(): Promise<void> {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(
      <StrictMode>
        <LyraChatModal isOpen onClose={() => {}} />
      </StrictMode>,
    )
  })
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  // jsdom has no layout, so the auto-scroll of the message list has no
  // implementation to call.
  Element.prototype.scrollIntoView = vi.fn()
  fetchMock = vi.fn().mockResolvedValue(response({ credits: 5, is_unlimited: false }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount()
    })
  }
  root = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  _resetAuthTokenForTests()
})

describe('LyraChatModal sign-in gate', () => {
  it('shows the gate while no token is stored', async () => {
    await renderModal()

    expect(gate()).not.toBeNull()
    expect(chatBody()).toBeNull()
  })

  it('opens when the OAuth cookie is promoted in this tab', async () => {
    await renderModal()
    expect(gate()).not.toBeNull()

    // AuthProvider's mount effect, announcing the promoted token.
    await act(async () => {
      storeAuthToken('jwt-from-oauth-cookie')
    })

    expect(gate()).toBeNull()
    expect(chatBody()).not.toBeNull()
  })

  it('opens when another tab signs in (storage event)', async () => {
    await renderModal()
    expect(gate()).not.toBeNull()

    localStorage.setItem(KEY, 'jwt-from-other-tab')
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', { key: KEY }))
    })

    expect(gate()).toBeNull()
    expect(chatBody()).not.toBeNull()
  })

  it('keeps the token when the credits request answers 503', async () => {
    localStorage.setItem(KEY, 'jwt')
    fetchMock.mockResolvedValue(response({ detail: 'Service Unavailable' }, 503))

    await renderModal()
    await act(async () => {
      await Promise.resolve()
    })

    expect(localStorage.getItem(KEY)).toBe('jwt')
    expect(gate()).toBeNull()
  })

  it('drops the token when the credits request answers 401', async () => {
    localStorage.setItem(KEY, 'jwt-dead')
    fetchMock.mockResolvedValue(response({ detail: 'Unauthorized' }, 401))

    await renderModal()

    await vi.waitFor(() => expect(localStorage.getItem(KEY)).toBeNull())
    expect(gate()).not.toBeNull()
  })
})
