/**
 * StorySegment — the core repeatable unit for each news story.
 *
 * Sequences: screenshot → YouTube clip (with attribution) → wiki images (Ken Burns)
 * Audio narration plays throughout. Optional site info lower-third and globe fly-to.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { StorySegment as StorySegmentType } from "../types";
import { KenBurns } from "../components/KenBurns";
import { SiteInfo } from "../components/LowerThird";
import { ClipWithAttribution } from "./ClipWithAttribution";
import { GlobeFlyTo } from "./GlobeFlyTo";

interface StorySegmentProps {
  segment: StorySegmentType;
  /** Previous site coordinates for globe fly-to starting position. */
  prevSiteLat?: number;
  prevSiteLon?: number;
}

const KEN_BURNS_DIRECTIONS = ["zoom-in", "zoom-out", "pan-left", "pan-right"] as const;

export const StorySegment: React.FC<StorySegmentProps> = ({
  segment,
  prevSiteLat,
  prevSiteLon,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Section heading fades in at the start
  const headingOpacity = interpolate(frame, [0, fps * 0.5, fps * 2, fps * 3], [0, 1, 1, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Visual elements sequenced by their frame ranges */}
      {segment.visuals.map((visual, i) => {
        const visualDuration = visual.endFrame - visual.startFrame;
        if (visualDuration <= 0) return null;

        return (
          <Sequence
            key={i}
            from={visual.startFrame}
            durationInFrames={visualDuration}
          >
            {visual.type === "screenshot" && visual.src && (
              <KenBurns
                src={visual.src}
                direction={KEN_BURNS_DIRECTIONS[i % KEN_BURNS_DIRECTIONS.length]}
              />
            )}

            {visual.type === "clip" && visual.src && visual.attribution && (
              <ClipWithAttribution
                src={visual.src}
                channel={visual.attribution.channel}
                title={visual.attribution.title}
              />
            )}

            {visual.type === "wiki_image" && visual.src && (
              <KenBurns
                src={visual.src}
                direction={KEN_BURNS_DIRECTIONS[(i + 1) % KEN_BURNS_DIRECTIONS.length]}
              />
            )}

            {visual.type === "globe_flyto" &&
              visual.targetLat !== undefined &&
              visual.targetLon !== undefined && (
                <GlobeFlyTo
                  targetLat={visual.targetLat}
                  targetLon={visual.targetLon}
                  siteName={visual.siteName || ""}
                  country={visual.country || ""}
                  startLat={prevSiteLat}
                  startLon={prevSiteLon}
                />
              )}
          </Sequence>
        );
      })}

      {/* Section heading overlay */}
      {segment.sectionHeading && (
        <div
          style={{
            position: "absolute",
            top: 40,
            left: 40,
            opacity: headingOpacity,
            backgroundColor: "rgba(192, 32, 35, 0.9)",
            padding: "8px 24px",
            borderRadius: 4,
          }}
        >
          <div
            style={{
              color: "#fff",
              fontSize: 20,
              fontWeight: 600,
              fontFamily: "system-ui, sans-serif",
              letterSpacing: 1,
              textTransform: "uppercase",
            }}
          >
            {segment.sectionHeading}
          </div>
        </div>
      )}

      {/* Site info lower-third */}
      {segment.lowerThird && (
        <Sequence from={Math.floor(durationInFrames * 0.1)}>
          <SiteInfo
            siteName={segment.lowerThird.siteName}
            period={segment.lowerThird.period}
            country={segment.lowerThird.country}
            siteType={segment.lowerThird.siteType}
          />
        </Sequence>
      )}

      {/* Narration audio */}
      {segment.audio && <Audio src={segment.audio} />}
    </AbsoluteFill>
  );
};
