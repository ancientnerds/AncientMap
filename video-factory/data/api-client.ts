/**
 * API Client for Video Factory
 *
 * Fetches site data from the Ancient Nerds public API.
 * No database connection needed - uses public endpoints.
 */

import {
  Site,
  SiteDetail,
  SourceMeta,
  Category,
  SitesSearchResponse,
  SiteDetailResponse,
} from './types';

// =============================================================================
// Configuration
// =============================================================================

const DEFAULT_BASE_URL = 'https://ancientnerds.com';
const LOCAL_BASE_URL = 'http://localhost:3000';

export interface ApiClientConfig {
  baseUrl?: string;
  useLocal?: boolean;
  timeout?: number;
}

// =============================================================================
// API Client Class
// =============================================================================

export class ApiClient {
  private baseUrl: string;
  private timeout: number;

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = config.useLocal
      ? LOCAL_BASE_URL
      : config.baseUrl || DEFAULT_BASE_URL;
    this.timeout = config.timeout || 30000;
  }

  /**
   * Fetch with timeout support
   */
  private async fetchWithTimeout(url: string): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  /**
   * Search for sites by name
   */
  async searchSites(query: string, limit = 10): Promise<Site[]> {
    const url = `${this.baseUrl}/api/sites?search=${encodeURIComponent(query)}&limit=${limit}`;
    const response = await this.fetchWithTimeout(url);

    if (!response.ok) {
      throw new Error(`Failed to search sites: ${response.statusText}`);
    }

    const data = await response.json() as SitesSearchResponse;
    return data.sites || [];
  }

  /**
   * Get site by ID
   */
  async getSiteById(siteId: string): Promise<SiteDetail | null> {
    const url = `${this.baseUrl}/api/sites/${encodeURIComponent(siteId)}`;
    const response = await this.fetchWithTimeout(url);

    if (!response.ok) {
      if (response.status === 404) {
        return null;
      }
      throw new Error(`Failed to get site: ${response.statusText}`);
    }

    const data = await response.json() as SiteDetailResponse;
    return data.site || null;
  }

  /**
   * Get sites by category
   */
  async getSitesByCategory(category: string, limit = 50): Promise<Site[]> {
    const url = `${this.baseUrl}/api/sites?category=${encodeURIComponent(category)}&limit=${limit}`;
    const response = await this.fetchWithTimeout(url);

    if (!response.ok) {
      throw new Error(`Failed to get sites by category: ${response.statusText}`);
    }

    const data = await response.json() as SitesSearchResponse;
    return data.sites || [];
  }

  /**
   * Get sites by country/location
   */
  async getSitesByCountry(country: string, limit = 50): Promise<Site[]> {
    const url = `${this.baseUrl}/api/sites?country=${encodeURIComponent(country)}&limit=${limit}`;
    const response = await this.fetchWithTimeout(url);

    if (!response.ok) {
      throw new Error(`Failed to get sites by country: ${response.statusText}`);
    }

    const data = await response.json() as SitesSearchResponse;
    return data.sites || [];
  }

  /**
   * Get all available categories
   */
  async getCategories(): Promise<Category[]> {
    const url = `${this.baseUrl}/api/categories`;
    const response = await this.fetchWithTimeout(url);

    if (!response.ok) {
      // Categories endpoint might not exist, return empty
      console.warn('Categories endpoint not available');
      return [];
    }

    const data = await response.json();
    return data.categories || [];
  }

  /**
   * Get all available sources
   */
  async getSources(): Promise<SourceMeta[]> {
    const url = `${this.baseUrl}/api/sources`;
    const response = await this.fetchWithTimeout(url);

    if (!response.ok) {
      console.warn('Sources endpoint not available');
      return [];
    }

    const data = await response.json();
    return data.sources || [];
  }

  /**
   * Get global stats (total sites, categories, countries)
   */
  async getStats(): Promise<{
    totalSites: number;
    categories: number;
    countries: number;
    sources: number;
  }> {
    const url = `${this.baseUrl}/api/stats`;
    const response = await this.fetchWithTimeout(url);

    if (!response.ok) {
      // Return default stats if endpoint unavailable
      return {
        totalSites: 800000,
        categories: 50,
        countries: 200,
        sources: 20,
      };
    }

    return response.json();
  }

  /**
   * Find site by name (exact or fuzzy match)
   */
  async findSiteByName(name: string): Promise<SiteDetail | null> {
    // First, search for sites with this name
    const sites = await this.searchSites(name, 5);

    if (sites.length === 0) {
      return null;
    }

    // Try to find exact match (case-insensitive)
    const exactMatch = sites.find(
      (s) => s.name.toLowerCase() === name.toLowerCase()
    );

    // Get full details for the best match
    const targetSite = exactMatch || sites[0];
    return this.getSiteById(targetSite.id);
  }

  /**
   * Get featured sites for teaser video
   */
  async getFeaturedSites(limit = 10): Promise<SiteDetail[]> {
    // Get sites from different categories for variety
    const featuredNames = [
      'Machu Picchu',
      'Stonehenge',
      'Pyramids of Giza',
      'Colosseum',
      'Angkor Wat',
      'Petra',
      'Chichen Itza',
      'Acropolis',
      'Pompeii',
      'Teotihuacan',
    ];

    const sites: SiteDetail[] = [];

    for (const name of featuredNames.slice(0, limit)) {
      try {
        const site = await this.findSiteByName(name);
        if (site) {
          sites.push(site);
        }
      } catch (error) {
        console.warn(`Failed to fetch site: ${name}`, error);
      }
    }

    return sites;
  }
}

// =============================================================================
// Default Export
// =============================================================================

/** Default API client instance */
export const apiClient = new ApiClient();

/** Create API client with custom config */
export function createApiClient(config?: ApiClientConfig): ApiClient {
  return new ApiClient(config);
}
