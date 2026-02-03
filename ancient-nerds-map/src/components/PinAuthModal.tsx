import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { config } from '../config'

// Extend Window interface for Turnstile
declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: {
        sitekey: string
        callback: (token: string) => void
        'error-callback'?: () => void
        'expired-callback'?: () => void
      }) => string
      reset: (widgetId: string) => void
      remove: (widgetId: string) => void
    }
  }
}

// Discord invite link
const DISCORD_URL = 'https://discord.gg/8bAjKKCue4'

interface PinAuthModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: (sessionToken: string) => void
  variant?: 'lyra' | 'admin' | 'refresh'
}

export default function PinAuthModal({ isOpen, onClose, onSuccess, variant = 'lyra' }: PinAuthModalProps) {
  const [pin, setPin] = useState(['', '', '', ''])
  const isAdminMode = variant === 'admin'
  const isRefreshMode = variant === 'refresh'
  const [error, setError] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)
  const [isLocked, setIsLocked] = useState(false)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  // Turnstile state
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null)
  const turnstileRef = useRef<HTMLDivElement>(null)
  const turnstileWidgetId = useRef<string | null>(null)
  const turnstileInitialized = useRef(false)

  // Focus first input when modal opens
  useEffect(() => {
    if (isOpen) {
      setPin(['', '', '', ''])
      setError('')
      setIsLocked(false)
      setTurnstileToken(null)
      setTimeout(() => {
        inputRefs.current[0]?.focus()
      }, 100)
    }
  }, [isOpen])

  // Initialize Turnstile widget when modal opens
  useEffect(() => {
    if (!isOpen) {
      // Cleanup when modal closes
      if (turnstileWidgetId.current && window.turnstile) {
        try {
          window.turnstile.remove(turnstileWidgetId.current)
        } catch {
          // Ignore
        }
        turnstileWidgetId.current = null
        turnstileInitialized.current = false
      }
      return
    }

    const initTurnstile = () => {
      if (!turnstileRef.current || !window.turnstile || turnstileWidgetId.current) return

      turnstileInitialized.current = true
      turnstileWidgetId.current = window.turnstile.render(turnstileRef.current, {
        sitekey: config.turnstile.siteKey,
        callback: (token: string) => setTurnstileToken(token),
        'error-callback': () => setTurnstileToken(null),
        'expired-callback': () => setTurnstileToken(null),
      })
    }

    // Load Turnstile script if not already loaded
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
      // Script is loading, wait for it
      const checkInterval = setInterval(() => {
        if (window.turnstile) {
          clearInterval(checkInterval)
          initTurnstile()
        }
      }, 100)
      setTimeout(() => clearInterval(checkInterval), 10000)
    }

    return () => {
      if (turnstileWidgetId.current && window.turnstile) {
        try {
          window.turnstile.remove(turnstileWidgetId.current)
        } catch {
          // Ignore removal errors
        }
        turnstileWidgetId.current = null
        turnstileInitialized.current = false
      }
    }
  }, [isOpen])

  // Handle keyboard navigation
  const handleKeyDown = useCallback((index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !pin[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    } else if (e.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1]?.focus()
    } else if (e.key === 'ArrowRight' && index < 3) {
      inputRefs.current[index + 1]?.focus()
    } else if (e.key === 'Escape') {
      onClose()
    }
  }, [pin, onClose])

  const handleDigitChange = useCallback((index: number, value: string) => {
    if (!/^\d?$/.test(value)) return

    const newPin = [...pin]
    newPin[index] = value
    setPin(newPin)
    setError('')

    if (value && index < 3) {
      inputRefs.current[index + 1]?.focus()
    }

    if (value && index === 3 && newPin.every(d => d)) {
      handleSubmit(newPin.join(''))
    }
  }, [pin])

  const handleSubmit = useCallback(async (pinCode: string) => {
    if (isVerifying || isLocked) return

    // Check if Turnstile token is available
    if (!turnstileToken) {
      setError('Please complete the verification first')
      return
    }

    setIsVerifying(true)
    setError('')

    try {
      // Use different endpoint for refresh mode
      const endpoint = isRefreshMode
        ? `${config.api.baseUrl}/content/connectors/verify-refresh`
        : `${config.api.baseUrl}/ai/verify`

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pin: pinCode,
          turnstile_token: turnstileToken
        })
      })

      const data = await response.json()

      if (data.verified) {
        // Successfully verified
        onSuccess(isRefreshMode ? 'refresh_authorized' : data.session_token)
      } else {
        // Handle different error types
        if (data.error === 'ip_locked') {
          setError(data.message || 'Too many failed attempts. Please try again later.')
          setIsLocked(true)
          setPin(['', '', '', ''])
        } else if (data.error === 'rate_limited') {
          setError(data.message || 'Please wait before refreshing again.')
          setPin(['', '', '', ''])
          inputRefs.current[0]?.focus()
        } else if (data.error === 'captcha_failed') {
          setError(data.message || 'Verification failed. Please refresh and try again.')
          // Reset Turnstile widget
          if (turnstileWidgetId.current && window.turnstile) {
            window.turnstile.reset(turnstileWidgetId.current)
          }
          setTurnstileToken(null)
          setPin(['', '', '', ''])
        } else if (data.error === 'pin_in_use') {
          setError(data.message || 'This PIN is already in use')
          setPin(['', '', '', ''])
          inputRefs.current[0]?.focus()
        } else {
          // Invalid PIN - show message with attempts remaining
          setError(data.message || 'Invalid PIN')
          setPin(['', '', '', ''])
          inputRefs.current[0]?.focus()
        }
      }
    } catch (err) {
      setError('Connection error. Please try again.')
      setPin(['', '', '', ''])
      inputRefs.current[0]?.focus()
    } finally {
      setIsVerifying(false)
    }
  }, [isVerifying, isLocked, turnstileToken, onSuccess, isRefreshMode])

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 4)
    if (pasted.length === 4) {
      const newPin = pasted.split('')
      setPin(newPin)
      handleSubmit(pasted)
    }
  }, [handleSubmit])

  if (!isOpen) return null

  return createPortal(
    <div className="pin-modal-overlay" onClick={onClose}>
      <div className="pin-modal pin-modal-enhanced" onClick={e => e.stopPropagation()}>
        <button className="popup-close" onClick={onClose} title="Close">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <div className="pin-modal-content">
          {isRefreshMode ? (
            /* Refresh mode header */
            <div className="pin-header admin">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="pin-admin-icon">
                <path d="M23 4v6h-6" />
                <path d="M1 20v-6h6" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
              <h2>Refresh Connectors</h2>
              <p className="pin-admin-subtitle">Enter admin PIN to refresh all 47 connectors</p>
              <p className="pin-refresh-warning">This pings external APIs - use sparingly</p>
            </div>
          ) : isAdminMode ? (
            /* Admin mode header */
            <div className="pin-header admin">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="pin-admin-icon">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              <h2>Admin Access</h2>
              <p className="pin-admin-subtitle">Enter PIN to edit site data</p>
            </div>
          ) : (
            <>
              {/* Header with Lyra branding */}
              <div className="pin-header">
                <img src="/lyra.png" alt="Lyra" className="pin-lyra-icon" />
                <h2>Lyra AI Assistant</h2>
                <span className="pin-experimental-badge">Experimental Feature</span>
              </div>

              {/* Fair use explanation */}
              <div className="pin-fair-use">
                <p className="pin-tagline">Free for the community</p>
                <p className="pin-welcome">Ask Lyra anything about archaeological sites, ancient history, or explore the map together!</p>
                <ul className="pin-rules">
                  <li>Get your personal PIN from our Discord</li>
                  <li>Multiple users welcome - questions are queued</li>
                  <li>Running on limited resources - please be patient</li>
                </ul>
              </div>
            </>
          )}

          {/* Turnstile verification */}
          <div className="pin-turnstile-section">
            <div className="turnstile-container">
              <div ref={turnstileRef}></div>
            </div>
            {turnstileToken && (
              <div className="turnstile-verified">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                Verified
              </div>
            )}
          </div>

          {/* PIN input section */}
          <div className={`pin-input-section ${isLocked ? 'locked' : ''}`}>
            <label>Enter PIN to access</label>
            <div className="pin-inputs" onPaste={handlePaste}>
              {pin.map((digit, i) => (
                <input
                  key={i}
                  ref={el => inputRefs.current[i] = el}
                  type="password"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={e => handleDigitChange(i, e.target.value)}
                  onKeyDown={e => handleKeyDown(i, e)}
                  className={`pin-digit ${error ? 'error' : ''} ${isLocked ? 'locked' : ''}`}
                  disabled={isVerifying || isLocked || !turnstileToken}
                  autoComplete="off"
                />
              ))}
            </div>

            {error && (
              <div className={`pin-error ${isLocked ? 'locked' : ''}`}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  {isLocked ? (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                      <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                    </>
                  ) : (
                    <>
                      <circle cx="12" cy="12" r="10"/>
                      <line x1="12" y1="8" x2="12" y2="12"/>
                      <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </>
                  )}
                </svg>
                {error}
              </div>
            )}

            {isVerifying && (
              <div className="pin-verifying">
                <div className="pin-spinner"></div>
                Verifying...
              </div>
            )}
          </div>

          {/* Discord CTA - only for Lyra mode */}
          {!isAdminMode && !isRefreshMode && (
            <div className="pin-discord">
              <p>Need access? Talk to the founders</p>
              <a
                href={DISCORD_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="pin-discord-btn"
              >
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                  <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
                </svg>
                Join Discord
              </a>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
