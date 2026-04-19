import React from 'react'
import type { WindowDragResizeHandlers } from '../../../hooks/globe/useWindowDragResize'

const RESIZE_DIRECTIONS = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'] as const

export interface WindowFrameProps {
  className: string
  position: { x: number; y: number }
  width: number
  height: number
  title: string
  onClose: () => void
  dragResizeHandlers: WindowDragResizeHandlers
  headerClassName?: string
  children: React.ReactNode
}

export function WindowFrame({
  className,
  position,
  width,
  height,
  title,
  onClose,
  dragResizeHandlers,
  headerClassName = 'window-frame-header',
  children,
}: WindowFrameProps) {
  return (
    <div
      className={className}
      style={{
        width,
        height,
        left: position.x,
        bottom: position.y,
      } as React.CSSProperties}
    >
      {RESIZE_DIRECTIONS.map(dir => (
        <div
          key={dir}
          className={`resize-${dir}`}
          onMouseDown={e => dragResizeHandlers.startResize(e, dir)}
        />
      ))}

      <div
        className={headerClassName}
        onMouseDown={dragResizeHandlers.handlePositionDragStart}
      >
        <div className="panel-label">{title}</div>
        <button
          className="panel-close-btn"
          onClick={onClose}
          title="Close"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      {children}
    </div>
  )
}
