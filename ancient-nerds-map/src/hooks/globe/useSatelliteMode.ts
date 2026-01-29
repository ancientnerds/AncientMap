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
  satellite: boolean
  vectorLayers: Record<VectorLayerKey, boolean>
  showMapbox: boolean
  mapboxServiceRef?: React.MutableRefObject<MapboxGlobeService | null>
}

export function useSatelliteMode({
  refs,
  satellite,
  vectorLayers,
  showMapbox,
  mapboxServiceRef,
}: UseSatelliteModeOptions): void {
  // Handle satellite mode toggle (textures already loaded by LOD effect)
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

    const material = basemapMesh.material as THREE.ShaderMaterial
    const sectionMaterials = refs.basemapSectionMeshes.current.map(m => m.material as THREE.ShaderMaterial)
    const allMaterials = [material, ...sectionMaterials]

    // FORCE basemap visible if textures are loaded (fixes initial load issue)
    const cache = refs.textureCache.current
    if (cache.grayBasemap && cache.satellite && !basemapMesh.visible) {
      basemapMesh.visible = true
    }

    // Hide globe base visual when basemap is visible (set opacity to 0, NOT visible=false)
    // Setting visible=false would hide vector layers which are children of globe
    if (globeBase && basemapMesh?.visible) {
      const globeMaterial = globeBase.material as THREE.MeshBasicMaterial
      globeMaterial.opacity = 0
    }

    // Toggle satellite mode uniform
    allMaterials.forEach(mat => {
      mat.uniforms.uUseSatellite.value = satellite
      mat.needsUpdate = true
    })

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
  }, [satellite, vectorLayers, showMapbox, refs.satelliteMode, refs.basemapMesh, refs.basemapBackMesh, refs.basemapSectionMeshes, refs.textureCache, refs.backLineLayers, refs.scene, refs.stars])
}
