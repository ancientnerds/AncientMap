import { useState, useEffect } from 'react'
import { ANIMATION } from '../config/globeConstants'

/**
 * Debounce a value - returns the value only after it stops changing
 * Useful for search inputs, sliders, etc.
 *
 * @param value - The value to debounce
 * @param delay - Delay in ms (default: 150ms)
 * @returns The debounced value
 */
export function useDebounce<T>(value: T, delay: number = ANIMATION.DEBOUNCE_DELAY): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}
