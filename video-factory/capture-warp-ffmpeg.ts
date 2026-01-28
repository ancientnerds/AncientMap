/**
 * Capture Globe Warp-In using FFmpeg Desktop Capture
 *
 * Opens browser, then uses ffmpeg gdigrab to record the screen.
 * No flickering since it's actual screen recording.
 */

import puppeteer from 'puppeteer';
import { spawn, execSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

const SITE_URL = 'https://ancientnerds.com';
const OUTPUT_DIR = path.join(__dirname, 'output', 'captures');
const VIEWPORT = { width: 1920, height: 1080 };

function log(msg: string) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms));
}

async function main() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const outputVideo = path.join(OUTPUT_DIR, 'warp_in_screen.mp4');

  log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: false,
    args: [
      '--no-sandbox',
      `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
      '--window-position=0,0',
    ],
    defaultViewport: VIEWPORT,
  });

  const page = await browser.newPage();

  // Start ffmpeg screen recording BEFORE navigating
  log('Starting screen recording...');
  const ffmpeg = spawn('ffmpeg', [
    '-y',
    '-f', 'gdigrab',           // Windows screen capture
    '-framerate', '60',
    '-offset_x', '0',
    '-offset_y', '0',
    '-video_size', `${VIEWPORT.width}x${VIEWPORT.height}`,
    '-i', 'desktop',
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-crf', '18',
    '-t', '10',                // Record for 10 seconds
    outputVideo
  ], {
    stdio: ['pipe', 'inherit', 'inherit']
  });

  // Small delay to ensure ffmpeg starts
  await sleep(500);

  log('Navigating to site...');
  await page.goto(SITE_URL, { waitUntil: 'domcontentloaded' });

  // Wait for recording to complete
  await new Promise<void>((resolve, reject) => {
    ffmpeg.on('close', (code) => {
      if (code === 0) {
        log('Recording complete!');
        resolve();
      } else {
        reject(new Error(`FFmpeg exited with code ${code}`));
      }
    });
  });

  await browser.close();
  log(`Video saved: ${outputVideo}`);
}

main().catch(console.error);
