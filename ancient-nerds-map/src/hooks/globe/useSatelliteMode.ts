/**
 * useSatelliteMode - Hook for managing satellite mode toggle
 *
 * Consolidates:
 * - Satellite mode toggle effect
 * - Body class toggle for CSS styling
 * - Shader uniform updates for basemap materials
 * - Back layer visibility management (vectors, dots, empire fills)
 */

import { useEffect } from 'react'
import * as THREE from 'three'
import type { GlobeRefs } from './types'
import type { VectorLayerKey } from '../../config/vectorLayers'
import type { MapboxGlobeService } from '../../services/MapboxGlobeService'

interface UseSatelliteModeOptions {
  refs: GlobeRefs
  /** The active satellite: switched on and loaded (stays on through a context loss). */
  satellite: boolean
  /** The shader samples the satellite: active and its texture on the GPU (false while a restore reloads it). */
  satelliteShown: boolean
  vectorLayers: Record<VectorLayerKey, boolean>
  showMapbox: boolean
  mapboxServiceRef?: React.MutableRefObject<MapboxGlobeService | null>
}

export function useSatelliteMode({
  refs,
  satellite,
  satelliteShown,
  vectorLayers,
  showMapbox,
  mapboxServiceRef,
}: UseSatelliteModeOptions): void {
  // Handle satellite mode toggle. `satellite` is the active state: switched on
  // AND loaded once (useTextureLoading's satelliteReady, which stays true through a
  // context loss); the shader follows `satelliteShown` instead.
  useEffect(() => {
    // Sync ref for useCallback closures
    refs.satelliteMode.current = satellite

    // Sync Mapbox style when satellite mode changes
    const mapboxService = mapboxServiceRef?.current
    if (mapboxService?.getIsInitialized()) {
      mapboxService.setStyle(satellite ? 'satellite' : 'dark')
    }

    // Toggle body class for CSS styling (glass effect adjustments)
    if (satellite) {
      document.body.classList.add('satellite-mode')
    } else {
      document.body.classList.remove('satellite-mode')
    }

    const basemapMesh = refs.basemapMesh.current
    const basemapBackMesh = refs.basemapBackMesh.current
    const globeBase = refs.scene.current?.globe
    if (!basemapMesh) return

    // FORCE basemap visible once the start-tier gray is on the GPU (fixes initial load issue)
    if (refs.texturesReady.current && !basemapMesh.visible) {
      basemapMesh.visible = true
    }

    // Hide globe base visual when basemap is visible (set opacity to 0, NOT visible=false)
    // Setting visible=false would hide vector layers which are children of globe
    if (globeBase && basemapMesh?.visible) {
      const globeMaterial = globeBase.material as THREE.MeshBasicMaterial
      globeMaterial.opacity = 0
    }

    // Also update back mesh (glass blur effect)
    if (basemapBackMesh) {
      // Back mesh disabled - no blur effect needed
      basemapBackMesh.visible = false
    }

    // Hide backside vectors and dots in satellite mode (satellite is fully opaque)
    const isSatellite = satellite

    // Hide/show back line layers
    Object.keys(refs.backLineLayers.current).forEach(key => {
      const backLines = refs.backLineLayers.current[key as VectorLayerKey]
      if (backLines) {
        backLines.forEach(line => {
          line.visible = !isSatellite && vectorLayers[key as VectorLayerKey]
        })
      }
    })

    // Also traverse scene to hide any back lines not in ref (renderOrder < 0 are back lines)
    refs.scene.current?.scene.traverse((obj) => {
      if (obj instanceof THREE.Line && obj.renderOrder < 0) {
        obj.visible = !isSatellite
      }
    })

    // Hide/show back dots (use ref AND traverse scene for robustness)
    if (refs.scene.current?.backPoints) {
      refs.scene.current.backPoints.visible = !isSatellite
    }
    // Also traverse scene to catch any back points not in ref
    refs.scene.current?.scene.traverse((obj) => {
      if (obj instanceof THREE.Points && obj.renderOrder < 0) {
        obj.visible = !isSatellite
      }
    })

    // Hide/show empire fill backside (update shader uniform)
    refs.scene.current?.scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh && obj.userData.empireId) {
        const mat = obj.material as THREE.ShaderMaterial
        if (mat.uniforms?.uHideBackside) {
          mat.uniforms.uHideBackside.value = isSatellite ? 1 : 0
        }
      }
    })

    // Update star shader when satellite mode changes
    const starsGroup = refs.stars.current
    const starPoints = starsGroup?.children[0] as THREE.Points | undefined
    if (starPoints) {
      const mat = starPoints.material as THREE.ShaderMaterial
      if (mat.uniforms?.uSatelliteMode) {
        mat.uniforms.uSatelliteMode.value = satellite ? 1.0 : 0.0
      }
    }
  }, [satellite, vectorLayers, showMapbox, refs.satelliteMode, refs.basemapMesh, refs.basemapBackMesh, refs.basemapSectionMeshes, refs.texturesReady, refs.backLineLayers, refs.scene, refs.stars])

  // The shader samples the satellite only while its texture is on the GPU: after
  // a context loss the restore shows the gray until the satellite is back, not
  // an empty texture.
  useEffect(() => {
    const basemapMesh = refs.basemapMesh.current
    if (!basemapMesh) return
    const allMaterials = [basemapMesh, ...refs.basemapSectionMeshes.current].map(m => m.material as THREE.ShaderMaterial)
    allMaterials.forEach(mat => {
      mat.uniforms.uUseSatellite.value = satelliteShown
      mat.needsUpdate = true
    })
  }, [satelliteShown, refs.basemapMesh, refs.basemapSectionMeshes])
}
