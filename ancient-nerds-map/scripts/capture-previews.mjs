/**
 * capture-previews.mjs — one JPEG per portal page, taken from the live site.
 *
 * Owner, 2026-09-10: "On the phone everything flickers quite a bit — are
 * screenshots maybe better after all?" The answer is both. Every portal on the
 * landing page carries a poster image of the page it points at; only
 * hover-capable desktops mount the live iframe on top of it (PagePortal.tsx).
 * Phones and tablets never load a second page — they see this file.
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

/** The three pages the landing portals point at, named after their poster. */
const PAGES = [
  { name: 'news', path: '/news.html' },
  { name: 'articles', path: '/articles.html' },
  { name: 'research', path: '/research/' },
]

/** The portal frame is laid out at 1280×800 — the poster has to match it. */
const VIEWPORT = { width: 1280, height: 800, deviceScaleFactor: 1 }
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
  for (const { name, path } of PAGES) {
    const page = await browser.newPage()
    await page.setViewport(VIEWPORT)
    const url = `${BASE}${path}`
    await page.goto(url, { waitUntil: 'networkidle2' })
    await new Promise(done => setTimeout(done, SETTLE_MS))
    // The consent bar is fixed to the bottom of every page and would sit in
    // every poster; a visitor dismisses it once, the screenshot cannot.
    await page.evaluate(() => document.querySelector('#cookie-notice')?.remove())
    const file = join(OUT, `${name}.jpg`)
    await page.screenshot({ path: file, type: 'jpeg', quality: 82 })
    await page.close()
    const { size } = await stat(file)
    console.log(`${url} -> ${file} (${size.toLocaleString('en-US')} bytes)`)
  }
} finally {
  await browser.close()
}
