/**
 * Root — Remotion composition registry.
 *
 * Registers the WeeklyVideo composition with default props for Remotion Studio preview.
 */

import React from "react";
import { Composition } from "remotion";
import { WeeklyVideo } from "./WeeklyVideo";
import type { Timeline } from "./types";

// Default props for Remotion Studio preview (no actual assets)
const defaultProps: Timeline = {
  fps: 30,
  width: 1920,
  height: 1080,
  totalDurationFrames: 900, // 30 seconds preview
  totalDurationSeconds: 30,
  title: "This Week in Archaeology",
  articleTitle: "Preview: Temple Discovery at Gobekli Tepe",
  dateRange: "February 10-16, 2026",
  segments: [
    {
      type: "intro",
      startFrame: 0,
      durationFrames: 240,
      audio: "",
      wordTimings: [],
      titleText: "This Week in Archaeology",
      dateRange: "February 10-16, 2026",
    },
    {
      type: "transition",
      startFrame: 240,
      durationFrames: 60,
      audio: "",
      wordTimings: [],
      narration: "Meanwhile, in Turkey...",
    },
    {
      type: "story",
      startFrame: 300,
      durationFrames: 450,
      audio: "",
      wordTimings: [],
      visuals: [],
      lowerThird: {
        siteName: "Gobekli Tepe",
        period: "Pre-Pottery Neolithic",
        country: "Turkey",
        siteType: "Temple",
      },
      sectionHeading: "New Excavations & Fieldwork",
    },
    {
      type: "outro",
      startFrame: 750,
      durationFrames: 150,
      audio: "",
      wordTimings: [],
      credits: [
        { channel: "World of Antiquity", clips_used: 3 },
        { channel: "Stefan Milo", clips_used: 2 },
      ],
      sources: [],
    },
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <Composition
        id="WeeklyVideo"
        component={WeeklyVideo as any}
        durationInFrames={defaultProps.totalDurationFrames}
        fps={defaultProps.fps}
        width={defaultProps.width}
        height={defaultProps.height}
        defaultProps={defaultProps as any}
      />
    </>
  );
};
