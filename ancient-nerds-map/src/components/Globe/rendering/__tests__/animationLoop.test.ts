/**
 * The two branches that stop the loop. three.js compiles its programs inside
 * renderer.render(), so on a dead context gl.createShader() returns null and
 * shaderSource throws out of the frame callback — with the next frame already
 * booked. Both checks therefore run BEFORE requestAnimationFrame, and that
 * order is the whole fix: it is what turns a runaway loop into one webgl_lost
 * event the Problems panel can rank.
 *
 * No DOM needed: both branches return before the first frame is scheduled, so
 * a fake context and a renderer stub are enough.
 */

import { describe, expect, it, vi } from 'vitest'

import { type AnimationLoopContext, runAnimationLoop } from '../animationLoop'

function ctxWith(lost: boolean, contextLost: boolean) {
  const onContextLost = vi.fn()
  const booked = vi.fn()
  vi.stubGlobal('requestAnimationFrame', booked)
  const ctx = {
    renderer: { getContext: () => ({ isContextLost: () => contextLost }) },
    webglContextLostRef: { current: lost },
    isPageVisibleRef: { current: true },
    animationId: { value: 0 },
    onContextLost,
  } as unknown as AnimationLoopContext
  return { ctx, onContextLost, booked }
}

describe('runAnimationLoop', () => {
  it('stops and reports once when the context was already lost', () => {
    const { ctx, onContextLost, booked } = ctxWith(true, false)
    runAnimationLoop(ctx)
    expect(onContextLost).toHaveBeenCalledExactlyOnceWith('context_lost')
    expect(booked).not.toHaveBeenCalled()
  })

  it('stops and reports when the renderer hands back a dead context', () => {
    const { ctx, onContextLost, booked } = ctxWith(false, true)
    runAnimationLoop(ctx)
    expect(onContextLost).toHaveBeenCalledExactlyOnceWith('no_shader')
    // The flag is set here, so the restore handler knows there is a loop to
    // restart and a second frame cannot report the same loss again.
    expect(ctx.webglContextLostRef.current).toBe(true)
    expect(booked).not.toHaveBeenCalled()
  })
})
