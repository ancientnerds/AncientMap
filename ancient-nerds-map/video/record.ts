/**
 * Main video recording orchestrator.
 *
 * Starts a Vite dev server, launches Puppeteer with the globe in demo mode,
 * runs each scene script, captures via canvas stream, then encodes to MP4.
 *
 * Usage: npx tsx video/record.ts [scene-name]
 *   If scene-name is provided, only that scene is recorded.
 *   Otherwise, all scenes are recorded.
 */

import { spawn, execSync, type ChildProcess } from 'child_process'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { mkdirSync, unlinkSync } from 'fs'
import puppeteer, { type Browser, type Page } from 'puppeteer'
import type { CameraState, DemoAPI } from '../src/utils/demoApi'

// Scene imports
import { heroScene } from './scenes/hero.js'
import { globeOverviewScene } from './scenes/globe-overview.js'
import { filtersScene } from './scenes/filters.js'
import { empiresScene } from './scenes/empires.js'
import { toolsScene } from './scenes/tools.js'
import { regionalToursScene } from './scenes/regional-tours.js'
import { empireSpotlightsScene } from './scenes/empire-spotlights.js'
import { dataStoriesScene } from './scenes/data-stories.js'
import { brollScene } from './scenes/b-roll.js'
import { siteShortScenes } from './scenes/site-short.js'
import { encodeScene } from './utils/encode.js'
import { bindRecorderFunctions, injectTimeControl, StreamRecorder } from './utils/capture.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export interface SceneContext {
  page: Page
  demo: DemoAPI
  /** Fire a demo command without waiting for completion */
  fire: (code: string) => void
  recorder: StreamRecorder
  fps: number
}

export interface SceneDefinition {
  name: string
  duration: number  // seconds
  resolution: 'hero' | 'section' | 'tool' | 'short'
  /** Canvas to record; defaults to the Three.js globe. Mapbox scenes pass the Mapbox canvas. */
  canvasSelector?: string
  /** Wall-clock ms to wait per captured frame so MediaRecorder keeps up (portrait scenes need ~40). */
  frameYieldMs?: number
  /** Mapbox scenes: hold each frame until every tile of the current view is loaded. */
  waitForTiles?: boolean
  run: (ctx: SceneContext) => Promise<void>
}

const ALL_SCENES: SceneDefinition[] = [
  ...heroScene,
  ...globeOverviewScene,
  ...filtersScene,
  ...empiresScene,
  ...toolsScene,
  ...regionalToursScene,
  ...empireSpotlightsScene,
  ...dataStoriesScene,
  ...brollScene,
  ...siteShortScenes,
]

/**
 * CLI flags. Positional = scene name.
 *   --portrait        1080×1920 viewport (site shorts)
 *   --input <path>    site.json for the site-short scenes (exposed as SITE_SHORT_INPUT)
 *   --out <dir>       where the MP4s go (default: public/landing/video)
 *   --fps <n>         capture/encode rate (default 24; shorts use 60)
 */
function parseArgs(argv: string[]): { scene?: string; portrait: boolean; input?: string; out?: string; fps: number } {
  const result: { scene?: string; portrait: boolean; input?: string; out?: string; fps: number } = { portrait: false, fps: 24 }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--portrait') result.portrait = true
    else if (a === '--input') result.input = argv[++i]
    else if (a === '--out') result.out = argv[++i]
    else if (a === '--fps') result.fps = Number(argv[++i])
    else if (!a.startsWith('--')) result.scene = a
  }
  return result
}

const DEV_SERVER_PORT = 5199  // High port to avoid conflicts
const DEV_SERVER_URL = `http://localhost:${DEV_SERVER_PORT}`
const GLOBE_URL = `${DEV_SERVER_URL}/globe.html?demo=1`

async function startDevServer(): Promise<ChildProcess> {
  console.log('Starting Vite dev server...')

  const vite = spawn('npm', ['run', 'dev', '--', '--port', String(DEV_SERVER_PORT)], {
    cwd: join(__dirname, '..'),
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: true,
  })

  // Wait for server to be ready
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Dev server startup timed out')), 30000)

    vite.stdout?.on('data', (data: Buffer) => {
      const text = data.toString()
      if (text.includes('Local:') || text.includes('ready in')) {
        clearTimeout(timeout)
        resolve()
      }
    })

    vite.on('error', (err) => {
      clearTimeout(timeout)
      reject(err)
    })
  })

  console.log(`Dev server running at ${DEV_SERVER_URL}`)
  return vite
}

async function launchBrowser(portrait: boolean): Promise<{ browser: Browser; page: Page }> {
  console.log(`Launching Puppeteer (${portrait ? '1080x1920' : '1920x1080'})...`)
  const width = portrait ? 1080 : 1920
  const height = portrait ? 1920 : 1080

  const browser = await puppeteer.launch({
    headless: false,  // Use headed mode for WebGL support on Windows
    protocolTimeout: 300_000,  // 5 minutes for globe loading
    args: [
      '--use-angle=default',
      '--enable-webgl',
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-web-security',
      `--window-size=${width},${height}`,
      // Compositor stability:
      '--run-all-compositor-stages-before-draw',
      '--disable-gpu-vsync',
      '--disable-frame-rate-limit',
      '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding',
      // Enable MediaRecorder VP9 support:
      '--enable-features=WebRTCPipeWireCapturer',
    ],
    defaultViewport: {
      width,
      height,
    },
  })

  const page = await browser.newPage()
  page.on('console', (msg) => {
    const text = msg.text()
    const tagged = text.startsWith('[DemoAPI]') || text.startsWith('[TimeControl]') || text.startsWith('[StreamRecorder]')
    if (tagged || msg.type() === 'error' || msg.type() === 'warn') {
      const url = msg.location()?.url
      console.log(`  browser[${msg.type()}]:`, text.slice(0, 300), url ? `(${url.slice(0, 160)})` : '')
    }
  })
  page.on('pageerror', (err) => console.log('  browser[pageerror]:', String(err).slice(0, 300)))
  await loadGlobe(page)
  return { browser, page }
}

/** Navigate to the globe and wait until demo API reports ready. */
async function loadGlobe(page: Page): Promise<void> {
  console.log(`Navigating to ${GLOBE_URL}`)
  // 'load', not 'networkidle0': a Mapbox scene keeps tiles streaming, so the
  // reload between scenes never went network-idle and timed out. Readiness
  // is polled through the demo API below anyway.
  await page.goto(GLOBE_URL, { waitUntil: 'load', timeout: 60000 })

  console.log('Waiting for globe to be ready...')
  const readyTimeout = 120_000
  const startTime = Date.now()
  let ready = false

  while (!ready && Date.now() - startTime < readyTimeout) {
    const status = await page.evaluate(`(function() {
      var d = window.__DEMO;
      if (!d) return 'no __DEMO yet';
      if (d.isReady && d.isReady()) return 'READY';
      return 'waiting (demo API registered, globe loading...)';
    })()`).catch(() => 'evaluate failed')

    if (status === 'READY') {
      ready = true
    } else {
      const elapsed = Math.round((Date.now() - startTime) / 1000)
      process.stdout.write(`\r  [${elapsed}s] ${status}`)
      await new Promise(r => setTimeout(r, 1000))
    }
  }
  console.log('')

  if (!ready) {
    throw new Error('Globe did not become ready within timeout. Check if WebGL works in this Chrome instance.')
  }

  console.log('Globe is ready!')
}

/**
 * Get the DemoAPI proxy that calls into the page context.
 */
function createDemoProxy(page: Page): DemoAPI {
  // Use string evaluation to avoid tsx/esbuild __name injection into browser context
  const evalDemo = (code: string) => page.evaluate(code) as Promise<void>

  return {
    flyTo: (lng, lat) => evalDemo(`window.__DEMO.flyTo(${lng}, ${lat})`),
    setZoom: (d) => evalDemo(`window.__DEMO.setZoom(${d})`),
    smoothZoom: (from, to, ms) => evalDemo(`window.__DEMO.smoothZoom(${from}, ${to}, ${ms})`),
    setAutoRotate: (on) => evalDemo(`window.__DEMO.setAutoRotate(${on})`),
    setFlyToDuration: (ms) => evalDemo(`window.__DEMO.setFlyToDuration(${ms})`),
    setCameraPose: (lng, lat, d) => evalDemo(`window.__DEMO.setCameraPose(${lng}, ${lat}, ${d})`),
    setFilterMode: (mode) => evalDemo(`window.__DEMO.setFilterMode("${mode}")`),
    setAgeRange: (min, max) => evalDemo(`window.__DEMO.setAgeRange(${min}, ${max})`),
    setSelectedSources: (ids) => evalDemo(`window.__DEMO.setSelectedSources(${JSON.stringify(ids)})`),
    loadSources: (ids) => evalDemo(`window.__DEMO.loadSources(${JSON.stringify(ids)})`),
    setVectorLayer: (layer, vis) => evalDemo(`window.__DEMO.setVectorLayer("${layer}", ${vis})`),
    setSatellite: (on) => evalDemo(`window.__DEMO.setSatellite(${on})`),
    setGeoLabels: (vis) => evalDemo(`window.__DEMO.setGeoLabels(${vis})`),
    showEmpire: (id) => evalDemo(`window.__DEMO.showEmpire("${id}")`),
    hideAllEmpires: () => evalDemo(`window.__DEMO.hideAllEmpires()`),
    setPaleoshoreline: (vis, sl) => evalDemo(`window.__DEMO.setPaleoshoreline(${vis}${sl !== undefined ? ', ' + sl : ''})`),
    // Site interaction
    selectSite: (name) => evalDemo(`window.__DEMO.selectSite("${name}")`),
    deselectSite: () => evalDemo(`window.__DEMO.deselectSite()`),
    openSitePopup: (name) => evalDemo(`window.__DEMO.openSitePopup("${name}")`),
    closeAllPopups: () => evalDemo(`window.__DEMO.closeAllPopups()`),
    setDemoTooltips: (vis) => evalDemo(`window.__DEMO.setDemoTooltips(${vis})`),
    setDemoPopups: (vis) => evalDemo(`window.__DEMO.setDemoPopups(${vis})`),
    // Mapbox street-level
    enterMapbox: () => evalDemo(`window.__DEMO.enterMapbox()`),
    exitMapbox: () => evalDemo(`window.__DEMO.exitMapbox()`),
    mapboxJumpTo: (lng, lat, zoom, bearing, pitch) => evalDemo(`window.__DEMO.mapboxJumpTo(${lng}, ${lat}, ${zoom}${bearing !== undefined ? ', ' + bearing : ''}${pitch !== undefined ? ', ' + pitch : ''})`),
    setTerrain: (exaggeration) => evalDemo(`window.__DEMO.setTerrain(${exaggeration === null ? 'null' : exaggeration})`),
    mapboxOrbit: (lng, lat, zoom, pitch, b0, b1, ms) => evalDemo(`window.__DEMO.mapboxOrbit(${lng}, ${lat}, ${zoom}, ${pitch}, ${b0}, ${b1}, ${ms})`),
    mapboxWaitIdle: (timeoutMs) => evalDemo(`window.__DEMO.mapboxWaitIdle(${timeoutMs ?? 15000})`),
    setMapboxStyleUrl: (url) => evalDemo(`window.__DEMO.setMapboxStyleUrl(${JSON.stringify(url)})`),
    mapboxPath: (keyframes, ms) => evalDemo(`window.__DEMO.mapboxPath(${JSON.stringify(keyframes)}, ${ms})`),
    mapboxJumpToPathPose: (keyframes, t) => evalDemo(`window.__DEMO.mapboxJumpToPathPose(${JSON.stringify(keyframes)}, ${t})`),
    setMapboxFog: (spec) => evalDemo(`window.__DEMO.setMapboxFog(${JSON.stringify(spec)})`),
    hideMapboxLayers: (pattern) => page.evaluate(`window.__DEMO.hideMapboxLayers(${JSON.stringify(pattern)})`) as Promise<number>,
    setMapboxRasterFade: (ms) => evalDemo(`window.__DEMO.setMapboxRasterFade(${ms})`),
    mapboxTilesLoaded: () => { throw new Error('mapboxTilesLoaded is polled inside the capture loop') },
    // UI control
    hideAllUI: () => evalDemo(`window.__DEMO.hideAllUI()`),
    showUI: () => evalDemo(`window.__DEMO.showUI()`),
    getCameraState: () => page.evaluate('window.__DEMO.getCameraState()') as Promise<CameraState>,
    isReady: () => { throw new Error('Use page.evaluate for isReady') },
    waitUntilReady: () => evalDemo(`window.__DEMO.waitUntilReady()`),
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const requestedScene = args.scene
  if (args.input) process.env.SITE_SHORT_INPUT = args.input

  const baseDir = __dirname
  const outputDir = args.out ?? join(baseDir, '..', 'public', 'landing', 'video')
  const webmDir = join(baseDir, 'output')

  // Ensure output dirs exist
  mkdirSync(webmDir, { recursive: true })
  mkdirSync(outputDir, { recursive: true })

  // Determine which scenes to run
  let scenes = ALL_SCENES
  if (requestedScene) {
    const wanted = requestedScene.split(',')
    scenes = ALL_SCENES.filter(s => wanted.includes(s.name))
    if (scenes.length !== wanted.length) {
      console.error(`Unknown scene(s) in: ${requestedScene}`)
      console.error(`Available scenes: ${ALL_SCENES.map(s => s.name).join(', ')}`)
      process.exit(1)
    }
  }

  let devServer: ChildProcess | null = null
  let browser: Browser | null = null

  try {
    // Start dev server
    devServer = await startDevServer()

    // Launch browser
    const { browser: b, page } = await launchBrowser(args.portrait)
    browser = b
    await bindRecorderFunctions(page)

    // Create demo API proxy
    const demo = createDemoProxy(page)

    // Hide all UI for clean recording
    await demo.hideAllUI()

    // Inject synthetic time control — freezes performance.now() and Date.now()
    // so every frame advances by exactly 1000/fps ms. This eliminates flicker
    // caused by variable deltaTime in the animation loop.
    const fps = args.fps
    console.log('\nInjecting synthetic time control...')
    await injectTimeControl(page, fps)

    // Record each scene
    for (let i = 0; i < scenes.length; i++) {
      const scene = scenes[i]

      // Reload the globe between scenes to get clean state.
      // Without this, Chrome tab throttling + accumulated state from
      // earlier scenes causes later clips to capture static frames.
      if (i > 0) {
        console.log('\nReloading globe for clean state...')
        await loadGlobe(page)
        await demo.hideAllUI()
        // Re-inject time control after page reload
        await injectTimeControl(page, fps)
      }

      console.log(`\n${'='.repeat(50)}`)
      console.log(`Recording scene: ${scene.name} (${scene.duration}s)`)
      console.log('='.repeat(50))

      // Fresh StreamRecorder per scene; it starts on the scene's first capture()
      // so the setup phase (tiles, poses) never leaks into frame 0.
      const recorder = new StreamRecorder({ fps, canvasSelector: scene.canvasSelector, frameYieldMs: scene.frameYieldMs, waitForTiles: scene.waitForTiles })

      const ctx: SceneContext = {
        page,
        demo,
        fire: (code: string) => { page.evaluate(code).catch(() => {}) },
        recorder,
        fps,
      }

      // Run the scene choreography + capture
      await scene.run(ctx)

      // Stop recorder and save WebM
      const webmPath = join(webmDir, `${scene.name}.webm`)
      await recorder.stop(page, webmPath)

      // Encode WebM to MP4
      console.log(`\nEncoding ${scene.name}...`)
      const result = encodeScene(scene.name, webmPath, outputDir, scene.duration, fps)
      console.log(`  MP4: ${result.mp4}`)
      console.log(`  Fast: ${result.fast}`)

      // Clean up intermediate WebM
      try { unlinkSync(webmPath) } catch {}
    }

    console.log('\n\nAll scenes recorded and encoded!')
    console.log(`Output: ${outputDir}`)

  } finally {
    if (browser) await browser.close()
    killDevServer(devServer)
  }
}

/**
 * Kill the dev server and ALL child processes.
 * On Windows, `child.kill()` only kills the parent npm process,
 * leaving the Vite child alive and eating CPU. Use taskkill /T to
 * kill the entire process tree.
 */
function killDevServer(devServer: ChildProcess | null) {
  if (!devServer?.pid) return
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /PID ${devServer.pid} /F /T`, { stdio: 'ignore' })
    } else {
      // On Unix, kill the process group
      process.kill(-devServer.pid, 'SIGTERM')
    }
  } catch {
    // Process may already be dead
    devServer.kill()
  }
  console.log('Dev server stopped.')
}

// Also clean up on unexpected exit (Ctrl+C, crashes)
process.on('SIGINT', () => { process.exit(1) })
process.on('SIGTERM', () => { process.exit(1) })

main().catch(err => {
  console.error('Recording failed:', err)
  process.exit(1)
})
