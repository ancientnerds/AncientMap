import { MIN_BASEMAP_TEXTURE_SIZE } from '../utils/deviceTier'
import { FallbackLink, GlobeFallbackScreen } from './globeFallbackLinks'

/**
 * What a browser that cannot run the globe sees instead of a black screen
 * (utils/globeSupport.ts decides): what is missing, the usual fix, and the
 * pages that work without the globe. The phone gate's layout and links.
 */
export default function GlobeUnsupported({ reason, detail }: { reason: 'no_webgl2' | 'max_texture_size'; detail: string | undefined }) {
  const missing = reason === 'no_webgl2'
    ? 'WebGL 2 is not available.'
    : `Your graphics card supports textures up to ${detail} px; the globe needs ${MIN_BASEMAP_TEXTURE_SIZE}.`
  return (
    <GlobeFallbackScreen
      message="Your browser can't show the 3D globe"
      hint={`${missing} Turning on hardware acceleration in your browser settings often fixes this.`}
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
      </div>
    </GlobeFallbackScreen>
  )
}
