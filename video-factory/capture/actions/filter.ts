/**
 * Filter interaction capture action
 *
 * Simulates filter panel interactions for video capture.
 */

import { Page } from 'puppeteer';

// =============================================================================
// Types
// =============================================================================

export interface FilterOptions {
  animationDelay?: number;  // Delay for animation effects (ms)
  waitAfter?: number;       // Wait time after filter action (ms)
}

// =============================================================================
// Default Configuration
// =============================================================================

const DEFAULT_OPTIONS: FilterOptions = {
  animationDelay: 300,
  waitAfter: 500,
};

// =============================================================================
// Filter Actions
// =============================================================================

/**
 * Toggle the filter panel visibility
 */
export async function toggleFilterPanel(
  page: Page,
  options: FilterOptions = {}
): Promise<boolean> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log('Toggling filter panel...');

  const toggleSelectors = [
    '.filter-toggle',
    '[class*="filter"] button',
    'button[aria-label*="filter" i]',
    '[class*="Filter"] button',
    '.sidebar-toggle',
  ];

  for (const selector of toggleSelectors) {
    const toggle = await page.$(selector);
    if (toggle) {
      await toggle.click();
      await page.waitForTimeout(opts.animationDelay! + opts.waitAfter!);
      console.log('Filter panel toggled');
      return true;
    }
  }

  console.warn('Filter toggle not found');
  return false;
}

/**
 * Select a category filter
 */
export async function selectCategory(
  page: Page,
  categoryName: string,
  options: FilterOptions = {}
): Promise<boolean> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log(`Selecting category: ${categoryName}`);

  // Try to find category by text content
  const selected = await page.evaluate((name) => {
    const items = document.querySelectorAll(
      '[class*="category"], [class*="filter-item"], [class*="checkbox"], label'
    );

    for (const item of items) {
      if (item.textContent?.toLowerCase().includes(name.toLowerCase())) {
        (item as HTMLElement).click();
        return true;
      }
    }

    return false;
  }, categoryName);

  if (selected) {
    await page.waitForTimeout(opts.waitAfter!);
    console.log(`Category "${categoryName}" selected`);
    return true;
  }

  console.warn(`Category "${categoryName}" not found`);
  return false;
}

/**
 * Select a time period filter
 */
export async function selectPeriod(
  page: Page,
  periodName: string,
  options: FilterOptions = {}
): Promise<boolean> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log(`Selecting period: ${periodName}`);

  const selected = await page.evaluate((name) => {
    const items = document.querySelectorAll(
      '[class*="period"], [class*="timeline"], [class*="filter-item"]'
    );

    for (const item of items) {
      if (item.textContent?.toLowerCase().includes(name.toLowerCase())) {
        (item as HTMLElement).click();
        return true;
      }
    }

    return false;
  }, periodName);

  if (selected) {
    await page.waitForTimeout(opts.waitAfter!);
    console.log(`Period "${periodName}" selected`);
    return true;
  }

  console.warn(`Period "${periodName}" not found`);
  return false;
}

/**
 * Select a source filter
 */
export async function selectSource(
  page: Page,
  sourceName: string,
  options: FilterOptions = {}
): Promise<boolean> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log(`Selecting source: ${sourceName}`);

  const selected = await page.evaluate((name) => {
    const items = document.querySelectorAll(
      '[class*="source"], [class*="filter-item"], input[type="checkbox"]'
    );

    for (const item of items) {
      const text = item.textContent || (item as HTMLInputElement).value || '';
      if (text.toLowerCase().includes(name.toLowerCase())) {
        (item as HTMLElement).click();
        return true;
      }
    }

    return false;
  }, sourceName);

  if (selected) {
    await page.waitForTimeout(opts.waitAfter!);
    console.log(`Source "${sourceName}" selected`);
    return true;
  }

  console.warn(`Source "${sourceName}" not found`);
  return false;
}

/**
 * Clear all filters
 */
export async function clearFilters(
  page: Page,
  options: FilterOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log('Clearing all filters...');

  const clearSelectors = [
    '.clear-filters',
    'button:contains("Clear")',
    '[class*="clear"]',
    'button[aria-label*="reset" i]',
  ];

  for (const selector of clearSelectors) {
    const clearBtn = await page.$(selector);
    if (clearBtn) {
      await clearBtn.click();
      await page.waitForTimeout(opts.waitAfter!);
      console.log('Filters cleared');
      return;
    }
  }

  // Try clicking reset via evaluate
  await page.evaluate(() => {
    const buttons = document.querySelectorAll('button');
    for (const btn of buttons) {
      if (btn.textContent?.toLowerCase().includes('clear') ||
          btn.textContent?.toLowerCase().includes('reset')) {
        btn.click();
        return;
      }
    }
  });

  await page.waitForTimeout(opts.waitAfter!);
}

/**
 * Get list of available categories
 */
export async function getAvailableCategories(page: Page): Promise<string[]> {
  const categories = await page.evaluate(() => {
    const items = document.querySelectorAll('[class*="category"]');
    return Array.from(items).map((item) => item.textContent?.trim() || '').filter(Boolean);
  });

  return categories;
}

/**
 * Get current filter state
 */
export async function getFilterState(page: Page): Promise<{
  categories: string[];
  periods: string[];
  sources: string[];
}> {
  const state = await page.evaluate(() => {
    const getChecked = (selector: string) => {
      const items = document.querySelectorAll(`${selector} input:checked`);
      return Array.from(items).map((item) => {
        const label = item.closest('label');
        return label?.textContent?.trim() || '';
      }).filter(Boolean);
    };

    return {
      categories: getChecked('[class*="category"]'),
      periods: getChecked('[class*="period"]'),
      sources: getChecked('[class*="source"]'),
    };
  });

  return state;
}

// =============================================================================
// Export
// =============================================================================

export default toggleFilterPanel;
