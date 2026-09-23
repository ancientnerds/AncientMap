import type { GateChoice } from '../analytics/globeAbandon'
import { FallbackLink, GLOBE_ICON, GlobeFallbackScreen } from './globeFallbackLinks'

/**
 * The phone gate of /globe.html (text and layout unchanged since before the
 * globe-load work): phones and small screens see it before the globe, with
 * links to the mobile-friendly pages and a button that continues to the globe.
 * Every control reports its choice (App tracks it as globe_gate).
 */
export default function PhoneGate({ onChoice }: { onChoice: (choice: GateChoice) => void }) {
  return (
    <GlobeFallbackScreen
      message="The 3D globe is optimized for desktop browsers."
      hint="Explore our mobile-friendly pages below, or continue to the globe."
    >
      <div className="mobile-actions-row">
        <FallbackLink page="stories" onClick={() => onChoice('stories')} />
        <FallbackLink page="radar" onClick={() => onChoice('radar')} />
      </div>
      <div className="mobile-actions-row">
        <FallbackLink page="journal" onClick={() => onChoice('journal')} />
        <FallbackLink page="lyra" onClick={() => onChoice('lyra')} />
      </div>
      <div className="mobile-actions-row">
        <FallbackLink page="db" onClick={() => onChoice('db')} />
        <button
          className="mobile-action-btn mobile-action-globe"
          onClick={() => onChoice('globe')}
        >
          {GLOBE_ICON}
          3D Globe
        </button>
      </div>
    </GlobeFallbackScreen>
  )
}
