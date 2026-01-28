/**
 * Intro component for video compositions
 *
 * Displays the Ancient Nerds logo with animated entrance.
 */

import React from 'react';
import {
  AbsoluteFill,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from 'remotion';
import { BRAND, BACKGROUNDS, TEXT, SHADOWS, FONTS } from '../../styles/theme';

// =============================================================================
// Types
// =============================================================================

export interface IntroProps {
  title?: string;
  subtitle?: string;
  logoSrc?: string;
  durationInFrames?: number;
}

// =============================================================================
// Component
// =============================================================================

export const Intro: React.FC<IntroProps> = ({
  title = 'ANCIENT NERDS',
  subtitle = 'Explore 800,000+ Archaeological Sites',
  logoSrc,
  durationInFrames = 90,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Animation timing
  const logoFadeIn = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const logoScale = interpolate(frame, [0, 20], [0.8, 1], {
    extrapolateRight: 'clamp',
  });

  const titleFadeIn = interpolate(frame, [15, 35], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const titleSlide = interpolate(frame, [15, 35], [30, 0], {
    extrapolateRight: 'clamp',
  });

  const subtitleFadeIn = interpolate(frame, [30, 50], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const subtitleSlide = interpolate(frame, [30, 50], [20, 0], {
    extrapolateRight: 'clamp',
  });

  // Glow animation
  const glowIntensity = interpolate(
    Math.sin(frame * 0.1),
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
      {/* Background gradient */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(circle at 50% 50%, rgba(0, 180, 180, 0.1) 0%, transparent 60%)`,
        }}
      />

      {/* Content container */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 24,
        }}
      >
        {/* Logo */}
        <div
          style={{
            opacity: logoFadeIn,
            transform: `scale(${logoScale})`,
            filter: `drop-shadow(0 0 ${30 * glowIntensity}px rgba(0, 180, 180, ${glowIntensity}))`,
          }}
        >
          {logoSrc ? (
            <Img
              src={logoSrc}
              style={{
                width: 200,
                height: 200,
                objectFit: 'contain',
              }}
            />
          ) : (
            <div
              style={{
                width: 150,
                height: 150,
                borderRadius: '50%',
                background: `linear-gradient(135deg, ${BRAND.gold} 0%, ${BRAND.primary} 100%)`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 72,
                fontWeight: 900,
                color: BRAND.white,
                fontFamily: FONTS.heading,
              }}
            >
              AN
            </div>
          )}
        </div>

        {/* Title */}
        <h1
          style={{
            opacity: titleFadeIn,
            transform: `translateY(${titleSlide}px)`,
            fontSize: 72,
            fontWeight: 900,
            color: TEXT.primary,
            fontFamily: FONTS.heading,
            letterSpacing: 8,
            margin: 0,
            textShadow: SHADOWS.lg,
          }}
        >
          {title}
        </h1>

        {/* Subtitle */}
        <p
          style={{
            opacity: subtitleFadeIn,
            transform: `translateY(${subtitleSlide}px)`,
            fontSize: 28,
            fontWeight: 400,
            color: TEXT.secondary,
            fontFamily: FONTS.body,
            margin: 0,
          }}
        >
          {subtitle}
        </p>
      </div>
    </AbsoluteFill>
  );
};

export default Intro;
