/**
 * Show popup capture action
 *
 * Opens and displays a site popup for capture.
 */

import { Page } from 'puppeteer';

// =============================================================================
// Types
// =============================================================================

export interface PopupOptions {
  waitForAnimation?: number;  // Wait time for popup animation (ms)
  scrollContent?: boolean;    // Whether to scroll popup content
  scrollDelay?: number;       // Delay between scroll steps (ms)
}

// =============================================================================
// Default Configuration
// =============================================================================

const DEFAULT_OPTIONS: PopupOptions = {
  waitForAnimation: 500,
  scrollContent: false,
  scrollDelay: 100,
};

// =============================================================================
// Popup Actions
// =============================================================================

/**
 * Click on a site marker to open its popup
 */
export async function clickSiteMarker(
  page: Page,
  options: PopupOptions = {}
): Promise<boolean> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log('Attempting to click site marker...');

  // Try various marker selectors
  const markerSelectors = [
    '.site-marker',
    '.marker',
    '.mapboxgl-marker',
    '[class*="marker"]',
    'canvas', // Click on canvas if markers are rendered on it
  ];

  for (const selector of markerSelectors) {
    const marker = await page.$(selector);
    if (marker) {
      const box = await marker.boundingBox();
      if (box) {
        // Click center of the element
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        await page.waitForTimeout(opts.waitForAnimation!);
        console.log(`Clicked marker with selector: ${selector}`);
        return true;
      }
    }
  }

  console.warn('No marker found to click');
  return false;
}

/**
 * Wait for popup to appear and be fully loaded
 */
export async function waitForPopup(
  page: Page,
  timeout: number = 5000
): Promise<boolean> {
  console.log('Waiting for popup...');

  const popupSelectors = [
    '.site-popup',
    '.popup',
    '.mapboxgl-popup',
    '[class*="popup"]',
    '[class*="Popup"]',
    '.modal',
    '[role="dialog"]',
  ];

  try {
    for (const selector of popupSelectors) {
      try {
        await page.waitForSelector(selector, { timeout: timeout / popupSelectors.length });
        console.log(`Popup found with selector: ${selector}`);
        return true;
      } catch {
        // Try next selector
      }
    }
  } catch {
    console.warn('Popup did not appear within timeout');
    return false;
  }

  return false;
}

/**
 * Close the currently open popup
 */
export async function closePopup(page: Page): Promise<void> {
  console.log('Closing popup...');

  const closeSelectors = [
    '.popup-close',
    '.close-button',
    '[class*="close"]',
    'button[aria-label="Close"]',
    '.mapboxgl-popup-close-button',
  ];

  for (const selector of closeSelectors) {
    const closeBtn = await page.$(selector);
    if (closeBtn) {
      await closeBtn.click();
      await page.waitForTimeout(300);
      console.log('Popup closed');
      return;
    }
  }

  // Try pressing Escape
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}

/**
 * Scroll through popup content
 */
export async function scrollPopupContent(
  page: Page,
  options: PopupOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log('Scrolling popup content...');

  await page.evaluate(async (delay) => {
    const popup = document.querySelector('.site-popup, .popup, [class*="popup"]');
    if (!popup) return;

    const scrollable = popup.querySelector('[class*="content"], [class*="body"]') || popup;
    const scrollHeight = (scrollable as HTMLElement).scrollHeight;
    const clientHeight = (scrollable as HTMLElement).clientHeight;

    if (scrollHeight <= clientHeight) return;

    // Smooth scroll down
    const steps = 10;
    const stepSize = (scrollHeight - clientHeight) / steps;

    for (let i = 0; i < steps; i++) {
      (scrollable as HTMLElement).scrollTop += stepSize;
      await new Promise((r) => setTimeout(r, delay));
    }
  }, opts.scrollDelay);
}

/**
 * Get popup content as text
 */
export async function getPopupContent(page: Page): Promise<string | null> {
  const content = await page.evaluate(() => {
    const popup = document.querySelector('.site-popup, .popup, [class*="popup"]');
    return popup ? popup.textContent : null;
  });

  return content;
}

/**
 * Check if popup is currently open
 */
export async function isPopupOpen(page: Page): Promise<boolean> {
  const isOpen = await page.evaluate(() => {
    const popup = document.querySelector('.site-popup, .popup, [class*="popup"]');
    if (!popup) return false;

    const style = window.getComputedStyle(popup);
    return style.display !== 'none' && style.visibility !== 'hidden';
  });

  return isOpen;
}

// =============================================================================
// Export
// =============================================================================

export { clickSiteMarker as showPopup };
export default clickSiteMarker;
