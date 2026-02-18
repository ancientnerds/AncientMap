/**
 * KenBurns — pan/zoom effect on still images (screenshots, wiki photos).
 *
 * Slowly zooms in and pans across the image for a cinematic feel.
 */

import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from "remotion";

interface KenBurnsProps {
  src: string;
  direction?: "zoom-in" | "zoom-out" | "pan-left" | "pan-right";
}

export const KenBurns: React.FC<KenBurnsProps> = ({
  src,
  direction = "zoom-in",
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const progress = frame / durationInFrames;

  let scale: number;
  let translateX: number;
  let translateY: number;

  switch (direction) {
    case "zoom-in":
      scale = interpolate(progress, [0, 1], [1, 1.15]);
      translateX = interpolate(progress, [0, 1], [0, -2]);
      translateY = interpolate(progress, [0, 1], [0, -1]);
      break;
    case "zoom-out":
      scale = interpolate(progress, [0, 1], [1.15, 1]);
      translateX = interpolate(progress, [0, 1], [-2, 0]);
      translateY = interpolate(progress, [0, 1], [-1, 0]);
      break;
    case "pan-left":
      scale = 1.08;
      translateX = interpolate(progress, [0, 1], [3, -3]);
      translateY = 0;
      break;
    case "pan-right":
      scale = 1.08;
      translateX = interpolate(progress, [0, 1], [-3, 3]);
      translateY = 0;
      break;
  }

  return (
    <AbsoluteFill style={{ overflow: "hidden", backgroundColor: "#000" }}>
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translate(${translateX}%, ${translateY}%)`,
        }}
      />
    </AbsoluteFill>
  );
};
