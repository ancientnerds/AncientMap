/**
 * empireHoverUtils.ts - Empire hover detection and state management
 *
 * Handles:
 * 1. Detecting which empire is under the cursor
 * 2. Managing hover state transitions (opacity changes)
 * 3. Respecting site dot priority (dead zones)
 */

import * as THREE from 'three'
import type { SiteData } from '../../../data/sites'
import { setEmpireHoverState } from '../../../shaders/globe/empireMaterials'

/** Refs needed for empire hover management */
export interface EmpireHoverRefs {
  hoveredEmpireRef: React.MutableRefObject<string | null>
  empireBorderLinesRef: React.MutableRefObject<Record<string, THREE.Line[]>>
  empireFillMeshesRef: React.MutableRefObject<Record<string, THREE.Mesh[]>>
}

/** Result of empire hover detection */
export interface EmpireHoverResult {
  /** The empire ID being hovered, or null */
  empireId: string | null
  /** Whether the hover state changed from previous */
  changed: boolean
  /** Whether cursor is over a site (empire hover should be skipped) */
  blockedBySite: boolean
}

/**
 * Detect which empire (if any) is under the cursor
 * Note: Sites take priority for CLICKS, but both can show hover effects
 *
 * @param screenX - Screen X coordinate (pixels)
 * @param screenY - Screen Y coordinate (pixels)
 * @param camera - Three.js camera
 * @param globe - Globe mesh to traverse for empire fill meshes
 * @returns Empire ID or null
 */
export function detectEmpireUnderCursor(
  screenX: number,
  screenY: number,
  camera: THREE.PerspectiveCamera,
  globe: THREE.Mesh
): string | null {
  // Find all empire fill meshes
  const empireMeshes: THREE.Mesh[] = []
  globe.traverse((child) => {
    if (child.userData?.empireId && child.userData?.isFillMesh && child instanceof THREE.Mesh) {
      empireMeshes.push(child)
    }
  })

  if (empireMeshes.length === 0) {
    return null
  }

  // Raycast to find empire under cursor
  const raycaster = new THREE.Raycaster()
  const mouse = new THREE.Vector2(
    (screenX / window.innerWidth) * 2 - 1,
    -(screenY / window.innerHeight) * 2 + 1
  )
  raycaster.setFromCamera(mouse, camera)
  const hits = raycaster.intersectObjects(empireMeshes)

  if (hits.length > 0) {
    // Find the first visible hit with an empireId
    for (const hit of hits) {
      const empireId = hit.object.userData?.empireId
      if (empireId && hit.object.visible) {
        return empireId
      }
    }
  }

  return null
}

/**
 * Update empire hover state and visual effects
 * Call this from mousemove handler
 * Note: Empire hover is shown even when site is hovered (both can highlight)
 *
 * @returns EmpireHoverResult with the new state
 */
export function updateEmpireHoverState(
  screenX: number,
  screenY: number,
  camera: THREE.PerspectiveCamera,
  globe: THREE.Mesh,
  refs: EmpireHoverRefs
): EmpireHoverResult {
  const { hoveredEmpireRef, empireBorderLinesRef, empireFillMeshesRef } = refs

  // Detect empire under cursor
  const newHoveredEmpire = detectEmpireUnderCursor(
    screenX,
    screenY,
    camera,
    globe
  )

  const prevHoveredEmpire = hoveredEmpireRef.current
  const changed = newHoveredEmpire !== prevHoveredEmpire

  // Only update visuals if state changed
  if (changed) {
    // Clear previous hover state
    if (prevHoveredEmpire) {
      const prevFillMeshes = empireFillMeshesRef.current[prevHoveredEmpire] || []
      const prevBorderLines = empireBorderLinesRef.current[prevHoveredEmpire] || []
      setEmpireHoverState(prevFillMeshes, prevBorderLines, false)
    }

    // Set new hover state
    if (newHoveredEmpire) {
      const fillMeshes = empireFillMeshesRef.current[newHoveredEmpire] || []
      const borderLines = empireBorderLinesRef.current[newHoveredEmpire] || []
      setEmpireHoverState(fillMeshes, borderLines, true)
    }

    hoveredEmpireRef.current = newHoveredEmpire
  }

  return {
    empireId: newHoveredEmpire,
    changed,
    blockedBySite: false
  }
}

/**
 * Clear empire hover state (call on mouseleave)
 */
export function clearEmpireHoverState(refs: EmpireHoverRefs): void {
  const { hoveredEmpireRef, empireBorderLinesRef, empireFillMeshesRef } = refs

  if (hoveredEmpireRef.current) {
    const fillMeshes = empireFillMeshesRef.current[hoveredEmpireRef.current] || []
    const borderLines = empireBorderLinesRef.current[hoveredEmpireRef.current] || []
    setEmpireHoverState(fillMeshes, borderLines, false)
    hoveredEmpireRef.current = null
  }
}

/**
 * Determine cursor style based on hover state
 * Priority: site > empire > default (crosshair)
 */
export function getHoverCursorStyle(
  hoveredSite: SiteData | null,
  hoveredEmpire: string | null
): 'pointer' | 'crosshair' {
  if (hoveredSite) return 'pointer'
  if (hoveredEmpire) return 'pointer'
  return 'crosshair'
}
