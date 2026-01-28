/**
 * Search interaction capture action
 *
 * Simulates search interactions for video capture.
 */

import { Page } from 'puppeteer';

// =============================================================================
// Types
// =============================================================================

export interface SearchOptions {
  typeDelay?: number;       // Delay between keystrokes (ms)
  waitForResults?: number;  // Wait time for results to appear (ms)
  selectResult?: boolean;   // Whether to click first result
}

// =============================================================================
// Default Configuration
// =============================================================================

const DEFAULT_OPTIONS: SearchOptions = {
  typeDelay: 80,
  waitForResults: 1500,
  selectResult: true,
};

// =============================================================================
// Search Actions
// =============================================================================

/**
 * Find the search input element
 */
async function findSearchInput(page: Page): Promise<any | null> {
  const selectors = [
    'input[type="search"]',
    'input[placeholder*="search" i]',
    'input[placeholder*="Search" i]',
    '.search-input',
    '#search',
    '[class*="search"] input',
  ];

  for (const selector of selectors) {
    const input = await page.$(selector);
    if (input) {
      return input;
    }
  }

  return null;
}

/**
 * Perform a search query
 */
export async function performSearch(
  page: Page,
  query: string,
  options: SearchOptions = {}
): Promise<boolean> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  console.log(`Performing search: "${query}"`);

  // Find search input
  const searchInput = await findSearchInput(page);

  if (!searchInput) {
    console.warn('Search input not found');
    return false;
  }

  // Focus and clear input
  await searchInput.click();
  await page.keyboard.down('Control');
  await page.keyboard.press('a');
  await page.keyboard.up('Control');
  await page.waitForTimeout(100);

  // Type search query with delay for visual effect
  await searchInput.type(query, { delay: opts.typeDelay });

  // Wait for results
  await page.waitForTimeout(opts.waitForResults!);

  console.log('Search query entered');

  // Optionally select first result
  if (opts.selectResult) {
    const selected = await selectFirstResult(page);
    return selected;
  }

  return true;
}

/**
 * Select the first search result
 */
export async function selectFirstResult(page: Page): Promise<boolean> {
  const resultSelectors = [
    '.search-result:first-child',
    '.search-results li:first-child',
    '.search-results > div:first-child',
    '[class*="search-result"]:first-child',
    '[class*="SearchResult"]:first-child',
    '.autocomplete-item:first-child',
    '[class*="autocomplete"] li:first-child',
  ];

  for (const selector of resultSelectors) {
    const result = await page.$(selector);
    if (result) {
      await result.click();
      await page.waitForTimeout(500);
      console.log('Selected first search result');
      return true;
    }
  }

  // Try pressing Enter to select
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);

  console.log('Pressed Enter to select');
  return true;
}

/**
 * Clear the search input
 */
export async function clearSearch(page: Page): Promise<void> {
  const searchInput = await findSearchInput(page);

  if (searchInput) {
    await searchInput.click({ clickCount: 3 });
    await page.keyboard.press('Backspace');
    await page.waitForTimeout(300);
    console.log('Search cleared');
  }
}

/**
 * Focus the search input (for visual)
 */
export async function focusSearch(page: Page): Promise<void> {
  const searchInput = await findSearchInput(page);

  if (searchInput) {
    await searchInput.click();
    console.log('Search input focused');
  }
}

/**
 * Type in search with visual caret blinking
 */
export async function typeSearchAnimated(
  page: Page,
  text: string,
  charDelay: number = 100
): Promise<void> {
  const searchInput = await findSearchInput(page);

  if (!searchInput) {
    console.warn('Search input not found');
    return;
  }

  await searchInput.click();

  // Type character by character
  for (const char of text) {
    await page.keyboard.type(char);
    await page.waitForTimeout(charDelay);
  }

  console.log(`Typed: "${text}"`);
}

// =============================================================================
// Export
// =============================================================================

export default performSearch;
