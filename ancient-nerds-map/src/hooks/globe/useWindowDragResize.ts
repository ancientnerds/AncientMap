import { useCallback, useRef } from 'react'

export interface WindowDragResizeOptions {
  position: { x: number; y: number }
  width: number
  height: number
  onPositionChange: (pos: { x: number; y: number }) => void
  onWidthChange: (width: number) => void
  onHeightChange: (height: number) => void
  minWidth?: number
  minHeight?: number
  onResizeStart?: () => void
  onResizeEnd?: () => void
  onDragStart?: () => void
  onDragEnd?: () => void
}

export interface WindowDragResizeHandlers {
  startResize: (e: React.MouseEvent, direction: string) => void
  handlePositionDragStart: (e: React.MouseEvent) => void
}

export function useWindowDragResize({
  position,
  width,
  height,
  onPositionChange,
  onWidthChange,
  onHeightChange,
  minWidth = 200,
  minHeight = 150,
  onResizeStart,
  onResizeEnd,
  onDragStart,
  onDragEnd,
}: WindowDragResizeOptions): WindowDragResizeHandlers {
  const startPosRef = useRef({ x: 0, y: 0 })
  const startDimsRef = useRef({ width: 0, height: 0 })

  const startResize = useCallback(
    (e: React.MouseEvent, direction: string) => {
      e.preventDefault()
      e.stopPropagation()
      onResizeStart?.()

      const startX = e.clientX
      const startY = e.clientY
      startPosRef.current = { x: position.x, y: position.y }
      startDimsRef.current = { width, height }

      const onMove = (e: MouseEvent) => {
        const deltaX = e.clientX - startX
        const deltaY = e.clientY - startY

        let newWidth = startDimsRef.current.width
        let newHeight = startDimsRef.current.height
        let newX = startPosRef.current.x
        let newY = startPosRef.current.y

        const startBottom = startPosRef.current.y + startDimsRef.current.height

        if (direction.includes('e')) {
          // Dragging east → right edge moves → width grows, left edge fixed
          newWidth = Math.max(minWidth, startDimsRef.current.width + deltaX)
        }
        if (direction.includes('w')) {
          // Dragging west → left edge moves → width shrinks, right edge fixed
          const widthChange = Math.min(deltaX, startDimsRef.current.width - minWidth)
          newWidth = startDimsRef.current.width - widthChange
          newX = startPosRef.current.x + widthChange
        }
        if (direction.includes('s')) {
          // Dragging south → bottom edge moves → height grows, top edge fixed
          newHeight = Math.max(minHeight, startDimsRef.current.height + deltaY)
        }
        if (direction.includes('n')) {
          // Dragging north → top edge moves → height grows from fixed bottom edge
          newY = startPosRef.current.y + deltaY
          newHeight = startBottom - newY
        }

        // Clamp only axes NOT being resized
        const clampX = !direction.includes('e') && !direction.includes('w')
        const clampY = !direction.includes('n') && !direction.includes('s')
        if (clampX) newX = Math.max(0, Math.min(newX, window.innerWidth - newWidth))
        if (clampY) {
          newY = Math.max(0, Math.min(newY, window.innerHeight - newHeight))
        }

        // North resize: top can go to 0 but not above (max 0), height = fixed bottom - newTop
        if (direction.includes('n')) {
          newY = Math.max(0, newY)
        }

        onWidthChange(newWidth)
        onHeightChange(newHeight)
        onPositionChange({ x: newX, y: newY })
      }

      const onUp = () => {
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        onResizeEnd?.()
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [position, width, height, onPositionChange, onWidthChange, onHeightChange, minWidth, minHeight, onResizeStart, onResizeEnd]
  )

  const handlePositionDragStart = useCallback(
    (e: React.MouseEvent) => {
      if ((e.target as HTMLElement).closest('.panel-close-btn')) return
      e.preventDefault()
      e.stopPropagation()
      onDragStart?.()

      const startX = e.clientX
      const startY = e.clientY
      startPosRef.current = { x: position.x, y: position.y }

      const onMove = (e: MouseEvent) => {
        const deltaX = e.clientX - startX
        const deltaY = e.clientY - startY

        let newX = startPosRef.current.x + deltaX
        let newY = startPosRef.current.y + deltaY

        newX = Math.max(0, Math.min(newX, window.innerWidth - width))
        newY = Math.max(0, Math.min(newY, window.innerHeight - height))

        onPositionChange({ x: newX, y: newY })
      }

      const onUp = () => {
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        onDragEnd?.()
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [position, width, height, onPositionChange, onDragStart, onDragEnd]
  )

  return { startResize, handlePositionDragStart }
}
