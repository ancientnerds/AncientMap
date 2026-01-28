/**
 * ProductTeaser Composition
 *
 * 16:9 horizontal teaser video for YouTube/website.
 * Duration: 45-60 seconds
 * Content: Logo → Globe → Filters → Search → Popup → Stats → Outro
 */

import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  Img,
} from 'remotion';
import { Intro, Outro, SiteInfo, StaticGlobe, GlobeClip } from './shared';
import { BRAND, BACKGROUNDS, TEXT, FONTS, SHADOWS, RADIUS } from '../styles/theme';
import { SiteDetail, TeaserVideoProps } from '../data/types';

// =============================================================================
// Configuration
// =============================================================================

const TEASER_CONFIG = {
  width: 1920,
  height: 1080,
  fps: 30,
  // Segment durations (in frames at 30fps)
  segments: {
    intro: 90,           // 3 seconds
    globeReveal: 120,    // 4 seconds
    features: 180,       // 6 seconds
    siteShowcase: 360,   // 12 seconds (3 sites @ 4s each)
    stats: 120,          // 4 seconds
    outro: 90,           // 3 seconds
  },
};

// Calculate total duration
const TOTAL_FRAMES = Object.values(TEASER_CONFIG.segments).reduce((a, b) => a + b, 0);

// =============================================================================
// Sub-components
// =============================================================================

interface StatsDisplayProps {
  totalSites: number;
  categories: number;
  countries: number;
}

const StatsDisplay: React.FC<StatsDisplayProps> = ({
  totalSites,
  categories,
  countries,
}) => {
  const frame = useCurrentFrame();

  const stats = [
    { value: totalSites.toLocaleString() + '+', label: 'Archaeological Sites' },
    { value: categories.toString(), label: 'Categories' },
    { value: countries.toString() + '+', label: 'Countries' },
  ];

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: BACKGROUNDS.dark,
      }}
    >
      {/* Background */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(circle at 50% 50%, rgba(0, 180, 180, 0.1) 0%, transparent 60%)`,
        }}
      />

      {/* Stats grid */}
      <div
        style={{
          display: 'flex',
          gap: 80,
          zIndex: 10,
        }}
      >
        {stats.map((stat, index) => {
          const delay = index * 10;
          const opacity = interpolate(frame, [delay, delay + 20], [0, 1], {
            extrapolateRight: 'clamp',
          });
          const scale = interpolate(frame, [delay, delay + 20], [0.8, 1], {
            extrapolateRight: 'clamp',
          });
          const counterValue = interpolate(
            frame,
            [delay, delay + 30],
            [0, 1],
            { extrapolateRight: 'clamp' }
          );

          return (
            <div
              key={stat.label}
              style={{
                opacity,
                transform: `scale(${scale})`,
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  fontSize: 72,
                  fontWeight: 900,
                  color: BRAND.gold,
                  fontFamily: FONTS.heading,
                  textShadow: SHADOWS.glowGold,
                }}
              >
                {stat.value}
              </div>
              <div
                style={{
                  fontSize: 20,
                  fontWeight: 500,
                  color: TEXT.secondary,
                  fontFamily: FONTS.body,
                  textTransform: 'uppercase',
                  letterSpacing: 2,
                  marginTop: 8,
                }}
              >
                {stat.label}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

interface FeatureShowcaseProps {
  features: string[];
}

const FeatureShowcase: React.FC<FeatureShowcaseProps> = ({ features }) => {
  const frame = useCurrentFrame();

  const defaultFeatures = [
    'Interactive 3D Globe',
    'Advanced Filtering',
    'AI-Powered Search',
    'Detailed Site Info',
  ];

  const displayFeatures = features.length > 0 ? features : defaultFeatures;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BACKGROUNDS.dark,
      }}
    >
      {/* Background gradient */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `linear-gradient(135deg, rgba(192, 32, 35, 0.1) 0%, rgba(0, 180, 180, 0.1) 100%)`,
        }}
      />

      {/* Features list */}
      <div
        style={{
          position: 'absolute',
          left: '10%',
          top: '50%',
          transform: 'translateY(-50%)',
          display: 'flex',
          flexDirection: 'column',
          gap: 32,
        }}
      >
        {displayFeatures.map((feature, index) => {
          const delay = index * 20;
          const opacity = interpolate(frame, [delay, delay + 15], [0, 1], {
            extrapolateRight: 'clamp',
          });
          const slideX = interpolate(frame, [delay, delay + 15], [-30, 0], {
            extrapolateRight: 'clamp',
          });

          return (
            <div
              key={feature}
              style={{
                opacity,
                transform: `translateX(${slideX}px)`,
                display: 'flex',
                alignItems: 'center',
                gap: 16,
              }}
            >
              <div
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: '50%',
                  backgroundColor: BRAND.teal,
                  boxShadow: SHADOWS.glow,
                }}
              />
              <span
                style={{
                  fontSize: 36,
                  fontWeight: 600,
                  color: TEXT.primary,
                  fontFamily: FONTS.heading,
                }}
              >
                {feature}
              </span>
            </div>
          );
        })}
      </div>

      {/* Right side decoration */}
      <div
        style={{
          position: 'absolute',
          right: '10%',
          top: '50%',
          transform: 'translateY(-50%)',
          width: 400,
          height: 400,
          borderRadius: '50%',
          border: `2px solid ${BRAND.teal}`,
          opacity: interpolate(frame, [0, 30], [0, 0.3], {
            extrapolateRight: 'clamp',
          }),
        }}
      />
    </AbsoluteFill>
  );
};

interface SiteCarouselProps {
  sites: SiteDetail[];
  framesPerSite: number;
}

const SiteCarousel: React.FC<SiteCarouselProps> = ({ sites, framesPerSite }) => {
  const frame = useCurrentFrame();

  // Determine which site to show
  const siteIndex = Math.min(
    Math.floor(frame / framesPerSite),
    sites.length - 1
  );
  const currentSite = sites[siteIndex];
  const localFrame = frame % framesPerSite;

  if (!currentSite) {
    return null;
  }

  // Transition animation
  const opacity = interpolate(
    localFrame,
    [0, 15, framesPerSite - 15, framesPerSite],
    [0, 1, 1, 0],
    { extrapolateRight: 'clamp' }
  );

  const scale = interpolate(
    localFrame,
    [0, 15, framesPerSite - 15, framesPerSite],
    [1.1, 1, 1, 0.95],
    { extrapolateRight: 'clamp' }
  );

  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      {/* Background (placeholder for captured frames) */}
      <StaticGlobe opacity={0.4} />

      {/* Site info overlay */}
      <SiteInfo site={currentSite} variant="full" position="bottom" />

      {/* Site number indicator */}
      <div
        style={{
          position: 'absolute',
          top: 40,
          right: 40,
          padding: '8px 16px',
          background: 'rgba(0, 0, 0, 0.5)',
          borderRadius: RADIUS.md,
        }}
      >
        <span
          style={{
            fontSize: 18,
            fontWeight: 500,
            color: TEXT.secondary,
            fontFamily: FONTS.mono,
          }}
        >
          {siteIndex + 1} / {sites.length}
        </span>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Main Composition
// =============================================================================

export interface ProductTeaserProps {
  title?: string;
  tagline?: string;
  featuredSites?: SiteDetail[];
  stats?: {
    totalSites: number;
    categories: number;
    countries: number;
  };
  features?: string[];
  globeFrames?: string[];
  logoSrc?: string;
}

export const ProductTeaser: React.FC<ProductTeaserProps> = ({
  title = 'ANCIENT NERDS',
  tagline = 'Explore 800,000+ Archaeological Sites',
  featuredSites = [],
  stats = { totalSites: 800000, categories: 50, countries: 200 },
  features = [],
  globeFrames = [],
  logoSrc,
}) => {
  const { segments } = TEASER_CONFIG;

  // Calculate start frames for each segment
  let currentFrame = 0;
  const segmentStarts = {
    intro: currentFrame,
    globeReveal: (currentFrame += segments.intro),
    features: (currentFrame += segments.globeReveal),
    siteShowcase: (currentFrame += segments.features),
    stats: (currentFrame += segments.siteShowcase),
    outro: (currentFrame += segments.stats),
  };

  return (
    <AbsoluteFill style={{ backgroundColor: BACKGROUNDS.dark }}>
      {/* Intro - Logo reveal */}
      <Sequence from={segmentStarts.intro} durationInFrames={segments.intro}>
        <Intro title={title} subtitle={tagline} logoSrc={logoSrc} />
      </Sequence>

      {/* Globe reveal */}
      <Sequence from={segmentStarts.globeReveal} durationInFrames={segments.globeReveal}>
        {globeFrames.length > 0 ? (
          <GlobeClip frames={globeFrames} overlay="vignette" />
        ) : (
          <StaticGlobe />
        )}
      </Sequence>

      {/* Features showcase */}
      <Sequence from={segmentStarts.features} durationInFrames={segments.features}>
        <FeatureShowcase features={features} />
      </Sequence>

      {/* Site showcase carousel */}
      <Sequence from={segmentStarts.siteShowcase} durationInFrames={segments.siteShowcase}>
        <SiteCarousel
          sites={featuredSites}
          framesPerSite={Math.floor(segments.siteShowcase / Math.max(featuredSites.length, 1))}
        />
      </Sequence>

      {/* Stats display */}
      <Sequence from={segmentStarts.stats} durationInFrames={segments.stats}>
        <StatsDisplay {...stats} />
      </Sequence>

      {/* Outro - CTA */}
      <Sequence from={segmentStarts.outro} durationInFrames={segments.outro}>
        <Outro logoSrc={logoSrc} />
      </Sequence>
    </AbsoluteFill>
  );
};

// =============================================================================
// Export Configuration
// =============================================================================

export const productTeaserConfig = {
  id: 'ProductTeaser',
  component: ProductTeaser,
  durationInFrames: TOTAL_FRAMES,
  fps: TEASER_CONFIG.fps,
  width: TEASER_CONFIG.width,
  height: TEASER_CONFIG.height,
};

export default ProductTeaser;
