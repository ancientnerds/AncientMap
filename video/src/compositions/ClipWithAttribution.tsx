/**
 * ClipWithAttribution — YouTube clip playing with channel name + video title lower-third.
 */

import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ChannelAttribution } from "../components/LowerThird";

interface ClipWithAttributionProps {
  src: string;
  channel: string;
  title: string;
}

export const ClipWithAttribution: React.FC<ClipWithAttributionProps> = ({
  src,
  channel,
  title,
}) => {
  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
        // Mute source audio — AI narration plays over it
        volume={0.08}
      />
      <ChannelAttribution channel={channel} title={title} />
    </AbsoluteFill>
  );
};
