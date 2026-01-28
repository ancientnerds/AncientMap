/**
 * Globe rotation capture action
 *
 * Smoothly rotates the globe for cinematic captures.
 */

import { Page } from 'puppeteer';

// =============================================================================
// Types
// =============================================================================

export interface RotateOptions {
  duration?: number;        // Total rotation duration in ms
  degrees?: number;         // Degrees to rotate
  direction?: 'cw' | 'ccw'; // Clockwise or counter-clockwise
  easing?: 'linear' | 'ease-in-out' | 'ease-in' | 'ease-out';
}

// =============================================================================
// Default Configuration
// =============================================================================

const DEFAULT_OPTIONS: RotateOptions = {
  duration: 5000,
  degrees: 360,
  direction: 'cw',
  easing: 'linear',
};

// =============================================================================
// Rotate Action
// =============================================================================

/**
 * Rotate the globe smoothly
 */
export async function rotateGlobe(
  page: Page,
  options: RotateOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const rotationDegrees = opts.direction === 'ccw' ? -opts.degrees! : opts.degrees!;

  console.log(`Starting globe rotation: ${rotationDegrees}° over ${opts.duration}ms`);

  // Execute rotation animation
  await page.evaluate(
    ({ degrees, duration, easing }) => {
      const map = (window as any).map || (window as any).mapboxMap;

      if (!map || typeof map.getBearing !== 'function') {
        console.warn('No compatible map found for rotation');
        return;
      }

      const startBearing = map.getBearing();
      const endBearing = startBearing + degrees;

      // Rotate using bearing animation
      map.rotateTo(endBearing, {
        duration: duration,
        easing: (t: number) => {
          switch (easing) {
            case 'ease-in-out':
              return t < 0.5
                ? 2 * t * t
                : 1 - Math.pow(-2 * t + 2, 2) / 2;
            case 'ease-in':
              return t * t;
            case 'ease-out':
              return 1 - (1 - t) * (1 - t);
            default:
              return t; // linear
          }
        },
      });
    },
    { degrees: rotationDegrees, duration: opts.duration, easing: opts.easing }
  );

  // Wait for rotation to complete
  await page.waitForTimeout(opts.duration!);

  console.log('Globe rotation complete.');
}

/**
 * Perform a slow pan rotation (orbit) around current view
 */
export async function orbitView(
  page: Page,
  durationSeconds: number = 10
): Promise<void> {
  const duration = durationSeconds * 1000;

  console.log(`Starting orbit view for ${durationSeconds}s`);

  await page.evaluate((duration) => {
    const map = (window as any).map || (window as any).mapboxMap;

    if (!map) {
      console.warn('No map found for orbit');
      return;
    }

    const startBearing = map.getBearing();
    const startTime = Date.now();

    function animate() {
      const elapsed = Date.now() - startTime;
      const progress = elapsed / duration;

      if (progress < 1) {
        const bearing = startBearing + progress * 360;
        map.setBearing(bearing);
        requestAnimationFrame(animate);
      }
    }

    animate();
  }, duration);

  await page.waitForTimeout(duration);

  console.log('Orbit complete.');
}

/**
 * Tilt the globe view (change pitch)
 */
export async function tiltView(
  page: Page,
  targetPitch: number = 45,
  duration: number = 2000
): Promise<void> {
  console.log(`Tilting view to ${targetPitch}° pitch`);

  await page.evaluate(
    ({ pitch, duration }) => {
      const map = (window as any).map || (window as any).mapboxMap;

      if (!map || typeof map.easeTo !== 'function') {
        console.warn('No compatible map found for tilt');
        return;
      }

      map.easeTo({
        pitch: pitch,
        duration: duration,
      });
    },
    { pitch: targetPitch, duration }
  );

  await page.waitForTimeout(duration);

  console.log('Tilt complete.');
}

// =============================================================================
// Export
// =============================================================================

export default rotateGlobe;
