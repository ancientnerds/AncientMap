/**
 * LowerThird — channel/site attribution overlay displayed over video clips.
 *
 * Two variants:
 * - Channel attribution: shows channel name + video title over YouTube clips
 * - Site info: shows site name, period, country with flag
 */

import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface ChannelAttributionProps {
  channel: string;
  title: string;
}

export const ChannelAttribution: React.FC<ChannelAttributionProps> = ({
  channel,
  title,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Slide in from left over 0.5s, stay, slide out in last 0.5s
  const slideIn = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });
  const translateX = interpolate(slideIn, [0, 1], [-300, 0]);
  const opacity = interpolate(slideIn, [0, 1], [0, 1]);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 80,
        left: 0,
        transform: `translateX(${translateX}px)`,
        opacity,
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.85)",
          padding: "8px 24px 8px 16px",
          borderRadius: "0 4px 4px 0",
        }}
      >
        <div
          style={{
            color: "#fff",
            fontSize: 22,
            fontWeight: 700,
            fontFamily: "system-ui, sans-serif",
          }}
        >
          {channel}
        </div>
      </div>
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.7)",
          padding: "6px 24px 6px 16px",
          borderRadius: "0 4px 4px 0",
          maxWidth: 600,
        }}
      >
        <div
          style={{
            color: "#ccc",
            fontSize: 16,
            fontFamily: "system-ui, sans-serif",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {title}
        </div>
      </div>
    </div>
  );
};

interface SiteInfoProps {
  siteName: string;
  period: string;
  country: string;
  siteType: string;
}

export const SiteInfo: React.FC<SiteInfoProps> = ({
  siteName,
  period,
  country,
  siteType,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn = interpolate(frame, [0, fps * 0.4], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        bottom: 80,
        right: 40,
        opacity: fadeIn,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: 4,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(192, 32, 35, 0.9)",
          padding: "10px 20px",
          borderRadius: 4,
        }}
      >
        <div
          style={{
            color: "#fff",
            fontSize: 26,
            fontWeight: 700,
            fontFamily: "system-ui, sans-serif",
          }}
        >
          {siteName}
        </div>
      </div>
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.8)",
          padding: "6px 16px",
          borderRadius: 4,
          display: "flex",
          gap: 16,
        }}
      >
        {period && (
          <span style={{ color: "#f0c040", fontSize: 16, fontFamily: "system-ui, sans-serif" }}>
            {period}
          </span>
        )}
        {siteType && (
          <span style={{ color: "#aaa", fontSize: 16, fontFamily: "system-ui, sans-serif" }}>
            {siteType}
          </span>
        )}
        {country && (
          <span style={{ color: "#ccc", fontSize: 16, fontFamily: "system-ui, sans-serif" }}>
            {country}
          </span>
        )}
      </div>
    </div>
  );
};
