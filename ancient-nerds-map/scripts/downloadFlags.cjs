/**
 * Script to download country flag images from Flagpedia API
 * Downloads 64x48 waving flag webp images for all countries
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const FLAGS_DIR = path.join(__dirname, '..', 'public', 'flags');
const CODES_URL = 'https://flagcdn.com/en/codes.json';
const FLAG_BASE_URL = 'https://flagcdn.com/64x48';

// Ensure flags directory exists
if (!fs.existsSync(FLAGS_DIR)) {
  fs.mkdirSync(FLAGS_DIR, { recursive: true });
  console.log(`Created directory: ${FLAGS_DIR}`);
}

/**
 * Fetch JSON data from a URL
 */
function fetchJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      if (res.statusCode !== 200) {
        reject(new Error(`Failed to fetch ${url}: ${res.statusCode}`));
        return;
      }

      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

/**
 * Download a file from URL to local path
 */
function downloadFile(url, destPath) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(destPath);

    https.get(url, (res) => {
      if (res.statusCode === 302 || res.statusCode === 301) {
        // Handle redirect
        file.close();
        fs.unlinkSync(destPath);
        downloadFile(res.headers.location, destPath).then(resolve).catch(reject);
        return;
      }

      if (res.statusCode !== 200) {
        file.close();
        fs.unlinkSync(destPath);
        reject(new Error(`Failed to download ${url}: ${res.statusCode}`));
        return;
      }

      res.pipe(file);
      file.on('finish', () => {
        file.close();
        resolve();
      });
    }).on('error', (err) => {
      file.close();
      fs.unlink(destPath, () => {}); // Delete partial file
      reject(err);
    });
  });
}

/**
 * Sleep for specified milliseconds
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  console.log('Fetching country codes from Flagpedia...');

  let countryCodes;
  try {
    countryCodes = await fetchJson(CODES_URL);
  } catch (err) {
    console.error('Failed to fetch country codes:', err.message);
    process.exit(1);
  }

  const codes = Object.keys(countryCodes);
  console.log(`Found ${codes.length} country codes`);

  let downloaded = 0;
  let failed = 0;
  let skipped = 0;

  for (const code of codes) {
    const flagUrl = `${FLAG_BASE_URL}/${code}.webp`;
    const destPath = path.join(FLAGS_DIR, `${code}.webp`);

    // Skip if already exists
    if (fs.existsSync(destPath)) {
      skipped++;
      continue;
    }

    try {
      await downloadFile(flagUrl, destPath);
      downloaded++;
      process.stdout.write(`\rDownloaded: ${downloaded} | Skipped: ${skipped} | Failed: ${failed}`);

      // Small delay to be nice to the server
      await sleep(50);
    } catch (err) {
      failed++;
      console.error(`\nFailed to download ${code}: ${err.message}`);
    }
  }

  console.log(`\n\nDone!`);
  console.log(`Downloaded: ${downloaded}`);
  console.log(`Skipped (already exist): ${skipped}`);
  console.log(`Failed: ${failed}`);
  console.log(`Total flags in directory: ${fs.readdirSync(FLAGS_DIR).filter(f => f.endsWith('.webp')).length}`);
}

main();
