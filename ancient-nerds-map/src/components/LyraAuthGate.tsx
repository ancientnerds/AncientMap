/**
 * LyraAuthGate — Admin auth gate rendered inside LyraChatModal.
 *
 * 4-digit PIN input (same UX as PinAuthModal) + Turnstile.
 * Auto-submits on the 4th digit. On success, calls onAuthenticated(pin).
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { config } from '../config'

interface Props {
  onAuthenticated: (key: string) => void
}

export default function LyraAuthGate({ onAuthenticated }: Props) {
  const [pin, setPin] = useState(['', '', '', ''])
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)

  const inputRefs = useRef<(HTMLInputElement | null)[]>([])
  const turnstileRef = useRef<HTMLDivElement>(null)
  const turnstileWidgetId = useRef<string | null>(null)

  // Initialize Turnstile widget
  useEffect(() => {
    const initTurnstile = () => {
      if (!turnstileRef.current || !window.turnstile || turnstileWidgetId.current) return

      turnstileWidgetId.current = window.turnstile.render(turnstileRef.current, {
        sitekey: config.turnstile.siteKey,
        callback: (token: string) => setTurnstileToken(token),
        'error-callback': () => setTurnstileToken(null),
        'expired-callback': () => setTurnstileToken(null),
        theme: 'dark',
        size: 'compact',
      })
    }

    if (!document.getElementById('turnstile-script')) {
      const script = document.createElement('script')
      script.id = 'turnstile-script'
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
      script.async = true
      script.onload = () => setTimeout(initTurnstile, 100)
      document.head.appendChild(script)
    } else if (window.turnstile) {
      setTimeout(initTurnstile, 100)
    } else {
      const checkInterval = setInterval(() => {
        if (window.turnstile) {
          clearInterval(checkInterval)
          initTurnstile()
        }
      }, 100)
      return () => clearInterval(checkInterval)
    }

    return () => {
      if (turnstileWidgetId.current && window.turnstile) {
        try { window.turnstile.remove(turnstileWidgetId.current) } catch { /* ignore */ }
        turnstileWidgetId.current = null
      }
    }
  }, [])

  // Focus first input after Turnstile verifies
  useEffect(() => {
    if (turnstileToken) {
      setTimeout(() => inputRefs.current[0]?.focus(), 100)
    }
  }, [turnstileToken])

  const handleSubmit = useCallback(async (pinCode: string) => {
    if (!turnstileToken || isVerifying) return

    setIsVerifying(true)
    setError('')

    try {
      const response = await fetch(`${config.api.baseUrl}/lyra/admin/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${pinCode}`,
        },
      })

      if (response.ok) {
        sessionStorage.setItem('lyra_admin_key', pinCode)
        onAuthenticated(pinCode)
      } else {
        const data = await response.json().catch(() => ({ detail: 'Invalid PIN' }))
        setError(data.detail || `Error ${response.status}`)
        setPin(['', '', '', ''])
        inputRefs.current[0]?.focus()
        // Reset Turnstile on auth failure
        if (turnstileWidgetId.current && window.turnstile) {
          window.turnstile.reset(turnstileWidgetId.current)
          setTurnstileToken(null)
        }
      }
    } catch {
      setError('Connection error. Please try again.')
      setPin(['', '', '', ''])
      inputRefs.current[0]?.focus()
    } finally {
      setIsVerifying(false)
    }
  }, [turnstileToken, isVerifying, onAuthenticated])

  const handleDigitChange = useCallback((index: number, value: string) => {
    if (!/^\d?$/.test(value)) return

    const newPin = [...pin]
    newPin[index] = value
    setPin(newPin)
    setError('')

    if (value && index < 3) {
      inputRefs.current[index + 1]?.focus()
    }

    // Auto-submit on 4th digit
    if (value && index === 3 && newPin.every(d => d)) {
      handleSubmit(newPin.join(''))
    }
  }, [pin, handleSubmit])

  const handleKeyDown = useCallback((index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !pin[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    } else if (e.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1]?.focus()
    } else if (e.key === 'ArrowRight' && index < 3) {
      inputRefs.current[index + 1]?.focus()
    }
  }, [pin])

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 4)
    if (pasted.length === 4) {
      setPin(pasted.split(''))
      handleSubmit(pasted)
    }
  }, [handleSubmit])

  return (
    <div className="lyra-auth-gate">
      <img src="/lyra.gif" alt="Lyra" className="lyra-auth-gate-avatar" />
      <div className="lyra-auth-gate-name">Lyra Wiskerbyte</div>
      <div className="lyra-auth-gate-subtitle">Admin Access</div>

      <div className="lyra-auth-gate-turnstile">
        <div ref={turnstileRef} />
      </div>

      <label className="lyra-auth-gate-label">Enter PIN to access</label>
      <div className="lyra-auth-gate-pins" onPaste={handlePaste}>
        {pin.map((digit, i) => (
          <input
            key={i}
            ref={el => { inputRefs.current[i] = el }}
            type="password"
            inputMode="numeric"
            maxLength={1}
            value={digit}
            onChange={e => handleDigitChange(i, e.target.value)}
            onKeyDown={e => handleKeyDown(i, e)}
            className={`lyra-auth-gate-digit ${error ? 'error' : ''}`}
            disabled={!turnstileToken || isVerifying}
            autoComplete="off"
          />
        ))}
      </div>

      {error && <div className="lyra-auth-gate-error">{error}</div>}

      {isVerifying && (
        <div className="lyra-auth-gate-verifying">
          <div className="pin-spinner" />
          Verifying...
        </div>
      )}
    </div>
  )
}
