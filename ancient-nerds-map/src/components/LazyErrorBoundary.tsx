import React from 'react'
import { track } from '../analytics'

/**
 * Catches a lazy chunk that fails to load (flaky network, a deploy swapped
 * the chunk) so it shows a notice instead of unmounting the whole app:
 * React.lazy throws during render and nothing above catches it otherwise.
 * Wrap every React.lazy as <LazyErrorBoundary><Suspense …>.
 */
export default class LazyErrorBoundary extends React.Component<
  { children: React.ReactNode; resetKey?: string | number | boolean },
  { hasError: boolean }
> {
  state = { hasError: false }
  static getDerivedStateFromError() { return { hasError: true } }
  componentDidCatch(error: Error) {
    track('js_error', { message: String(error?.message ?? error).slice(0, 120), source: 'boundary', page: 'globe' })
  }
  componentDidUpdate(prevProps: { resetKey?: string | number | boolean }) {
    // Reset error state when resetKey changes (e.g. modal reopened)
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false })
    }
  }
  render() {
    if (this.state.hasError) {
      return <div style={{ padding: '1rem', textAlign: 'center', opacity: 0.6 }}>
        Failed to load. Please refresh the page.
      </div>
    }
    return this.props.children
  }
}
