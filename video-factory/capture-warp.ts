/**
 * Capture Globe Warp-In Animation
 *
 * Opens ancientnerds.com fresh and captures the full warp-in effect.
 * The warp takes ~3 seconds and scales globe from 0.3 to 1.0 with 180° rotation.
 */

import puppeteer from 'puppeteer';
import * as fs from 'fs';
import * as path from 'path';

const SITE_URL = 'https://ancientnerds.com';
const OUTPUT_DIR = path.join(__dirname, 'output', 'captures', '00_warp_in');
const FPS = 60;  // Higher FPS for smooth warp
const VIEWPORT = { width: 1920, height: 1080 };

// Ensure output directory exists
if (fs.existsSync(OUTPUT_DIR)) {
  fs.rmSync(OUTPUT_DIR, { recursive: true });
}
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

function log(msg: string) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

async function main() {
  log('Starting warp capture...');

  const browser = await puppeteer.launch({
    headless: false,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
      '--disable-gpu-vsync',  // Faster rendering
    ],
    defaultViewport: VIEWPORT,
  });

  const page = await browser.newPage();
  await page.setViewport(VIEWPORT);

  // Start capturing BEFORE navigation to catch everything
  log('Navigating to site...');

  // Navigate and wait for initial HTML only (not full load)
  await page.goto(SITE_URL, { waitUntil: 'domcontentloaded' });

  // Wait for canvas to appear (globe is rendering)
  log('Waiting for canvas...');
  await page.waitForSelector('canvas', { timeout: 30000 });

  // Small delay for WebGL context initialization
  await new Promise(r => setTimeout(r, 500));

  log('Starting frame capture (5 seconds at 60fps = 300 frames)...');

  const frames: string[] = [];
  const totalFrames = 5 * FPS;  // 5 seconds
  const frameInterval = 1000 / FPS;

  const startTime = Date.now();

  for (let i = 0; i < totalFrames; i++) {
    const framePath = path.join(OUTPUT_DIR, `frame_${String(i).padStart(5, '0')}.jpg`);
    await page.screenshot({ path: framePath, type: 'jpeg', quality: 95 });
    frames.push(framePath);

    if (i % 60 === 0) {
      log(`  Frame ${i}/${totalFrames} (${Math.round(i/totalFrames*100)}%)`);
    }

    // Wait for next frame
    const elapsed = Date.now() - startTime;
    const targetTime = (i + 1) * frameInterval;
    const waitTime = Math.max(0, targetTime - elapsed);
    if (waitTime > 0) {
      await new Promise(r => setTimeout(r, waitTime));
    }
  }

  const totalTime = Date.now() - startTime;
  log(`Captured ${frames.length} frames in ${(totalTime/1000).toFixed(1)}s`);
  log(`Output: ${OUTPUT_DIR}`);

  await browser.close();

  // Convert to video
  log('Converting to video...');
  const { execSync } = require('child_process');
  const outputVideo = path.join(__dirname, 'output', 'captures', 'warp_in.mp4');

  try {
    execSync(`ffmpeg -y -framerate ${FPS} -i "${OUTPUT_DIR}/frame_%05d.jpg" -c:v libx264 -pix_fmt yuv420p -crf 18 "${outputVideo}"`, {
      stdio: 'inherit'
    });
    log(`Video saved: ${outputVideo}`);
  } catch (e) {
    log('FFmpeg conversion failed - frames are still available');
  }
}

main().catch(console.error);
