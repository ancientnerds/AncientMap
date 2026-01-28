/**
 * Capture Teaser Footage from ancientnerds.com
 *
 * Captures real footage for the Epic Discovery teaser.
 */

import puppeteer, { Browser, Page } from 'puppeteer';
import * as fs from 'fs';
import * as path from 'path';

// =============================================================================
// Configuration
// =============================================================================

const SITE_URL = 'https://ancientnerds.com';
const OUTPUT_DIR = path.join(__dirname, 'output', 'captures');
const FPS = 30;
const VIEWPORT = { width: 1920, height: 1080 };

// Ensure output directory exists
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// =============================================================================
// Utility Functions
// =============================================================================

function log(msg: string) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function captureFrames(
  page: Page,
  sessionName: string,
  durationSec: number,
  fps: number = FPS
): Promise<string[]> {
  const sessionDir = path.join(OUTPUT_DIR, sessionName);
  if (!fs.existsSync(sessionDir)) {
    fs.mkdirSync(sessionDir, { recursive: true });
  }

  const totalFrames = Math.ceil(durationSec * fps);
  const frameInterval = 1000 / fps;
  const frames: string[] = [];

  log(`Capturing ${totalFrames} frames for "${sessionName}"...`);

  for (let i = 0; i < totalFrames; i++) {
    const framePath = path.join(sessionDir, `frame_${String(i).padStart(5, '0')}.jpg`);
    await page.screenshot({ path: framePath, type: 'jpeg', quality: 90 });
    frames.push(framePath);

    if (i % 30 === 0) {
      log(`  ${sessionName}: ${i}/${totalFrames} frames`);
    }

    await sleep(frameInterval);
  }

  log(`  ${sessionName}: Done (${frames.length} frames)`);
  return frames;
}

// =============================================================================
// Main Capture Script
// =============================================================================

async function main() {
  log('Starting capture from ancientnerds.com...');

  // Launch browser
  const browser = await puppeteer.launch({
    headless: false,  // Show browser so we can see what's happening
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
    ],
    defaultViewport: VIEWPORT,
  });

  const page = await browser.newPage();
  await page.setViewport(VIEWPORT);

  try {
    // ===========================================
    // SHOT 1: Load site and capture globe reveal
    // ===========================================
    log('Loading ancientnerds.com...');
    await page.goto(SITE_URL, { waitUntil: 'networkidle2', timeout: 60000 });

    // Wait for globe to be ready
    log('Waiting for globe to load...');
    await sleep(5000);

    // Capture globe reveal (5 seconds)
    await captureFrames(page, '01_globe_reveal', 5);

    // ===========================================
    // SHOT 2: Fly to Pyramids of Giza
    // ===========================================
    log('Flying to Pyramids of Giza...');

    // Use search to navigate
    const searchInput = await page.$('input[type="text"], input[type="search"], .search-input, input[placeholder*="Search"]');
    if (searchInput) {
      await searchInput.click();
      await sleep(500);
      await searchInput.type('Pyramids of Giza', { delay: 50 });
      await sleep(1500);

      // Try to click first result
      await page.keyboard.press('Enter');
      await sleep(3000);
    }

    // Capture the fly-to (4 seconds)
    await captureFrames(page, '02_giza', 4);

    // Clear search
    if (searchInput) {
      await searchInput.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(500);
    }

    // ===========================================
    // SHOT 3: Fly to Machu Picchu (Featured)
    // ===========================================
    log('Flying to Machu Picchu...');

    const searchInput2 = await page.$('input[type="text"], input[type="search"], .search-input, input[placeholder*="Search"]');
    if (searchInput2) {
      await searchInput2.click();
      await sleep(500);
      await searchInput2.type('Machu Picchu', { delay: 50 });
      await sleep(1500);
      await page.keyboard.press('Enter');
      await sleep(3000);
    }

    await captureFrames(page, '03_machu_picchu', 4);

    // Clear search
    if (searchInput2) {
      await searchInput2.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(500);
    }

    // ===========================================
    // SHOT 4: Fly to Stonehenge
    // ===========================================
    log('Flying to Stonehenge...');

    const searchInput3 = await page.$('input[type="text"], input[type="search"], .search-input, input[placeholder*="Search"]');
    if (searchInput3) {
      await searchInput3.click();
      await sleep(500);
      await searchInput3.type('Stonehenge', { delay: 50 });
      await sleep(1500);
      await page.keyboard.press('Enter');
      await sleep(3000);
    }

    await captureFrames(page, '04_stonehenge', 4);

    // ===========================================
    // SHOT 5: Filter Panel Demo
    // ===========================================
    log('Capturing filter panel...');

    // Look for filter button/panel
    const filterBtn = await page.$('[class*="filter"], [class*="Filter"], button[aria-label*="filter"]');
    if (filterBtn) {
      await filterBtn.click();
      await sleep(1000);
    }

    await captureFrames(page, '05_filter_demo', 6);

    // ===========================================
    // SHOT 6: Search Demo
    // ===========================================
    log('Capturing search demo...');

    // Clear and type slowly for visual effect
    const searchInput4 = await page.$('input[type="text"], input[type="search"], .search-input, input[placeholder*="Search"]');
    if (searchInput4) {
      await searchInput4.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(500);
    }

    // Start capturing while typing
    const searchCapturePromise = captureFrames(page, '06_search_demo', 6);

    if (searchInput4) {
      await sleep(1000);
      await searchInput4.type('Temple', { delay: 150 });
    }

    await searchCapturePromise;

    // ===========================================
    // SHOT 7: Popup Demo
    // ===========================================
    log('Capturing popup demo...');

    // Click on a marker or search result to open popup
    await page.keyboard.press('Enter');
    await sleep(2000);

    await captureFrames(page, '07_popup_demo', 6);

    // ===========================================
    // SHOT 8: Globe overview / outro
    // ===========================================
    log('Capturing globe overview...');

    // Press Escape to close any popup
    await page.keyboard.press('Escape');
    await sleep(500);

    // Clear search to show full globe
    const searchInput5 = await page.$('input[type="text"], input[type="search"], .search-input, input[placeholder*="Search"]');
    if (searchInput5) {
      await searchInput5.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(1000);
    }

    await captureFrames(page, '08_globe_outro', 7);

    // ===========================================
    // Done!
    // ===========================================
    log('');
    log('='.repeat(50));
    log('CAPTURE COMPLETE!');
    log('='.repeat(50));
    log(`Frames saved to: ${OUTPUT_DIR}`);
    log('');
    log('Captured shots:');
    log('  01_globe_reveal  - 5 seconds');
    log('  02_giza          - 4 seconds');
    log('  03_machu_picchu  - 4 seconds');
    log('  04_stonehenge    - 4 seconds');
    log('  05_filter_demo   - 6 seconds');
    log('  06_search_demo   - 6 seconds');
    log('  07_popup_demo    - 6 seconds');
    log('  08_globe_outro   - 7 seconds');
    log('');

  } catch (error) {
    console.error('Capture error:', error);
  } finally {
    await browser.close();
  }
}

// Run
main().catch(console.error);
