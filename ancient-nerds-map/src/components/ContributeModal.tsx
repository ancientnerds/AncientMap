import { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { config } from '../config'
import { OfflineStorage } from '../services/OfflineStorage'
import SiteForm from './SiteForm'
import type { SiteFormValues } from './SiteForm'

interface ContributeModalProps {
  isOpen: boolean
  onClose: () => void
  onEnableMapPicker: () => void
  isMapPickerActive: boolean
  hoverCoords: [number, number] | null  // [lng, lat] - live coords from hover
  onClearCoords: () => void
  wasMapPickerCancelled: boolean  // True if picker was cancelled (not confirmed)
}

type SubmitStatus = 'idle' | 'submitting' | 'success' | 'queued' | 'error'

// Turnstile types declared in PinAuthModal.tsx (shared)


export default function ContributeModal({
  isOpen,
  onClose,
  onEnableMapPicker,
  isMapPickerActive,
  hoverCoords,
  onClearCoords,
  wasMapPickerCancelled,
}: ContributeModalProps) {
  const [formValues, setFormValues] = useState<SiteFormValues | null>(null)
  const [formResetKey, setFormResetKey] = useState(0)

  const [submitStatus, setSubmitStatus] = useState<SubmitStatus>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null)
  const [showSavedIndicator, setShowSavedIndicator] = useState(false)

  const turnstileRef = useRef<HTMLDivElement>(null)
  const turnstileWidgetId = useRef<string | null>(null)
  const turnstileInitialized = useRef(false)
  const coordsBeforePickerRef = useRef<string>('')
  const validCoordsBeforePickerRef = useRef<[number, number] | null>(null)
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [hasBeenOpened, setHasBeenOpened] = useState(false)
  const [turnstileKey, setTurnstileKey] = useState(0)
  const wasOpenRef = useRef(false)

  // Track if modal has ever been opened & reset form after successful submission
  useEffect(() => {
    const justOpened = isOpen && !wasOpenRef.current
    wasOpenRef.current = isOpen

    if (isOpen && !hasBeenOpened) {
      setHasBeenOpened(true)
    }
    if (justOpened && submitStatus === 'success') {
      setSubmitStatus('idle')
      setFormResetKey(k => k + 1)
      setTurnstileToken(null)
      turnstileInitialized.current = false
      turnstileWidgetId.current = null
      setTurnstileKey(k => k + 1)
    }
  }, [isOpen, hasBeenOpened, submitStatus])

  // Initialize Turnstile widget - runs when modal is first opened
  useEffect(() => {
    if (!hasBeenOpened || turnstileInitialized.current) return

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

    let pollId: ReturnType<typeof setInterval> | null = null
    let timeoutId: ReturnType<typeof setTimeout> | null = null

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
      pollId = setInterval(() => {
        if (window.turnstile) {
          clearInterval(pollId!)
          pollId = null
          initTurnstile()
        }
      }, 100)
      timeoutId = setTimeout(() => { if (pollId) { clearInterval(pollId); pollId = null } }, 10000)
    }

    return () => {
      if (pollId) clearInterval(pollId)
      if (timeoutId) clearTimeout(timeoutId)
      if (turnstileWidgetId.current && window.turnstile) {
        try {
          window.turnstile.remove(turnstileWidgetId.current)
        } catch {
          // Ignore
        }
        turnstileWidgetId.current = null
        turnstileInitialized.current = false
      }
    }
  }, [hasBeenOpened, turnstileKey])

  // Save coordinates when entering map picker mode (only on transition to active)
  const wasPickerActive = useRef(false)
  useEffect(() => {
    if (isMapPickerActive && !wasPickerActive.current) {
      coordsBeforePickerRef.current = formValues?.coordinates || ''
      validCoordsBeforePickerRef.current = formValues?.validCoords || null
    } else if (!isMapPickerActive && wasPickerActive.current) {
      if (wasMapPickerCancelled) {
        // Restore by bumping the key with initial values restored — but we can't easily
        // reset just coords. Instead, the SiteForm externalCoords=null will leave coords alone.
        // For a full restore, we need to re-create the form. Since the picker cancel is rare
        // and the form values are controlled by SiteForm internally, we accept this limitation.
        // The externalCoords going null stops overwriting.
      }
    }
    wasPickerActive.current = isMapPickerActive
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMapPickerActive, wasMapPickerCancelled])

  // Show "Saved" indicator after typing stops
  useEffect(() => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current)

    const hasContent = formValues && (formValues.name || formValues.description || formValues.country || formValues.coordinates || formValues.category || formValues.sourceUrl)
    if (hasContent && submitStatus === 'idle') {
      saveTimeoutRef.current = setTimeout(() => {
        setShowSavedIndicator(true)
        setTimeout(() => setShowSavedIndicator(false), 2000)
      }, 500)
    }

    return () => { if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current) }
  }, [formValues, submitStatus])

  const handleResetForm = useCallback(() => {
    setFormResetKey(k => k + 1)
    onClearCoords()
  }, [onClearCoords])

  const handleContributeAnother = useCallback(() => {
    setSubmitStatus('idle')
    setFormResetKey(k => k + 1)
    setTurnstileToken(null)
    setErrorMessage('')
    turnstileInitialized.current = false
    turnstileWidgetId.current = null
    setTurnstileKey(k => k + 1)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formValues?.name.trim()) {
      setErrorMessage('Site name is required')
      return
    }

    const validCoords = formValues.validCoords

    // Check if offline - queue contribution for later sync
    if (!navigator.onLine) {
      setSubmitStatus('submitting')
      setErrorMessage('')

      try {
        await OfflineStorage.queueContribution({
          formData: {
            name: formValues.name.trim(),
            country: formValues.country.trim() || '',
            lat: validCoords ? validCoords[1] : null,
            lon: validCoords ? validCoords[0] : null,
            siteType: formValues.category || '',
            description: formValues.description.trim() || '',
            sourceUrl: formValues.sourceUrl.trim() || '',
          }
        })
        setSubmitStatus('queued')
      } catch {
        setSubmitStatus('error')
        setErrorMessage('Failed to save contribution for later. Please try again.')
      }
      return
    }

    // Online - require Turnstile verification
    if (!turnstileToken) {
      setErrorMessage('Please complete the verification')
      return
    }

    setSubmitStatus('submitting')
    setErrorMessage('')

    try {
      const response = await fetch(`${config.api.baseUrl}/contributions/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formValues.name.trim(),
          lat: validCoords ? validCoords[1] : null,
          lon: validCoords ? validCoords[0] : null,
          description: formValues.description.trim() || null,
          country: formValues.country.trim() || null,
          site_type: formValues.category || null,
          source_url: formValues.sourceUrl.trim() || null,
          turnstile_token: turnstileToken,
        }),
      })

      const data = await response.json()

      if (response.ok && data.success) {
        setSubmitStatus('success')
      } else {
        setSubmitStatus('error')
        setErrorMessage(data.detail || 'Submission failed. Please try again.')
        if (turnstileWidgetId.current && window.turnstile) {
          window.turnstile.reset(turnstileWidgetId.current)
          setTurnstileToken(null)
        }
      }
    } catch {
      setSubmitStatus('error')
      setErrorMessage('Network error. Please check your connection.')
      if (turnstileWidgetId.current && window.turnstile) {
        window.turnstile.reset(turnstileWidgetId.current)
        setTurnstileToken(null)
      }
    }
  }

  const handleOverlayClick = (e: React.MouseEvent) => {
    e.stopPropagation()
  }

  // Don't render until first opened (lazy load Turnstile)
  if (!hasBeenOpened) {
    return null
  }

  // Hide when closed or in map picker mode
  const isHidden = !isOpen || isMapPickerActive

  const modalContent = (
    <div className={`contribute-modal-overlay ${isHidden ? 'hidden' : ''}`} onClick={handleOverlayClick}>
      <div className="contribute-modal">
        <button className="popup-close" onClick={onClose} title="Close - Your input is saved until you leave the site">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        {submitStatus === 'success' ? (
          <div className="contribute-success">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
            <h3>Thank you!</h3>
            <p>Your contribution has been submitted for review.</p>

            <div className="success-socials">
              <p className="socials-invite">Join <span className="brand-name">ANCIENT NERDS</span> - Modern Tech for Ancient Mysteries</p>
              <div className="socials-links">
                <a href="https://discord.gg/8bAjKKCue4" target="_blank" rel="noopener noreferrer" title="Discord">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
                  </svg>
                </a>
                <a href="https://x.com/AncientNerdsDAO" target="_blank" rel="noopener noreferrer" title="X (Twitter)">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                  </svg>
                </a>
                <a href="https://www.youtube.com/@ancientnerds" target="_blank" rel="noopener noreferrer" title="YouTube">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                  </svg>
                </a>
              </div>
            </div>

            <div className="success-buttons">
              <button className="contribute-another-btn" onClick={handleContributeAnother}>Contribute Another</button>
              <button className="contribute-done-btn" onClick={onClose}>Done</button>
            </div>
          </div>
        ) : submitStatus === 'queued' ? (
          <div className="contribute-success contribute-queued">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#00b4b4" strokeWidth="2">
              <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/>
            </svg>
            <h3>Saved for Later</h3>
            <p>Your contribution has been saved and will be submitted automatically when you're back online.</p>
            <p className="queued-hint">You can continue adding more sites while offline.</p>

            <div className="success-buttons">
              <button className="contribute-another-btn" onClick={handleContributeAnother}>Contribute Another</button>
              <button className="contribute-done-btn" onClick={onClose}>Done</button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="contribute-form" autoComplete="off">
            <div className="contribute-header">
              {showSavedIndicator && <span className="form-saved-indicator">Saved</span>}
              <h2>Contribute a Site</h2>
              <button type="button" className="form-reset-btn" onClick={handleResetForm} title="Reset form">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
              </button>
            </div>

            <SiteForm
              key={formResetKey}
              onChange={setFormValues}
              showMapPicker={true}
              onEnableMapPicker={onEnableMapPicker}
              showPeriod={false}
              externalCoords={isMapPickerActive ? hoverCoords : null}
            />

            {/* Media Upload - placeholder for Google Drive integration */}
            <div className="form-group">
              <label>Media</label>
              <div className="media-upload-area">
                <button type="button" className="media-upload-btn" disabled>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                  Upload photos & videos
                </button>
                <span className="media-hint">Coming soon - Google Drive integration</span>
              </div>
            </div>

            {/* Turnstile Widget - Fixed height container */}
            <div className="turnstile-container">
              <div ref={turnstileRef}></div>
            </div>

            {/* Error Message */}
            {errorMessage && (
              <div className="contribute-error">{errorMessage}</div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              className="contribute-submit-btn"
              disabled={submitStatus === 'submitting' || (!navigator.onLine ? false : !turnstileToken)}
            >
              {submitStatus === 'submitting' ? (
                <>
                  <span className="submit-spinner"></span>
                  Submitting...
                </>
              ) : (
                'Submit Contribution'
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  )

  return createPortal(modalContent, document.body)
}
