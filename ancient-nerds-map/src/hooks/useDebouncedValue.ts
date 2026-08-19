import { useEffect, useState } from 'react'

/**
 * Debounced copy of `value` — updates only after `delayMs` without further
 * changes.
 *
 * Built for the significance slider on the Stories page: a range input fires
 * onChange per notch, so dragging from 0 to 9 would otherwise trigger nine
 * feed requests and flicker the grid. The raw value drives the slider (no
 * input lag), the debounced one drives the fetch.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(handle)
  }, [value, delayMs])

  return debounced
}
