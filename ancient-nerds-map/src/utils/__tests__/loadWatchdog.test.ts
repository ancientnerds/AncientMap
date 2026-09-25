/**
 * The loading watchdog: when no critical item of the start has progressed for
 * 20 s of visible time, the overlay offers a reload. Timers only - no
 * requestAnimationFrame, which never runs in a hidden tab.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { START_STALL_MS, createStallWatchdog } from '../loadWatchdog'

describe('createStallWatchdog', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('waits 20 s', () => {
    expect(START_STALL_MS).toBe(20_000)
  })

  it('fires once after the timeout without progress', () => {
    const onStall = vi.fn()
    createStallWatchdog({ timeoutMs: 1000, onStall })
    vi.advanceTimersByTime(999)
    expect(onStall).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onStall).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(10_000)
    expect(onStall).toHaveBeenCalledOnce()
  })

  it('progress starts the wait again, also after a stall', () => {
    const onStall = vi.fn()
    const dog = createStallWatchdog({ timeoutMs: 1000, onStall })
    vi.advanceTimersByTime(900)
    dog.progress()
    vi.advanceTimersByTime(900)
    expect(onStall).not.toHaveBeenCalled()
    vi.advanceTimersByTime(100)
    expect(onStall).toHaveBeenCalledOnce()
    dog.progress()
    vi.advanceTimersByTime(1000)
    expect(onStall).toHaveBeenCalledTimes(2)
  })

  it('does not count time while paused; resuming gives a fresh wait', () => {
    const onStall = vi.fn()
    const dog = createStallWatchdog({ timeoutMs: 1000, onStall })
    vi.advanceTimersByTime(900)
    dog.pause()
    vi.advanceTimersByTime(60_000)
    expect(onStall).not.toHaveBeenCalled()
    dog.progress() // progress while hidden does not start the clock either
    vi.advanceTimersByTime(60_000)
    expect(onStall).not.toHaveBeenCalled()
    dog.resume()
    vi.advanceTimersByTime(999)
    expect(onStall).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onStall).toHaveBeenCalledOnce()
  })

  it('stop ends it for good', () => {
    const onStall = vi.fn()
    const dog = createStallWatchdog({ timeoutMs: 1000, onStall })
    dog.stop()
    dog.progress()
    dog.resume()
    vi.advanceTimersByTime(60_000)
    expect(onStall).not.toHaveBeenCalled()
  })

  it('can start paused (a load that begins in a hidden tab)', () => {
    const onStall = vi.fn()
    const dog = createStallWatchdog({ timeoutMs: 1000, onStall, paused: true })
    vi.advanceTimersByTime(5000)
    expect(onStall).not.toHaveBeenCalled()
    dog.resume()
    vi.advanceTimersByTime(1000)
    expect(onStall).toHaveBeenCalledOnce()
  })
})
