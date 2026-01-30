import type { ResizeHandlesProps } from '../types'

export function ResizeHandles({ onStartResize }: ResizeHandlesProps) {
  return (
    <>
      <div className="resize-handle resize-n" onMouseDown={(e) => onStartResize(e, 'n')} />
      <div className="resize-handle resize-s" onMouseDown={(e) => onStartResize(e, 's')} />
      <div className="resize-handle resize-e" onMouseDown={(e) => onStartResize(e, 'e')} />
      <div className="resize-handle resize-w" onMouseDown={(e) => onStartResize(e, 'w')} />
      <div className="resize-handle resize-ne" onMouseDown={(e) => onStartResize(e, 'ne')} />
      <div className="resize-handle resize-nw" onMouseDown={(e) => onStartResize(e, 'nw')} />
      <div className="resize-handle resize-se" onMouseDown={(e) => onStartResize(e, 'se')} />
      <div className="resize-handle resize-sw" onMouseDown={(e) => onStartResize(e, 'sw')} />
    </>
  )
}
