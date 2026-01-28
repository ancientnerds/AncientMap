/**
 * useTextureLoading - Hook for managing texture loading and application
 *
 * Consolidates:
 * - High quality texture loading (gray basemap, satellite)
 * - Texture application to mesh materials
 * - Low FPS warning delay
 * - Texture ready state management
 */

import { useEffect, useState } from 'react'
import * as THREE from 'three'
import type { GlobeRefs } from './types'

interface UseTextureLoadingOptions {
  refs: GlobeRefs
  sceneReady: boolean
}

interface UseTextureLoadingReturn {
  texturesReady: boolean
  backgroundLoadingComplete: boolean
  lowFpsReady: boolean
}

export function useTextureLoading({
  refs,
  sceneReady,
}: UseTextureLoadingOptions): UseTextureLoadingReturn {
  const [texturesReady, setTexturesReady] = useState(false)
  const [backgroundLoadingComplete, setBackgroundLoadingComplete] = useState(false)
  const [lowFpsReady, setLowFpsReady] = useState(false)

  // Texel size for high resolution textures (16384x8192)
  const texelSize = new THREE.Vector2(1.0 / 16384, 1.0 / 8192)

  // Load HIGH quality textures DURING INITIAL LOADING SCREEN
  useEffect(() => {
    if (!sceneReady) return

    console.log('[Loading] Starting texture loading...')
    const loader = new THREE.TextureLoader()
    let loadedCount = 0
    const totalTextures = 2

    const checkAllLoaded = () => {
      loadedCount++
      if (loadedCount >= totalTextures) {
        console.log('[Loading] Textures DONE')
        refs.highResGrayLoaded.current = true
        refs.highResSatelliteLoaded.current = true
        refs.backgroundLoadingComplete.current = true
        setBackgroundLoadingComplete(true)
        setTexturesReady(true)
      }
    }

    // Load HIGH quality grayscale basemap
    loader.load('/data/basemaps/gray_dark_high.webp', (texture) => {
      console.log('[Loading] Gray basemap loaded')
      texture.colorSpace = THREE.SRGBColorSpace
      texture.generateMipmaps = true
      texture.minFilter = THREE.LinearMipmapLinearFilter
      texture.magFilter = THREE.LinearFilter
      texture.anisotropy = 16
      refs.textureCache.current.grayBasemap = texture
      checkAllLoaded()
    }, undefined, (err) => {
      console.error('[Loading] FAILED to load gray basemap:', err)
      checkAllLoaded() // Still count as loaded to not block forever
    })

    // Load HIGH quality satellite
    loader.load('/data/basemaps/satellite_high.webp', (texture) => {
      console.log('[Loading] Satellite loaded')
      texture.colorSpace = THREE.SRGBColorSpace
      texture.generateMipmaps = true
      texture.minFilter = THREE.LinearMipmapLinearFilter
      texture.magFilter = THREE.LinearFilter
      texture.anisotropy = 16
      refs.textureCache.current.satellite = texture
      checkAllLoaded()
    }, undefined, (err) => {
      console.error('[Loading] FAILED to load satellite:', err)
      checkAllLoaded() // Still count as loaded to not block forever
    })

    return () => {
      refs.textureCache.current.grayBasemap?.dispose()
      refs.textureCache.current.satellite?.dispose()
    }
  }, [sceneReady, refs.highResGrayLoaded, refs.highResSatelliteLoaded, refs.backgroundLoadingComplete, refs.textureCache])

  // Apply high quality textures when loaded (and load land mask first)
  useEffect(() => {
    const basemapMesh = refs.basemapMesh.current
    if (!basemapMesh || !sceneReady) return

    const material = basemapMesh.material as THREE.ShaderMaterial
    const allFrontMaterials = [material, ...refs.basemapSectionMeshes.current.map(m => m.material as THREE.ShaderMaterial)]

    // Set texel size for back mesh blur effect (front materials don't use it)
    const backMesh = refs.basemapBackMesh.current
    if (backMesh) {
      const backMaterial = backMesh.material as THREE.ShaderMaterial
      backMaterial.uniforms.uTexelSize.value = texelSize
    }

    // Apply cached textures (poll if not ready yet)
    // Note: Land mask disabled temporarily - was causing visibility issues
    const applyTextures = () => {
      const cache = refs.textureCache.current
      const { grayBasemap, satellite } = cache

      if (grayBasemap && satellite) {
        // Apply textures to front materials
        allFrontMaterials.forEach(mat => {
          mat.uniforms.uGrayBasemap.value = grayBasemap
          mat.uniforms.uSatellite.value = satellite
          mat.needsUpdate = true
        })
        basemapMesh.visible = true

        // Apply to back mesh for glass blur effect
        // Access ref directly to avoid stale closure issues
        const basemapBackMesh = refs.basemapBackMesh.current
        if (basemapBackMesh) {
          const backMaterial = basemapBackMesh.material as THREE.ShaderMaterial
          backMaterial.uniforms.uGrayBasemap.value = grayBasemap
          backMaterial.uniforms.uSatellite.value = satellite
          backMaterial.uniforms.uUseSatellite.value = false  // Ensure satellite mode uniform is initialized
          backMaterial.needsUpdate = true

          // Back mesh disabled - no blur effect, just darker elements
          // Keep it hidden
          if (refs.basemapBackMesh.current) {
            refs.basemapBackMesh.current.visible = false
          }
        }

        setTexturesReady(true)
        return true
      }
      return false
    }

    // Try immediately, then poll
    if (!applyTextures()) {
      const interval = setInterval(() => {
        if (applyTextures()) {
          clearInterval(interval)
        }
      }, 100)
      // Cleanup on unmount
      return () => clearInterval(interval)
    }
  }, [sceneReady, refs.basemapMesh, refs.basemapBackMesh, refs.basemapSectionMeshes, refs.textureCache])

  // Delay low FPS warning until scene is fully loaded + 3 second buffer
  useEffect(() => {
    if (!sceneReady) return
    const timer = setTimeout(() => setLowFpsReady(true), 3000)
    return () => clearTimeout(timer)
  }, [sceneReady])

  // CRITICAL: Force basemap visible when textures become ready
  // This is a separate effect to ensure it runs when texturesReady state changes
  useEffect(() => {
    refs.texturesReady.current = texturesReady

    if (!texturesReady) return

    // Force basemap visible
    const basemapMesh = refs.basemapMesh.current
    if (basemapMesh && !basemapMesh.visible) {
      basemapMesh.visible = true
    }

    // Hide globe base visual (set opacity to 0, NOT visible=false which hides children/vector layers)
    const sceneData = refs.scene.current
    const globeBase = sceneData?.globe
    if (globeBase && basemapMesh?.visible) {
      const globeMaterial = globeBase.material as THREE.MeshBasicMaterial
      globeMaterial.opacity = 0
    }

    // Force render if we have a scene
    if (sceneData) {
      const { renderer, scene, camera } = sceneData
      renderer.render(scene, camera)
    }
  }, [texturesReady, refs.texturesReady, refs.basemapMesh, refs.scene])

  return {
    texturesReady,
    backgroundLoadingComplete,
    lowFpsReady,
  }
}
