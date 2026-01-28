declare module 'troika-three-text' {
  import { Object3D, Color, Material, Quaternion, Vector3 } from 'three'

  export class Text extends Object3D {
    text: string
    fontSize: number
    color: number | string | Color
    anchorX: 'left' | 'center' | 'right' | number
    anchorY: 'top' | 'top-baseline' | 'top-cap' | 'top-ex' | 'middle' | 'bottom-baseline' | 'bottom' | number
    font?: string
    fontWeight?: string | number
    fontStyle?: 'normal' | 'italic'
    letterSpacing?: number
    lineHeight?: number | 'normal'
    maxWidth?: number
    overflowWrap?: 'normal' | 'break-word'
    textAlign?: 'left' | 'right' | 'center' | 'justify'
    textIndent?: number
    whiteSpace?: 'normal' | 'nowrap'
    material?: Material
    outlineWidth?: number | string
    outlineColor?: number | string | Color
    outlineOpacity?: number
    outlineBlur?: number | string
    outlineOffsetX?: number | string
    outlineOffsetY?: number | string
    strokeWidth?: number | string
    strokeColor?: number | string | Color
    strokeOpacity?: number
    fillOpacity?: number
    depthOffset?: number
    clipRect?: [number, number, number, number] | null
    orientation?: string
    glyphGeometryDetail?: number
    sdfGlyphSize?: number
    gpuAccelerateSDF?: boolean

    // Curved text support
    curveRadius?: number  // Negative = convex (text wraps around outside of curve)
    direction?: 'auto' | 'ltr' | 'rtl'

    // Inherited from Object3D
    visible: boolean
    position: Vector3
    quaternion: Quaternion

    sync(callback?: () => void): void
    dispose(): void
  }
}
