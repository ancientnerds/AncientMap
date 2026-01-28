import { useRef, useEffect, useCallback } from 'react'

/**
 * Animation frame callback type
 * @param deltaTime - Time since last frame in milliseconds
 * @param elapsedTime - Total elapsed time since start in milliseconds
 */
export type AnimationCallback = (deltaTime: number, elapsedTime: number) => void

/**
 * Hook for managing a requestAnimationFrame loop
 * Automatically handles cleanup and pause/resume
 *
 * @param callback - Function called each frame
 * @param isPlaying - Whether the loop is running
 * @returns Object with start, stop, and pause controls
 */
export function useAnimationLoop(
  callback: AnimationCallback,
  isPlaying: boolean = true
): {
  start: () => void
  stop: () => void
  pause: () => void
  resume: () => void
  isPaused: boolean
} {
  const frameIdRef = useRef<number | null>(null)
  const callbackRef = useRef(callback)
  const lastTimeRef = useRef<number>(0)
  const startTimeRef = useRef<number>(0)
  const isPausedRef = useRef(false)

  // Keep callback ref updated
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  const stop = useCallback(() => {
    if (frameIdRef.current !== null) {
      cancelAnimationFrame(frameIdRef.current)
      frameIdRef.current = null
    }
  }, [])

  const loop = useCallback((time: number) => {
    if (isPausedRef.current) {
      frameIdRef.current = requestAnimationFrame(loop)
      return
    }

    if (startTimeRef.current === 0) {
      startTimeRef.current = time
      lastTimeRef.current = time
    }

    const deltaTime = time - lastTimeRef.current
    const elapsedTime = time - startTimeRef.current
    lastTimeRef.current = time

    callbackRef.current(deltaTime, elapsedTime)
    frameIdRef.current = requestAnimationFrame(loop)
  }, [])

  const start = useCallback(() => {
    if (frameIdRef.current === null) {
      startTimeRef.current = 0
      lastTimeRef.current = 0
      isPausedRef.current = false
      frameIdRef.current = requestAnimationFrame(loop)
    }
  }, [loop])

  const pause = useCallback(() => {
    isPausedRef.current = true
  }, [])

  const resume = useCallback(() => {
    isPausedRef.current = false
    lastTimeRef.current = performance.now()  // Reset delta to avoid jump
  }, [])

  // Start/stop based on isPlaying prop
  useEffect(() => {
    if (isPlaying) {
      start()
    } else {
      stop()
    }
    return stop
  }, [isPlaying, start, stop])

  return {
    start,
    stop,
    pause,
    resume,
    isPaused: isPausedRef.current,
  }
}
