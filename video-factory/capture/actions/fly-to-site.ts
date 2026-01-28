/**
 * Fly-to-site capture action
 *
 * Navigates the globe to a specific site with smooth animation.
 */

import { Page } from 'puppeteer';

// =============================================================================
// Types
// =============================================================================

export interface FlyToOptions {
  duration?: number;      // Animation duration in ms
  zoom?: number;          // Target zoom level
  pitch?: number;         // Camera pitch
  bearing?: number;       // Camera bearing/rotation
  waitAfter?: number;     // Wait time after animation (ms)
}

export interface Coordinates {
  lat: number;
  lon: number;
}

// =============================================================================
// Default Configuration
// =============================================================================

const DEFAULT_OPTIONS: FlyToOptions = {
  duration: 3000,
  zoom: 12,
  pitch: 45,
  bearing: 0,
  waitAfter: 1000,
};

// =============================================================================
// Fly-To Action
// =============================================================================

/**
 * Fly to a specific coordinate on the globe
 */
export async function flyToCoordinates(
  page: Page,
  coords: Coordinates,
  options: FlyToOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log(`Flying to coordinates: ${coords.lat}, ${coords.lon}`);

  // Execute fly-to animation via map API
  await page.evaluate(
    ({ lat, lon, duration, zoom, pitch, bearing }) => {
      // Try Mapbox GL
      const mapboxMap = (window as any).map || (window as any).mapboxMap;
      if (mapboxMap && typeof mapboxMap.flyTo === 'function') {
        mapboxMap.flyTo({
          center: [lon, lat],
          zoom: zoom,
          pitch: pitch,
          bearing: bearing,
          duration: duration,
          essential: true,
        });
        return;
      }

      console.warn('No map instance found for fly-to animation');
    },
    { lat: coords.lat, lon: coords.lon, ...opts }
  );

  // Wait for animation to complete
  await page.waitForTimeout(opts.duration! + opts.waitAfter!);

  console.log('Fly-to animation complete.');
}

/**
 * Fly to a site by searching for it
 */
export async function flyToSite(
  page: Page,
  siteName: string,
  options: FlyToOptions = {}
): Promise<void> {
  console.log(`Flying to site: ${siteName}`);

  // First, try to use the site search to find and select the site
  const searchInput = await page.$('input[type="search"], input[placeholder*="search" i], .search-input');

  if (searchInput) {
    // Clear and type site name
    await searchInput.click({ clickCount: 3 });
    await searchInput.type(siteName, { delay: 50 });

    // Wait for search results
    await page.waitForTimeout(1000);

    // Try to click on the first result
    const resultSelectors = [
      '.search-result:first-child',
      '.search-results li:first-child',
      '[class*="search"] [class*="result"]:first-child',
      '.autocomplete-item:first-child',
    ];

    for (const selector of resultSelectors) {
      const result = await page.$(selector);
      if (result) {
        await result.click();
        await page.waitForTimeout(options.duration || DEFAULT_OPTIONS.duration!);
        console.log(`Clicked search result for: ${siteName}`);
        return;
      }
    }
  }

  // If search doesn't work, try direct URL navigation
  const currentUrl = page.url();
  const baseUrl = new URL(currentUrl).origin;
  const siteUrl = `${baseUrl}/?site=${encodeURIComponent(siteName)}`;

  console.log(`Navigating to site URL: ${siteUrl}`);
  await page.goto(siteUrl, { waitUntil: 'networkidle2' });
  await page.waitForTimeout(options.waitAfter || DEFAULT_OPTIONS.waitAfter!);
}

/**
 * Fly to site by ID (if known)
 */
export async function flyToSiteById(
  page: Page,
  siteId: string,
  options: FlyToOptions = {}
): Promise<void> {
  console.log(`Flying to site ID: ${siteId}`);

  const currentUrl = page.url();
  const baseUrl = new URL(currentUrl).origin;
  const siteUrl = `${baseUrl}/?id=${encodeURIComponent(siteId)}`;

  await page.goto(siteUrl, { waitUntil: 'networkidle2' });
  await page.waitForTimeout(options.waitAfter || DEFAULT_OPTIONS.waitAfter!);
}

// =============================================================================
// Export
// =============================================================================

export default flyToSite;
