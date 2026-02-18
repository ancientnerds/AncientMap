/**
 * WeeklyVideo — main composition that sequences all segments into a full video.
 *
 * Reads timeline.json as inputProps and renders IntroSequence, StorySegment,
 * TransitionWipe, and OutroSequence in order.
 */

import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import type {
  Timeline,
  IntroSegment,
  StorySegment as StorySegmentType,
  TransitionSegment,
  OutroSegment,
} from "./types";
import { IntroSequence } from "./compositions/IntroSequence";
import { StorySegment } from "./compositions/StorySegment";
import { TransitionWipe } from "./compositions/TransitionWipe";
import { OutroSequence } from "./compositions/OutroSequence";

export const WeeklyVideo: React.FC<Timeline> = (props) => {
  const { segments } = props;

  // Track previous site coordinates for globe fly-to transitions
  let prevSiteLat: number | undefined;
  let prevSiteLon: number | undefined;

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a1a" }}>
      {segments.map((segment, index) => {
        const { startFrame, durationFrames } = segment;

        let element: React.ReactNode;

        switch (segment.type) {
          case "intro":
            element = <IntroSequence segment={segment as IntroSegment} />;
            break;

          case "story": {
            const storySeg = segment as StorySegmentType;
            element = (
              <StorySegment
                segment={storySeg}
                prevSiteLat={prevSiteLat}
                prevSiteLon={prevSiteLon}
              />
            );
            // Update previous site position for next globe fly-to
            if (storySeg.lowerThird) {
              const flyToVisual = storySeg.visuals.find(
                (v) => v.type === "globe_flyto",
              );
              if (flyToVisual?.targetLat !== undefined) {
                prevSiteLat = flyToVisual.targetLat;
                prevSiteLon = flyToVisual.targetLon;
              }
            }
            break;
          }

          case "transition":
            element = (
              <TransitionWipe segment={segment as TransitionSegment} />
            );
            break;

          case "outro":
            element = <OutroSequence segment={segment as OutroSegment} />;
            break;

          default:
            element = null;
        }

        if (!element) return null;

        return (
          <Sequence
            key={index}
            from={startFrame}
            durationInFrames={durationFrames}
          >
            {element}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
