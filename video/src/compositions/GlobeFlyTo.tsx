/**
 * GlobeFlyTo — camera animation from one point to another on the 3D globe.
 *
 * Ported from useFlyToAnimation.ts SLERP logic, using @remotion/three for rendering.
 */

import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Globe3D } from "../components/Globe3D";

interface GlobeFlyToProps {
  targetLat: number;
  targetLon: number;
  siteName: string;
  country: string;
  /** Previous camera position. Defaults to a wide view if not provided. */
  startLat?: number;
  startLon?: number;
}

export const GlobeFlyTo: React.FC<GlobeFlyToProps> = ({
  targetLat,
  targetLon,
  siteName,
  country,
  startLat = 30,
  startLon = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Site label fades in during the last third of the animation
  const labelStart = Math.floor(durationInFrames * 0.6);
  const labelOpacity = interpolate(frame, [labelStart, labelStart + fps * 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a1a" }}>
      <Globe3D
        startLat={startLat}
        startLng={startLon}
        targetLat={targetLat}
        targetLng={targetLon}
        siteName={siteName}
      />

      {/* Site name label */}
      <div
        style={{
          position: "absolute",
          bottom: 100,
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: labelOpacity,
        }}
      >
        <div
          style={{
            display: "inline-block",
            backgroundColor: "rgba(0, 0, 0, 0.8)",
            padding: "12px 32px",
            borderRadius: 6,
            borderLeft: "4px solid #c02023",
          }}
        >
          <div
            style={{
              color: "#fff",
              fontSize: 32,
              fontWeight: 700,
              fontFamily: "system-ui, sans-serif",
            }}
          >
            {siteName}
          </div>
          {country && (
            <div
              style={{
                color: "#aaa",
                fontSize: 18,
                fontFamily: "system-ui, sans-serif",
                marginTop: 4,
              }}
            >
              {country}
            </div>
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};
