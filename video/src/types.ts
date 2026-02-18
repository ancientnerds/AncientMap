/**
 * Timeline JSON schema types — matches the output of pipeline/video/timeline_builder.py.
 */

export interface WordTiming {
  word: string;
  start: number;
  end: number;
}

export interface ClipAttribution {
  channel: string;
  title: string;
}

export interface LowerThirdData {
  siteName: string;
  period: string;
  country: string;
  siteType: string;
}

export interface VisualElement {
  type: "screenshot" | "clip" | "wiki_image" | "globe_flyto";
  src?: string;
  startFrame: number;
  endFrame: number;
  attribution?: ClipAttribution;
  targetLat?: number;
  targetLon?: number;
  siteName?: string;
  country?: string;
}

export interface CreditEntry {
  channel: string;
  clips_used: number;
}

export interface SourceEntry {
  citation: number;
  video_id: string;
  timestamp_seconds: number | null;
  channel_name: string;
  video_title: string;
}

export interface IntroSegment {
  type: "intro";
  startFrame: number;
  durationFrames: number;
  audio: string;
  wordTimings: WordTiming[];
  titleText: string;
  dateRange: string;
}

export interface StorySegment {
  type: "story";
  startFrame: number;
  durationFrames: number;
  audio: string;
  wordTimings: WordTiming[];
  visuals: VisualElement[];
  lowerThird: LowerThirdData | null;
  sectionHeading: string;
}

export interface TransitionSegment {
  type: "transition";
  startFrame: number;
  durationFrames: number;
  audio: string;
  wordTimings: WordTiming[];
  narration: string;
}

export interface OutroSegment {
  type: "outro";
  startFrame: number;
  durationFrames: number;
  audio: string;
  wordTimings: WordTiming[];
  credits: CreditEntry[];
  sources: SourceEntry[];
}

export type TimelineSegment =
  | IntroSegment
  | StorySegment
  | TransitionSegment
  | OutroSegment;

export interface Timeline {
  fps: number;
  width: number;
  height: number;
  totalDurationFrames: number;
  totalDurationSeconds: number;
  segments: TimelineSegment[];
  title: string;
  articleTitle: string;
  dateRange: string;
}
