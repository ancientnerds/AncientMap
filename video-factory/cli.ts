#!/usr/bin/env node
/**
 * Ancient Nerds Video Factory CLI
 *
 * Command-line interface for generating archaeological site videos.
 *
 * Examples:
 *   npx ts-node cli.ts teaser
 *   npx ts-node cli.ts short --site "Machu Picchu"
 *   npx ts-node cli.ts short --site-id "pleiades-12345"
 *   npx ts-node cli.ts short --category "Pyramid" --limit 10
 *   npx ts-node cli.ts capture --action "fly-to" --site "Stonehenge"
 */

import { program } from 'commander';
import * as path from 'path';
import * as fs from 'fs';

import { ApiClient, createApiClient } from './data/api-client';
import { Directive, SiteDetail, VIDEO_FORMATS } from './data/types';

// =============================================================================
// Configuration
// =============================================================================

const VERSION = '1.0.0';
const OUTPUT_DIR = path.join(__dirname, 'output');
const ASSETS_DIR = path.join(__dirname, 'assets');

// Ensure output directories exist
if (!fs.existsSync(path.join(OUTPUT_DIR, 'teaser'))) {
  fs.mkdirSync(path.join(OUTPUT_DIR, 'teaser'), { recursive: true });
}
if (!fs.existsSync(path.join(OUTPUT_DIR, 'shorts'))) {
  fs.mkdirSync(path.join(OUTPUT_DIR, 'shorts'), { recursive: true });
}

// =============================================================================
// Utilities
// =============================================================================

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

function log(message: string, type: 'info' | 'success' | 'error' | 'warn' = 'info'): void {
  const prefix = {
    info: '\x1b[36m[INFO]\x1b[0m',
    success: '\x1b[32m[SUCCESS]\x1b[0m',
    error: '\x1b[31m[ERROR]\x1b[0m',
    warn: '\x1b[33m[WARN]\x1b[0m',
  };
  console.log(`${prefix[type]} ${message}`);
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

// =============================================================================
// Video Generation Functions
// =============================================================================

async function generateTeaser(options: {
  output?: string;
  useLocal?: boolean;
  skipCapture?: boolean;
}): Promise<void> {
  log('Generating Product Teaser (16:9)...');

  const apiClient = createApiClient({ useLocal: options.useLocal });
  const outputPath = options.output || path.join(OUTPUT_DIR, 'teaser', 'product-teaser.mp4');

  try {
    // Fetch featured sites
    log('Fetching featured sites...');
    const featuredSites = await apiClient.getFeaturedSites(5);
    log(`Found ${featuredSites.length} featured sites`);

    // Fetch stats
    log('Fetching stats...');
    const stats = await apiClient.getStats();

    // Generate render props
    const props = {
      title: 'ANCIENT NERDS',
      tagline: 'Explore 800,000+ Archaeological Sites',
      featuredSites,
      stats,
      features: [
        'Interactive 3D Globe',
        'Advanced Filtering',
        'AI-Powered Search',
        'Detailed Site Info',
      ],
      logoSrc: path.join(ASSETS_DIR, 'an-logo.png'),
    };

    // Output render command
    log('To render the teaser, run:');
    console.log(`
  npx remotion render ProductTeaser ${outputPath} --props='${JSON.stringify(props)}'
    `);

    // Save props to file for easier rendering
    const propsPath = path.join(OUTPUT_DIR, 'teaser', 'teaser-props.json');
    fs.writeFileSync(propsPath, JSON.stringify(props, null, 2));
    log(`Props saved to: ${propsPath}`, 'success');

    log(`Teaser will be saved to: ${outputPath}`, 'success');
  } catch (error) {
    log(`Failed to generate teaser: ${error}`, 'error');
    throw error;
  }
}

async function generateShort(options: {
  site?: string;
  siteId?: string;
  output?: string;
  useLocal?: boolean;
  skipCapture?: boolean;
}): Promise<void> {
  if (!options.site && !options.siteId) {
    throw new Error('Either --site or --site-id is required');
  }

  const apiClient = createApiClient({ useLocal: options.useLocal });

  try {
    // Find the site
    let siteDetail: SiteDetail | null = null;

    if (options.siteId) {
      log(`Looking up site by ID: ${options.siteId}...`);
      siteDetail = await apiClient.getSiteById(options.siteId);
    } else if (options.site) {
      log(`Searching for site: ${options.site}...`);
      siteDetail = await apiClient.findSiteByName(options.site);
    }

    if (!siteDetail) {
      throw new Error(`Site not found: ${options.site || options.siteId}`);
    }

    log(`Found site: ${siteDetail.name}`, 'success');

    // Determine output path
    const filename = `${slugify(siteDetail.name)}.mp4`;
    const outputPath = options.output || path.join(OUTPUT_DIR, 'shorts', filename);

    // Generate render props
    const props = {
      site: siteDetail,
      thumbnailSrc: siteDetail.thumbnail,
    };

    // Output render command
    log('To render the short, run:');
    console.log(`
  npx remotion render SiteShort ${outputPath} --props='${JSON.stringify(props)}'
    `);

    // Save props to file
    const propsPath = path.join(OUTPUT_DIR, 'shorts', `${slugify(siteDetail.name)}-props.json`);
    fs.writeFileSync(propsPath, JSON.stringify(props, null, 2));
    log(`Props saved to: ${propsPath}`, 'success');

    log(`Short will be saved to: ${outputPath}`, 'success');
  } catch (error) {
    log(`Failed to generate short: ${error}`, 'error');
    throw error;
  }
}

async function generateBatchShorts(options: {
  category?: string;
  country?: string;
  limit?: number;
  useLocal?: boolean;
}): Promise<void> {
  const apiClient = createApiClient({ useLocal: options.useLocal });
  const limit = options.limit || 10;

  try {
    let sites: SiteDetail[] = [];

    if (options.category) {
      log(`Fetching sites by category: ${options.category}...`);
      const results = await apiClient.getSitesByCategory(options.category, limit);
      // Convert to SiteDetail
      for (const site of results) {
        const detail = await apiClient.getSiteById(site.id);
        if (detail) sites.push(detail);
      }
    } else if (options.country) {
      log(`Fetching sites by country: ${options.country}...`);
      const results = await apiClient.getSitesByCountry(options.country, limit);
      for (const site of results) {
        const detail = await apiClient.getSiteById(site.id);
        if (detail) sites.push(detail);
      }
    } else {
      throw new Error('Either --category or --country is required for batch generation');
    }

    log(`Found ${sites.length} sites`, 'success');

    // Generate batch script
    const batchScript = sites.map((site) => {
      const filename = `${slugify(site.name)}.mp4`;
      const outputPath = path.join(OUTPUT_DIR, 'shorts', filename);
      const props = JSON.stringify({ site, thumbnailSrc: site.thumbnail });
      return `npx remotion render SiteShort "${outputPath}" --props='${props}'`;
    }).join('\n');

    // Save batch script
    const scriptPath = path.join(OUTPUT_DIR, 'batch-render.sh');
    fs.writeFileSync(scriptPath, `#!/bin/bash\n\n${batchScript}\n`);
    log(`Batch script saved to: ${scriptPath}`, 'success');

    // Also save as Windows batch file
    const batPath = path.join(OUTPUT_DIR, 'batch-render.bat');
    const batScript = sites.map((site) => {
      const filename = `${slugify(site.name)}.mp4`;
      const outputPath = path.join(OUTPUT_DIR, 'shorts', filename);
      const props = JSON.stringify({ site, thumbnailSrc: site.thumbnail }).replace(/"/g, '\\"');
      return `npx remotion render SiteShort "${outputPath}" --props="${props}"`;
    }).join('\n');
    fs.writeFileSync(batPath, `@echo off\n\n${batScript}\n`);
    log(`Windows batch script saved to: ${batPath}`, 'success');

    log(`Run the batch script to render all ${sites.length} shorts`);
  } catch (error) {
    log(`Failed to generate batch shorts: ${error}`, 'error');
    throw error;
  }
}

async function captureAction(options: {
  action: string;
  site?: string;
  siteId?: string;
  duration?: number;
  output?: string;
  useLocal?: boolean;
}): Promise<void> {
  log(`Capture action: ${options.action}`);
  log('Capture functionality requires Puppeteer browser automation.');
  log('To use capture features, ensure the Ancient Nerds site is running.');

  // This would integrate with the capture layer
  // For now, output instructions

  console.log(`
To capture frames:

1. Start the Ancient Nerds site:
   cd ../ancient-nerds-map && npm run dev

2. Run capture with Puppeteer:
   npx ts-node -e "
     const { createBrowser } = require('./capture/browser');
     const { flyToSite } = require('./capture/actions');
     const { createRecorder } = require('./capture/recorder');

     (async () => {
       const browser = await createBrowser({ useLocal: true });
       await browser.navigateToSite();
       const page = browser.getPage();
       const recorder = createRecorder(page);

       await recorder.startSession('${options.site || 'capture'}');
       await flyToSite(page, '${options.site || 'Stonehenge'}');
       const frames = await recorder.captureFrames(${options.duration || 5});

       console.log('Captured frames:', frames.length);
       await browser.close();
     })();
   "
  `);
}

// =============================================================================
// CLI Definition
// =============================================================================

program
  .name('video-factory')
  .description('Ancient Nerds Video Factory - Generate archaeological site videos')
  .version(VERSION);

// Teaser command
program
  .command('teaser')
  .description('Generate product teaser video (16:9 horizontal)')
  .option('-o, --output <path>', 'Output file path')
  .option('--local', 'Use local development server')
  .option('--skip-capture', 'Skip browser capture, use static assets')
  .action(async (options) => {
    try {
      await generateTeaser({
        output: options.output,
        useLocal: options.local,
        skipCapture: options.skipCapture,
      });
    } catch (error) {
      process.exit(1);
    }
  });

// Short command
program
  .command('short')
  .description('Generate site short video (9:16 vertical)')
  .option('-s, --site <name>', 'Site name to generate short for')
  .option('--site-id <id>', 'Site ID to generate short for')
  .option('-c, --category <category>', 'Generate shorts for all sites in category')
  .option('--country <country>', 'Generate shorts for all sites in country')
  .option('-l, --limit <number>', 'Limit number of sites for batch generation', parseInt)
  .option('-o, --output <path>', 'Output file path')
  .option('--local', 'Use local development server')
  .option('--skip-capture', 'Skip browser capture, use static assets')
  .action(async (options) => {
    try {
      if (options.category || options.country) {
        await generateBatchShorts({
          category: options.category,
          country: options.country,
          limit: options.limit,
          useLocal: options.local,
        });
      } else {
        await generateShort({
          site: options.site,
          siteId: options.siteId,
          output: options.output,
          useLocal: options.local,
          skipCapture: options.skipCapture,
        });
      }
    } catch (error) {
      process.exit(1);
    }
  });

// Capture command
program
  .command('capture')
  .description('Capture globe footage for video')
  .requiredOption('-a, --action <type>', 'Capture action (fly-to, rotate, popup, search, filter)')
  .option('-s, --site <name>', 'Site name for fly-to action')
  .option('--site-id <id>', 'Site ID for fly-to action')
  .option('-d, --duration <seconds>', 'Capture duration in seconds', parseInt)
  .option('-o, --output <path>', 'Output directory for frames')
  .option('--local', 'Use local development server')
  .action(async (options) => {
    try {
      await captureAction({
        action: options.action,
        site: options.site,
        siteId: options.siteId,
        duration: options.duration,
        output: options.output,
        useLocal: options.local,
      });
    } catch (error) {
      process.exit(1);
    }
  });

// List command - show available sites/categories
program
  .command('list')
  .description('List available sites, categories, or sources')
  .option('-c, --categories', 'List available categories')
  .option('-s, --sources', 'List available sources')
  .option('--search <query>', 'Search for sites')
  .option('--local', 'Use local development server')
  .action(async (options) => {
    const apiClient = createApiClient({ useLocal: options.local });

    try {
      if (options.categories) {
        log('Fetching categories...');
        const categories = await apiClient.getCategories();
        console.log('\nAvailable Categories:');
        categories.forEach((cat) => {
          console.log(`  - ${cat.name} (${cat.count} sites)`);
        });
      } else if (options.sources) {
        log('Fetching sources...');
        const sources = await apiClient.getSources();
        console.log('\nAvailable Sources:');
        sources.forEach((src) => {
          console.log(`  - ${src.name}: ${src.recordCount} records`);
        });
      } else if (options.search) {
        log(`Searching for: ${options.search}...`);
        const sites = await apiClient.searchSites(options.search, 20);
        console.log(`\nFound ${sites.length} sites:`);
        sites.forEach((site) => {
          console.log(`  - ${site.name} (${site.location || 'Unknown location'})`);
        });
      } else {
        log('Specify --categories, --sources, or --search <query>');
      }
    } catch (error) {
      log(`Failed to list: ${error}`, 'error');
      process.exit(1);
    }
  });

// Info command - show configuration
program
  .command('info')
  .description('Show video factory configuration and status')
  .action(() => {
    console.log(`
Ancient Nerds Video Factory v${VERSION}
${'='.repeat(40)}

Output Directory: ${OUTPUT_DIR}
Assets Directory: ${ASSETS_DIR}

Video Formats:
  Teaser (16:9): ${VIDEO_FORMATS.teaser.width}x${VIDEO_FORMATS.teaser.height} @ ${VIDEO_FORMATS.teaser.fps}fps
  Short (9:16):  ${VIDEO_FORMATS.short.width}x${VIDEO_FORMATS.short.height} @ ${VIDEO_FORMATS.short.fps}fps

Available Commands:
  teaser              Generate product teaser
  short               Generate site short
  capture             Capture globe footage
  list                List sites/categories/sources
  info                Show this information

Examples:
  npx ts-node cli.ts teaser
  npx ts-node cli.ts short --site "Machu Picchu"
  npx ts-node cli.ts short --category "Pyramid" --limit 10
  npx ts-node cli.ts list --search "Stonehenge"
    `);
  });

// Parse and run
program.parse(process.argv);

// Show help if no command provided
if (!process.argv.slice(2).length) {
  program.outputHelp();
}
