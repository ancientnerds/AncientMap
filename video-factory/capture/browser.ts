/**
 * Browser setup & management for Puppeteer
 *
 * Handles browser launch, page creation, and cleanup.
 */

import puppeteer, { Browser, Page, PuppeteerLaunchOptions } from 'puppeteer';

// =============================================================================
// Configuration
// =============================================================================

const DEFAULT_SITE_URL = 'https://ancientnerds.com';
const LOCAL_SITE_URL = 'http://localhost:5173';

export interface BrowserConfig {
  headless?: boolean;
  siteUrl?: string;
  useLocal?: boolean;
  viewport?: {
    width: number;
    height: number;
  };
  timeout?: number;
}

const DEFAULT_CONFIG: BrowserConfig = {
  headless: true,
  siteUrl: DEFAULT_SITE_URL,
  useLocal: false,
  viewport: {
    width: 1920,
    height: 1080,
  },
  timeout: 60000,
};

// =============================================================================
// Browser Manager Class
// =============================================================================

export class BrowserManager {
  private browser: Browser | null = null;
  private page: Page | null = null;
  private config: BrowserConfig;

  constructor(config: Partial<BrowserConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Get the site URL based on configuration
   */
  getSiteUrl(): string {
    return this.config.useLocal ? LOCAL_SITE_URL : (this.config.siteUrl || DEFAULT_SITE_URL);
  }

  /**
   * Launch browser and create page
   */
  async launch(): Promise<Page> {
    const launchOptions: PuppeteerLaunchOptions = {
      headless: this.config.headless ? 'shell' : false,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-web-security',
        '--disable-features=IsolateOrigins,site-per-process',
        `--window-size=${this.config.viewport!.width},${this.config.viewport!.height}`,
      ],
      defaultViewport: this.config.viewport,
    };

    this.browser = await puppeteer.launch(launchOptions);
    this.page = await this.browser.newPage();

    // Set viewport
    await this.page.setViewport({
      width: this.config.viewport!.width,
      height: this.config.viewport!.height,
      deviceScaleFactor: 1,
    });

    // Set timeout
    this.page.setDefaultTimeout(this.config.timeout!);

    return this.page;
  }

  /**
   * Navigate to the Ancient Nerds site
   */
  async navigateToSite(): Promise<void> {
    if (!this.page) {
      throw new Error('Browser not launched. Call launch() first.');
    }

    const url = this.getSiteUrl();
    console.log(`Navigating to ${url}...`);

    await this.page.goto(url, {
      waitUntil: 'networkidle2',
      timeout: this.config.timeout,
    });

    // Wait for globe to be ready
    await this.waitForGlobe();
  }

  /**
   * Wait for the globe to be fully loaded and interactive
   */
  async waitForGlobe(): Promise<void> {
    if (!this.page) return;

    console.log('Waiting for globe to load...');

    // Wait for canvas or map container
    await this.page.waitForSelector('canvas, .mapboxgl-canvas, #map', {
      timeout: this.config.timeout,
    });

    // Additional wait for animation/rendering
    await this.page.waitForTimeout(2000);

    console.log('Globe loaded and ready.');
  }

  /**
   * Get the current page
   */
  getPage(): Page | null {
    return this.page;
  }

  /**
   * Get the browser instance
   */
  getBrowser(): Browser | null {
    return this.browser;
  }

  /**
   * Take a screenshot
   */
  async screenshot(path: string): Promise<void> {
    if (!this.page) {
      throw new Error('Browser not launched.');
    }
    await this.page.screenshot({ path, type: 'png' });
  }

  /**
   * Close browser and cleanup
   */
  async close(): Promise<void> {
    if (this.page) {
      await this.page.close();
      this.page = null;
    }
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
    }
  }
}

// =============================================================================
// Factory Function
// =============================================================================

/**
 * Create and launch a browser manager
 */
export async function createBrowser(config?: Partial<BrowserConfig>): Promise<BrowserManager> {
  const manager = new BrowserManager(config);
  await manager.launch();
  return manager;
}

// =============================================================================
// Default Export
// =============================================================================

export const browserManager = new BrowserManager();
