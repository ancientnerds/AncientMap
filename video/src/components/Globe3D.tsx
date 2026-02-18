/**
 * Globe3D — Three.js globe for @remotion/three fly-to animations.
 *
 * Ported from the main app's useFlyToAnimation.ts SLERP logic, adapted for
 * frame-based interpolation instead of requestAnimationFrame.
 *
 * Uses @react-three/fiber Canvas with @remotion/three's ThreeCanvas.
 */

import React, { useMemo, useRef } from "react";
import { ThreeCanvas } from "@remotion/three";
import { useCurrentFrame, useVideoConfig } from "remotion";
import * as THREE from "three";
import { easeOutCubic, latLngToVector3 } from "../utils/timing";

interface Globe3DProps {
  /** Starting lat/lng for the camera. */
  startLat: number;
  startLng: number;
  /** Target lat/lng to fly to. */
  targetLat: number;
  targetLng: number;
  /** Site name to display as a pulsing dot. */
  siteName?: string;
}

/** Simple earth sphere with color gradient. */
const EarthSphere: React.FC = () => {
  return (
    <mesh>
      <sphereGeometry args={[1, 48, 48]} />
      <meshStandardMaterial
        color="#1a3a5c"
        roughness={0.8}
        metalness={0.1}
      />
    </mesh>
  );
};

/** Pulsing dot marker at a lat/lng position on the globe. */
const SiteDot: React.FC<{ lat: number; lng: number; pulse: number }> = ({
  lat,
  lng,
  pulse,
}) => {
  const [x, y, z] = latLngToVector3(lat, lng);
  const scale = 0.02 + pulse * 0.01;

  return (
    <mesh position={[x * 1.01, y * 1.01, z * 1.01]}>
      <sphereGeometry args={[scale, 16, 16]} />
      <meshBasicMaterial color="#c02023" />
    </mesh>
  );
};

export const Globe3D: React.FC<Globe3DProps> = ({
  startLat,
  startLng,
  targetLat,
  targetLng,
  siteName,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps, width, height } = useVideoConfig();

  const progress = Math.min(1, frame / durationInFrames);
  const eased = easeOutCubic(progress);

  // Camera distance (fixed, slight zoom during fly-to)
  const distance = 2.2 - eased * 0.3;

  // Spherical interpolation using quaternions (ported from useFlyToAnimation.ts)
  const cameraPosition = useMemo(() => {
    const startDir = new THREE.Vector3(...latLngToVector3(startLat, startLng)).normalize();
    const targetDir = new THREE.Vector3(...latLngToVector3(targetLat, targetLng)).normalize();

    const startQuat = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 0, 1),
      startDir,
    );
    const targetQuat = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 0, 1),
      targetDir,
    );

    const currentQuat = new THREE.Quaternion();
    currentQuat.slerpQuaternions(startQuat, targetQuat, eased);

    const currentDir = new THREE.Vector3(0, 0, 1).applyQuaternion(currentQuat);
    return currentDir.multiplyScalar(distance);
  }, [startLat, startLng, targetLat, targetLng, eased, distance]);

  // Pulse animation for the site dot
  const pulsePhase = Math.sin(frame * (Math.PI / fps) * 3);

  return (
    <ThreeCanvas
      width={width}
      height={height}
      camera={{
        fov: 60,
        position: [cameraPosition.x, cameraPosition.y, cameraPosition.z],
      }}
      style={{ backgroundColor: "#0a0a1a" }}
    >
      <ambientLight intensity={0.4} />
      <directionalLight position={[5, 3, 5]} intensity={0.8} />

      <EarthSphere />

      {/* Target site dot */}
      <SiteDot lat={targetLat} lng={targetLng} pulse={pulsePhase} />
    </ThreeCanvas>
  );
};
