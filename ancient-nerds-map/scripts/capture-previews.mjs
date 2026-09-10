/**
 * capture-previews.mjs — the portal posters, taken from the live site: two
 * WebPs per page, the 1280×800 frame and the same frame at half scale.
 *
 * Owner, 2026-09-10: "Those are no screenshots! It lags like hell! The
 * landing page must load super fast — and mobile first!" Every portal on the
 * landing page is a poster of the page it points at and nothing else
 * (PagePortal.tsx); the 640 px file is what a phone downloads.
 *
 * The screenshots are not built into the bundle. They are captured against
 * production by .github/workflows/previews.yml (after every successful deploy
 * and every six hours) and copied to the VPS into public/data/previews/, which
 * nginx serves under /data/ with `Cache-Control: public, max-age=3600` — so a
 * poster is at most six hours behind the page it shows and no deploy is needed
 * to refresh it.
 *
 * Run it by hand against any origin:
 *   PREVIEW_BASE_URL=http://localhost:5173 PREVIEW_OUT_DIR=/tmp/out npm run previews
 */
import { mkdir, stat } from 'node:fs/promises'
import { join, resolve } from 'node:path'

import puppeteer from 'puppeteer'

/**
 * The four pages the landing portals show, named after their poster. `ready`
 * is what a page has to have painted before it is worth a screenshot: the
 * search is empty until someone types or hits Random, so the portal opens it
 * on `?random` (SearchPage.tsx) and the poster waits for the first card.
 */
const PAGES = [
  { name: 'news', path: '/news.html' },
  { name: 'articles', path: '/articles.html' },
  { name: 'research', path: '/research/' },
  { name: 'search', path: '/search.html?random', ready: '.site-card' },
]

/** The portal box is 16/10 — the capture is a desktop page at 1280×800. */
const VIEWPORT = { width: 1280, height: 800 }
/** The full frame, and the same frame rasterised at half the pixel ratio. */
const SCALES = [
  { suffix: '', deviceScaleFactor: 1 },
  { suffix: '-640', deviceScaleFactor: 0.5 },
]
/** networkidle2 fires before the last images decode and the fonts swap in. */
const SETTLE_MS = 1500

const BASE = process.env.PREVIEW_BASE_URL ?? 'https://ancientnerds.com'
const OUT = resolve(process.env.PREVIEW_OUT_DIR ?? 'previews-out')

await mkdir(OUT, { recursive: true })

const browser = await puppeteer.launch({
  headless: true,
  // The GitHub runner has no user namespaces for Chrome's sandbox.
  args: ['--no-sandbox'],
})

try {
  for (const { name, path, ready } of PAGES) {
    const page = await browser.newPage()
    await page.setViewport({ ...VIEWPORT, deviceScaleFactor: 1 })
    const url = `${BASE}${path}`
    await page.goto(url, { waitUntil: 'networkidle2' })
    if (ready) await page.waitForSelector(ready, { timeout: 60_000 })
    await new Promise(done => setTimeout(done, SETTLE_MS))
    // The consent bar is fixed to the bottom of every page and would sit in
    // every poster; a visitor dismisses it once, the screenshot cannot.
    await page.evaluate(() => document.querySelector('#cookie-notice')?.remove())
    for (const { suffix, deviceScaleFactor } of SCALES) {
      // Same layout, fewer pixels: the ratio changes the raster, not the page.
      await page.setViewport({ ...VIEWPORT, deviceScaleFactor })
      const file = join(OUT, `${name}${suffix}.webp`)
      await page.screenshot({ path: file, type: 'webp', quality: 80 })
      const { size } = await stat(file)
      console.log(`${url} -> ${file} (${size.toLocaleString('en-US')} bytes)`)
    }
    await page.close()
  }
} finally {
  await browser.close()
}
