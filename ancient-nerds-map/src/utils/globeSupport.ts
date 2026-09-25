/**
 * Can this browser show the 3D globe? Checked once, before <Globe> mounts,
 * on a throw-away canvas: three r182 needs a WebGL 2 context with the
 * renderer's attributes, and the smallest basemap needs a texture limit of
 * MIN_BASEMAP_TEXTURE_SIZE. When either is missing, App shows the unsupported
 * screen (and tracks globe_unsupported) instead of mounting a renderer that
 * would throw.
 *
 * A software renderer (hardware acceleration off) passes: it can run the
 * globe, slowly, and HardwareWarning tells the visitor.
 */

import { RENDERER_ATTRIBUTES } from '../config/globeConstants'
import { MIN_BASEMAP_TEXTURE_SIZE } from './deviceTier'

export type GlobeSupport =
  | { ok: true }
  | { ok: false; reason: 'no_webgl2' | 'max_texture_size'; detail: string | undefined }

/** What the check needs of a canvas (an HTMLCanvasElement; tests pass a fake). */
interface ProbeCanvas {
  getContext(kind: 'webgl2', attributes: WebGLContextAttributes): WebGL2RenderingContext | null
  addEventListener(type: 'webglcontextcreationerror', listener: (e: Event) => void): void
  removeEventListener(type: 'webglcontextcreationerror', listener: (e: Event) => void): void
}

export function checkGlobeSupport(canvas: ProbeCanvas): GlobeSupport {
  // Engines that dispatch webglcontextcreationerror do it inside getContext and
  // say why there; the others give no reason, so the detail is optional.
  let status = ''
  const onCreationError = (e: Event) => { status = (e as WebGLContextEvent).statusMessage }
  canvas.addEventListener('webglcontextcreationerror', onCreationError)
  const gl = canvas.getContext('webgl2', RENDERER_ATTRIBUTES)
  canvas.removeEventListener('webglcontextcreationerror', onCreationError)
  if (!gl) return { ok: false, reason: 'no_webgl2', detail: status || undefined }

  const maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE) as number
  // Release the probe context now: browsers cap the live WebGL contexts per page
  gl.getExtension('WEBGL_lose_context')?.loseContext()
  return maxTextureSize < MIN_BASEMAP_TEXTURE_SIZE
    ? { ok: false, reason: 'max_texture_size', detail: String(maxTextureSize) }
    : { ok: true }
}
