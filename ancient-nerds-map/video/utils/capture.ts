/**
 * Stream-based capture utility for Puppeteer-based video recording.
 *
 * Uses canvas.captureStream(0) + MediaRecorder to record directly from the
 * WebGL canvas buffer. This avoids per-frame CDP screenshot round-trips and
 * compositor races that caused flicker with the old FrameRecorder approach.
 *
 * Synthetic time control is still used for deterministic animations:
 *  - performance.now() and Date.now() are frozen and advanced by exactly
 *    1000/fps ms per frame.
 *  - Double-RAF before each requestFrame() ensures Three.js renders are complete.
 */

import { writeFileSync } from 'fs'
import type { Page } from 'puppeteer'

/**
 * Inject synthetic time control into the page.
 * Must be called AFTER the globe is fully loaded and ready,
 * but BEFORE any recording starts.
 *
 * Freezes performance.now() and Date.now() at their current values.
 * Call window.__tickFrame() to advance by exactly 1000/fps ms.
 */
export async function injectTimeControl(page: Page, fps: number): Promise<void> {
  await page.evaluate(`(function() {
    var frameInterval = ${1000 / fps};
    var syntheticPerfTime = performance.now();
    var baseDateNow = Date.now();
    var basePerfNow = syntheticPerfTime;

    // Override performance.now to return synthetic time
    var _origPerfNow = performance.now.bind(performance);
    performance.now = function() { return syntheticPerfTime; };

    // Override Date.now to advance in sync with performance.now.
    // Note: we don't override the Date constructor — sun position uses
    // new Date() but moves so slowly (~0.25 per minute) that wall-clock
    // time is fine. Only performance.now deltaTime matters for flicker.
    var _origDateNow = Date.now;
    Date.now = function() {
      return baseDateNow + (syntheticPerfTime - basePerfNow);
    };

    // Advance synthetic time by one frame interval
    window.__tickFrame = function() {
      syntheticPerfTime += frameInterval;
    };

    console.log('[TimeControl] Injected. Frame interval: ' + frameInterval.toFixed(2) + 'ms (' + ${fps} + ' fps)');
  })()`)
}

/**
 * Records video directly from the WebGL canvas using captureStream + MediaRecorder.
 * Eliminates per-frame CDP screenshots — Chrome encodes VP9 in a background thread.
 */
export class StreamRecorder {
  private readonly fps: number
  private chunks: Buffer[] = []
  private frameCount = 0

  constructor(options: { fps?: number }) {
    this.fps = options.fps ?? 24
  }

  /**
   * Start the MediaRecorder in the browser.
   * Exposes a Node function to receive WebM chunks from the page.
   */
  async start(page: Page): Promise<void> {
    this.chunks = []
    this.frameCount = 0

    // Expose function to receive binary chunks from the browser
    await page.exposeFunction('__saveVideoChunk', (base64: string) => {
      this.chunks.push(Buffer.from(base64, 'base64'))
    })

    // Expose function for progress logging from browser context
    await page.exposeFunction('__logProgress', (msg: string) => {
      process.stdout.write(msg)
    })

    // Find the WebGL canvas and start captureStream + MediaRecorder
    await page.evaluate(`(function() {
      var canvas = document.querySelector('.globe-container canvas');
      if (!canvas) throw new Error('No canvas found in .globe-container');

      // captureStream(0) = manual frame requests only (no automatic capture)
      var stream = canvas.captureStream(0);
      window.__captureStream = stream;

      // VP8 is much faster to encode than VP9, preventing frame drops
      // when the encoder can't keep up with capture speed. Quality loss
      // is irrelevant since we re-encode to H.264 anyway.
      var recorder = new MediaRecorder(stream, {
        mimeType: 'video/webm;codecs=vp8',
        videoBitsPerSecond: 20_000_000,
      });

      recorder.ondataavailable = function(e) {
        if (e.data && e.data.size > 0) {
          // Convert blob to base64 and send to Node
          var reader = new FileReader();
          reader.onloadend = function() {
            var base64 = reader.result.split(',')[1];
            window.__saveVideoChunk(base64);
          };
          reader.readAsDataURL(e.data);
        }
      };

      // Start recording with 1-second timeslice for periodic chunk delivery
      recorder.start(1000);
      window.__mediaRecorder = recorder;

      console.log('[StreamRecorder] Started. VP8 @ 20 Mbps');
    })()`)
  }

  /**
   * Capture frames for a given duration.
   * Runs a batched loop inside page.evaluate — ticks synthetic time,
   * double-RAFs for render, then requests a stream frame.
   */
  async capture(page: Page, durationSec: number): Promise<void> {
    const totalFrames = Math.ceil(durationSec * this.fps)
    const startFrame = this.frameCount

    console.log(`  Capturing ${totalFrames} frames (${durationSec}s @ ${this.fps}fps)...`)

    // Run the frame loop inside the browser to avoid per-frame CDP round-trips
    await page.evaluate(`(async function() {
      var totalFrames = ${totalFrames};
      var startFrame = ${startFrame};
      var stream = window.__captureStream;
      var videoTrack = stream.getVideoTracks()[0];

      for (var i = 0; i < totalFrames; i++) {
        // 1. Advance synthetic time by one frame interval
        window.__tickFrame();

        // 2. Double-RAF: first flushes Three.js render, second flushes React updates
        await new Promise(function(r) {
          requestAnimationFrame(function() { requestAnimationFrame(r); });
        });

        // 3. Request a frame from the capture stream
        if (videoTrack.requestFrame) {
          videoTrack.requestFrame();
        } else {
          // Fallback for older Chrome: use canvas-level requestFrame
          stream.requestFrame();
        }

        // 4. Yield to event loop so the VP8 encoder can process the frame.
        // Without this, requestFrame() calls pile up faster than the
        // encoder can handle, causing frame drops in the WebM.
        await new Promise(function(r) { setTimeout(r, 0); });

        // Progress logging every 30 frames
        if ((i + 1) % 30 === 0 || i === totalFrames - 1) {
          var pct = Math.round(((i + 1) / totalFrames) * 100);
          var globalFrame = startFrame + i + 1;
          window.__logProgress('\\r  Segment progress: ' + pct + '% (' + (i + 1) + '/' + totalFrames + ') | Total frames: ' + globalFrame);
        }
      }
    })()`)

    this.frameCount += totalFrames
    console.log('')
  }

  /**
   * Stop the MediaRecorder and write the WebM file to disk.
   */
  async stop(page: Page, outputPath: string): Promise<void> {
    // Stop the recorder and wait for the final dataavailable event
    await page.evaluate(`new Promise(function(resolve) {
      var recorder = window.__mediaRecorder;
      recorder.onstop = function() {
        // Small delay to ensure the last ondataavailable fires
        setTimeout(resolve, 500);
      };
      recorder.stop();
    })`)

    // Give a moment for the last chunk transfer to complete
    await new Promise(r => setTimeout(r, 1000))

    // Concatenate all chunks and write to disk
    const webm = Buffer.concat(this.chunks)
    writeFileSync(outputPath, webm)

    console.log(`  WebM saved: ${outputPath} (${(webm.length / 1024 / 1024).toFixed(1)} MB, ${this.frameCount} frames)`)

    // Clean up browser-side globals
    await page.evaluate(`(function() {
      delete window.__captureStream;
      delete window.__mediaRecorder;
    })()`)
  }

  /** Total frames captured so far */
  get totalFrames(): number {
    return this.frameCount
  }
}
