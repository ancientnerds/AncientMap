/**
 * The GPU proof of the render browser (spec 2026-09-26 section 4.11): the
 * WebGL renderer string of the Chrome that renders the frames. The
 * compositions' calculateMetadata puts it into their props, so every node
 * script reads it from selectComposition() in the same browser that will
 * render, and refuses anything but the NVIDIA (scripts/args.ts nvidiaProblem).
 */

/** UNMASKED_RENDERER_WEBGL of a fresh WebGL context, e.g. "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 ...)". */
export function webglRenderer(): string {
  const canvas = document.createElement('canvas')
  const gl = (canvas.getContext('webgl2') ?? canvas.getContext('webgl')) as WebGLRenderingContext | null
  if (!gl) throw new Error('the render browser has no WebGL context')
  const info = gl.getExtension('WEBGL_debug_renderer_info')
  if (!info) throw new Error('the render browser hides its WebGL renderer (no WEBGL_debug_renderer_info)')
  return String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL))
}
