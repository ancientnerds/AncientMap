/**
 * Capture Globe Warp-In Animation v2
 *
 * Waits for splash screen to close, then captures the warp animation.
 */

import puppeteer from 'puppeteer';
import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';

const SITE_URL = 'https://ancientnerds.com';
const OUTPUT_DIR = path.join(__dirname, 'output', 'captures', '00_warp_in');
const FPS = 60;
const VIEWPORT = { width: 1920, height: 1080 };

if (fs.existsSync(OUTPUT_DIR)) {
  fs.rmSync(OUTPUT_DIR, { recursive: true });
}
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

function log(msg: string) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

async function main() {
  log('Starting warp capture v2...');

  const browser = await puppeteer.launch({
    headless: false,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
    ],
    defaultViewport: VIEWPORT,
  });

  const page = await browser.newPage();
  await page.setViewport(VIEWPORT);

  log('Navigating to site...');
  await page.goto(SITE_URL, { waitUntil: 'networkidle2', timeout: 60000 });

  // Wait for canvas
  log('Waiting for canvas...');
  await page.waitForSelector('canvas', { timeout: 30000 });

  // Wait for splash/loading screen to disappear
  log('Waiting for splash screen to close...');
  try {
    await page.waitForFunction(() => {
      // Check if loading overlay is hidden
      const loading = document.querySelector('.loading-overlay, [class*="loading"], [class*="splash"]');
      if (loading) {
        const style = window.getComputedStyle(loading);
        return style.opacity === '0' || style.display === 'none' || style.visibility === 'hidden';
      }
      return true;  // No loading element found
    }, { timeout: 30000 });
  } catch (e) {
    log('Splash detection timed out, proceeding anyway...');
  }

  // The warp starts NOW - capture immediately
  log('Splash closed! Starting frame capture...');

  const frames: string[] = [];
  const totalFrames = 4 * FPS;  // 4 seconds for warp
  const frameInterval = 1000 / FPS;
  const startTime = Date.now();

  for (let i = 0; i < totalFrames; i++) {
    const framePath = path.join(OUTPUT_DIR, `frame_${String(i).padStart(5, '0')}.jpg`);
    await page.screenshot({ path: framePath, type: 'jpeg', quality: 95 });
    frames.push(framePath);

    if (i % 60 === 0) {
      log(`  Frame ${i}/${totalFrames}`);
    }

    const elapsed = Date.now() - startTime;
    const targetTime = (i + 1) * frameInterval;
    const waitTime = Math.max(0, targetTime - elapsed);
    if (waitTime > 0) {
      await new Promise(r => setTimeout(r, waitTime));
    }
  }

  log(`Captured ${frames.length} frames`);
  await browser.close();

  // Convert to video
  const outputVideo = path.join(__dirname, 'output', 'captures', 'warp_in.mp4');
  log('Converting to video...');
  execSync(`ffmpeg -y -framerate ${FPS} -i "${OUTPUT_DIR}/frame_%05d.jpg" -c:v libx264 -pix_fmt yuv420p -crf 18 "${outputVideo}"`, {
    stdio: 'inherit'
  });
  log(`Done! Video: ${outputVideo}`);
}

main().catch(console.error);
