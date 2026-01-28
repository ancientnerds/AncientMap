/**
 * Outro component for video compositions
 *
 * Displays call-to-action and branding.
 */

import React from 'react';
import {
  AbsoluteFill,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BRAND, BACKGROUNDS, TEXT, SHADOWS, FONTS, RADIUS } from '../../styles/theme';

// =============================================================================
// Types
// =============================================================================

export interface OutroProps {
  ctaText?: string;
  websiteUrl?: string;
  logoSrc?: string;
  showSocials?: boolean;
}

// =============================================================================
// Component
// =============================================================================

export const Outro: React.FC<OutroProps> = ({
  ctaText = 'Start Exploring',
  websiteUrl = 'ancientnerds.com',
  logoSrc,
  showSocials = true,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Animation timing
  const contentFadeIn = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const contentSlide = interpolate(frame, [0, 20], [40, 0], {
    extrapolateRight: 'clamp',
  });

  const ctaScale = interpolate(frame, [20, 35], [0.9, 1], {
    extrapolateRight: 'clamp',
  });

  const ctaGlow = interpolate(
    Math.sin(frame * 0.15),
    [-1, 1],
    [0.2, 0.5]
  );

  const urlFadeIn = interpolate(frame, [35, 50], [0, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BACKGROUNDS.dark,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      {/* Background gradient */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(ellipse at 50% 80%, rgba(192, 32, 35, 0.2) 0%, transparent 50%)`,
        }}
      />

      {/* Content container */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 40,
          opacity: contentFadeIn,
          transform: `translateY(${contentSlide}px)`,
        }}
      >
        {/* Logo */}
        {logoSrc && (
          <Img
            src={logoSrc}
            style={{
              width: 120,
              height: 120,
              objectFit: 'contain',
            }}
          />
        )}

        {/* CTA Button */}
        <div
          style={{
            transform: `scale(${ctaScale})`,
            padding: '20px 48px',
            background: BRAND.primary,
            borderRadius: RADIUS.lg,
            boxShadow: `0 0 ${40 * ctaGlow}px rgba(192, 32, 35, ${ctaGlow + 0.3})`,
          }}
        >
          <span
            style={{
              fontSize: 32,
              fontWeight: 700,
              color: TEXT.primary,
              fontFamily: FONTS.heading,
              letterSpacing: 2,
            }}
          >
            {ctaText}
          </span>
        </div>

        {/* Website URL */}
        <div
          style={{
            opacity: urlFadeIn,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span
            style={{
              fontSize: 36,
              fontWeight: 600,
              color: TEXT.accent,
              fontFamily: FONTS.mono,
              letterSpacing: 2,
            }}
          >
            {websiteUrl}
          </span>

          {/* Social icons placeholder */}
          {showSocials && (
            <div
              style={{
                display: 'flex',
                gap: 24,
                marginTop: 16,
              }}
            >
              {['YouTube', 'Twitter', 'Discord'].map((social, index) => (
                <span
                  key={social}
                  style={{
                    fontSize: 16,
                    fontWeight: 500,
                    color: TEXT.secondary,
                    fontFamily: FONTS.body,
                    opacity: interpolate(
                      frame,
                      [50 + index * 5, 60 + index * 5],
                      [0, 1],
                      { extrapolateRight: 'clamp' }
                    ),
                  }}
                >
                  @AncientNerds
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Bottom tagline */}
      <div
        style={{
          position: 'absolute',
          bottom: 40,
          opacity: interpolate(frame, [60, 75], [0, 0.6], {
            extrapolateRight: 'clamp',
          }),
        }}
      >
        <span
          style={{
            fontSize: 18,
            fontWeight: 400,
            color: TEXT.muted,
            fontFamily: FONTS.body,
          }}
        >
          Discover humanity's ancient wonders
        </span>
      </div>
    </AbsoluteFill>
  );
};

export default Outro;
