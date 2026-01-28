import { useEffect, useRef } from 'react'

/**
 * Keyboard shortcut definition
 */
export interface KeyboardShortcut {
  /** Key to listen for (e.g., 'a', 'Enter', 'Escape', 'ArrowUp') */
  key: string
  /** Callback when shortcut is triggered */
  callback: (event: KeyboardEvent) => void
  /** Require Ctrl/Cmd key (default: false) */
  ctrl?: boolean
  /** Require Shift key (default: false) */
  shift?: boolean
  /** Require Alt/Option key (default: false) */
  alt?: boolean
  /** Require Meta/Windows key (default: false) */
  meta?: boolean
  /** Prevent default browser behavior (default: true) */
  preventDefault?: boolean
  /** Stop event propagation (default: false) */
  stopPropagation?: boolean
  /** Whether shortcut is enabled (default: true) */
  enabled?: boolean
  /** Description for accessibility/documentation */
  description?: string
}

/**
 * Check if an element is an input that should capture keyboard events
 */
function isInputElement(element: EventTarget | null): boolean {
  if (!element || !(element instanceof HTMLElement)) return false
  const tagName = element.tagName.toLowerCase()
  return (
    tagName === 'input' ||
    tagName === 'textarea' ||
    tagName === 'select' ||
    element.isContentEditable
  )
}

/**
 * Hook for managing keyboard shortcuts
 * Automatically handles cleanup and prevents conflicts with input elements
 *
 * @param shortcuts - Array of keyboard shortcut definitions
 * @param options - Global options for all shortcuts
 */
export function useKeyboardShortcuts(
  shortcuts: KeyboardShortcut[],
  options: {
    /** Ignore shortcuts when focus is in input elements (default: true) */
    ignoreInputs?: boolean
    /** Enable all shortcuts (default: true) */
    enabled?: boolean
  } = {}
): void {
  const { ignoreInputs = true, enabled = true } = options
  const shortcutsRef = useRef(shortcuts)

  // Keep shortcuts ref updated
  useEffect(() => {
    shortcutsRef.current = shortcuts
  }, [shortcuts])

  useEffect(() => {
    if (!enabled) return

    const handleKeyDown = (event: KeyboardEvent) => {
      // Skip if focus is in an input element
      if (ignoreInputs && isInputElement(event.target)) return

      for (const shortcut of shortcutsRef.current) {
        // Skip disabled shortcuts
        if (shortcut.enabled === false) continue

        // Check key match (case-insensitive for letters)
        const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase()
        if (!keyMatch) continue

        // Check modifier keys
        const ctrlMatch = !!shortcut.ctrl === (event.ctrlKey || event.metaKey)
        const shiftMatch = !!shortcut.shift === event.shiftKey
        const altMatch = !!shortcut.alt === event.altKey
        const metaMatch = !!shortcut.meta === event.metaKey

        if (ctrlMatch && shiftMatch && altMatch && metaMatch) {
          // Matched! Execute callback
          if (shortcut.preventDefault !== false) {
            event.preventDefault()
          }
          if (shortcut.stopPropagation) {
            event.stopPropagation()
          }
          shortcut.callback(event)
          return  // Stop after first match
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [enabled, ignoreInputs])
}
