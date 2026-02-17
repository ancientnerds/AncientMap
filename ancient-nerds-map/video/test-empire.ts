/**
 * Quick test: verify that showEmpire actually renders empire borders.
 * Takes screenshots before and after calling showEmpire.
 */
import puppeteer from 'puppeteer'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const GLOBE_URL = 'http://localhost:5199/globe.html?demo=1'

async function main() {
  console.log('Launching browser...')
  const browser = await puppeteer.launch({
    headless: false,
    args: ['--use-angle=default', '--enable-webgl', '--no-sandbox', '--window-size=1280,720'],
    defaultViewport: { width: 1280, height: 720 },
  })

  const page = await browser.newPage()
  console.log(`Navigating to ${GLOBE_URL}`)
  await page.goto(GLOBE_URL, { waitUntil: 'networkidle0', timeout: 60000 })

  // Wait for globe ready
  console.log('Waiting for globe to be ready...')
  let ready = false
  const start = Date.now()
  while (!ready && Date.now() - start < 120000) {
    const status = await page.evaluate(`(function() {
      var d = window.__DEMO;
      if (!d) return 'no __DEMO';
      if (d.isReady && d.isReady()) return 'READY';
      return 'waiting...';
    })()`).catch(() => 'error')
    if (status === 'READY') { ready = true; break }
    process.stdout.write(`\r  ${status}`)
    await new Promise(r => setTimeout(r, 1000))
  }
  console.log('\nGlobe ready!')

  // Hide UI
  await page.evaluate('window.__DEMO.hideAllUI()')
  await page.evaluate('window.__DEMO.setAutoRotate(true)')
  await new Promise(r => setTimeout(r, 500))

  // Screenshot 1: Before empire
  const outDir = join(__dirname, 'output')
  const shot1 = join(outDir, 'test-before-empire.png')
  await page.screenshot({ path: shot1 })
  console.log(`Screenshot BEFORE empire: ${shot1}`)

  // Check what showEmpire returns and if it exists
  const apiCheck = await page.evaluate(`(function() {
    var d = window.__DEMO;
    return {
      hasShowEmpire: typeof d.showEmpire === 'function',
      hasHideAllEmpires: typeof d.hideAllEmpires === 'function',
      keys: Object.keys(d)
    };
  })()`)
  console.log('Demo API check:', JSON.stringify(apiCheck, null, 2))

  // Fly to Rome first
  console.log('Flying to Rome...')
  await page.evaluate('window.__DEMO.flyTo(12.49, 41.89)')
  await new Promise(r => setTimeout(r, 1000))

  // Now call showEmpire and wait
  console.log('Calling showEmpire("roman")...')
  const empireResult = await page.evaluate(`
    (async function() {
      try {
        await window.__DEMO.showEmpire("roman");
        return 'resolved OK';
      } catch(e) {
        return 'error: ' + e.message;
      }
    })()
  `)
  console.log('showEmpire result:', empireResult)

  // Wait for render
  await new Promise(r => setTimeout(r, 2000))

  // Screenshot 2: After empire
  const shot2 = join(outDir, 'test-after-empire.png')
  await page.screenshot({ path: shot2 })
  console.log(`Screenshot AFTER empire: ${shot2}`)

  // Check visible empires state
  const empireState = await page.evaluate(`
    (function() {
      // Try to find React state - check if there are any empire-related DOM elements
      var empireElements = document.querySelectorAll('[class*="empire"]');
      var empireClasses = Array.from(empireElements).map(e => e.className).slice(0, 10);

      // Check if there are any canvas-related empire renders
      var canvases = document.querySelectorAll('canvas');

      return {
        empireElementCount: empireElements.length,
        empireClasses: empireClasses,
        canvasCount: canvases.length,
      };
    })()
  `)
  console.log('Empire DOM state:', JSON.stringify(empireState, null, 2))

  // Try the Inca empire too
  console.log('\nNow testing Inca empire...')
  await page.evaluate('window.__DEMO.hideAllEmpires()')
  await new Promise(r => setTimeout(r, 500))

  console.log('Flying to Machu Picchu...')
  await page.evaluate('window.__DEMO.flyTo(-72.545, -13.163)')
  await new Promise(r => setTimeout(r, 1000))

  console.log('Calling showEmpire("inca")...')
  const incaResult = await page.evaluate(`
    (async function() {
      try {
        await window.__DEMO.showEmpire("inca");
        return 'resolved OK';
      } catch(e) {
        return 'error: ' + e.message;
      }
    })()
  `)
  console.log('showEmpire("inca") result:', incaResult)
  await new Promise(r => setTimeout(r, 2000))

  const shot3 = join(outDir, 'test-inca-empire.png')
  await page.screenshot({ path: shot3 })
  console.log(`Screenshot INCA empire: ${shot3}`)

  await browser.close()
  console.log('\nDone! Check the screenshots in video/output/')
}

main().catch(e => { console.error(e); process.exit(1) })
