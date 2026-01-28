/**
 * GlobeClip component for displaying captured globe frames
 *
 * Displays a sequence of captured frames as video.
 */

import React from 'react';
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BACKGROUNDS } from '../../styles/theme';

// =============================================================================
// Types
// =============================================================================

export interface GlobeClipProps {
  frames: string[];
  startFrame?: number;
  durationInFrames?: number;
  zoom?: number;
  opacity?: number;
  overlay?: 'none' | 'vignette' | 'gradient';
}

// =============================================================================
// Component
// =============================================================================

export const GlobeClip: React.FC<GlobeClipProps> = ({
  frames,
  startFrame = 0,
  durationInFrames,
  zoom = 1,
  opacity = 1,
  overlay = 'vignette',
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Calculate which frame to show
  const relativeFrame = frame - startFrame;
  const frameIndex = Math.min(
    Math.max(0, relativeFrame),
    frames.length - 1
  );

  // Get current frame path
  const currentFramePath = frames[frameIndex];

  if (!currentFramePath) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: BACKGROUNDS.darkBlue,
        }}
      />
    );
  }

  // Zoom animation
  const zoomValue = interpolate(
    frame,
    [0, durationInFrames || frames.length],
    [zoom, zoom * 1.05],
    { extrapolateRight: 'clamp' }
  );

  return (
    <AbsoluteFill>
      {/* Globe frame */}
      <AbsoluteFill
        style={{
          opacity,
          transform: `scale(${zoomValue})`,
          transformOrigin: 'center center',
        }}
      >
        <Img
          src={currentFramePath}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      </AbsoluteFill>

      {/* Overlay */}
      {overlay === 'vignette' && (
        <AbsoluteFill
          style={{
            background: 'radial-gradient(circle, transparent 40%, rgba(0,0,0,0.6) 100%)',
            pointerEvents: 'none',
          }}
        />
      )}

      {overlay === 'gradient' && (
        <AbsoluteFill
          style={{
            background: `linear-gradient(to bottom, rgba(0,0,0,0.3) 0%, transparent 30%, transparent 70%, rgba(0,0,0,0.5) 100%)`,
            pointerEvents: 'none',
          }}
        />
      )}
    </AbsoluteFill>
  );
};

// =============================================================================
// Static Globe Background
// =============================================================================

export interface StaticGlobeProps {
  imageSrc?: string;
  zoom?: number;
  opacity?: number;
}

export const StaticGlobe: React.FC<StaticGlobeProps> = ({
  imageSrc,
  zoom = 1,
  opacity = 0.6,
}) => {
  const frame = useCurrentFrame();

  // Subtle rotation animation
  const rotation = interpolate(frame, [0, 300], [0, 5], {
    extrapolateRight: 'extend',
  });

  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `scale(${zoom}) rotate(${rotation}deg)`,
        transformOrigin: 'center center',
      }}
    >
      {imageSrc ? (
        <Img
          src={imageSrc}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      ) : (
        // Placeholder gradient globe
        <div
          style={{
            width: '100%',
            height: '100%',
            background: `radial-gradient(circle at 30% 30%, ${BACKGROUNDS.darkBlue} 0%, #000 100%)`,
          }}
        />
      )}

      {/* Vignette overlay */}
      <AbsoluteFill
        style={{
          background: 'radial-gradient(circle, transparent 30%, rgba(0,0,0,0.7) 100%)',
          pointerEvents: 'none',
        }}
      />
    </AbsoluteFill>
  );
};

// =============================================================================
// Globe with Ken Burns effect
// =============================================================================

export interface KenBurnsGlobeProps {
  imageSrc: string;
  startZoom?: number;
  endZoom?: number;
  startX?: number;
  startY?: number;
  endX?: number;
  endY?: number;
}

export const KenBurnsGlobe: React.FC<KenBurnsGlobeProps> = ({
  imageSrc,
  startZoom = 1,
  endZoom = 1.2,
  startX = 50,
  startY = 50,
  endX = 50,
  endY = 50,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const progress = frame / durationInFrames;

  const currentZoom = interpolate(progress, [0, 1], [startZoom, endZoom]);
  const currentX = interpolate(progress, [0, 1], [startX, endX]);
  const currentY = interpolate(progress, [0, 1], [startY, endY]);

  return (
    <AbsoluteFill
      style={{
        overflow: 'hidden',
      }}
    >
      <Img
        src={imageSrc}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `scale(${currentZoom})`,
          transformOrigin: `${currentX}% ${currentY}%`,
        }}
      />

      {/* Vignette */}
      <AbsoluteFill
        style={{
          background: 'radial-gradient(circle, transparent 40%, rgba(0,0,0,0.5) 100%)',
          pointerEvents: 'none',
        }}
      />
    </AbsoluteFill>
  );
};

export default GlobeClip;
