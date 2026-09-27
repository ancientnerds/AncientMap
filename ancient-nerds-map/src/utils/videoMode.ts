/**
 * Studio capture mode, `?video=1` (next to `?demo=1`): the globe as the
 * platform takes of pipeline/studio/capture/platform.py record it
 * (spec docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md 4.6).
 *
 * - hides the options panel (FPS counter, database/connector status), the
 *   social/contribute buttons, the hover tooltips and the native cursor (the
 *   capture injects its own NERV cursor);
 * - `?hud=1.3` sets the HUD scale (--hud-scale) so the UI reads on video;
 * - window.__VIDEO.ready turns true at globe_ready, when a visitor would see
 *   the globe (App.tsx), so the capture never films the loading overlay.
 *
 * Only query parameters are read: no browser storage, nothing on import, safe
 * in every render path.
 */

export interface VideoMode {
  enabled: boolean
  /** From ?hud=, null keeps the HUD's own default. */
  hudScale: number | null
}

export interface VideoState {
  ready: boolean
  hudScale: number | null
}

declare global {
  interface Window {
    __VIDEO?: VideoState
  }
}

export const HUD_MIN = 0.5
export const HUD_MAX = 2
export const VIDEO_MODE_CLASS = 'video-mode'
const STYLE_ID = 'video-mode-style'

/**
 * Hidden in video mode; class names verified against the components (OptionsPanel,
 * SocialLinks, Globe). The label of the selected site also carries .site-hover-tooltip
 * (TooltipOverlay.tsx: "site-hover-tooltip selected-site-label"); after click_result it
 * is the answer of the take, so only hover tooltips are hidden.
 */
export const VIDEO_MODE_HIDDEN = [
  '.info-panel-top-right',
  '.social-contribute-wrapper',
  '.fps-display-container',
  '.database-status-indicator',
  '.connectors-status-indicator',
  '.site-hover-tooltip:not(.selected-site-label)',
  '.fps-warning-tooltip',
  '.hardware-warning-banner',
] as const

export const VIDEO_MODE_CSS =
  `${VIDEO_MODE_HIDDEN.map((s) => `body.${VIDEO_MODE_CLASS} ${s}`).join(',\n')} { display: none !important; }\n` +
  `body.${VIDEO_MODE_CLASS}, body.${VIDEO_MODE_CLASS} * { cursor: none !important; }`

/** Read the mode from a query string; an out-of-range ?hud= is an error, not a silent default. */
export function parseVideoMode(search: string): VideoMode {
  const params = new URLSearchParams(search)
  if (params.get('video') !== '1') return { enabled: false, hudScale: null }
  const raw = params.get('hud')
  if (raw === null) return { enabled: true, hudScale: null }
  const hud = Number(raw)
  if (raw.trim() === '' || !Number.isFinite(hud) || hud < HUD_MIN || hud > HUD_MAX) {
    throw new Error(`?hud=${raw}: expected a number between ${HUD_MIN} and ${HUD_MAX}`)
  }
  return { enabled: true, hudScale: hud }
}

/** Switch video mode on (style + body class + window.__VIDEO); returns the cleanup. */
export function applyVideoMode(mode: VideoMode, doc: Document, win: Window): () => void {
  if (!mode.enabled) return () => undefined
  const style = doc.createElement('style')
  style.id = STYLE_ID
  style.textContent = VIDEO_MODE_CSS
  doc.head.appendChild(style)
  doc.body.classList.add(VIDEO_MODE_CLASS)
  win.__VIDEO = { ready: false, hudScale: mode.hudScale }
  return () => {
    style.remove()
    doc.body.classList.remove(VIDEO_MODE_CLASS)
    delete win.__VIDEO
  }
}

/** globe_ready: the capture may start. A no-op outside video mode. */
export function markVideoReady(win: Window): void {
  if (win.__VIDEO) win.__VIDEO.ready = true
}
