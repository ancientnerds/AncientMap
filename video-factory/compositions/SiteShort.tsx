/**
 * SiteShort Composition
 *
 * 9:16 vertical short video for each archaeological site.
 * Duration: 15-30 seconds
 * Content: Site name → Globe fly-to → Key facts → Images → CTA
 * Embeddable in site popups.
 */

import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  Img,
  spring,
} from 'remotion';
import { SiteInfo, GlobeClip, StaticGlobe } from './shared';
import {
  BRAND,
  BACKGROUNDS,
  TEXT,
  FONTS,
  SHADOWS,
  RADIUS,
  BORDERS,
  getCategoryColor,
} from '../styles/theme';
import { SiteDetail, SiteVideoProps } from '../data/types';

// =============================================================================
// Configuration
// =============================================================================

const SHORT_CONFIG = {
  width: 1080,
  height: 1920,
  fps: 30,
  // Segment durations (in frames at 30fps)
  segments: {
    titleReveal: 60,      // 2 seconds
    globeFlyTo: 150,      // 5 seconds
    siteInfo: 120,        // 4 seconds
    facts: 120,           // 4 seconds
    cta: 60,              // 2 seconds
  },
};

// Calculate total duration
const TOTAL_FRAMES = Object.values(SHORT_CONFIG.segments).reduce((a, b) => a + b, 0);

// =============================================================================
// Sub-components
// =============================================================================

interface TitleRevealProps {
  siteName: string;
  category?: string;
}

const TitleReveal: React.FC<TitleRevealProps> = ({ siteName, category }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Spring animation for title
  const titleScale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 100 },
  });

  const titleOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const categoryOpacity = interpolate(frame, [20, 35], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const categorySlide = interpolate(frame, [20, 35], [20, 0], {
    extrapolateRight: 'clamp',
  });

  const categoryColor = category ? getCategoryColor(category) : BRAND.teal;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BACKGROUNDS.dark,
        justifyContent: 'center',
        alignItems: 'center',
        padding: 48,
      }}
    >
      {/* Background accent */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(circle at 50% 40%, rgba(0, 180, 180, 0.15) 0%, transparent 50%)`,
        }}
      />

      {/* Content */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 24,
          textAlign: 'center',
          zIndex: 10,
        }}
      >
        {/* Category badge */}
        {category && (
          <div
            style={{
              opacity: categoryOpacity,
              transform: `translateY(${categorySlide}px)`,
            }}
          >
            <span
              style={{
                display: 'inline-block',
                padding: '12px 28px',
                background: `rgba(${hexToRgb(categoryColor)}, 0.2)`,
                border: `2px solid ${categoryColor}`,
                borderRadius: RADIUS.full,
                color: categoryColor,
                fontSize: 20,
                fontWeight: 700,
                fontFamily: FONTS.body,
                textTransform: 'uppercase',
                letterSpacing: 2,
              }}
            >
              {category}
            </span>
          </div>
        )}

        {/* Site name */}
        <h1
          style={{
            opacity: titleOpacity,
            transform: `scale(${titleScale})`,
            margin: 0,
            fontSize: 72,
            fontWeight: 900,
            color: TEXT.primary,
            fontFamily: FONTS.heading,
            lineHeight: 1.1,
            textShadow: SHADOWS.xl,
            maxWidth: '90%',
          }}
        >
          {siteName}
        </h1>
      </div>

      {/* Decorative line */}
      <div
        style={{
          position: 'absolute',
          bottom: 200,
          left: '50%',
          transform: 'translateX(-50%)',
          width: interpolate(frame, [40, 55], [0, 200], {
            extrapolateRight: 'clamp',
          }),
          height: 3,
          background: `linear-gradient(90deg, transparent, ${BRAND.teal}, transparent)`,
        }}
      />
    </AbsoluteFill>
  );
};

interface FactsDisplayProps {
  site: SiteDetail;
}

const FactsDisplay: React.FC<FactsDisplayProps> = ({ site }) => {
  const frame = useCurrentFrame();

  // Build facts array
  const facts: { label: string; value: string }[] = [];

  if (site.country) {
    facts.push({ label: 'Location', value: site.country });
  }
  if (site.period?.name) {
    facts.push({ label: 'Period', value: site.period.name });
  } else if (site.period?.start) {
    const periodStr = site.period.end
      ? `${site.period.start} - ${site.period.end}`
      : `${site.period.start} onwards`;
    facts.push({ label: 'Period', value: periodStr });
  }
  if (site.type) {
    facts.push({ label: 'Type', value: site.type });
  }
  if (site.source) {
    facts.push({ label: 'Source', value: site.source });
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BACKGROUNDS.dark,
        padding: 48,
      }}
    >
      {/* Background */}
      <StaticGlobe opacity={0.2} />

      {/* Facts container */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: 48,
          right: 48,
          transform: 'translateY(-50%)',
          display: 'flex',
          flexDirection: 'column',
          gap: 32,
        }}
      >
        {/* Title */}
        <h2
          style={{
            margin: 0,
            fontSize: 36,
            fontWeight: 700,
            color: TEXT.accent,
            fontFamily: FONTS.heading,
            textTransform: 'uppercase',
            letterSpacing: 3,
            opacity: interpolate(frame, [0, 15], [0, 1], {
              extrapolateRight: 'clamp',
            }),
          }}
        >
          Key Facts
        </h2>

        {/* Facts list */}
        {facts.map((fact, index) => {
          const delay = 15 + index * 15;
          const opacity = interpolate(frame, [delay, delay + 15], [0, 1], {
            extrapolateRight: 'clamp',
          });
          const slideX = interpolate(frame, [delay, delay + 15], [-30, 0], {
            extrapolateRight: 'clamp',
          });

          return (
            <div
              key={fact.label}
              style={{
                opacity,
                transform: `translateX(${slideX}px)`,
                padding: 24,
                background: BACKGROUNDS.cardGlass,
                borderRadius: RADIUS.lg,
                border: `1px solid ${BORDERS.teal}`,
              }}
            >
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 500,
                  color: TEXT.secondary,
                  fontFamily: FONTS.body,
                  textTransform: 'uppercase',
                  letterSpacing: 1,
                  marginBottom: 4,
                }}
              >
                {fact.label}
              </div>
              <div
                style={{
                  fontSize: 28,
                  fontWeight: 600,
                  color: TEXT.primary,
                  fontFamily: FONTS.heading,
                }}
              >
                {fact.value}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

interface ShortCTAProps {
  siteName: string;
}

const ShortCTA: React.FC<ShortCTAProps> = ({ siteName }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const buttonScale = spring({
    frame: frame - 15,
    fps,
    config: { damping: 10, stiffness: 80 },
  });

  const opacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: 'clamp',
  });

  // Glow animation
  const glowIntensity = interpolate(
    Math.sin(frame * 0.15),
    [-1, 1],
    [0.3, 0.6]
  );

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BACKGROUNDS.dark,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      {/* Background */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(ellipse at 50% 60%, rgba(192, 32, 35, 0.2) 0%, transparent 50%)`,
        }}
      />

      {/* Content */}
      <div
        style={{
          opacity,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 40,
          textAlign: 'center',
          padding: 48,
        }}
      >
        {/* Explore text */}
        <p
          style={{
            margin: 0,
            fontSize: 28,
            fontWeight: 500,
            color: TEXT.secondary,
            fontFamily: FONTS.body,
          }}
        >
          Discover more about
        </p>

        {/* Site name */}
        <h2
          style={{
            margin: 0,
            fontSize: 48,
            fontWeight: 700,
            color: TEXT.primary,
            fontFamily: FONTS.heading,
          }}
        >
          {siteName}
        </h2>

        {/* CTA Button */}
        <div
          style={{
            transform: `scale(${Math.max(0, buttonScale)})`,
            padding: '24px 48px',
            background: BRAND.primary,
            borderRadius: RADIUS.lg,
            boxShadow: `0 0 ${50 * glowIntensity}px rgba(192, 32, 35, ${glowIntensity})`,
          }}
        >
          <span
            style={{
              fontSize: 28,
              fontWeight: 700,
              color: TEXT.primary,
              fontFamily: FONTS.heading,
              letterSpacing: 1,
            }}
          >
            Explore on Ancient Nerds
          </span>
        </div>

        {/* Website */}
        <p
          style={{
            margin: 0,
            fontSize: 24,
            fontWeight: 500,
            color: TEXT.accent,
            fontFamily: FONTS.mono,
          }}
        >
          ancientnerds.com
        </p>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Main Composition
// =============================================================================

export interface SiteShortProps {
  site: SiteDetail;
  globeFrames?: string[];
  thumbnailSrc?: string;
}

export const SiteShort: React.FC<SiteShortProps> = ({
  site,
  globeFrames = [],
  thumbnailSrc,
}) => {
  const { segments } = SHORT_CONFIG;

  // Calculate start frames for each segment
  let currentFrame = 0;
  const segmentStarts = {
    titleReveal: currentFrame,
    globeFlyTo: (currentFrame += segments.titleReveal),
    siteInfo: (currentFrame += segments.globeFlyTo),
    facts: (currentFrame += segments.siteInfo),
    cta: (currentFrame += segments.facts),
  };

  return (
    <AbsoluteFill style={{ backgroundColor: BACKGROUNDS.dark }}>
      {/* Title reveal */}
      <Sequence
        from={segmentStarts.titleReveal}
        durationInFrames={segments.titleReveal}
      >
        <TitleReveal siteName={site.name} category={site.type} />
      </Sequence>

      {/* Globe fly-to */}
      <Sequence
        from={segmentStarts.globeFlyTo}
        durationInFrames={segments.globeFlyTo}
      >
        {globeFrames.length > 0 ? (
          <GlobeClip frames={globeFrames} overlay="gradient" />
        ) : thumbnailSrc ? (
          <AbsoluteFill>
            <Img
              src={thumbnailSrc}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background: 'radial-gradient(circle, transparent 30%, rgba(0,0,0,0.6) 100%)',
              }}
            />
          </AbsoluteFill>
        ) : (
          <StaticGlobe />
        )}
      </Sequence>

      {/* Site info overlay */}
      <Sequence
        from={segmentStarts.siteInfo}
        durationInFrames={segments.siteInfo}
      >
        <AbsoluteFill>
          <StaticGlobe opacity={0.3} />
          <SiteInfo
            site={site}
            variant="compact"
            position="center"
            showDescription={true}
          />
        </AbsoluteFill>
      </Sequence>

      {/* Facts display */}
      <Sequence from={segmentStarts.facts} durationInFrames={segments.facts}>
        <FactsDisplay site={site} />
      </Sequence>

      {/* CTA */}
      <Sequence from={segmentStarts.cta} durationInFrames={segments.cta}>
        <ShortCTA siteName={site.name} />
      </Sequence>
    </AbsoluteFill>
  );
};

// =============================================================================
// Utilities
// =============================================================================

function hexToRgb(hex: string): string {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (result) {
    return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
  }
  return '255, 255, 255';
}

// =============================================================================
// Export Configuration
// =============================================================================

export const siteShortConfig = {
  id: 'SiteShort',
  component: SiteShort,
  durationInFrames: TOTAL_FRAMES,
  fps: SHORT_CONFIG.fps,
  width: SHORT_CONFIG.width,
  height: SHORT_CONFIG.height,
};

export default SiteShort;
