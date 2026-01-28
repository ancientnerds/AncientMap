/**
 * Epic Discovery Teaser Composition
 *
 * 16:9 horizontal teaser - "Epic Discovery" style
 * No voiceover, no music - video/text only
 * Tagline: "Modern Tech for Ancient Mysteries"
 */

import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  Img,
  spring,
  Easing,
} from 'remotion';
import { BRAND, BACKGROUNDS, TEXT, FONTS, SHADOWS, RADIUS } from '../styles/theme';

// =============================================================================
// Configuration
// =============================================================================

const CONFIG = {
  width: 1920,
  height: 1080,
  fps: 30,
  durationInSeconds: 60,
};

const TOTAL_FRAMES = CONFIG.durationInSeconds * CONFIG.fps; // 1800 frames

// Convert seconds to frames
const sec = (s: number) => Math.round(s * CONFIG.fps);

// =============================================================================
// Shot Components
// =============================================================================

/** Shot 1: Logo Reveal (0-3s) */
const LogoReveal: React.FC<{ logoSrc?: string }> = ({ logoSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: 'clamp' });
  const scale = spring({ frame, fps, config: { damping: 12, stiffness: 80 } });
  const glowIntensity = interpolate(Math.sin(frame * 0.1), [-1, 1], [0.3, 0.7]);

  return (
    <AbsoluteFill style={{ backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' }}>
      <div
        style={{
          opacity,
          transform: `scale(${scale})`,
          textAlign: 'center',
          filter: `drop-shadow(0 0 ${40 * glowIntensity}px rgba(0, 180, 180, ${glowIntensity}))`,
        }}
      >
        {logoSrc ? (
          <Img src={logoSrc} style={{ width: 180, height: 180, marginBottom: 24 }} />
        ) : (
          <div
            style={{
              width: 140,
              height: 140,
              borderRadius: '50%',
              background: `linear-gradient(135deg, ${BRAND.gold} 0%, ${BRAND.primary} 100%)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 64,
              fontWeight: 900,
              color: '#fff',
              fontFamily: FONTS.heading,
              marginBottom: 24,
            }}
          >
            AN
          </div>
        )}
        <h1
          style={{
            fontSize: 96,
            fontWeight: 900,
            color: '#fff',
            fontFamily: FONTS.heading,
            letterSpacing: 12,
            margin: 0,
            textShadow: '0 4px 30px rgba(0,0,0,0.8)',
          }}
        >
          ANCIENT NERDS
        </h1>
      </div>
    </AbsoluteFill>
  );
};

/** Shot 2: Tagline (3-5s) */
const TaglineReveal: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: 'clamp' });
  const slideY = interpolate(frame, [0, 20], [30, 0], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ textAlign: 'center' }}>
        <h1
          style={{
            fontSize: 96,
            fontWeight: 900,
            color: '#fff',
            fontFamily: FONTS.heading,
            letterSpacing: 12,
            margin: 0,
            marginBottom: 24,
          }}
        >
          ANCIENT NERDS
        </h1>
        <p
          style={{
            opacity,
            transform: `translateY(${slideY}px)`,
            fontSize: 36,
            fontWeight: 400,
            color: BRAND.teal,
            fontFamily: FONTS.body,
            fontStyle: 'italic',
            margin: 0,
          }}
        >
          Modern Tech for Ancient Mysteries
        </p>
      </div>
    </AbsoluteFill>
  );
};

/** Shot 3: Globe Reveal with Sites Count (5-10s) */
const GlobeReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scaleIn = spring({ frame, fps, config: { damping: 15, stiffness: 60 } });
  const textOpacity = interpolate(frame, [60, 90], [0, 1], { extrapolateRight: 'clamp' });
  const countUp = interpolate(frame, [30, 120], [0, 800000], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* Globe placeholder - radial gradient */}
      <AbsoluteFill
        style={{
          transform: `scale(${scaleIn})`,
          background: 'radial-gradient(circle at 50% 50%, #0a1628 0%, #000 70%)',
        }}
      >
        {/* Simulated markers */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `radial-gradient(circle at 30% 40%, rgba(0, 180, 180, 0.4) 0%, transparent 20%),
                         radial-gradient(circle at 60% 35%, rgba(255, 215, 0, 0.3) 0%, transparent 15%),
                         radial-gradient(circle at 45% 55%, rgba(192, 32, 35, 0.3) 0%, transparent 18%),
                         radial-gradient(circle at 70% 60%, rgba(0, 180, 180, 0.3) 0%, transparent 12%)`,
            opacity: interpolate(frame, [30, 90], [0, 1], { extrapolateRight: 'clamp' }),
          }}
        />
      </AbsoluteFill>

      {/* Sites count overlay */}
      <div
        style={{
          position: 'absolute',
          bottom: 120,
          left: 0,
          right: 0,
          textAlign: 'center',
          opacity: textOpacity,
        }}
      >
        <span
          style={{
            fontSize: 84,
            fontWeight: 900,
            color: BRAND.gold,
            fontFamily: FONTS.heading,
            textShadow: SHADOWS.glowGold,
          }}
        >
          {Math.floor(countUp).toLocaleString()}+
        </span>
        <span
          style={{
            display: 'block',
            fontSize: 32,
            fontWeight: 500,
            color: '#fff',
            fontFamily: FONTS.body,
            textTransform: 'uppercase',
            letterSpacing: 4,
            marginTop: 8,
          }}
        >
          Archaeological Sites
        </span>
      </div>
    </AbsoluteFill>
  );
};

/** Site Fly-To Shot */
interface SiteFlyToProps {
  siteName: string;
  location: string;
  featured?: boolean;
}

const SiteFlyTo: React.FC<SiteFlyToProps> = ({ siteName, location, featured }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const zoomIn = interpolate(frame, [0, 60], [1, 1.15], {
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  const textOpacity = interpolate(frame, [20, 40], [0, 1], { extrapolateRight: 'clamp' });
  const textSlide = interpolate(frame, [20, 40], [40, 0], { extrapolateRight: 'clamp' });

  // Different background tints for each site
  const bgColor = featured ? 'rgba(192, 32, 35, 0.15)' : 'rgba(0, 180, 180, 0.1)';

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* Simulated fly-to background */}
      <AbsoluteFill
        style={{
          transform: `scale(${zoomIn})`,
          background: `radial-gradient(circle at 50% 50%, ${bgColor} 0%, #0a1628 50%, #000 100%)`,
        }}
      />

      {/* Vignette */}
      <AbsoluteFill
        style={{
          background: 'radial-gradient(circle, transparent 30%, rgba(0,0,0,0.7) 100%)',
        }}
      />

      {/* Site name overlay */}
      <div
        style={{
          position: 'absolute',
          bottom: 100,
          left: 80,
          opacity: textOpacity,
          transform: `translateY(${textSlide}px)`,
        }}
      >
        {featured && (
          <span
            style={{
              display: 'inline-block',
              padding: '8px 20px',
              background: 'rgba(192, 32, 35, 0.3)',
              border: '1px solid #c02023',
              borderRadius: 9999,
              color: '#c02023',
              fontSize: 16,
              fontWeight: 600,
              fontFamily: FONTS.body,
              textTransform: 'uppercase',
              letterSpacing: 2,
              marginBottom: 16,
            }}
          >
            Featured Site
          </span>
        )}
        <h2
          style={{
            fontSize: 72,
            fontWeight: 700,
            color: '#fff',
            fontFamily: FONTS.heading,
            margin: 0,
            textShadow: '0 4px 20px rgba(0,0,0,0.8)',
          }}
        >
          {siteName}
        </h2>
        <p
          style={{
            fontSize: 28,
            fontWeight: 400,
            color: 'rgba(255,255,255,0.8)',
            fontFamily: FONTS.body,
            margin: 0,
            marginTop: 8,
          }}
        >
          {location}
        </p>
      </div>
    </AbsoluteFill>
  );
};

/** Feature Demo Shot */
interface FeatureDemoProps {
  title: string;
  description?: string;
}

const FeatureDemo: React.FC<FeatureDemoProps> = ({ title, description }) => {
  const frame = useCurrentFrame();

  const titleOpacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: 'clamp' });
  const barWidth = interpolate(frame, [20, 80], [0, 300], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* Background */}
      <AbsoluteFill
        style={{
          background: 'linear-gradient(135deg, rgba(0, 180, 180, 0.1) 0%, rgba(0,0,0,0) 50%)',
        }}
      />

      {/* Simulated UI element */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center',
        }}
      >
        <h2
          style={{
            opacity: titleOpacity,
            fontSize: 64,
            fontWeight: 700,
            color: '#fff',
            fontFamily: FONTS.heading,
            margin: 0,
            marginBottom: 32,
          }}
        >
          {title}
        </h2>

        {/* Animated bar (simulating UI interaction) */}
        <div
          style={{
            width: 400,
            height: 8,
            background: 'rgba(255,255,255,0.2)',
            borderRadius: 4,
            margin: '0 auto',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: barWidth,
              height: '100%',
              background: `linear-gradient(90deg, ${BRAND.teal}, ${BRAND.gold})`,
              borderRadius: 4,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Popup Demo Shot */
const PopupDemo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const popupScale = spring({ frame: frame - 30, fps, config: { damping: 12, stiffness: 100 } });
  const popupOpacity = interpolate(frame, [30, 50], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* Background */}
      <AbsoluteFill
        style={{
          background: 'radial-gradient(circle at 50% 50%, #0a1628 0%, #000 70%)',
        }}
      />

      {/* Simulated popup */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: `translate(-50%, -50%) scale(${Math.max(0, popupScale)})`,
          opacity: popupOpacity,
          width: 500,
          background: 'rgba(0, 20, 25, 0.95)',
          border: '1px solid rgba(0, 180, 180, 0.3)',
          borderRadius: 16,
          padding: 32,
          boxShadow: '0 20px 60px rgba(0,0,0,0.8)',
        }}
      >
        {/* Popup header */}
        <h3
          style={{
            fontSize: 36,
            fontWeight: 700,
            color: '#fff',
            fontFamily: FONTS.heading,
            margin: 0,
            marginBottom: 8,
          }}
        >
          Machu Picchu
        </h3>
        <p
          style={{
            fontSize: 18,
            color: BRAND.teal,
            fontFamily: FONTS.body,
            margin: 0,
            marginBottom: 16,
          }}
        >
          Peru • 15th Century
        </p>

        {/* Fake image placeholder */}
        <div
          style={{
            width: '100%',
            height: 200,
            background: 'linear-gradient(135deg, rgba(0,180,180,0.2), rgba(192,32,35,0.2))',
            borderRadius: 8,
            marginBottom: 16,
          }}
        />

        {/* Fake description */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[80, 100, 60].map((width, i) => (
            <div
              key={i}
              style={{
                width: `${width}%`,
                height: 12,
                background: 'rgba(255,255,255,0.15)',
                borderRadius: 4,
              }}
            />
          ))}
        </div>
      </div>

      {/* Title overlay */}
      <div
        style={{
          position: 'absolute',
          bottom: 80,
          left: 0,
          right: 0,
          textAlign: 'center',
          opacity: interpolate(frame, [60, 80], [0, 1], { extrapolateRight: 'clamp' }),
        }}
      >
        <span
          style={{
            fontSize: 48,
            fontWeight: 600,
            color: '#fff',
            fontFamily: FONTS.heading,
          }}
        >
          Rich Details & Images
        </span>
      </div>
    </AbsoluteFill>
  );
};

/** Stats Counter Shot */
const StatsCounter: React.FC = () => {
  const frame = useCurrentFrame();

  const stats = [
    { value: 800000, suffix: '+', label: 'Sites' },
    { value: 50, suffix: '+', label: 'Categories' },
    { value: 200, suffix: '+', label: 'Countries' },
  ];

  return (
    <AbsoluteFill style={{ backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' }}>
      {/* Background */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'radial-gradient(circle at 50% 50%, rgba(0, 180, 180, 0.1) 0%, transparent 60%)',
        }}
      />

      {/* Stats grid */}
      <div style={{ display: 'flex', gap: 120 }}>
        {stats.map((stat, index) => {
          const delay = index * 20;
          const opacity = interpolate(frame, [delay, delay + 20], [0, 1], { extrapolateRight: 'clamp' });
          const scale = interpolate(frame, [delay, delay + 20], [0.8, 1], { extrapolateRight: 'clamp' });
          const countProgress = interpolate(frame, [delay, delay + 60], [0, 1], { extrapolateRight: 'clamp' });
          const displayValue = Math.floor(stat.value * countProgress);

          return (
            <div
              key={stat.label}
              style={{
                opacity,
                transform: `scale(${scale})`,
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  fontSize: 84,
                  fontWeight: 900,
                  color: BRAND.gold,
                  fontFamily: FONTS.heading,
                  textShadow: SHADOWS.glowGold,
                }}
              >
                {displayValue.toLocaleString()}{stat.suffix}
              </div>
              <div
                style={{
                  fontSize: 24,
                  fontWeight: 500,
                  color: 'rgba(255,255,255,0.7)',
                  fontFamily: FONTS.body,
                  textTransform: 'uppercase',
                  letterSpacing: 3,
                  marginTop: 8,
                }}
              >
                {stat.label}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** Explore History Shot */
const ExploreHistory: React.FC = () => {
  const frame = useCurrentFrame();

  const textOpacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: 'clamp' });
  const glowPulse = interpolate(Math.sin(frame * 0.08), [-1, 1], [0.3, 0.6]);
  const rotation = interpolate(frame, [0, 210], [0, 15], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* Slowly rotating globe background */}
      <AbsoluteFill
        style={{
          transform: `rotate(${rotation}deg)`,
          background: `radial-gradient(circle at 50% 50%, #0a1628 0%, #000 70%)`,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `radial-gradient(circle at 30% 40%, rgba(0, 180, 180, 0.3) 0%, transparent 25%),
                         radial-gradient(circle at 65% 55%, rgba(255, 215, 0, 0.2) 0%, transparent 20%)`,
          }}
        />
      </AbsoluteFill>

      {/* Text */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center',
          opacity: textOpacity,
        }}
      >
        <h2
          style={{
            fontSize: 96,
            fontWeight: 700,
            color: '#fff',
            fontFamily: FONTS.heading,
            margin: 0,
            textShadow: `0 0 ${60 * glowPulse}px rgba(0, 180, 180, ${glowPulse})`,
          }}
        >
          Explore History
        </h2>
      </div>
    </AbsoluteFill>
  );
};

/** Outro CTA Shot */
const OutroCTA: React.FC<{ logoSrc?: string }> = ({ logoSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({ frame, fps, config: { damping: 12, stiffness: 80 } });
  const glowPulse = interpolate(Math.sin(frame * 0.12), [-1, 1], [0.4, 0.8]);

  return (
    <AbsoluteFill style={{ backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' }}>
      {/* Background glow */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(circle at 50% 50%, rgba(192, 32, 35, 0.2) 0%, transparent 50%)`,
        }}
      />

      <div
        style={{
          transform: `scale(${scale})`,
          textAlign: 'center',
        }}
      >
        {logoSrc && (
          <Img src={logoSrc} style={{ width: 100, height: 100, marginBottom: 24 }} />
        )}
        <h2
          style={{
            fontSize: 72,
            fontWeight: 700,
            color: BRAND.teal,
            fontFamily: FONTS.mono,
            margin: 0,
            textShadow: `0 0 ${40 * glowPulse}px rgba(0, 180, 180, ${glowPulse})`,
          }}
        >
          ancientnerds.com
        </h2>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Main Composition
// =============================================================================

export interface EpicDiscoveryTeaserProps {
  logoSrc?: string;
}

export const EpicDiscoveryTeaser: React.FC<EpicDiscoveryTeaserProps> = ({ logoSrc }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* Shot 1: Logo Reveal (0-3s) */}
      <Sequence from={sec(0)} durationInFrames={sec(3)}>
        <LogoReveal logoSrc={logoSrc} />
      </Sequence>

      {/* Shot 2: Tagline (3-5s) */}
      <Sequence from={sec(3)} durationInFrames={sec(2)}>
        <TaglineReveal />
      </Sequence>

      {/* Shot 3: Globe Reveal (5-10s) */}
      <Sequence from={sec(5)} durationInFrames={sec(5)}>
        <GlobeReveal />
      </Sequence>

      {/* Shot 4: Fly to Giza (10-14s) */}
      <Sequence from={sec(10)} durationInFrames={sec(4)}>
        <SiteFlyTo siteName="Pyramids of Giza" location="Egypt" />
      </Sequence>

      {/* Shot 5: Fly to Machu Picchu - FEATURED (14-18s) */}
      <Sequence from={sec(14)} durationInFrames={sec(4)}>
        <SiteFlyTo siteName="Machu Picchu" location="Peru" featured />
      </Sequence>

      {/* Shot 6: Fly to Stonehenge (18-22s) */}
      <Sequence from={sec(18)} durationInFrames={sec(4)}>
        <SiteFlyTo siteName="Stonehenge" location="England" />
      </Sequence>

      {/* Shot 7: Filter Demo (22-28s) */}
      <Sequence from={sec(22)} durationInFrames={sec(6)}>
        <FeatureDemo title="Filter by Type" />
      </Sequence>

      {/* Shot 8: Search Demo (28-34s) */}
      <Sequence from={sec(28)} durationInFrames={sec(6)}>
        <FeatureDemo title="Search Any Site" />
      </Sequence>

      {/* Shot 9: Popup Demo (34-40s) */}
      <Sequence from={sec(34)} durationInFrames={sec(6)}>
        <PopupDemo />
      </Sequence>

      {/* Shot 10: Stats Counter (40-48s) */}
      <Sequence from={sec(40)} durationInFrames={sec(8)}>
        <StatsCounter />
      </Sequence>

      {/* Shot 11: Explore History (48-55s) */}
      <Sequence from={sec(48)} durationInFrames={sec(7)}>
        <ExploreHistory />
      </Sequence>

      {/* Shot 12: Outro CTA (55-60s) */}
      <Sequence from={sec(55)} durationInFrames={sec(5)}>
        <OutroCTA logoSrc={logoSrc} />
      </Sequence>
    </AbsoluteFill>
  );
};

// =============================================================================
// Export Configuration
// =============================================================================

export const epicDiscoveryTeaserConfig = {
  id: 'EpicDiscoveryTeaser',
  component: EpicDiscoveryTeaser,
  durationInFrames: TOTAL_FRAMES,
  fps: CONFIG.fps,
  width: CONFIG.width,
  height: CONFIG.height,
};

export default EpicDiscoveryTeaser;
