/**
 * TransitionWipe — crossfade with optional narration text between story sections.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { TransitionSegment } from "../types";

interface TransitionWipeProps {
  segment: TransitionSegment;
}

export const TransitionWipe: React.FC<TransitionWipeProps> = ({ segment }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Fade in from black, then fade out
  const midpoint = durationInFrames / 2;
  const opacity = interpolate(
    frame,
    [0, midpoint * 0.4, midpoint, durationInFrames * 0.8, durationInFrames],
    [0, 1, 1, 1, 0],
    { extrapolateRight: "clamp" },
  );

  // Text slides in
  const textY = interpolate(frame, [0, fps * 0.3], [20, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a1a" }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity,
        }}
      >
        <div
          style={{
            color: "#f0c040",
            fontSize: 36,
            fontWeight: 400,
            fontFamily: "system-ui, sans-serif",
            fontStyle: "italic",
            transform: `translateY(${textY}px)`,
            textAlign: "center",
            maxWidth: 800,
          }}
        >
          {segment.narration}
        </div>
      </div>

      {segment.audio && <Audio src={segment.audio} />}
    </AbsoluteFill>
  );
};
