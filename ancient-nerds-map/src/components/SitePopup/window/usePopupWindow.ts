import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import type {
  WindowState,
  WindowPosition,
  WindowSize,
  WindowDragStart,
  WindowResizeStart
} from '../types'

const MIN_WIDTH = 400
const MIN_HEIGHT = 300

interface UsePopupWindowOptions {
  isStandalone?: boolean
  minimizedStackIndex?: number
  onMinimizedChange?: (isMinimized: boolean) => void
}

interface UsePopupWindowReturn {
  // State
  windowState: WindowState
  position: WindowPosition
  size: WindowSize
  isDragging: boolean
  isResizing: boolean
  isPositioned: boolean

  // Refs
  popupRef: React.RefObject<HTMLDivElement>
  savedStateRef: React.MutableRefObject<{ x: number; y: number; width: number; height: number }>

  // Handlers
  handleTitleBarMouseDown: (e: React.MouseEvent) => void
  handleTitleBarDoubleClick: () => void
  handleMinimize: (e: React.MouseEvent) => void
  handleMaximize: (e: React.MouseEvent) => void
  startResize: (e: React.MouseEvent, direction: string) => void

  // Computed
  popupStyle: React.CSSProperties

  // Window class names
  windowClasses: string
}

export function usePopupWindow({
  isStandalone = false,
  minimizedStackIndex = -1,
  onMinimizedChange
}: UsePopupWindowOptions): UsePopupWindowReturn {
  // Window management state
  const [windowState, setWindowState] = useState<WindowState>('normal')
  const [position, setPosition] = useState<WindowPosition>({ x: 0, y: 0 })
  const [size, setSize] = useState<WindowSize>({ width: 0, height: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [resizeDirection, setResizeDirection] = useState('')
  const [isPositioned, setIsPositioned] = useState(false)

  // Refs for window management
  const popupRef = useRef<HTMLDivElement>(null)
  const dragStartRef = useRef<WindowDragStart>({ x: 0, y: 0, posX: 0, posY: 0 })
  const resizeStartRef = useRef<WindowResizeStart>({ x: 0, y: 0, width: 0, height: 0, posX: 0, posY: 0 })

  // Saved state for restore from maximize
  const savedStateRef = useRef({ x: 0, y: 0, width: 0, height: 0 })

  // Sync internal windowState with parent's minimized state (via minimizedStackIndex prop)
  useEffect(() => {
    if (minimizedStackIndex >= 0 && windowState !== 'minimized') {
      setWindowState('minimized')
    } else if (minimizedStackIndex === -1 && windowState === 'minimized') {
      setWindowState('normal')
    }
  }, [minimizedStackIndex, windowState])

  // Initialize position and size on mount
  useEffect(() => {
    if (popupRef.current && !isPositioned && !isStandalone) {
      const rect = popupRef.current.getBoundingClientRect()
      const initialWidth = rect.width
      const initialHeight = rect.height
      setSize({ width: initialWidth, height: initialHeight })
      setPosition({
        x: (window.innerWidth - initialWidth) / 2,
        y: (window.innerHeight - initialHeight) / 2
      })
      savedStateRef.current = {
        x: (window.innerWidth - initialWidth) / 2,
        y: (window.innerHeight - initialHeight) / 2,
        width: initialWidth,
        height: initialHeight
      }
      setIsPositioned(true)
    }
  }, [isPositioned, isStandalone])

  // Title bar drag handlers
  const handleTitleBarMouseDown = useCallback((e: React.MouseEvent) => {
    if (windowState === 'maximized' || isStandalone) return
    e.preventDefault()
    setIsDragging(true)
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      posX: position.x,
      posY: position.y
    }
  }, [windowState, position, isStandalone])

  // Double-click to toggle maximize
  const handleTitleBarDoubleClick = useCallback(() => {
    if (isStandalone) return
    if (windowState === 'maximized') {
      setWindowState('normal')
      setPosition({ x: savedStateRef.current.x, y: savedStateRef.current.y })
      setSize({ width: savedStateRef.current.width, height: savedStateRef.current.height })
    } else {
      savedStateRef.current = { x: position.x, y: position.y, width: size.width, height: size.height }
      setWindowState('maximized')
    }
  }, [windowState, position, size, isStandalone])

  // Resize handlers
  const startResize = useCallback((e: React.MouseEvent, direction: string) => {
    if (windowState !== 'normal' || isStandalone) return
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
    setResizeDirection(direction)
    resizeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      width: size.width,
      height: size.height,
      posX: position.x,
      posY: position.y
    }
  }, [windowState, size, position, isStandalone])

  // Window control actions
  const handleMinimize = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (windowState === 'minimized') {
      // Restoring from minimized - clamp position to fit on screen
      const newX = Math.max(0, Math.min(window.innerWidth - size.width, position.x))
      const newY = Math.max(0, Math.min(window.innerHeight - size.height, position.y))
      setPosition({ x: newX, y: newY })
      setWindowState('normal')
      onMinimizedChange?.(false)
    } else {
      setWindowState('minimized')
      onMinimizedChange?.(true)
    }
  }, [windowState, position, size, onMinimizedChange])

  const handleMaximize = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (windowState === 'maximized') {
      // Restoring from maximized - clamp position to fit on screen
      const restoreWidth = savedStateRef.current.width
      const restoreHeight = savedStateRef.current.height
      const newX = Math.max(0, Math.min(window.innerWidth - restoreWidth, savedStateRef.current.x))
      const newY = Math.max(0, Math.min(window.innerHeight - restoreHeight, savedStateRef.current.y))
      setPosition({ x: newX, y: newY })
      setSize({ width: restoreWidth, height: restoreHeight })
      setWindowState('normal')
    } else {
      // Save current state before maximizing (only if not minimized)
      if (windowState !== 'minimized') {
        savedStateRef.current = { x: position.x, y: position.y, width: size.width, height: size.height }
      }
      setWindowState('maximized')
    }
  }, [windowState, position, size])

  // Global mouse move/up handlers for drag and resize
  useEffect(() => {
    if (isStandalone) return

    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        const deltaX = e.clientX - dragStartRef.current.x
        const deltaY = e.clientY - dragStartRef.current.y
        let newX = dragStartRef.current.posX + deltaX
        let newY = dragStartRef.current.posY + deltaY

        // Use actual current dimensions (minimized = 280x32, otherwise stored size)
        const currentWidth = windowState === 'minimized' ? 280 : size.width
        const currentHeight = windowState === 'minimized' ? 32 : size.height

        // Keep within bounds
        newX = Math.max(0, Math.min(window.innerWidth - currentWidth, newX))
        newY = Math.max(0, Math.min(window.innerHeight - currentHeight, newY))

        setPosition({ x: newX, y: newY })
      }

      if (isResizing) {
        const deltaX = e.clientX - resizeStartRef.current.x
        const deltaY = e.clientY - resizeStartRef.current.y
        let newWidth = resizeStartRef.current.width
        let newHeight = resizeStartRef.current.height
        let newX = resizeStartRef.current.posX
        let newY = resizeStartRef.current.posY

        // Handle resize based on direction
        if (resizeDirection.includes('e')) {
          newWidth = Math.max(MIN_WIDTH, resizeStartRef.current.width + deltaX)
        }
        if (resizeDirection.includes('w')) {
          const widthChange = Math.min(deltaX, resizeStartRef.current.width - MIN_WIDTH)
          newWidth = resizeStartRef.current.width - widthChange
          newX = resizeStartRef.current.posX + widthChange
        }
        if (resizeDirection.includes('s')) {
          newHeight = Math.max(MIN_HEIGHT, resizeStartRef.current.height + deltaY)
        }
        if (resizeDirection.includes('n')) {
          const heightChange = Math.min(deltaY, resizeStartRef.current.height - MIN_HEIGHT)
          newHeight = resizeStartRef.current.height - heightChange
          newY = resizeStartRef.current.posY + heightChange
        }

        // Clamp to screen bounds
        newWidth = Math.min(newWidth, window.innerWidth - newX)
        newHeight = Math.min(newHeight, window.innerHeight - newY)
        newX = Math.max(0, newX)
        newY = Math.max(0, newY)

        setSize({ width: newWidth, height: newHeight })
        setPosition({ x: newX, y: newY })
      }
    }

    const handleMouseUp = () => {
      setIsDragging(false)
      setIsResizing(false)
      setResizeDirection('')
    }

    if (isDragging || isResizing) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
      return () => {
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [isDragging, isResizing, resizeDirection, size.width, size.height, isStandalone, windowState])

  // Compute popup style based on window state
  const popupStyle = useMemo((): React.CSSProperties => {
    if (isStandalone) return {}
    if (!isPositioned) return { opacity: 0, zIndex: 1000 } // Hide until positioned

    if (windowState === 'maximized') {
      return {
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        borderRadius: 0,
        zIndex: 1000
      }
    }

    // Minimized: stack at lower-left corner
    if (windowState === 'minimized') {
      const stackOffset = (minimizedStackIndex >= 0 ? minimizedStackIndex : 0) * 40 // 32px height + 8px gap
      return {
        position: 'fixed',
        left: 20,
        bottom: 20 + stackOffset,
        width: 280, // Compact width for minimized state
        height: 32,
        zIndex: 1000 + (minimizedStackIndex >= 0 ? minimizedStackIndex : 0)
      }
    }

    return {
      position: 'fixed',
      left: position.x,
      top: position.y,
      width: size.width || undefined,
      height: size.height || undefined,
      zIndex: 1000
    }
  }, [isStandalone, isPositioned, windowState, position, size, minimizedStackIndex])

  // Window state class names
  const windowClasses = useMemo(() => {
    return [
      'site-popup',
      'site-popup-large',
      isStandalone ? 'standalone' : 'windowed',
      windowState === 'minimized' ? 'minimized' : '',
      windowState === 'maximized' ? 'maximized' : '',
      isDragging ? 'dragging' : '',
      isResizing ? 'resizing' : ''
    ].filter(Boolean).join(' ')
  }, [isStandalone, windowState, isDragging, isResizing])

  return {
    // State
    windowState,
    position,
    size,
    isDragging,
    isResizing,
    isPositioned,

    // Refs
    popupRef,
    savedStateRef,

    // Handlers
    handleTitleBarMouseDown,
    handleTitleBarDoubleClick,
    handleMinimize,
    handleMaximize,
    startResize,

    // Computed
    popupStyle,
    windowClasses
  }
}
