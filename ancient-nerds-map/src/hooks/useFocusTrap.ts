import { useEffect, useRef } from 'react'

/**
 * Traps Tab/Shift+Tab focus within a container.
 * Saves and restores focus when the trap activates/deactivates.
 * Only active when `enabled` is true.
 */
export function useFocusTrap(enabled: boolean) {
  const ref = useRef<HTMLDivElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!enabled) return
    const container = ref.current
    if (!container) return

    // Save the element that had focus before the trap activated
    previousFocus.current = document.activeElement as HTMLElement | null

    // Move focus into the container
    const focusable = container.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    if (focusable.length > 0) focusable[0].focus()

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const current = container.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
      if (current.length === 0) return
      const first = current[0]
      const last = current[current.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    container.addEventListener('keydown', onKeyDown)
    return () => {
      container.removeEventListener('keydown', onKeyDown)
      // Restore focus to the element that was focused before the trap
      previousFocus.current?.focus()
    }
  }, [enabled])

  return ref
}
