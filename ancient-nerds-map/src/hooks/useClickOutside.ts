import { useEffect, useRef, RefObject } from 'react'

/**
 * Detect clicks outside of a referenced element
 * Useful for closing dropdowns, modals, and popups
 *
 * @param callback - Function to call when click is detected outside
 * @param enabled - Whether to listen for clicks (default: true)
 * @returns Ref to attach to the element to monitor
 */
export function useClickOutside<T extends HTMLElement = HTMLElement>(
  callback: (event: MouseEvent | TouchEvent) => void,
  enabled: boolean = true
): RefObject<T> {
  const ref = useRef<T>(null)
  const callbackRef = useRef(callback)

  // Keep callback ref updated
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  useEffect(() => {
    if (!enabled) return

    const handleClick = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node
      if (ref.current && !ref.current.contains(target)) {
        callbackRef.current(event)
      }
    }

    // Use capture phase to catch events before they bubble
    document.addEventListener('mousedown', handleClick, true)
    document.addEventListener('touchstart', handleClick, true)

    return () => {
      document.removeEventListener('mousedown', handleClick, true)
      document.removeEventListener('touchstart', handleClick, true)
    }
  }, [enabled])

  return ref
}
