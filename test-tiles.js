const puppeteer = require('puppeteer');

async function runTest() {
  console.log('='.repeat(60));
  console.log('TILE LOADING PERFORMANCE TEST - FINAL');
  console.log('='.repeat(60));

  const browser = await puppeteer.launch({
    headless: false,
    args: ['--no-sandbox', '--start-maximized']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });

  page.on('console', msg => {
    if (msg.type() === 'log') console.log(`  [page] ${msg.text()}`);
  });

  try {
    await page.goto('http://localhost:5173/tile-debug.html', { waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForFunction(() => window.camera !== undefined, { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1500));
    console.log('Page loaded.\n');

    async function setCamera(lat, lng, distance) {
      await page.evaluate(({ lat, lng, distance }) => {
        const phi = (90 - lat) * Math.PI / 180;
        const theta = (lng + 180) * Math.PI / 180;
        window.camera.position.set(
          -distance * Math.sin(phi) * Math.cos(theta),
          distance * Math.cos(phi),
          distance * Math.sin(phi) * Math.sin(theta)
        );
        window.controls.target.set(0, 0, 0);
        window.controls.update();
      }, { lat, lng, distance });
    }

    // Clear cache between tests
    async function clearAndLoad(zoom) {
      await page.evaluate(() => {
        window.tileGroup.clear();
        window.loadedTiles.clear();
      });
      const start = Date.now();
      await page.evaluate((z) => window.loadTilesForZoom(z), zoom);
      return Date.now() - start;
    }

    // ========== TEST 1: Globe ==========
    console.log('TEST 1: Globe View (z2)');
    console.log('-'.repeat(40));
    await setCamera(30, 0, 3.0);
    const time1 = await clearAndLoad(2);
    const tiles1 = await page.evaluate(() => window.loadedTiles.size);
    await page.screenshot({ path: 'test1-globe.png' });
    console.log(`  Tiles: ${tiles1} | Time: ${time1}ms`);
    console.log(`  Screenshot: test1-globe.png\n`);

    // ========== TEST 2: Europe ==========
    console.log('TEST 2: Europe (z6)');
    console.log('-'.repeat(40));
    await setCamera(45, 10, 1.5);
    const time2 = await clearAndLoad(6);
    const tiles2 = await page.evaluate(() => window.loadedTiles.size);
    await page.screenshot({ path: 'test2-europe.png' });
    console.log(`  Tiles: ${tiles2} | Time: ${time2}ms`);
    console.log(`  Screenshot: test2-europe.png\n`);

    // ========== TEST 3: Malta z10 ==========
    console.log('TEST 3: Malta (z10)');
    console.log('-'.repeat(40));
    await setCamera(35.9, 14.5, 1.15);
    const time3 = await clearAndLoad(10);
    const tiles3 = await page.evaluate(() => window.loadedTiles.size);
    await page.screenshot({ path: 'test3-malta-z10.png' });
    console.log(`  Tiles: ${tiles3} | Time: ${time3}ms`);
    console.log(`  Screenshot: test3-malta-z10.png\n`);

    // ========== TEST 4: Malta z14 (high detail) ==========
    console.log('TEST 4: Malta Airport (z14 - high detail)');
    console.log('-'.repeat(40));
    await setCamera(35.8575, 14.4775, 1.02);
    const time4 = await clearAndLoad(14);
    const tiles4 = await page.evaluate(() => window.loadedTiles.size);
    const fps = await page.evaluate(() => document.getElementById('perf-info')?.textContent);
    await page.screenshot({ path: 'test4-malta-z14.png' });
    console.log(`  Tiles: ${tiles4} | Time: ${time4}ms | ${fps}`);
    console.log(`  Screenshot: test4-malta-z14.png\n`);

    // ========== SUMMARY ==========
    console.log('='.repeat(60));
    console.log('FINAL RESULTS');
    console.log('='.repeat(60));
    console.log(`Globe (z2):    ${tiles1} tiles in ${time1}ms`);
    console.log(`Europe (z6):   ${tiles2} tiles in ${time2}ms`);
    console.log(`Malta (z10):   ${tiles3} tiles in ${time3}ms`);
    console.log(`Malta (z14):   ${tiles4} tiles in ${time4}ms`);

    const totalTime = time1 + time2 + time3 + time4;
    const avgTime = Math.round(totalTime / 4);
    console.log(`\nTotal: ${totalTime}ms | Average: ${avgTime}ms per zoom level`);

    if (avgTime < 1000) {
      console.log('\n✓ FAST - Under 1 second average');
    }
    if (tiles4 >= 25) {
      console.log('✓ HIGH DETAIL - 25+ tiles at z14');
    }

    console.log('\nBrowser staying open for 10 seconds...');
    await new Promise(r => setTimeout(r, 10000));

  } catch (err) {
    console.error('Test failed:', err.message);
  } finally {
    await browser.close();
  }
}

runTest();
