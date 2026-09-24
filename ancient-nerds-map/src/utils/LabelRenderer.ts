import * as THREE from 'three'
import { LABEL_STYLES, LABEL_BASE_SCALE, ATLAS_FONT_FAMILY, ANIMATION, EFFECTS, GEO, CUDDLE, EASING } from '../config/globeConstants'
import { FadeManager } from './FadeManager'

// Earth radius for scale calculations
const EARTH_RADIUS_KM = GEO.EARTH_RADIUS_KM

// =============================================================================
// CANVAS-BASED LABEL SYSTEM - WebGL sprites for performance
// =============================================================================

// Cache for label textures to avoid regenerating
const labelTextureCache = new Map<string, THREE.CanvasTexture>()

// Clear cache on HMR to pick up style changes
if (import.meta.hot) {
  import.meta.hot.dispose(() => labelTextureCache.clear())
}

/** The typography of a label: what its texture is measured and drawn with. */
interface LabelTypography {
  style: (typeof LABEL_STYLES)[string]
  /** Canvas font size: the style's size at 3x, so the text stays crisp when shown smaller */
  fontSize: number
  font: string
  letterSpacing: string
  displayText: string
}

function labelTypography(text: string, type: string, isNational?: boolean): LabelTypography {
  const styleKey = (type === 'capital' && isNational) ? 'capitalNat' : type
  const style = LABEL_STYLES[styleKey] || LABEL_STYLES.country
  const fontSize = style.fontSize * 3

  // Orbitron to match branding
  const fontStyle = style.italic ? 'italic ' : ''
  const fontWeight = style.bold ? '600 ' : '400 '

  // Letter spacing scaled by font size
  const baseSpacing = Math.round(2 + (style.fontSize - 18) * 14 / 46)
  const spacingMultiplier = (type === 'continent' || type === 'ocean') ? 3 : ((type === 'sea' || type === 'country') ? 2 : 1)

  return {
    style,
    fontSize,
    font: `${fontStyle}${fontWeight}${fontSize}px ${ATLAS_FONT_FAMILY}`,
    letterSpacing: `${baseSpacing * spacingMultiplier}px`,
    displayText: style.uppercase ? text.toUpperCase() : text,
  }
}

/** One 2D context for every measurement; created on the first call (no DOM at module scope). */
let measureContext: CanvasRenderingContext2D | null = null

/**
 * The size of the texture `createLabelTexture` draws for a label, in canvas
 * pixels, from `measureText` alone: text width plus a shadow padding on each
 * side. A geo label's mesh gets its aspect from this at load; the texture
 * itself is drawn when the label is first shown.
 */
export function measureLabel(text: string, type: string, isNational?: boolean): { width: number; height: number } {
  const t = labelTypography(text, type, isNational)
  if (!measureContext) measureContext = document.createElement('canvas').getContext('2d')!
  measureContext.font = t.font
  measureContext.letterSpacing = t.letterSpacing
  const textWidth = measureContext.measureText(t.displayText).width
  const textHeight = t.fontSize * 1.4
  const padding = t.fontSize * 0.6
  return { width: Math.ceil(textWidth + padding * 2), height: Math.ceil(textHeight + padding * 2) }
}

/**
 * Create a canvas texture for a text label, sized by `measureLabel`.
 * Uses cached textures when available for performance
 */
export function createLabelTexture(
  text: string,
  type: string,
  isNational?: boolean
): { texture: THREE.CanvasTexture; width: number; height: number } {
  const styleKey = (type === 'capital' && isNational) ? 'capitalNat' : type

  // Check cache
  const cacheKey = `${text}_${styleKey}`
  const cached = labelTextureCache.get(cacheKey)
  if (cached) {
    return { texture: cached, width: cached.image.width, height: cached.image.height }
  }

  const t = labelTypography(text, type, isNational)
  const { width, height } = measureLabel(text, type, isNational)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d', { willReadFrequently: false })!

  // Enable high-quality antialiasing
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.font = t.font
  ctx.letterSpacing = t.letterSpacing
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'center'

  // Draw label with unified styling
  drawUnifiedLabel(ctx, t.displayText, width / 2, height / 2, t.fontSize, t.style.color, {
    bold: t.style.bold,
    italic: t.style.italic,
  })

  // Create texture with high-quality filtering for stable appearance
  const texture = new THREE.CanvasTexture(canvas)
  texture.minFilter = THREE.LinearMipmapLinearFilter  // Trilinear filtering for smooth scaling
  texture.magFilter = THREE.LinearFilter
  texture.anisotropy = 4  // Anisotropic filtering for better quality at angles
  texture.generateMipmaps = true
  texture.needsUpdate = true

  // Cache it
  labelTextureCache.set(cacheKey, texture)

  return { texture, width, height }
}

/**
 * Unified label styling - professional cartographic technique using strokeText halo
 * Based on Mapbox/Google Maps best practices for readable map labels
 */
export function drawUnifiedLabel(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  fontSize: number,
  textColor: string,
  options?: {
    bold?: boolean
    italic?: boolean
  }
): void {
  const fontWeight = options?.bold ? '600 ' : '400 '
  const fontStyle = options?.italic ? 'italic ' : ''
  ctx.font = `${fontStyle}${fontWeight}${fontSize}px ${ATLAS_FONT_FAMILY}`

  // Layer 1: Subtle drop shadow for depth
  ctx.shadowColor = 'rgba(0, 0, 0, 0.35)'
  ctx.shadowBlur = 3
  ctx.shadowOffsetX = 1
  ctx.shadowOffsetY = 2

  // Layer 2: Black halo/stroke - draw FIRST (critical for proper layering)
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.95)'
  ctx.lineWidth = Math.max(4, fontSize * 0.22)  // 22% of font size, min 4px
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.strokeText(text, x, y)
  ctx.strokeText(text, x, y)
  ctx.strokeText(text, x, y)  // Triple pass for solid coverage

  // Reset shadow for clean fill
  ctx.shadowColor = 'transparent'
  ctx.shadowBlur = 0
  ctx.shadowOffsetX = 0
  ctx.shadowOffsetY = 0

  // Layer 3: Main text fill - draw SECOND
  ctx.fillStyle = textColor
  ctx.fillText(text, x, y)
}

// Alias for backward compatibility
export const drawLabelWithShadow = drawUnifiedLabel

// =============================================================================
// GLOBE LABEL MESH SYSTEM
// =============================================================================

// Extended mesh type with label metadata
export interface GlobeLabelMesh extends THREE.Mesh {
  userData: {
    baseScale: number  // Base scale factor for screen-size calculation
    aspect: number     // Width/height aspect ratio
    hasOffset?: boolean  // True if label has stacking offset applied
    originalPosition?: THREE.Vector3  // For cuddle system - original position before offset
    cuddleOffset?: THREE.Vector3      // For cuddle system - current displacement
    empireId?: string   // For empire labels - the empire ID
  }
}

// Cached curved geometry - subdivided plane with 32 horizontal segments for smooth curving
const curvedLabelGeometry = new THREE.PlaneGeometry(1, 1, 32, 1)

/**
 * Shader material that curves labels to follow globe surface
 * All vertices are projected to the same distance from globe center as the label position
 * Labels fade in from horizon (edge) toward camera, hidden on back side
 */
export function createCurvedLabelMaterial(texture: THREE.Texture | null): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      map: { value: texture },
      opacity: { value: 1.0 }
    },
    vertexShader: `
      varying vec2 vUv;
      varying float vViewFade;

      void main() {
        vUv = uv;

        // Transform vertex to world space
        vec4 worldPos = modelMatrix * vec4(position, 1.0);

        // Get the label center's distance from globe center (from translation in model matrix)
        vec3 labelCenter = modelMatrix[3].xyz;
        float labelRadius = length(labelCenter);

        // Project this vertex onto sphere at that radius
        vec3 normalized = normalize(worldPos.xyz);
        worldPos.xyz = normalized * labelRadius;

        // Calculate view-dependent fade based on angle to camera
        vec3 labelDir = normalize(labelCenter);
        vec3 cameraDir = normalize(cameraPosition);
        float dotProduct = dot(labelDir, cameraDir);

        // Fade zone: wider band for visible transition
        vViewFade = smoothstep(${EFFECTS.HORIZON_FADE_START.toFixed(1)}, ${EFFECTS.HORIZON_FADE_END.toFixed(1)}, dotProduct);

        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      varying vec2 vUv;
      varying float vViewFade;
      uniform sampler2D map;
      uniform float opacity;

      void main() {
        vec4 texColor = texture2D(map, vUv);
        float finalOpacity = texColor.a * opacity * vViewFade;
        gl_FragColor = vec4(texColor.rgb, finalOpacity);
      }
    `,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    side: THREE.FrontSide
  })
}

/**
 * Create a label mesh that is tangent to the globe surface
 * Maintains constant screen size via dynamic scaling
 * `texture` null: a geo label whose texture is drawn when it is first shown;
 * `aspect` is then the texture's size to come (`measureLabel`).
 */
export function createGlobeTangentLabel(
  texture: THREE.Texture | null,
  position: THREE.Vector3,
  baseScale: number,
  aspect: number,
  renderOrder: number = 1000
): GlobeLabelMesh {
  const material = createCurvedLabelMaterial(texture)

  // Start with opacity 0 for fade-in effect
  material.uniforms.opacity.value = 0

  const mesh = new THREE.Mesh(curvedLabelGeometry, material)
  mesh.renderOrder = renderOrder

  // Position on globe surface
  mesh.position.copy(position)

  // Orient to be tangent to globe (face outward from center)
  mesh.lookAt(position.clone().multiplyScalar(2))

  // Store base scale info for dynamic scaling
  mesh.userData = { baseScale, aspect }

  return mesh as unknown as GlobeLabelMesh
}

/**
 * Fade a label in with animation
 */
export function fadeLabelIn(mesh: GlobeLabelMesh, fadeManager: FadeManager, key: string): void {
  const material = mesh.material as THREE.ShaderMaterial
  // A geo label gets its texture on the show path; a mesh without one must never draw
  if (material.uniforms?.map && !material.uniforms.map.value) {
    throw new Error(`Label ${key} shown without its texture`)
  }
  if (material.uniforms?.opacity) {
    mesh.visible = true
    fadeManager.fadeTo(key, [material], 1, { duration: ANIMATION.LABEL_FADE_DURATION })
  }
}

/**
 * Fade a label out (hides after fade completes)
 */
export function fadeLabelOut(mesh: GlobeLabelMesh, fadeManager: FadeManager, key: string): void {
  const material = mesh.material as THREE.ShaderMaterial
  if (material.uniforms?.opacity) {
    fadeManager.fadeTo(key, [material], 0, {
      duration: ANIMATION.LABEL_FADE_DURATION,
      onComplete: () => { mesh.visible = false }
    })
  }
}

/**
 * Update label mesh scale to maintain constant screen size using kmPerPixel
 * This accounts for both camera distance AND FOV (telephoto effect)
 */
export function updateGlobeLabelScale(mesh: GlobeLabelMesh, kmPerPixel: number): void {
  const { baseScale, aspect } = mesh.userData
  // baseScale represents target size as fraction of globe
  // Convert to pixels, then back to 3D units using current kmPerPixel
  const targetPixels = baseScale * 800  // baseScale 0.04 → 32 pixels, 0.10 → 80 pixels
  const kmSize = targetPixels * kmPerPixel
  const scale = kmSize / EARTH_RADIUS_KM
  mesh.scale.set(scale * aspect, scale, 1)
}

/**
 * Animate capital label cuddle offset (push apart from country label)
 * Smoothly moves labels to avoid overlaps
 */
export function animateCuddleOffset(
  mesh: GlobeLabelMesh,
  key: string,
  targetOffset: THREE.Vector3 | null,
  originalPosition: THREE.Vector3,
  cuddleAnimations: Map<string, number>
): void {
  // Cancel existing animation
  const existing = cuddleAnimations.get(key)
  if (existing) cancelAnimationFrame(existing)

  const originalRadius = originalPosition.length()
  const startPos = mesh.position.clone()

  // Calculate end position: add offset then project back onto sphere at original radius
  let endPos: THREE.Vector3
  if (targetOffset) {
    endPos = originalPosition.clone().add(targetOffset)
    endPos.normalize().multiplyScalar(originalRadius) // Keep on globe surface
  } else {
    endPos = originalPosition.clone()
  }

  // Skip if already at target
  if (startPos.distanceTo(endPos) < 0.0001) return

  const startTime = performance.now()
  const duration = CUDDLE.DURATION

  const animate = () => {
    const progress = Math.min(1, (performance.now() - startTime) / duration)
    const eased = EASING.easeOutCubic(progress)

    mesh.position.lerpVectors(startPos, endPos, eased)
    // Ensure we stay on sphere surface during animation
    mesh.position.normalize().multiplyScalar(originalRadius)
    mesh.lookAt(mesh.position.clone().multiplyScalar(2)) // Keep tangent to globe

    if (progress < 1) {
      cuddleAnimations.set(key, requestAnimationFrame(animate))
    } else {
      cuddleAnimations.delete(key)
    }
  }

  cuddleAnimations.set(key, requestAnimationFrame(animate))
}

/**
 * Get the base scale for a label type
 */
export function getLabelBaseScale(type: string): number {
  return LABEL_BASE_SCALE[type] ?? LABEL_BASE_SCALE.country
}

/**
 * Clear the texture cache and the measuring canvas (hot reloading, tests)
 */
export function clearLabelTextureCache(): void {
  labelTextureCache.clear()
  measureContext = null
}

/**
 * Dispose of a label mesh and its resources
 */
export function disposeLabelMesh(mesh: GlobeLabelMesh): void {
  const material = mesh.material as THREE.ShaderMaterial
  if (material.uniforms?.map?.value) {
    material.uniforms.map.value.dispose()
  }
  material.dispose()
  mesh.geometry.dispose()
}
