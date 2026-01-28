/**
 * Remotion Root Component
 *
 * Entry point for Remotion that registers all compositions.
 */

import React from 'react';
import { Composition } from 'remotion';
import {
  ProductTeaser,
  productTeaserConfig,
  SiteShort,
  siteShortConfig,
  EpicDiscoveryTeaser,
  epicDiscoveryTeaserConfig,
} from './compositions';
import { SiteDetail } from './data/types';

// =============================================================================
// Default Props
// =============================================================================

const defaultTeaserProps = {
  title: 'ANCIENT NERDS',
  tagline: 'Explore 800,000+ Archaeological Sites',
  featuredSites: [],
  stats: {
    totalSites: 800000,
    categories: 50,
    countries: 200,
  },
  features: [
    'Interactive 3D Globe',
    'Advanced Filtering',
    'AI-Powered Search',
    'Detailed Site Info',
  ],
};

const defaultSiteDetail: SiteDetail = {
  id: 'sample-site',
  source: 'ancient_nerds',
  name: 'Machu Picchu',
  lat: -13.1631,
  lon: -72.5450,
  type: 'City/town/settlement',
  period: {
    start: 1450,
    end: 1572,
    name: '15th-16th Century',
  },
  country: 'Peru',
  description:
    'Machu Picchu is a 15th-century Inca citadel located in the Eastern Cordillera of southern Peru on a mountain ridge above the Sacred Valley.',
};

const defaultShortProps = {
  site: defaultSiteDetail,
};

// =============================================================================
// Root Component
// =============================================================================

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* Product Teaser - 16:9 Horizontal */}
      <Composition
        id={productTeaserConfig.id}
        component={ProductTeaser}
        durationInFrames={productTeaserConfig.durationInFrames}
        fps={productTeaserConfig.fps}
        width={productTeaserConfig.width}
        height={productTeaserConfig.height}
        defaultProps={defaultTeaserProps}
      />

      {/* Site Short - 9:16 Vertical */}
      <Composition
        id={siteShortConfig.id}
        component={SiteShort}
        durationInFrames={siteShortConfig.durationInFrames}
        fps={siteShortConfig.fps}
        width={siteShortConfig.width}
        height={siteShortConfig.height}
        defaultProps={defaultShortProps}
      />

      {/* Epic Discovery Teaser - The Main Teaser */}
      <Composition
        id={epicDiscoveryTeaserConfig.id}
        component={EpicDiscoveryTeaser}
        durationInFrames={epicDiscoveryTeaserConfig.durationInFrames}
        fps={epicDiscoveryTeaserConfig.fps}
        width={epicDiscoveryTeaserConfig.width}
        height={epicDiscoveryTeaserConfig.height}
        defaultProps={{ logoSrc: undefined }}
      />

      {/* Preview Compositions for Testing */}
      <Composition
        id="TeaserPreview"
        component={ProductTeaser}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultTeaserProps}
      />

      <Composition
        id="ShortPreview"
        component={SiteShort}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultShortProps}
      />
    </>
  );
};

export default RemotionRoot;
