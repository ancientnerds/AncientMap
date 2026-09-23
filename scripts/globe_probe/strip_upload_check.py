"""Prove the basemap upload paths in a real WebGL2 context.

The unit tests (ancient-nerds-map/src/services/__tests__/basemapUpgrade.test.ts)
pin the call sequence against a duck-typed renderer. This script runs the real
module (bundled with the project's esbuild) against three's real WebGLRenderer
in a real browser and reads the texels back through a framebuffer.

An image is decoded with ``decodeBasemap`` (default createImageBitmap
options) and uploaded three ways: ``uploadInStrips`` (one strip per animation
frame), ``uploadWhole``, and the legacy path the globe used before
(``THREE.Texture(<img>)`` with the default ``flipY = true``, which is what
``TextureLoader`` produced). Then:

1. Level 0 and mip level 1 of the strip and whole textures are compared with
   the legacy texture mirrored top to bottom: the legacy texture held image
   row H-1-r in row r for UVs ``(u, 1 - v)``, the ImageBitmap textures hold
   image row r for UVs ``(u, v)``, so both sample the same texel at every
   point of the globe. Exact equality is reported; the pass criterion is a
   maximum channel difference of ``--tolerance`` (default 0).
2. Without ``--image`` the image is a lossless PNG with a position-coded
   pattern (R = x & 255, G = y & 255, B = high bits of x and y), and texture
   row r must hold image row r: north at t = 0, which the basemap UVs
   ``(u, v)`` in sceneInit sample at the north pole.
3. No GL error is pending afterwards, the strip source texture never entered
   the renderer's properties (so the copies took the texSubImage2D path), and
   the destination ends at version 1 with ``generateMipmaps`` back at its
   allocation value (false).

Measured 2026-09-24: every real basemap file (low, med, and the 16383-wide
high tier, gray and satellite) matches the mirrored legacy texture byte for
byte at level 0 and level 1 in Chromium (SwiftShader and a real D3D11 GPU)
and in Playwright's WebKit 26.6. The synthetic pattern differs by 1 in about
0.1 % of the channels in WebKit, because WebKit colour-tags the PNG that
``canvas.toBlob`` writes; run the pattern there with ``--tolerance 1``.

Usage (from the repo root, with the globeload venv):
    python scripts/globe_probe/strip_upload_check.py [--size 1024x512 | --image FILE] [--rows 64]
        [--gpu] [--finish] [--browser chromium|webkit] [--tolerance N]

Writes output/globe_probe/strip-<timestamp>/report.json and exits 1 if any
check fails.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "ancient-nerds-map"

ENTRY = r"""
import * as THREE from '@APP@/node_modules/three/build/three.module.js'
import { decodeBasemap, nextAnimationFrame, uploadInStrips, uploadWhole } from '@APP@/src/services/basemapUpgrade'

function pattern(W: number, H: number): ImageData {
  const img = new ImageData(W, H)
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4
      img.data[i] = x & 255
      img.data[i + 1] = y & 255
      img.data[i + 2] = (((x >> 8) & 15) << 4) | ((y >> 8) & 15)
      img.data[i + 3] = 255
    }
  }
  return img
}

function readLevel(gl: WebGL2RenderingContext, renderer: THREE.WebGLRenderer, tex: THREE.Texture, level: number, W: number, H: number): Uint8Array {
  const w = Math.max(1, W >> level)
  const h = Math.max(1, H >> level)
  const handle = (renderer.properties.get(tex) as { __webglTexture: WebGLTexture }).__webglTexture
  const fb = gl.createFramebuffer()
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb)
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, handle, level)
  const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER)
  if (status !== gl.FRAMEBUFFER_COMPLETE) throw new Error('framebuffer incomplete: 0x' + status.toString(16))
  const out = new Uint8Array(w * h * 4)
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, out)
  gl.bindFramebuffer(gl.FRAMEBUFFER, null)
  gl.deleteFramebuffer(fb)
  return out
}

/** The rows of an RGBA image in reverse order. */
function mirrorRows(a: Uint8Array, W: number, H: number): Uint8Array {
  const out = new Uint8Array(a.length)
  for (let r = 0; r < H; r++) out.set(a.subarray((H - 1 - r) * W * 4, (H - r) * W * 4), r * W * 4)
  return out
}

/** Largest channel difference and the share of channels that differ at all. */
function compare(a: Uint8Array | Uint8ClampedArray, b: Uint8Array | Uint8ClampedArray) {
  if (a.length !== b.length) return { maxAbsDiff: 256, differingShare: 1 }
  let max = 0
  let n = 0
  for (let i = 0; i < a.length; i++) {
    const d = Math.abs(a[i] - b[i])
    if (d > 0) n++
    if (d > max) max = d
  }
  return { maxAbsDiff: max, differingShare: n / a.length }
}

async function run(W: number, H: number, rows: number, finish: boolean, imageB64: string | null) {
  let blob: Blob
  let img: ImageData | null = null
  if (imageB64 !== null) {
    const bytes = Uint8Array.from(atob(imageB64), c => c.charCodeAt(0))
    blob = new Blob([bytes], { type: 'image/webp' })
  } else {
    const src = document.createElement('canvas')
    src.width = W
    src.height = H
    img = pattern(W, H)
    src.getContext('2d')!.putImageData(img, 0, 0)
    blob = await new Promise((resolve, reject) => src.toBlob(b => (b ? resolve(b) : reject(new Error('toBlob'))), 'image/png'))
  }
  const url = URL.createObjectURL(blob)

  const renderer = new THREE.WebGLRenderer({ canvas: document.createElement('canvas') })
  const gl = renderer.getContext() as WebGL2RenderingContext
  const ctrl = new AbortController()

  // strip path, timed per copy (with finish including the GPU work, otherwise main-thread time only)
  const copyMs: number[] = []
  let stripSource: THREE.Texture | null = null
  const copy = renderer.copyTextureToTexture.bind(renderer)
  renderer.copyTextureToTexture = ((s: THREE.Texture, d: THREE.Texture, ...rest: unknown[]) => {
    stripSource = s
    const t0 = performance.now()
    ;(copy as (...a: unknown[]) => void)(s, d, ...rest)
    if (finish) gl.finish()
    copyMs.push(performance.now() - t0)
  }) as typeof renderer.copyTextureToTexture
  // main-thread time of the allocation and of every synchronous GL error check
  const initMs: number[] = []
  const getErrorMs: number[] = []
  const init = renderer.initTexture.bind(renderer)
  renderer.initTexture = ((t: THREE.Texture) => { const t1 = performance.now(); init(t); initMs.push(performance.now() - t1) }) as typeof renderer.initTexture
  const getError = gl.getError.bind(gl)
  gl.getError = () => { const t1 = performance.now(); const e = getError(); getErrorMs.push(performance.now() - t1); return e }
  const bitmapA = await decodeBasemap(url, ctrl.signal)
  W = bitmapA.width
  H = bitmapA.height
  const t0 = performance.now()
  const strips = await uploadInStrips(renderer, bitmapA, { rows, nextFrame: nextAnimationFrame, signal: ctrl.signal })
  const stripWallMs = performance.now() - t0
  renderer.copyTextureToTexture = copy
  renderer.initTexture = init
  gl.getError = getError
  const stripInitMs = initMs.map(v => Math.round(v * 10) / 10)
  const stripGetErrorMs = getErrorMs.map(v => Math.round(v * 10) / 10)

  // whole path (the start tier)
  const bitmapB = await decodeBasemap(url, ctrl.signal)
  const whole = uploadWhole(renderer, bitmapB)

  // legacy path: an <img> through THREE.Texture with the default flipY = true (TextureLoader)
  const el = new Image()
  el.src = url
  await el.decode()
  const legacy = new THREE.Texture(el)
  legacy.colorSpace = THREE.SRGBColorSpace
  legacy.generateMipmaps = true
  legacy.minFilter = THREE.LinearMipmapLinearFilter
  legacy.magFilter = THREE.LinearFilter
  legacy.anisotropy = 16
  legacy.needsUpdate = true
  renderer.initTexture(legacy)

  // legacy rows mirrored: what the (u, v) UVs sample equals what the old (u, 1 - v) UVs sampled
  const W1 = Math.max(1, W >> 1)
  const H1 = Math.max(1, H >> 1)
  const L0 = { strips: readLevel(gl, renderer, strips, 0, W, H), whole: readLevel(gl, renderer, whole, 0, W, H), legacy: mirrorRows(readLevel(gl, renderer, legacy, 0, W, H), W, H) }
  const L1 = { strips: readLevel(gl, renderer, strips, 1, W, H), legacy: mirrorRows(readLevel(gl, renderer, legacy, 1, W, H), W1, H1) }

  // Pattern only: texture row r against image rows r (expected) and H-1-r (flipped).
  let orientation: { unflipped: ReturnType<typeof compare>; flipped: ReturnType<typeof compare> } | null = null
  if (img) {
    const pixels = new Uint8Array(img.data.buffer.slice(0))
    orientation = { unflipped: compare(L0.strips, pixels), flipped: compare(L0.strips, mirrorRows(pixels, W, H)) }
  }
  const level1NonZero = L1.strips.some((v, i) => i % 4 !== 3 && v !== 0)
  const glError = gl.getError()
  const sourceRegistered = stripSource !== null && (renderer.properties as unknown as { has: (o: object) => boolean }).has(stripSource)
  const sortedMs = [...copyMs].sort((a, b) => a - b)
  const debug = gl.getExtension('WEBGL_debug_renderer_info')
  return {
    width: W, height: H, rows,
    renderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    copies: copyMs.length,
    copyMs: copyMs.map(v => Math.round(v * 10) / 10),
    copyMsMedian: sortedMs[Math.floor(sortedMs.length / 2)],
    copyMsMax: sortedMs[sortedMs.length - 1],
    stripWallMs,
    stripInitMs,
    stripGetErrorMs,
    stripsVsLegacyLevel0: compare(L0.strips, L0.legacy),
    wholeVsLegacyLevel0: compare(L0.whole, L0.legacy),
    stripsVsLegacyLevel1: compare(L1.strips, L1.legacy),
    orientation,
    level1NonZero,
    glError,
    sourceRegistered,
    stripsGenerateMipmapsAtEnd: strips.generateMipmaps,
    stripsVersion: strips.version,
    bitmapClosedAfterStrips: bitmapA.width === 0 && bitmapA.height === 0,
  }
}

;(window as unknown as { runStripCheck: typeof run }).runStripCheck = run
"""


def bundle(tmp: Path) -> str:
    entry = tmp / "entry.ts"
    entry.write_text(ENTRY.replace("@APP@", APP.as_posix()), encoding="utf-8")
    out = tmp / "bundle.js"
    subprocess.run(
        [
            "node",
            str(APP / "node_modules" / "esbuild" / "bin" / "esbuild"),
            str(entry),
            "--bundle",
            "--format=iife",
            "--target=es2020",
            f"--outfile={out}",
            "--log-level=warning",
        ],
        check=True,
        cwd=APP,
    )
    return out.read_text(encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--size", default="1024x512", help="WxH of the generated pattern image")
    ap.add_argument(
        "--image", type=Path, help="a real image file instead of the pattern (e.g. a basemap .webp)"
    )
    ap.add_argument("--rows", type=int, default=64, help="rows per strip")
    ap.add_argument("--gpu", action="store_true", help="headed, real GPU (default: headless)")
    ap.add_argument(
        "--finish", action="store_true", help="time each copy including GPU completion (gl.finish)"
    )
    ap.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    ap.add_argument(
        "--tolerance", type=int, default=0, help="largest channel difference that still passes"
    )
    args = ap.parse_args(argv)
    width, height = (int(v) for v in args.size.lower().split("x"))
    image_b64 = base64.b64encode(args.image.read_bytes()).decode() if args.image else None

    run_dir = ROOT / "output" / "globe_probe" / f"strip-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        script = bundle(Path(tmp))

    with sync_playwright() as pw:
        engine = getattr(pw, args.browser)
        launch: dict = {"headless": not args.gpu}
        if args.browser == "chromium" and args.gpu:
            launch["args"] = [
                "--ignore-gpu-blocklist",
                "--enable-gpu",
                "--disable-backgrounding-occluded-windows",
            ]
        browser = engine.launch(**launch)
        page = browser.new_page()
        console: list[str] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.set_content("<!doctype html><title>strip upload check</title>")
        page.add_script_tag(content=script)
        report = page.evaluate(
            "([w, h, r, f, i]) => window.runStripCheck(w, h, r, f, i)",
            [width, height, args.rows, args.finish, image_b64],
        )
        report["browser"] = f"{args.browser} {browser.version}"
        report["image"] = str(args.image) if args.image else f"pattern {width}x{height}"
        report["console"] = console
        browser.close()

    tol = args.tolerance
    checks = {
        f"strip texture matches the mirrored legacy <img> texture, level 0 (max diff <= {tol})": report[
            "stripsVsLegacyLevel0"
        ]["maxAbsDiff"]
        <= tol,
        f"whole texture matches the mirrored legacy <img> texture, level 0 (max diff <= {tol})": report[
            "wholeVsLegacyLevel0"
        ]["maxAbsDiff"]
        <= tol,
        f"strip mip level 1 matches the mirrored legacy mip level 1 (max diff <= {tol})": report[
            "stripsVsLegacyLevel1"
        ]["maxAbsDiff"]
        <= tol,
        "mip level 1 was generated": report["level1NonZero"],
        "no GL error pending": report["glError"] == 0,
        "strip source never entered the renderer": not report["sourceRegistered"],
        "one copy per strip plus the mip copy": report["copies"]
        == -(-report["height"] // args.rows) + 1,
        "destination ends at version 1 with generateMipmaps back at false": report[
            "stripsGenerateMipmapsAtEnd"
        ]
        is False
        and report["stripsVersion"] == 1,
        "bitmap closed after the strips": report["bitmapClosedAfterStrips"],
    }
    if report["orientation"] is not None:
        o = report["orientation"]
        checks[f"texture row r holds image row r (max diff <= {tol})"] = (
            o["unflipped"]["maxAbsDiff"] <= tol
        )
        checks["texture is not the mirrored image"] = o["flipped"]["maxAbsDiff"] > 16
    report["checks"] = checks
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + name)
    for key in ("stripsVsLegacyLevel0", "wholeVsLegacyLevel0", "stripsVsLegacyLevel1"):
        c = report[key]
        print(
            f"  {key}: max diff {c['maxAbsDiff']}, {c['differingShare'] * 100:.3f} % of channels differ"
        )
    print(
        f"{report['browser']} | {report['renderer']} | {report['image']} {report['width']}x{report['height']} "
        f"in {args.rows}-row strips: {report['copies']} copies, median {report['copyMsMedian']:.2f} ms, "
        f"max {report['copyMsMax']:.2f} ms, wall {report['stripWallMs']:.0f} ms"
    )
    print(
        f"  allocation (initTexture) ms: {report['stripInitMs']}, getError ms: {report['stripGetErrorMs']}"
    )
    print(f"report: {run_dir / 'report.json'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
