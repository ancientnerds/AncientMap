/**
 * Ancient Nerds Video Factory
 *
 * Standalone video generation system for archaeological site videos.
 *
 * This module provides:
 * - Remotion compositions for teaser and site short videos
 * - Puppeteer-based capture layer for globe animations
 * - CLI interface for directive-based video generation
 * - API client for fetching site data
 *
 * @module video-factory
 */

// Re-export compositions
export * from './compositions';

// Re-export data types and API client
export * from './data/types';
export * from './data/api-client';

// Re-export capture utilities
export * from './capture/browser';
export * from './capture/recorder';
export * from './capture/actions';

// Re-export theme
export * from './styles/theme';

// Default export for Remotion
export { RemotionRoot } from './Root';
