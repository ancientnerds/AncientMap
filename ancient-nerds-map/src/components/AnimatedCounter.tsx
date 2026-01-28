import { memo } from 'react'

interface AnimatedCounterProps {
  value: number
  isLoading?: boolean
  className?: string
}

/**
 * Simple animated counter - uses CSS for all animations (GPU accelerated).
 * Shows loading dots and pulse while loading.
 */
function AnimatedCounterComponent({ value, isLoading = false, className = '' }: AnimatedCounterProps) {
  return (
    <span className={`animated-counter ${isLoading ? 'loading' : ''} ${className}`}>
      {value.toLocaleString()}
      {isLoading && <span className="loading-dots"><span>.</span><span>.</span><span>.</span></span>}
    </span>
  )
}

export const AnimatedCounter = memo(AnimatedCounterComponent)
