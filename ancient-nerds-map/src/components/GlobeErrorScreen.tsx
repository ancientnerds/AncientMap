import { FallbackLink, GLOBE_ICON, GlobeFallbackScreen } from './globeFallbackLinks'

/**
 * The globe failed (GlobeErrorBoundary, or a start step App watches itself):
 * which step, what went wrong, a reload, and the pages that work without the
 * globe. The reload takes the place the gate gives its "3D Globe" button.
 */
export default function GlobeErrorScreen({ phase, message }: { phase: string; message: string }) {
  return (
    <GlobeFallbackScreen
      message="The 3D globe could not start"
      hint={`Something went wrong while loading (${phase}): ${message}`}
    >
      <div className="mobile-actions-row">
        <FallbackLink page="stories" />
        <FallbackLink page="radar" />
      </div>
      <div className="mobile-actions-row">
        <FallbackLink page="journal" />
        <FallbackLink page="lyra" />
      </div>
      <div className="mobile-actions-row">
        <FallbackLink page="db" />
        <button className="mobile-action-btn mobile-action-globe" onClick={() => window.location.reload()}>
          {GLOBE_ICON}
          Reload the globe
        </button>
      </div>
    </GlobeFallbackScreen>
  )
}
