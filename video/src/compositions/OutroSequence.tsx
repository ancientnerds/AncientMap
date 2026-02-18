/**
 * OutroSequence — source channel credits scroll, subscribe CTA, website link.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { OutroSegment } from "../types";

interface OutroSequenceProps {
  segment: OutroSegment;
}

export const OutroSequence: React.FC<OutroSequenceProps> = ({ segment }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Credits scroll upward
  const totalCreditsHeight = (segment.credits.length + 2) * 50;
  const scrollY = interpolate(
    frame,
    [fps * 1, durationInFrames - fps * 2],
    [0, -totalCreditsHeight],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // "Thanks for watching" fade in
  const thanksOpacity = interpolate(frame, [0, fps * 0.8], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Website URL fades in later
  const urlOpacity = interpolate(
    frame,
    [durationInFrames - fps * 3, durationInFrames - fps * 2],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at center, #1a2a3a 0%, #0a0a1a 70%)",
      }}
    >
      {/* Header */}
      <div
        style={{
          position: "absolute",
          top: 100,
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: thanksOpacity,
        }}
      >
        <div
          style={{
            color: "#fff",
            fontSize: 36,
            fontWeight: 700,
            fontFamily: "system-ui, sans-serif",
          }}
        >
          Thanks for watching
        </div>
        <div
          style={{
            color: "#c02023",
            fontSize: 22,
            fontFamily: "system-ui, sans-serif",
            marginTop: 8,
            letterSpacing: 4,
            textTransform: "uppercase",
          }}
        >
          Sources & Credits
        </div>
      </div>

      {/* Scrolling credits */}
      <div
        style={{
          position: "absolute",
          top: 250,
          left: "20%",
          right: "20%",
          overflow: "hidden",
          height: 500,
        }}
      >
        <div style={{ transform: `translateY(${scrollY}px)` }}>
          {segment.credits.map((credit, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                padding: "12px 0",
                borderBottom: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              <span
                style={{
                  color: "#fff",
                  fontSize: 22,
                  fontFamily: "system-ui, sans-serif",
                }}
              >
                {credit.channel}
              </span>
              <span
                style={{
                  color: "#aaa",
                  fontSize: 18,
                  fontFamily: "system-ui, sans-serif",
                }}
              >
                {credit.clips_used} clip{credit.clips_used !== 1 ? "s" : ""}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Website URL */}
      <div
        style={{
          position: "absolute",
          bottom: 80,
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: urlOpacity,
        }}
      >
        <div
          style={{
            color: "#f0c040",
            fontSize: 28,
            fontFamily: "system-ui, sans-serif",
            letterSpacing: 2,
          }}
        >
          ancientnerds.com
        </div>
      </div>

      {segment.audio && <Audio src={segment.audio} />}
    </AbsoluteFill>
  );
};
