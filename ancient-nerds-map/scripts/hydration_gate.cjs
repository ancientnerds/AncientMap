/**
 * Hydration gate (react-ssr Task 15 Step 2+3): load every spliced page in a
 * real browser, collect console errors and page errors, and compare the
 * link count of the served HTML against the DOM after hydration settles.
 *
 * Every console error is a finding; React 18 production hydration
 * mismatches surface as "Minified React error #418/#423/#425".
 *
 *   node scripts/hydration_gate.cjs http://localhost:8099
 */
const puppeteer = require('puppeteer')

const NAMES = [
  'story',
  'storyArchive',
  'site',
  'sitesIndex',
  'country',
  'research',
  'researchIndex',
  'article',
  'articleIndex',
]

;(async () => {
  const base = process.argv[2] || 'http://localhost:8099'
  const browser = await puppeteer.launch({ args: ['--no-sandbox'] })
  const results = {}

  for (const name of NAMES) {
    const url = `${base}/hydr_${name}.html`
    const page = await browser.newPage()
    const errors = []
    page.on('console', m => {
      if (m.type() === 'error' || m.type() === 'warning') {
        errors.push(`[console.${m.type()}] ${m.text()}`)
      }
    })
    page.on('pageerror', e => errors.push(`[pageerror] ${e.message}`))
    page.on('requestfailed', r =>
      errors.push(`[requestfailed] ${r.url()} ${r.failure()?.errorText || ''}`),
    )

    const resp = await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 })
    const served = await resp.text()
    const linksBefore = (served.match(/<a[\s>]/gi) || []).length
    const h1Before = (served.match(/<h1[\s>]/gi) || []).length

    await new Promise(r => setTimeout(r, 2000)) // let hydration + effects settle

    const after = await page.evaluate(() => ({
      links: document.querySelectorAll('a').length,
      h1: document.querySelectorAll('h1').length,
      rootChildren: document.getElementById('root')?.children.length ?? 0,
      textLen: (document.getElementById('root')?.textContent || '').length,
    }))
    results[name] = { linksBefore, h1Before, after, errors }
    await page.close()
  }

  await browser.close()
  console.log(JSON.stringify(results, null, 1))
})()
