/**
 * SiteInfo component for displaying site details
 *
 * Shows site name, location, period, and description with animations.
 */

import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
} from 'remotion';
import {
  BRAND,
  BACKGROUNDS,
  TEXT,
  BORDERS,
  FONTS,
  RADIUS,
  SHADOWS,
  getCategoryColor,
} from '../../styles/theme';
import { SiteDetail } from '../../data/types';

// =============================================================================
// Types
// =============================================================================

export interface SiteInfoProps {
  site: SiteDetail;
  variant?: 'full' | 'compact' | 'minimal';
  position?: 'bottom' | 'center' | 'overlay';
  showDescription?: boolean;
  showBadge?: boolean;
}

// =============================================================================
// Component
// =============================================================================

export const SiteInfo: React.FC<SiteInfoProps> = ({
  site,
  variant = 'full',
  position = 'bottom',
  showDescription = true,
  showBadge = true,
}) => {
  const frame = useCurrentFrame();

  // Animation timing
  const containerFadeIn = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const nameSlide = interpolate(frame, [0, 20], [30, 0], {
    extrapolateRight: 'clamp',
  });

  const locationFadeIn = interpolate(frame, [10, 25], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const badgeFadeIn = interpolate(frame, [20, 35], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const descFadeIn = interpolate(frame, [30, 45], [0, 1], {
    extrapolateRight: 'clamp',
  });

  // Get category color
  const categoryColor = site.type ? getCategoryColor(site.type) : BRAND.teal;

  // Period text
  const periodText = site.period?.name || (
    site.period?.start && site.period?.end
      ? `${site.period.start} - ${site.period.end}`
      : site.period?.start
        ? `${site.period.start} onwards`
        : null
  );

  // Position styles
  const positionStyles: React.CSSProperties = position === 'center'
    ? { justifyContent: 'center', alignItems: 'center' }
    : position === 'overlay'
      ? { justifyContent: 'flex-end', alignItems: 'flex-start', padding: 48 }
      : { justifyContent: 'flex-end', alignItems: 'flex-start', padding: 48 };

  return (
    <AbsoluteFill style={positionStyles}>
      {/* Gradient overlay for readability */}
      {position !== 'center' && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            height: '50%',
            background: BACKGROUNDS.gradientBottom,
            pointerEvents: 'none',
          }}
        />
      )}

      {/* Content container */}
      <div
        style={{
          opacity: containerFadeIn,
          display: 'flex',
          flexDirection: 'column',
          gap: variant === 'minimal' ? 8 : 16,
          maxWidth: variant === 'compact' ? 600 : 800,
          zIndex: 10,
        }}
      >
        {/* Category badge */}
        {showBadge && site.type && (
          <div
            style={{
              opacity: badgeFadeIn,
              alignSelf: 'flex-start',
            }}
          >
            <span
              style={{
                display: 'inline-block',
                padding: '8px 20px',
                background: `rgba(${hexToRgb(categoryColor)}, 0.2)`,
                border: `1px solid ${categoryColor}`,
                borderRadius: RADIUS.full,
                color: categoryColor,
                fontSize: variant === 'minimal' ? 14 : 16,
                fontWeight: 600,
                fontFamily: FONTS.body,
                textTransform: 'uppercase',
                letterSpacing: 1,
              }}
            >
              {site.type}
            </span>
          </div>
        )}

        {/* Site name */}
        <h2
          style={{
            transform: `translateY(${nameSlide}px)`,
            margin: 0,
            fontSize: variant === 'minimal' ? 36 : variant === 'compact' ? 48 : 64,
            fontWeight: 700,
            color: TEXT.primary,
            fontFamily: FONTS.heading,
            lineHeight: 1.1,
            textShadow: SHADOWS.lg,
          }}
        >
          {site.name}
        </h2>

        {/* Location */}
        {site.country && (
          <p
            style={{
              opacity: locationFadeIn,
              margin: 0,
              fontSize: variant === 'minimal' ? 18 : 24,
              fontWeight: 400,
              color: 'rgba(255, 255, 255, 0.85)',
              fontFamily: FONTS.body,
            }}
          >
            {site.country}
          </p>
        )}

        {/* Period */}
        {periodText && (
          <p
            style={{
              opacity: locationFadeIn,
              margin: 0,
              fontSize: variant === 'minimal' ? 16 : 20,
              fontWeight: 500,
              color: TEXT.accent,
              fontFamily: FONTS.body,
            }}
          >
            {periodText}
          </p>
        )}

        {/* Description */}
        {showDescription && site.description && variant === 'full' && (
          <p
            style={{
              opacity: descFadeIn,
              margin: 0,
              marginTop: 8,
              fontSize: 18,
              fontWeight: 400,
              color: 'rgba(255, 255, 255, 0.8)',
              fontFamily: FONTS.body,
              lineHeight: 1.6,
              maxWidth: 600,
            }}
          >
            {site.description.length > 200
              ? `${site.description.slice(0, 200)}...`
              : site.description}
          </p>
        )}
      </div>
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

export default SiteInfo;
