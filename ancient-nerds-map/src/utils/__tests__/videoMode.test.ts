/**
 * ?video=1 is the studio's capture mode (pipeline/studio/capture/platform.py):
 * panels and tooltips hidden, ?hud= scale, window.__VIDEO.ready at globe_ready.
 * It reads only the query string, never browser storage.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  HUD_MAX,
  VIDEO_MODE_CLASS,
  VIDEO_MODE_CSS,
  applyVideoMode,
  markVideoReady,
  parseVideoMode,
} from '../videoMode'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('parseVideoMode', () => {
  it('is off without ?video=1, even with ?hud=', () => {
    expect(parseVideoMode('')).toEqual({ enabled: false, hudScale: null })
    expect(parseVideoMode('?demo=1&hud=1.3')).toEqual({ enabled: false, hudScale: null })
    expect(parseVideoMode('?video=0')).toEqual({ enabled: false, hudScale: null })
  })

  it('reads the HUD scale next to demo mode', () => {
    expect(parseVideoMode('?demo=1&video=1')).toEqual({ enabled: true, hudScale: null })
    expect(parseVideoMode('?demo=1&video=1&hud=1.3')).toEqual({ enabled: true, hudScale: 1.3 })
  })

  it.each(['abc', '', '0.2', String(HUD_MAX + 1)])('rejects ?hud=%s', (hud) => {
    expect(() => parseVideoMode(`?video=1&hud=${hud}`)).toThrow(/expected a number between/)
  })
})

function fakeDom() {
  const classes = new Set<string>()
  const appended: { id: string; textContent: string; remove: () => void }[] = []
  const style = { id: '', textContent: '', remove: vi.fn() }
  const doc = {
    createElement: vi.fn(() => style),
    head: { appendChild: vi.fn((el: typeof style) => appended.push(el)) },
    body: { classList: { add: (c: string) => classes.add(c), remove: (c: string) => classes.delete(c) } },
  }
  return { doc: doc as unknown as Document, classes, appended, style }
}

describe('applyVideoMode', () => {
  it('does nothing outside video mode', () => {
    const { doc, classes } = fakeDom()
    const win = {} as Window
    applyVideoMode({ enabled: false, hudScale: null }, doc, win)()
    expect(classes.size).toBe(0)
    expect(win.__VIDEO).toBeUndefined()
  })

  it('adds the style and body class, exposes __VIDEO and undoes it all', () => {
    const { doc, classes, appended, style } = fakeDom()
    const win = {} as Window
    const cleanup = applyVideoMode({ enabled: true, hudScale: 1.3 }, doc, win)
    expect(classes.has(VIDEO_MODE_CLASS)).toBe(true)
    expect(appended[0].textContent).toBe(VIDEO_MODE_CSS)
    expect(win.__VIDEO).toEqual({ ready: false, hudScale: 1.3 })
    markVideoReady(win)
    expect(win.__VIDEO?.ready).toBe(true)
    cleanup()
    expect(classes.has(VIDEO_MODE_CLASS)).toBe(false)
    expect(style.remove).toHaveBeenCalledOnce()
    expect(win.__VIDEO).toBeUndefined()
  })

  it('hides the panels the spec names and the native cursor', () => {
    for (const selector of ['.info-panel-top-right', '.social-contribute-wrapper', '.fps-display-container', '.site-hover-tooltip']) {
      expect(VIDEO_MODE_CSS).toContain(`body.video-mode ${selector}`)
    }
    expect(VIDEO_MODE_CSS).toContain('cursor: none !important')
  })

  it('keeps the label of the selected site (the answer of a search moment), hiding only hover tooltips', () => {
    expect(VIDEO_MODE_CSS).toContain('body.video-mode .site-hover-tooltip:not(.selected-site-label)')
    expect(VIDEO_MODE_CSS).not.toMatch(/\.site-hover-tooltip,/)
  })

  it('never touches browser storage', () => {
    const trap = new Proxy({}, { get: () => { throw new Error('storage touched') } })
    vi.stubGlobal('localStorage', trap)
    vi.stubGlobal('sessionStorage', trap)
    const { doc } = fakeDom()
    const win = {} as Window
    applyVideoMode(parseVideoMode('?video=1&hud=1.2'), doc, win)
    markVideoReady(win)
    expect(win.__VIDEO?.ready).toBe(true)
  })
})

describe('markVideoReady', () => {
  it('is a no-op outside video mode', () => {
    const win = {} as Window
    markVideoReady(win)
    expect(win.__VIDEO).toBeUndefined()
  })
})
