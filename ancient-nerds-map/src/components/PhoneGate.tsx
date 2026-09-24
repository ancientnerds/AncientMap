import type { GateChoice } from '../analytics/globeAbandon'
import { FallbackLinkRows, GLOBE_ICON, GlobeFallbackScreen } from './globeFallbackLinks'

/**
 * The phone gate of /globe.html (text unchanged since before the
 * globe-load work): phones and small screens see it before the globe, with
 * links to the mobile-friendly pages and, on a row of its own, a button that
 * continues to the globe.
 * Every control reports its choice (App tracks it as globe_gate).
 */
export default function PhoneGate({ onChoice }: { onChoice: (choice: GateChoice) => void }) {
  return (
    <GlobeFallbackScreen
      message="The 3D globe is optimized for desktop browsers."
      hint="Explore our mobile-friendly pages below, or continue to the globe."
    >
      <FallbackLinkRows onChoice={onChoice} />
      <div className="mobile-actions-row">
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
