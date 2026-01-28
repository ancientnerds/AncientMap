import * as THREE from 'three'
import { ANIMATION, EASING } from '../config/globeConstants'

/**
 * FadeManager - Unified opacity animations for all map layers
 *
 * Manages smooth fade transitions for THREE.js materials with:
 * - Cancelable animations (prevents conflicts when toggling layers rapidly)
 * - Support for ShaderMaterial uniforms (uOpacity, opacity) and basic materials
 * - Configurable duration and easing
 * - Completion callbacks
 */
export class FadeManager {
  private animations = new Map<string, number>()  // key -> requestAnimationFrame id

  /**
   * Smoothly fade materials to a target opacity
   * @param key - Unique identifier for this animation (for cancellation)
   * @param materials - Array of THREE.Material to animate
   * @param targetOpacity - Target opacity value (0-1)
   * @param options - Optional configuration
   */
  fadeTo(
    key: string,
    materials: THREE.Material[],
    targetOpacity: number,
    options: { duration?: number; onComplete?: () => void } = {}
  ): void {
    this.cancel(key)
    if (materials.length === 0) return

    const duration = options.duration ?? ANIMATION.FADE_DURATION
    const startOpacity = this.getOpacity(materials[0])

    // Skip if already at target
    if (Math.abs(startOpacity - targetOpacity) < 0.01) {
      options.onComplete?.()
      return
    }

    const startTime = performance.now()
    const animate = () => {
      const progress = Math.min(1, (performance.now() - startTime) / duration)
      const opacity = startOpacity + (targetOpacity - startOpacity) * EASING.easeOutCubic(progress)
      materials.forEach(mat => this.setOpacity(mat, opacity))

      if (progress < 1) {
        this.animations.set(key, requestAnimationFrame(animate))
      } else {
        this.animations.delete(key)
        options.onComplete?.()
      }
    }
    this.animations.set(key, requestAnimationFrame(animate))
  }

  /**
   * Fade materials in (to opacity 1)
   */
  fadeIn(key: string, materials: THREE.Material[], options?: { duration?: number; onComplete?: () => void }): void {
    this.fadeTo(key, materials, 1, options)
  }

  /**
   * Fade materials out (to opacity 0)
   */
  fadeOut(key: string, materials: THREE.Material[], options?: { duration?: number; onComplete?: () => void }): void {
    this.fadeTo(key, materials, 0, options)
  }

  /**
   * Cancel an ongoing animation
   */
  cancel(key: string): void {
    const id = this.animations.get(key)
    if (id) {
      cancelAnimationFrame(id)
      this.animations.delete(key)
    }
  }

  /**
   * Cancel all animations and clean up
   */
  dispose(): void {
    this.animations.forEach((_, key) => this.cancel(key))
  }

  /**
   * Check if an animation is currently running
   */
  isAnimating(key: string): boolean {
    return this.animations.has(key)
  }

  /**
   * Get current opacity from a material
   */
  private getOpacity(mat: THREE.Material): number {
    const shader = mat as THREE.ShaderMaterial
    if (shader.uniforms?.uOpacity) return shader.uniforms.uOpacity.value
    if (shader.uniforms?.opacity) return shader.uniforms.opacity.value
    return (mat as THREE.PointsMaterial).opacity ?? 1
  }

  /**
   * Set opacity on a material
   */
  private setOpacity(mat: THREE.Material, value: number): void {
    const shader = mat as THREE.ShaderMaterial
    if (shader.uniforms?.uOpacity) {
      shader.uniforms.uOpacity.value = value
    } else if (shader.uniforms?.opacity) {
      shader.uniforms.opacity.value = value
    } else {
      (mat as THREE.PointsMaterial).opacity = value
    }
  }
}

// Singleton instance for global use
export const globalFadeManager = new FadeManager()
