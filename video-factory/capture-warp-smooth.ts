/**
 * Capture Globe Warp-In - Smooth Screen Recording
 *
 * Uses Chrome DevTools Protocol to record video without flickering.
 */

import puppeteer from 'puppeteer';
import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';

const SITE_URL = 'https://ancientnerds.com';
const OUTPUT_DIR = path.join(__dirname, 'output', 'captures');
const VIEWPORT = { width: 1920, height: 1080 };

function log(msg: string) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

async function main() {
  log('Starting smooth warp capture...');

  // Ensure output dir exists
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const browser = await puppeteer.launch({
    headless: false,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
      '--start-maximized',
      '--auto-select-desktop-capture-source=Entire screen',
    ],
    defaultViewport: VIEWPORT,
  });

  const page = await browser.newPage();
  await page.setViewport(VIEWPORT);

  // Get CDP session for screen capture
  const client = await page.createCDPSession();

  // Start screencast (captures frames from GPU)
  const frames: Buffer[] = [];
  let frameCount = 0;

  await client.send('Page.startScreencast', {
    format: 'jpeg',
    quality: 95,
    maxWidth: VIEWPORT.width,
    maxHeight: VIEWPORT.height,
    everyNthFrame: 1,  // Every frame
  });

  client.on('Page.screencastFrame', async (event) => {
    const buffer = Buffer.from(event.data, 'base64');
    frames.push(buffer);
    frameCount++;

    // Acknowledge frame
    await client.send('Page.screencastFrameAck', {
      sessionId: event.sessionId,
    });
  });

  log('Navigating to site...');
  await page.goto(SITE_URL, { waitUntil: 'domcontentloaded' });

  // Wait for canvas
  await page.waitForSelector('canvas', { timeout: 30000 });
  log('Canvas found, capturing warp...');

  // Capture for 6 seconds (covers loading + warp)
  await new Promise(r => setTimeout(r, 6000));

  // Stop screencast
  await client.send('Page.stopScreencast');
  log(`Captured ${frameCount} frames`);

  await browser.close();

  // Save frames
  const framesDir = path.join(OUTPUT_DIR, '00_warp_in');
  if (fs.existsSync(framesDir)) {
    fs.rmSync(framesDir, { recursive: true });
  }
  fs.mkdirSync(framesDir, { recursive: true });

  log('Saving frames...');
  for (let i = 0; i < frames.length; i++) {
    const framePath = path.join(framesDir, `frame_${String(i).padStart(5, '0')}.jpg`);
    fs.writeFileSync(framePath, frames[i]);
  }

  // Convert to video (variable framerate based on actual capture rate)
  const fps = Math.round(frames.length / 6);  // Approximate FPS
  log(`Converting ${frames.length} frames at ~${fps}fps...`);

  const outputVideo = path.join(OUTPUT_DIR, 'warp_in.mp4');
  execSync(`ffmpeg -y -framerate ${fps} -i "${framesDir}/frame_%05d.jpg" -c:v libx264 -pix_fmt yuv420p -crf 18 "${outputVideo}"`, {
    stdio: 'inherit'
  });

  log(`Done! Video: ${outputVideo}`);
}

main().catch(console.error);
