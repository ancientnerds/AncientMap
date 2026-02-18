/**
 * IntroSequence — animated title card with date range and spinning globe.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from "remotion";
import type { IntroSegment } from "../types";

interface IntroSequenceProps {
  segment: IntroSegment;
}

export const IntroSequence: React.FC<IntroSequenceProps> = ({ segment }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Fade in the background
  const bgOpacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Title animation: scale up and fade in
  const titleScale = interpolate(frame, [fps * 0.3, fps * 1], [0.8, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleOpacity = interpolate(frame, [fps * 0.3, fps * 0.8], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Date range slides up
  const dateY = interpolate(frame, [fps * 0.8, fps * 1.5], [30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const dateOpacity = interpolate(frame, [fps * 0.8, fps * 1.5], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      {/* Dark background with gradient */}
      <AbsoluteFill
        style={{
          opacity: bgOpacity,
          background: "radial-gradient(ellipse at center, #1a2a3a 0%, #0a0a1a 70%)",
        }}
      />

      {/* Title */}
      <div
        style={{
          position: "absolute",
          top: "35%",
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: titleOpacity,
          transform: `scale(${titleScale})`,
        }}
      >
        <div
          style={{
            color: "#c02023",
            fontSize: 28,
            fontWeight: 400,
            fontFamily: "system-ui, sans-serif",
            letterSpacing: 8,
            textTransform: "uppercase",
            marginBottom: 16,
          }}
        >
          Ancient Nerds
        </div>
        <div
          style={{
            color: "#ffffff",
            fontSize: 56,
            fontWeight: 700,
            fontFamily: "system-ui, sans-serif",
            lineHeight: 1.2,
          }}
        >
          {segment.titleText}
        </div>
      </div>

      {/* Date range */}
      <div
        style={{
          position: "absolute",
          top: "58%",
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: dateOpacity,
          transform: `translateY(${dateY}px)`,
        }}
      >
        <div
          style={{
            color: "#f0c040",
            fontSize: 24,
            fontFamily: "system-ui, sans-serif",
            letterSpacing: 3,
          }}
        >
          {segment.dateRange}
        </div>
      </div>

      {/* Decorative line */}
      <div
        style={{
          position: "absolute",
          top: "55%",
          left: "30%",
          right: "30%",
          height: 2,
          backgroundColor: "#c02023",
          opacity: titleOpacity,
          transform: `scaleX(${titleScale})`,
        }}
      />

      {/* Audio */}
      {segment.audio && <Audio src={segment.audio} />}
    </AbsoluteFill>
  );
};
