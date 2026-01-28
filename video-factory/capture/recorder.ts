/**
 * Screen capture wrapper for video recording
 *
 * Captures frames from Puppeteer for use in Remotion compositions.
 */

import { Page } from 'puppeteer';
import * as fs from 'fs';
import * as path from 'path';

// =============================================================================
// Configuration
// =============================================================================

export interface RecorderConfig {
  outputDir: string;
  fps: number;
  quality: number;
  format: 'png' | 'jpeg';
}

const DEFAULT_CONFIG: RecorderConfig = {
  outputDir: './output/frames',
  fps: 30,
  quality: 90,
  format: 'jpeg',
};

// =============================================================================
// Frame Recorder Class
// =============================================================================

export class FrameRecorder {
  private page: Page;
  private config: RecorderConfig;
  private frameCount: number = 0;
  private isRecording: boolean = false;
  private sessionDir: string = '';

  constructor(page: Page, config: Partial<RecorderConfig> = {}) {
    this.page = page;
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Initialize recording session
   */
  async startSession(sessionName: string): Promise<string> {
    this.sessionDir = path.join(this.config.outputDir, sessionName);

    // Create output directory
    if (!fs.existsSync(this.sessionDir)) {
      fs.mkdirSync(this.sessionDir, { recursive: true });
    }

    this.frameCount = 0;
    this.isRecording = true;

    console.log(`Recording session started: ${this.sessionDir}`);
    return this.sessionDir;
  }

  /**
   * Capture a single frame
   */
  async captureFrame(): Promise<string> {
    if (!this.isRecording) {
      throw new Error('Recording not started. Call startSession() first.');
    }

    const frameName = `frame_${String(this.frameCount).padStart(6, '0')}.${this.config.format}`;
    const framePath = path.join(this.sessionDir, frameName);

    await this.page.screenshot({
      path: framePath,
      type: this.config.format,
      quality: this.config.format === 'jpeg' ? this.config.quality : undefined,
    });

    this.frameCount++;
    return framePath;
  }

  /**
   * Capture frames for a specified duration
   */
  async captureFrames(durationSeconds: number): Promise<string[]> {
    const totalFrames = Math.ceil(durationSeconds * this.config.fps);
    const frameInterval = 1000 / this.config.fps;
    const frames: string[] = [];

    console.log(`Capturing ${totalFrames} frames at ${this.config.fps} fps...`);

    for (let i = 0; i < totalFrames; i++) {
      const framePath = await this.captureFrame();
      frames.push(framePath);

      // Wait for next frame
      await new Promise((resolve) => setTimeout(resolve, frameInterval));

      // Progress logging
      if (i % 30 === 0) {
        console.log(`Progress: ${i}/${totalFrames} frames (${Math.round((i / totalFrames) * 100)}%)`);
      }
    }

    console.log(`Captured ${frames.length} frames.`);
    return frames;
  }

  /**
   * Capture frames while executing an action
   */
  async captureWithAction(
    action: () => Promise<void>,
    maxDurationSeconds: number = 10
  ): Promise<string[]> {
    const frames: string[] = [];
    const frameInterval = 1000 / this.config.fps;
    const maxFrames = Math.ceil(maxDurationSeconds * this.config.fps);
    let actionComplete = false;

    // Start action
    const actionPromise = action().then(() => {
      actionComplete = true;
    });

    // Capture frames while action runs
    let frameIndex = 0;
    while (!actionComplete && frameIndex < maxFrames) {
      const framePath = await this.captureFrame();
      frames.push(framePath);
      await new Promise((resolve) => setTimeout(resolve, frameInterval));
      frameIndex++;
    }

    // Wait for action to complete
    await actionPromise;

    return frames;
  }

  /**
   * Stop recording session
   */
  stopSession(): { sessionDir: string; frameCount: number } {
    this.isRecording = false;
    const result = {
      sessionDir: this.sessionDir,
      frameCount: this.frameCount,
    };

    console.log(`Recording session ended. ${this.frameCount} frames captured.`);
    return result;
  }

  /**
   * Get frame paths for a session
   */
  getFramePaths(): string[] {
    if (!this.sessionDir || !fs.existsSync(this.sessionDir)) {
      return [];
    }

    return fs.readdirSync(this.sessionDir)
      .filter((file) => file.startsWith('frame_'))
      .sort()
      .map((file) => path.join(this.sessionDir, file));
  }

  /**
   * Clean up session frames
   */
  cleanupSession(): void {
    if (this.sessionDir && fs.existsSync(this.sessionDir)) {
      fs.rmSync(this.sessionDir, { recursive: true });
      console.log(`Cleaned up session: ${this.sessionDir}`);
    }
  }
}

// =============================================================================
// Factory Function
// =============================================================================

/**
 * Create a frame recorder for a page
 */
export function createRecorder(page: Page, config?: Partial<RecorderConfig>): FrameRecorder {
  return new FrameRecorder(page, config);
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Get duration of captured frames
 */
export function getFramesDuration(frameCount: number, fps: number = 30): number {
  return frameCount / fps;
}

/**
 * Calculate frame count for duration
 */
export function getFrameCount(durationSeconds: number, fps: number = 30): number {
  return Math.ceil(durationSeconds * fps);
}
