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
/**
 * Page bindings survive reloads but cannot be exposed twice on the same page
 * (Puppeteer throws "already exists"). Bind once per page here and route the
 * chunks to whichever recorder is active — each scene creates a fresh one.
 */
let activeRecorder: StreamRecorder | null = null

/** Frames per page.evaluate() in capture(); keeps each call well under the protocol timeout. */
const CAPTURE_CHUNK_FRAMES = 60

export async function bindRecorderFunctions(page: Page): Promise<void> {
  await page.exposeFunction('__saveVideoChunk', (base64: string) => {
    activeRecorder?.pushChunk(base64)
  })
  await page.exposeFunction('__logProgress', (msg: string) => {
    process.stdout.write(msg)
  })
}

export class StreamRecorder {
  private readonly fps: number
  private readonly canvasSelector: string
  private readonly frameYieldMs: number
  private readonly waitForTiles: boolean
  private chunks: Buffer[] = []
  private frameCount = 0

  constructor(options: { fps?: number; canvasSelector?: string; frameYieldMs?: number; waitForTiles?: boolean }) {
    this.fps = options.fps ?? 24
    // Three.js canvas by default; Mapbox scenes record `.mapbox-globe-container canvas`.
    this.canvasSelector = options.canvasSelector ?? '.globe-container canvas'
    // Wall-clock pause after each requestFrame() so the VP8 encoder drains.
    // Synthetic time makes this free for the animation; 0 ms dropped 60 % of
    // 1080×1920 frames (36/97, Machu Picchu approach, 2026-09-16).
    this.frameYieldMs = options.frameYieldMs ?? 0
    // Mapbox scenes: poll window.__DEMO.mapboxTilesLoaded() before each frame.
    // A zoom path outruns tile loading otherwise, and zoom-outs have no finer
    // tiles to fall back on (grey patches, Machu Picchu return flight).
    this.waitForTiles = options.waitForTiles ?? false
  }

  private started = false

  /**
   * Start the MediaRecorder in the browser. Chrome emits one frame of the
   * current canvas the moment recording starts, so `capture()` starts lazily:
   * the first recorded frame is then the scene's first real frame, not the
   * globe as it looked before the scene's setup ran.
   */
  async start(page: Page): Promise<void> {
    this.chunks = []
    this.frameCount = 0
    this.started = true
    activeRecorder = this

    // Find the WebGL canvas and start captureStream + MediaRecorder
    await page.evaluate(`(function() {
      var canvas = document.querySelector(${JSON.stringify(this.canvasSelector)});
      if (!canvas) throw new Error('No canvas found for ' + ${JSON.stringify(this.canvasSelector)});

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
    if (!this.started) await this.start(page)
    const totalFrames = Math.ceil(durationSec * this.fps)
    const startFrame = this.frameCount

    console.log(`  Capturing ${totalFrames} frames (${durationSec}s @ ${this.fps}fps)...`)

    // The frame loop runs inside the browser (no per-frame CDP round-trips),
    // but in chunks: with per-frame tile waits one evaluate() for a whole
    // 6 s take exceeded Puppeteer's protocol timeout.
    let tileWaits = 0
    for (let first = 0; first < totalFrames; first += CAPTURE_CHUNK_FRAMES) {
      const count = Math.min(CAPTURE_CHUNK_FRAMES, totalFrames - first)
      tileWaits += await page.evaluate(`(async function() {
      var totalFrames = ${totalFrames};
      var startFrame = ${startFrame};
      var first = ${first};
      var count = ${count};
      var tileWaits = 0;
      var stream = window.__captureStream;
      var videoTrack = stream.getVideoTracks()[0];

      for (var i = first; i < first + count; i++) {
        // 1. Advance synthetic time by one frame interval
        window.__tickFrame();

        // 2. Double-RAF: first flushes Three.js render, second flushes React updates
        await new Promise(function(r) {
          requestAnimationFrame(function() { requestAnimationFrame(r); });
        });

        // 2b. Mapbox scenes: hold this frame until its tiles are in, then let the
        // map draw them before the frame is sampled. setTimeout is wall-clock.
        if (${this.waitForTiles}) {
          var polls = 0;
          while (polls < 400 && !(window.__DEMO && window.__DEMO.mapboxTilesLoaded && window.__DEMO.mapboxTilesLoaded())) {
            await new Promise(function(r) { setTimeout(r, 25); });
            polls++;
          }
          if (polls > 0) {
            tileWaits++;
            await new Promise(function(r) {
              requestAnimationFrame(function() { requestAnimationFrame(r); });
            });
          }
        }

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
        await new Promise(function(r) { setTimeout(r, ${this.frameYieldMs}); });

        // Progress logging every 30 frames
        if ((i + 1) % 30 === 0 || i === totalFrames - 1) {
          var pct = Math.round(((i + 1) / totalFrames) * 100);
          var globalFrame = startFrame + i + 1;
          window.__logProgress('\\r  Segment progress: ' + pct + '% (' + (i + 1) + '/' + totalFrames + ') | Total frames: ' + globalFrame);
        }
      }
      return tileWaits;
    })()`) as number
    }
    if (this.waitForTiles) console.log(`\n  Frames that waited for tiles: ${tileWaits}/${totalFrames}`)

    this.frameCount += totalFrames
    console.log('')
  }

  /** Receive one base64 WebM chunk from the page binding. */
  pushChunk(base64: string): void {
    this.chunks.push(Buffer.from(base64, 'base64'))
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
